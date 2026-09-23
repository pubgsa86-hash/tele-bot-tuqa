import asyncio
import inspect
import json
import math
import os
import shutil


class FFmpegError(RuntimeError):
    pass


class ConversionError(RuntimeError):
    pass


def ensure_binary(name):
    project_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "ffmpeg", "bin")
    local = os.path.join(project_bin, name)
    if os.path.isfile(local):
        return local
    path = shutil.which(name)
    if not path:
        raise FFmpegError(f"{name} is not installed")
    return path


def _rotation_from_side_data(streams):
    for st in streams:
        if st.get("codec_type") != "video":
            continue
        for sd in st.get("side_data_list") or []:
            if sd.get("rotation") is not None:
                return int(round(float(sd.get("rotation"))))
    return 0


async def probe(path):
    ensure_binary("ffprobe")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height,duration:format=duration",
        "-of", "json", path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError((err or b"").decode("utf-8", "ignore")[-500:] or "ffprobe failed")
    data = json.loads(out.decode("utf-8", "ignore") or "{}")
    format_info = data.get("format", {})
    duration = _to_float(format_info.get("duration"))
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    width = int(video.get("width") or 0) if video else 0
    height = int(video.get("height") or 0) if video else 0
    rotation = _rotation_from_side_data(streams)
    if rotation in (90, 270):
        width, height = height, width
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio,
        "has_video": video is not None,
        "format": format_info.get("format_name", ""),
    }


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def run_ffmpeg(cmd, duration=None, progress_cb=None, timeout=None):
    ensure_binary("ffmpeg")
    full = list(cmd) + ["-progress", "pipe:1", "-nostats", "-y"]
    proc = await asyncio.create_subprocess_exec(
        *full, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stderr_lines = []

    async def read_stderr():
        async for raw in proc.stderr:
            stderr_lines.append(raw.decode("utf-8", "ignore"))

    async def _report(pct):
        if not progress_cb:
            return
        if inspect.isawaitable(progress_cb(pct)):
            await progress_cb(pct)
        else:
            progress_cb(pct)

    async def read_progress():
        out_time = 0.0
        last = [0]
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "ignore").strip()
            if line.startswith("out_time_us="):
                try:
                    out_time = float(line.split("=", 1)[1]) / 1_000_000.0
                except (ValueError, IndexError):
                    out_time = 0.0
            elif line.startswith("out_time_ms="):
                try:
                    out_time = float(line.split("=", 1)[1]) / 1_000.0
                except (ValueError, IndexError):
                    pass
            elif line == "progress=end":
                await _report(100)
            if duration and duration > 0:
                pct = int(min(99, max(0, out_time / duration * 100)))
                if pct != last[0]:
                    last[0] = pct
                    await _report(pct)

    stderr_task = asyncio.create_task(read_stderr())
    progress_task = asyncio.create_task(read_progress())

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise FFmpegError("timeout")
    finally:
        await stderr_task
        await progress_task

    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-8:])
        raise FFmpegError(tail[-1200:] or "ffmpeg failed")
    return True


def scale_to_cover(in_w, in_h, target_w, target_h):
    s = max(target_w / max(in_w, 1), target_h / max(in_h, 1))
    return max(in_w * s, 1), max(in_h * s, 1)


def time_str(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds//60:02d}:{seconds%60:02d}"