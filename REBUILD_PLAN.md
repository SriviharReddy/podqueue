# PodQueue — Proper Rebuild Plan

## Background

PodQueue is a self-hosted service that turns YouTube channels/playlists into podcast RSS feeds.
The current version is a vibecoded mess:

- 649-line monolithic Streamlit `app.py` with hardcoded absolute paths
- Business logic, UI, subprocess management, and JSON I/O all tangled together
- `downloader.sh` is bash (requires `jq`, not portable, no structured error output, untestable)
- Streamlit is the wrong tool for an always-on control panel — it re-runs the entire script
  on every interaction, making real-time log streaming a threading hack with `###DONE###` sentinels
- No config system — `BASE_DIR`, `BASE_URL` hardcoded in multiple files
- No tests anywhere

**Kemono support is excluded** from this rebuild (site is down; can be re-added later as a plugin).

**Fresh instance deployment** — no migration of existing data needed.

**Deployment target: Oracle Cloud Always Free AMD** — `VM.Standard.E2.1.Micro`: 1/8 OCPU (throttled), 1 GB RAM.
Every architectural decision should minimise CPU spikes and heap pressure.

---

## Decisions

| Concern | Decision | Reason |
|---|---|---|
| Backend framework | **FastAPI** | Async, proper HTTP API, native SSE, auto OpenAPI docs |
| Background jobs | **APScheduler** (in-process) | Replaces cron; jobs controllable via API; systemd keeps server alive |
| Downloader | **yt-dlp Python API** | No bash/jq dependency; structured errors; same functionality |
| yt-dlp execution | **`asyncio.to_thread()`** with **`max_workers=1`** | yt-dlp + ffmpeg are synchronous and CPU-heavy. Only one job ever runs at a time (filelock), so a single worker thread is sufficient. Set via `loop.set_default_executor(ThreadPoolExecutor(max_workers=1))` at startup. Keeps RAM bounded on 1 GB. |
| ffmpeg CPU limiting | **`postprocessor_args={'ffmpeg': ['-threads', '1']}`** | ffmpeg defaults to using all CPU threads; on 1/8 OCPU this pins the machine and starves the FastAPI server. Force single-threaded ffmpeg in yt-dlp options. |
| yt-dlp playlist scan | **Flat extraction pre-pass** | Use `extract_flat=True` first to get only video IDs, cross-reference against `archive.txt` in Python, then fetch full metadata only for genuinely new entries. Saves significant RAM and network for large playlists (yt-dlp's `--download-archive` still fetches full metadata before skipping). |
| Post-job cleanup | **`gc.collect()`** | Call explicitly at the end of `run_download()` and `run_rss()`. yt-dlp and info JSON parsing leave large temporary object graphs; CPython’s GC won’t cycle immediately without a nudge. Critical on 1 GB RAM. |
| RSS generator | Refactored as Python module | Already good logic, just needs cleanup |
| Frontend | **Vanilla HTML/CSS/JS, system fonts** | No build step; no Google Fonts external request; system font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`) is instant and looks fine |
| Auth | **Password in `.env`** | Goal is only to deter casual stumble-uponers. Single `ADMIN_PASSWORD` env var, checked with `secrets.compare_digest()`. No username field — there is only one user. Session cookie set on success. |
| Config | **`python-dotenv` + `os.getenv()`** | 6 env vars don’t need pydantic-settings. `python-dotenv` is tiny; reads `.env` on startup; vars accessed via `os.getenv()` with defaults. Removes a heavy import. |
| File serving | **FastAPI StaticFiles** | Serve `downloads/`, `feeds/`, `artwork/`; Starlette's StaticFiles natively supports HTTP Range requests (required by podcast players for scrubbing). Mounted **without auth** so podcast clients can access feeds. |
| Job concurrency | **`filelock.FileLock`** | File-based lock on `data/podqueue.lock`; safe across processes. Enforces sequential per-channel processing — no parallel ffmpeg processes that would OOM on 1 GB RAM |
| Scheduling | **APScheduler `BackgroundScheduler`** | Explicitly use the lightweight `BackgroundScheduler` (one daemon thread), not the heavier async variant. Two jobs: hourly download→rss, daily yt-dlp update. |
| FastAPI docs | **Disabled** (`docs_url=None`) | `app = FastAPI(docs_url=None, redoc_url=None)`. Saves RAM from schema generation; not useful in production. |
| Uvicorn workers | **`--workers 1`** | Explicitly in the systemd `ExecStart`. Single process is required for the in-process filelock and `asyncio.RLock` to be effective. |
| Systemd priority | **`Nice=19`, `IOSchedulingClass=idle`** | Runs the service at the lowest CPU and I/O priority. SSH, cron, and other interactive processes remain responsive during downloads. `Restart=always`, `RestartSec=1s` for auto-restart after yt-dlp update. |
| SSE log source | **Dedicated job log file** | Job output written to `data/logs/last_job.log` (separate from app log). Tailed with `asyncio.sleep()`. SSE sends byte offset as event `id:`; reconnect seeks to that offset — no duplicate lines. **Rotated at 500 KB, 2 backups** to protect disk space. |
| channels.json safety | **`asyncio.RLock`** | All channel CRUD serialised through an in-process async reentrant lock. Separate from the job filelock. |
| App log rotation | **1 MB, 3 backups** | `RotatingFileHandler` with small limits. On a small-disk free-tier VM, uncapped logs will fill the volume. |
| yt-dlp post-update | **Graceful `sys.exit(0)`** | After a successful `update-ytdlp` job, the process exits; systemd (`Restart=always`, `RestartSec=1s`) immediately restarts it, loading the new version from disk — avoids stale in-memory module cache |
| Path resolution | **Anchor to `__file__`** | `config.py` resolves all default paths relative to the package root (`Path(__file__).resolve().parent.parent`). Relative `.env` values are resolved against this anchor, preventing breakage when systemd starts from a different CWD |
| Auth boundary | **Explicit public/private split** | `/feeds/`, `/downloads/`, `/artwork/` → no auth (podcast players). `/api/channels`, `/api/jobs/*` → session cookie required |
| Kemono | **Excluded** | Site is down; add back later as separate module |

---

## New Directory Structure

```
podqueue/
├── podqueue/               # Python package
│   ├── __init__.py
│   ├── config.py           # Loads .env, exposes typed Settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI app (docs disabled) + StaticFiles mounts + GET /api/feeds
│   │   ├── auth.py         # POST /api/login (password only), /api/logout, GET /api/me
│   │   ├── channels.py     # CRUD /api/channels
│   │   └── jobs.py         # POST /api/jobs/download|rss|update-ytdlp, GET /api/jobs/status|logs/stream
│   ├── core/
│   │   ├── __init__.py
│   │   ├── channels.py     # Channel Pydantic model + asyncio.RLock for JSON read/write
│   │   ├── downloader.py   # yt-dlp Python API wrapper; YTDLPLogger + progress_hook; SponsorBlock via postprocessors
│   │   ├── rss.py          # RSS generation (refactored from rss_generator.py)
│   │   ├── job_runner.py   # filelock + job state + run_download/run_rss/run_update_ytdlp coroutines
│   │   └── scheduler.py    # APScheduler BackgroundScheduler; calls job_runner
│   └── utils/
│       ├── __init__.py
│       ├── media.py        # format_duration, rfc2822_format, get_best_thumbnail,
│       │                   # sanitize_title, parse_chapters_from_description
│       └── log_config.py   # RotatingFileHandler setup (app log + job log, with size limits)
│
├── static/                 # Frontend (served by FastAPI at /)
│   ├── index.html          # Single-page app shell, three sections: Channels / Jobs / Settings
│   ├── css/
│   │   └── app.css         # Dark mode design system, CSS custom properties
│   └── js/
│       ├── api.js          # Thin fetch wrapper — all API calls go through here
│       ├── app.js          # Router: shows/hides sections; auth check on load
│       ├── channels.js     # Channel list, add/edit/delete modals
│       └── jobs.js         # Trigger buttons, SSE live log viewer
│
├── data/                   # Runtime data (gitignored)
│   ├── channels.json
│   ├── downloads/          # Audio files, organized by channel ID
│   ├── feeds/              # Generated RSS XML files
│   ├── artwork/            # Cached channel artwork
│   ├── logs/               # Rotating log files
│   └── state/              # Per-channel last-check timestamps
│       └── channel_checks/
│
├── cookies.txt             # YouTube auth cookies (gitignored)
├── .env.example            # Template — all config vars documented
├── .env                    # Actual config (gitignored)
├── requirements.txt
├── setup.sh                # Creates venv, .env, systemd unit
└── README.md
```

---

## API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/login` | `{password}` — no username; sets session cookie on match |
| `POST` | `/api/logout` | Clears session cookie |
| `GET` | `/api/me` | Returns 200 if session valid, 401 otherwise |

### Channels
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/channels` | List all channels |
| `POST` | `/api/channels` | Add channel (auto-converts @username URLs) |
| `PUT` | `/api/channels/{id}` | Update limit / sponsorblock / check_interval_hours |
| `DELETE` | `/api/channels/{id}` | Remove channel + delete its downloads/, feed XML, state file |

### Jobs  *(auth required)*
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jobs/download` | Trigger a downloader run (acquires filelock, runs in thread pool) |
| `POST` | `/api/jobs/rss` | Trigger RSS generation (acquires filelock, runs in thread pool) |
| `POST` | `/api/jobs/update-ytdlp` | Run `pip install -U yt-dlp yt_dlp_ejs` in a thread pool |
| `GET` | `/api/jobs/status` | `{running: bool, current_job: str, last_run: datetime, last_exit_code: int}` |
| `GET` | `/api/jobs/logs/stream` | SSE — tails `data/logs/last_job.log`; reconnect-safe; uses `asyncio.sleep()` in tail loop |

### Feeds & Static  *(no auth — public)*
> Podcast players cannot send session cookies. These paths must be mounted **outside** any auth middleware.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/feeds` | ✅ required | List generated RSS feeds with metadata |
| `GET` | `/feeds/{name}.xml` | ❌ public | Served as static file |
| `GET` | `/downloads/{id}/{file}` | ❌ public | Served as static file (Range requests supported) |
| `GET` | `/artwork/{file}` | ❌ public | Served as static file |

---

## channels.json Schema (unchanged)

```json
[
  {
    "id": "ChannelName",
    "url": "https://www.youtube.com/channel/UC...",
    "limit": 5,
    "sponsorblock": false,
    "check_interval_hours": 1
  }
]
```

---

## .env Variables

```ini
# Required
BASE_URL=http://YOUR_SERVER_IP          # Public URL used in RSS feed links
ADMIN_PASSWORD=changeme                 # Plain text — just keep strangers out
SESSION_SECRET=changeme                 # Signs session cookie — change this

# Optional — defaults shown
DATA_DIR=./data                         # Where channels.json, downloads/, feeds/ etc. live
COOKIES_FILE=./cookies.txt              # YouTube cookies
PORT=8000                               # FastAPI listen port
HOST=0.0.0.0                           # FastAPI listen host
LOG_LEVEL=INFO
SCHEDULE_INTERVAL_MINUTES=60           # How often the scheduled job runs
```

---

## Frontend Design (Vanilla JS — No Framework)

The JS is split into small, focused modules. No bundler needed — `<script type="module">` handles
imports natively in modern browsers.

```
static/js/
├── api.js          # fetch('/api/...') wrappers, handles 401 redirect to login
├── app.js          # init(): auth check -> show app or login form
│                   # router: hashchange -> show correct section
├── channels.js     # renderChannels(), openAddModal(), openEditModal(), deleteChannel()
└── jobs.js         # triggerDownload(), triggerRSS(), startLogStream() [EventSource SSE]
```

Design system — CSS custom properties in `:root`, no utility classes:
- Dark background (`#0d1117`), card surface (`#161b22`), border (`#30363d`)
- Accent: `#58a6ff` (blue) for actions, `#3fb950` (green) for success, `#f85149` (red) for danger
- Typography: **system font stack** (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`) — no external HTTP request, instant render
- Components: `.card`, `.btn`, `.btn-danger`, `.badge`, `.modal`, `.log-viewer`

---

## Functionality Preserved

All existing features are kept:

| Feature | How |
|---|---|
| YouTube @username -> channel ID conversion | downloader.py using yt-dlp Python API |
| Per-channel episode limits + auto-cleanup | downloader.py (before and after download) |
| Per-channel check interval (skip if not due) | downloader.py reads/writes state/channel_checks/ |
| SponsorBlock removal | downloader.py passes sponsorblock-remove option to yt-dlp |
| Artwork caching | rss.py -> data/artwork/ |
| Chapter parsing from description | utils/media.py -> rss.py |
| Episode thumbnails in RSS | rss.py |
| YouTube cookie auth | COOKIES_FILE env var, passed to yt-dlp |
| Archive file (skip already-downloaded) | data/downloads/{id}/archive.txt |
| .m4a audio format | yt-dlp format selection in downloader.py |
| RSS feeds compatible with Pocket Casts, Overcast | rss.py — iTunes namespace preserved |

---

## Implementation Phases

### Phase 1 — Foundation
1. `podqueue/config.py` + `.env.example`
2. `podqueue/utils/media.py` — all shared helpers
3. `podqueue/utils/logging.py` — rotating log setup with per-job log files

### Phase 2 — Core Business Logic
4. `podqueue/core/channels.py` — Channel Pydantic model + `asyncio.RLock` for safe JSON read/write
5. `podqueue/core/downloader.py` — yt-dlp wrapper via `asyncio.to_thread()`; `YTDLPLogger` + `progress_hook`; SponsorBlock via `postprocessors` list; writes to job log file
6. `podqueue/core/rss.py` — refactored RSS generator; run via `asyncio.to_thread()`; writes to same job log
7. `podqueue/core/job_runner.py` — `filelock.FileLock`; job state (`running`, `current_job`, `last_run`, `last_exit_code`); `run_download()`, `run_rss()`, `run_update_ytdlp()` (last one calls `sys.exit(0)` on success)
8. `podqueue/core/scheduler.py` — `APScheduler.BackgroundScheduler`; hourly download→rss job + daily yt-dlp update job

### Phase 3 — API Layer
9. `podqueue/api/main.py` — FastAPI app (`docs_url=None`); `ThreadPoolExecutor(max_workers=1)` as default executor; StaticFiles mounts; `GET /api/feeds`
10. `podqueue/api/auth.py` — password-only login, session cookie
11. `podqueue/api/channels.py`
12. `podqueue/api/jobs.py` — trigger endpoints + SSE log-tailing + update-ytdlp

### Phase 4 — Frontend
14. `static/css/app.css` — dark mode design system
15. `static/index.html` — SPA shell
16. `static/js/api.js`
17. `static/js/app.js`
18. `static/js/channels.js`
19. `static/js/jobs.js` — SSE uses `EventSource`; reconnects automatically if the stream drops

### Phase 5 — Setup
20. `requirements.txt`
21. `setup.sh` — venv + `.env` creation + systemd unit generation
22. `README.md` — updated docs

---

## What's Explicitly Excluded

- Kemono support (add back later as core/downloader_kemono.py + api/kemono.py)
- Data migration from old instance (fresh deployment)
- HTTPS / reverse proxy setup (document in README, not automated)
- Multi-user support
- Mobile app / external API consumers (JWT not needed yet)
