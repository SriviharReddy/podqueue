import json
import xml.etree.ElementTree as ET
import pytest
from podqueue.utils.media import sanitize_title, parse_chapters_from_description, extract_chapters
from podqueue.core.rss import generate_rss
from podqueue.config import settings
from unittest.mock import patch

def test_sanitize_title_preserves_punctuation():
    # Colons and question marks must be preserved for podcast feeds
    title = "Lex Fridman Podcast #400: Sam Altman - Is AGI Here?"
    assert sanitize_title(title) == "Lex Fridman Podcast #400: Sam Altman - Is AGI Here?"
    
    # Extra whitespace and unprintable control characters should be stripped
    messy = "  Episode 1:  Hello \x00\x08World!  \t\n  "
    assert sanitize_title(messy) == "Episode 1: Hello World!"

def test_parse_chapters_from_description():
    desc = """
    Check out the timestamps below:
    00:00 Introduction
    [01:30] - Discussion Begins
    (05:45) Deep Dive into Topic
    01:15:30 Concluding Thoughts
    Some other text without timestamps
    """
    chapters = parse_chapters_from_description(desc)
    assert len(chapters) == 4
    assert chapters[0] == {"time": "00:00:00", "title": "Introduction"}
    assert chapters[1] == {"time": "00:01:30", "title": "Discussion Begins"}
    assert chapters[2] == {"time": "00:05:45", "title": "Deep Dive into Topic"}
    assert chapters[3] == {"time": "01:15:30", "title": "Concluding Thoughts"}

def test_extract_chapters_native_and_fallback():
    # 1. Native chapters in info.json
    native_info = {
        "chapters": [
            {"start_time": 0.0, "end_time": 60.0, "title": "Intro"},
            {"start_time": 65.5, "end_time": 180.0, "title": "Chapter 2"}
        ],
        "description": "00:00 Wrong Fallback"
    }
    chapters = extract_chapters(native_info)
    assert len(chapters) == 2
    assert chapters[0] == {"time": "00:00:00", "title": "Intro"}
    assert chapters[1] == {"time": "00:01:05", "title": "Chapter 2"}
    
    # 2. Fallback to description when chapters is empty
    fallback_info = {
        "chapters": [],
        "description": "00:00 Intro\n02:30 Main Segment"
    }
    chapters_fb = extract_chapters(fallback_info)
    assert len(chapters_fb) == 2
    assert chapters_fb[1] == {"time": "00:02:30", "title": "Main Segment"}

def test_rss_generation_with_psc_chapters(tmp_path):
    downloads_dir = tmp_path / "downloads"
    feeds_dir = tmp_path / "feeds"
    downloads_dir.mkdir()
    feeds_dir.mkdir()
    
    feed_dir = downloads_dir / "ChapterFeed"
    feed_dir.mkdir()
    
    (feed_dir / "ch_ep1.m4a").write_bytes(b"audio")
    (feed_dir / "ch_ep1.info.json").write_text(json.dumps({
        "id": "ch_ep1",
        "title": "Episode with Chapters",
        "chapters": [
            {"start_time": 0.0, "title": "Start"},
            {"start_time": 90.0, "title": "Middle"}
        ]
    }), encoding="utf-8")
    
    with patch.object(settings, "DOWNLOADS_DIR", downloads_dir), \
         patch.object(settings, "FEEDS_DIR", feeds_dir), \
         patch.object(settings, "BASE_URL", "http://localhost:8000"):
        
        generate_rss("ChapterFeed", feed_dir)
        
        tree = ET.parse(feeds_dir / "ChapterFeed.xml")
        root = tree.getroot()
        item = root.find("channel/item")
        
        # Verify psc:chapters and psc:chapter tags
        psc_chapters = item.find("{http://podlove.org/simple-chapters}chapters")
        assert psc_chapters is not None
        chapter_elements = psc_chapters.findall("{http://podlove.org/simple-chapters}chapter")
        assert len(chapter_elements) == 2
        assert chapter_elements[0].attrib["start"] == "00:00:00"
        assert chapter_elements[0].attrib["title"] == "Start"
        assert chapter_elements[1].attrib["start"] == "00:01:30"
        assert chapter_elements[1].attrib["title"] == "Middle"
