import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from podqueue.core.pawchive import is_pawchive_url, strip_html_tags, run_pawchive_download
from podqueue.core.channels import Channel
from podqueue.config import settings

def test_is_pawchive_url():
    assert is_pawchive_url("https://pawchive.st/patreon/user123") is True
    assert is_pawchive_url("https://pawchive.pw/user456") is True
    assert is_pawchive_url("https://www.youtube.com/@somecreator") is False
    assert is_pawchive_url("https://youtu.be/12345") is False

def test_strip_html_tags():
    html_input = "<p>Hello <b>World</b>!</p><br><p>Second paragraph with <a href='https://example.com'>link</a></p>"
    clean = strip_html_tags(html_input)
    assert "<b>" not in clean
    assert "<p>" not in clean
    assert "Hello World!" in clean
    assert "Second paragraph with link" in clean

def test_ndjson_parsing_resilience(tmp_path):
    """Verify that multiple JSON lines (NDJSON) output from gallery-dl is parsed correctly without JSONDecodeError."""
    sample_ndjson = (
        '["2", {"id": "1001", "title": "Post 1", "date": "2026-07-20 12:00:00", "attachments": [{"url": "https://example.com/audio1.mp3", "extension": "mp3"}]}]\n'
        '["2", {"id": "1002", "title": "Post 2", "date": "2026-07-21 12:00:00", "attachments": [{"url": "https://example.com/audio2.m4a", "extension": "m4a"}]}]\n'
        'invalid json line that should be skipped\n'
        '["2", {"id": "1003", "title": "Post 3", "date": "2026-07-22 12:00:00", "attachments": []}]\n'
    )
    
    channel = Channel(id="TestPawchiveChan", url="https://pawchive.st/user/test", limit=5)
    
    # Mock subprocess.run for gallery-dl and requests.get for file downloads
    with patch("subprocess.run") as mock_subproc, \
         patch("requests.get") as mock_requests_get, \
         patch("podqueue.utils.media.get_audio_duration", return_value=120):
        
        mock_subproc.return_value = MagicMock(returncode=0, stdout=sample_ndjson, stderr="")
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content = MagicMock(return_value=[b"fake_audio_chunk_1", b"fake_audio_chunk_2"])
        mock_resp.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_resp
        
        # Point settings dirs to tmp_path
        with patch.object(settings, "DATA_DIR", tmp_path), \
             patch.object(settings, "DOWNLOADS_DIR", tmp_path / "downloads"), \
             patch.object(settings, "STATE_DIR", tmp_path / "state"):
            
            (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            
            run_pawchive_download(channel, force=True)
            
            chan_dir = tmp_path / "downloads" / "TestPawchiveChan"
            assert (chan_dir / "1001.mp3").exists()
            assert (chan_dir / "1001.info.json").exists()
            assert (chan_dir / "1002.m4a").exists()
            assert (chan_dir / "1002.info.json").exists()
            
            info1 = json.loads((chan_dir / "1001.info.json").read_text(encoding="utf-8"))
            assert info1["title"] == "Post 1"
            assert info1["duration"] == 120

def test_pawchive_download_range_resume_206_vs_200(tmp_path):
    """Verify that HTTP 206 appends to partial file, but HTTP 200 replaces/truncates."""
    channel = Channel(id="RangeTestChan", url="https://pawchive.st/user/range", limit=1)
    
    sample_ndjson = (
        '["2", {"id": "2001", "title": "Post Range", "date": "2026-07-22 12:00:00", "attachments": [{"url": "https://example.com/audio.mp3", "extension": "mp3"}]}]\n'
    )
    
    with patch("subprocess.run") as mock_subproc, \
         patch("requests.get") as mock_requests_get, \
         patch("podqueue.utils.media.get_audio_duration", return_value=60):
        
        mock_subproc.return_value = MagicMock(returncode=0, stdout=sample_ndjson, stderr="")
        
        # Pre-create a partial temp file
        chan_dir = tmp_path / "downloads" / "RangeTestChan"
        chan_dir.mkdir(parents=True, exist_ok=True)
        temp_file = chan_dir / "2001.temp.mp3"
        temp_file.write_bytes(b"INITIAL_PARTIAL_BYTES_")
        
        # Test Case A: Server returns 200 OK (ignored Range) -> must overwrite, not append
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.iter_content = MagicMock(return_value=[b"FULL_NEW_FILE_BYTES"])
        mock_resp_200.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_resp_200
        
        with patch.object(settings, "DOWNLOADS_DIR", tmp_path / "downloads"), \
             patch.object(settings, "STATE_DIR", tmp_path / "state"):
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            
            run_pawchive_download(channel, force=True)
            
            dest_file = chan_dir / "2001.mp3"
            assert dest_file.exists()
            content = dest_file.read_bytes()
            assert content == b"FULL_NEW_FILE_BYTES"
            assert b"INITIAL_PARTIAL_BYTES_" not in content
