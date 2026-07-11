import os
import datetime
import json
import requests
import xml.etree.ElementTree as ET
import logging
import gc
from pathlib import Path
from podqueue.config import settings
from podqueue.utils.media import (
    rfc2822_format,
    format_duration,
    parse_upload_date,
    sanitize_title,
    get_best_thumbnail,
    get_best_episode_thumbnail,
    parse_chapters_from_description,
    get_episode_sort_key
)

logger = logging.getLogger("podqueue")
job_logger = logging.getLogger("podqueue_job")

def cache_artwork(channel_id: str, image_url: str) -> str:
    if not image_url:
        job_logger.warning(f"No image URL provided for {channel_id}.")
        return None
    
    artwork_filename = f"{channel_id}.jpg"
    local_artwork_path = settings.ARTWORK_DIR / artwork_filename
    public_artwork_url = f"{settings.BASE_URL}/artwork/{artwork_filename}"
    
    if not local_artwork_path.exists():
        job_logger.info(f"Downloading artwork for {channel_id}...")
        try:
            response = requests.get(image_url, stream=True, timeout=10)
            response.raise_for_status()
            with open(local_artwork_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            job_logger.info(f"Successfully cached artwork for {channel_id}")
        except requests.exceptions.RequestException as e:
            job_logger.error(f"Error downloading artwork for {channel_id}: {e}")
            return None
            
    return public_artwork_url

def generate_rss(feed_name: str, podcast_dir: Path):
    job_logger.info(f"--- Processing feed for: {feed_name} ---")
    channel_title = feed_name
    channel_desc = f"A podcast stream of audio from the Youtube Channel"
    local_image_url = None
    
    # Look for channel info JSON files
    all_info_files = list(podcast_dir.glob("*.info.json"))
    if all_info_files:
        # Sort files by name length (descending) to get the longest filename first
        all_info_files.sort(key=lambda x: len(x.name), reverse=True)
        channel_info_file = all_info_files[0]
        job_logger.info(f"Found channel info file: {channel_info_file.name}")
        
        try:
            with open(channel_info_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                channel_title = data.get("channel", feed_name)
                channel_desc = f"A podcast stream of audio from the Youtube Channel {channel_title}"
                
                image_to_download = get_best_thumbnail(data.get("thumbnails", []))
                if image_to_download:
                    local_image_url = cache_artwork(feed_name, image_to_download)
                else:
                    job_logger.info(f"No thumbnail found for {feed_name}")
        except Exception as e:
            job_logger.error(f"Error reading channel info JSON for {feed_name}: {e}")
    else:
        job_logger.info(f"No channel info file found for {feed_name}")
        
    # Create RSS XML
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("psc", "http://podlove.org/simple-chapters")
    
    rss = ET.Element("rss", version="2.0", attrib={
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:psc": "http://podlove.org/simple-chapters"
    })
    
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = f"{settings.BASE_URL}/feeds/{feed_name}.xml"
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "language").text = "en-US"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_format(datetime.datetime.now(datetime.timezone.utc))
    ET.SubElement(channel, "itunes:author").text = channel_title
    
    if local_image_url:
        ET.SubElement(channel, "itunes:image", href=local_image_url)
        
    # Find all audio files
    audio_files = sorted(
        [f for f in os.listdir(podcast_dir) if f.endswith('.m4a') and not '.temp.' in f],
        key=lambda f: get_episode_sort_key(podcast_dir / f),
        reverse=True
    )
    job_logger.info(f"Found {len(audio_files)} audio files")
    
    for filename in audio_files:
        file_path = podcast_dir / filename
        file_url = f"{settings.BASE_URL}/downloads/{feed_name}/{filename}"
        file_size = os.path.getsize(file_path)
        
        video_id = os.path.splitext(filename)[0]
        info_file_path = podcast_dir / f"{video_id}.info.json"
        
        item = ET.SubElement(channel, "item")
        
        if info_file_path.exists():
            try:
                with open(info_file_path, "r", encoding='utf-8') as f:
                    episode_info = json.load(f)
                
                episode_title = episode_info.get("title", video_id)
                sanitized = sanitize_title(episode_title)
                ET.SubElement(item, "title").text = sanitized
                
                upload_date_str = episode_info.get("upload_date")
                pub_date = parse_upload_date(upload_date_str) if upload_date_str else None
                
                if not pub_date:
                    pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.timezone.utc)
                
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
                
                description = episode_info.get("description", "")
                if description:
                    ET.SubElement(item, "description").text = description
                    
                duration = episode_info.get("duration", 0)
                if duration:
                    ET.SubElement(item, "itunes:duration").text = format_duration(duration)
                    
                thumbnails = episode_info.get("thumbnails", [])
                if thumbnails:
                    ep_thumb = get_best_episode_thumbnail(thumbnails)
                    if ep_thumb:
                        ET.SubElement(item, "itunes:image", href=ep_thumb)
                        
                chapters = parse_chapters_from_description(description)
                if chapters:
                    chapters_element = ET.SubElement(item, "psc:chapters", attrib={"version": "1.2"})
                    for ch in chapters:
                        ET.SubElement(chapters_element, "psc:chapter", attrib={"start": ch['time'], "title": ch['title']})
                        
            except Exception as e:
                job_logger.error(f"Error reading episode info for {video_id}: {e}")
                pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.timezone.utc)
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
        else:
            pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.timezone.utc)
            ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
            ET.SubElement(item, "guid", isPermaLink="false").text = file_url
            ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
            
    tree = ET.ElementTree(rss)
    output_path = settings.FEEDS_DIR / f"{feed_name}.xml"
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    job_logger.info(f"Generated RSS feed: {output_path}")

def run_rss_job():
    job_logger.info("Starting RSS feed generation...")
    if not settings.DOWNLOADS_DIR.exists():
        job_logger.info("Downloads directory does not exist. RSS generation complete.")
        return
        
    for name in os.listdir(settings.DOWNLOADS_DIR):
        podcast_dir = settings.DOWNLOADS_DIR / name
        if podcast_dir.is_dir():
            try:
                generate_rss(name, podcast_dir)
            except Exception as e:
                job_logger.error(f"Error generating RSS for {name}: {e}")
                
    job_logger.info("RSS feed generation complete.")
    gc.collect()
