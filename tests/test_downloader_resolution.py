import pytest
from unittest.mock import patch, MagicMock
from podqueue.core.downloader import resolve_channel_url, run_download_job
from podqueue.core.channels import Channel
from podqueue.config import settings

def test_resolve_channel_url_appends_videos():
    # Channel ID URL
    assert resolve_channel_url("https://www.youtube.com/channel/UC12345") == "https://www.youtube.com/channel/UC12345/videos"
    assert resolve_channel_url("https://www.youtube.com/c/SomeCreator") == "https://www.youtube.com/c/SomeCreator/videos"
    assert resolve_channel_url("https://www.youtube.com/user/LegacyUser") == "https://www.youtube.com/user/LegacyUser/videos"
    assert resolve_channel_url("https://www.youtube.com/@DirectHandle") == "https://www.youtube.com/@DirectHandle/videos"
    
    # Existing specific endpoints should not have /videos appended
    assert resolve_channel_url("https://www.youtube.com/playlist?list=PL123") == "https://www.youtube.com/playlist?list=PL123"
    assert resolve_channel_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert resolve_channel_url("https://www.youtube.com/@Creator/videos") == "https://www.youtube.com/@Creator/videos"
    assert resolve_channel_url("https://www.youtube.com/@Creator/streams") == "https://www.youtube.com/@Creator/streams"

def test_single_video_url_download_support(tmp_path):
    """Verify that a single video URL without 'entries' is properly parsed and downloaded."""
    channel = Channel(id="SingleVidChan", url="https://www.youtube.com/watch?v=single123", limit=1)
    
    single_video_info = {
        "id": "single123",
        "title": "Single Test Video",
        "url": "https://www.youtube.com/watch?v=single123",
        "webpage_url": "https://www.youtube.com/watch?v=single123",
        "upload_date": "20260720",
    }
    
    with patch("podqueue.core.downloader.load_channels_sync", return_value=[channel]), \
         patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
         patch.object(settings, "DOWNLOADS_DIR", tmp_path / "downloads"), \
         patch.object(settings, "STATE_DIR", tmp_path / "state"):
        
        (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance
        # extract_info returns the single video dict (no 'entries' key)
        mock_ydl_instance.extract_info.return_value = single_video_info
        
        run_download_job(force=True)
        
        # Verify download was called with the single video URL
        mock_ydl_instance.download.assert_called_once_with(["https://www.youtube.com/watch?v=single123"])
