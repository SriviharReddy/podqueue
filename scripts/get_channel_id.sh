#!/bin/bash

# This script retrieves the channel ID for a given YouTube channel URL.
# It uses yt-dlp to extract the channel ID from the channel's page.

# Usage: ./get_channel_id.sh <channel_url>

if [ -z "$1" ]; then
  echo "Usage: $0 <channel_url>"
  exit 1
fi

CHANNEL_URL=$1

# Use yt-dlp to get the channel ID
CHANNEL_ID=$(yt-dlp --print "%(channel_id)s" --playlist-end 1 "$CHANNEL_URL")

if [ -n "$CHANNEL_ID" ]; then
  echo "Channel ID: $CHANNEL_ID"
else
  echo "Could not retrieve channel ID. Please check the URL and make sure yt-dlp is installed."
fi