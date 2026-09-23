"""Cloudflare Media Transformations client.

Uses the official URL-based Media Transformations API:

    https://<zone>/cdn-cgi/media/<OPTIONS>/<SOURCE-URL>

The bot serves the source video at a public URL of its own webapp
(``/api/video/<token>``, which supports HTTP Range requests), requests a
transformation with the desired options and streams the resulting MP4 back
to the user as a Telegram Video Note.
"""
import logging
import os
import re

import aiohttp

from bot.config import cfg

logger = logging.getLogger(__name__)

FILENAME_RE = re.compile(r"^[a-zA-Z0-9-_]+\.?[a-zA-Z0-9-_]+$")
_OPTION_ORDER = ("mode", "time", "duration", "width", "height", "fit", "audio", "format", "filename")


class CloudflareMediaError(RuntimeError):
    pass


def _secs(value):
    value = max(0, int(round(float(value or 0))))
    return f"{value}s"


def build_transform_url(source_url, *, start=0.0, duration=60.0,
                        width=320, height=320, audio=False,
                        filename="video_note.mp4"):
    options = {
        "mode": "video",
        "time": _secs(start),
        "duration": _secs(max(1, duration)),
        "width": int(max(10, min(2000, width))),
        "height": int(max(10, min(2000, height))),
        "fit": "cover",
        "audio": "true" if audio else "false",
    }
    if filename and FILENAME_RE.match(filename):
        options["filename"] = filename
    ordered = ",".join(f"{k}={options[k]}" for k in _OPTION_ORDER if k in options)
    return f"https://{cfg.cloudflare_media_zone}/cdn-cgi/media/{ordered}/{source_url}"


async def fetch_transformed(url, out_path, progress_cb=None):
    """Download the transformed MP4 from Cloudflare into ``out_path``."""
    timeout = aiohttp.ClientTimeout(total=cfg.cloudflare_media_timeout)
    written = 0
    try:
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.get(url) as resp:
                if resp.status != 200:
                    text = ""
                    try:
                        text = await resp.text()
                    except Exception:
                        pass
                    raise CloudflareMediaError(
                        f"cloudflare {resp.status}: {(text or '').strip()[:300] or 'transformation failed'}")
                total = resp.content_length
                with open(out_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
                        written += len(chunk)
                        if progress_cb and total and total > 0:
                            pct = min(99, int(written / total * 100))
                            await progress_cb(pct)
    except aiohttp.ClientError as exc:
        raise CloudflareMediaError(f"cloudflare network error: {exc}")
    if written <= 0:
        raise CloudflareMediaError("cloudflare empty response")
    if progress_cb:
        await progress_cb(100)
    return out_path


async def transform_video_note(source_url, start, duration, size, out_path, progress_cb=None):
    """Transform a video into a square, silent MP4 ready for sendVideoNote()."""
    url = build_transform_url(
        source_url,
        start=start,
        duration=duration,
        width=size,
        height=size,
        audio=False,
        filename="video_note.mp4",
    )
    logger.info("Cloudflare transform: %s", url)
    return await fetch_transformed(url, out_path, progress_cb=progress_cb)