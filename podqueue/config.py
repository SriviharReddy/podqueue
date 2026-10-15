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

        # --- Castria ad-skip source -------------------------------------
        # Channels whose url is "castria:<subscriptionId|feedUrl>" are populated
        # from https://castria.app and have their ads removed before publishing.
        self.CASTRIA_BASE_URL = os.getenv("CASTRIA_BASE_URL", "https://castria.app").rstrip("/")
        self.CASTRIA_EMAIL = os.getenv("CASTRIA_EMAIL", "").strip()
        self.CASTRIA_PASSWORD = os.getenv("CASTRIA_PASSWORD", "")
        # Sent as X-App-Version; the server gates some endpoints on this.
        self.CASTRIA_APP_VERSION = os.getenv("CASTRIA_APP_VERSION", "2272").strip()
        # Node runtime + vendored engine (see tools/castria_align).
        self.CASTRIA_NODE_BIN = os.getenv("CASTRIA_NODE_BIN", "node").strip() or "node"
        self.CASTRIA_ALIGN_TOOL = ROOT_DIR / "tools" / "castria_align" / "align.mjs"
        self.CASTRIA_ALIGN_TIMEOUT_SECONDS = int(os.getenv("CASTRIA_ALIGN_TIMEOUT_SECONDS", "3600"))
        self.CASTRIA_ALIGN_ENABLED = os.getenv("CASTRIA_ALIGN_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
        # Castria's engine refuses to align more than 7200s (2h) of decoded audio
        # in one pass (its internal "bug-543" guard), so episodes longer than
        # this are not worth a full decode - the aligner is skipped for them.
        self.CASTRIA_MAX_ALIGN_DURATION_SECONDS = int(os.getenv("CASTRIA_MAX_ALIGN_DURATION_SECONDS", "7200"))
        # When alignment is impossible, optionally fall back to the server's raw
        # adSegments. These are timed against Castria's copy, NOT ours, so they
        # can be wrong under dynamic ad insertion - hence off by default.
        self.CASTRIA_ALLOW_TIMESTAMP_FALLBACK = os.getenv("CASTRIA_ALLOW_TIMESTAMP_FALLBACK", "false").strip().lower() in ("1", "true", "yes", "on")
        
        # Deduced paths inside DATA_DIR
        self.DOWNLOADS_DIR = self.DATA_DIR / "downloads"
        self.FEEDS_DIR = self.DATA_DIR / "feeds"
        self.ARTWORK_DIR = self.DATA_DIR / "artwork"
        self.LOGS_DIR = self.DATA_DIR / "logs"
        self.STATE_DIR = self.DATA_DIR / "state" / "channel_checks"
        self.LOCK_FILE = self.DATA_DIR / "podqueue.lock"
        self.CHANNELS_FILE = self.DATA_DIR / "channels.json"
        
        # Ensure dirs exist (best-effort — don't crash on import if no write permission)
        for d in (self.DOWNLOADS_DIR, self.FEEDS_DIR, self.ARTWORK_DIR, self.LOGS_DIR, self.STATE_DIR):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

settings = Settings()
