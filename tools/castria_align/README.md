# `tools/castria_align` — Castria's ad-alignment engine, driven from Node

This directory lets PodQueue compute ad-skip gaps for a **locally held podcast
file** using **Castria's own engine**, unchanged.

## Provenance

Both files are taken verbatim from the Castria Android/web app (build 1154,
package `com.extroverteddeveloper.podcastify`), from the shipped web bundle
`assets/public/assets/`:

| File here | Original asset |
|---|---|
| `castria_adskip_wasm_bg.wasm` | `castria_adskip_wasm_bg-D9KNMgHW.wasm` |
| `glue.mjs` | the wasm-bindgen glue inside `adskip.worker-C2_MPN9o.js` |

`glue.mjs` is the worker's glue with the surrounding IIFE and the
browser-worker tail (the `postMessage` / `XMLHttpRequest`-via-`/api/cdn-proxy`
plumbing) removed, plus ES-module exports. `align.mjs` is ours.

## How it works

The engine exposes two entry points (used exactly as Castria's web worker does):

```
FingerprintSession(fetchFn, totalLenBytes, sampleRate)   // streams the audio
    .step(150) ... .isDone() ... .finish()               // -> client fingerprint
detect_ads(showFingerprintBytes, clientFingerprintBytes) // -> { gaps, blocks }
```

- The **show fingerprint** is a CFP1 blob fetched from
  `GET /api/episodes/{id}/fingerprint`.
- The **client fingerprint** is computed here by streaming *our* downloaded
  file through the in-wasm decoder (symphonia). `align.mjs` supplies a
  `fetchFn` that reads byte ranges straight off disk — no network, no
  `/api/cdn-proxy`.
- `detect_ads` returns `gaps` (skip these) and `blocks` (matched show<->client
  segments), both in seconds relative to our file.

## Usage

```bash
node align.mjs <audioPath> <showFingerprintFile> [--sample-rate 11025]
```

`<showFingerprintFile>` holds the base64 `showFingerprint` string (or a JSON
body containing it). Output is a single JSON object on stdout:

```json
{"gaps": [[0,160.4],[728.18,911.01]], "blocks": [[73.98,641.71,160.4,728.18,86.45,17343]],
 "clientDuration": 914.67, "engineVersion": "0.1.0", "sampleRate": 11025}
```

PodQueue calls this via `podqueue/utils/castria_align.py`; you normally don't
run it by hand.

Requires Node.js (tested on v20/v24). Memory stays low because the file is read
in small ranges as the fingerprint session consumes it.
