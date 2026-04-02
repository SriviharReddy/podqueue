# PodQueue

**Convert YouTube channels into podcast RSS feeds.** PodQueue automatically downloads the latest videos from your favorite YouTube channels, converts them to audio (M4A), and generates RSS feeds that work with any podcast client.

## Features

- 🔄 **Automatic downloads** - Hourly checks for new videos from configured channels
- 📻 **RSS feed generation** - Compatible with all major podcast apps (Pocket Casts, Overcast, etc.)
- 🌐 **Web UI** - Easy channel management via Streamlit interface
- 🗑️ **Auto-cleanup** - Configurable episode limits per channel
- 📑 **Automatic chapters** - YouTube video sections converted to podcast chapters
- 🔐 **YouTube authentication** - Cookie support to avoid bot detection

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/SriviharReddy/podqueue.git
cd podqueue
./setup.sh
```

### 2. Export YouTube Cookies (Highly Recommended)

Without cookies, YouTube may block automated downloads:

1. Install [Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension
2. Log into YouTube in Chrome
3. Export cookies as `cookies.txt`
4. Place in project root: `podqueue/cookies.txt`

### 3. Start the Web UI

```bash
./webui/start.sh
```

Open `http://localhost:8501` in your browser to configure channels.

### 4. Subscribe to Podcast Feeds

Access your RSS feeds at:
- **Local**: `http://localhost:8501/feeds/CHANNEL_NAME.xml`
- **Remote**: `http://YOUR_SERVER_IP/feeds/CHANNEL_NAME.xml`

Add these URLs to your podcast app.

---

## Table of Contents

- [Manual Installation](#manual-installation)
- [Configuration](#configuration)
- [Running on Remote Server](#running-on-remote-server)
- [Automation (Cron)](#automation-cron)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## Manual Installation

### Prerequisites

| Dependency | Installation |
|------------|--------------|
| Python 3.8+ | `sudo apt install python3 python3-pip` |
| yt-dlp | `pip install yt-dlp` |
| jq | `sudo apt install jq` |
| ffmpeg | `sudo apt install ffmpeg` |

### Setup Steps

1. **Install Python dependencies**:
   ```bash
   pip install -r scripts/requirements.txt
   ```

2. **Configure channels** - Copy and edit `scripts/channels.json`:
   ```bash
   cp scripts/channels.json.example scripts/channels.json
   ```

3. **Set BASE_DIR** - Edit `scripts/downloader.sh` and `scripts/rss_generator.py` to set the absolute path to your project directory.

4. **Add cookies** (recommended):
   Place `cookies.txt` in the project root to avoid YouTube bot detection.

---

## Configuration

### channels.json Format

```json
[
  {
    "id": "ChannelName",
    "url": "https://www.youtube.com/channel/CHANNEL_ID",
    "limit": 5
  }
]
```

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (used for folder and feed names) |
| `url` | YouTube channel or playlist URL |
| `limit` | Maximum episodes to keep (older ones auto-deleted) |

**Supported URLs**:
- Channel: `https://www.youtube.com/channel/UC...`
- Playlist: `https://www.youtube.com/playlist?list=PL...`
- Username: `https://www.youtube.com/@channelname` (converted via Web UI)

---

## Running on Remote Server

### Web UI Access

```bash
cd webui
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

### Firewall Configuration

**Oracle Cloud**: Add security list rule for port 8501 (TCP, source 0.0.0.0/0)

**Linux (ufw)**:
```bash
sudo ufw allow 8501/tcp
```

### Production Recommendations

- Use a reverse proxy (Nginx) with SSL/TLS
- Set up authentication for the Web UI
- Use systemd or supervisor to keep services running
- Serve the `feeds/` directory via HTTP for podcast clients

---

## Automation (Cron)

Edit crontab with `crontab -e`:

```bash
# Update yt-dlp daily (keeps YouTube challenge solver current)
0 2 * * * /path/to/venv/bin/pip install -U yt-dlp yt_dlp_ejs

# Download new episodes hourly
0 * * * * /path/to/podqueue/scripts/downloader.sh

# Generate RSS feeds hourly (after downloader)
5 * * * * /path/to/podqueue/venv/bin/python /path/to/podqueue/scripts/rss_generator.py
```

**Important**: Keep `yt-dlp` and `yt_dlp_ejs` updated to avoid YouTube bot detection issues.

---

## Troubleshooting

### No New Episodes Downloading

**Symptom**: Downloader runs but no new episodes appear.

**Causes & Fixes**:

1. **Expired cookies** - Re-export YouTube cookies (see [Quick Start](#2-export-youtube-cookies-highly-recommended))

2. **Outdated yt-dlp** - Update manually:
   ```bash
   pip install -U yt-dlp yt_dlp_ejs
   ```

3. **Check logs**:
   ```bash
   tail -100 logs/cron.log
   ```

### File Limits Not Enforced

The cleanup runs before and after downloads. To manually clean up:

```bash
cd /path/to/downloads/ChannelName
ls -t *.m4a | awk 'NR>LIMIT' | xargs rm
```

### RSS Feeds Not Updating

Run the generator manually:
```bash
python3 scripts/rss_generator.py
```

### YouTube Bot Detection Errors

Common errors:
- `Sign in to confirm you're not a bot`
- `n challenge solving failed`
- `Requested format is not available`

**Fix**: Update yt-dlp and refresh cookies:
```bash
pip install -U yt-dlp yt_dlp_ejs
# Then re-export cookies.txt
```

### SSH Connection Issues (Remote Servers)

If SSH times out:
1. Check cloud provider's security groups/firewall rules
2. Verify port 22 is allowed
3. Restart VM if needed

---

## Project Structure

```
podqueue/
├── scripts/
│   ├── downloader.sh          # Downloads videos from YouTube
│   ├── rss_generator.py       # Generates RSS feeds
│   └── channels.json          # Channel configuration
├── downloads/                  # Downloaded audio files (by channel)
├── feeds/                      # Generated RSS feeds
├── artwork/                    # Channel artwork
├── webui/                      # Streamlit web interface
├── cookies.txt                 # YouTube authentication
└── MAINTENANCE.md              # Detailed troubleshooting guide
```

---

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

MIT License

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [Streamlit](https://streamlit.io/) - Web UI framework
