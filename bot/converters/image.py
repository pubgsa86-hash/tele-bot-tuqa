import asyncio
import inspect
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.converters.ffmpeg import ConversionError
from bot.converters.fonts import find_image_font_path

POSITION_POINTS = {
    "tl": "la",
    "tc": "ha",
    "tr": "ra",
    "ml": "lm",
    "c": "c",
    "mr": "rm",
    "bl": "lb",
    "bc": "hb",
    "br": "rb",
}

POSITION_KEYS = list(POSITION_POINTS.keys())


def _load(path):
    img = Image.open(path)
    img.load()
    return img


async def _in_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)


def _probe_progress_cb(progress_cb, steps=3):
    async def cb(pct):
        if progress_cb:
            res = progress_cb(pct)
            if inspect.isawaitable(res):
                await res
    return cb


async def to_png(input_path, out_path, progress_cb=None):
    def work():
        img = _load(input_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(out_path, "PNG", optimize=True)

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": "تحويل إلى PNG",
        "filename": f"image.png",
    }


async def to_sticker(input_path, out_path, kind="webp", progress_cb=None):
    kind = str(kind).lower()
    if kind not in ("webp", "png"):
        kind = "webp"

    def work():
        img = _load(input_path)
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.thumbnail((512, 512), Image.LANCZOS)
        if img.mode == "RGB":
            img = img.convert("RGBA")
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        canvas.paste(img, ((512 - img.width) // 2, (512 - img.height) // 2), img)
        if kind == "png":
            canvas.save(out_path, "PNG", optimize=True)
        else:
            canvas.save(out_path, "WEBP", quality=95, method=6)

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": "تحويل إلى ملصق",
        "filename": f"sticker.{kind}",
    }


async def sticker_to_png(input_path, out_path, progress_cb=None):
    def work():
        img = _load(input_path)
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.save(out_path, "PNG", optimize=True)

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": "ملصق → صورة",
        "filename": "sticker.png",
    }


async def resize_image(input_path, out_path, width, height, mode="cover", progress_cb=None):
    width = max(16, int(width))
    height = max(16, int(height))

    def work():
        img = _load(input_path)
        target = (width, height)
        if mode == "cover":
            img2 = ImageOps.fit(img, target, method=Image.LANCZOS, centering=(0.5, 0.5))
        else:
            img.load()
            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")
            background = (0, 0, 0, 0) if img.mode == "RGBA" else (255, 255, 255)
            img2 = ImageOps.pad(img, target, method=Image.LANCZOS, color=background, centering=(0.5, 0.5))
        out_ext = os.path.splitext(out_path)[1].lower()
        if out_ext in (".jpg", ".jpeg"):
            if img2.mode not in ("RGB", "L"):
                img2 = img2.convert("RGB")
            img2.save(out_path, "JPEG", quality=95)
        else:
            if img2.mode not in ("RGB", "RGBA"):
                img2 = img2.convert("RGBA")
            img2.save(out_path, "PNG", optimize=True)

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": f"تغيير الحجم {width}×{height}",
        "filename": f"resized_{width}x{height}.png",
    }


async def convert_image_format(input_path, out_path, fmt, progress_cb=None):
    fmt = str(fmt).lower()

    def work():
        img = _load(input_path)
        if fmt == "png":
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(out_path, "PNG", optimize=True)
        elif fmt == "jpg":
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(out_path, "JPEG", quality=95)
        elif fmt == "webp":
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(out_path, "WEBP", quality=90, method=6)
        else:
            raise ConversionError("unsupported_format")

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": f"تحويل إلى {fmt.upper()}",
        "filename": f"image_converted.{fmt}",
    }


def _display_text(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def _load_font(size):
    path = find_image_font_path(prefer_arabic=True)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


async def add_image_watermark(input_path, out_path, text, pos, frac, opacity, progress_cb=None):
    if not (text or "").strip():
        raise ConversionError("empty_text")
    if pos not in POSITION_KEYS:
        pos = "br"

    def work():
        img = _load(input_path)
        if img.mode not in ("RGBA",):
            img = img.convert("RGBA")
        w, h = img.size
        font_size = max(12, int(round(min(w, h) * max(0.02, min(0.2, float(frac))))))
        font = _load_font(font_size)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        content = _display_text(text)
        bbox = draw.textbbox((0, 0), content, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = int(font_size * 0.6)
        x_of = {
            "tl": margin, "tc": (w - tw) // 2, "tr": w - tw - margin,
            "ml": margin, "c": (w - tw) // 2, "mr": w - tw - margin,
            "bl": margin, "bc": (w - tw) // 2, "br": w - tw - margin,
        }
        y_of = {
            "tl": margin, "tc": margin, "tr": margin,
            "ml": (h - th) // 2, "c": (h - th) // 2, "mr": (h - th) // 2,
            "bl": h - th - margin, "bc": h - th - margin, "br": h - th - margin,
        }
        x0 = x_of[pos] - bbox[0]
        y0 = y_of[pos] - bbox[1]
        alpha = int(max(30, min(255, 255 * float(opacity))))
        draw.text((x0, y0), content, font=font, fill=(255, 255, 255, alpha),
                  stroke_width=max(1, font_size // 12), stroke_fill=(0, 0, 0, min(alpha, 140)))
        out = Image.alpha_composite(img, overlay)
        out_ext = os.path.splitext(out_path)[1].lower()
        if out_ext in (".jpg", ".jpeg"):
            out.convert("RGB").save(out_path, "JPEG", quality=95)
        else:
            out.save(out_path, "PNG", optimize=True)

    await _in_thread(work)
    await _probe_progress_cb(progress_cb)(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": "إضافة علامة مائية",
        "filename": "watermarked.png",
    }