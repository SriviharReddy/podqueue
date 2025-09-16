#!/bin/bash

BASE_DIR="/home/ubuntu/my_podcast_service"
source "$BASE_DIR/venv/bin/activate"

# Create downloads_kemono directory if it doesn't exist
mkdir -p "$BASE_DIR/downloads_kemono"

echo "--- Starting Kemono podcast sync with gallery-dl at $(date) ---"

jq -c '.[]' "$BASE_DIR/scripts/channels_kemono.json" |
while read i; do
  ID=$(jq -r '.id' <<< "$i")
  URL=$(jq -r '.url' <<< "$i")
  LIMIT=$(jq -r '.limit' <<< "$i")
  DOWNLOAD_DIR="$BASE_DIR/downloads_kemono/$ID"
  mkdir -p "$DOWNLOAD_DIR"

  echo "--- Processing: $ID ---"

  RANGE_ARG=""
  if [[ "$LIMIT" -gt 0 ]]; then
    RANGE_ARG="--range 1-${LIMIT}"
  fi

  gallery-dl \
    --write-metadata \
    --directory "$DOWNLOAD_DIR" \
    --filename "{id}_{title}.{extension}" \
    --filter "extension in ('mp3', 'm4a', 'opus', 'ogg', 'wav')" \
    $RANGE_ARG \
    "$URL"

  echo "--- Finished processing: $ID ---"
done

echo "--- Kemono sync complete at $(date) ---"
