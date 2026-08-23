import json
import xml.etree.ElementTree as ET
import pytest
from pathlib import Path
from unittest.mock import patch
from podqueue.core.rss import generate_rss
from podqueue.config import settings

def test_rss_immutable_guid_and_enclosure(tmp_path):
    downloads_dir = tmp_path / "downloads"
    feeds_dir = tmp_path / "feeds"
    artwork_dir = tmp_path / "artwork"
    
    downloads_dir.mkdir()
    feeds_dir.mkdir()
    artwork_dir.mkdir()
    
    feed_dir = downloads_dir / "TechPodcast"
    feed_dir.mkdir()
    
    # Create audio and info.json
    (feed_dir / "vid123.m4a").write_bytes(b"dummy_m4a_audio_content")
    (feed_dir / "vid123.info.json").write_text(json.dumps({
        "id": "vid123",
        "title": "Episode 1: The Beginning",
        "upload_date": "20260720",
        "description": "Episode description",
        "channel": "Tech Podcast Channel"
    }), encoding="utf-8")
    
    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "ARTWORK_DIR", artwork_dir), \
         patch.object(settings, "BASE_URL", "http://192.168.1.10:8000"):
        
        generate_rss("TechPodcast", feed_dir)
        
        feed_xml_path = feeds_dir / "TechPodcast.xml"
        assert feed_xml_path.exists()
        
        tree = ET.parse(feed_xml_path)
        root = tree.getroot()
        item = root.find("channel/item")
        assert item is not None
        
        # Verify immutable GUID
        guid = item.find("guid")
        assert guid is not None
        assert guid.attrib.get("isPermaLink") == "false"
        assert guid.text == "podqueue:TechPodcast:vid123"
        
        # Verify enclosure URL
        enclosure = item.find("enclosure")
        assert enclosure is not None
        assert enclosure.attrib["url"] == "http://192.168.1.10:8000/downloads/TechPodcast/vid123.m4a"
        assert enclosure.attrib["type"] == "audio/mp4"

    # Now verify that changing BASE_URL preserves the GUID
    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "ARTWORK_DIR", artwork_dir), \
         patch.object(settings, "BASE_URL", "https://podcast.mydomain.com"):
        
        generate_rss("TechPodcast", feed_dir)
        tree = ET.parse(feed_xml_path)
        root = tree.getroot()
        item = root.find("channel/item")
        
        guid = item.find("guid")
        assert guid.text == "podqueue:TechPodcast:vid123"
        
        enclosure = item.find("enclosure")
        assert enclosure.attrib["url"] == "https://podcast.mydomain.com/downloads/TechPodcast/vid123.m4a"

def test_rss_local_artwork_detection_fallback(tmp_path):
    """Verify that existing local artwork in ARTWORK_DIR is used even if info.json has no thumbnails."""
    downloads_dir = tmp_path / "downloads"
    feeds_dir = tmp_path / "feeds"
    artwork_dir = tmp_path / "artwork"
    
    downloads_dir.mkdir()
    feeds_dir.mkdir()
    artwork_dir.mkdir()
    
    # Place custom artwork
    (artwork_dir / "ArtFeed.jpg").write_bytes(b"fake_jpg_bytes")
    
    feed_dir = downloads_dir / "ArtFeed"
    feed_dir.mkdir()
    (feed_dir / "ep1.mp3").write_bytes(b"audio")
    # info.json without thumbnails
    (feed_dir / "ep1.info.json").write_text(json.dumps({
        "id": "ep1",
        "title": "Art Episode",
        "thumbnails": []
    }), encoding="utf-8")
    
    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "ARTWORK_DIR", artwork_dir), \
         patch.object(settings, "BASE_URL", "http://localhost:8000"):
        
        generate_rss("ArtFeed", feed_dir)
        
        tree = ET.parse(feeds_dir / "ArtFeed.xml")
        root = tree.getroot()
        
        # Check itunes:image on channel
        itunes_image = root.find(".//{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        assert itunes_image is not None
        assert itunes_image.attrib.get("href") == "http://localhost:8000/artwork/ArtFeed.jpg"
