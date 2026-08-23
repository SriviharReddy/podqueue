import datetime
import email.utils
import json
import xml.etree.ElementTree as ET
import pytest
from unittest.mock import patch
from podqueue.utils.media import rfc2822_format, parse_upload_date
from podqueue.core.rss import generate_rss
from podqueue.config import settings

def test_rfc2822_format():
    dt = datetime.datetime(2026, 7, 14, 12, 30, 45, tzinfo=datetime.timezone.utc)
    formatted = rfc2822_format(dt)
    
    # Must parse back cleanly with email.utils.parsedate_to_datetime
    parsed = email.utils.parsedate_to_datetime(formatted)
    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 14
    assert parsed.hour == 12
    assert parsed.minute == 30
    assert parsed.second == 45

def test_parse_upload_date():
    dt = parse_upload_date("20260720")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 20
    assert dt.tzinfo == datetime.timezone.utc
    
    assert parse_upload_date("invalid") is None
    assert parse_upload_date("") is None

def test_rss_exact_timestamp_pubdate(tmp_path):
    downloads_dir = tmp_path / "downloads"
    feeds_dir = tmp_path / "feeds"
    downloads_dir.mkdir()
    feeds_dir.mkdir()
    
    feed_dir = downloads_dir / "ExactDateFeed"
    feed_dir.mkdir()
    
    # Unix timestamp for 2026-07-20 18:45:30 UTC = 1784573130
    test_epoch = 1784573130
    
    (feed_dir / "ep_ts.m4a").write_bytes(b"audio")
    (feed_dir / "ep_ts.info.json").write_text(json.dumps({
        "id": "ep_ts",
        "title": "Exact Timestamp Episode",
        "timestamp": test_epoch,
        "upload_date": "20260720"
    }), encoding="utf-8")
    
    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "BASE_URL", "http://localhost:8000"):
        
        generate_rss("ExactDateFeed", feed_dir)
        
        tree = ET.parse(feeds_dir / "ExactDateFeed.xml")
        root = tree.getroot()
        item = root.find("channel/item")
        
        pub_date_str = item.find("pubDate").text
        parsed_dt = email.utils.parsedate_to_datetime(pub_date_str)
        
        # Verify exact hour, minute, second from timestamp
        assert parsed_dt.hour == 18
        assert parsed_dt.minute == 45
        assert parsed_dt.second == 30
