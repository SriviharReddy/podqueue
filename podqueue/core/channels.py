import json
import logging
from typing import List, Union
from pydantic import BaseModel, Field
import asyncio
from podqueue.config import settings

logger = logging.getLogger("podqueue")

class Channel(BaseModel):
    id: str
    url: str
    limit: int = Field(default=5, ge=1)
    sponsorblock: Union[bool, str] = False
    check_interval_hours: int = Field(default=1, ge=1)

# In-process asyncio Lock for serializing CRUD
_channels_lock = asyncio.Lock()

def _load_channels_raw() -> list:
    if not settings.CHANNELS_FILE.exists():
        return []
    try:
        with open(settings.CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading channels.json: {e}")
        return []

def _save_channels_raw(channels_data: list):
    try:
        settings.CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving channels.json: {e}")
        raise

async def load_channels() -> List[Channel]:
    async with _channels_lock:
        raw = _load_channels_raw()
        channels = []
        for item in raw:
            try:
                channels.append(Channel(**item))
            except Exception as e:
                logger.error(f"Error parsing channel record {item}: {e}")
        return channels

async def save_channels(channels: List[Channel]):
    async with _channels_lock:
        data = [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in channels]
        _save_channels_raw(data)

async def add_channel(channel: Channel) -> bool:
    async with _channels_lock:
        raw = _load_channels_raw()
        # Check if already exists
        for item in raw:
            if item.get("id") == channel.id:
                return False
        
        raw.append(channel.model_dump() if hasattr(channel, "model_dump") else channel.dict())
        _save_channels_raw(raw)
        return True

async def update_channel(channel_id: str, limit: int, sponsorblock: Union[bool, str], check_interval_hours: int) -> bool:
    async with _channels_lock:
        raw = _load_channels_raw()
        updated = False
        for item in raw:
            if item.get("id") == channel_id:
                item["limit"] = limit
                item["sponsorblock"] = sponsorblock
                item["check_interval_hours"] = check_interval_hours
                updated = True
                break
        if updated:
            _save_channels_raw(raw)
        return updated

async def delete_channel(channel_id: str) -> bool:
    async with _channels_lock:
        raw = _load_channels_raw()
        initial_len = len(raw)
        raw = [item for item in raw if item.get("id") != channel_id]
        if len(raw) < initial_len:
            _save_channels_raw(raw)
            return True
        return False
