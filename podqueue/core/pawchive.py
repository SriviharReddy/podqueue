import sys
import os
import subprocess
import json
import logging
import time
import re
import html
import shutil
import requests
from pathlib import Path
from podqueue.config import settings
from podqueue.core.channels import Channel

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")

def is_pawchive_url(url: str) -> bool:
    return "pawchive." in url.lower()

def strip_html_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'</?p\s*[^>]*>', '\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n+', '\n', text).strip()
    return text

def run_pawchive_download(channel: Channel, force: bool = False):
    from podqueue.core.downloader import cleanup_old_episodes, cleanup_leftovers
    job_logger.info(f"Starting Pawchive podcast sync for {channel.id}...")
    
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
                    return
        except Exception as e:
            job_logger.error(f"Error reading last check file for {channel.id}: {e}")

    download_dir = settings.DOWNLOADS_DIR / channel.id
    download_dir.mkdir(parents=True, exist_ok=True)
    archive_file = download_dir / "archive.txt"
    cleanup_leftovers(download_dir)
    cleanup_old_episodes(download_dir, archive_file, channel.limit)

    # Build archive set
    archive_set = set()
    if archive_file.exists():
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    parts = line.split(" ")
                    if len(parts) >= 2 and parts[0] in ("youtube", "pawchive"):
                        archive_set.add(parts[1])
        except Exception as e:
            job_logger.error(f"Error reading archive file: {e}")

    # Resolve gallery-dl path dynamically
    gallery_dl_path = shutil.which("gallery-dl")
    if not gallery_dl_path:
        python_bin_dir = Path(sys.executable).parent
        for candidate in ["gallery-dl.exe", "gallery-dl"]:
            p = python_bin_dir / candidate
            if p.exists():
                gallery_dl_path = str(p)
                break
    if not gallery_dl_path:
        gallery_dl_path = "gallery-dl"
    # Normalize the URL for gallery-dl's pawchive extractor
    target_url = channel.url.strip().rstrip('/')
    for suffix in ['/videos', '/posts', '/files', '/photos']:
        if target_url.endswith(suffix):
            target_url = target_url[:-len(suffix)]
            break

    job_logger.info(f"Running gallery-dl metadata scan for {target_url}...")
    cmd = [
        str(gallery_dl_path),
        "--dump-json",
        "--range", f"1-{max(10, channel.limit * 2)}",
        target_url
    ]
    
    # Apply proxy if configured
    if settings.YTDLP_PROXY:
        cmd.extend(["--proxy", settings.YTDLP_PROXY])

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            job_logger.error(f"gallery-dl failed with code {result.returncode}: {result.stderr}")
            return
        
        # Parse stdout JSON Lines (one JSON object per line)
        raw_data = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    raw_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        # gallery-dl prints list of arrays where each item has format: [type_code, metadata_dict] or [type_code, url/payload, metadata_dict]
        posts_metadata = {}
        for item in raw_data:
            meta = None
            if isinstance(item, list):
                if len(item) >= 3 and isinstance(item[2], dict):
                    meta = item[2]
                elif len(item) == 2 and isinstance(item[1], dict):
                    meta = item[1]
            elif isinstance(item, dict):
                meta = item
                
            if meta:
                post_id = meta.get("id")
                if post_id:
                    posts_metadata[post_id] = meta
    except Exception as e:
        job_logger.error(f"Error executing gallery-dl: {e}")
        return

    # Download new posts
    new_posts = []
    for post_id, meta in sorted(posts_metadata.items(), key=lambda x: x[1].get("date", ""), reverse=True):
        if post_id not in archive_set:
            attachments = meta.get("attachments", [])
            audio_url = None
            audio_name = None
            audio_ext = "mp3"
            allowed_exts = {"mp3", "m4a", "wav", "flac", "ogg", "opus"}
            for att in attachments:
                ext = att.get("extension", "").lower()
                url_clean = att.get("url", "").split("?")[0].lower()
                for candidate_ext in allowed_exts:
                    if ext == candidate_ext or url_clean.endswith(f".{candidate_ext}"):
                        audio_url = att.get("url")
                        audio_ext = candidate_ext
                        audio_name = att.get("name") or f"{post_id}.{audio_ext}"
                        break
                if audio_url:
                    break
            if audio_url:
                new_posts.append((post_id, audio_url, audio_name, audio_ext, meta))

    if new_posts:
        posts_to_download = new_posts[:channel.limit]
        job_logger.info(f"Found {len(new_posts)} new posts. Downloading the newest {len(posts_to_download)} (limit {channel.limit}).")
        
        proxies = None
        if settings.YTDLP_PROXY:
            proxies = {"http": settings.YTDLP_PROXY, "https": settings.YTDLP_PROXY}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for post_id, audio_url, audio_name, audio_ext, meta in posts_to_download:
            dest_path = download_dir / f"{post_id}.{audio_ext}"
            temp_path = download_dir / f"{post_id}.temp.{audio_ext}"
            try:
                job_logger.info(f"Downloading Pawchive file: {audio_name} ({audio_url})")
                
                max_retries = 5
                attempt = 0
                success = False
                
                while attempt < max_retries and not success:
                    attempt += 1
                    downloaded_bytes = 0
                    if temp_path.exists():
                        downloaded_bytes = temp_path.stat().st_size
                    
                    headers_copy = headers.copy()
                    if downloaded_bytes > 0:
                        headers_copy["Range"] = f"bytes={downloaded_bytes}-"
                        job_logger.info(f"Resuming download from byte {downloaded_bytes} (attempt {attempt}/{max_retries})...")
                    else:
                        job_logger.info(f"Starting fresh download (attempt {attempt}/{max_retries})...")
                        
                    try:
                        response = requests.get(audio_url, headers=headers_copy, proxies=proxies, stream=True, timeout=30)
                        
                        if downloaded_bytes > 0:
                            if response.status_code == 200:
                                job_logger.warning(f"Server returned 200 OK for Range request. Restarting download from byte 0...")
                                temp_path.unlink(missing_ok=True)
                                downloaded_bytes = 0
                            elif response.status_code != 206:
                                job_logger.warning(f"Server rejected Range request with code {response.status_code}. Restarting download...")
                                temp_path.unlink(missing_ok=True)
                                downloaded_bytes = 0
                                response = requests.get(audio_url, headers=headers, proxies=proxies, stream=True, timeout=30)
                        
                        response.raise_for_status()
                        
                        mode = "ab" if (downloaded_bytes > 0 and response.status_code == 206) else "wb"
                        with open(temp_path, mode) as f:
                            for chunk in response.iter_content(chunk_size=16384):
                                if chunk:
                                    f.write(chunk)
                                    
                        success = True
                    except (requests.RequestException, Exception) as e:
                        job_logger.warning(f"Download attempt {attempt} failed: {e}")
                        if attempt >= max_retries:
                            raise e
                        else:
                            sleep_time = min(30, 2 ** attempt)
                            job_logger.info(f"Sleeping {sleep_time} seconds before retry...")
                            time.sleep(sleep_time)
                            
                if temp_path.exists() and success:
                    temp_path.rename(dest_path)
                        
                    # Extract actual duration using ffprobe
                    from podqueue.utils.media import get_audio_duration
                    duration = get_audio_duration(dest_path)

                    # Write info.json
                    info_path = download_dir / f"{post_id}.info.json"
                    raw_date = meta.get("date", "").split(" ")[0].replace("-", "")
                    artist_name = meta.get("user_profile", {}).get("name") or meta.get("username") or channel.id
                    avatar_url = f"https://pawchive.st/icons/patreon/{meta.get('user')}" if meta.get('user') else ""
                    
                    info_data = {
                        "id": post_id,
                        "title": meta.get("title") or f"Post {post_id}",
                        "upload_date": raw_date,
                        "description": strip_html_tags(meta.get("content", "")),
                        "duration": duration,
                        "channel": artist_name,
                        "thumbnails": [{"url": avatar_url, "width": 400, "height": 400}] if avatar_url else []
                    }
                    
                    with open(info_path, "w", encoding="utf-8") as f:
                        json.dump(info_data, f, indent=2)
                        
                    # Write to archive
                    with open(archive_file, "a", encoding="utf-8") as f:
                        f.write(f"pawchive {post_id}\n")
                        
                    job_logger.info(f"Successfully processed post: {post_id}")
            except Exception as e:
                job_logger.error(f"Error downloading post {post_id}: {e}")
                if temp_path.exists():
                    temp_path.unlink()

    cleanup_leftovers(download_dir)
    cleanup_old_episodes(download_dir, archive_file, channel.limit)

    # Save check status
    try:
        last_check_file.write_text(str(current_time))
    except Exception as e:
        job_logger.error(f"Error writing last check file for {channel.id}: {e}")

    job_logger.info(f"Finished Pawchive sync for {channel.id}.")
