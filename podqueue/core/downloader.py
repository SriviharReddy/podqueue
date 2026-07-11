import os
import time
import json
import logging
import gc
import yt_dlp
from pathlib import Path
from typing import List
from podqueue.config import settings
from podqueue.core.channels import Channel, load_channels

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")

def get_valid_cookies_file() -> str | None:
    path = settings.COOKIES_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline()
            if "# Netscape HTTP Cookie File" in first_line:
                return str(path)
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                if len(line.split("\t")) >= 7:
                    return str(path)
    except Exception:
        pass
    
    logger.warning(f"Cookies file '{path}' is not a valid Netscape format cookies file. Running without cookies.")
    return None

class YTDLPLogger:
    def __init__(self, logger_obj):
        self.logger = logger_obj

    def debug(self, msg):
        # Filter out verbose debug logs unless needed
        if not msg.startswith('[debug]'):
            self.logger.info(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

def ytdlp_progress_hook(d):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        if total:
            percent = int(downloaded / total * 100)
            # Only log every 20% to prevent console spam in Web UI
            last_percent = getattr(ytdlp_progress_hook, 'last_percent', -20)
            if percent >= last_percent + 20 or percent >= 100:
                ytdlp_progress_hook.last_percent = percent
                speed = d.get('_speed_str', 'unknown speed')
                eta = d.get('_eta_str', 'unknown ETA')
                job_logger.info(f"[download] {percent}% of {total / (1024*1024):.2f}MiB at {speed} ETA {eta}")
    elif d['status'] == 'finished':
        # Reset last_percent for next download
        ytdlp_progress_hook.last_percent = -20
        job_logger.info(f"Finished downloading: {d.get('filename')}. Processing...")

def resolve_channel_url(url: str, cookies_file: Path = None) -> str:
    """Resolve @username or custom channel URL to standard channel URL and ensure it points to the videos tab"""
    resolved = url
    if "@" in url and "youtube.com" in url:
        cookie_path = get_valid_cookies_file() if cookies_file == settings.COOKIES_FILE else (str(cookies_file) if cookies_file and cookies_file.exists() else None)
        opts = {
            'extract_flat': True,
            'playlistend': 1,
            'cookiefile': cookie_path,
            'quiet': True,
            'no_warnings': True,
            'proxy': settings.YTDLP_PROXY,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                channel_id = info.get('channel_id') or info.get('id')
                if channel_id:
                    resolved = f"https://www.youtube.com/channel/{channel_id}"
                    logger.info(f"Resolved URL {url} to {resolved}")
            except Exception as e:
                logger.error(f"Error resolving channel URL {url}: {e}")
                
    # If the URL points to a channel, ensure it targets the videos tab to extract individual uploads
    if ("/channel/" in resolved or "/c/" in resolved or "/user/" in resolved) and not any(x in resolved for x in ["/videos", "/shorts", "/streams", "/playlists", "watch?v=", "playlist?"]):
        resolved = resolved.rstrip("/") + "/videos"
        logger.info(f"Appended /videos to channel URL: {resolved}")
        
    return resolved

def cleanup_old_episodes(download_dir: Path, archive_file: Path, limit: int):
    """Delete old episodes exceeding the limit, sorting by modification time (newest first)"""
    audio_files = sorted(
        list(download_dir.glob("*.m4a")),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    audio_count = len(audio_files)
    job_logger.info(f"[{download_dir.name}] Found {audio_count} audio files, limit is {limit}")
    
    if audio_count > limit:
        to_delete = audio_files[limit:]
        for file_path in to_delete:
            job_logger.info(f"[{download_dir.name}] Deleting old episode: {file_path.name}")
            
            # Delete info.json
            info_file = file_path.with_suffix(".info.json")
            video_id = file_path.stem
            
            if info_file.exists():
                try:
                    info_file.unlink()
                except Exception as e:
                    job_logger.error(f"Error deleting info file {info_file}: {e}")
                    
            try:
                file_path.unlink()
            except Exception as e:
                job_logger.error(f"Error deleting audio file {file_path}: {e}")
                
            # Remove from archive file
            if archive_file.exists():
                job_logger.info(f"[{download_dir.name}] Removing {video_id} from archive file")
                try:
                    lines = []
                    with open(archive_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    with open(archive_file, "w", encoding="utf-8") as f:
                        for line in lines:
                            if f"youtube {video_id}" not in line:
                                f.write(line)
                except Exception as e:
                    job_logger.error(f"Error updating archive file: {e}")

def cleanup_leftovers(download_dir: Path):
    """Clean up leftover temp files"""
    job_logger.info(f"[{download_dir.name}] Cleaning up leftover temp and mp4 files...")
    for ext in ("*.mp4", "*.temp.mp4", "*.part", "*.ytdl"):
        for f in download_dir.glob(ext):
            if f.is_file() and not f.name.endswith(".info.json"):
                try:
                    f.unlink()
                    job_logger.info(f"Deleted leftover: {f.name}")
                except Exception as e:
                    job_logger.error(f"Error deleting leftover {f.name}: {e}")

def run_download_job(force: bool = False):
    """Run yt-dlp downloads for all configured channels"""
    job_logger.info("Starting YouTube podcast sync...")
    
    channels = []
    # Run load_channels synchronously by creating a loop or since we are in to_thread, we run it inside the async event loop of the app.
    # Wait, load_channels is an async function. Since run_download_job is running in a thread pool (asyncio.to_thread),
    # we can run load_channels synchronously by using asyncio.run() or if a loop is already running in this thread, we fetch it.
    # Actually, let's create a helper to load channels synchronously, or run it via asyncio.run().
    import asyncio
    try:
        channels = asyncio.run(load_channels())
    except RuntimeError:
        # If loop is already running in this thread (unlikely for to_thread), use next method
        loop = asyncio.new_event_loop()
        channels = loop.run_until_complete(load_channels())
        loop.close()

    if not channels:
        job_logger.info("No channels configured. Sync complete.")
        return

    for channel in channels:
        job_logger.info(f"--- Processing: {channel.id} ---")
        
        # Check interval
        last_check_file = settings.STATE_DIR / f"{channel.id}.last_check"
        current_time = int(time.time())
        
        if not force and last_check_file.exists():
            try:
                last_check_str = last_check_file.read_text().strip()
                if last_check_str.isdigit():
                    last_check_time = int(last_check_str)
                    next_check_time = last_check_time + (channel.check_interval_hours * 3600)
                    if current_time < next_check_time:
                        remaining_minutes = (next_check_time - current_time + 59) // 60
                        job_logger.info(f"Skipping {channel.id}. Next check in about {remaining_minutes} minute(s).")
                        continue
            except Exception as e:
                job_logger.error(f"Error reading last check file for {channel.id}: {e}")

        # Directory setup
        download_dir = settings.DOWNLOADS_DIR / channel.id
        download_dir.mkdir(parents=True, exist_ok=True)
        archive_file = download_dir / "archive.txt"
        
        # Clean up BEFORE download
        cleanup_old_episodes(download_dir, archive_file, channel.limit)
        
        # Build list of already downloaded video IDs
        archive_set = set()
        if archive_file.exists():
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("youtube "):
                            archive_set.add(line.split(" ")[1])
            except Exception as e:
                job_logger.error(f"Error reading archive file: {e}")

        # Flat extraction pre-pass
        playlist_scan_limit = max(20, channel.limit * 5)
        job_logger.info(f"Scanning playlist (limit {playlist_scan_limit})...")
        
        flat_opts = {
            'extract_flat': True,
            'playlistend': playlist_scan_limit,
            'cookiefile': get_valid_cookies_file(),
            'quiet': True,
            'no_warnings': True,
            'proxy': settings.YTDLP_PROXY,
        }
        
        new_videos = []
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            try:
                # If URL is an @username URL, resolve it first
                resolved_url = resolve_channel_url(channel.url, settings.COOKIES_FILE)
                info = ydl.extract_info(resolved_url, download=False)
                
                if 'entries' in info:
                    for entry in info['entries']:
                        if not entry:
                            continue
                        # Layer 2 defense: Skip entries that are actually other playlists/tabs rather than videos
                        if entry.get('_type') == 'playlist':
                            continue
                        video_id = entry.get('id')
                        video_url = entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={video_id}"
                        
                        # Filter Shorts out based on URL or title
                        title = (entry.get('title') or '').lower()
                        is_short = False
                        if video_url and '/shorts/' in video_url:
                            is_short = True
                        if '#shorts' in title or 'shorts' in title:
                            # Might be a short, but let's trust URL more.
                            pass
                            
                        if is_short:
                            continue
                            
                        if video_id and video_id not in archive_set:
                            new_videos.append((video_id, video_url))
            except Exception as e:
                job_logger.error(f"Error scanning playlist for {channel.id}: {e}")

        # Download new videos one by one (only download up to the channel limit)
        if new_videos:
            videos_to_download = new_videos[:channel.limit]
            job_logger.info(f"Limiting downloads to the newest {len(videos_to_download)} new episodes (channel limit is {channel.limit}).")
            for video_id, video_url in videos_to_download:
                job_logger.info(f"Downloading video: {video_id} ({video_url})")
                
                ydl_opts = {
                    'cookiefile': get_valid_cookies_file(),
                    'download_archive': str(archive_file),
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'm4a',
                    }],
                    'writeinfojson': True,
                    'restrictfilenames': True,
                    'logger': YTDLPLogger(job_logger),
                    'progress_hooks': [ytdlp_progress_hook],
                    'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
                    'postprocessor_args': {'ffmpeg': ['-threads', '1']},
                    'noprogress': True,
                    'quiet': True,
                    'no_warnings': True,
                    'proxy': settings.YTDLP_PROXY,
                }
                
                # Add SponsorBlock if enabled
                sb_val = channel.sponsorblock
                if sb_val:
                    cat = 'all' if sb_val in (True, 'true', '1', 'yes', 'on') else sb_val
                    ydl_opts['postprocessors'].append({
                        'key': 'SponsorBlock',
                        'categories': [cat] if isinstance(cat, str) else cat,
                    })

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        # Extract and download
                        ydl.download([video_url])
                    except Exception as e:
                        job_logger.error(f"Error downloading {video_id}: {e}")
                        
        # Clean up AFTER download
        cleanup_old_episodes(download_dir, archive_file, channel.limit)
        cleanup_leftovers(download_dir)
        
        # Write last check time
        try:
            last_check_file.write_text(str(current_time))
        except Exception as e:
            job_logger.error(f"Error writing last check file for {channel.id}: {e}")
            
        job_logger.info(f"--- Finished processing: {channel.id} ---")
        
    job_logger.info("Sync complete.")
    gc.collect()
