#!/bin/bash

# This script deletes a podcast, including all its downloaded files, artwork, and the RSS feed.

# Usage: ./delete_podcast.sh <podcast_id>

if [ -z "$1" ]; then
  echo "Usage: $0 <podcast_id>"
  exit 1
fi

PODCAST_ID=$1
BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..

DOWNLOAD_DIR="$BASE_DIR/downloads/$PODCAST_ID"
ARTWORK_FILE="$BASE_DIR/artwork/$PODCAST_ID.jpg"
FEED_FILE="$BASE_DIR/feeds/$PODCAST_ID.xml"

read -p "Are you sure you want to delete all files for podcast '$PODCAST_ID'? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    exit 1
fi

if [ -d "$DOWNLOAD_DIR" ]; then
  echo "Deleting download directory: $DOWNLOAD_DIR"
  rm -rf "$DOWNLOAD_DIR"
fi

if [ -f "$ARTWORK_FILE" ]; then
  echo "Deleting artwork file: $ARTWORK_FILE"
  rm -f "$ARTWORK_FILE"
fi

if [ -f "$FEED_FILE" ]; then
  echo "Deleting feed file: $FEED_FILE"
  rm -f "$FEED_FILE"
fi

# Remove the channel from channels.json
TEMP_CHANNELS_FILE="$BASE_DIR/scripts/channels.json.tmp"

if [ -f "$BASE_DIR/scripts/channels.json" ]; then
    echo "Removing $PODCAST_ID from channels.json"
    jq 'del(.[] | select(.id == "'$PODCAST_ID''))' "$BASE_DIR/scripts/channels.json" > "$TEMP_CHANNELS_FILE" && mv "$TEMP_CHANNELS_FILE" "$BASE_DIR/scripts/channels.json"
fi

echo "Podcast '$PODCAST_ID' deleted."