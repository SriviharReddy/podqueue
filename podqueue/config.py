import os
from pathlib import Path
from dotenv import load_dotenv

# Root dir is the repository root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env file
env_path = ROOT_DIR / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    def __init__(self):
        self.BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
        self.SESSION_SECRET = os.getenv("SESSION_SECRET", "changeme")
        
        # Resolve paths relative to ROOT_DIR if they are relative
        data_dir_raw = os.getenv("DATA_DIR", "./data")
        self.DATA_DIR = Path(data_dir_raw) if Path(data_dir_raw).is_absolute() else (ROOT_DIR / data_dir_raw).resolve()
        
        cookies_file_raw = os.getenv("COOKIES_FILE", "./cookies.txt")
        self.COOKIES_FILE = Path(cookies_file_raw) if Path(cookies_file_raw).is_absolute() else (ROOT_DIR / cookies_file_raw).resolve()
        
        self.PORT = int(os.getenv("PORT", "8000"))
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))
        # Optional proxy for yt-dlp (e.g. socks5://127.0.0.1:40000 for Cloudflare Warp)
        self.YTDLP_PROXY = os.getenv("YTDLP_PROXY", "").strip() or None
        
        # Deduced paths inside DATA_DIR
        self.DOWNLOADS_DIR = self.DATA_DIR / "downloads"
        self.FEEDS_DIR = self.DATA_DIR / "feeds"
        self.ARTWORK_DIR = self.DATA_DIR / "artwork"
        self.LOGS_DIR = self.DATA_DIR / "logs"
        self.STATE_DIR = self.DATA_DIR / "state" / "channel_checks"
        self.LOCK_FILE = self.DATA_DIR / "podqueue.lock"
        self.CHANNELS_FILE = self.DATA_DIR / "channels.json"
        
        # Ensure dirs exist
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.FEEDS_DIR.mkdir(parents=True, exist_ok=True)
        self.ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.STATE_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
