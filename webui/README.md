# PodQueue Web UI

A Streamlit-based web interface for managing your PodQueue YouTube to podcast converter.

## Features

- Add and remove YouTube channels/playlists
- Automatically convert @username URLs to channel IDs
- Edit episode limits for existing channels
- Run the downloader to fetch new episodes
- Generate RSS feeds for your podcasts
- View status of your channels and downloads
- Easy management through a web interface

## Automated Setup and Start

### Windows
1. After cloning the repository, double-click `setup.bat` in the main directory to set up all dependencies
2. To start the Web UI, double-click `webui\start.bat`

### Linux/macOS
1. After cloning the repository, run `./setup.sh` to set up all dependencies
2. To start the Web UI, run `./webui/start.sh`

## Manual Setup

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Make sure you have the following tools installed on your system:
   - `yt-dlp` - For downloading YouTube videos ([installation instructions](https://github.com/yt-dlp/yt-dlp#installation))
   - `jq` - For processing JSON in shell scripts

## Usage

Run the Streamlit app:
```bash
streamlit run app.py
```

The web interface will be available at `http://localhost:8501` by default.

## Configuration

The web UI uses the same `channels.json` file as the main PodQueue application, so any channels you've already configured will be visible in the web interface.

## @username URL Support

The Web UI automatically converts YouTube @username URLs (e.g., https://www.youtube.com/@Level1Linux) to channel ID URLs that yt-dlp can recognize. This requires yt-dlp to be installed and accessible from the command line.