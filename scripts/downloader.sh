#!/bin/bash
BASE_DIR="/home/ubuntu/my_podcast_service"
source "$BASE_DIR/venv/bin/activate"
echo "Starting YouTube podcast sync at $(date)"
jq -c '.[]' "$BASE_DIR/scripts/channels.json" | while read i; do
  ID=$(jq -r '.id' <<< "$i")
  URL=$(jq -r '.url' <<< "$i")
  LIMIT=$(jq -r '.limit' <<< "$i")
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
  # Download new videos (excluding Shorts)
  yt-dlp \
    --cookies "$BASE_DIR/cookies.txt" \
    --download-archive "$ARCHIVE_FILE" \
    --playlist-end "$LIMIT" \
    -f "bestaudio[ext=m4a]/bestaudio/best" \
    --extract-audio \
    --write-info-json \
    --restrict-filenames \
    --verbose \
    --match-filter "!is_short" \
    --output "$DOWNLOAD_DIR/%(id)s.%(ext)s" \
    "$URL"
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
