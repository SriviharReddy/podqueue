import sys
import os
import time
import subprocess
import logging
import datetime
import asyncio
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
        self.last_run = None
        self.last_exit_code = 0

state = JobState()
state_lock = asyncio.Lock()

def get_file_lock():
    return FileLock(settings.LOCK_FILE, timeout=1)

def sync_pipeline(force: bool = False):
    """Sequence download job followed by RSS generation"""
    run_download_job(force=force)
    run_rss_job()

def update_ytdlp():
    """Runs pip update on yt-dlp and yt-dlp-ejs, and exits process to let systemd restart it"""
    job_logger.info("Updating yt-dlp and yt-dlp-ejs using pip...")
    cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "yt-dlp-ejs"]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    job_logger.info(result.stdout)
    
    if result.returncode != 0:
        raise RuntimeError(f"pip install failed with exit code {result.returncode}")
        
    job_logger.info("yt-dlp updated successfully. Process exiting now to trigger systemd auto-restart.")
    # Flush logs and exit
    time.sleep(1)
    os._exit(0)

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
        await asyncio.to_thread(_execute)
    finally:
        async with state_lock:
            state.running = False
            state.current_job = None
            state.last_run = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state.last_exit_code = exit_code

    return exit_code == 0
