#!/bin/bash

BASE_DIR="/home/ubuntu/my_podcast_service"
DOWNLOADS_DIR="$BASE_DIR/downloads_kemono"

echo "--- Starting Kemono podcast cleanup at $(date) ---"

# Process each channel in channels_kemono.json
jq -c '.[]' "$BASE_DIR/scripts/channels_kemono.json" |
while read -r channel; do
  CHANNEL_ID=$(jq -r '.id' <<< "$channel")
  LIMIT=$(jq -r '.limit' <<< "$channel")
  
  # Skip if limit is 0 or negative (no limit)
  if [[ "$LIMIT" -le 0 ]]; then
    echo "--- Skipping $CHANNEL_ID (no limit set) ---"
    continue
  fi
  
  CHANNEL_DIR="$DOWNLOADS_DIR/$CHANNEL_ID"
  
  # Skip if channel directory doesn't exist
  if [[ ! -d "$CHANNEL_DIR" ]]; then
    echo "--- Channel directory not found: $CHANNEL_DIR ---"
    continue
  fi
  
  echo "--- Processing: $CHANNEL_ID (limit: $LIMIT) ---"
  
  # Find all audio files and their corresponding JSON files
  declare -A files_to_delete
  audio_files=()
  
  # Find all audio files with supported extensions
  while IFS= read -r -d $'\0' audio_file; do
    audio_files+=("$audio_file")
  done < <(find "$CHANNEL_DIR" -type f \( -iname "*.mp3" -o -iname "*.m4a" -o -iname "*.ogg" -o -iname "*.opus" -o -iname "*.wav" \) -print0)
  
  # Count total audio files
  total_files=${#audio_files[@]}
  echo "Found $total_files audio files for $CHANNEL_ID"
  
  # If we're under the limit, nothing to do
  if [[ "$total_files" -le "$LIMIT" ]]; then
    echo "No deletion needed (under limit)"
    continue
  fi
  
  # Calculate how many files to delete
  files_to_delete_count=$((total_files - LIMIT))
  echo "Need to delete $files_to_delete_count oldest files"
  
  # Create an array to hold file paths and their dates
  declare -a file_dates
  
  # Process each audio file
  for audio_file in "${audio_files[@]}"; do
    json_file="${audio_file}.json"
    
    # Try to get published date from JSON file
    if [[ -f "$json_file" ]]; then
      published_date=$(jq -r '.published' "$json_file" 2>/dev/null)
      
      if [[ "$published_date" != "null" && -n "$published_date" ]]; then
        # Convert ISO date to timestamp for comparison
        # Handle both formats: "2025-08-24T02:28:49" and "2025-08-24 02:28:49"
        if [[ "$published_date" == *"T"* ]]; then
          timestamp=$(date -d "${published_date/T/ }" +%s 2>/dev/null)
        else
          timestamp=$(date -d "$published_date" +%s 2>/dev/null)
        fi
        
        if [[ -n "$timestamp" ]]; then
          file_dates+=("$timestamp $audio_file")
          continue
        fi
      fi
    fi
    
    # Fall back to file modification time
    timestamp=$(stat -c %Y "$audio_file")
    file_dates+=("$timestamp $audio_file")
  done
  
  # Sort files by timestamp (oldest first)
  IFS=$'\n' sorted_files=($(sort -n <<< "${file_dates[*]}"))
  unset IFS
  
  # Collect files to delete (oldest files first)
  for ((i=0; i<files_to_delete_count; i++)); do
    file_to_delete=$(echo "${sorted_files[i]}" | cut -d' ' -f2-)
    files_to_delete["$file_to_delete"]=1
  done
  
  # Delete the selected files and their JSON
  deleted_count=0
  for audio_file in "${!files_to_delete[@]}"; do
    json_file="${audio_file}.json"
    
    echo "Deleting: $audio_file"
    rm -f "$audio_file"
    
    if [[ -f "$json_file" ]]; then
      echo "Deleting: $json_file"
      rm -f "$json_file"
    fi
    
    ((deleted_count++))
  done
  
  echo "Deleted $deleted_count files for $CHANNEL_ID"
done

echo "--- Kemono cleanup complete at $(date) ---"
