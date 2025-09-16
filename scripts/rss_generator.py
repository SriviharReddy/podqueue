import os
import datetime
import json
import glob
import requests
import xml.etree.ElementTree as ET
import re

# --- CONFIGURATION ---
BASE_DIR = "/home/ubuntu/my_podcast_service"
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
FEEDS_DIR = os.path.join(BASE_DIR, "feeds")
ARTWORK_DIR = os.path.join(BASE_DIR, "artwork")
BASE_URL = "http://152.67.182.84"

# Ensure artwork directory exists
os.makedirs(ARTWORK_DIR, exist_ok=True)

# --- HELPER FUNCTIONS ---
def rfc2822_format(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format for iTunes duration"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def parse_upload_date(upload_date_str: str) -> datetime.datetime:
    """Parse YouTube upload date (YYYYMMDD) to datetime object"""
    if not upload_date_str:
        return None
    
    try:
        # YouTube upload_date is in YYYYMMDD format
        year = int(upload_date_str[:4])
        month = int(upload_date_str[4:6])
        day = int(upload_date_str[6:8])
        return datetime.datetime(year, month, day, tzinfo=datetime.UTC)
    except (ValueError, IndexError):
        return None

def sanitize_title(title: str) -> str:
    """Sanitize episode title for podcast compatibility"""
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

def cache_artwork(channel_id, image_url):
    if not image_url:
        print(f"No image URL provided for {channel_id}.")
        return None
    
    artwork_filename = f"{channel_id}.jpg"
    local_artwork_path = os.path.join(ARTWORK_DIR, artwork_filename)
    public_artwork_url = f"{BASE_URL}/artwork/{artwork_filename}"
    
    if not os.path.exists(local_artwork_path):
        print(f"Downloading artwork for {channel_id}...")
        try:
            response = requests.get(image_url, stream=True, timeout=10)
            response.raise_for_status()
            with open(local_artwork_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Successfully cached artwork for {channel_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading artwork for {channel_id}: {e}")
            return None
    
    return public_artwork_url

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

# --- MAIN SCRIPT LOGIC ---
def generate_rss(feed_name, podcast_dir):
    print(f"--- Processing feed for: {feed_name} ---")
    channel_title = feed_name
    # Use the actual channel name in the description instead of feed_name
    channel_desc = f"A podcast stream of audio from the Youtube Channel"
    local_image_url = None
    
    # Look for channel info JSON files - find the one with the longest filename
    all_info_files = glob.glob(os.path.join(podcast_dir, "*.info.json"))
    channel_info_files = []
    
    if all_info_files:
        # Sort files by name length (descending) to get the longest filename first
        all_info_files.sort(key=lambda x: len(os.path.basename(x)), reverse=True)
        channel_info_files = [all_info_files[0]]
        print(f"Found channel info file with longest name: {channel_info_files[0]}")
    
    if channel_info_files:
        with open(channel_info_files[0], "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
                # Get the actual channel name
                channel_title = data.get("channel", feed_name)
                # Update the description with the actual channel name
                channel_desc = f"A podcast stream of audio from the Youtube Channel {channel_title}"
                
                # Get the best thumbnail - highest resolution square image with fallback
                image_to_download = get_best_thumbnail(data.get("thumbnails", []))
                
                if image_to_download:
                    print(f"Using thumbnail URL: {image_to_download}")
                    local_image_url = cache_artwork(feed_name, image_to_download)
                else:
                    print(f"No thumbnail found for {feed_name}")
                
            except Exception as e:
                print(f"Error reading channel info JSON for {feed_name}: {e}")
    else:
        print(f"No channel info file found for {feed_name}")
    
    # Create RSS with namespaces
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("psc", "http://podlove.org/simple-chapters")
    
    rss = ET.Element("rss", version="2.0", attrib={
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:psc": "http://podlove.org/simple-chapters"
    })
    
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = f"{BASE_URL}/feeds/{feed_name}.xml"
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "language").text = "en-US"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_format(datetime.datetime.now(datetime.UTC))
    ET.SubElement(channel, "itunes:author").text = channel_title
    
    if local_image_url:
        ET.SubElement(channel, "itunes:image", href=local_image_url)
        print(f"Added iTunes image: {local_image_url}")
    else:
        print("No iTunes image added")
    
    # Find all individual audio files for the episodes
    audio_files = sorted(
        [f for f in os.listdir(podcast_dir) if f.endswith('.m4a')],
        key=lambda f: os.path.getmtime(os.path.join(podcast_dir, f)),
        reverse=True
    )
    
    print(f"Found {len(audio_files)} audio files")
    
    for filename in audio_files:
        file_path = os.path.join(podcast_dir, filename)
        file_url = f"{BASE_URL}/downloads/{feed_name}/{filename}"
        file_size = os.path.getsize(file_path)
        
        # Get base filename without extension (this is the video ID)
        video_id = os.path.splitext(filename)[0]
        info_file_path = os.path.join(podcast_dir, f"{video_id}.info.json")
        
        # Create RSS item
        item = ET.SubElement(channel, "item")
        
        # Try to get episode info from the info.json file
        if os.path.exists(info_file_path):
            try:
                with open(info_file_path, "r", encoding='utf-8') as f:
                    episode_info = json.load(f)
                
                # Get the episode title from the info.json file
                episode_title = episode_info.get("title", video_id)
                sanitized_title = sanitize_title(episode_title)
                ET.SubElement(item, "title").text = sanitized_title
                
                # Get the upload date from YouTube
                upload_date_str = episode_info.get("upload_date")
                pub_date = None
                
                if upload_date_str:
                    pub_date = parse_upload_date(upload_date_str)
                
                # If we couldn't parse the upload date, fall back to file modification time
                if not pub_date:
                    pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
                    print(f"Using file modification time for: {sanitized_title}")
                else:
                    print(f"Using YouTube upload date for: {sanitized_title}")
                
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
                
                # Add episode description
                description = episode_info.get("description", "")
                if description:
                    ET.SubElement(item, "description").text = description
                    print(f"Added description for: {sanitized_title}")
                
                # Add episode duration
                duration = episode_info.get("duration", 0)
                if duration:
                    duration_str = format_duration(duration)
                    ET.SubElement(item, "itunes:duration").text = duration_str
                    print(f"Added duration ({duration_str}) for: {sanitized_title}")
                
                # Add episode thumbnail (using the video's thumbnail instead of channel art)
                thumbnails = episode_info.get("thumbnails", [])
                if thumbnails:
                    thumbnail_url = get_best_episode_thumbnail(thumbnails)
                    if thumbnail_url:
                        ET.SubElement(item, "itunes:image", href=thumbnail_url)
                        print(f"Added episode thumbnail for: {sanitized_title}")
                
                # Add chapters if found in description
                chapters = parse_chapters_from_description(description)
                if chapters:
                    chapters_element = ET.SubElement(item, "psc:chapters", attrib={"version": "1.2"})
                    for chapter in chapters:
                        ET.SubElement(chapters_element, "psc:chapter", 
                                    attrib={"start": chapter['time'], "title": chapter['title']})
                    print(f"Added {len(chapters)} chapters for: {sanitized_title}")
                
            except Exception as e:
                print(f"Error reading episode info for {video_id}: {e}")
                # Fall back to file modification time if there's an error
                pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
        else:
            print(f"No info file found for: {video_id}")
            # Use file modification time if no info file exists
            pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
            ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
            ET.SubElement(item, "guid", isPermaLink="false").text = file_url
            ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mp4")
    
    tree = ET.ElementTree(rss)
    output_path = os.path.join(FEEDS_DIR, f"{feed_name}.xml")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Generated RSS feed: {output_path}")

def main():
    for podcast_name in os.listdir(DOWNLOADS_DIR):
        podcast_dir = os.path.join(DOWNLOADS_DIR, podcast_name)
        if os.path.isdir(podcast_dir):
            generate_rss(podcast_name, podcast_dir)

if __name__ == "__main__":
    main()
