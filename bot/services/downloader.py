import os

from bot.config import cfg
from bot.converters.ffmpeg import ConversionError
from bot.utils.helpers import cleanup_file


async def download_media(bot, file_id, work_dir, file_name="input", mime="", ext_hint=""):
    file_info = await bot.get_file(file_id)
    if not file_info or not file_info.file_path:
        raise ConversionError("cannot_resolve")

    ext = ext_hint or _mime_ext(mime) or os.path.splitext(file_info.file_path)[1] or ".bin"
    dest = os.path.join(work_dir, f"{os.urandom(4).hex()}{ext}")
    try:
        await bot.download_file(file_info.file_path, dest)
    except Exception:
        cleanup_file(dest)
        raise ConversionError("cannot_resolve")
    size = os.path.getsize(dest) if os.path.exists(dest) else 0
    if size <= 0:
        cleanup_file(dest)
        raise ConversionError("empty")
    if size > cfg.max_file_size:
        cleanup_file(dest)
        raise ConversionError("too_large")
    return dest


_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def _mime_ext(mime):
    if not mime:
        return ""
    mime = mime.lower().split(";")[0].strip()
    return _EXT_BY_MIME.get(mime, "")