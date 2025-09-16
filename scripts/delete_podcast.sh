#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 <podcast_name>"
    echo "Example: $0 VergeCast"
    exit 1
fi

PODCAST_NAME="$1"
BASE_DIR="/home/ubuntu/my_podcast_service"

# Define paths
DOWNLOADS_DIR="$BASE_DIR/downloads/$PODCAST_NAME"
FEEDS_FILE="$BASE_DIR/feeds/$PODCAST_NAME.xml"
ARTWORK_FILE="$BASE_DIR/artwork/$PODCAST_NAME.jpg"
CHANNELS_FILE="$BASE_DIR/scripts/channels.json"

echo "Deleting podcast: $PODCAST_NAME"

# Delete downloads directory
if [ -d "$DOWNLOADS_DIR" ]; then
    echo "Deleting downloads directory: $DOWNLOADS_DIR"
    sudo rm -rf "$DOWNLOADS_DIR"
else
    echo "Downloads directory not found: $DOWNLOADS_DIR"
fi

# Delete feed file
if [ -f "$FEEDS_FILE" ]; then
    echo "Deleting feed file: $FEEDS_FILE"
    sudo rm -f "$FEEDS_FILE"
else
    echo "Feed file not found: $FEEDS_FILE"
fi

# Delete artwork file
if [ -f "$ARTWORK_FILE" ]; then
    echo "Deleting artwork file: $ARTWORK_FILE"
    sudo rm -f "$ARTWORK_FILE"
else
    echo "Artwork file not found: $ARTWORK_FILE"
fi

# Ask if user wants to remove from channels.json
read -p "Do you want to remove $PODCAST_NAME from channels.json? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -f "$CHANNELS_FILE" ]; then
        echo "Removing from channels.json..."
        # Create a temporary file
        TEMP_FILE=$(mktemp)
        # Remove the podcast entry using jq
        jq "del(.[] | select(.id == \"$PODCAST_NAME\"))" "$CHANNELS_FILE" > "$TEMP_FILE"
        # Replace the original file
        sudo mv "$TEMP_FILE" "$CHANNELS_FILE"
        sudo chown ubuntu:ubuntu "$CHANNELS_FILE"
        echo "Removed $PODCAST_NAME from channels.json"
    else
        echo "channels.json file not found"
    fi
fi

echo "Deletion complete for podcast: $PODCAST_NAME"
