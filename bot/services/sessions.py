import secrets

from bot.config import cfg
from bot.database.db import db
from bot.services.downloader import download_media
from bot.utils.helpers import cleanup_tree, ext_of, make_job_dir


async def create_video_session(bot, user_id, chat_id, media_message_id, file_id, file_name="", duration=0.0, width=0, height=0, mime=""):
    token = secrets.token_urlsafe(32)
    work_dir = make_job_dir("session")
    try:
        dl_path = await download_media(bot, file_id, work_dir, file_name or "input", mime)
        from bot.converters.ffmpeg import probe
        try:
            info = await probe(dl_path)
            if info["duration"] and info["duration"] > 0:
                duration = info["duration"]
            if info["width"] and info["height"]:
                width, height = info["width"], info["height"]
        except Exception:
            pass
    except Exception:
        cleanup_tree(work_dir)
        raise
    await purge_sessions(user_id, except_token=None)
    return await _finalize_session(
        token, user_id, chat_id, media_message_id, "video", file_id,
        dl_path, work_dir, duration, width, height,
    )


async def create_generic_session(bot, user_id, chat_id, media_message_id, kind, file_id,
                                 file_name="", mime="", duration=0.0, width=0, height=0):
    token = secrets.token_urlsafe(32)
    work_dir = make_job_dir("session")
    try:
        dl_path = await download_media(bot, file_id, work_dir, file_name or "input", mime, ext_hint=kind)
    except Exception:
        cleanup_tree(work_dir)
        raise
    return await _finalize_session(
        token, user_id, chat_id, media_message_id, kind, file_id,
        dl_path, work_dir, duration, width, height,
    )


async def _finalize_session(token, user_id, chat_id, media_message_id, kind, file_id,
                            file_path, work_dir, duration, width, height):
    await db().create_session(
        token=token, user_id=user_id, chat_id=chat_id, media_message_id=media_message_id,
        kind=kind, file_id=file_id, file_path=file_path, work_dir=work_dir,
        extension=ext_of(file_path), duration=duration or 0.0,
        width=width or 0, height=height or 0, ttl=cfg.session_ttl,
    )
    return {
        "token": token,
        "kind": kind,
        "duration": duration or 0.0,
        "width": width or 0,
        "height": height or 0,
    }


async def get_valid_session(token):
    session = await db().get_session(token)
    if not session:
        return None
    import os
    if not os.path.isfile(session.get("file_path", "")):
        await db().delete_session(token)
        return None
    return session


async def purge_sessions(user_id, except_token=None):
    """Delete the user's stored media sessions (kept until 'end' or expiry)."""
    for s in await db().sessions_for_user(user_id):
        if except_token and s["token"] == except_token:
            continue
        cleanup_tree(s.get("work_dir") or "")
        await db().delete_session(s["token"])


async def sweep_expired_sessions(ttl):
    for s in await db().list_expired_sessions(ttl):
        cleanup_tree(s.get("work_dir") or "")
        await db().delete_session(s["token"])