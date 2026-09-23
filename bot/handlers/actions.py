"""Inline action handlers for the media-converter bot.

Callback map (matches constants.py keyboard builders exactly):
  act:vnote:{tid}   video -> circular-video-note Mini App session
  act:va:{tid}      video -> audio (mp3)
  act:a2voice:{tid} audio  -> voice (opus/ogg)
  act:gif:{tid}     video -> gif animation
  act:vfmt:{tid}    video -> choose format (via format_kb / run:fconv)
  act:afmt:{tid}    audio  -> choose format
  act:ifmt:{tid}    image  -> choose format
  act:vna:{tid}     video -> remove audio track
  act:v2mp3:{tid}   voice -> mp3
  act:i2png:{tid}   image -> png
  act:i2stk:{tid}   image -> sticker type (via sticker_type_kb / stk:)
  act:s2img:{tid}   sticker -> photo
  act:irz:{tid}     image -> resize size (via resize_size_kb / rzs: / rzm:)
  act:vwm:{tid}     video -> watermark (FSM)
  act:iwm:{tid}     image -> watermark (FSM)
  act:d2pdf:{tid}   doc -> pdf
  m:{key}           main menu navigation (video/audio/image/doc/hist/sett/help)
  m:back            go back one step
  m:home            back to the main menu
  m:end             explicitly end the session
  m:again           repeat the last conversion
  m:edit            edit settings of the last conversion
  stk:* , rzs:* , rzm:* , wmpos:* , wmsize:* , wmop:*  (sub-steps)
"""
import logging
import os

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot.config import cfg
from bot.constants import (
    ERR_MESSAGES,
    HELP_TEXT,
    MSG_ASK_FORMAT,
    MSG_ASK_OPACITY,
    MSG_ASK_POS,
    MSG_ASK_RESIZE_MODE,
    MSG_ASK_RESIZE_SIZE,
    MSG_ASK_SIZE,
    MSG_ASK_STICKER_TYPE,
    MSG_ASK_TEXT,
    MSG_ENDED,
    MSG_ERROR,
    MSG_HISTORY_EMPTY,
    MSG_UNAVAILABLE,
    SETTINGS_TEXT,
    WELCOME_TEXT,
    back_kb,
    format_kb,
    main_menu_kb,
    resize_mode_kb,
    resize_size_kb,
    sticker_type_kb,
    wm_opacity_kb,
    wm_pos_kb,
    wm_size_kb,
)
from bot.converters import audio as cv_audio
from bot.converters import image as cv_image
from bot.converters import pdf as cv_pdf
from bot.converters import video as cv_video
from bot.converters.ffmpeg import ConversionError, probe, run_ffmpeg
from bot.database.db import db
from bot.services import nav
from bot.services.conversion import run_conversion
from bot.services.downloader import download_media
from bot.services.pending import PendingItem, drop_user, get_pending
from bot.services.sessions import create_video_session, get_valid_session, purge_sessions
from bot.utils.helpers import cleanup_tree, make_job_dir

logger = logging.getLogger(__name__)

router = Router()


class WatermarkStates(StatesGroup):
    waiting_text = State()
    waiting_pos = State()
    waiting_size = State()
    waiting_opacity = State()


_EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])

_WM_OPACITY = {
    "light": 0.3,
    "medium": 0.5,
    "strong": 0.75,
    "full": 1.0,
}

_MENU_ENTER_TEXT = {
    "video": "🎬 أرسل <b>فيديو</b> وسأعرض لك خيارات التحويل.",
    "audio": "🎵 أرسل <b>صوتًا</b> وسأعرض لك خيارات التحويل.",
    "image": "🖼 أرسل <b>صورة</b> وسأعرض لك خيارات التحويل.",
    "doc": "📄 أرسل <b>مستندًا</b> وسأحوّله إلى PDF.",
}

_MEDIA_ACT_TEXT = {
    "video": "🎬 الفيديو",
    "audio": "🎵 الصوت",
    "voice": "🎤 البصمة",
    "image": "🖼 الصورة",
    "sticker": "🎟 الملصق",
    "doc": "📄 المستند",
}


def parse(data: str) -> dict:
    parts = data.split(":")
    head = parts[0] if parts else ""
    if head == "m":
        key = parts[1] if len(parts) > 1 else "home"
        if key in ("back", "home", "end", "again", "edit"):
            return {"action": key}
        return {"action": "menu", "key": key}
    if head == "act":
        act = parts[1] if len(parts) > 1 else ""
        if act == "cancel":
            return {"action": "cancel"}
        return {"action": "act", "act": act, "tid": parts[2] if len(parts) > 2 else "x"}
    if head == "run" and len(parts) > 4 and parts[1] == "fconv":
        return {"action": "fconv", "kind": parts[2], "key": parts[3],
                "tid": parts[4] if len(parts) > 4 else "x"}
    if head == "rzs" and len(parts) > 2:
        return {"action": "rzs", "size": parts[1],
                "tid": parts[2] if len(parts) > 2 else "x"}
    if head == "rzm" and len(parts) > 3:
        return {"action": "rzm", "mode": parts[1], "size": parts[2],
                "tid": parts[3] if len(parts) > 3 else "x"}
    if head == "stk" and len(parts) > 2:
        return {"action": "stk", "key": parts[1],
                "tid": parts[2] if len(parts) > 2 else "x"}
    if head == "wmpos" and len(parts) > 2:
        return {"action": "wmpos", "pos": parts[1],
                "tid": parts[2] if len(parts) > 2 else "x"}
    if head == "wmsize" and len(parts) > 2:
        return {"action": "wmsize", "key": parts[1],
                "tid": parts[2] if len(parts) > 2 else "x"}
    if head == "wmop" and len(parts) > 2:
        return {"action": "wmop", "key": parts[1],
                "tid": parts[2] if len(parts) > 2 else "x"}
    return {"action": "unknown"}


# ----------------------------------------------------------------------
# Message helpers
# ----------------------------------------------------------------------

async def _edit(message: Message, text: str, kb=None) -> bool:
    try:
        await message.edit_text(text, reply_markup=kb if kb is not None else _EMPTY_KB)
        return True
    except Exception:
        return False


async def _show(q: CallbackQuery, text: str, kb=None):
    if q.message and await _edit(q.message, text, kb):
        return
    if q.message:
        await q.message.answer(text, reply_markup=kb)


def _editor_button(token) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 فتح المحرر",
            web_app=WebAppInfo(url=f"{cfg.webapp_url}?token={token}"),
        )],
    ])


async def _get(q: CallbackQuery, tid) -> PendingItem | None:
    item = get_pending(tid) if (tid and tid != "x") else None
    if item is None:
        await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
        return None
    if item.user_id != q.from_user.id:
        await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
        return None
    return item


async def _download_into(q: CallbackQuery, item: PendingItem, work_dir: str):
    try:
        return await download_media(
            q.bot, item.file_id, work_dir,
            item.file_name or "input", item.mime,
        )
    except ConversionError as exc:
        err = ERR_MESSAGES.get(str(exc), str(exc))
        if q.message:
            try:
                await q.message.answer(f"❌ {err}")
            except Exception:
                pass
    except Exception:
        logger.exception("download failed (tid resolved)")
        if q.message:
            try:
                await q.message.answer(MSG_ERROR)
            except Exception:
                pass
    cleanup_tree(work_dir)
    return None


def _parse_rz(size):
    size = str(size)
    if "x" in size:
        w, _, h = size.partition("x")
        return (int(w) or 512, int(h) or 512)
    n = int(size) or 512
    return n, n


def _converters_pos(pos):
    return "c" if str(pos).lower() == "mc" else str(pos)


async def _remove_audio(input_path, out_path, progress_cb=None):
    try:
        info = await probe(input_path)
    except Exception:
        raise ConversionError("unsupported")
    if not info["has_video"]:
        raise ConversionError("no_video_stream")
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-map", "0:v?", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        out_path,
    ]
    await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": "إزالة الصوت",
        "filename": "no_audio.mp4",
    }


# ----------------------------------------------------------------------
# Screen rendering (nav)
# ----------------------------------------------------------------------

async def _screen(key: str):
    """Return (text, kb) for a screen key, or (None, None) if unknown."""
    if key in ("home", ""):
        return WELCOME_TEXT, main_menu_kb()
    if key in _MENU_ENTER_TEXT:
        return _MENU_ENTER_TEXT[key], back_kb()
    if key == "sett":
        return SETTINGS_TEXT, back_kb()
    if key == "help":
        return HELP_TEXT, back_kb()
    if key.startswith("fmt:"):
        _, kind, tid = key.split(":", 2)
        return MSG_ASK_FORMAT, format_kb(kind, tid)
    if key.startswith("irz:"):
        _, tid = key.split(":", 1)
        return MSG_ASK_RESIZE_SIZE, resize_size_kb(tid)
    if key.startswith("rzm:"):
        _, mode, size, tid = key.split(":", 3)
        return MSG_ASK_RESIZE_MODE, resize_mode_kb(tid, size)
    if key.startswith("stk:"):
        _, tid = key.split(":", 1)
        return MSG_ASK_STICKER_TYPE, sticker_type_kb(tid)
    if key.startswith("wm:"):
        _, kind, tid = key.split(":", 2)
        return MSG_ASK_TEXT, back_kb()
    for kind in _MEDIA_ACT_TEXT:
        if key.startswith(f"{kind}_act:"):
            _, tid = key.split(":", 1)
            kb_builder = {
                "video": _kb_video, "audio": _kb_audio, "voice": _kb_voice,
                "image": _kb_image, "sticker": _kb_sticker, "doc": _kb_doc,
            }[kind]
            text = {
                "video": MSG_ON_VIDEO, "audio": MSG_ON_AUDIO, "voice": MSG_ON_VOICE,
                "image": MSG_ON_IMAGE, "sticker": MSG_ON_STICKER, "doc": MSG_ON_DOC,
            }[kind]
            return text, kb_builder(tid)
    return None, None


def _kb_video(tid):
    from bot.constants import video_actions_kb
    return video_actions_kb(tid)


def _kb_audio(tid):
    from bot.constants import audio_actions_kb
    return audio_actions_kb(tid)


def _kb_voice(tid):
    from bot.constants import voice_actions_kb
    return voice_actions_kb(tid)


def _kb_image(tid):
    from bot.constants import image_actions_kb
    return image_actions_kb(tid)


def _kb_sticker(tid):
    from bot.constants import sticker_actions_kb
    return sticker_actions_kb(tid)


def _kb_doc(tid):
    from bot.constants import doc_actions_kb
    return doc_actions_kb(tid)


async def _render(q: CallbackQuery, key: str):
    text, kb = await _screen(key)
    if text is None:
        text, kb = WELCOME_TEXT, main_menu_kb()
    await _show(q, text, kb)


async def _render_history(q: CallbackQuery, user_id: int, back_to: str):
    rows = []
    handle = db()
    if handle is not None:
        rows = await handle.history(user_id, limit=10)
    if not rows:
        await _show(q, MSG_HISTORY_EMPTY, back_kb())
        return
    lines = []
    for r in rows:
        icon = "✅" if r.get("status") == "ok" else "❌"
        lines.append(f"{icon} {r.get('conv_type') or 'تحويل'} — {r.get('filename') or '-'}")
    await _show(q, "📋 <b>آخر التحويلات:</b>\n\n" + "\n".join(lines), back_kb())


# ----------------------------------------------------------------------
# Navigation callbacks
# ----------------------------------------------------------------------

async def _menu(q: CallbackQuery, state: FSMContext, p: dict):
    key = p.get("key") or "home"
    user_id = q.from_user.id
    if key == "hist":
        nav.push(user_id, "hist")
        await _render_history(q, user_id, "hist")
        await q.answer()
        return
    if key == "home":
        nav.reset(user_id)
    else:
        nav.push(user_id, key)
    await _render(q, key)
    await q.answer()


async def _back(q: CallbackQuery, state: FSMContext, p: dict):
    user_id = q.from_user.id
    await state.clear()
    target = nav.pop(user_id) or "home"
    while target and str(target).startswith("wm:"):
        target = nav.pop(user_id) or "home"
    await _render(q, target)
    await q.answer()


async def _home_cb(q: CallbackQuery, state: FSMContext, p: dict):
    user_id = q.from_user.id
    await state.clear()
    nav.reset(user_id)
    await _render(q, "home")
    await q.answer()


async def _end(q: CallbackQuery, state: FSMContext, p: dict):
    user_id = q.from_user.id
    await state.clear()
    drop_user(user_id)
    await purge_sessions(user_id)
    nav.drop(user_id)
    await q.answer()
    if q.message:
        await _edit(q.message, MSG_ENDED, main_menu_kb())


async def _cancel(q: CallbackQuery, state: FSMContext, p: dict):
    await _back(q, state, p)


# ----------------------------------------------------------------------
# Video note (Mini App session)
# ----------------------------------------------------------------------

async def _do_vnote(q: CallbackQuery, tid: str):
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    if not q.message:
        return
    if not cfg.has_webapp:
        await q.message.answer(MSG_UNAVAILABLE)
        return
    try:
        session = await create_video_session(
            q.bot, item.user_id, q.message.chat.id, 0,
            item.file_id, item.file_name or "video",
            duration=item.duration, width=item.width,
            height=item.height, mime=item.mime,
        )
        token = session["token"]
        nav.record_op(item.user_id, {"op": "vnote", "tid": tid, "token": token, "settings": {}})
        await q.message.answer(
            "⭕ اضغط الزر لفتح محرر الفيديو الدائري:",
            reply_markup=_editor_button(token),
        )
    except Exception:
        logger.exception("video note session creation failed")
        if q.message:
            await q.message.answer(MSG_ERROR)


# ----------------------------------------------------------------------
# One-step conversions (kept alive, get not pop)
# ----------------------------------------------------------------------

async def _run_simple(q: CallbackQuery, item: PendingItem, act: str):
    work_dir = make_job_dir(act)
    path = await _download_into(q, item, work_dir)
    if not path:
        return
    chat_id = q.message.chat.id
    nav.enter_result(item.user_id)
    nav.record_op(item.user_id, {"op": act, "tid": item.tid})
    try:
        if act == "va":
            out = os.path.join(work_dir, "extracted.mp3")
            send_kind = "audio"

            async def convert_fn(cb):
                return await cv_audio.extract_video_audio(path, out, fmt="mp3", progress_cb=cb)
        elif act == "a2voice":
            out = os.path.join(work_dir, "voice.ogg")
            send_kind = "voice"

            async def convert_fn(cb):
                return await cv_audio.to_voice_ogg(path, out, progress_cb=cb)
        elif act == "gif":
            out = os.path.join(work_dir, "animated.gif")
            send_kind = "animation"

            async def convert_fn(cb):
                return await cv_video.to_gif(path, out, progress_cb=cb)
        elif act == "vna":
            out = os.path.join(work_dir, "no_audio.mp4")
            send_kind = "video"

            async def convert_fn(cb):
                return await _remove_audio(path, out, progress_cb=cb)
        elif act == "v2mp3":
            out = os.path.join(work_dir, "audio.mp3")
            send_kind = "audio"

            async def convert_fn(cb):
                return await cv_audio.to_mp3(path, out, progress_cb=cb)
        elif act == "i2png":
            out = os.path.join(work_dir, "image.png")
            send_kind = "photo"

            async def convert_fn(cb):
                return await cv_image.to_png(path, out, progress_cb=cb)
        elif act == "s2img":
            out = os.path.join(work_dir, "sticker.png")
            send_kind = "photo"

            async def convert_fn(cb):
                return await cv_image.sticker_to_png(path, out, progress_cb=cb)
        else:  # d2pdf
            out = os.path.join(work_dir, "output.pdf")
            send_kind = "document"

            async def convert_fn(cb):
                return await cv_pdf.to_pdf(path, out, progress_cb=cb)

        await run_conversion(q.bot, chat_id, item.user_id, convert_fn, send_kind, None)
    finally:
        cleanup_tree(work_dir)


async def _run_format_once(q: CallbackQuery, item: PendingItem, kind: str, key: str):
    work_dir = make_job_dir("fconv")
    path = await _download_into(q, item, work_dir)
    if not path:
        return
    nav.enter_result(item.user_id)
    nav.record_op(item.user_id, {"op": "fconv", "tid": item.tid, "kind": kind, "key": key})
    try:
        out = os.path.join(work_dir, f"converted.{key}")
        if kind == "video":
            send_kind = "video"

            async def convert_fn(cb):
                return await cv_video.convert_video_format(path, out, key, progress_cb=cb)
        elif kind == "audio":
            send_kind = "audio"

            async def convert_fn(cb):
                return await cv_audio.convert_audio_format(path, out, key, progress_cb=cb)
        else:
            send_kind = "photo"

            async def convert_fn(cb):
                return await cv_image.convert_image_format(path, out, key, progress_cb=cb)

        await run_conversion(q.bot, q.message.chat.id, item.user_id, convert_fn, send_kind, None)
    finally:
        cleanup_tree(work_dir)


async def _run_resize_once(q: CallbackQuery, item: PendingItem, mode: str, size: str):
    work_dir = make_job_dir("resize")
    path = await _download_into(q, item, work_dir)
    if not path:
        return
    nav.enter_result(item.user_id)
    nav.record_op(item.user_id, {"op": "rzm", "tid": item.tid, "mode": mode, "size": size})
    try:
        width, height = _parse_rz(size)
        out = os.path.join(work_dir, "resized.png")

        async def convert_fn(cb):
            return await cv_image.resize_image(path, out, width, height, mode=mode, progress_cb=cb)

        await run_conversion(q.bot, q.message.chat.id, item.user_id, convert_fn, "photo", None)
    finally:
        cleanup_tree(work_dir)


async def _run_sticker_once(q: CallbackQuery, item: PendingItem, key: str):
    work_dir = make_job_dir("sticker")
    path = await _download_into(q, item, work_dir)
    if not path:
        return
    nav.enter_result(item.user_id)
    nav.record_op(item.user_id, {"op": "stk", "tid": item.tid, "key": key})
    try:
        out = os.path.join(work_dir, f"sticker.{key}")

        async def convert_fn(cb):
            return await cv_image.to_sticker(path, out, kind=key, progress_cb=cb)

        await run_conversion(q.bot, q.message.chat.id, item.user_id, convert_fn, "sticker", None)
    finally:
        cleanup_tree(work_dir)


async def _run_wm_once(q: CallbackQuery, item: PendingItem, kind: str, text: str, pos: str, frac: float, opacity: float):
    work_dir = make_job_dir("watermark")
    path = await _download_into(q, item, work_dir)
    if not path:
        return
    nav.enter_result(item.user_id)
    nav.record_op(item.user_id, {"op": "wm", "tid": item.tid, "kind": kind,
                                 "text": text, "pos": pos, "frac": frac, "opacity": opacity})
    try:
        if kind == "video":
            out = os.path.join(work_dir, "watermarked.mp4")
            send_kind = "video"

            async def convert_fn(cb):
                return await cv_video.add_video_watermark(path, out, text, pos, frac, opacity, progress_cb=cb)
        else:
            out = os.path.join(work_dir, "watermarked.png")
            send_kind = "photo"

            async def convert_fn(cb):
                return await cv_image.add_image_watermark(path, out, text, pos, frac, opacity, progress_cb=cb)

        await run_conversion(q.bot, q.message.chat.id, item.user_id, convert_fn, send_kind, None)
    finally:
        cleanup_tree(work_dir)


# ----------------------------------------------------------------------
# Choice-gated actions
# ----------------------------------------------------------------------

async def _start_format(q: CallbackQuery, kind: str, tid: str):
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    nav.push(item.user_id, f"fmt:{kind}:{tid}")
    await _show(q, MSG_ASK_FORMAT, format_kb(kind, tid))


async def _start_resize_size(q: CallbackQuery, tid: str):
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    nav.push(item.user_id, f"irz:{tid}")
    await _show(q, MSG_ASK_RESIZE_SIZE, resize_size_kb(tid))


async def _resize_mode(q: CallbackQuery, p: dict):
    size, tid = p["size"], p["tid"]
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    nav.push(item.user_id, f"rzm:__:{size}:{tid}")
    await _show(q, MSG_ASK_RESIZE_MODE, resize_mode_kb(tid, size))


async def _resize_run(q: CallbackQuery, p: dict):
    mode, size, tid = p["mode"], p["size"], p["tid"]
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    await _run_resize_once(q, item, mode, size)


async def _sticker_type(q: CallbackQuery, tid: str):
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    nav.push(item.user_id, f"stk:{tid}")
    await _show(q, MSG_ASK_STICKER_TYPE, sticker_type_kb(tid))


async def _sticker_run(q: CallbackQuery, p: dict):
    key, tid = p["key"], p["tid"]
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    await _run_sticker_once(q, item, key)


async def _format_run(q: CallbackQuery, p: dict):
    kind, key, tid = p["kind"], p["key"], p["tid"]
    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    await _run_format_once(q, item, kind, key)


# ----------------------------------------------------------------------
# Watermark flow (FSM)
# ----------------------------------------------------------------------

async def _begin_watermark(q: CallbackQuery, state: FSMContext, tid: str, kind: str):
    item = await _get(q, tid)
    if item is None:
        return
    await state.set_state(WatermarkStates.waiting_text)
    await state.update_data(tid=tid, kind=kind)
    nav.push(item.user_id, f"wm:{kind}:{tid}")
    await q.answer()
    await _show(q, MSG_ASK_TEXT)


@router.message(WatermarkStates.waiting_text)
async def _on_wm_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    tid = data.get("tid")
    if not text or not tid:
        await state.clear()
        await message.answer(ERR_MESSAGES["no_text"])
        return
    await state.update_data(text=text)
    await state.set_state(WatermarkStates.waiting_pos)
    await message.answer(MSG_ASK_POS, reply_markup=wm_pos_kb(tid))


async def _wm_pos(q: CallbackQuery, state: FSMContext, p: dict):
    if await state.get_state() != WatermarkStates.waiting_pos.state:
        return await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
    tid = p["tid"]
    await state.update_data(pos=p["pos"])
    await state.set_state(WatermarkStates.waiting_size)
    await q.answer()
    await _show(q, MSG_ASK_SIZE, wm_size_kb(tid))


async def _wm_size(q: CallbackQuery, state: FSMContext, p: dict):
    if await state.get_state() != WatermarkStates.waiting_size.state:
        return await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
    tid = p["tid"]
    await state.update_data(size=p["key"])
    await state.set_state(WatermarkStates.waiting_opacity)
    await q.answer()
    await _show(q, MSG_ASK_OPACITY, wm_opacity_kb(tid))


async def _wm_opacity(q: CallbackQuery, state: FSMContext, p: dict):
    if await state.get_state() != WatermarkStates.waiting_opacity.state:
        return await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
    data = await state.get_data()
    tid = p["tid"]
    kind = data.get("kind")
    text = data.get("text") or ""
    pos = data.get("pos")
    size = data.get("size") or "medium"
    item = await _get(q, tid)
    if item is None:
        await state.clear()
        return
    await q.answer()
    opacity = _WM_OPACITY.get(p["key"], 0.5)
    frac = cv_video.watermark_frac(size)
    pos = _converters_pos(pos)
    await _run_wm_once(q, item, kind, text, pos, frac, opacity)
    await state.clear()


# ----------------------------------------------------------------------
# Repeat / edit
# ----------------------------------------------------------------------

async def _again(q: CallbackQuery, state: FSMContext, p: dict):
    user_id = q.from_user.id
    op = nav.last_op(user_id)
    if not op:
        nav.reset(user_id)
        await _render(q, "home")
        return await q.answer()
    if op.get("op") == "vnote":
        token = op.get("token") or ""
        settings = op.get("settings") or {}
        session = await get_valid_session(token) if token else None
        if not session:
            await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
            return
        from bot.services.bot_registry import get_bot
        from bot.services.conversion import run_video_note_job
        bot = get_bot()
        await q.answer()
        await run_video_note_job(bot, session, settings, send_result=True)
        return
    item = await _get(q, op.get("tid"))
    if item is None:
        return
    await q.answer()
    kind = op.get("op")
    if kind == "fconv":
        await _run_format_once(q, item, op.get("kind"), op.get("key"))
    elif kind == "rzm":
        await _run_resize_once(q, item, op.get("mode"), op.get("size"))
    elif kind == "stk":
        await _run_sticker_once(q, item, op.get("key"))
    elif kind == "wm":
        await _run_wm_once(q, item, op.get("kind"), op.get("text"), op.get("pos"),
                           op.get("frac"), op.get("opacity"))
    else:
        await _run_simple(q, item, kind)


async def _edit(q: CallbackQuery, state: FSMContext, p: dict):
    user_id = q.from_user.id
    op = nav.last_op(user_id)
    if op and op.get("op") == "vnote":
        token = op.get("token") or ""
        session = await get_valid_session(token) if token else None
        if session and cfg.has_webapp:
            await q.answer()
            if q.message:
                await q.message.answer(
                    "✏️ <b>تعديل الإعدادات</b>\n\nعدّل ثم اضغط تحويل لإنشاء الفيديو الدائري من جديد:",
                    reply_markup=_editor_button(token),
                )
            return
        await q.answer(ERR_MESSAGES["expired_session"], show_alert=True)
        return
    await _back(q, state, p)


# ----------------------------------------------------------------------
# Top-level act:* dispatcher
# ----------------------------------------------------------------------

async def _act_callback(q: CallbackQuery, state: FSMContext, p: dict):
    act = p["act"]
    tid = p["tid"]

    if act == "vnote":
        return await _do_vnote(q, tid)
    if act in ("vwm", "iwm"):
        return await _begin_watermark(q, state, tid, "video" if act == "vwm" else "image")
    if act == "vfmt":
        return await _start_format(q, "video", tid)
    if act == "afmt":
        return await _start_format(q, "audio", tid)
    if act == "ifmt":
        return await _start_format(q, "image", tid)
    if act == "irz":
        return await _start_resize_size(q, tid)
    if act == "i2stk":
        return await _sticker_type(q, tid)

    item = await _get(q, tid)
    if item is None:
        return
    await q.answer()
    await _run_simple(q, item, act)


_HANDLERS = {
    "menu": _menu,
    "back": _back,
    "home": _home_cb,
    "end": _end,
    "again": _again,
    "edit": _edit,
    "cancel": _cancel,
    "act": _act_callback,
    "fconv": _format_run,
    "rzs": _resize_mode,
    "rzm": _resize_run,
    "stk": _sticker_run,
    "wmpos": _wm_pos,
    "wmsize": _wm_size,
    "wmop": _wm_opacity,
}


@router.callback_query()
async def on_callback(q: CallbackQuery, state: FSMContext):
    if not q.data:
        return await q.answer()
    try:
        p = parse(q.data)
        handler = _HANDLERS.get(p["action"])
        if handler is None:
            await q.answer(MSG_ERROR, show_alert=True)
            return
        await handler(q, state, p)
    except Exception:
        logger.exception("callback %r failed", q.data)
        try:
            await q.answer()
        except Exception:
            pass
        if q.message:
            try:
                await q.message.answer(MSG_ERROR)
            except Exception:
                pass