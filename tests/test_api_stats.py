import mimetypes
import pytest
from unittest.mock import patch, MagicMock
from podqueue.config import settings
from podqueue.core.channels import Channel

def test_mimetype_registrations():
    """Verify that mimetypes for podcast feeds and media are registered properly."""
    assert mimetypes.guess_type("test.m4a")[0] == "audio/mp4"
    assert mimetypes.guess_type("test.mp3")[0] == "audio/mpeg"
    assert mimetypes.guess_type("feed.xml")[0] in ("application/xml", "text/xml")

@pytest.mark.asyncio
async def test_list_feeds_excludes_temp_files(tmp_path):
    from podqueue.api.main import list_feeds
    
    feeds_dir = tmp_path / "feeds"
    downloads_dir = tmp_path / "downloads"
    feeds_dir.mkdir(parents=True)
    downloads_dir.mkdir(parents=True)
    
    # Create sample feed XML
    feed_file = feeds_dir / "FeedA.xml"
    feed_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Feed A Title</title></channel></rss>""", encoding="utf-8")
    
    # Create downloads subdir with 2 real episodes and 2 temp/part files
    chan_downloads = downloads_dir / "FeedA"
    chan_downloads.mkdir()
    (chan_downloads / "ep1.m4a").write_bytes(b"audio")
    (chan_downloads / "ep2.mp3").write_bytes(b"audio")
    (chan_downloads / "ep3.temp.m4a").write_bytes(b"temp")
    (chan_downloads / "ep4.part").write_bytes(b"part")
    (chan_downloads / "ep1.info.json").write_text("{}", encoding="utf-8")
    
    mock_request = MagicMock()
    mock_request.session = {"authenticated": True}
    
    with patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "DOWNLOADS_DIR", downloads_dir):
        
        feeds = await list_feeds(mock_request)
        assert len(feeds) == 1
        assert feeds[0]["name"] == "FeedA"
        assert feeds[0]["title"] == "Feed A Title"
        # Must only count the 2 valid audio files, ignoring temp/part/json
        assert feeds[0]["audio_count"] == 2

@pytest.mark.asyncio
async def test_list_channels_excludes_temp_files(tmp_path):
    from podqueue.api.channels import list_channels
    
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True)
    
    chan = Channel(id="ChanCountTest", url="https://youtube.com/@ChanCountTest")
    
    chan_dir = downloads_dir / "ChanCountTest"
    chan_dir.mkdir()
    (chan_dir / "audio1.m4a").write_bytes(b"audio")
    (chan_dir / "audio2.temp.mp3").write_bytes(b"temp")
    (chan_dir / "audio3.part").write_bytes(b"part")
    
    mock_request = MagicMock()
    mock_request.session = {"authenticated": True}
    
    with patch("podqueue.api.channels.load_channels", return_value=[chan]), \
         patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "STATE_DIR", tmp_path / "state"):
        
        channels = await list_channels(mock_request)
        assert len(channels) == 1
        assert channels[0]["id"] == "ChanCountTest"
        assert channels[0]["audio_count"] == 1
