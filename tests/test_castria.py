import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from podqueue.config import settings
from podqueue.core.channels import Channel
from podqueue.core.castria import (
    _coerce_gaps,
    _episode_ready,
    is_castria_url,
    parse_castria_target,
    run_castria_download,
)
from podqueue.core.downloader import run_download_job
from podqueue.utils.castria_align import AlignerError


def test_is_castria_url():
    assert is_castria_url("castria:c7e1e018-6f86-4d53-94de-3c69990ccb7c") is True
    assert is_castria_url("CASTRIA:something") is True
    assert is_castria_url("https://www.youtube.com/@somecreator") is False
    assert is_castria_url("https://pawchive.st/user/x") is False
    assert is_castria_url("") is False


def test_parse_castria_target():
    assert parse_castria_target("castria:c7e1e018-6f86-4d53-94de-3c69990ccb7c") == (
        "id",
        "c7e1e018-6f86-4d53-94de-3c69990ccb7c",
    )
    assert parse_castria_target("castria://c7e1e018-6f86-4d53-94de-3c69990ccb7c") == (
        "id",
        "c7e1e018-6f86-4d53-94de-3c69990ccb7c",
    )
    assert parse_castria_target("castria:https://example.com/feed.rss") == ("url", "https://example.com/feed.rss")
    assert parse_castria_target("castria:Knowledge Fight Country") == ("url", "Knowledge Fight Country")
    with pytest.raises(ValueError):
        parse_castria_target("castria:")
    with pytest.raises(ValueError):
        parse_castria_target("https://youtube.com/@x")


def test_coerce_gaps_variants():
    assert _coerce_gaps({"gaps": [{"start": 1, "end": 2}]}) == [(1.0, 2.0)]
    assert _coerce_gaps({"plan": {"gaps": [{"start": 3, "end": 4}]}}) == [(3.0, 4.0)]
    assert _coerce_gaps([[5, 6]]) == [(5.0, 6.0)]
    assert _coerce_gaps(None) == []
    assert _coerce_gaps({}) == []
    # zero-length / inverted ranges are dropped
    assert _coerce_gaps({"gaps": [{"start": 5, "end": 5}, {"start": 9, "end": 8}]}) == []


def test_episode_ready():
    assert _episode_ready({"showFingerprintAvailable": True}) is True
    assert _episode_ready({"adStatus": "completed"}) is True
    assert _episode_ready({"showFingerprintAvailable": False, "adStatus": "processing"}) is False


class _FakeClient:
    """Stands in for CastriaClient in end-to-end download tests."""

    episodes = []

    def __init__(self, *args, **kwargs):
        self.base_url = "https://castria.app"
        self.session = MagicMock()

    def resolve_subscription(self, kind, value):
        return {
            "id": "sub-1",
            "title": "Test Show",
            "url": "https://feed.example/rss",
            "imageUrl": "",
        }

    def get_episodes(self, subscription_id, page_size=20):
        return list(self.episodes)

    def get_skipplan(self, episode_id, file_hash, algo=2):
        return None

    def get_fingerprint(self, episode_id):
        return "AAAA"

    def get_episode(self, episode_id):
        return {"id": episode_id, "adSegments": []}


def _episode(**overrides):
    base = {
        "id": "ep-1",
        "subscriptionId": "sub-1",
        "subscriptionTitle": "Test Show",
        "title": "Ep One",
        "description": "<p>Hello <b>world</b></p>",
        "pubDate": "2026-10-14T09:30:00+00:00",
        "audioUrl": "https://cdn.example/ep1.mp3",
        "adStatus": "completed",
        "adSegmentCount": 3,
        "showFingerprintAvailable": True,
        "subscriptionImageUrl": "",
    }
    base.update(overrides)
    return base


def _fake_http_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.iter_content = MagicMock(return_value=[b"ORIGINAL-AUDIO"])
    resp.raise_for_status = MagicMock()
    return resp


def _settings_patches(tmp_path):
    return [
        patch.object(settings, "CASTRIA_EMAIL", "user@example.com"),
        patch.object(settings, "CASTRIA_PASSWORD", "secret"),
        patch.object(settings, "DOWNLOADS_DIR", tmp_path / "downloads"),
        patch.object(settings, "STATE_DIR", tmp_path / "state"),
        patch.object(settings, "ARTWORK_DIR", tmp_path / "artwork"),
    ]


def test_run_castria_download_removes_ads_end_to_end(tmp_path):
    _FakeClient.episodes = [_episode()]
    channel = Channel(id="TestCastria", url="castria:sub-1", limit=5)

    def fake_cut(src, dst, gaps, **kwargs):
        Path(dst).write_bytes(b"CUT-AUDIO")
        return True

    patches = _settings_patches(tmp_path)
    with patch("podqueue.core.castria.CastriaClient", _FakeClient), \
         patch("podqueue.core.castria.requests.get", return_value=_fake_http_response()), \
         patch("podqueue.core.castria.run_aligner", return_value=[(0.0, 160.4), (728.18, 911.01)]) as m_align, \
         patch("podqueue.core.castria.cut_audio_segments", side_effect=fake_cut) as m_cut, \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=914.68), \
         patch("podqueue.core.castria.get_audio_duration", return_value=400), \
         patch("podqueue.core.downloader.cleanup_old_episodes"), \
         patch("podqueue.core.downloader.cleanup_leftovers"):
        for p in patches:
            p.start()
        try:
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            run_castria_download(channel, force=True)
        finally:
            for p in patches:
                p.stop()

    chan_dir = tmp_path / "downloads" / "TestCastria"
    dest = chan_dir / "ep-1.mp3"
    assert dest.exists()
    assert dest.read_bytes() == b"CUT-AUDIO"  # cut output replaced the original

    info = json.loads((chan_dir / "ep-1.info.json").read_text(encoding="utf-8"))
    assert info["title"] == "Ep One"
    assert info["channel"] == "Test Show"
    assert info["upload_date"] == "20261014"
    assert info["timestamp"] == int(
        datetime.datetime(2026, 10, 14, 9, 30, tzinfo=datetime.timezone.utc).timestamp()
    )
    assert info["duration"] == 400
    assert "world" in info["description"] and "<b>" not in info["description"]
    assert info["castria"]["adSource"] == "alignment"
    assert info["castria"]["adRanges"] == [[0.0, 160.4], [728.18, 911.01]]

    archive = (chan_dir / "archive.txt").read_text(encoding="utf-8")
    assert "castria ep-1" in archive

    m_align.assert_called_once()
    m_cut.assert_called_once()


def test_run_castria_download_skips_unready_episode(tmp_path):
    _FakeClient.episodes = [
        _episode(adStatus="processing", showFingerprintAvailable=False, adSegmentCount=0)
    ]
    channel = Channel(id="TestCastria2", url="castria:sub-1", limit=5)

    patches = _settings_patches(tmp_path)
    with patch("podqueue.core.castria.CastriaClient", _FakeClient), \
         patch("podqueue.core.castria.requests.get") as m_http, \
         patch("podqueue.core.downloader.cleanup_old_episodes"), \
         patch("podqueue.core.downloader.cleanup_leftovers"):
        for p in patches:
            p.start()
        try:
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            run_castria_download(channel, force=True)
        finally:
            for p in patches:
                p.stop()

    chan_dir = tmp_path / "downloads" / "TestCastria2"
    assert not (chan_dir / "ep-1.mp3").exists()
    assert not (chan_dir / "archive.txt").exists()
    m_http.assert_not_called()


def test_run_castria_download_without_credentials(tmp_path):
    channel = Channel(id="NoCreds", url="castria:sub-1", limit=5)
    with patch.object(settings, "CASTRIA_EMAIL", ""), \
         patch.object(settings, "CASTRIA_PASSWORD", ""), \
         patch.object(settings, "DOWNLOADS_DIR", tmp_path / "downloads"), \
         patch("podqueue.core.castria.CastriaClient") as m_client:
        run_castria_download(channel, force=True)
        m_client.assert_not_called()


def test_download_job_routes_castria_channels():
    channel = Channel(id="CastriaChan", url="castria:sub-1", limit=2)
    with patch("podqueue.core.downloader.load_channels_sync", return_value=[channel]), \
         patch("podqueue.core.downloader.run_castria_download") as m_castria:
        run_download_job(force=True)
    m_castria.assert_called_once()
    assert m_castria.call_args[0][0].id == "CastriaChan"


# --------------------------------------------------------------------------- #
# UI helper endpoint: GET /api/castria/subscriptions
# --------------------------------------------------------------------------- #

def _authed_request():
    request = MagicMock()
    request.session = {"authenticated": True}
    return request


@pytest.mark.asyncio
async def test_list_castria_subscriptions_returns_trimmed_shows():
    from podqueue.api.channels import list_castria_subscriptions

    raw = [{
        "id": "sub-1", "title": "Show A", "url": "https://feed/a",
        "imageUrl": "https://img/a.jpg", "episodeCount": 12,
        "accessToken": "should-not-leak",
    }]

    with patch.object(settings, "CASTRIA_EMAIL", "u@example.com"), \
         patch.object(settings, "CASTRIA_PASSWORD", "pw"), \
         patch("podqueue.api.channels.CastriaClient") as m_client:
        m_client.return_value.get_subscriptions.return_value = raw
        result = await list_castria_subscriptions(_authed_request())

    assert result == [{
        "id": "sub-1", "title": "Show A", "url": "https://feed/a",
        "imageUrl": "https://img/a.jpg", "episodeCount": 12,
    }]


@pytest.mark.asyncio
async def test_list_castria_subscriptions_requires_auth():
    from fastapi import HTTPException
    from podqueue.api.channels import list_castria_subscriptions

    request = MagicMock()
    request.session = {}

    with pytest.raises(HTTPException) as exc:
        await list_castria_subscriptions(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_list_castria_subscriptions_requires_credentials():
    from fastapi import HTTPException
    from podqueue.api.channels import list_castria_subscriptions

    with patch.object(settings, "CASTRIA_EMAIL", ""), \
         patch.object(settings, "CASTRIA_PASSWORD", ""):
        with pytest.raises(HTTPException) as exc:
            await list_castria_subscriptions(_authed_request())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_castria_subscriptions_surfaces_api_errors():
    from fastapi import HTTPException
    from podqueue.api.channels import list_castria_subscriptions
    from podqueue.core.castria import CastriaApiError

    with patch.object(settings, "CASTRIA_EMAIL", "u@example.com"), \
         patch.object(settings, "CASTRIA_PASSWORD", "pw"), \
         patch("podqueue.api.channels.CastriaClient") as m_client:
        m_client.return_value.get_subscriptions.side_effect = CastriaApiError("boom")
        with pytest.raises(HTTPException) as exc:
            await list_castria_subscriptions(_authed_request())
    assert exc.value.status_code == 502


# --------------------------------------------------------------------------- #
# Timeout scaling and failure reporting
# --------------------------------------------------------------------------- #

def test_resolve_timeout_scales_with_audio_length():
    from podqueue.utils.castria_align import ALIGN_TIMEOUT_PER_AUDIO_SECOND, resolve_timeout

    with patch("podqueue.utils.castria_align.get_audio_duration_seconds", return_value=10000):
        assert resolve_timeout(Path("x.mp3"), configured=3600) == int(10000 * ALIGN_TIMEOUT_PER_AUDIO_SECOND)


def test_resolve_timeout_keeps_floor_for_short_audio():
    from podqueue.utils.castria_align import resolve_timeout

    with patch("podqueue.utils.castria_align.get_audio_duration_seconds", return_value=120):
        assert resolve_timeout(Path("x.mp3"), configured=3600) == 3600


class _StubClient:
    def get_skipplan(self, *args, **kwargs):
        return None

    def get_fingerprint(self, *args, **kwargs):
        return "FP"

    def get_episode(self, *args, **kwargs):
        return {}


def test_resolve_gaps_reports_alignment_failure(tmp_path):
    from podqueue.core.castria import _resolve_gaps
    from podqueue.utils.castria_align import AlignerError

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-x", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch.object(settings, "CASTRIA_ALLOW_TIMESTAMP_FALLBACK", False), \
         patch("podqueue.core.castria.run_aligner", side_effect=AlignerError("aligner timed out after 3600s")):
        gaps, source, _meta = _resolve_gaps(_StubClient(), episode, audio)

    assert gaps == []
    assert source == "failed"


def test_resolve_gaps_reports_empty_result_as_success(tmp_path):
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-y", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch("podqueue.core.castria.run_aligner", return_value=[]):
        gaps, source, _meta = _resolve_gaps(_StubClient(), episode, audio)

    assert gaps == []
    assert source == "alignment"


# --------------------------------------------------------------------------- #
# The engine's per-session duration ceiling ("bug-543") and chunked alignment
# --------------------------------------------------------------------------- #

def test_exceeds_align_ceiling():
    from podqueue.utils.castria_align import exceeds_align_ceiling

    with patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200):
        assert exceeds_align_ceiling(7200) is False       # exactly at the limit is fine
        assert exceeds_align_ceiling(7200.5) is True
        assert exceeds_align_ceiling(10113) is True       # the 2.8h episode
        assert exceeds_align_ceiling(600) is False
        assert exceeds_align_ceiling(0) is False          # unknown duration must not block


def test_chunk_count():
    from podqueue.utils.castria_align import chunk_count

    with patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNK_SECONDS", 6600):
        assert chunk_count(0) == 1        # unknown duration -> one pass
        assert chunk_count(600) == 1      # short episode -> one pass
        assert chunk_count(6600) == 1     # exactly one chunk
        assert chunk_count(6600.5) == 2
        assert chunk_count(10113) == 2    # the 2.8h episode: 6600 + 3513
        assert chunk_count(13201) == 3


def test_chunk_count_clamps_to_engine_ceiling():
    """A chunk larger than the engine's guard would just trip it, so it is clamped."""
    from podqueue.utils.castria_align import align_chunk_seconds

    with patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNK_SECONDS", 99999):
        assert align_chunk_seconds() == 7200

    with patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNK_SECONDS", 0):
        assert align_chunk_seconds() == 7200


def test_bridge_ranges_rejoins_chunk_boundary_gaps():
    """A gap spanning a chunk boundary arrives as two pieces; they must rejoin."""
    from podqueue.utils.castria_align import bridge_ranges

    # two halves of one ad, split at the 200s boundary (0.13s of encoder padding)
    split = [(169.6, 199.88), (200.01, 229.96)]
    assert bridge_ranges(split) == [(169.6, 229.96)]

    # genuinely separate ads must stay separate
    apart = [(10.0, 40.0), (300.0, 340.0)]
    assert bridge_ranges(apart) == [(10.0, 40.0), (300.0, 340.0)]

    # overlapping/unsorted input is normalised
    assert bridge_ranges([(30.0, 50.0), (10.0, 35.0)]) == [(10.0, 50.0)]


def test_resolve_gaps_chunks_alignment_for_over_long_episodes(tmp_path):
    """Over-ceiling episodes are aligned in chunks rather than skipped."""
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-long", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNKING_ENABLED", True), \
         patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNK_SECONDS", 6600), \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=10113.0), \
         patch("podqueue.core.castria.run_aligner") as m_single, \
         patch("podqueue.core.castria.run_aligner_chunked", return_value=[(0.6, 160.4)]) as m_chunked:
        gaps, source, meta = _resolve_gaps(_StubClient(), episode, audio)

    assert gaps == [(0.6, 160.4)]
    assert source == "alignment"
    assert meta["alignChunks"] == 2
    m_chunked.assert_called_once()
    m_single.assert_not_called()


def test_resolve_gaps_uses_single_pass_below_chunk_size(tmp_path):
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-short", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNK_SECONDS", 6600), \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=600.0), \
         patch("podqueue.core.castria.run_aligner", return_value=[(5.0, 40.0)]) as m_single, \
         patch("podqueue.core.castria.run_aligner_chunked") as m_chunked:
        gaps, source, meta = _resolve_gaps(_StubClient(), episode, audio)

    assert source == "alignment"
    assert meta["alignChunks"] == 1
    m_single.assert_called_once()
    m_chunked.assert_not_called()


def test_resolve_gaps_reports_too_long_when_chunking_disabled(tmp_path):
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-long", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNKING_ENABLED", False), \
         patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=10113.0), \
         patch("podqueue.core.castria.run_aligner") as m_single, \
         patch("podqueue.core.castria.run_aligner_chunked") as m_chunked:
        gaps, source, _meta = _resolve_gaps(_StubClient(), episode, audio)

    assert gaps == []
    assert source == "too-long"
    m_single.assert_not_called()
    m_chunked.assert_not_called()


def test_resolve_gaps_still_uses_crowd_skipmap_for_over_long_episodes(tmp_path):
    """The skip-map has no duration limit, so it must be tried before the ceiling."""
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-long2", "showFingerprintAvailable": True}

    class SkipMapClient(_StubClient):
        def get_skipplan(self, *args, **kwargs):
            return {"gaps": [[0, 30.0], [500.0, 560.0]]}

    with patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=10113.0), \
         patch("podqueue.core.castria.run_aligner") as m_align:
        gaps, source, _meta = _resolve_gaps(SkipMapClient(), episode, audio)

    assert gaps == [(0.0, 30.0), (500.0, 560.0)]
    assert source == "skipplan"
    m_align.assert_not_called()

def test_resolve_gaps_reports_failed_when_chunked_alignment_fails(tmp_path):
    from podqueue.core.castria import _resolve_gaps

    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"x")
    episode = {"id": "ep-fail", "showFingerprintAvailable": True}

    with patch.object(settings, "CASTRIA_ALIGN_ENABLED", True), \
         patch.object(settings, "CASTRIA_ALIGN_CHUNKING_ENABLED", True), \
         patch.object(settings, "CASTRIA_MAX_ALIGN_DURATION_SECONDS", 7200), \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=10113.0), \
         patch("podqueue.core.castria.run_aligner_chunked", side_effect=AlignerError("OOM")):
        gaps, source, _meta = _resolve_gaps(_StubClient(), episode, audio)

    assert gaps == []
    assert source == "failed"


def test_run_castria_download_retries_incomplete_episode(tmp_path):
    """An episode with an existing mp3 but missing info.json must be re-processed."""
    _FakeClient.episodes = [_episode()]
    channel = Channel(id="TestCastriaIncomplete", url="castria:sub-1", limit=5)

    chan_dir = tmp_path / "downloads" / "TestCastriaIncomplete"
    chan_dir.mkdir(parents=True, exist_ok=True)
    # Create leftover un-cut mp3 without info.json
    (chan_dir / "ep-1.mp3").write_bytes(b"RAW-UNCUT-AUDIO")

    def fake_cut(src, dst, gaps, **kwargs):
        Path(dst).write_bytes(b"CUT-AUDIO")
        return True

    patches = _settings_patches(tmp_path)
    with patch("podqueue.core.castria.CastriaClient", _FakeClient), \
         patch("podqueue.core.castria.requests.get", return_value=_fake_http_response()), \
         patch("podqueue.core.castria.run_aligner", return_value=[(0.0, 160.4)]) as m_align, \
         patch("podqueue.core.castria.cut_audio_segments", side_effect=fake_cut) as m_cut, \
         patch("podqueue.core.castria.get_audio_duration_seconds", return_value=914.68), \
         patch("podqueue.core.castria.get_audio_duration", return_value=400), \
         patch("podqueue.core.downloader.cleanup_old_episodes"), \
         patch("podqueue.core.downloader.cleanup_leftovers"):
        for p in patches:
            p.start()
        try:
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            run_castria_download(channel, force=True)
        finally:
            for p in patches:
                p.stop()

    dest = chan_dir / "ep-1.mp3"
    assert dest.exists()
    assert dest.read_bytes() == b"CUT-AUDIO"
    assert (chan_dir / "ep-1.info.json").exists()
    assert "castria ep-1" in (chan_dir / "archive.txt").read_text()
    m_align.assert_called_once()
    m_cut.assert_called_once()


def test_process_episode_does_not_leave_dest_on_failure(tmp_path):
    """If ad removal or processing crashes, dest_path must not be left behind without info.json."""
    from podqueue.core.castria import _process_episode

    chan_dir = tmp_path / "downloads" / "CrashShow"
    chan_dir.mkdir(parents=True, exist_ok=True)
    archive = chan_dir / "archive.txt"
    channel = Channel(id="CrashShow", url="castria:sub-1", limit=5)
    episode = _episode(id="ep-crash")

    client = _FakeClient()
    with patch("podqueue.core.castria.requests.get", return_value=_fake_http_response()), \
         patch("podqueue.core.castria._resolve_gaps", side_effect=RuntimeError("unexpected crash")):
        _process_episode(client, channel, episode, chan_dir, archive)

    assert not (chan_dir / "ep-crash.mp3").exists()
    assert not (chan_dir / "ep-crash.work.mp3").exists()
    assert not (chan_dir / "ep-crash.info.json").exists()
