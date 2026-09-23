import logging

from aiogram.enums import ChatAction
from aiogram.types import FSInputFile

from bot.constants import ERR_MESSAGES, MSG_CONVERTING, MSG_ERROR, MSG_PROCESSING, MSG_SUCCESS, progress_bar, result_kb
from bot.converters.ffmpeg import ConversionError, probe
from bot.database.db import db
from bot.utils.helpers import cleanup_tree, make_job_dir

VIDEO_SENDS = {"video_note": "upload_video", "video": "upload_video", "animation": "upload_video"}
AUDIO_SENDS = {"voice": "upload_voice", "audio": "upload_audio"}
PHOTO_SENDS = {"photo": "upload_photo", "sticker": "upload_video", "document": "upload_document"}

logger = logging.getLogger(__name__)


def friendly_error(exc):
    msg = getattr(exc, "code", None) or str(exc)
    if isinstance(exc, ConversionError):
        return ERR_MESSAGES.get(str(exc), str(exc))
    return None


async def send_output(bot, chat_id, send_kind, path, reply_to=0, duration=0.0, length=None):
    media = FSInputFile(path)
    kwargs = {}
    if reply_to:
        kwargs["reply_to_message_id"] = reply_to
    if send_kind == "video_note":
        dur = max(1, int(duration or 1))
        if length is None:
            try:
                info = await probe(path)
            except Exception:
                info = {}
            length = int(info.get("height") or info.get("width") or 640)
        await bot.send_video_note(chat_id, media, duration=dur, length=int(length or 640), **kwargs)
    elif send_kind == "video":
        await bot.send_video(chat_id, media, supports_streaming=True, **kwargs)
    elif send_kind == "voice":
        await bot.send_voice(chat_id, media, duration=max(1, int(duration)) if duration else None, **kwargs)
    elif send_kind == "audio":
        await bot.send_audio(chat_id, media, **kwargs)
    elif send_kind == "animation":
        await bot.send_animation(chat_id, media, **kwargs)
    elif send_kind == "photo":
        await bot.send_photo(chat_id, media, **kwargs)
    elif send_kind == "sticker":
        await bot.send_sticker(chat_id, media, **kwargs)
    else:
        await bot.send_document(chat_id, media, **kwargs)


def _action_for(send_kind):
    if send_kind in VIDEO_SENDS:
        return VIDEO_SENDS[send_kind]
    if send_kind in AUDIO_SENDS:
        return AUDIO_SENDS[send_kind]
    if send_kind in PHOTO_SENDS:
        return PHOTO_SENDS[send_kind]
    return "upload_document"


async def send_result_menu(bot, chat_id, reply_to=0):
    """Send the post-success action menu (again / edit / home / back)."""
    try:
        await bot.send_message(
            chat_id,
            MSG_SUCCESS,
            reply_markup=result_kb(),
            reply_to_message_id=reply_to or None,
        )
    except Exception:
        logger.exception("failed to send result menu")


async def run_conversion(bot, chat_id, user_id, convert_fn, send_kind, label, reply_to=0):
    status = await bot.send_message(chat_id, MSG_PROCESSING, reply_to_message_id=reply_to)
    msg_id = status.message_id
    last = [0]

    async def cb(pct):
        pct = max(0, min(100, int(pct)))
        if pct >= last[0] + 5 or pct >= 100:
            last[0] = pct
            text = MSG_SUCCESS if pct >= 100 else MSG_CONVERTING.format(bar=progress_bar(pct), pct=pct)
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    result = None
    try:
        result = await convert_fn(cb)
        path = result.get("path")
        await bot.send_chat_action(chat_id=chat_id, action=_action_for(send_kind))
        await send_output(bot, chat_id, send_kind, path,
                          reply_to=reply_to, duration=result.get("duration") or 0.0,
                          length=result.get("length"))
        try:
            await bot.edit_message_text(MSG_SUCCESS, chat_id=chat_id, message_id=msg_id,
                                        reply_markup=result_kb())
        except Exception:
            pass
        await db().record_conversion(
            user_id, label or result.get("label", "تحويل"),
            result.get("filename", ""), "ok",
            duration_ms=int(result.get("duration_ms", 0) * 1000),
        )
        return result
    except ConversionError as exc:
        logger.warning("conversion failed: %s", exc)
        text_err = friendly_error(exc) or MSG_ERROR
        try:
            await bot.edit_message_text(f"❌ {text_err}", chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        await db().record_conversion(user_id, label or "تحويل", "", "failed", error=str(exc)[:400])
        return None
    except Exception as exc:
        logger.exception("conversion error")
        try:
            await bot.edit_message_text(MSG_ERROR, chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        await db().record_conversion(user_id, label or "تحويل", "", "failed", error=str(exc)[:400])
        return None
    finally:
        if result:
            cleanup_tree(result.get("work_dir") or "")


async def run_video_note_job(bot, session, settings, send_result=True):
    """Queue a video-note job that runs on the configured media engine
    (Cloudflare Media Transformations by default) and sends the note back
    to the user. The session stays alive so the user can re-edit/re-convert.
    """
    from bot.converters.video import create_video_note
    from bot.services.jobs import job_manager

    token = session["token"]
    chat_id = session["chat_id"]
    media_message_id = session.get("media_message_id") or 0
    user_id = session["user_id"]

    async def convert_fn(progress_cb):
        out_dir = make_job_dir("note")
        out_path = f"{out_dir}/video_note.mp4"
        try:
            source_url = None
            from bot.config import cfg
            if cfg.media_engine == "cloudflare":
                source_url = f"{cfg.media_public_base}/api/video/{token}"
            result = await create_video_note(
                session["file_path"], out_path, settings, progress_cb,
                source_url=source_url,
            )
            await send_output(
                bot, chat_id, "video_note", result["path"],
                reply_to=media_message_id, duration=result["duration"],
                length=result.get("length"),
            )
            if send_result:
                await send_result_menu(bot, chat_id, reply_to=media_message_id)
            return result
        except Exception:
            cleanup_tree(out_dir)
            raise

    return await job_manager.start(token, user_id, chat_id, media_message_id, convert_fn)