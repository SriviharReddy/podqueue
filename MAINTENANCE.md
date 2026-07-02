# PodQueue Maintenance Guide

This document provides maintenance instructions and troubleshooting for the PodQueue podcast service.

## Server Information

- **Host**: Oracle Cloud VM
- **IP**: 152.67.182.84
- **User**: ubuntu
- **SSH Key**: `ssh-key-2025-08-20.key`
- **Base Directory**: `/home/ubuntu/my_podcast_service/`

## SSH Connection

```bash
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84
```

## Service Architecture

```
/home/ubuntu/my_podcast_service/
├── scripts/
│   ├── downloader.sh          # Downloads videos from YouTube channels
│   ├── rss_generator.py       # Generates RSS feeds from downloaded audio
│   ├── downloader_kemono.sh   # Downloads from Kemono (fan content)
│   ├── rss_generator_kemono.py
│   ├── delete_podcast_kemono.sh
│   └── channels.json          # Channel configuration
├── downloads/                  # Downloaded audio files (organized by channel)
├── feeds/                      # Generated RSS feeds
├── artwork/                    # Channel/podcast artwork
├── logs/                       # Cron and script logs
├── webui/                      # Streamlit web interface
├── venv/                       # Python virtual environment
└── cookies.txt                 # YouTube authentication cookies
```

## Cron Jobs

```bash
# View cron jobs
crontab -l

# Schedule:
0 2 * * *   # Daily at 2 AM UTC - Update yt-dlp and yt_dlp_ejs
0 * * * *   # Every hour - Run downloader and RSS generator
15 */6 * * * # Every 6 hours - Kemono sync
30 3 * * *   # Daily at 3:30 AM - Kemono cleanup
```

## Key Dependencies

| Package | Purpose | Update Command |
|---------|---------|----------------|
| yt-dlp | YouTube video downloader | `pip install -U yt-dlp` |
| yt_dlp_ejs | JavaScript challenge solver for YouTube | `pip install -U yt_dlp_ejs` |
| ffmpeg | Audio conversion | System package |
| jq | JSON parsing in shell scripts | System package |

## Common Issues and Fixes

### 1. No New Episodes Downloading

**Symptoms**: Downloader runs but no new episodes are downloaded, even when new videos exist on YouTube.

**Possible Causes**:

#### A. Expired Cookies
YouTube cookies expire and need to be refreshed.

**Fix**:
1. Install "Get cookies.txt locally" Chrome extension
2. Log into YouTube in Chrome
3. Export cookies using the extension
4. Upload to server:
   ```bash
   scp -i ssh-key-2025-08-20.key cookies.txt ubuntu@152.67.182.84:/home/ubuntu/my_podcast_service/cookies.txt
   ```

#### B. Outdated yt-dlp or yt_dlp_ejs
YouTube frequently changes their bot detection. Older versions may fail.

**Fix**:
```bash
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84
/home/ubuntu/my_podcast_service/venv/bin/pip install -U yt-dlp yt_dlp_ejs
```

**Signs of this issue**:
- Error: `Challenge solver lib script version X.X.X is not supported`
- Error: `n challenge solving failed`
- Error: `Requested format is not available` (only images available)

#### C. Unsupported JavaScript Runtime
yt-dlp on the VM now uses Deno for challenge solving. If the runtime is missing or misconfigured, the extractor can still fall back to a broken Node setup.

**Fix**:
```bash
sudo sh -lc 'cat > /home/ubuntu/.config/yt-dlp/config <<EOF
--js-runtimes node
--js-runtimes deno:/home/ubuntu/.deno/bin/deno
--remote-components ejs:npm
EOF'
```

**Verify**:
```bash
/home/ubuntu/my_podcast_service/venv/bin/yt-dlp --verbose --skip-download --cookies /home/ubuntu/my_podcast_service/cookies.txt "https://www.youtube.com/watch?v=VIDEO_ID"
```

You should see `JS runtimes: deno-...` in the debug output and `[jsc:deno]` challenge-solving lines.

#### D. Format Not Available
Some videos may be Premieres, members-only, or have restricted formats.

**Fix**: Check if the video is publicly available or requires Premium access.

### 2. File Limits Not Being Enforced

**Symptoms**: More audio files exist in download folders than the configured limit.

**Cause**: The cleanup logic only runs after yt-dlp downloads something. If all videos are already in the archive, cleanup never triggers.

**Fix**: The script now runs cleanup **before** yt-dlp as well. To manually clean up:

```bash
# For a specific channel (e.g., limit=5)
cd /home/ubuntu/my_podcast_service/downloads/SkillUpYT
ls -t *.m4a | awk 'NR>5' | xargs -I {} sh -c 'echo "Deleting: {}"; rm -f "{}" "{}.info.json"'

# Rebuild archive file
for f in *.m4a; do vid="${f%.m4a}"; grep -q "youtube $vid" archive.txt || echo "youtube $vid" >> archive.txt; done
sort -u archive.txt -o archive.txt
```

### 2b. Playlist Scan Window Too Small

**Symptoms**: Downloader runs hourly, but new episodes do not appear after private or unavailable entries at the top of a playlist.

**Cause**: The downloader used to scan only `limit` items, which could stop at unavailable videos before reaching a playable episode.

**Fix**: The downloader now scans a larger window before applying the download archive. If this regresses, inspect `scripts/downloader.sh` and increase the scan window again.

### 3. RSS Feeds Not Updating

**Symptoms**: New episodes downloaded but not appearing in podcast clients.

**Fix**:
```bash
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84
cd /home/ubuntu/my_podcast_service
/home/ubuntu/my_podcast_service/venv/bin/python /home/ubuntu/my_podcast_service/scripts/rss_generator.py
```

### 4. SSH Connection Timeouts

**Symptoms**: SSH connection times out or hangs.

**Causes**:
- Network issues
- Server overloaded
- Oracle Cloud security list blocking

**Fix**:
1. Wait a few minutes and retry
2. Check Oracle Cloud Console → Networking → Security Lists to ensure port 22 is allowed
3. Restart the VM from Oracle Cloud Console if needed

### 5. Duplicate Download Folders

**Symptoms**: Multiple folders for the same channel (e.g., `BehindtBas` and `BehindtBas ` with trailing space).

**Cause**: Channel name typos in channels.json or script bugs.

**Fix**:
```bash
# Identify duplicates
ls -la /home/ubuntu/my_podcast_service/downloads/

# Remove old folders (after verifying content)
rm -rf /home/ubuntu/my_podcast_service/downloads/OldFolderName
```

## Channel Configuration

Edit `/home/ubuntu/my_podcast_service/scripts/channels.json`:

```json
[
  {
    "id": "ChannelName",
    "url": "https://www.youtube.com/channel/CHANNEL_ID or https://www.youtube.com/playlist?list=PLAYLIST_ID",
    "limit": 5
  }
]
```

**Notes**:
- `limit`: Maximum number of episodes to keep per channel
- URLs can be channel IDs or playlist IDs
- For @username URLs, convert to channel ID first using the WebUI

## Manual Operations

### Run Downloader Manually
```bash
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84
cd /home/ubuntu/my_podcast_service
./scripts/downloader.sh
```

### Run RSS Generator Manually
```bash
/home/ubuntu/my_podcast_service/venv/bin/python /home/ubuntu/my_podcast_service/scripts/rss_generator.py
```

### Check Logs
```bash
# Recent cron logs
tail -100 /home/ubuntu/my_podcast_service/logs/cron.log

# Kemono logs
tail -100 /home/ubuntu/my_podcast_service/logs/kemono_cron.log

# Systemd journal
journalctl -u cron --since "2 hours ago"
```

### Check Download Status
```bash
# Count files per channel
for dir in /home/ubuntu/my_podcast_service/downloads/*/; do 
  echo "$(basename $dir): $(ls -1 $dir/*.m4a 2>/dev/null | wc -l) files"
done

# Latest downloads
find /home/ubuntu/my_podcast_service/downloads -name "*.m4a" -printf '%T@ %p\n' | sort -rn | head -20
```

## Web Interface

The Streamlit WebUI runs on port 8501:
- **URL**: `http://152.67.182.84:8501`
- **Start**: `cd /home/ubuntu/my_podcast_service/webui && streamlit run app.py`
- **Status**: Runs in tmux session named `streamlit`

### Access WebUI via tmux
```bash
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84
tmux attach -t streamlit
```

## Firewall/Network

Oracle Cloud requires security list rules for inbound traffic:

| Port | Purpose | Required |
|------|---------|----------|
| 22 | SSH | Yes |
| 8501 | WebUI | Optional |
| 80/443 | Public RSS feeds | Optional |

To add a rule:
1. Oracle Cloud Console → Networking → Virtual Cloud Networks
2. Click your VCN → Security Lists
3. Add Ingress Rule: Source `0.0.0.0/0`, Port `8501`, Protocol `TCP`

## Backup Recommendations

1. **cookies.txt**: Re-export when expired
2. **channels.json**: Version control or manual backup
3. **downloaded audio**: Not critical (can re-download), but consider backing up favorites

## Version History

| Date | Change |
|------|--------|
| 2026-03-29 | Fixed yt_dlp_ejs challenge solver (0.3.1 → 0.8.0), updated yt-dlp (2025.11.12 → 2026.03.17), fixed cookie authentication |
| 2026-04-01 | Fixed file limit enforcement - added cleanup before yt-dlp runs, cleaned up duplicate folders |
| 2026-07-02 | Added Deno-based yt-dlp runtime config and widened the playlist scan window so private or unavailable entries do not block downloads |

## Quick Reference Commands

```bash
# SSH to server
ssh -i ssh-key-2025-08-20.key ubuntu@152.67.182.84

# Update yt-dlp and challenge solver
/home/ubuntu/my_podcast_service/venv/bin/pip install -U yt-dlp yt_dlp_ejs

# Check yt-dlp version
/home/ubuntu/my_podcast_service/venv/bin/yt-dlp --version

# Test YouTube access
/home/ubuntu/my_podcast_service/venv/bin/yt-dlp --cookies /home/ubuntu/my_podcast_service/cookies.txt --skip-download "https://www.youtube.com/watch?v=VIDEO_ID"

# Restart WebUI (if needed)
tmux kill-session -t streamlit
cd /home/ubuntu/my_podcast_service/webui
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
