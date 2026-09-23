import os

from PIL import Image, ImageDraw

from bot.config import cfg
from bot.converters.ffmpeg import ConversionError, probe, run_ffmpeg
from bot.converters.fonts import ffmpeg_font_path

VIDEO_FMT_OPTS = {
    "mp4": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
    "mov": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k"],
    "mkv": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k"],
    "avi": ["-c:v", "mpeg4", "-q:v", "5", "-c:a", "libmp3lame", "-b:a", "160k"],
    "webm": ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-c:a", "libopus", "-b:a", "128k"],
}


def _clampf(value, lo, hi):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _drawtext_escape(text):
    text = str(text)
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == ":":
            out.append("\\:")
        elif ch in ",;'":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


WATERMARK_POS_EXPR = {
    "tl": ("20", "20"),
    "tc": ("(w-text_w)/2", "20"),
    "tr": ("w-tw-20", "20"),
    "ml": ("20", "(h-text_h)/2"),
    "c": ("(w-tw)/2", "(h-th)/2"),
    "mr": ("w-tw-20", "(h-th)/2"),
    "bl": ("20", "h-th-20"),
    "bc": ("(w-tw)/2", "h-th-20"),
    "br": ("w-tw-20", "h-th-20"),
}

WATERMARK_SIZE_FRAC = {
    "small": 0.04,
    "medium": 0.06,
    "large": 0.09,
    "xlarge": 0.13,
}


def _wm_textfile(text, out_dir=None):
    """Write the watermark text to a UTF-8 file (ffmpeg mangles non-ASCII argv
    on Windows, so text must be passed via textfile= instead of text=)."""
    import tempfile
    import uuid
    if out_dir:
        try:
            os.makedirs(out_dir, exist_ok=True)
            text_path = os.path.join(out_dir, "_wm_text.txt")
        except OSError:
            text_path = None
    else:
        text_path = None
    if text_path is None:
        text_path = os.path.join(tempfile.gettempdir(), f"wm_{uuid.uuid4().hex}.txt")
    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(str(text)[:200])
    return text_path.replace("\\", "/")


def _build_drawtext(text, pos, frac, opacity, out_dim, out_dir=None):
    font_file = ffmpeg_font_path(prefer_arabic=True)
    font_size = max(10, int(round(max(out_dim, 1) * frac)))
    if font_file is None:
        raise ConversionError("no_font")
    if pos not in WATERMARK_POS_EXPR:
        pos = "br"
    x_expr, y_expr = WATERMARK_POS_EXPR[pos]
    opacity = max(0.05, min(1.0, float(opacity)))
    # On Windows, ffmpeg's filter-graph parser splits option values on ':' and
    # Python's argv mangling is unreliable — the combination of single quotes
    # PLUS a backslash-escaped colon (e.g. 'C\:/Windows/...') is what works.
    # The Arabic text itself is read from a UTF-8 file via textfile=.
    font_val = "'" + _drawtext_escape(font_file.replace("\\", "/")) + "'"
    text_val = "'" + _drawtext_escape(_wm_textfile(text, out_dir)) + "'"
    filter_part = (
        f"drawtext=fontfile={font_val}:textfile={text_val}:"
        f"fontsize={font_size}:fontcolor=white@{opacity:.2f}:"
        f"x={x_expr}:y={y_expr}:text_shaping=1"
    )
    return filter_part


def create_video_note_settings(settings, duration, width, height):
    start = _clampf(settings.get("start", 0), 0, duration)
    end = _clampf(settings.get("end", duration), 0, duration)
    if end - start < 0.3:
        if start + 0.3 <= duration:
            end = start + 0.3
        else:
            start = max(0.0, end - 0.3)
    if end - start > 60:
        end = start + 60
    seg_duration = end - start

    circle = settings.get("circle") or {}
    zoom = _clampf(settings.get("zoom", 1.0), 1.0, 4.0)
    pan = settings.get("pan") or {}

    size_raw = settings.get("size", 320)
    if isinstance(size_raw, str) and size_raw.lower() in ("original", "orig"):
        base = min(width if width > 0 else 320, height if height > 0 else 320)
        out_size = max(16, min(1080, base))
    else:
        out_size = int(_to_float(size_raw, 320))
        out_size = max(16, min(1080, out_size))
    out_size = out_size - (out_size % 2) if out_size % 2 else out_size
    if out_size < 2:
        out_size = 2

    base_cover = max(out_size / max(width, 1), out_size / max(height, 1))
    s = base_cover * zoom
    dw = max(width * s, 1)
    dh = max(height * s, 1)

    pan_x = _to_float(pan.get("x"))
    pan_y = _to_float(pan.get("y"))
    min_tx = out_size - dw
    min_ty = out_size - dh
    tx = max(min_tx, min(0.0, pan_x))
    ty = max(min_ty, min(0.0, pan_y))

    d_frac = _clampf(circle.get("d", 0.9), 0.2, 1.0)
    diameter = out_size * d_frac
    diameter = min(diameter, dw, dh)
    diameter = max(8.0, diameter)
    if diameter > out_size:
        diameter = out_size
    d_even = int(diameter)
    d_even -= d_even % 2
    if d_even < 2:
        d_even = 2
    diameter = float(d_even)

    max_off = (out_size - diameter) / 2.0
    cx = _to_float(circle.get("cx", 0.5)) * out_size
    cy = _to_float(circle.get("cy", 0.5)) * out_size
    cx = max(max_off, min(out_size - max_off, cx))
    cy = max(max_off, min(out_size - max_off, cy))

    crop_x = int(cx - diameter / 2.0 - tx)
    crop_y = int(cy - diameter / 2.0 - ty)
    crop_x = max(0, min(int(dw - diameter), crop_x))
    crop_y = max(0, min(int(dh - diameter), crop_y))

    return {
        "out_size": out_size,
        "seg_duration": seg_duration,
        "start": start,
        "end": end,
        "dw": dw,
        "dh": dh,
        "tx": tx,
        "ty": ty,
        "cx": cx,
        "cy": cy,
        "diameter": diameter,
        "crop_x": crop_x,
        "crop_y": crop_y,
    }


def _first_pass_filter(cfg_data, watermark=None, enabled_shape=True, out_dir=None):
    dw, dh = cfg_data["dw"], cfg_data["dh"]
    scale_w = int(dw / 2) * 2
    scale_h = int(dh / 2) * 2
    parts = [
        f"scale={scale_w}:{scale_h}",
        f"crop={int(cfg_data['diameter'])}:{int(cfg_data['diameter'])}:{cfg_data['crop_x']}:{cfg_data['crop_y']}",
        f"scale={cfg_data['out_size']}:{cfg_data['out_size']}:flags=lanczos",
        "setsar=1",
    ]
    if watermark:
        text = watermark.get("text") or ""
        pos = watermark.get("pos") or "br"
        frac = float(watermark.get("size", 0.06))
        opacity = float(watermark.get("opacity", 0.8))
        dt = _build_drawtext(text, pos, frac, opacity, cfg_data["out_size"], out_dir)
        parts.append(dt)
    return ",".join(parts)


def _build_overlay(out_size, cx, cy, radius, mask, frame):
    scale = 2
    big = out_size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cxc = cx * scale
    cyc = cy * scale
    r = radius * scale
    if mask:
        draw.rectangle((0, 0, big, big), fill=(0, 0, 0, 255))
        draw.ellipse((cxc - r, cyc - r, cxc + r, cyc + r), fill=(0, 0, 0, 0))
    if frame and frame.get("enabled"):
        color = frame.get("color") or "#ffffff"
        try:
            color = color.lstrip("#")
            r_, g_, b_ = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        except (ValueError, IndexError):
            r_, g_, b_ = 255, 255, 255
        width = float(frame.get("width") or 4)
        half = width * scale / 2.0
        outer = int(r + half)
        inner = int(max(0, r - half))
        draw.ellipse((cxc - outer, cyc - outer, cxc + outer, cyc + outer), fill=(r_, g_, b_, 255))
        draw.ellipse((cxc - inner, cyc - inner, cxc + inner, cyc + inner), fill=(0, 0, 0, 0))
    return img.resize((out_size, out_size), Image.LANCZOS)


async def create_video_note(input_path, out_path, settings, progress_cb=None, source_url=None, engine=None):
    info = await probe(input_path)
    if not info["has_video"]:
        raise ConversionError("no_video_stream")
    if info["duration"] <= 0:
        raise ConversionError("empty")
    if info["duration"] > cfg.max_video_duration:
        raise ConversionError("video_too_long")
    duration = info["duration"]
    width = info["width"] or 1
    height = info["height"] or 1

    g = create_video_note_settings(settings, duration, width, height)
    engine = (engine or cfg.media_engine).lower()

    if engine == "cloudflare":
        if not source_url:
            raise ConversionError("cloudflare_not_configured")
        from bot.services.cloudflare import transform_video_note
        await transform_video_note(
            source_url,
            start=g["start"], duration=g["seg_duration"], size=g["out_size"],
            out_path=out_path, progress_cb=progress_cb,
        )
        return {
            "path": out_path,
            "duration": g["seg_duration"],
            "duration_ms": g["seg_duration"],
            "length": g["out_size"],
            "label": "فيديو دائري",
            "filename": os.path.basename(out_path),
        }

    watermark = (settings.get("watermark") or {}) if settings.get("watermark", {}).get("enabled") else None

    first = os.path.join(os.path.dirname(out_path), "_note_first.mp4")
    vf = _first_pass_filter(g, watermark, out_dir=os.path.dirname(out_path))
    cmd = [
        "ffmpeg", "-i", input_path,
        "-ss", f"{g['start']:.3f}", "-t", f"{g['seg_duration']:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an",
        "-movflags", "+faststart", first,
    ]
    try:
        await run_ffmpeg(cmd, duration=g["seg_duration"], progress_cb=progress_cb)
    except Exception as exc:
        raise ConversionError(f"ffmpeg: {str(exc)[:300]}")

    mask = bool(settings.get("mask", False))
    frame = settings.get("frame") or {}
    if mask or frame.get("enabled"):
        overlay = os.path.join(os.path.dirname(out_path), "_overlay.png")
        img = _build_overlay(g["out_size"], g["cx"], g["cy"], g["diameter"] / 2.0, mask, frame)
        img.save(overlay)
        cmd2 = [
            "ffmpeg", "-i", first, "-loop", "1", "-i", overlay,
            "-filter_complex",
            "[1:v]format=rgba[ov];[0:v][ov]overlay=0:0:shortest=1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-an", "-movflags", "+faststart", out_path,
        ]
        await run_ffmpeg(cmd2, duration=g["seg_duration"], progress_cb=progress_cb)
        for p in (first, overlay):
            try:
                os.remove(p)
            except OSError:
                pass
    else:
        os.replace(first, out_path)

    return {
        "path": out_path,
        "duration": g["seg_duration"],
        "duration_ms": g["seg_duration"],
        "length": g["out_size"],
        "label": "فيديو دائري",
        "filename": os.path.basename(out_path),
    }


async def to_gif(input_path, out_path, start=0.0, duration=None, progress_cb=None):
    info = await probe(input_path)
    if not info["has_video"]:
        raise ConversionError("no_video_stream")
    total = info["duration"] or 0
    start = max(0.0, min(float(start or 0), max(0.0, total - 0.2)))
    seg = duration
    if seg is None or seg <= 0:
        seg = min(cfg.max_gif_duration, max(0.1, total - start))
    seg = min(seg, cfg.max_gif_duration)
    if seg <= 0:
        raise ConversionError("unsupported_duration")
    width = info["width"] or 1
    height = info["height"] or 1
    target_w = min(cfg.max_gif_width, width)
    cmd = [
        "ffmpeg", "-i", input_path,
        "-ss", f"{start:.3f}", "-t", f"{seg:.3f}",
        "-vf", f"fps=12,scale={target_w}:-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0", out_path,
    ]
    await run_ffmpeg(cmd, duration=seg, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": seg,
        "duration_ms": seg,
        "label": "تحويل إلى GIF",
        "filename": "animated.gif",
    }


async def convert_video_format(input_path, out_path, fmt, progress_cb=None):
    info = await probe(input_path)
    if not info["has_video"]:
        raise ConversionError("no_video_stream")
    if fmt not in VIDEO_FMT_OPTS:
        raise ConversionError("unsupported_format")
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    cmd = [
        "ffmpeg", "-i", input_path,
        "-map", "0:v?", "-map", "0:a?",
        *VIDEO_FMT_OPTS[fmt], out_path,
    ]
    try:
        await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    except Exception:
        if fmt == "webm":
            fallback = ["-c:v", "libvpx", "-crf", "10", "-b:v", "1M", "-c:a", "libvorbis", "-q:a", "5"]
            cmd = [
                "ffmpeg", "-i", input_path,
                "-map", "0:v?", "-map", "0:a?",
                *fallback, out_path,
            ]
            await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
        else:
            raise
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": f"تحويل إلى {fmt.upper()}",
        "filename": f"video_converted.{fmt}",
    }


async def add_video_watermark(input_path, out_path, text, pos, frac, opacity, progress_cb=None):
    info = await probe(input_path)
    if not info["has_video"]:
        raise ConversionError("no_video_stream")
    if not (text or "").strip():
        raise ConversionError("empty_text")
    duration = info["duration"] if info["duration"] and info["duration"] > 0 else None
    out_dim = max(info["width"] or 320, info["height"] or 320)
    vf = _build_drawtext(text, pos, frac, opacity, out_dim, os.path.dirname(out_path))
    cmd = [
        "ffmpeg", "-i", input_path,
        "-map", "0:v?", "-map", "0:a?",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", out_path,
    ]
    try:
        await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    except Exception:
        cmd = [
            "ffmpeg", "-i", input_path,
            "-map", "0:v?", "-map", "0:a?",
            "-vf", vf.replace(":text_shaping=1", ""),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", out_path,
        ]
        await run_ffmpeg(cmd, duration=duration, progress_cb=progress_cb)
    return {
        "path": out_path,
        "duration": duration,
        "duration_ms": duration or 0,
        "label": "إضافة علامة مائية",
        "filename": "watermarked.mp4",
    }


def watermark_frac(size_key):
    return WATERMARK_SIZE_FRAC.get(str(size_key).lower(), 0.06)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))