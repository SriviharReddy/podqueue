import sys
import os
import time
import subprocess
import logging
import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from filelock import FileLock, Timeout
from podqueue.config import settings
from podqueue.core.downloader import run_download_job
from podqueue.core.rss import run_rss_job

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")

class JobState:
    def __init__(self):
        self.running = False
        self.current_job = None
        self.last_job = None
        self.last_run = None
        self.last_exit_code = 0

state = JobState()
state_lock = asyncio.Lock()
job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="podqueue_job")

def shutdown_job_runner():
    job_executor.shutdown(wait=False)

def get_file_lock():
    return FileLock(settings.LOCK_FILE, timeout=1)

def sync_pipeline(force: bool = False):
    """Sequence download job followed by RSS generation"""
    run_download_job(force=force)
    run_rss_job()

def is_supervised() -> bool:
    """Detect if running under a supervisor (e.g. systemd) or configured for auto-restart."""
    if "INVOCATION_ID" in os.environ or "JOURNAL_STREAM" in os.environ:
        return True
    auto_restart = os.getenv("AUTO_RESTART_ON_UPDATE", "").strip().lower()
    return auto_restart in ("1", "true", "yes", "on")

def update_ytdlp():
    """Runs pip update on yt-dlp, yt-dlp-ejs, and gallery-dl, restarting only if supervised."""
    job_logger.info("Updating yt-dlp, yt-dlp-ejs, and gallery-dl using pip...")
    cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "yt-dlp-ejs", "gallery-dl"]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    job_logger.info(result.stdout)
    
    if result.returncode != 0:
        raise RuntimeError(f"pip install failed with exit code {result.returncode}")
        
    if is_supervised():
        job_logger.info("Supervisor detected (e.g. systemd). Process exiting now to trigger auto-restart.")
        time.sleep(1)
        os._exit(0)
    else:
        job_logger.info("Upstream tools updated successfully. No supervisor detected; please restart PodQueue to load updated packages.")
async def run_job_safely(job_name: str, sync_func, *args, **kwargs) -> bool:
    """Run a job in a thread pool with file-based locking to prevent concurrent execution"""
    async with state_lock:
        if state.running:
            job_logger.warning(f"Job '{state.current_job}' is already running. Cannot start '{job_name}'.")
            return False
        state.running = True
        state.current_job = job_name

    exit_code = 0
    lock = get_file_lock()
    
    # Run the blocking function in asyncio thread pool
    def _execute():
        lock_acquired = False
        try:
            lock.acquire()
            lock_acquired = True
            job_logger.info(f"Lock acquired. Running job: {job_name}")
            sync_func(*args, **kwargs)
        except Timeout:
            job_logger.error(f"Could not acquire file lock for '{job_name}'. Another process is running.")
            nonlocal exit_code
            exit_code = 1
        except Exception as e:
            job_logger.error(f"Error executing job '{job_name}': {e}", exc_info=True)
            exit_code = 1
        finally:
            if lock_acquired and lock.is_locked:
                try:
                    lock.release()
                except Exception:
                    pass

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(job_executor, _execute)
    finally:
        async with state_lock:
            state.running = False
            state.last_job = state.current_job or job_name
            state.current_job = None
            state.last_run = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state.last_exit_code = exit_code
    return exit_code == 0
