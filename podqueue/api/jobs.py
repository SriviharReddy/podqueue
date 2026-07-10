import os
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from podqueue.config import settings
from podqueue.api.auth import require_auth
from podqueue.core.job_runner import run_job_safely, sync_pipeline, update_ytdlp, state
from podqueue.core.rss import run_rss_job

router = APIRouter(prefix="/api")
logger = logging.getLogger("podqueue")

class DownloadTriggerRequest(BaseModel):
    force: bool = False

@router.post("/jobs/download")
async def trigger_download(request: Request, data: DownloadTriggerRequest = None):
    require_auth(request)
    force = data.force if data else False
    
    # Run in background task
    asyncio.create_task(run_job_safely("Sync", sync_pipeline, force=force))
    return {"status": "ok", "message": "Download and RSS sync job triggered."}

@router.post("/jobs/rss")
async def trigger_rss(request: Request):
    require_auth(request)
    asyncio.create_task(run_job_safely("RSS Generation", run_rss_job))
    return {"status": "ok", "message": "RSS generation job triggered."}

@router.post("/jobs/update-ytdlp")
async def trigger_update(request: Request):
    require_auth(request)
    asyncio.create_task(run_job_safely("Update yt-dlp", update_ytdlp))
    return {"status": "ok", "message": "yt-dlp update job triggered."}

@router.get("/jobs/status")
async def get_jobs_status(request: Request):
    require_auth(request)
    return {
        "running": state.running,
        "current_job": state.current_job,
        "last_run": state.last_run,
        "last_exit_code": state.last_exit_code
    }

@router.get("/jobs/logs/stream")
async def stream_logs(request: Request):
    require_auth(request)
    
    async def log_generator():
        log_file_path = settings.LOGS_DIR / "last_job.log"
        last_id = request.headers.get("last-event-id")
        offset = 0
        
        if last_id and last_id.isdigit():
            offset = int(last_id)
            
        while True:
            if await request.is_disconnected():
                break
                
            if not log_file_path.exists():
                await asyncio.sleep(1.0)
                continue
                
            try:
                # Open with ignore to handle any weird encoding issues gracefully
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    file_size = os.path.getsize(log_file_path)
                    if offset > file_size:
                        # File rotated/truncated
                        offset = 0
                        
                    f.seek(offset)
                    
                    while True:
                        line = f.readline()
                        if not line:
                            break
                        offset = f.tell()
                        # Send line inside EventSource data field
                        yield f"id: {offset}\ndata: {line.rstrip()}\n\n"
            except Exception as e:
                logger.error(f"Error reading last_job.log in SSE: {e}")
                
            await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")
