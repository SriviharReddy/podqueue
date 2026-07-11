import datetime
import re

def rfc2822_format(dt: datetime.datetime) -> str:
    """Format datetime to RFC 2822 standard string (e.g. Wed, 02 Oct 2002 13:00:00 GMT)"""
    # Ensure dt is aware or has a default format
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format for iTunes duration"""
    if not seconds:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def parse_upload_date(upload_date_str: str) -> datetime.datetime:
    """Parse YouTube upload date (YYYYMMDD) to datetime object"""
    if not upload_date_str:
        return None
    
    try:
        # YouTube upload_date is in YYYYMMDD format
        year = int(upload_date_str[:4])
        month = int(upload_date_str[4:6])
        day = int(upload_date_str[6:8])
        return datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    except (ValueError, IndexError):
        return None

def sanitize_title(title: str) -> str:
    """Sanitize episode title for podcast compatibility"""
    if not title:
        return ""
    # Replace colons with dashes
    title = title.replace(":", " -")
    # Replace other problematic characters if needed
    title = title.replace("|", "-")
    title = title.replace("/", "-")
    # Replace backslashes using re.sub
    title = re.sub(r'\\', '-', title) # Use raw string for regex pattern
    title = title.replace("?", "")
    title = title.replace("*", "")
    # Remove extra spaces that might result from replacements
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def get_best_thumbnail(thumbnails):
    """Get the highest resolution square thumbnail from thumbnails with fallback to any image"""
    if not thumbnails:
        return None
    
    # First, try to find square thumbnails
    square_thumbnails = []
    for thumb in thumbnails:
        width = thumb.get("width")
        height = thumb.get("height")
        
        # Skip if width or height is None or not positive
        if width is None or height is None or width <= 0 or height <= 0:
            continue
            
        # Check if it's square (within a small tolerance)
        if abs(width - height) <= 10:  # Allow small differences
            square_thumbnails.append(thumb)
    
    # If we found square thumbnails, find the highest resolution one
    if square_thumbnails:
        best_thumb = None
        max_resolution = 0
        for thumb in square_thumbnails:
            width = thumb.get("width", 0)
            height = thumb.get("height", 0)
            resolution = width * height
            if resolution > max_resolution:
                max_resolution = resolution
                best_thumb = thumb
        
        return best_thumb["url"] if best_thumb and best_thumb.get("url") else None
    
    # If no square thumbnails found, fall back to any thumbnail (highest resolution)
    best_thumb = None
    max_resolution = 0
    for thumb in thumbnails:
        width = thumb.get("width", 0)
        height = thumb.get("height", 0)
        resolution = width * height
        if resolution > max_resolution:
            max_resolution = resolution
            best_thumb = thumb
    
    return best_thumb["url"] if best_thumb and best_thumb.get("url") else None

def get_best_episode_thumbnail(thumbnails):
    """Get the highest resolution thumbnail from thumbnails (not necessarily square)"""
    if not thumbnails:
        return None
    
    # Find the highest resolution thumbnail
    best_thumb = None
    max_resolution = 0
    for thumb in thumbnails:
        width = thumb.get("width", 0)
        height = thumb.get("height", 0)
        resolution = width * height
        if resolution > max_resolution:
            max_resolution = resolution
            best_thumb = thumb
    
    # Return the URL of the best thumbnail, or None if none found
    return best_thumb["url"] if best_thumb and best_thumb.get("url") else None

def parse_chapters_from_description(description):
    """Parse chapter timestamps from video description"""
    if not description:
        return []
    
    # Pattern to match timestamps like: 00:00, 0:00, 00:00:00, 0:00:00
    timestamp_pattern = r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.+)$'
    chapters = []
    
    for line in description.split('\n'):
        line = line.strip()
        match = re.match(timestamp_pattern, line)
        if match:
            hours, minutes, seconds, title = match.groups()
            
            # Convert to total seconds
            total_seconds = 0
            
            if seconds:  # Three segments: hours:minutes:seconds
                total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            else:  # Two segments: minutes:seconds
                total_seconds = int(hours) * 60 + int(minutes)
            
            # Format as HH:MM:SS
            chapter_time = f"{int(total_seconds // 3600):02d}:{int((total_seconds % 3600) // 60):02d}:{int(total_seconds % 60):02d}"
            
            # Clean up the title - remove any leading dash or hyphen
            clean_title = title.strip()
            if clean_title.startswith('-') or clean_title.startswith('–') or clean_title.startswith('—'):
                clean_title = clean_title[1:].strip()
            
            chapters.append({
                'time': chapter_time,
                'title': clean_title
            })
    
    return chapters

import json
from pathlib import Path

def get_episode_sort_key(file_path: Path) -> tuple:
    """Get a sorting key for an audio file based on its YouTube upload date from .info.json,
    falling back to file modification time."""
    mtime = 0.0
    try:
        mtime = file_path.stat().st_mtime
    except Exception:
        pass

    info_file = file_path.with_suffix(".info.json")
    if info_file.exists():
        try:
            with open(info_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                upload_date = data.get("upload_date")
                if upload_date and len(upload_date) == 8 and upload_date.isdigit():
                    return (upload_date, mtime)
        except Exception:
            pass

    # Fallback: format mtime as YYYYMMDD
    try:
        mtime_dt = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc)
        mtime_str = mtime_dt.strftime("%Y%m%d")
        return (mtime_str, mtime)
    except Exception:
        return ("00000000", mtime)

