import shutil
import asyncio
import logging
from typing import List, Union
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from podqueue.config import settings
from podqueue.core.channels import Channel, load_channels, add_channel, update_channel, delete_channel
from podqueue.api.auth import require_auth
from podqueue.core.downloader import resolve_channel_url

router = APIRouter(prefix="/api")
logger = logging.getLogger("podqueue")

class ChannelCreate(BaseModel):
    id: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1)
    sponsorblock: Union[bool, str] = False
    check_interval_hours: int = Field(default=1, ge=1)

class ChannelUpdate(BaseModel):
    limit: int = Field(..., ge=1)
    sponsorblock: Union[bool, str] = False
    check_interval_hours: int = Field(..., ge=1)

@router.get("/channels")
async def list_channels(request: Request):
    require_auth(request)
    channels = await load_channels()
    result = []
    for c in channels:
        # Check files count
        downloads_subdir = settings.DOWNLOADS_DIR / c.id
        audio_count = 0
        if downloads_subdir.exists():
            audio_count = len(list(downloads_subdir.glob("*.m4a")))
            
        last_check = None
        next_check = None
        last_check_file = settings.STATE_DIR / f"{c.id}.last_check"
        if last_check_file.exists():
            try:
                val = last_check_file.read_text().strip()
                if val.isdigit():
                    t = int(val)
                    last_check = t
                    next_check = t + (c.check_interval_hours * 3600)
            except Exception:
                pass
                
        result.append({
            "id": c.id,
            "url": c.url,
            "limit": c.limit,
            "sponsorblock": c.sponsorblock,
            "check_interval_hours": c.check_interval_hours,
            "audio_count": audio_count,
            "last_check": last_check,
            "next_check": next_check
        })
    return result

@router.post("/channels")
async def create_channel(request: Request, data: ChannelCreate):
    require_auth(request)
    
    # Auto convert @username URLs in a thread pool
    try:
        resolved_url = await asyncio.to_thread(resolve_channel_url, data.url, settings.COOKIES_FILE)
    except Exception as e:
        logger.error(f"Failed to resolve channel URL {data.url}: {e}")
        resolved_url = data.url
        
    new_chan = Channel(
        id=data.id,
        url=resolved_url,
        limit=data.limit,
        sponsorblock=data.sponsorblock,
        check_interval_hours=data.check_interval_hours
    )
    
    success = await add_channel(new_chan)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Channel with ID '{data.id}' already exists."
        )
        
    return {"status": "ok", "channel": new_chan}

@router.put("/channels/{channel_id}")
async def edit_channel(request: Request, channel_id: str, data: ChannelUpdate):
    require_auth(request)
    success = await update_channel(
        channel_id,
        data.limit,
        data.sponsorblock,
        data.check_interval_hours
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found"
        )
    return {"status": "ok", "message": f"Channel '{channel_id}' updated successfully."}

@router.delete("/channels/{channel_id}")
async def remove_channel_api(request: Request, channel_id: str):
    require_auth(request)
    success = await delete_channel(channel_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found"
        )
        
    # Clean up physical files
    download_dir = settings.DOWNLOADS_DIR / channel_id
    feed_file = settings.FEEDS_DIR / f"{channel_id}.xml"
    state_file = settings.STATE_DIR / f"{channel_id}.last_check"
    artwork_file = settings.ARTWORK_DIR / f"{channel_id}.jpg"
    
    if download_dir.exists():
        shutil.rmtree(download_dir, ignore_errors=True)
    if feed_file.exists():
        feed_file.unlink(missing_ok=True)
    if state_file.exists():
        state_file.unlink(missing_ok=True)
    if artwork_file.exists():
        artwork_file.unlink(missing_ok=True)
        
    return {"status": "ok", "message": f"Channel '{channel_id}' and all associated files deleted."}
