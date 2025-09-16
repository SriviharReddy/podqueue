import os
import datetime
import json
import glob
import xml.etree.ElementTree as ET
import subprocess

# --- CONFIGURATION ---
BASE_DIR = "/home/ubuntu/my_podcast_service"
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads_kemono")
FEEDS_DIR = os.path.join(BASE_DIR, "feeds")
ARTWORK_DIR = os.path.join(BASE_DIR, "artwork")
BASE_URL = "http://152.67.182.84"

# --- HELPER FUNCTIONS ---
def rfc2822_format(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def parse_published_date(published_str: str) -> datetime.datetime:
    """Parse Kemono published date (ISO 8601) to datetime object"""
    if not published_str:
        return None
    
    try:
        # Handle both formats: "2025-08-24T02:28:49" and "2025-08-24 02:28:49"
        if 'T' in published_str:
            return datetime.datetime.fromisoformat(published_str.replace('Z', '+00:00'))
        else:
            return datetime.datetime.strptime(published_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format for iTunes duration"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe"""
    try:
        # Use ffprobe to get the duration
        result = subprocess.run(
            [
                "ffprobe", 
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode == 0:
            duration_str = result.stdout.strip()
            if duration_str:
                return float(duration_str)
    except Exception as e:
        print(f"Error getting duration for {file_path}: {e}")
    
    return 0.0

# --- MAIN SCRIPT LOGIC ---
def generate_rss_kemono(feed_name, podcast_dir):
    print(f"--- Processing Kemono feed for: {feed_name} ---")
    channel_title = feed_name
    channel_desc = f"A podcast stream of audio from the Kemono Channel {feed_name}"
    local_image_url = None
    user_id = None
    
    # Find all JSON metadata files
    json_files = glob.glob(os.path.join(podcast_dir, "*.json"))
    
    if json_files:
        # Get user_id and channel info from the first JSON file
        try:
            with open(json_files[0], "r", encoding='utf-8') as f:
                data = json.load(f)
                user_id = data.get("user")
                channel_title = data.get("username", feed_name)
                
                # Check for artwork in the artwork directory
                if user_id:
                    artwork_filename = f"{user_id}.jpg"
                    local_artwork_path = os.path.join(ARTWORK_DIR, artwork_filename)
                    if os.path.exists(local_artwork_path):
                        local_image_url = f"{BASE_URL}/artwork/{artwork_filename}"
                        print(f"Found artwork: {local_image_url}")
                    else:
                        print(f"No artwork found for user_id: {user_id}")
                
        except Exception as e:
            print(f"Error reading channel info JSON for {feed_name}: {e}")
    else:
        print(f"No JSON files found for {feed_name}")
    
    # Create RSS with namespaces
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    
    rss = ET.Element("rss", version="2.0", attrib={
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"
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
    
    # Find all audio files for the episodes
    audio_extensions = ['.mp3', '.m4a', '.ogg', '.opus', '.wav']
    audio_files = []
    
    for ext in audio_extensions:
        audio_files.extend(glob.glob(os.path.join(podcast_dir, f"*{ext}")))
    
    # Sort by published date if available, otherwise by filename
    audio_files.sort(key=lambda f: os.path.basename(f), reverse=True)
    
    print(f"Found {len(audio_files)} audio files")
    
    for filename in audio_files:
        file_path = os.path.join(podcast_dir, filename)
        file_url = f"{BASE_URL}/downloads_kemono/{feed_name}/{os.path.basename(filename)}"
        file_size = os.path.getsize(file_path)
        
        # Get the full audio filename with extension
        audio_filename = os.path.basename(filename)
        # Look for JSON file with the same name as audio file plus ".json"
        json_file_path = os.path.join(podcast_dir, audio_filename + ".json")
        
        # Create RSS item
        item = ET.SubElement(channel, "item")
        
        # Try to get episode info from the JSON file
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, "r", encoding='utf-8') as f:
                    episode_info = json.load(f)
                
                # Get the episode title
                episode_title = episode_info.get("title", audio_filename)
                ET.SubElement(item, "title").text = episode_title
                
                # Get the publication date
                published_str = episode_info.get("published")
                pub_date = None
                
                if published_str:
                    pub_date = parse_published_date(published_str)
                
                # If we couldn't parse the published date, fall back to file modification time
                if not pub_date:
                    pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
                    print(f"Using file modification time for: {episode_title}")
                else:
                    print(f"Using published date for: {episode_title}")
                
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                
                # Determine file type based on extension
                file_ext = os.path.splitext(filename)[1].lower()
                mime_type = "audio/mpeg"  # default for mp3
                if file_ext == '.m4a':
                    mime_type = "audio/mp4"
                elif file_ext == '.ogg':
                    mime_type = "audio/ogg"
                elif file_ext == '.opus':
                    mime_type = "audio/opus"
                elif file_ext == '.wav':
                    mime_type = "audio/wav"
                
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type=mime_type)
                
                # Add episode description
                description = episode_info.get("substring", "")
                if description:
                    ET.SubElement(item, "description").text = description
                
                # Get and add episode duration
                duration_seconds = get_audio_duration(file_path)
                if duration_seconds > 0:
                    duration_str = format_duration(duration_seconds)
                    ET.SubElement(item, "itunes:duration").text = duration_str
                    print(f"Added duration ({duration_str}) for: {episode_title}")
                else:
                    print(f"Could not determine duration for: {episode_title}")
                
            except Exception as e:
                print(f"Error reading episode info for {audio_filename}: {e}")
                # Fall back to file modification time if there's an error
                pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
                ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
                ET.SubElement(item, "guid", isPermaLink="false").text = file_url
                ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mpeg")
        else:
            print(f"No JSON file found for: {audio_filename}")
            # Use file modification time if no JSON file exists
            pub_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path), datetime.UTC)
            ET.SubElement(item, "pubDate").text = rfc2822_format(pub_date)
            ET.SubElement(item, "guid", isPermaLink="false").text = file_url
            ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type="audio/mpeg")
            
            # Still try to get duration even without JSON
            duration_seconds = get_audio_duration(file_path)
            if duration_seconds > 0:
                duration_str = format_duration(duration_seconds)
                ET.SubElement(item, "itunes:duration").text = duration_str
                print(f"Added duration ({duration_str}) for: {audio_filename}")
    
    tree = ET.ElementTree(rss)
    output_path = os.path.join(FEEDS_DIR, f"{feed_name}.xml")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Generated RSS feed: {output_path}")

def main():
    for podcast_name in os.listdir(DOWNLOADS_DIR):
        podcast_dir = os.path.join(DOWNLOADS_DIR, podcast_name)
        if os.path.isdir(podcast_dir):
            generate_rss_kemono(podcast_name, podcast_dir)

if __name__ == "__main__":
    main()
