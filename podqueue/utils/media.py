import datetime
import email.utils
import re
import subprocess
import logging

logger = logging.getLogger("podqueue")

def rfc2822_format(dt: datetime.datetime) -> str:
    """Format datetime to RFC 2822 standard string (e.g. Wed, 02 Oct 2002 13:00:00 +0000)."""
    if not dt:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return email.utils.format_datetime(dt)

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
    """Sanitize episode title for podcast compatibility by removing unprintable characters and normalizing whitespace."""
    if not title:
        return ""
    # Strip non-printable control characters while preserving full Unicode and standard punctuation (:, ?, !, -, etc.)
    title = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', title)
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

def parse_chapters_from_description(description: str) -> list:
    """Parse chapter timestamps from video description, supporting bracketed and standard timestamps."""
    if not description:
        return []
    
    # Pattern to match timestamps like: 00:00, 0:00, 00:00:00, 0:00:00, [01:23], (01:23)
    timestamp_pattern = r'^[\[\(]?(\d{1,2}):(\d{2})(?::(\d{2}))?[\]\)]?\s+(.+)$'
    chapters = []
    
    for line in description.split('\n'):
        line = line.strip()
        match = re.match(timestamp_pattern, line)
        if match:
            hours, minutes, seconds, title = match.groups()
            
            # Convert to total seconds
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

def extract_chapters(episode_info: dict) -> list:
    """Extract chapters from info.json native chapters list, falling back to description parsing."""
    if not episode_info:
        return []
    
    # 1. Native yt-dlp chapters from metadata
    native_chapters = episode_info.get("chapters")
    if isinstance(native_chapters, list) and len(native_chapters) > 0:
        parsed = []
        for ch in native_chapters:
            if isinstance(ch, dict) and "start_time" in ch:
                start_sec = float(ch.get("start_time", 0))
                title = ch.get("title", "").strip()
                time_str = f"{int(start_sec // 3600):02d}:{int((start_sec % 3600) // 60):02d}:{int(start_sec % 60):02d}"
                parsed.append({
                    "time": time_str,
                    "title": title or "Chapter"
                })
        if parsed:
            return parsed
            
    # 2. Fallback to description parsing
    description = episode_info.get("description", "")
    return parse_chapters_from_description(description)
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

def get_audio_duration(file_path: Path) -> int:
    """Use ffprobe to query audio file duration in seconds"""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            duration_str = result.stdout.strip()
            if duration_str:
                return int(float(duration_str))
    except Exception as e:
        logger.error(f"Error extracting duration using ffprobe for {file_path.name}: {e}")
    return 0


def get_audio_duration_seconds(file_path: Path) -> float:
    """Like :func:`get_audio_duration` but keeps sub-second precision."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            value = result.stdout.strip()
            if value:
                return float(value)
    except Exception as e:
        logger.error(f"Error extracting precise duration for {file_path.name}: {e}")
    return 0.0


def merge_ranges(ranges, duration: float = None) -> list:
    """Normalise ``[(start, end), ...]`` second ranges: clamp, sort, merge overlaps.

    Returns a list of disjoint ``(start, end)`` tuples. Ranges with no duration
    (or out of bounds) are dropped. This is used to turn a set of ad gaps into a
    clean "remove these" set before cutting.
    """
    cleaned = []
    for item in ranges or []:
        try:
            start, end = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if duration:
            start = max(0.0, min(start, duration))
            end = max(0.0, min(end, duration))
        if end <= start:
            continue
        cleaned.append((start, end))

    cleaned.sort(key=lambda r: r[0])
    merged = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def build_aselect_expression(ranges) -> str:
    """Build the audio ``aselect`` expression that DROPS the given ranges."""
    terms = [f"between(t,{start:.3f},{end:.3f})" for start, end in ranges]
    if not terms:
        return ""
    return "not(" + "+".join(terms) + ")"


def cut_audio_segments(src: Path, dst: Path, remove_ranges, bitrate: str = "128k", threads: int = 1) -> bool:
    """Re-encode ``src`` to ``dst`` with ``remove_ranges`` seconds spliced out.

    ``remove_ranges`` is an iterable of ``(start, end)`` seconds to delete. The
    result is a lossy mp3 re-encode (the source is mp3 too). Returns True when a
    file was written, False when there was nothing to remove.
    """
    duration = get_audio_duration_seconds(src)
    ranges = merge_ranges(remove_ranges, duration=duration)
    if not ranges:
        return False

    # If the removal covers essentially the whole file there is nothing to keep.
    if duration and sum(end - start for start, end in ranges) >= duration - 0.5:
        logger.warning(f"Ad ranges cover the whole of {src.name}; skipping cut")
        return False

    expression = build_aselect_expression(ranges)
    audio_filter = f"aselect='{expression}',asetpts=N/SR/TB"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i", str(src),
        "-af", audio_filter,
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-threads", str(threads),
        str(dst),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error(f"ffmpeg cut failed for {src.name}: {result.stderr.strip()[-400:]}")
        return False
    return True

