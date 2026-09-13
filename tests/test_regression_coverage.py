"""Regression tests for bugs identified in comprehensive codebase analysis.

Each test targets a specific bug that currently has no coverage. These tests
FAIL against the current code; once fixes are applied they should pass.
"""
import os
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import xml.etree.ElementTree as ET

from podqueue.config import settings
from podqueue.core.channels import Channel
from podqueue.core.downloader import cleanup_old_episodes


# ─── Bug: cleanup_old_episodes does not write pruned IDs to archive.txt ────────

def test_cleanup_old_episodes_writes_pruned_to_archive(tmp_path):
    """Pruned episode video IDs must be written to archive.txt to prevent
    yt-dlp from re-downloading them on the next sync cycle.

    This catches the `pass` placeholder at downloader.py:139 where the archive
    write was never implemented.
    """
    download_dir = tmp_path / "PrunedChan"
    download_dir.mkdir()
    archive_file = download_dir / "archive.txt"

    # Create 4 episodes with upload_date metadata; limit is 2
    for i, date_str in enumerate(["20260101", "20260201", "20260301", "20260401"]):
        ep_id = f"vid_{i}"
        (download_dir / f"{ep_id}.m4a").write_bytes(b"audio")
        (download_dir / f"{ep_id}.info.json").write_text(
            json.dumps({"id": ep_id, "upload_date": date_str}),
            encoding="utf-8"
        )

    cleanup_old_episodes(download_dir, archive_file, limit=2)

    # ep_0 and ep_1 should be pruned (oldest)
    assert not (download_dir / "vid_0.m4a").exists()
    assert not (download_dir / "vid_1.m4a").exists()

    # The pruned IDs must appear in archive.txt
    assert archive_file.exists(), "archive.txt should be created"
    archive_content = archive_file.read_text(encoding="utf-8")
    assert "vid_0" in archive_content, "Pruned episode vid_0 must be in archive.txt"
    assert "vid_1" in archive_content, "Pruned episode vid_1 must be in archive.txt"


# ─── Bug: rss.py audio file filter does NOT exclude .part files ────────────────

def test_rss_generation_excludes_part_files(tmp_path):
    """RSS generation must exclude .part files just like the download count
    filter in main.py and downloader.py. The current rss.py filter only
    checks for '.temp.' — .part files slip through and corrupt podcast feeds.
    """
    from podqueue.core.rss import generate_rss

    downloads_dir = tmp_path / "downloads"
    feeds_dir = tmp_path / "feeds"
    artwork_dir = tmp_path / "artwork"
    for d in (downloads_dir, feeds_dir, artwork_dir):
        d.mkdir(parents=True)

    feed_dir = downloads_dir / "PartFileFeed"
    feed_dir.mkdir()
    (feed_dir / "real_ep.m4a").write_bytes(b"real_audio")
    (feed_dir / "real_ep.info.json").write_text(json.dumps({
        "id": "real_ep",
        "title": "Real Episode",
        "upload_date": "20260720"
    }), encoding="utf-8")
    # A .part file should NOT appear in the feed
    (feed_dir / "incomplete.part.m4a").write_bytes(b"partial")
    (feed_dir / "incomplete2.part").write_bytes(b"part")

    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "ARTWORK_DIR", artwork_dir), \
         patch.object(settings, "BASE_URL", "http://localhost:8000"):

        generate_rss("PartFileFeed", feed_dir)

        tree = ET.parse(feeds_dir / "PartFileFeed.xml")
        root = tree.getroot()
        items = root.findall("channel/item")
        assert len(items) == 1, "Only real_ep.m4a should be in the feed; .part files must be excluded"

        enclosure_url = items[0].find("enclosure").attrib["url"]
        assert "real_ep.m4a" in enclosure_url
        assert ".part" not in enclosure_url


# ─── Bug: resolve_channel_url ignores the cookies_file parameter ───────────────

def test_resolve_channel_url_respects_cookies_file_param():
    """When a non-default cookies_file is explicitly passed, it should be used
    directly instead of being overridden by get_valid_cookies_file().

    The current implementation has inverted/dead logic: all callers pass
    settings.COOKIES_FILE, so `cookies_file == settings.COOKIES_FILE` is
    always True, making get_valid_cookies_file() always called and the
    else branch unreachable dead code.
    """
    from podqueue.core.downloader import resolve_channel_url

    # Create a fake cookies file that is NOT settings.COOKIES_FILE
    custom_cookies = Path("/tmp/test_custom_cookies_regression.txt")
    custom_cookies.write_text("# Netscape HTTP Cookie File\nfake_domain\tTRUE\t/\t\tTRUE\t0\tfake\tvalue\n", encoding="utf-8")

    try:
        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
             patch("podqueue.core.downloader.get_valid_cookies_file") as mock_get_cookies:

            mock_instance = MagicMock()
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = {
                "id": "UC123",
                "channel_id": "UC123"
            }
            mock_ydl_cls.return_value = mock_instance

            resolve_channel_url(
                "https://www.youtube.com/@SomeCreator",
                cookies_file=custom_cookies
            )

            # Verify get_valid_cookies_file was NOT called — we passed a custom path
            mock_get_cookies.assert_not_called()

            # Verify the ydl_opts used the custom cookies file directly
            ydl_opts = mock_ydl_cls.call_args[0][0]
            assert ydl_opts['cookiefile'] == str(custom_cookies), \
                "Custom cookies_file should be used directly, not routed through get_valid_cookies_file()"
    finally:
        custom_cookies.unlink(missing_ok=True)


# ─── Bug: ChannelUpdate requires all fields, preventing partial updates ─────────

def test_channel_update_partial_update_allowed():
    """The ChannelUpdate model should allow partial updates so the API
    can accept a PUT with only the fields being changed.
    Currently limit and check_interval_hours are required (Field(...)).
    """
    from podqueue.api.channels import ChannelUpdate

    # Only updating sponsorblock should work and unspecified fields must default to None
    update = ChannelUpdate(sponsorblock=True)
    assert update.sponsorblock is True
    assert update.limit is None
    assert update.check_interval_hours is None


def test_edit_channel_endpoint_partial_update_preserves_existing_values(tmp_path):
    """Calling edit_channel with partial fields must not overwrite unspecified fields with defaults."""
    from podqueue.api.channels import edit_channel, ChannelUpdate
    from podqueue.core.channels import Channel, add_channel_sync, load_channels_sync

    channels_file = tmp_path / "channels.json"
    with patch.object(settings, "CHANNELS_FILE", channels_file):
        add_channel_sync(Channel(id="TestChan", url="https://youtube.com/@TestChan", limit=20, sponsorblock=False, check_interval_hours=12))

        mock_request = MagicMock()
        mock_request.session = {"authenticated": True}

        loop = asyncio.new_event_loop()
        try:
            # Partial update only sponsorblock
            loop.run_until_complete(edit_channel(mock_request, "TestChan", ChannelUpdate(sponsorblock=True)))
            channels = load_channels_sync()
            assert len(channels) == 1
            assert channels[0].sponsorblock is True
            assert channels[0].limit == 20, "Limit must not be overwritten to default 5"
            assert channels[0].check_interval_hours == 12, "Interval must not be overwritten to default 1"

            # Partial update only limit
            loop.run_until_complete(edit_channel(mock_request, "TestChan", ChannelUpdate(limit=10)))
            channels = load_channels_sync()
            assert channels[0].limit == 10
            assert channels[0].sponsorblock is True, "Sponsorblock must not be overwritten to default False"
            assert channels[0].check_interval_hours == 12, "Interval must not be overwritten"
        finally:
            loop.close()


# ─── Bug: API auth enforcement on all endpoints ─────────────────────────────────

def test_list_feeds_requires_auth():
    """The list_feeds endpoint must reject unauthenticated requests with 401."""
    from podqueue.api.main import list_feeds
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.session = {"authenticated": False}

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(HTTPException) as exc_info:
            loop.run_until_complete(list_feeds(mock_request))
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail
    finally:
        loop.close()


def test_list_channels_requires_auth():
    """The list_channels endpoint must reject unauthenticated requests."""
    from podqueue.api.channels import list_channels
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.session = {"authenticated": False}

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(HTTPException) as exc_info:
            loop.run_until_complete(list_channels(mock_request))
        assert exc_info.value.status_code == 401
    finally:
        loop.close()


def test_download_job_endpoint_requires_auth():
    """The download trigger endpoint must reject unauthenticated requests."""
    from podqueue.api.jobs import trigger_download
    from fastapi import HTTPException

    mock_request = MagicMock()
    mock_request.session = {"authenticated": False}
    mock_request.headers = {}

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(HTTPException) as exc_info:
            loop.run_until_complete(trigger_download(mock_request))
        assert exc_info.value.status_code == 401
    finally:
        loop.close()


# ─── Bug: pull_changes.py deploys to wrong directory ───────────────────────────

def test_pull_changes_deploys_to_correct_directory():
    """The pull_changes.py deploy script must target the correct server
    directory (PodQueue_server, not Poqueue_server).
    """
    # pull_changes.py lives at the repo root, one level above podqueue_repo/
    pull_changes_path = Path(__file__).resolve().parent.parent.parent / "pull_changes.py"
    source = pull_changes_path.read_text(encoding="utf-8")

    # The typo'd directory name must not appear in the remote_commands string
    assert "Poqueue_server" not in source, \
        "pull_changes.py must use 'PodQueue_server' (correct spelling), not 'Poqueue_server'"
    assert "PodQueue_server" in source, \
        "pull_changes.py should deploy to 'PodQueue_server'"


# ─── Bug: cleanup_leftovers should delete .part and .ytdl files ────────────────

def test_cleanup_leftovers_deletes_part_files(tmp_path):
    """cleanup_leftovers must delete .part, .ytdl, .temp.mp4 files while
    preserving legitimate audio files."""
    from podqueue.core.downloader import cleanup_leftovers

    download_dir = tmp_path / "LeftoverChan"
    download_dir.mkdir()

    # Create files that should be deleted
    (download_dir / "vid1.part").write_bytes(b"part")
    (download_dir / "vid2.ytdl").write_bytes(b"ytdl")
    (download_dir / "vid3.temp.mp4").write_bytes(b"temp")

    # Create files that should survive
    (download_dir / "vid4.m4a").write_bytes(b"real")
    (download_dir / "vid4.info.json").write_text(json.dumps({"id": "vid4"}), encoding="utf-8")

    cleanup_leftovers(download_dir)

    assert not (download_dir / "vid1.part").exists()
    assert not (download_dir / "vid2.ytdl").exists()
    assert not (download_dir / "vid3.temp.mp4").exists()
    assert (download_dir / "vid4.m4a").exists()
    assert (download_dir / "vid4.info.json").exists()
