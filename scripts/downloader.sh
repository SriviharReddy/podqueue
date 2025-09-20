#!/bin/bash
BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..
source "$BASE_DIR/venv/bin/activate"
echo "Starting YouTube podcast sync at $(date)"
jq -c '.[]' "$BASE_DIR/scripts/channels.json" | while read i; do
  ID=$(jq -r '.id' <<< "$i")
  URL=$(jq -r '.url' <<< "$i")
  LIMIT=$(jq -r '.limit' <<< "$i")
  DOWNLOAD_LIMIT=$(jq -r '.download_limit' <<< "$i")
  QUALITY=$(jq -r '.quality' <<< "$i")
  DATE_AFTER=$(jq -r '.date_after' <<< "$i")
  DATE_BEFORE=$(jq -r '.date_before' <<< "$i")
  SUB_LANG=$(jq -r '.sub_lang' <<< "$i")
  ARCHIVE=$(jq -r '.archive' <<< "$i")
  SPONSOR_BLOCK=$(jq -r '.sponsor_block' <<< "$i")
  FORMAT=$(jq -r '.format' <<< "$i")
  COOKIES=$(jq -r '.cookies' <<< "$i")
  USER_AGENT=$(jq -r '.user_agent' <<< "$i")
  PROXY=$(jq -r '.proxy' <<< "$i")
  RATE_LIMIT=$(jq -r '.rate_limit' <<< "$i")
  OUTPUT_TEMPLATE=$(jq -r '.output_template' <<< "$i")
  CONFIG_FILE=$(jq -r '.config_file' <<< "$i")
  LOG_FILE=$(jq -r '.log_file' <<< "$i")
  DOWNLOAD_DIR="$BASE_DIR/downloads/$ID"
  ARCHIVE_FILE="$DOWNLOAD_DIR/archive.txt"
  mkdir -p "$DOWNLOAD_DIR"
  echo "--- Processing: $ID ---"
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
  # Set download limit
  if [ "$DOWNLOAD_LIMIT" != "null" ] && [ -n "$DOWNLOAD_LIMIT" ]; then
    PLAYLIST_END_OPTION="--playlist-end $DOWNLOAD_LIMIT"
  else
    PLAYLIST_END_OPTION="--playlist-end $LIMIT"
  fi

  # Set audio quality
  if [ "$QUALITY" != "null" ] && [ -n "$QUALITY" ]; then
    AUDIO_FORMAT_OPTION="-f $QUALITY"
  else
    AUDIO_FORMAT_OPTION="-f bestaudio[ext=m4a]/bestaudio/best"
  fi

  # Set date range
  DATE_OPTIONS=""
  if [ "$DATE_AFTER" != "null" ] && [ -n "$DATE_AFTER" ]; then
    DATE_OPTIONS="$DATE_OPTIONS --dateafter $DATE_AFTER"
  fi
  if [ "$DATE_BEFORE" != "null" ] && [ -n "$DATE_BEFORE" ]; then
    DATE_OPTIONS="$DATE_OPTIONS --datebefore $DATE_BEFORE"
  fi

  # Set subtitle language
  SUB_OPTIONS=""
  if [ "$SUB_LANG" != "null" ] && [ -n "$SUB_LANG" ]; then
    SUB_OPTIONS="--write-sub --sub-lang $SUB_LANG"
  fi

  # Set archive file
  if [ "$ARCHIVE" != "null" ] && [ -n "$ARCHIVE" ]; then
    ARCHIVE_FILE="$ARCHIVE"
  else
    ARCHIVE_FILE="$DOWNLOAD_DIR/archive.txt"
  fi

  # Set sponsor block removal
  SPONSOR_BLOCK_OPTIONS=""
  if [ "$SPONSOR_BLOCK" != "null" ] && [ -n "$SPONSOR_BLOCK" ]; then
    SPONSOR_BLOCK_OPTIONS="--sponsorblock-remove $SPONSOR_BLOCK"
  fi

  # Set output format
  if [ "$FORMAT" != "null" ] && [ -n "$FORMAT" ]; then
    AUDIO_FORMAT_OPTION="--extract-audio --audio-format $FORMAT"
  else
    AUDIO_FORMAT_OPTION="--extract-audio --audio-format m4a"
  fi

  # Set cookie file
  if [ "$COOKIES" != "null" ] && [ -n "$COOKIES" ]; then
    COOKIE_FILE="$COOKIES"
  else
    COOKIE_FILE="$BASE_DIR/cookies.txt"
  fi

  # Set user agent
  if [ "$USER_AGENT" != "null" ] && [ -n "$USER_AGENT" ]; then
    USER_AGENT_OPTION="--user-agent \"$USER_AGENT\""
  else
    USER_AGENT_OPTION=""
  fi

  # Set proxy
  if [ "$PROXY" != "null" ] && [ -n "$PROXY" ]; then
    PROXY_OPTION="--proxy \"$PROXY\""
  else
    PROXY_OPTION=""
  fi

  # Set rate limit
  if [ "$RATE_LIMIT" != "null" ] && [ -n "$RATE_LIMIT" ]; then
    RATE_LIMIT_OPTION="--limit-rate $RATE_LIMIT"
  else
    RATE_LIMIT_OPTION=""
  fi

  # Set output template
  if [ "$OUTPUT_TEMPLATE" != "null" ] && [ -n "$OUTPUT_TEMPLATE" ]; then
    OUTPUT_TEMPLATE_OPTION="--output \"$DOWNLOAD_DIR/$OUTPUT_TEMPLATE\""
  else
    OUTPUT_TEMPLATE_OPTION="--output \"$DOWNLOAD_DIR/%(id)s.%(ext)s\""
  fi

  # Set config file
  if [ "$CONFIG_FILE" != "null" ] && [ -n "$CONFIG_FILE" ]; then
    CONFIG_FILE_OPTION="--config-location \"$CONFIG_FILE\""
  else
    CONFIG_FILE_OPTION=""
  fi

  # Set log file
  if [ "$LOG_FILE" != "null" ] && [ -n "$LOG_FILE" ]; then
    LOG_FILE_OPTION="--log-file \"$LOG_FILE\""
  else
    LOG_FILE_OPTION=""
  fi

  # Download new videos (excluding Shorts)
  yt-dlp \
    $LOG_FILE_OPTION \
    $CONFIG_FILE_OPTION \
    $RATE_LIMIT_OPTION \
    $PROXY_OPTION \
    $USER_AGENT_OPTION \
    --cookies "$COOKIE_FILE" \
    --download-archive "$ARCHIVE_FILE" \
    $PLAYLIST_END_OPTION \
    $AUDIO_FORMAT_OPTION \
    $DATE_OPTIONS \
    $SUB_OPTIONS \
    $SPONSOR_BLOCK_OPTIONS \
    $OUTPUT_TEMPLATE_OPTION \
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
  echo "--- Finished processing: $ID ---"
done
echo "Sync complete at $(date)"
