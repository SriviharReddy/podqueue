# PodQueue Web UI

A Streamlit-based web interface for managing your PodQueue YouTube to podcast converter.

## Features

- Add and remove YouTube channels/playlists
- Run the downloader to fetch new episodes
- Generate RSS feeds for your podcasts
- View status of your channels and downloads
- Easy management through a web interface

## Installation

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Make sure you have the following tools installed on your system:
   - `yt-dlp` - For downloading YouTube videos
   - `jq` - For processing JSON in shell scripts

## Usage

Run the Streamlit app:
```bash
streamlit run app.py
```

The web interface will be available at `http://localhost:8501` by default.

## Configuration

The web UI uses the same `channels.json` file as the main PodQueue application, so any channels you've already configured will be visible in the web interface.