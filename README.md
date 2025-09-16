# YouTube to Podcast Service (Ubuntu)

This service automates the process of downloading audio from YouTube channels and playlists and converting them into a podcast-style RSS feed.

This guide is tailored for an Ubuntu environment.

## Prerequisites (Ubuntu)

Before you begin, ensure you have the following software installed on your system. You can install them using `apt`:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip jq
```

Next, install or update `yt-dlp`:

```bash
sudo pip install -U yt-dlp
```

## Setup

1.  **Create a Python Virtual Environment:**

    It's best practice to use a virtual environment to manage Python dependencies.

    ```bash
    python3 -m venv venv
    ```

2.  **Activate the Virtual Environment:**

    ```bash
    source venv/bin/activate
    ```

3.  **Install Python Dependencies:**

    Install the required Python packages from the `scripts/requirements.txt` file.

    ```bash
    pip install -r scripts/requirements.txt
    ```

## Configuration

The `scripts/channels.json` file is where you define the YouTube channels and playlists to process.

Each entry is an object with the following keys:

-   `id`: A unique identifier for the channel. This is used for naming directories and files.
-   `url`: The URL of the YouTube channel or playlist.
-   `limit`: The maximum number of recent videos to keep for this feed.

**Example `channels.json`:**

```json
[
  {
    "id": "SkillUpYT",
    "url": "https://www.youtube.com/channel/UCZ7AeeVbyslLM_8-nVy2B8Q",
    "limit": 12
  },
  {
    "id": "TheVergeCast",
    "url": "https://youtube.com/playlist?list=PL39u5ZEfYDEO5PaNRWyqloGY6zzJ1fjBa&si=qNN0R_3Bwylkcbje",
    "limit": 6
  }
]
```

## Usage

The service has two main scripts that should be run in order.

1.  **Download Audio (`downloader.sh`):**

    This script reads `channels.json` and downloads the audio from the specified sources into the `downloads` directory.

    ```bash
    bash scripts/downloader.sh
    ```

2.  **Generate RSS Feeds (`rss_generator.py`):**

    After downloading, this script generates the RSS feeds and places them in the `feeds` directory.

    ```bash
    python3 scripts/rss_generator.py
    ```

    *(Ensure your virtual environment is activated before running.)*

### Scheduling with Cron

To automate the process, you can schedule these scripts to run periodically using `cron`.

1.  Open your crontab for editing: `crontab -e`
2.  Add the following lines to run the downloader every hour and the RSS generator every two hours:

    ```crontab
    0 * * * * /bin/bash /path/to/your/my_podcast_service/scripts/downloader.sh
    0 */2 * * * /path/to/your/my_podcast_service/venv/bin/python /path/to/your/my_podcast_service/scripts/rss_generator.py
    ```

    *Remember to replace `/path/to/your/my_podcast_service` with the actual absolute path to your project directory.*

## Managing Podcasts

### Deleting a Podcast

The `delete_podcast.sh` script allows you to remove a podcast and all its associated files.

**Usage:**

```bash
bash scripts/delete_podcast.sh <podcast_id>
```

-   `<podcast_id>`: The `id` of the podcast you want to delete (as defined in `channels.json`).

The script will delete the downloads, feed file, and artwork. It will then ask for confirmation before removing the podcast's entry from `channels.json`.

## The "Kemono" Service

You will notice a set of scripts with `_kemono` in their names (`downloader_kemono.sh`, `rss_generator_kemono.py`, `delete_podcast_kemono.sh`) and a `channels_kemono.json` file.

This is a parallel service that functions identically to the YouTube service but is configured to work with a different source. It uses `channels_kemono.json` for its list of sources and operates independently from the main YouTube podcast service.

## Serving the Podcast

To listen to your podcasts, you need a web server to make the `feeds`, `downloads`, and `artwork` directories accessible over the network.

Here is a sample Nginx configuration that you can adapt. Create a new file in `/etc/nginx/sites-available/`, for example, `podcast.conf`:

```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    root /path/to/your/my_podcast_service;

    location /feeds {
        alias /path/to/your/my_podcast_service/feeds;
        try_files $uri $uri/ =404;
    }

    location /downloads {
        alias /path/to/your/my_podcast_service/downloads;
        try_files $uri $uri/ =404;
    }

    location /artwork {
        alias /path/to/your/my_podcast_service/artwork;
        try_files $uri $uri/ =404;
    }
}
```

-   Replace `your_domain_or_ip` with your server's public IP address or domain name.
-   Replace `/path/to/your/my_podcast_service` with the absolute path to your project directory.

Enable the site by creating a symbolic link and then restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/podcast.conf /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

You can then access your RSS feeds at `http://your_domain_or_ip/feeds/<podcast_id>.xml`.