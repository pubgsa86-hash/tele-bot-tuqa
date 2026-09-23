import json
import logging
import os
from pathlib import Path

from aiohttp import web

from bot.database.db import db
from bot.services.conversion import run_video_note_job
from bot.services.jobs import job_manager
from bot.services.nav import enter_result, record_op
from bot.services.sessions import get_valid_session
from bot.utils.telegram_auth import validate_init_data

logger = logging.getLogger(__name__)

METADATA = Path(__file__).resolve().parent.parent
DIST_DIR = METADATA / "web" / "dist"


def _json_ok(body):
    return web.json_response(body)


def _json_err(status, message, extra=None):
    body = {"error": message}
    if extra:
        body.update(extra)
    return web.json_response(body, status=status)


def _clamp_float(value, lo, hi, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _sanitize_settings(raw, video_duration):
    if not isinstance(raw, dict):
        raise ValueError("invalid settings")
    duration = float(video_duration or 0)
    start = _clamp_float(raw.get("start", 0), 0, max(0, duration), 0)
    end = _clamp_float(raw.get("end", duration), 0, max(0, duration), duration)
    if end - start < 0.3:
        end = min(duration, start + 0.3)
    if end - start > 60:
        end = start + 60
    circle = raw.get("circle") or {}
    if not isinstance(circle, dict):
        circle = {}
    pan = raw.get("pan") or {}
    if not isinstance(pan, dict):
        pan = {}
    zoom = _clamp_float(raw.get("zoom", 1), 1, 4, 1)
    size = raw.get("size", 320)
    if isinstance(size, str) and size.lower() in ("original", "orig"):
        size = "original"
    else:
        size = int(size) if str(size).isdigit() else 320
        size = max(16, min(1080, size))
        size = size - (size % 2)
        if size < 2:
            size = 2
    frame = raw.get("frame") or {}
    if not isinstance(frame, dict):
        frame = {}
    watermark = raw.get("watermark") or {}
    if not isinstance(watermark, dict):
        watermark = {}
    if watermark.get("enabled") not in (True, False):
        watermark["enabled"] = True
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "zoom": round(zoom, 4),
        "pan": {
            "x": _clamp_float(pan.get("x"), -100000, 100000, 0),
            "y": _clamp_float(pan.get("y"), -100000, 100000, 0),
        },
        "circle": {
            "cx": _clamp_float(circle.get("cx", 0.5), 0, 1, 0.5),
            "cy": _clamp_float(circle.get("cy", 0.5), 0, 1, 0.5),
            "d": _clamp_float(circle.get("d", 0.9), 0.1, 1, 0.9),
        },
        "size": size,
        "mask": bool(raw.get("mask", False)),
        "frame": {
            "enabled": bool(frame.get("enabled", False)),
            "color": str(frame.get("color") or "#ffffff")[:9],
            "width": int(_clamp_float(frame.get("width"), 1, 40, 4)),
        },
        "watermark": {
            "enabled": bool(watermark.get("enabled", False)),
            "text": str(watermark.get("text") or "")[:120],
            "size": _clamp_float(watermark.get("size"), 0.02, 0.2, 0.06),
            "opacity": _clamp_float(watermark.get("opacity"), 0.1, 1, 0.8),
            "pos": str(watermark.get("pos") or "br")[:8],
        },
    }


def _verify_or_null(request):
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        return True
    return validate_init_data(init_data) is not None


async def health(_request):
    return _json_ok({"status": "ok", "service": "media-converter-bot"})


async def index(_request):
    idx = DIST_DIR / "index.html"
    if idx.is_file():
        return web.FileResponse(idx)
    return web.Response(text="Backend is running. Build the frontend (npm run build in /web) "
                             "or access a Mini App token URL.", content_type="text/plain")


class SPAStatic:
    def __init__(self):
        self.assets_dir = DIST_DIR / "assets"

    async def asset(self, request):
        name = request.match_info["name"]
        path = (self.assets_dir / name).resolve()
        root = self.assets_dir.resolve()
        if root not in path.parents or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def fallback(self, request):
        idx = DIST_DIR / "index.html"
        if idx.is_file():
            return web.FileResponse(idx)
        raise web.HTTPNotFound()


async def api_session(request):
    token = request.match_info["token"]
    session = await get_valid_session(token)
    if not session:
        return _json_err(404, "session_not_found")
    return _json_ok({
        "token": token,
        "kind": session["kind"],
        "duration": session.get("duration") or 0,
        "width": session.get("width") or 0,
        "height": session.get("height") or 0,
        "extension": session.get("extension") or "",
    })


async def api_video(request):
    token = request.match_info["token"]
    session = await get_valid_session(token)
    if not session:
        return _json_err(404, "session_not_found")
    path = session.get("file_path", "")
    if not os.path.isfile(path):
        return _json_err(404, "file_missing")
    return await stream_file(request, path, "video/mp4")


async def api_video_head(request):
    token = request.match_info["token"]
    session = await get_valid_session(token)
    if not session:
        return _json_err(404, "session_not_found")
    path = session.get("file_path", "")
    if not os.path.isfile(path):
        return _json_err(404, "file_missing")
    return await stream_file(request, path, "video/mp4", with_body=False)


RANGE_RE = None


def _parse_range(range_header, size):
    if not range_header or not range_header.startswith("bytes="):
        return None
    try:
        parts = range_header[len("bytes="):].split("-", 1)
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else size - 1
        if start < 0 or end < start or start >= size:
            return None
        return start, min(end, size - 1)
    except (ValueError, IndexError):
        return None


async def stream_file(request, path, content_type, with_body=True):
    size = os.path.getsize(path)
    range_header = request.headers.get("Range")
    rng = _parse_range(range_header, size)
    base = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    if not rng or not with_body:
        if not with_body:
            return web.Response(status=200, body=b"", headers={**base, "Content-Length": str(size)},
                                content_type=content_type)
        resp = web.FileResponse(path, headers=base)
        resp.content_type = content_type
        return resp
    start, end = rng
    chunk_size = end - start + 1
    body = _read_chunk(path, start, chunk_size)
    return web.Response(
        status=206,
        body=body,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Cache-Control": "no-store",
        },
        content_type=content_type,
    )


def _read_chunk(path, start, length):
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(length)


async def api_process(request):
    if not _verify_or_null(request):
        return _json_err(403, "invalid_init_data")
    try:
        data = await request.json()
    except Exception:
        return _json_err(400, "invalid_json")
    token = str(data.get("token") or "")
    session = await get_valid_session(token)
    if not session:
        return _json_err(404, "session_not_found")
    if session.get("kind") != "video":
        return _json_err(400, "not_video")
    if job_manager.busy:
        return _json_err(429, "busy")

    existing = await db().active_job_for_token(token)
    if existing:
        return _json_err(409, "job_running")

    try:
        settings = _sanitize_settings(data.get("settings") or {}, session.get("duration") or 0)
    except ValueError:
        return _json_err(400, "invalid_settings")

    chat_id = session["chat_id"]
    user_id = session["user_id"]
    media_message_id = session.get("media_message_id") or 0

    # Refresh the expiry and remember the settings so "convert again" works.
    await db().update_session(token, settings_json=json.dumps(settings, ensure_ascii=False))

    from bot.services.bot_registry import get_bot
    bot = get_bot()

    enter_result(user_id)
    record_op(user_id, {"op": "vnote", "tid": "", "token": token, "settings": settings})

    job_id = await run_video_note_job(bot, session, settings, send_result=True)
    return _json_ok({"job_id": job_id, "status": "queued"})


async def api_job(request):
    job_id = request.match_info["job_id"]
    job = await db().get_job(job_id)
    if not job:
        return _json_err(404, "job_not_found")
    return _json_ok({
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"] or None,
    })


async def api_cleanup(request):
    """Optional cleanup — the frontend no longer calls this automatically;
    sessions are kept alive so the user can re-edit and re-convert."""
    try:
        data = await request.json()
    except Exception:
        return _json_err(400, "invalid_json")
    token = str(data.get("token") or "")
    exists = await get_valid_session(token)
    if exists:
        await db().delete_session(token)
        from bot.utils.helpers import cleanup_tree
        cleanup_tree(exists.get("work_dir") or "")
        return _json_ok({"cleaned": True})
    return _json_ok({"cleaned": False})


async def api_history(request):
    user_id = request.match_info["user_id"]
    try:
        uid = int(user_id)
    except ValueError:
        return _json_err(400, "invalid_user")
    rows = await db().history(uid, limit=15)
    return _json_ok({"history": rows})


async def cors_middleware(app, handler):
    async def middleware(request):
        if request.method == "OPTIONS":
            return web.Response(status=204, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Init-Data, Range",
                "Access-Control-Max-Age": "3600",
            })
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Init-Data, Range"
        return resp
    return middleware


def create_app():
    app = web.Application(middlewares=[cors_middleware])
    spa = SPAStatic()
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/assets/{name:.*}", spa.asset)
    app.router.add_get("/api/session/{token}", api_session)
    app.router.add_get("/api/video/{token}", api_video)
    app.router.add_head("/api/video/{token}", api_video_head)
    app.router.add_post("/api/process", api_process)
    app.router.add_get("/api/job/{job_id}", api_job)
    app.router.add_post("/api/cleanup", api_cleanup)
    app.router.add_get("/api/history/{user_id}", api_history)
    app.router.add_get("/{tail:.*}", spa.fallback)
    return app