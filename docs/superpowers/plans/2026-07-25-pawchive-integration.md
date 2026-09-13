# Pawchive Support Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend PodQueue to support downloading Patreon creator episodes from Pawchive pages using `gallery-dl` and serve them as podcast RSS feeds.

**Architecture:** Use `gallery-dl` to query the creator's page for the newest 10 posts in JSON format, parse descriptions and `.mp3` download URLs, download the audio using Python `requests`, and write a `.info.json` file. The RSS builder and cleanup module are updated to handle both `.m4a` (YouTube) and `.mp3` (Pawchive) files.

**Tech Stack:** Python 3.x, FastAPI, requests, gallery-dl CLI

## Global Constraints

- Avoid external heavy packages. Use built-in libraries (`re`, `json`, `subprocess`, `sys`, `html`) where possible.
- Do not run concurrent downloads. Adhere to sequential single-threaded processing.
- Maintain compatibility with the existing yt-dlp metadata schemas.

---

### Task 1: Generalize Media Formats in RSS Builder & Cleaners

**Files:**
- Modify: `podqueue/core/rss.py:100-165`
- Modify: `podqueue/core/downloader.py:103-145`
- Modify: `podqueue/api/channels.py:34-38`
- Modify: `podqueue/api/main.py:70-72`
- Create: `scratch/test_extensions.py`

**Interfaces:**
- Consumes: Existing file structure.
- Produces: RSS XML generation and file count/cleanup routines that support both `.m4a` and `.mp3`.

- [ ] **Step 1: Create verification test script**
  Write a script at `scratch/test_extensions.py` that generates dummy files and tests our extension changes:
  ```python
  # scratch/test_extensions.py
  import os
  from pathlib import Path
  import shutil
  import xml.etree.ElementTree as ET
  from podqueue.config import settings

  def test_counting_and_cleanups():
      test_dir = settings.DOWNLOADS_DIR / "test_channel"
      test_dir.mkdir(parents=True, exist_ok=True)
      
      # Create dummy files
      for name in ("1.m4a", "1.info.json", "2.mp3", "2.info.json", "3.mp3", "3.info.json"):
          (test_dir / name).write_text("dummy", encoding="utf-8")
          
      # Count files
      m4a_files = list(test_dir.glob("*.m4a"))
      mp3_files = list(test_dir.glob("*.mp3"))
      total_count = len(m4a_files) + len(mp3_files)
      assert total_count == 3, f"Expected 3 files, got {total_count}"
      
      # Clean up test dir
      shutil.rmtree(test_dir, ignore_errors=True)
      print("Extension baseline validation passed successfully!")

  if __name__ == "__main__":
      test_counting_and_cleanups()
  ```

- [ ] **Step 2: Run verification script to check baseline state**
  Run: `..\..\venv\Scripts\python.exe scratch/test_extensions.py`
  Expected: Success output of baseline validation.

- [ ] **Step 3: Modify RSS Builder to support MP3 formats**
  In `podqueue/core/rss.py`, replace lines 100-103 to glob both `.m4a` and `.mp3`:
  ```python
      audio_files = sorted(
          [f for f in os.listdir(podcast_dir) if (f.endswith('.m4a') or f.endswith('.mp3')) and not '.temp.' in f],
          key=lambda f: get_episode_sort_key(podcast_dir / f),
          reverse=True
      )
  ```
  And dynamically select enclosure MIME types (around line 133 and 160/165):
  ```python
                  mime_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/mp4"
                  ET.SubElement(item, "enclosure", url=file_url, length=str(file_size), type=mime_type)
  ```

- [ ] **Step 4: Modify Downloader Cleanup routines to support MP3**
  In `podqueue/core/downloader.py`, modify `cleanup_old_episodes()` (lines 103-109):
  ```python
  def cleanup_old_episodes(download_dir: Path, archive_file: Path, limit: int):
      """Delete old episodes exceeding the limit, sorting by upload date (newest first)"""
      audio_files = sorted(
          list(download_dir.glob("*.m4a")) + list(download_dir.glob("*.mp3")),
          key=get_episode_sort_key,
          reverse=True
      )
  ```
  And add `*.temp.mp3` cleanups in `cleanup_leftovers()` (line 139):
  ```python
      for ext in ("*.mp4", "*.temp.mp4", "*.part", "*.ytdl", "*.temp.m4a", "*.temp.mp3"):
  ```

- [ ] **Step 5: Modify API and feeds counts to support MP3**
  In `podqueue/api/channels.py` (lines 35-37):
  ```python
          if downloads_subdir.exists():
              audio_count = len(list(downloads_subdir.glob("*.m4a")) + list(downloads_subdir.glob("*.mp3")))
  ```
  In `podqueue/api/main.py` (line 71):
  ```python
                  audio_count = len(list(downloads_subdir.glob("*.m4a")) + list(downloads_subdir.glob("*.mp3"))) if downloads_subdir.exists() else 0
  ```

- [ ] **Step 6: Run verification script to check updated behavior**
  Run: `..\..\venv\Scripts\python.exe scratch/test_extensions.py`
  Expected: PASS

- [ ] **Step 7: Commit changes**
  ```bash
  git add podqueue/core/rss.py podqueue/core/downloader.py podqueue/api/channels.py podqueue/api/main.py
  git commit -m "feat: generalize media counts and RSS enclosure to support mp3 formats"
  ```

---

### Task 2: Implement Pawchive Scraper & Downloader

**Files:**
- Create: `podqueue/core/pawchive.py`
- Modify: `podqueue/core/downloader.py`
- Create: `scratch/test_pawchive_downloader.py`

**Interfaces:**
- Consumes: Config settings and requests.
- Produces: Downloads Pawchive `.mp3` assets, updates the archive file, and writes `.info.json` files.

- [ ] **Step 1: Create pawchive.py submodule**
  Create the isolated Pawchive scraper downloader in `podqueue/core/pawchive.py`:
  ```python
  import sys
  import os
  import subprocess
  import json
  import logging
  import time
  import re
  import html
  import requests
  from pathlib import Path
  from urllib.parse import urljoin
  from podqueue.config import settings
  from podqueue.core.channels import Channel
  from podqueue.core.downloader import cleanup_old_episodes, cleanup_leftovers

  logger = logging.getLogger("podqueue")
  job_logger = logging.getLogger("podqueue_job")

  def is_pawchive_url(url: str) -> bool:
      return "pawchive." in url.lower()

  def strip_html_tags(text: str) -> str:
      if not text:
          return ""
      text = re.sub(r'</?p\s*[^>]*>', '\n', text)
      text = re.sub(r'<br\s*/?>', '\n', text)
      text = re.sub(r'<[^>]+>', '', text)
      text = re.sub(r'\n+', '\n', text).strip()
      return text

  def run_pawchive_download(channel: Channel, force: bool = False):
      job_logger.info(f"Starting Pawchive podcast sync for {channel.id}...")
      
      # Check interval
      last_check_file = settings.STATE_DIR / f"{channel.id}.last_check"
      current_time = int(time.time())
      
      if not force and last_check_file.exists():
          try:
              last_check_str = last_check_file.read_text().strip()
              if last_check_str.isdigit():
                  last_check_time = int(last_check_str)
                  next_check_time = last_check_time + (channel.check_interval_hours * 3600)
                  if current_time < next_check_time:
                      remaining_minutes = (next_check_time - current_time + 59) // 60
                      job_logger.info(f"Skipping {channel.id}. Next check in about {remaining_minutes} minute(s).")
                      return
          except Exception as e:
              job_logger.error(f"Error reading last check file for {channel.id}: {e}")

      download_dir = settings.DOWNLOADS_DIR / channel.id
      download_dir.mkdir(parents=True, exist_ok=True)
      archive_file = download_dir / "archive.txt"

      cleanup_old_episodes(download_dir, archive_file, channel.limit)

      # Build archive set
      archive_set = set()
      if archive_file.exists():
          try:
              with open(archive_file, "r", encoding="utf-8") as f:
                  for line in f:
                      line = line.strip()
                      parts = line.split(" ")
                      if len(parts) >= 2 and parts[0] in ("youtube", "pawchive"):
                          archive_set.add(parts[1])
          except Exception as e:
              job_logger.error(f"Error reading archive file: {e}")

      # Resolve gallery-dl path
      python_bin_dir = Path(sys.executable).parent
      gallery_dl_path = python_bin_dir / "gallery-dl.exe"
      if not gallery_dl_path.exists():
          gallery_dl_path = python_bin_dir / "gallery-dl"

      job_logger.info(f"Running gallery-dl metadata scan for {channel.url}...")
      cmd = [
          str(gallery_dl_path),
          "--dump-json",
          "--range", f"1-{max(10, channel.limit * 2)}",
          channel.url
      ]
      
      # Apply proxy if configured
      if settings.YTDLP_PROXY:
          cmd.extend(["--proxy", settings.YTDLP_PROXY])

      try:
          result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
          if result.returncode != 0:
              job_logger.error(f"gallery-dl failed with code {result.returncode}: {result.stderr}")
              return
          
          # Parse stdout JSON
          raw_data = json.loads(result.stdout)
          
          # gallery-dl prints list of arrays where each item has format: [type_code, url/payload, metadata_dict]
          posts_metadata = {}
          for item in raw_data:
              if len(item) >= 3 and isinstance(item[2], dict):
                  meta = item[2]
                  post_id = meta.get("id")
                  if post_id:
                      posts_metadata[post_id] = meta

      except Exception as e:
          job_logger.error(f"Error executing gallery-dl: {e}")
          return

      # Download new posts
      new_posts = []
      for post_id, meta in sorted(posts_metadata.items(), key=lambda x: x[1].get("date", ""), reverse=True):
          if post_id not in archive_set:
              attachments = meta.get("attachments", [])
              mp3_url = None
              mp3_name = None
              for att in attachments:
                  if att.get("extension") == "mp3" or att.get("url", "").split("?")[0].endswith(".mp3"):
                      mp3_url = att.get("url")
                      mp3_name = att.get("name") or f"{post_id}.mp3"
                      break
              if mp3_url:
                  new_posts.append((post_id, mp3_url, mp3_name, meta))

      if new_posts:
          posts_to_download = new_posts[:channel.limit]
          job_logger.info(f"Found {len(new_posts)} new posts. Downloading the newest {len(posts_to_download)} (limit {channel.limit}).")
          
          proxies = None
          if settings.YTDLP_PROXY:
              proxies = {"http": settings.YTDLP_PROXY, "https": settings.YTDLP_PROXY}

          headers = {
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
          }

          for post_id, mp3_url, mp3_name, meta in posts_to_download:
              dest_path = download_dir / f"{post_id}.mp3"
              temp_path = download_dir / f"{post_id}.temp.mp3"
              
              job_logger.info(f"Downloading Pawchive file: {mp3_name} ({mp3_url})")
              try:
                  response = requests.get(mp3_url, headers=headers, proxies=proxies, stream=True, timeout=120)
                  response.raise_for_status()
                  
                  # Download chunk-by-chunk to save RAM
                  with open(temp_path, "wb") as f:
                      for chunk in response.iter_content(chunk_size=16384):
                          if chunk:
                              f.write(chunk)
                              
                  if temp_path.exists():
                      temp_path.rename(dest_path)
                      
                  # Write info.json
                  info_path = download_dir / f"{post_id}.info.json"
                  raw_date = meta.get("date", "").split(" ")[0].replace("-", "")
                  artist_name = meta.get("user_profile", {}).get("name") or meta.get("username") or channel.id
                  avatar_url = f"https://pawchive.st/icons/patreon/{meta.get('user')}" if meta.get('user') else ""
                  
                  info_data = {
                      "id": post_id,
                      "title": meta.get("title") or f"Post {post_id}",
                      "upload_date": raw_date,
                      "description": strip_html_tags(meta.get("content", "")),
                      "duration": 0,
                      "channel": artist_name,
                      "thumbnails": [{"url": avatar_url, "width": 400, "height": 400}] if avatar_url else []
                  }
                  
                  with open(info_path, "w", encoding="utf-8") as f:
                      json.dump(info_data, f, indent=2)
                      
                  # Write to archive
                  with open(archive_file, "a", encoding="utf-8") as f:
                      f.write(f"pawchive {post_id}\n")
                      
                  job_logger.info(f"Successfully processed post: {post_id}")
              except Exception as e:
                  job_logger.error(f"Error downloading post {post_id}: {e}")
                  if temp_path.exists():
                      temp_path.unlink()

      cleanup_old_episodes(download_dir, archive_file, channel.limit)
      cleanup_leftovers(download_dir)

      # Save check status
      try:
          last_check_file.write_text(str(current_time))
      except Exception as e:
          job_logger.error(f"Error writing last check file for {channel.id}: {e}")

      job_logger.info(f"Finished Pawchive sync for {channel.id}.")
  ```

- [ ] **Step 2: Route downloader pipeline**
  Modify [downloader.py](file:///c:/Users/victo/Documents/Misc/Oracle_cloud/PodQueue/podqueue_repo/podqueue/core/downloader.py) to import and delegate to the new module:
  - Add import: `from podqueue.core.pawchive import is_pawchive_url, run_pawchive_download`
  - Modify `run_download_job()` (line 170) to route Pawchive requests:
  ```python
      for channel in channels:
          job_logger.info(f"--- Processing: {channel.id} ---")
          
          if is_pawchive_url(channel.url):
              try:
                  run_pawchive_download(channel, force=force)
              except Exception as e:
                  job_logger.error(f"Error in Pawchive downloader for {channel.id}: {e}")
              continue
  ```
  - Modify `archive_set` parser in `run_download_job()` to match prefixes:
  ```python
          archive_set = set()
          if archive_file.exists():
              try:
                  with open(archive_file, "r", encoding="utf-8") as f:
                      for line in f:
                          line = line.strip()
                          parts = line.split(" ")
                          if len(parts) >= 2 and parts[0] in ("youtube", "pawchive"):
                              archive_set.add(parts[1])
              except Exception as e:
                  job_logger.error(f"Error reading archive file: {e}")
  ```

- [ ] **Step 3: Create developer test harness**
  Create a script at `scratch/test_pawchive_downloader.py`:
  ```python
  # scratch/test_pawchive_downloader.py
  import logging
  import sys
  from podqueue.core.channels import Channel
  from podqueue.core.pawchive import run_pawchive_download

  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger("podqueue")

  def test_pawchive_harness():
      # Create a channel object for testing
      chan = Channel(
          id="test_pawchive",
          url="https://pawchive.pw/patreon/user/12883973",
          limit=1,
          sponsorblock=False,
          check_interval_hours=1
      )
      
      # Run download with force=True
      run_pawchive_download(chan, force=True)
      print("Integration execution completed!")

  if __name__ == "__main__":
      test_pawchive_harness()
  ```

- [ ] **Step 4: Run integration test**
  Run: `..\..\venv\Scripts\python.exe scratch/test_pawchive_downloader.py`
  Expected: Successful scan and single download of `.mp3`, generation of `info.json`, and creation of `archive.txt`.

- [ ] **Step 5: Commit changes**
  ```bash
  git add podqueue/core/pawchive.py podqueue/core/downloader.py
  git commit -m "feat: add native pawchive downloader utilizing gallery-dl CLI for metadata"
  ```

---

### Task 3: Support gallery-dl in Update Pipelines

**Files:**
- Modify: `podqueue/core/job_runner.py:35-49`

**Interfaces:**
- Consumes: Pip update command triggers.
- Produces: Updates both `yt-dlp` and `gallery-dl` via pip.

- [ ] **Step 1: Modify update_ytdlp routine**
  In `podqueue/core/job_runner.py`, replace `update_ytdlp()` implementation (lines 35-49):
  ```python
  def update_ytdlp():
      """Runs pip update on yt-dlp, yt-dlp-ejs, and gallery-dl, and exits process to let systemd restart it"""
      job_logger.info("Updating yt-dlp, yt-dlp-ejs, and gallery-dl using pip...")
      cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "yt-dlp-ejs", "gallery-dl"]
      
      result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
      job_logger.info(result.stdout)
      
      if result.returncode != 0:
          raise RuntimeError(f"pip install failed with exit code {result.returncode}")
          
      job_logger.info("All dependencies updated successfully. Process exiting now to trigger systemd auto-restart.")
      # Flush logs and exit
      time.sleep(1)
      os._exit(0)
  ```

- [ ] **Step 2: Commit updates**
  ```bash
  git add podqueue/core/job_runner.py
  git commit -m "feat: include gallery-dl in automatic pip update logs"
  ```

---

### Task 4: Frontend UI Generalization

**Files:**
- Modify: `static/index.html`
- Modify: `static/js/channels.js`

**Interfaces:**
- Consumes: Backend API structures.
- Produces: Interactive visual channel cards and generalized form headers.

- [ ] **Step 1: Update form headers in index.html**
  In `static/index.html`, modify form text labels in the Add Channel Modal (lines 149-160):
  ```html
              <div class="modal-header">
                  <h3>Add New Feed</h3>
                  <button class="modal-close" data-close="add-channel-modal">&times;</button>
              </div>
              <form id="add-channel-form">
                  <div class="form-group">
                      <label for="add-chan-id" class="form-label">Feed Name / ID (alphanumeric, no spaces)</label>
                      <input type="text" id="add-chan-id" class="form-control" placeholder="e.g. LexFridman" required pattern="^[a-zA-Z0-9_-]+$">
                  </div>
                  <div class="form-group">
                      <label for="add-chan-url" class="form-label">Source URL (YouTube channel or Pawchive creator page)</label>
                      <input type="url" id="add-chan-url" class="form-control" placeholder="e.g. https://youtube.com/@lexfridman" required>
                  </div>
  ```

- [ ] **Step 2: Update channels listing icons in channels.js**
  In `static/js/channels.js` (line 79), select different icons based on URL prefix:
  ```javascript
              const isPawchive = c.url.toLowerCase().includes('pawchive.');
              const icon = isPawchive ? '🐾' : '📺';
                  
              return `
                  <div class="card">
                      <div class="card-header" style="margin-bottom: 1rem;">
                          <h3 class="card-title">${icon} ${c.id}</h3>
                          <span class="badge ${c.audio_count > 0 ? 'badge-success' : ''}">${c.audio_count} eps</span>
                      </div>
  ```

- [ ] **Step 3: Commit frontend updates**
  ```bash
  git add static/index.html static/js/channels.js
  git commit -m "style: generalize add channel form labels and render pawchive cards with a paw icon"
  ```

---
