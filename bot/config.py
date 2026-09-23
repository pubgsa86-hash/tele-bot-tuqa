import os
import tempfile


def _env_bool(key, default):
    v = os.getenv(key)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key, default):
    v = os.getenv(key)
    try:
        return int(v) if v is not None and str(v).strip() else default
    except (TypeError, ValueError):
        return default


def _env_float(key, default):
    v = os.getenv(key)
    try:
        return float(v) if v is not None and str(v).strip() else default
    except (TypeError, ValueError):
        return default


class Config:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "").strip()
        self.webapp_url = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
        self.port = _env_int("PORT", 8080)
        self.max_file_size = _env_int("MAX_FILE_SIZE", 50 * 1024 * 1024)
        self.max_video_duration = _env_int("MAX_VIDEO_DURATION", 120)
        self.max_gif_duration = _env_int("MAX_GIF_DURATION", 10)
        self.max_gif_width = _env_int("MAX_GIF_WIDTH", 480)
        self.max_concurrent_jobs = _env_int("MAX_CONCURRENT_JOBS", 2)
        self.session_ttl = _env_int("SESSION_TTL", 1800)
        self.enable_shaping = _env_bool("ENABLE_TEXT_SHAPING", True)
        self.media_engine = (os.getenv("MEDIA_ENGINE", "cloudflare").strip().lower() or "cloudflare")
        self.cloudflare_media_zone = os.getenv("CLOUDFLARE_MEDIA_ZONE", "").strip().lower()
        self.cloudflare_media_timeout = _env_int("CLOUDFLARE_MEDIA_TIMEOUT", 10 * 60)
        work = os.getenv("WORK_DIR", "").strip()
        if not work or not os.path.isdir(work):
            work = os.path.join(tempfile.gettempdir(), "media_converter")
        self.work_dir = work
        db_path = os.getenv("DB_PATH", "").strip()
        self.db_path = db_path or os.path.join(self.work_dir, "converter.db")

    @property
    def has_webapp(self):
        return bool(self.webapp_url)

    @property
    def media_public_base(self):
        return self.webapp_url

    def validate(self):
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is not set. See .env.example")
        if self.media_engine not in ("cloudflare", "ffmpeg"):
            raise RuntimeError("MEDIA_ENGINE must be either 'cloudflare' or 'ffmpeg'")
        if self.media_engine == "cloudflare":
            if not self.cloudflare_media_zone:
                raise RuntimeError(
                    "CLOUDFLARE_MEDIA_ZONE is not set (e.g. R2_MEDIA_EXAMPLE.com). "
                    "Enable Media Transformations for that zone in the Cloudflare dashboard."
                )
            if not self.webapp_url:
                raise RuntimeError(
                    "WEBAPP_URL must be set to the public URL of this bot "
                    "(used as the media source for Cloudflare Media Transformations)."
                )


cfg = Config()