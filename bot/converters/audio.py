from bot.converters.ffmpeg import ConversionError, run_ffmpeg

AUDIO_FMT_OPTS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "aac", "opus", "flac", "m4a"}


async def probe_media(path):
    from bot.converters.ffmpeg import probe
    return await probe(path)


async def to_voice_ogg(input_path, out_path, progress_cb=None):
    info = await probe_media(input_path)
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-vn", "-c:a", "libopus", "-b:a", "64k", "-ar", "48000", "-ac", "1",
        "-application", "voip", out_path,
    ]
    await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": "MP3→بصمة",
        "filename": "voice.ogg",
    }


async def to_mp3(input_path, out_path, progress_cb=None):
    info = await probe_media(input_path)
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k", out_path,
    ]
    await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": "بصمة→MP3",
        "filename": "audio.mp3",
    }


async def extract_video_audio(input_path, out_path, fmt="mp3", progress_cb=None):
    if fmt not in AUDIO_FMT_OPTS:
        raise ConversionError("unsupported_format")
    info = await probe_media(input_path)
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-vn", *AUDIO_FMT_OPTS[fmt], out_path,
    ]
    await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": f"استخراج صوت {fmt}",
        "filename": f"extracted.{fmt}",
    }


async def convert_audio_format(input_path, out_path, fmt, progress_cb=None):
    if fmt not in AUDIO_FMT_OPTS:
        raise ConversionError("unsupported_format")
    info = await probe_media(input_path)
    if not info["has_audio"]:
        raise ConversionError("no_audio_stream")
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-map", "0:a?", "-vn", *AUDIO_FMT_OPTS[fmt], out_path,
    ]
    await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": f"تحويل إلى {fmt.upper()}",
        "filename": f"audio_converted.{fmt}",
    }