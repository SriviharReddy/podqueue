# PodQueue Web UI

A Streamlit-based web interface for managing your PodQueue YouTube to podcast converter.

## Easy Setup for Beginners

1. After cloning the repository, run `./setup.sh` to set up all dependencies
2. To start the Web UI, run one of the following:
   - `./webui/start.sh` - Standard start (local access only)
   - `./webui/start-network.sh` - Network mode (remote access)
   - `./webui/start-venv.sh` - Standard start using virtual environment
   - `./webui/start-venv-network.sh` - Network mode using virtual environment

Then open your browser and go to `http://localhost:8501`

## Running on a Remote Server

To access the Web UI from another device when running on a remote server:

1. Start the Web UI with network access:
   ```bash
   ./webui/start-venv-network.sh
   ```

2. Configure your server's firewall to allow connections on port 8501

3. Access the Web UI from any device on the same network using:
   `http://YOUR_SERVER_IP:8501`

For production use, consider:
- Using a reverse proxy (like Nginx) with SSL encryption
- Setting up authentication to secure the Web UI
- Using a process manager (like systemd or supervisor) to keep the Web UI running

## Password Protection

The Web UI includes built-in password protection:
- On first access, you'll be prompted to set up an admin username and password
- You can choose to skip authentication if running in a secure environment
- After setup, you'll need to log in to access the Web UI
- A logout button is available in the sidebar

## Features

- Add and remove YouTube channels/playlists
- Automatically convert @username URLs to channel IDs
- Edit episode limits for existing channels
- Run the downloader to fetch new episodes
- Generate RSS feeds for your podcasts
- View status of your channels and downloads
- Easy management through a web interface

## Manual Setup

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Make sure you have the following tools installed on your system:
   - `yt-dlp` - For downloading YouTube videos ([installation instructions](https://github.com/yt-dlp/yt-dlp#installation))
   - `jq` - For processing JSON in shell scripts

## Usage

Run the Streamlit app using one of the provided scripts:
```bash
# Local access only
./webui/start-venv.sh

# Network access (remote devices)
./webui/start-venv-network.sh
```

The web interface will be available at `http://localhost:8501` by default.

## Configuration

The web UI uses the same `channels.json` file as the main PodQueue application, so any channels you've already configured will be visible in the web interface.

## @username URL Support

The Web UI automatically converts YouTube @username URLs (e.g., https://www.youtube.com/@Level1Linux) to channel ID URLs that yt-dlp can recognize. This requires yt-dlp to be installed and accessible from the command line.

## Exporting Cookies

If you need to download videos that require a login, you can export cookies from your browser using the [Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension. Save the exported cookies.txt file in the root directory of the project.