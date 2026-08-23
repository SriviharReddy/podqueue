import json
from pathlib import Path
from podqueue.core.downloader import cleanup_leftovers, cleanup_old_episodes

def test_cleanup_leftovers(tmp_path):
    download_dir = tmp_path / "TestChan"
    download_dir.mkdir()
    
    # Create legitimate files
    (download_dir / "valid_ep.m4a").write_bytes(b"audio")
    (download_dir / "valid_ep.info.json").write_text(json.dumps({"title": "Valid"}), encoding="utf-8")
    
    # Create leftover junk
    (download_dir / "temp1.temp.m4a").write_bytes(b"temp")
    (download_dir / "temp2.part").write_bytes(b"part")
    (download_dir / "temp3.temp.mp4").write_bytes(b"mp4")
    (download_dir / "temp4.ytdl").write_bytes(b"ytdl")
    
    cleanup_leftovers(download_dir)
    
    assert (download_dir / "valid_ep.m4a").exists()
    assert (download_dir / "valid_ep.info.json").exists()
    assert not (download_dir / "temp1.temp.m4a").exists()
    assert not (download_dir / "temp2.part").exists()
    assert not (download_dir / "temp3.temp.mp4").exists()
    assert not (download_dir / "temp4.ytdl").exists()

def test_cleanup_old_episodes_limit_pruning(tmp_path):
    download_dir = tmp_path / "LimitChan"
    download_dir.mkdir()
    archive_file = download_dir / "archive.txt"
    
    # Create 4 episodes with upload_date metadata
    for i, date_str in enumerate(["20260101", "20260201", "20260301", "20260401"]):
        ep_id = f"ep_{i}"
        (download_dir / f"{ep_id}.m4a").write_bytes(b"audio")
        (download_dir / f"{ep_id}.info.json").write_text(
            json.dumps({"id": ep_id, "upload_date": date_str}),
            encoding="utf-8"
        )
        
    # Limit is 2 -> newest 2 (ep_3: 20260401, ep_2: 20260301) should remain, ep_0 and ep_1 should be deleted
    cleanup_old_episodes(download_dir, archive_file, limit=2)
    
    assert (download_dir / "ep_3.m4a").exists()
    assert (download_dir / "ep_3.info.json").exists()
    assert (download_dir / "ep_2.m4a").exists()
    assert (download_dir / "ep_2.info.json").exists()
    
    assert not (download_dir / "ep_1.m4a").exists()
    assert not (download_dir / "ep_1.info.json").exists()
    assert not (download_dir / "ep_0.m4a").exists()
    assert not (download_dir / "ep_0.info.json").exists()

def test_cleanup_old_episodes_ignores_temp_files(tmp_path):
    """Verify that in-progress temp files do not displace legitimate episodes during cleanup."""
    download_dir = tmp_path / "TempIgnoreChan"
    download_dir.mkdir()
    archive_file = download_dir / "archive.txt"
    
    # Create 2 valid episodes
    (download_dir / "ep_1.m4a").write_bytes(b"audio")
    (download_dir / "ep_1.info.json").write_text(json.dumps({"upload_date": "20260101"}), encoding="utf-8")
    (download_dir / "ep_2.m4a").write_bytes(b"audio")
    (download_dir / "ep_2.info.json").write_text(json.dumps({"upload_date": "20260201"}), encoding="utf-8")
    
    # Create a temp file
    (download_dir / "ep_3.temp.m4a").write_bytes(b"temp")
    
    # Limit is 2. Both valid episodes must survive because the temp file should be ignored
    cleanup_old_episodes(download_dir, archive_file, limit=2)
    
    assert (download_dir / "ep_1.m4a").exists()
    assert (download_dir / "ep_2.m4a").exists()
