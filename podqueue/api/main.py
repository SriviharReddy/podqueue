import logging
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import asyncio
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from podqueue.config import settings, ROOT_DIR
from podqueue.api.auth import router as auth_router, require_auth
from podqueue.api.channels import router as channels_router
from podqueue.api.jobs import router as jobs_router
from podqueue.core.scheduler import init_scheduler, shutdown_scheduler

logger = logging.getLogger("podqueue")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    loop = asyncio.get_running_loop()
    # Configure default executor to 1 thread for yt-dlp/ffmpeg standard bounds
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    
    # Initialize background scheduler
    init_scheduler(loop)
    
    yield
    
    # Shutdown actions
    shutdown_scheduler()
    executor.shutdown(wait=True)

app = FastAPI(
    title="PodQueue API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

# Enable signed session cookies
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="podqueue_session",
    max_age=30 * 24 * 3600  # 30 days
)

# Register routers
app.include_router(auth_router)
app.include_router(channels_router)
app.include_router(jobs_router)

# GET /api/feeds - lists generated RSS feeds with metadata
@app.get("/api/feeds")
async def list_feeds(request: Request):
    require_auth(request)
    feeds = []
    
    if settings.FEEDS_DIR.exists():
        for file_path in settings.FEEDS_DIR.glob("*.xml"):
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                channel = root.find("channel")
                title = channel.find("title").text if channel is not None and channel.find("title") is not None else file_path.stem
                
                downloads_subdir = settings.DOWNLOADS_DIR / file_path.stem
                audio_count = len(list(downloads_subdir.glob("*.m4a"))) if downloads_subdir.exists() else 0
                
                feeds.append({
                    "name": file_path.stem,
                    "title": title,
                    "url": f"{settings.BASE_URL}/feeds/{file_path.name}",
                    "audio_count": audio_count
                })
            except Exception as e:
                logger.error(f"Error parsing feed {file_path.name}: {e}")
                feeds.append({
                    "name": file_path.stem,
                    "title": file_path.stem,
                    "url": f"{settings.BASE_URL}/feeds/{file_path.name}",
                    "audio_count": 0
                })
    return feeds

# Public static mounts (without auth) supporting range requests
app.mount("/feeds", StaticFiles(directory=str(settings.FEEDS_DIR)), name="feeds")
app.mount("/downloads", StaticFiles(directory=str(settings.DOWNLOADS_DIR)), name="downloads")
app.mount("/artwork", StaticFiles(directory=str(settings.ARTWORK_DIR)), name="artwork")

# Serve frontend at root last
static_dir = ROOT_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
