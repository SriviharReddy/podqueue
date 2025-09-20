# PodQueue

This project provides a self-hosted service to convert YouTube channels into podcast feeds. It automatically downloads the latest videos from specified YouTube channels, converts them to audio, and generates RSS feeds that can be used with any podcast client.

## How it Works

The service consists of two main components:

1.  **Downloader (`downloader.sh`)**: A shell script that uses `yt-dlp` to download the latest videos from the YouTube channels specified in `scripts/channels.json`. It converts the videos to M4A audio files and stores them in the `downloads` directory.
2.  **RSS Generator (`rss_generator.py`)**: A Python script that generates RSS feeds for each channel. It reads the downloaded audio files and their metadata to create the feeds in the `feeds` directory.

The service is designed to be run on a server and can be automated with cron jobs.

## Web UI

This project also includes a Streamlit-based web interface (`webui/`) for easier management of your podcast channels and downloads.

## Setup

1.  **Prerequisites**:
    *   [yt-dlp](https://github.com/yt-dlp/yt-dlp)
    *   [jq](https://stedolan.github.io/jq/)
    *   Python 3
    *   `pip`

2.  **Clone the repository**:
    ```bash
    git clone https://github.com/SriviharReddy/podqueue.git
    cd podqueue
    ```

3.  **Install Python dependencies**:
    ```bash
    pip install -r scripts/requirements.txt
    ```

4.  **Configure the channels**:
    *   Copy `scripts/channels.json.example` to `scripts/channels.json`.
    *   Edit `scripts/channels.json` to add the YouTube channels you want to follow. Each entry should have an `id`, `url`, and `limit` (the maximum number of episodes to keep).
    *   You can add playlists directly, but for channels with @username URLs (e.g., `https://www.youtube.com/@channelname`), they will be automatically converted to channel ID URLs when using the Web UI.
    *   The `url` in `channels.json` should be in the format `https://www.youtube.com/channel/CHANNEL_ID` for direct channel URLs.

5.  **Set up the base directory**:
    *   The scripts expect to be run from a specific base directory. You will need to edit `downloader.sh` and `rss_generator.py` to set the `BASE_DIR` variable to the absolute path of the project directory.

6.  **(Optional) Cookies**:
    *   If you need to download videos that require a login, you can provide a `cookies.txt` file in the root of the project. The `downloader.sh` script will automatically use it.

## Web UI Setup

1. Navigate to the webui directory:
   ```bash
   cd webui
   ```

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the Streamlit app:
   ```bash
   streamlit run app.py
   ```

4. Access the web interface at `http://localhost:8501`

## Usage

1.  **Run the downloader**:
    ```bash
    ./scripts/downloader.sh
    ```
    This will download the latest videos from the configured channels.

2.  **Run the RSS generator**:
    ```bash
    python3 scripts/rss_generator.py
    ```
    This will generate the RSS feeds in the `feeds` directory.

3.  **Serve the feeds**:
    *   The generated feeds are located in the `feeds` directory. You will need to serve this directory with a web server (e.g., Nginx, Apache) to access them from your podcast client. The `BASE_URL` in `rss_generator.py` should be set to the public URL of your server.

## Automation

You can automate the process of downloading and generating feeds using cron jobs. For example, to run the downloader every hour and the RSS generator every two hours, you could add the following to your crontab:

```
0 * * * * /path/to/your/project/scripts/downloader.sh
0 */2 * * * /path/to/your/project/scripts/rss_generator.py
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.