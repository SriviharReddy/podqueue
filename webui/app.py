import streamlit as st
import json
import os
import subprocess
import requests
from pathlib import Path

# Configuration
BASE_DIR = Path(__file__).parent.parent.absolute()
SCRIPTS_DIR = BASE_DIR / "scripts"
DOWNLOADS_DIR = BASE_DIR / "downloads"
FEEDS_DIR = BASE_DIR / "feeds"
ARTWORK_DIR = BASE_DIR / "artwork"
CHANNELS_FILE = SCRIPTS_DIR / "channels.json"

def load_channels():
    """Load channels from the channels.json file"""
    if CHANNELS_FILE.exists():
        with open(CHANNELS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_channels(channels):
    """Save channels to the channels.json file"""
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f, indent=2)

def add_channel(channel_id, url, limit):
    """Add a new channel to the channels.json file"""
    channels = load_channels()
    
    # Check if channel already exists
    for channel in channels:
        if channel['id'] == channel_id:
            st.warning(f"Channel with ID '{channel_id}' already exists!")
            return False
    
    # Add new channel
    new_channel = {
        "id": channel_id,
        "url": url,
        "limit": int(limit)
    }
    channels.append(new_channel)
    save_channels(channels)
    return True

def remove_channel(channel_id):
    """Remove a channel from the channels.json file"""
    channels = load_channels()
    channels = [channel for channel in channels if channel['id'] != channel_id]
    save_channels(channels)

def run_downloader():
    """Run the downloader script"""
    try:
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "downloader.sh")],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Downloader script timed out"
    except Exception as e:
        return False, "", str(e)

def run_rss_generator():
    """Run the RSS generator script"""
    try:
        result = subprocess.run(
            ["python", str(SCRIPTS_DIR / "rss_generator.py")],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "RSS generator script timed out"
    except Exception as e:
        return False, "", str(e)

def get_channel_info(channel_id):
    """Get information about a channel's downloads"""
    channel_dir = DOWNLOADS_DIR / channel_id
    if not channel_dir.exists():
        return 0, 0, []
    
    # Count audio files
    audio_files = list(channel_dir.glob("*.m4a"))
    audio_count = len(audio_files)
    
    # Count info files
    info_files = list(channel_dir.glob("*.info.json"))
    info_count = len(info_files)
    
    # Get recent downloads
    recent_downloads = []
    for audio_file in sorted(audio_files, key=os.path.getmtime, reverse=True)[:5]:
        info_file = audio_file.with_suffix('.info.json')
        if info_file.exists():
            try:
                with open(info_file, 'r') as f:
                    info = json.load(f)
                recent_downloads.append({
                    'title': info.get('title', audio_file.stem),
                    'upload_date': info.get('upload_date', 'Unknown'),
                    'duration': info.get('duration', 0)
                })
            except:
                recent_downloads.append({
                    'title': audio_file.stem,
                    'upload_date': 'Unknown',
                    'duration': 0
                })
    
    return audio_count, info_count, recent_downloads

def format_duration(seconds):
    """Format duration in seconds to HH:MM:SS"""
    if seconds <= 0:
        return "Unknown"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

# Streamlit App
st.set_page_config(page_title="PodQueue Manager", page_icon="🎧", layout="wide")
st.title("🎧 PodQueue Manager")

# Create tabs
tab1, tab2, tab3 = st.tabs(["Channels", "Downloads", "Settings"])

# Channels Tab
with tab1:
    st.header("Manage Podcast Channels")
    
    # Add new channel form
    with st.expander("Add New Channel", expanded=False):
        with st.form("add_channel_form"):
            channel_id = st.text_input("Channel ID")
            url = st.text_input("YouTube Channel/Playlist URL")
            limit = st.number_input("Episode Limit", min_value=1, value=10)
            submitted = st.form_submit_button("Add Channel")
            
            if submitted:
                if channel_id and url:
                    if add_channel(channel_id, url, limit):
                        st.success(f"Channel '{channel_id}' added successfully!")
                    else:
                        st.error("Failed to add channel. Check if it already exists.")
                else:
                    st.error("Please fill in all fields.")
    
    # Display existing channels
    st.subheader("Existing Channels")
    channels = load_channels()
    
    if not channels:
        st.info("No channels configured yet. Add a channel using the form above.")
    else:
        for channel in channels:
            col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
            with col1:
                st.write(f"**{channel['id']}**")
            with col2:
                st.write(channel['url'])
            with col3:
                st.write(f"Limit: {channel['limit']}")
            with col4:
                if st.button("Remove", key=f"remove_{channel['id']}"):
                    remove_channel(channel['id'])
                    st.experimental_rerun()

# Downloads Tab
with tab2:
    st.header("Manage Downloads")
    
    # Action buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Run Downloader", use_container_width=True):
            with st.spinner("Running downloader... This may take a while."):
                success, stdout, stderr = run_downloader()
                if success:
                    st.success("Downloader completed successfully!")
                else:
                    st.error("Downloader failed!")
                    st.text_area("Error output:", value=stderr, height=200)
    
    with col2:
        if st.button("📡 Run RSS Generator", use_container_width=True):
            with st.spinner("Generating RSS feeds... This may take a while."):
                success, stdout, stderr = run_rss_generator()
                if success:
                    st.success("RSS feeds generated successfully!")
                else:
                    st.error("RSS generation failed!")
                    st.text_area("Error output:", value=stderr, height=200)
    
    # Channel status
    st.subheader("Channel Status")
    channels = load_channels()
    
    if not channels:
        st.info("No channels configured. Add some channels first.")
    else:
        for channel in channels:
            with st.expander(f"📁 {channel['id']}", expanded=False):
                audio_count, info_count, recent_downloads = get_channel_info(channel['id'])
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Audio Files", audio_count)
                with col2:
                    st.metric("Info Files", info_count)
                
                if recent_downloads:
                    st.write("**Recent Downloads:**")
                    for download in recent_downloads:
                        duration = format_duration(download['duration'])
                        st.write(f"- {download['title']} ({duration}) - {download['upload_date']}")

# Settings Tab
with tab3:
    st.header("Application Settings")
    
    # Base directory information
    st.subheader("Directory Information")
    st.info(f"Base Directory: {BASE_DIR}")
    st.info(f"Scripts Directory: {SCRIPTS_DIR}")
    st.info(f"Downloads Directory: {DOWNLOADS_DIR}")
    st.info(f"Feeds Directory: {FEEDS_DIR}")
    st.info(f"Artwork Directory: {ARTWORK_DIR}")
    
    # Channels file
    st.subheader("Channels Configuration")
    if CHANNELS_FILE.exists():
        with open(CHANNELS_FILE, 'r') as f:
            channels_content = f.read()
        st.code(channels_content, language="json")
    else:
        st.warning("channels.json file not found. Add a channel to create it.")
    
    # Instructions
    st.subheader("Instructions")
    st.markdown("""
    1. **Add Channels**: Use the "Add New Channel" form to add YouTube channels or playlists
    2. **Run Downloader**: Click "Run Downloader" to download new episodes
    3. **Generate Feeds**: Click "Run RSS Generator" to create podcast feeds
    4. **View Status**: Check the "Downloads" tab to see the status of your channels
    """)
    
    # Requirements
    st.subheader("Requirements")
    st.markdown("""
    This application requires the following tools to be installed:
    - `yt-dlp` - For downloading YouTube videos
    - `jq` - For processing JSON in shell scripts
    - Python packages listed in `requirements.txt`
    """)