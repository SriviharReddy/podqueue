import json
import threading
import pytest
from unittest.mock import patch
from podqueue.core.channels import (
    Channel,
    load_channels,
    save_channels,
    add_channel,
    update_channel,
    delete_channel,
    load_channels_sync,
    save_channels_sync,
    add_channel_sync,
    update_channel_sync,
    delete_channel_sync,
)
from podqueue.config import settings

@pytest.mark.asyncio
async def test_channels_async_crud(tmp_path):
    channels_file = tmp_path / "channels.json"
    with patch.object(settings, "CHANNELS_FILE", channels_file):
        # Empty initial
        channels = await load_channels()
        assert channels == []
        
        # Add channel 1
        chan1 = Channel(id="Chan1", url="https://youtube.com/@Chan1", limit=5)
        assert await add_channel(chan1) is True
        
        # Adding duplicate should return False
        assert await add_channel(chan1) is False
        
        # Load and verify
        loaded = await load_channels()
        assert len(loaded) == 1
        assert loaded[0].id == "Chan1"
        assert loaded[0].limit == 5
        
        # Update channel
        assert await update_channel("Chan1", limit=10, sponsorblock=True, check_interval_hours=2) is True
        loaded = await load_channels()
        assert loaded[0].limit == 10
        assert loaded[0].sponsorblock is True
        assert loaded[0].check_interval_hours == 2
        
        # Update non-existent channel
        assert await update_channel("NonExistent", limit=10, sponsorblock=False, check_interval_hours=1) is False
        
        # Delete channel
        assert await delete_channel("Chan1") is True
        assert await delete_channel("Chan1") is False
        assert await load_channels() == []

def test_channels_sync_crud(tmp_path):
    channels_file = tmp_path / "channels.json"
    with patch.object(settings, "CHANNELS_FILE", channels_file):
        chan = Channel(id="SyncChan", url="https://youtube.com/@SyncChan", limit=3)
        assert add_channel_sync(chan) is True
        
        loaded = load_channels_sync()
        assert len(loaded) == 1
        assert loaded[0].id == "SyncChan"
        
        assert update_channel_sync("SyncChan", limit=7, sponsorblock="sponsor", check_interval_hours=4) is True
        loaded = load_channels_sync()
        assert loaded[0].limit == 7
        assert loaded[0].sponsorblock == "sponsor"
        
        assert delete_channel_sync("SyncChan") is True
        assert load_channels_sync() == []

def test_atomic_write_safety(tmp_path):
    channels_file = tmp_path / "channels.json"
    with patch.object(settings, "CHANNELS_FILE", channels_file):
        chan = Channel(id="AtomicChan", url="https://youtube.com/@AtomicChan")
        add_channel_sync(chan)
        
        # Verify file exists and is valid JSON
        assert channels_file.exists()
        data = json.loads(channels_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["id"] == "AtomicChan"
        
        # Verify no temp files remain in directory
        temp_files = list(tmp_path.glob("*.tmp*"))
        assert len(temp_files) == 0

def test_concurrent_multithreaded_crud(tmp_path):
    """Stress test concurrent channel operations across multiple threads."""
    channels_file = tmp_path / "channels.json"
    with patch.object(settings, "CHANNELS_FILE", channels_file):
        def worker(thread_idx):
            for i in range(10):
                chan_id = f"ThreadChan_{thread_idx}_{i}"
                chan = Channel(id=chan_id, url=f"https://youtube.com/@{chan_id}")
                add_channel_sync(chan)
                update_channel_sync(chan_id, limit=i + 1, sponsorblock=False, check_interval_hours=1)
                load_channels_sync()
                if i % 2 == 0:
                    delete_channel_sync(chan_id)
        
        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        # File must remain valid JSON without corruption
        assert channels_file.exists()
        loaded = load_channels_sync()
        assert isinstance(loaded, list)
