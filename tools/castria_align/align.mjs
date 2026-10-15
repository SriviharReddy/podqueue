// Castria ad-skip aligner, run outside the browser.
//
// This drives Castria's *own* Rust->WASM engine (the same one shipped in their
// Android app / PWA) to compute the ad gaps for a podcast audio file we hold
// locally, given the show fingerprint the server hands out.
//
// Uses both exports exposed by the engine's wasm-bindgen glue:
//   FingerprintSession(fetchFn, totalLenBytes, sampleRate)  -> streams the
//       container (mp3) through the in-wasm decoder and builds the *client*
//       fingerprint of OUR file.
//   detect_ads(showFingerprintBytes, clientFingerprintBytes) -> { gaps, blocks }
//
// Usage:
//   node align.mjs <audioPath> <showFingerprintFile> [--sample-rate 11025]
//
//   <showFingerprintFile> is a file containing the base64 string returned by
//   GET /api/episodes/{id}/fingerprint  (the "showFingerprint" field).
//
// Emits a single JSON object on stdout:
//   { "gaps": [[start,end], ...], "blocks": [[aStart,aEnd,bStart,bEnd,offset,nPairs], ...],
//     "clientDuration": <seconds>, "engineVersion": "<x.y.z>", "sampleRate": 11025 }
// or, on failure, { "error": "...", "reason": "<code>" } and exit code != 0.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  initSync,
  installPanicHook,
  FingerprintSession,
  detect_ads,
  version,
} from "./glue.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WASM_PATH = path.join(HERE, "castria_adskip_wasm_bg.wasm");

// The engine decodes at 11025 Hz (matches FpParams.sr in the app).
const DEFAULT_SAMPLE_RATE = 11025;
// Chunk pace used by the shipping web worker.
const STEP_BATCH = 150;

function parseArgs(argv) {
  const positional = [];
  let sampleRate = DEFAULT_SAMPLE_RATE;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--sample-rate") {
      sampleRate = Number(argv[++i]);
    } else if (a === "--help" || a === "-h") {
      process.stdout.write(
        "usage: node align.mjs <audioPath> <showFingerprintFile> [--sample-rate N]\n",
      );
      process.exit(0);
    } else {
      positional.push(a);
    }
  }
  return { positional, sampleRate };
}

function fail(reason, message) {
  process.stdout.write(JSON.stringify({ error: message, reason }) + "\n");
  process.exit(1);
}

function readFingerprint(file) {
  const raw = fs.readFileSync(file, "utf8").trim();
  // Accept either a raw base64 blob or a JSON body that contains it.
  let b64 = raw;
  if (raw.startsWith("{")) {
    try {
      const obj = JSON.parse(raw);
      b64 = obj.showFingerprint ?? obj.showFingerprintB64 ?? raw;
    } catch {
      /* fall through: treat as base64 */
    }
  }
  b64 = b64.replace(/\s+/g, "");
  const bytes = Buffer.from(b64, "base64");
  if (bytes.length === 0) throw new Error("show fingerprint decoded to 0 bytes");
  return new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function makeLocalRangeFetcher(audioPath) {
  const fd = fs.openSync(audioPath, "r");
  const totalLen = fs.fstatSync(fd).size;
  const close = () => {
    try {
      fs.closeSync(fd);
    } catch {
      /* ignore */
    }
  };
  // Returns a Uint8Array view of exactly the requested byte range. We allocate
  // per-call and never keep the whole file resident, to stay friendly to the
  // 1 GB target box.
  const fetchFn = (offset, length) => {
    const start = Math.max(0, offset | 0);
    const end = Math.min(start + Math.max(0, length | 0), totalLen);
    const n = Math.max(0, end - start);
    const buf = Buffer.allocUnsafe(n);
    const read = n === 0 ? 0 : fs.readSync(fd, buf, 0, n, start);
    return new Uint8Array(buf.buffer, buf.byteOffset, read);
  };
  return { fetchFn, totalLen, close };
}

function main() {
  const { positional, sampleRate } = parseArgs(process.argv.slice(2));
  if (positional.length !== 2) {
    fail("usage", "expected <audioPath> <showFingerprintFile>");
  }
  const [audioPath, fpFile] = positional;

  let showFp;
  try {
    showFp = readFingerprint(fpFile);
  } catch (e) {
    fail("fingerprint-parse-failed", String(e && e.message ? e.message : e));
  }

  try {
    initSync({ module: fs.readFileSync(WASM_PATH) });
    installPanicHook();
  } catch (e) {
    fail("wasm-init-failed", String(e && e.message ? e.message : e));
  }

  let engineVersion = "";
  try {
    engineVersion = version();
  } catch {
    /* non-fatal */
  }

  let fetcher;
  try {
    fetcher = makeLocalRangeFetcher(audioPath);
  } catch (e) {
    fail("download-failed", `cannot open audio: ${e && e.message ? e.message : e}`);
  }

  try {
    const session = new FingerprintSession(
      fetcher.fetchFn,
      fetcher.totalLen,
      sampleRate,
    );
    while (!session.isDone()) {
      session.step(STEP_BATCH);
    }
    const clientFp = session.finish();
    const clientDuration = session.totalSamples() / sampleRate;

    const result = detect_ads(showFp, clientFp);
    const gaps = pairsToTimeRanges(result.gaps);
    const blocks = sextuples(result.blocks);
    result.free();

    process.stdout.write(
      JSON.stringify({
        gaps,
        blocks,
        clientDuration,
        engineVersion,
        sampleRate,
      }) + "\n",
    );
  } catch (e) {
    fail("compute-error", String(e && e.message ? e.message : e));
  } finally {
    if (fetcher) fetcher.close();
  }
}

function pairsToTimeRanges(flat) {
  const out = [];
  for (let i = 0; i + 1 < flat.length; i += 2) {
    out.push([flat[i], flat[i + 1]]);
  }
  return out;
}

function sextuples(flat) {
  const out = [];
  for (let i = 0; i + 5 < flat.length; i += 6) {
    out.push([flat[i], flat[i + 1], flat[i + 2], flat[i + 3], flat[i + 4], flat[i + 5]]);
  }
  return out;
}

main();
