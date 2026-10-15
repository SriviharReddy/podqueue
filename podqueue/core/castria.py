"""Castria ad-skip source for PodQueue.

A channel whose ``url`` starts with ``castria:`` is populated from the Castria
service (https://castria.app). For every new episode we download the publisher's
audio and *remove the ads* before publishing it through PodQueue's normal RSS
pipeline, so any podcast app (Overcast, Pocket Casts, Apple Podcasts, ...) plays
it ad-free.

Why we run Castria's own aligner instead of trusting ``adSegments``
------------------------------------------------------------------
Castria's ``GET /api/episodes/{id}`` returns ``adSegments`` (start/end seconds
plus a label such as ``pre_roll``/``sponsor_read``), but those timestamps are
measured against *Castria's* copy of the episode. Podcast hosts routinely do
**dynamic ad insertion**: the pre/mid/post-rolls your download receives can be
different and longer than the ones Castria saw (we observed a ~72s pre-roll on
the server vs ~160s in a real download of the same episode). Splicing at the
raw ``adSegments`` times therefore leaves ads behind.

Instead we ask the server for the episode's *show fingerprint*
(``GET /api/episodes/{id}/fingerprint`` -> a CFP1 blob) and hand it, together
with our local file, to Castria's own Rust->WASM alignment engine via
``tools/castria_align``. That reproduces exactly what the Castria client does
and yields the ad gaps for *our* file.

Channel URL forms
-----------------
- ``castria:<subscriptionId>``      e.g. ``castria:c7e1e018-6f86-4d53-94de-3c69990ccb7c``
- ``castria:<original feed url>``   matched against your Castria subscriptions
- ``castria:<show title>``          matched by title as a last resort
"""

import datetime
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from podqueue.config import settings
from podqueue.core.channels import Channel
from podqueue.utils.castria_align import AlignerError, exceeds_align_ceiling, run_aligner
from podqueue.utils.media import (
    cut_audio_segments,
    get_audio_duration,
    get_audio_duration_seconds,
    merge_ranges,
)

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")

CASTRIA_PREFIX = "castria:"
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# access tokens are keyed by (base_url, email) and reused for the process lifetime
_TOKEN_CACHE: Dict[str, str] = {}


class CastriaError(RuntimeError):
    pass


class CastriaAuthError(CastriaError):
    pass


class CastriaApiError(CastriaError):
    pass


# --------------------------------------------------------------------------- #
# URL handling
# --------------------------------------------------------------------------- #

def is_castria_url(url: str) -> bool:
    """True when a channel url targets the Castria source."""
    return bool(url) and url.strip().lower().startswith(CASTRIA_PREFIX)


def parse_castria_target(url: str) -> Tuple[str, str]:
    """Split a ``castria:`` url into ``("id"|"url", value)``."""
    if not is_castria_url(url):
        raise ValueError("not a castria url")
    value = url.strip()[len(CASTRIA_PREFIX):].strip().lstrip("/").strip()
    if not value:
        raise ValueError("empty castria target (expected castria:<subscriptionId|feed url|title>)")
    if _UUID_RE.match(value):
        return ("id", value)
    return ("url", value)


# --------------------------------------------------------------------------- #
# Castria API client
# --------------------------------------------------------------------------- #

class CastriaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        app_version: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or settings.CASTRIA_BASE_URL).rstrip("/")
        self.email = email if email is not None else settings.CASTRIA_EMAIL
        self.password = password if password is not None else settings.CASTRIA_PASSWORD
        self.app_version = str(app_version or settings.CASTRIA_APP_VERSION)
        self.session = session or requests.Session()
        self._token: Optional[str] = None

    # -- auth --------------------------------------------------------------
    @property
    def _cache_key(self) -> str:
        return f"{self.base_url}|{self.email}"

    def _headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {"Accept": "application/json", "X-App-Version": self.app_version}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def login(self, force: bool = False) -> str:
        if not force and self._token:
            return self._token
        if not force and _TOKEN_CACHE.get(self._cache_key):
            self._token = _TOKEN_CACHE[self._cache_key]
            return self._token
        if not self.email or not self.password:
            raise CastriaAuthError("CASTRIA_EMAIL / CASTRIA_PASSWORD are not configured")

        try:
            resp = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"emailOrUsername": self.email, "password": self.password},
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-App-Version": self.app_version},
                timeout=30,
            )
        except requests.RequestException as e:
            raise CastriaApiError(f"login request failed: {e}") from e

        if resp.status_code == 401:
            raise CastriaAuthError("Castria rejected the credentials (HTTP 401)")
        if resp.status_code >= 400:
            raise CastriaApiError(f"login failed: HTTP {resp.status_code} {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise CastriaApiError("login returned non-JSON body") from e

        token = data.get("accessToken")
        if not token:
            raise CastriaAuthError("login response did not contain an accessToken")
        self._token = token
        _TOKEN_CACHE[self._cache_key] = token
        job_logger.info(f"Authenticated with Castria as {data.get('username') or self.email}")
        return token

    # -- generic GET -------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None, timeout: int = 60) -> Optional[requests.Response]:
        self.login()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, headers=self._headers(), timeout=timeout)
        if resp.status_code == 401:
            self.login(force=True)
            resp = self.session.get(url, params=params, headers=self._headers(), timeout=timeout)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CastriaApiError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return resp

    def _get_json(self, path: str, params: Optional[dict] = None, timeout: int = 60) -> Optional[Any]:
        resp = self._get(path, params=params, timeout=timeout)
        if resp is None:
            return None
        try:
            return resp.json()
        except ValueError as e:
            raise CastriaApiError(f"GET {path} returned non-JSON body") from e

    # -- endpoints ---------------------------------------------------------
    def get_subscriptions(self) -> List[dict]:
        data = self._get_json("/api/subscriptions")
        return data if isinstance(data, list) else []

    def get_episodes(self, subscription_id: str, page_size: int = 20) -> List[dict]:
        data = self._get_json("/api/episodes", params={"subscriptionId": subscription_id, "pageSize": page_size})
        if isinstance(data, dict):
            return data.get("items") or []
        return data if isinstance(data, list) else []

    def get_episode(self, episode_id: str) -> Optional[dict]:
        data = self._get_json(f"/api/episodes/{episode_id}")
        return data if isinstance(data, dict) else None

    def get_fingerprint(self, episode_id: str) -> Optional[str]:
        data = self._get_json(f"/api/episodes/{episode_id}/fingerprint", timeout=120)
        if isinstance(data, dict):
            return data.get("showFingerprint") or data.get("showFingerprintB64")
        return None

    def get_skipplan(self, episode_id: str, file_hash: str, algo: int = 2) -> Optional[Any]:
        return self._get_json(
            f"/api/episodes/{episode_id}/showskip",
            params={"hash": file_hash, "algo": algo},
        )

    def resolve_subscription(self, kind: str, value: str) -> Optional[dict]:
        subs = self.get_subscriptions()
        value = (value or "").strip()
        if kind == "id":
            for sub in subs:
                if str(sub.get("id", "")).lower() == value.lower():
                    return sub
            return None
        # by original feed url first, then by title
        for sub in subs:
            if (sub.get("url") or "").strip() == value:
                return sub
        for sub in subs:
            if (sub.get("title") or "").strip().lower() == value.lower():
                return sub
        return None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"</?p\s*[^>]*>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _parse_pubdate(value: Any) -> Optional[datetime.datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _read_archive(archive_file: Path) -> set:
    ids = set()
    if not archive_file.exists():
        return ids
    try:
        with open(archive_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" ")
                # "youtube" lines are written by cleanup_old_episodes when it prunes.
                if len(parts) >= 2 and parts[0] in ("castria", "youtube"):
                    ids.add(parts[1])
    except OSError as e:
        job_logger.error(f"Error reading archive file: {e}")
    return ids


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _coerce_gaps(plan: Any) -> List[Tuple[float, float]]:
    """Tolerantly pull ``(start, end)`` seconds out of a /showskip response."""
    if not plan:
        return []
    gaps = None
    if isinstance(plan, dict):
        gaps = plan.get("gaps")
        if gaps is None and isinstance(plan.get("plan"), dict):
            gaps = plan["plan"].get("gaps")
    elif isinstance(plan, list):
        gaps = plan

    out: List[Tuple[float, float]] = []
    for gap in gaps or []:
        if isinstance(gap, dict):
            start, end = gap.get("start"), gap.get("end")
        elif isinstance(gap, (list, tuple)) and len(gap) >= 2:
            start, end = gap[0], gap[1]
        else:
            continue
        try:
            start, end = float(start), float(end)
        except (TypeError, ValueError):
            continue
        if end > start:
            out.append((start, end))
    return out


def _download_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }


def _download_file(url: str, temp_path: Path, headers: Dict[str, str], max_retries: int = 5) -> bool:
    """Download ``url`` to ``temp_path`` with resume support (mirrors pawchive)."""
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        downloaded_bytes = temp_path.stat().st_size if temp_path.exists() else 0

        headers_copy = dict(headers)
        if downloaded_bytes > 0:
            headers_copy["Range"] = f"bytes={downloaded_bytes}-"
            job_logger.info(f"Resuming download from byte {downloaded_bytes} (attempt {attempt}/{max_retries})...")
        else:
            job_logger.info(f"Starting download (attempt {attempt}/{max_retries})...")

        try:
            response = requests.get(url, headers=headers_copy, stream=True, timeout=30)
            if downloaded_bytes > 0:
                if response.status_code == 200:
                    job_logger.warning("Server returned 200 for a Range request; restarting from byte 0.")
                    temp_path.unlink(missing_ok=True)
                    downloaded_bytes = 0
                elif response.status_code != 206:
                    job_logger.warning(f"Server rejected Range request with {response.status_code}; restarting.")
                    temp_path.unlink(missing_ok=True)
                    downloaded_bytes = 0
                    response = requests.get(url, headers=headers, stream=True, timeout=30)

            response.raise_for_status()

            mode = "ab" if (downloaded_bytes > 0 and response.status_code == 206) else "wb"
            with open(temp_path, mode) as fh:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
            return True
        except requests.RequestException as e:
            job_logger.warning(f"Download attempt {attempt} failed: {e}")
            if attempt >= max_retries:
                return False
            time.sleep(min(30, 2 ** attempt))
    return False


def _episode_ready(episode: dict) -> bool:
    """Whether Castria has enough data for us to remove ads."""
    if episode.get("showFingerprintAvailable"):
        return True
    return str(episode.get("adStatus") or "").lower() == "completed"


def _resolve_gaps(client: CastriaClient, episode: dict, audio_path: Path) -> Tuple[List[Tuple[float, float]], str]:
    """Return ``(gaps, source)`` where source is one of
    ``skipplan|alignment|adSegments|too-long|failed|none``.

    ``failed`` means alignment was attempted but did not succeed (e.g. the
    engine timed out); ``too-long`` means the episode is past the engine's
    whole-file ceiling (2h) so alignment was not attempted; ``none`` means
    genuinely no ads were found."""
    ep_id = episode.get("id")
    alignment_failed = False

    # 1. free exact hit from the crowd skip-map cache, keyed by our file hash.
    #    It has no duration limit, so it is worth trying even for long episodes.
    try:
        file_hash = _sha256_file(audio_path)
        plan = client.get_skipplan(ep_id, file_hash)
        gaps = _coerce_gaps(plan)
        if gaps:
            job_logger.info(f"[{ep_id}] Using cached skip-map ({len(gaps)} gap(s))")
            return gaps, "skipplan"
    except CastriaError as e:
        job_logger.warning(f"[{ep_id}] skip-map lookup failed: {e}")

    # 2. run Castria's own aligner against the show fingerprint, unless the
    #    episode is longer than the engine will process in one pass.
    duration = get_audio_duration_seconds(audio_path)
    too_long = exceeds_align_ceiling(duration)
    if too_long:
        job_logger.warning(
            f"[{ep_id}] Episode is {duration:.0f}s, past Castria's "
            f"{settings.CASTRIA_MAX_ALIGN_DURATION_SECONDS}s whole-file alignment ceiling "
            '(engine "bug-543" guard); skipping the aligner.'
        )
    elif settings.CASTRIA_ALIGN_ENABLED and episode.get("showFingerprintAvailable"):
        try:
            fingerprint = client.get_fingerprint(ep_id)
            if fingerprint:
                gaps = run_aligner(audio_path, fingerprint)
                job_logger.info(f"[{ep_id}] Alignment produced {len(gaps)} gap(s)")
                return gaps, "alignment"
            alignment_failed = True
            job_logger.warning(f"[{ep_id}] server reported a fingerprint but none was returned")
        except (AlignerError, CastriaError) as e:
            alignment_failed = True
            job_logger.warning(f"[{ep_id}] Alignment failed: {e}")

    # 3. optional, inaccurate fallback
    if settings.CASTRIA_ALLOW_TIMESTAMP_FALLBACK:
        try:
            detail = client.get_episode(ep_id) or {}
            segments = detail.get("adSegments") or []
            gaps = [
                (float(s["startSeconds"]), float(s["endSeconds"]))
                for s in segments
                if float(s.get("endSeconds", 0)) > float(s.get("startSeconds", 0))
            ]
            if gaps:
                job_logger.warning(f"[{ep_id}] Falling back to raw adSegments ({len(gaps)} gap(s)); these may be off.")
                return gaps, "adSegments"
        except CastriaError as e:
            job_logger.warning(f"[{ep_id}] adSegments fallback failed: {e}")

    if too_long:
        return [], "too-long"
    return [], ("failed" if alignment_failed else "none")


def _write_info_json(
    download_dir: Path,
    episode: dict,
    channel: Channel,
    duration: int,
    gaps: List[Tuple[float, float]],
    source: str,
    removed_seconds: float,
    original_bytes: int,
) -> None:
    ep_id = episode["id"]
    pub = _parse_pubdate(episode.get("pubDate"))
    description = _strip_html(episode.get("description") or "") or (episode.get("episodeSummary") or "")
    image = episode.get("subscriptionImageUrl") or ""

    data: Dict[str, Any] = {
        "id": ep_id,
        "title": episode.get("title") or f"Episode {ep_id}",
        "description": description,
        "duration": duration,
        "channel": episode.get("subscriptionTitle") or channel.id,
        "castria": {
            "episodeId": ep_id,
            "subscriptionId": episode.get("subscriptionId"),
            "audioUrl": episode.get("audioUrl"),
            "adSource": source,
            "adRanges": [[round(s, 2), round(e, 2)] for s, e in gaps],
            "removedSeconds": round(removed_seconds, 2),
            "originalBytes": original_bytes,
        },
    }
    if pub:
        data["upload_date"] = pub.strftime("%Y%m%d")
        data["timestamp"] = int(pub.timestamp())
    if image:
        data["thumbnails"] = [{"url": image, "width": 1400, "height": 1400}]

    with open(download_dir / f"{ep_id}.info.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _cache_channel_artwork(channel_id: str, subscription: dict, client: CastriaClient) -> None:
    url = subscription.get("imageUrl") or ""
    if not url:
        return
    if url.startswith("/"):
        url = f"{client.base_url}{url}"
    out = settings.ARTWORK_DIR / f"{channel_id}.jpg"
    if out.exists():
        return
    try:
        resp = client.session.get(url, headers=client._headers(), timeout=30)
        if resp.status_code == 200 and resp.content:
            settings.ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
            out.write_bytes(resp.content)
            job_logger.info(f"Cached Castria artwork for {channel_id}")
        else:
            job_logger.warning(f"Could not fetch artwork for {channel_id}: HTTP {resp.status_code}")
    except requests.RequestException as e:
        job_logger.warning(f"Could not fetch artwork for {channel_id}: {e}")


def _process_episode(client: CastriaClient, channel: Channel, episode: dict, download_dir: Path, archive_file: Path) -> None:
    ep_id = episode["id"]
    temp_path = download_dir / f"{ep_id}.temp.mp3"
    dest_path = download_dir / f"{ep_id}.mp3"
    cut_path = download_dir / f"{ep_id}.cut.mp3"

    try:
        if not _episode_ready(episode):
            job_logger.info(f"[{ep_id}] Castria has not finished analysing this episode yet; will retry next run.")
            return

        job_logger.info(f"[{ep_id}] Downloading '{episode.get('title')}'...")
        if not _download_file(episode["audioUrl"], temp_path, _download_headers()):
            job_logger.error(f"[{ep_id}] Download failed")
            return
        temp_path.replace(dest_path)
        original_bytes = dest_path.stat().st_size

        gaps, source = _resolve_gaps(client, episode, dest_path)
        removed_seconds = 0.0
        if gaps:
            removed_seconds = sum(e - s for s, e in merge_ranges(gaps, get_audio_duration_seconds(dest_path)))
            job_logger.info(
                f"[{ep_id}] Removing {len(gaps)} ad range(s) (~{removed_seconds:.0f}s) via {source}"
            )
            if cut_audio_segments(dest_path, cut_path, gaps):
                dest_path.unlink(missing_ok=True)
                cut_path.replace(dest_path)
            else:
                if cut_path.exists():
                    cut_path.unlink()
                job_logger.warning(f"[{ep_id}] Ad removal produced no output; keeping original audio")
        elif source == "failed":
            job_logger.warning(
                f"[{ep_id}] Could not determine ad ranges; publishing unchanged (ads may still be present)"
            )
        elif source == "too-long":
            job_logger.warning(
                f"[{ep_id}] Episode is too long for Castria's aligner; publishing unchanged (ads will remain)"
            )
        else:
            job_logger.info(f"[{ep_id}] No ad gaps found ({source}); publishing unchanged")

        duration = get_audio_duration(dest_path)
        _write_info_json(download_dir, episode, channel, duration, gaps, source, removed_seconds, original_bytes)

        with open(archive_file, "a", encoding="utf-8") as fh:
            fh.write(f"castria {ep_id}\n")

        job_logger.info(f"[{ep_id}] Done -> {dest_path.name} ({duration}s, -{removed_seconds:.0f}s ads)")
    except Exception as e:  # noqa: BLE001 - one bad episode must not abort the run
        job_logger.error(f"Error processing Castria episode {ep_id}: {e}")
        for path in (temp_path, cut_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def run_castria_download(channel: Channel, force: bool = False) -> None:
    """Sync one ``castria:`` channel into PodQueue's downloads/feeds."""
    from podqueue.core.downloader import cleanup_old_episodes, cleanup_leftovers

    job_logger.info(f"Starting Castria podcast sync for {channel.id}...")

    if not settings.CASTRIA_EMAIL or not settings.CASTRIA_PASSWORD:
        job_logger.error(
            "CASTRIA_EMAIL/CASTRIA_PASSWORD are not set; cannot sync Castria channel. "
            "Add them to .env (see .env.example) and restart."
        )
        return

    # interval check (mirrors pawchive)
    last_check_file = settings.STATE_DIR / f"{channel.id}.last_check"
    current_time = int(time.time())
    if not force and last_check_file.exists():
        try:
            last_check_str = last_check_file.read_text().strip()
            if last_check_str.isdigit():
                next_check_time = int(last_check_str) + (channel.check_interval_hours * 3600)
                if current_time < next_check_time:
                    remaining = (next_check_time - current_time + 59) // 60
                    job_logger.info(f"Skipping {channel.id}. Next check in about {remaining} minute(s).")
                    return
        except OSError as e:
            job_logger.error(f"Error reading last check file for {channel.id}: {e}")

    download_dir = settings.DOWNLOADS_DIR / channel.id
    download_dir.mkdir(parents=True, exist_ok=True)
    archive_file = download_dir / "archive.txt"
    cleanup_leftovers(download_dir)
    cleanup_old_episodes(download_dir, archive_file, channel.limit)
    archive_set = _read_archive(archive_file)

    client = CastriaClient()
    try:
        kind, value = parse_castria_target(channel.url)
        subscription = client.resolve_subscription(kind, value)
    except ValueError as e:
        job_logger.error(f"Invalid Castria channel url '{channel.url}': {e}")
        return
    except CastriaError as e:
        job_logger.error(f"Castria auth/API error for {channel.id}: {e}")
        return

    if not subscription:
        job_logger.error(
            f"No Castria subscription matched '{channel.url}' for {channel.id}. "
            "Add the show in the Castria app first."
        )
        return

    job_logger.info(f"Castria channel {channel.id} -> '{subscription.get('title')}' ({subscription.get('id')})")
    _cache_channel_artwork(channel.id, subscription, client)

    try:
        episodes = client.get_episodes(subscription["id"], page_size=max(20, channel.limit * 5))
    except CastriaError as e:
        job_logger.error(f"Could not list episodes for {subscription.get('id')}: {e}")
        return

    episodes.sort(key=lambda e: str(e.get("pubDate") or ""), reverse=True)
    pending = [
        e for e in episodes
        if e.get("id") not in archive_set and not (download_dir / f"{e['id']}.mp3").exists()
    ][:channel.limit]

    if pending:
        job_logger.info(f"Found {len(pending)} new episode(s) to process (limit {channel.limit}).")
        for episode in pending:
            _process_episode(client, channel, episode, download_dir, archive_file)
    else:
        job_logger.info("No new Castria episodes.")

    cleanup_leftovers(download_dir)
    cleanup_old_episodes(download_dir, archive_file, channel.limit)

    try:
        last_check_file.write_text(str(current_time))
    except OSError as e:
        job_logger.error(f"Error writing last check file for {channel.id}: {e}")

    job_logger.info(f"Finished Castria sync for {channel.id}.")
