import streamlit as st
import json
import os
import subprocess
import sys
import platform
import shutil
import hashlib
from pathlib import Path

# Configuration - Fix the path to point to the correct location
BASE_DIR = Path(__file__).parent.parent.absolute()
SCRIPTS_DIR = BASE_DIR / "scripts"
DOWNLOADS_DIR = BASE_DIR / "downloads"
FEEDS_DIR = BASE_DIR / "feeds"
ARTWORK_DIR = BASE_DIR / "artwork"
CHANNELS_FILE = SCRIPTS_DIR / "channels.json"
AUTH_FILE = BASE_DIR / "webui" / "auth.json"

def load_channels():
    """Load channels from the channels.json file"""
    if CHANNELS_FILE.exists():
        with open(CHANNELS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_channels(channels):
    """Save channels to the channels.json file"""
    # Ensure the scripts directory exists
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f, indent=2)

def is_ytdlp_available():
    """Check if yt-dlp is available on the system"""
    try:
        # Try to find yt-dlp in PATH
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # If not found, check if it's installed via pip
        try:
            import yt_dlp
            return True
        except ImportError:
            return False

def get_channel_id_from_url(url):
    """Extract channel ID from a YouTube URL using yt-dlp"""
    try:
        # Use yt-dlp to get the channel ID
        result = subprocess.run(
            ["yt-dlp", "--print", "%(channel_id)s", "--playlist-end", "1", url],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            channel_id = result.stdout.strip()
            # Convert to proper channel URL format
            return f"https://www.youtube.com/channel/{channel_id}"
        else:
            st.error(f"yt-dlp failed to extract channel ID. Error: {result.stderr}")
            return None
    except FileNotFoundError:
        st.error("yt-dlp is not installed or not found in PATH. Please install yt-dlp and make sure it's accessible from the command line.")
        return None
    except Exception as e:
        st.error(f"Error running yt-dlp: {e}")
        return None

def convert_channel_url(url):
    """Convert @username URLs to channel ID URLs if needed"""
    # Check if it's an @username URL
    if "@" in url and "youtube.com" in url:
        # Check if yt-dlp is available
        if not is_ytdlp_available():
            st.error("yt-dlp is required to convert @username URLs but it's not installed or not found in PATH. Please install yt-dlp and make sure it's accessible from the command line, or use a direct channel URL.")
            return None
            
        with st.spinner(f"Converting {url} to channel ID URL..."):
            converted_url = get_channel_id_from_url(url)
            if converted_url:
                st.success(f"Converted to: {converted_url}")
                return converted_url
            else:
                st.error("Failed to convert URL. Please check the URL or use a direct channel URL.")
                return None
    return url

def add_channel(channel_id, url, limit):
    """Add a new channel to the channels.json file"""
    channels = load_channels()
    
    # Check if channel already exists
    for channel in channels:
        if channel['id'] == channel_id:
            st.warning(f"Channel with ID '{channel_id}' already exists!")
            return False
    
    # Convert URL if it's an @username URL
    converted_url = convert_channel_url(url)
    
    # If conversion failed, don't add the channel
    if converted_url is None:
        return False
    
    # Add new channel
    new_channel = {
        "id": channel_id,
        "url": converted_url,
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

def update_channel_limit(channel_id, new_limit):
    """Update the limit of an existing channel"""
    channels = load_channels()
    for channel in channels:
        if channel['id'] == channel_id:
            channel['limit'] = int(new_limit)
            save_channels(channels)
            return True
    return False

def hash_password(password):
    """Hash a password for storing"""
    return hashlib.sha256(password.encode()).hexdigest()

def save_auth_config(username, password):
    """Save authentication configuration"""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    auth_data = {
        "username": username,
        "password_hash": hash_password(password)
    }
    with open(AUTH_FILE, 'w') as f:
        json.dump(auth_data, f, indent=2)

def load_auth_config():
    """Load authentication configuration"""
    if AUTH_FILE.exists():
        with open(AUTH_FILE, 'r') as f:
            return json.load(f)
    return None

def check_password(username, password):
    """Check if the provided password is correct"""
    auth_config = load_auth_config()
    if auth_config:
        return (auth_config.get("username") == username and 
                auth_config.get("password_hash") == hash_password(password))
    return False

def is_authenticated():
    """Check if the user is authenticated"""
    return "authenticated" in st.session_state and st.session_state.authenticated

def authenticate_user():
    """Show authentication screen"""
    st.title("🔒 PodQueue Web UI - Authentication")
    
    # Check if auth is already configured
    auth_config = load_auth_config()
    
    if auth_config is None:
        # First-time setup
        st.subheader("First-time Setup - Set Admin Password")
        st.info("Please set up an admin username and password for the Web UI.")
        
        with st.form("setup_auth_form"):
            username = st.text_input("Username", value="admin")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            skip_auth = st.checkbox("Skip authentication (not recommended)")
            
            submitted = st.form_submit_button("Set Up Authentication")
            
            if submitted:
                if skip_auth:
                    # Create empty auth file to indicate setup is complete
                    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(AUTH_FILE, 'w') as f:
                        json.dump({"auth_disabled": True}, f)
                    st.session_state.authenticated = True
                    st.success("Authentication skipped. Redirecting...")
                    st.rerun()
                elif password and password == confirm_password:
                    save_auth_config(username, password)
                    st.session_state.authenticated = True
                    st.success("Password set successfully! Redirecting...")
                    st.rerun()
                elif password != confirm_password:
                    st.error("Passwords do not match!")
                else:
                    st.error("Please enter a password!")
    else:
        # Regular login
        if auth_config.get("auth_disabled", False):
            st.session_state.authenticated = True
            st.rerun()
        
        st.subheader("Login to PodQueue Web UI")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if check_password(username, password):
                    st.session_state.authenticated = True
                    st.success("Login successful! Redirecting...")
                    st.rerun()
                else:
                    st.error("Invalid username or password!")

def run_downloader():
    """Run the downloader script"""
    try:
        # Determine the appropriate command based on the OS
        if platform.system() == "Windows":
            # On Windows, we need to use bash to run the shell script
            cmd = ["bash", str(SCRIPTS_DIR / "downloader.sh")]
        else:
            # On Unix-like systems, we can run the script directly
            cmd = ["bash", str(SCRIPTS_DIR / "downloader.sh")]
            
        result = subprocess.run(
            cmd,
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
            [sys.executable, str(SCRIPTS_DIR / "rss_generator.py")],
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
if not is_authenticated():
    authenticate_user()
else:
    st.set_page_config(page_title="PodQueue Manager", page_icon="🎧", layout="wide")
    
    # Add logout button in sidebar
    with st.sidebar:
        st.title("🎧 PodQueue Manager")
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.rerun()
    
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
                            st.rerun()
                        else:
                            st.error("Failed to add channel.")
                    else:
                        st.error("Please fill in all fields.")
        
        # Display existing channels
        st.subheader("Existing Channels")
        channels = load_channels()
        
        if not channels:
            st.info("No channels configured yet. Add a channel using the form above.")
        else:
            for channel in channels:
                with st.expander(f"📁 {channel['id']}", expanded=False):
                    col1, col2, col3, col4, col5 = st.columns([3, 3, 1, 1, 1])
                    with col1:
                        st.write(f"**{channel['id']}**")
                    with col2:
                        st.write(channel['url'])
                    with col3:
                        # Edit limit functionality
                        new_limit = st.number_input(
                            "Limit", 
                            min_value=1, 
                            value=channel['limit'], 
                            key=f"limit_{channel['id']}"
                        )
                    with col4:
                        if st.button("Update", key=f"update_{channel['id']}"):
                            if update_channel_limit(channel['id'], new_limit):
                                st.success("Limit updated successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to update limit.")
                    with col5:
                        if st.button("Remove", key=f"remove_{channel['id']}"):
                            remove_channel(channel['id'])
                            st.rerun()

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
                        if stderr:
                            st.text_area("Error output:", value=stderr, height=200)
        
        with col2:
            if st.button("📡 Run RSS Generator", use_container_width=True):
                with st.spinner("Generating RSS feeds... This may take a while."):
                    success, stdout, stderr = run_rss_generator()
                    if success:
                        st.success("RSS feeds generated successfully!")
                    else:
                        st.error("RSS generation failed!")
                        if stderr:
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
        st.info(f"Channels File: {CHANNELS_FILE}")
        
        # Check if required tools are available
        st.subheader("System Requirements Check")
        if is_ytdlp_available():
            st.success("✅ yt-dlp is available")
        else:
            st.error("❌ yt-dlp is not installed or not found in PATH. Please install yt-dlp: https://github.com/yt-dlp/yt-dlp")
        
        # Channels file
        st.subheader("Channels Configuration")
        if CHANNELS_FILE.exists():
            with open(CHANNELS_FILE, 'r') as f:
                channels_content = f.read()
            st.code(channels_content, language="json")
        else:
            st.warning("channels.json file not found. Add a channel to create it.")
        
        # System information
        st.subheader("System Information")
        st.info(f"Operating System: {platform.system()} {platform.release()}")
        st.info(f"Python Version: {sys.version}")
        
        # Instructions
        st.subheader("Instructions")
        st.markdown("""
        1. **Add Channels**: Use the "Add New Channel" form to add YouTube channels or playlists
        2. **Edit Limits**: Change the episode limit for existing channels and click "Update"
        3. **Remove Channels**: Click "Remove" to delete a channel
        4. **Run Downloader**: Click "Run Downloader" to download new episodes
        5. **Generate Feeds**: Click "Run RSS Generator" to create podcast feeds
        6. **View Status**: Check the "Downloads" tab to see the status of your channels
        
        **Note**: You can use @username URLs (e.g., https://www.youtube.com/@Level1Linux) and they will be automatically converted to channel ID URLs.
        """)
        
        # Requirements
        st.subheader("Requirements")
        st.markdown("""
        This application requires the following tools to be installed:
        - `yt-dlp` - For downloading YouTube videos ([installation instructions](https://github.com/yt-dlp/yt-dlp#installation))
        - `jq` - For processing JSON in shell scripts
        - Python packages listed in `requirements.txt`
        
        On Windows, you'll also need:
        - Git Bash or WSL to run the shell scripts
        """)