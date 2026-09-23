import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.constants import (
    MSG_ON_AUDIO,
    MSG_ON_DOC,
    MSG_ON_IMAGE,
    MSG_ON_STICKER,
    MSG_ON_VIDEO,
    MSG_ON_VOICE,
    audio_actions_kb,
    doc_actions_kb,
    image_actions_kb,
    sticker_actions_kb,
    video_actions_kb,
    voice_actions_kb,
)
from bot.services import nav
from bot.services.pending import push_pending

router = Router()


def _mime_kind(mime, name=""):
    mime = (mime or "").lower()
    name = (name or "").lower()
    if name.endswith(".webp") or mime in ("image/webp", "image/png", "image/jpeg", "image/jpg"):
        return "image"
    if mime.startswith("video/") or name.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi", ".gif")):
        return "video"
    if mime.startswith("audio/") or name.endswith((".mp3", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".flac")):
        return "audio"
    if name.endswith((".doc", ".docx", ".txt", ".pdf", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx")):
        return "doc"
    return "document"


@router.message(F.video | F.animation | F.video_note)
async def on_video(message: Message):
    media = message.video or message.animation or message.video_note
    duration = float(getattr(media, "duration", 0) or 0)
    mime = "video/mp4"
    name = "video"
    if message.video:
        mime = message.video.mime_type or mime
        name = message.video.file_name or "video"
    elif message.animation:
        name = message.animation.file_name or "video"
    tid = push_pending(
        message.from_user.id,
        "video",
        media.file_id,
        name,
        mime,
        duration=duration,
        width=getattr(media, "width", 0) or 0,
        height=getattr(media, "height", 0) or 0,
    )
    nav.push(message.from_user.id, f"video_act:{tid}")
    await message.answer(MSG_ON_VIDEO, reply_markup=video_actions_kb(tid))


@router.message(F.audio)
async def on_audio(message: Message):
    media = message.audio
    tid = push_pending(
        message.from_user.id,
        "audio",
        media.file_id,
        media.file_name or "audio",
        media.mime_type or "audio/mpeg",
        duration=float(media.duration or 0),
    )
    nav.push(message.from_user.id, f"audio_act:{tid}")
    await message.answer(MSG_ON_AUDIO, reply_markup=audio_actions_kb(tid))


@router.message(F.voice)
async def on_voice(message: Message):
    media = message.voice
    tid = push_pending(
        message.from_user.id,
        "voice",
        media.file_id,
        "voice",
        media.mime_type or "audio/ogg",
        duration=float(media.duration or 0),
    )
    nav.push(message.from_user.id, f"voice_act:{tid}")
    await message.answer(MSG_ON_VOICE, reply_markup=voice_actions_kb(tid))


@router.message(F.photo)
async def on_photo(message: Message):
    media = message.photo[-1]
    tid = push_pending(
        message.from_user.id,
        "image",
        media.file_id,
        "photo",
        "image/jpeg",
        width=media.width or 0,
        height=media.height or 0,
    )
    nav.push(message.from_user.id, f"image_act:{tid}")
    await message.answer(MSG_ON_IMAGE, reply_markup=image_actions_kb(tid))


@router.message(F.sticker)
async def on_sticker(message: Message):
    media = message.sticker
    if getattr(media, "is_animated", False) or getattr(media, "is_video", False):
        await message.answer(MSG_ON_STICKER, reply_markup=doc_actions_kb())
        return
    tid = push_pending(
        message.from_user.id,
        "sticker",
        media.file_id,
        "sticker",
        "image/webp",
        width=media.width or 0,
        height=media.height or 0,
    )
    nav.push(message.from_user.id, f"sticker_act:{tid}")
    await message.answer(MSG_ON_STICKER, reply_markup=sticker_actions_kb(tid))


@router.message(F.document)
async def on_document(message: Message):
    media = message.document
    mime = media.mime_type or ""
    kind = _mime_kind(mime, media.file_name or "")
    if kind in ("image", "video", "audio"):
        tid = push_pending(
            message.from_user.id,
            kind,
            media.file_id,
            media.file_name or "file",
            mime,
            duration=0.0,
        )
        text = {"image": MSG_ON_IMAGE, "video": MSG_ON_VIDEO, "audio": MSG_ON_AUDIO}[kind]
        kb = {"image": image_actions_kb, "video": video_actions_kb, "audio": audio_actions_kb}[kind](tid)
        nav.push(message.from_user.id, f"{kind}_act:{tid}")
        await message.answer(text, reply_markup=kb)
        return
    tid = push_pending(
        message.from_user.id,
        "doc",
        media.file_id,
        media.file_name or "file",
        mime,
        duration=0.0,
    )
    nav.push(message.from_user.id, f"doc_act:{tid}")
    await message.answer(MSG_ON_DOC, reply_markup=doc_actions_kb(tid))
