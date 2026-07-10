import logging
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from podqueue.config import settings
from podqueue.core.job_runner import run_job_safely, sync_pipeline, update_ytdlp

logger = logging.getLogger("podqueue")
scheduler = BackgroundScheduler()
_loop = None

def trigger_sync_job():
    if _loop:
        logger.info("Triggering scheduled sync job...")
        asyncio.run_coroutine_threadsafe(
            run_job_safely("Sync (Scheduled)", sync_pipeline),
            _loop
        )
    else:
        logger.error("Scheduler triggered sync job but event loop is not set.")

def trigger_update_job():
    if _loop:
        logger.info("Triggering scheduled yt-dlp update job...")
        asyncio.run_coroutine_threadsafe(
            run_job_safely("Update yt-dlp (Scheduled)", update_ytdlp),
            _loop
        )
    else:
        logger.error("Scheduler triggered update job but event loop is not set.")

def init_scheduler(loop):
    global _loop
    _loop = loop
    
    interval = settings.SCHEDULE_INTERVAL_MINUTES
    scheduler.add_job(
        trigger_sync_job,
        'interval',
        minutes=interval,
        id='sync_job',
        replace_existing=True
    )
    
    scheduler.add_job(
        trigger_update_job,
        'interval',
        days=1,
        id='update_job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"Scheduler started. Hourly sync interval: {interval} minutes.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down.")
