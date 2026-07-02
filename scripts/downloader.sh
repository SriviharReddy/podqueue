#!/bin/bash
BASE_DIR="/home/ubuntu/my_podcast_service"
source "$BASE_DIR/venv/bin/activate"
STATE_DIR="$BASE_DIR/state/channel_checks"
mkdir -p "$STATE_DIR"
echo "Starting YouTube podcast sync at $(date)"
jq -c '.[]' "$BASE_DIR/scripts/channels.json" | while read i; do
  ID=$(jq -r '.id' <<< "$i")
  URL=$(jq -r '.url' <<< "$i")
  LIMIT=$(jq -r '.limit' <<< "$i")
  CHECK_INTERVAL_HOURS=$(jq -r '(.check_interval_hours // 1) | tonumber? // 1 | if . < 1 then 1 else . end' <<< "$i")
  SPONSORBLOCK_VALUE=$(jq -r '
    if has("sponsorblock") then .sponsorblock
    elif has("sponsor_block") then .sponsor_block
    else false
    end
    | if . == null then "false" else tostring end
  ' <<< "$i")
  DOWNLOAD_DIR="$BASE_DIR/downloads/$ID"
  ARCHIVE_FILE="$DOWNLOAD_DIR/archive.txt"
  LAST_CHECK_FILE="$STATE_DIR/$ID.last_check"
  CURRENT_TIME=$(date +%s)
  PLAYLIST_SCAN_LIMIT=$((LIMIT * 5))
  if [ "$PLAYLIST_SCAN_LIMIT" -lt 20 ]; then
    PLAYLIST_SCAN_LIMIT=20
  fi
  mkdir -p "$DOWNLOAD_DIR"
  echo "--- Processing: $ID ---"
  echo "Check interval: ${CHECK_INTERVAL_HOURS} hour(s)"
  echo "SponsorBlock: $SPONSORBLOCK_VALUE"
  echo "Playlist scan window: ${PLAYLIST_SCAN_LIMIT} item(s)"
  if [ -f "$LAST_CHECK_FILE" ]; then
    LAST_CHECK_TIME=$(cat "$LAST_CHECK_FILE")
    if [[ "$LAST_CHECK_TIME" =~ ^[0-9]+$ ]]; then
      NEXT_CHECK_TIME=$((LAST_CHECK_TIME + CHECK_INTERVAL_HOURS * 3600))
      if [ "$CURRENT_TIME" -lt "$NEXT_CHECK_TIME" ]; then
        REMAINING_MINUTES=$(((NEXT_CHECK_TIME - CURRENT_TIME + 59) / 60))
        echo "Skipping $ID. Next check in about ${REMAINING_MINUTES} minute(s)."
        continue
      fi
    fi
  fi
  # Rebuild archive file based on existing .info.json files
  echo "--- Rebuilding archive file for: $ID ---"
  if [ -f "$ARCHIVE_FILE" ]; then
    # Create a temporary archive file
    TEMP_ARCHIVE="$ARCHIVE_FILE.tmp"
    > "$TEMP_ARCHIVE"
    # For each .info.json file, extract the video ID and add to temp archive
    for info_file in "$DOWNLOAD_DIR"/*.info.json; do
      if [ -f "$info_file" ]; then
        # Extract video ID from the info.json file
        VIDEO_ID=$(grep -o '"id": "[^"\\]*"' "$info_file" | head -1 | cut -d'"' -f4)
        if [ -n "$VIDEO_ID" ]; then
          echo "youtube $VIDEO_ID" >> "$TEMP_ARCHIVE"
          echo "Added $VIDEO_ID to archive from $(basename "$info_file")"
        fi
      fi
    done
    # Replace the original archive file with the rebuilt one
    mv "$TEMP_ARCHIVE" "$ARCHIVE_FILE"
    echo "Archive file rebuilt for $ID"
  fi
  # Clean up BEFORE downloading (in case limit was reduced)
  echo "--- Cleaning up old episodes for: $ID (before download) ---"
  cd "$DOWNLOAD_DIR"
  AUDIO_COUNT=$(ls -1 *.m4a 2>/dev/null | wc -l)
  echo "Found $AUDIO_COUNT audio files, limit is $LIMIT"
  if [ "$AUDIO_COUNT" -gt "$LIMIT" ]; then
    ls -t *.m4a | tail -n +$(($LIMIT + 1)) | while read file; do
      echo "Deleting old episode: $file"
      rm -f "$file" "${file%.m4a}.info.json"
    done
    echo "Cleanup complete for $ID"
  else
    echo "No cleanup needed for $ID"
  fi

  YTDLP_CMD=(
    yt-dlp
    --cookies "$BASE_DIR/cookies.txt"
    --download-archive "$ARCHIVE_FILE"
    --playlist-end "$PLAYLIST_SCAN_LIMIT"
    -f "bestaudio[ext=m4a]/bestaudio/best"
    --extract-audio
    --write-info-json
    --restrict-filenames
    --verbose
    --match-filter "!is_short"
    --output "$DOWNLOAD_DIR/%(id)s.%(ext)s"
  )

  case "${SPONSORBLOCK_VALUE,,}" in
    true|1|yes|on)
      YTDLP_CMD+=(--sponsorblock-remove all)
      ;;
    false|0|no|off|"")
      ;;
    *)
      YTDLP_CMD+=(--sponsorblock-remove "$SPONSORBLOCK_VALUE")
      ;;
  esac

  echo "$CURRENT_TIME" > "$LAST_CHECK_FILE"
  # Download new videos (excluding Shorts)
  "${YTDLP_CMD[@]}" "$URL"
  # Clean up old episodes if we have more than the limit
  echo "--- Cleaning up old episodes for: $ID ---"
  cd "$DOWNLOAD_DIR"
  # Count audio files
  AUDIO_COUNT=$(ls -1 *.m4a 2>/dev/null | wc -l)
  echo "Found $AUDIO_COUNT audio files, limit is $LIMIT"
  if [ "$AUDIO_COUNT" -gt "$LIMIT" ]; then
    # List all .m4a files sorted by modification time (newest first)
    # and delete all but the first $LIMIT files
    ls -t *.m4a | tail -n +$(($LIMIT + 1)) | while read file; do
      echo "Deleting old episode: $file"
      # Extract video ID from the info.json file if it exists
      INFO_FILE="${file%.m4a}.info.json"
      VIDEO_ID=""
      if [ -f "$INFO_FILE" ]; then
        # Extract video ID from the info.json file
        VIDEO_ID=$(grep -o '"id": "[^"\\]*"' "$INFO_FILE" | cut -d'"' -f4)
        echo "Found video ID: $VIDEO_ID"
        # Delete the info file
        rm -f "$INFO_FILE"
      fi
      # Delete the audio file
      rm -f "$file"
      # Remove from archive file if we found the video ID
      if [ -n "$VIDEO_ID" ] && [ -f "$ARCHIVE_FILE" ]; then
        echo "Removing $VIDEO_ID from archive file"
        # Create a temporary file without the video ID entry
        grep -v "youtube $VIDEO_ID" "$ARCHIVE_FILE" > "${ARCHIVE_FILE}.tmp"
        # Replace the original archive file
        mv "${ARCHIVE_FILE}.tmp" "$ARCHIVE_FILE"
      fi
    done
    echo "Cleanup complete for $ID"
  else
    echo "No cleanup needed for $ID"
  fi

  # ===================================================================
  # == NEW SECTION: Clean up leftover temp and mp4 files
  # ===================================================================
  echo "--- Cleaning up leftover .mp4 and .temp files for: $ID ---"
  # Find and delete files ending in .mp4 or .temp.mp4.
  # The 'find' command is safer than 'rm *.mp4' as it handles
  # filenames with spaces and other special characters correctly.
  # The '!' negates the name, so it won't delete .info.json files.
  find "$DOWNLOAD_DIR" -type f \( -name "*.mp4" -o -name "*.temp.mp4" \) ! -name "*.info.json" -print -delete
  echo "Leftover file cleanup complete for $ID"
  # ===================================================================

  echo "--- Finished processing: $ID ---"
done
echo "Sync complete at $(date)"
