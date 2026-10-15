"""Bridge between PodQueue (Python) and Castria's ad-alignment engine (WASM/Node).

Castria ships its ad aligner as a Rust->WASM module. We run *their* engine
unchanged (see ``tools/castria_align``) from a short Node harness, rather than
reimplementing the fingerprint/alignment algorithm, so the gaps we compute are
exactly what the Castria client would compute for the same file.
"""

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from podqueue.config import settings
from podqueue.utils.media import get_audio_duration_seconds, merge_ranges

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")


class AlignerError(RuntimeError):
    """Raised when the Castria aligner cannot be run or returns no result."""


# Alignment is roughly single-digit multiples of realtime on a loaded host, so
# a fixed timeout starves long episodes. We allow this many seconds of wall time
# per second of audio, on top of the configured floor.
ALIGN_TIMEOUT_PER_AUDIO_SECOND = 3.0


def _node_binary() -> Optional[str]:
    return shutil.which(settings.CASTRIA_NODE_BIN) or (
        settings.CASTRIA_NODE_BIN if Path(settings.CASTRIA_NODE_BIN).exists() else None
    )


def resolve_timeout(audio_path: Path, configured: Optional[int] = None) -> int:
    """Wall-clock budget for one alignment, scaled to the file's length."""
    base = configured or settings.CASTRIA_ALIGN_TIMEOUT_SECONDS
    duration = get_audio_duration_seconds(audio_path)
    if duration:
        base = max(base, int(duration * ALIGN_TIMEOUT_PER_AUDIO_SECOND))
    return base


def exceeds_align_ceiling(duration_seconds: float, ceiling: Optional[int] = None) -> bool:
    """Whether ``duration_seconds`` is past Castria's *single-pass* ceiling.

    The vendored engine carries an internal guard (it calls it "bug-543") that
    aborts once the accumulated decoded duration of a single fingerprint session
    passes :data:`settings.CASTRIA_MAX_ALIGN_DURATION_SECONDS` (7200s / 2h by
    default). This is a per-session limit, so longer episodes are still aligned
    by splitting them into chunks (:func:`run_aligner_chunked`); it only means
    "one pass cannot cover the whole file".
    """
    limit = settings.CASTRIA_MAX_ALIGN_DURATION_SECONDS if ceiling is None else ceiling
    return bool(duration_seconds) and duration_seconds > limit


def align_chunk_seconds() -> int:
    """Length of one alignment pass (seconds), clamped below the engine ceiling."""
    ceiling = settings.CASTRIA_MAX_ALIGN_DURATION_SECONDS
    configured = settings.CASTRIA_ALIGN_CHUNK_SECONDS
    if configured <= 0:
        configured = ceiling
    return max(1, min(configured, ceiling))


def chunk_count(duration_seconds: float) -> int:
    """How many alignment passes ``duration_seconds`` needs (always >= 1)."""
    chunk = align_chunk_seconds()
    if not duration_seconds or duration_seconds <= chunk:
        return 1
    return int(math.ceil(duration_seconds / chunk))


# A gap that straddles a chunk boundary is reported as two adjacent gaps (one
# ending a chunk, one starting the next, separated only by the encoder's frame
# padding). Anything closer than this is stitched back into a single gap.
BOUNDARY_BRIDGE_SECONDS = 3.0


def bridge_ranges(ranges, tolerance: float = BOUNDARY_BRIDGE_SECONDS) -> List[Tuple[float, float]]:
    """Merge overlaps and rejoin near-adjacent ranges (chunk-boundary stitching)."""
    merged = merge_ranges(ranges)
    if tolerance <= 0:
        return merged
    out: List[Tuple[float, float]] = []
    for start, end in merged:
        if out and start - out[-1][1] <= tolerance:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _split_audio(audio_path: Path, dest_dir: Path, chunk_seconds: int) -> List[Path]:
    """Stream-copy ``audio_path`` into <= ``chunk_seconds`` pieces.

    Uses ffmpeg's segment muxer with ``-c copy`` so splitting a multi-hundred-MB
    file costs seconds and never re-encodes the audio we are about to publish.
    """
    suffix = audio_path.suffix or ".mp3"
    pattern = str(dest_dir / f"part_%03d{suffix}")
    cmd = [
        "ffmpeg", "-hide_banner", "-v", "error", "-y",
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1",
        "-c", "copy",
        pattern,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900)
    except subprocess.TimeoutExpired as e:
        raise AlignerError("timed out splitting audio for chunked alignment") from e
    except OSError as e:
        raise AlignerError(f"could not run ffmpeg to split audio: {e}") from e

    if proc.returncode != 0:
        raise AlignerError(
            f"ffmpeg split failed (code {proc.returncode}): {(proc.stderr or '').strip()[-300:]}"
        )

    parts = sorted(dest_dir.glob(f"part_*{suffix}"))
    if len(parts) < 2:
        raise AlignerError("splitting produced fewer than two chunks")
    return parts


def run_aligner_chunked(
    audio_path: Path,
    show_fingerprint_b64: str,
    chunk_seconds: Optional[int] = None,
    node_bin: Optional[str] = None,
) -> List[Tuple[float, float]]:
    """Align a file longer than the engine's single-pass ceiling, in pieces.

    Each piece is decoded by its own fingerprint session (so none trips the
    "bug-543" guard) and aligned against the same show fingerprint; the gaps are
    then shifted onto the original timeline and stitched back together. This
    reproduces a whole-file pass (see ``tests/test_castria.py``).

    Raises :class:`AlignerError` on any failure.
    """
    if shutil.which("ffmpeg") is None:
        raise AlignerError("ffmpeg is required for chunked alignment but was not found")

    chunk = chunk_seconds or align_chunk_seconds()
    with tempfile.TemporaryDirectory(prefix="castria-chunk-") as tmp:
        tmp_dir = Path(tmp)
        parts = _split_audio(audio_path, tmp_dir, chunk)
        job_logger.info(
            f"Splitting {audio_path.name} into {len(parts)} alignment chunk(s) "
            f"of up to {chunk}s (past the engine's single-pass ceiling)"
        )

        gaps: List[Tuple[float, float]] = []
        offset = 0.0
        for index, part in enumerate(parts, start=1):
            part_duration = get_audio_duration_seconds(part)
            if part_duration <= 0:
                raise AlignerError(f"could not read duration of alignment chunk {index}")
            part_gaps = run_aligner(part, show_fingerprint_b64, node_bin=node_bin)
            job_logger.info(
                f"  alignment chunk {index}/{len(parts)} @ {offset:.0f}s: {len(part_gaps)} gap(s)"
            )
            gaps.extend((start + offset, end + offset) for start, end in part_gaps)
            offset += part_duration

    return merge_ranges(bridge_ranges(gaps), get_audio_duration_seconds(audio_path) or None)


def aligner_available() -> bool:
    """True when the Node harness and its wasm payload are present."""
    tool = settings.CASTRIA_ALIGN_TOOL
    return tool.exists() and (tool.parent / "castria_adskip_wasm_bg.wasm").exists() and _node_binary() is not None


def run_aligner(
    audio_path: Path,
    show_fingerprint_b64: str,
    node_bin: Optional[str] = None,
    timeout: Optional[int] = None,
) -> List[Tuple[float, float]]:
    """Return the ad gaps (in seconds, relative to ``audio_path``).

    Feeds the show fingerprint handed out by the Castria server into the engine
    alongside our locally downloaded file, so the returned gaps account for any
    dynamic ad insertion the publisher did to *our* copy.

    Raises :class:`AlignerError` on any failure.
    """
    tool = settings.CASTRIA_ALIGN_TOOL
    if not tool.exists():
        raise AlignerError(f"aligner tool not found at {tool}")

    node = node_bin or _node_binary()
    if not node:
        raise AlignerError(
            f"Node.js runtime not found (looked for '{settings.CASTRIA_NODE_BIN}'); "
            "install Node.js or set CASTRIA_NODE_BIN"
        )

    if not show_fingerprint_b64:
        raise AlignerError("empty show fingerprint")

    if timeout is None:
        timeout = resolve_timeout(audio_path)

    fp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".castria-fp.b64", delete=False, encoding="utf-8") as fh:
            fh.write(show_fingerprint_b64.strip())
            fp_file = Path(fh.name)

        cmd = [str(node), str(tool), str(audio_path), str(fp_file)]
        # Drop CPU priority so a long alignment on a small host cannot starve
        # the web UI / SSH (the engine pegs one core for minutes at a time).
        if os.name != "nt" and shutil.which("nice"):
            cmd = ["nice", "-n", "10", *cmd]
        job_logger.info(f"Running Castria aligner on {audio_path.name} (this can take a few minutes)...")
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise AlignerError(f"aligner timed out after {timeout}s") from e
    except Exception as e:  # noqa: BLE001 - surfaced to caller
        raise AlignerError(f"failed to run aligner: {e}") from e
    finally:
        if fp_file is not None:
            try:
                fp_file.unlink(missing_ok=True)
            except OSError:
                pass

    if proc.returncode != 0:
        detail = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        raise AlignerError(f"aligner exited with code {proc.returncode}: {detail[:400]}")

    payload = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            break

    if payload is None:
        raise AlignerError("aligner produced no JSON result")

    if payload.get("error"):
        raise AlignerError(f"aligner error ({payload.get('reason', 'unknown')}): {payload['error']}")

    gaps: List[Tuple[float, float]] = []
    for pair in payload.get("gaps", []):
        try:
            start, end = float(pair[0]), float(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        if end > start:
            gaps.append((start, end))

    client_duration = payload.get("clientDuration")
    engine_version = payload.get("engineVersion")
    job_logger.info(
        f"Aligner found {len(gaps)} ad gap(s)"
        + (f" in {client_duration:.1f}s of audio" if isinstance(client_duration, (int, float)) else "")
        + (f" [engine {engine_version}]" if engine_version else "")
    )
    return gaps
