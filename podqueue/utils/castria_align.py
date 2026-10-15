"""Bridge between PodQueue (Python) and Castria's ad-alignment engine (WASM/Node).

Castria ships its ad aligner as a Rust->WASM module. We run *their* engine
unchanged (see ``tools/castria_align``) from a short Node harness, rather than
reimplementing the fingerprint/alignment algorithm, so the gaps we compute are
exactly what the Castria client would compute for the same file.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from podqueue.config import settings

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")


class AlignerError(RuntimeError):
    """Raised when the Castria aligner cannot be run or returns no result."""


def _node_binary() -> Optional[str]:
    return shutil.which(settings.CASTRIA_NODE_BIN) or (
        settings.CASTRIA_NODE_BIN if Path(settings.CASTRIA_NODE_BIN).exists() else None
    )


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

    timeout = timeout or settings.CASTRIA_ALIGN_TIMEOUT_SECONDS

    fp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".castria-fp.b64", delete=False, encoding="utf-8") as fh:
            fh.write(show_fingerprint_b64.strip())
            fp_file = Path(fh.name)

        cmd = [str(node), str(tool), str(audio_path), str(fp_file)]
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
