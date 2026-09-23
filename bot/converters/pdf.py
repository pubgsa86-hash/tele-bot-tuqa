import asyncio
import os
import shutil
import textwrap

from bot.converters.ffmpeg import ConversionError
from bot.converters.fonts import find_image_font_path

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "gif"}
DOC_EXTS = {"doc", "docx"}
TXT_EXTS = {"txt", "log", "md"}


async def to_pdf(input_path, out_path, ext=None, progress_cb=None):
    ext = (ext or os.path.splitext(input_path)[1].lstrip(".")).lower()
    if ext in IMAGE_EXTS:
        await _images_to_pdf(input_path, out_path)
    elif ext in TXT_EXTS:
        await asyncio.to_thread(_text_to_pdf, input_path, out_path)
    elif ext in DOC_EXTS:
        await _soffice_to_pdf(input_path, out_path)
    else:
        raise ConversionError("unsupported_pdf_source")
    if progress_cb:
        await progress_cb(100)
    return {
        "path": out_path,
        "duration": 0,
        "duration_ms": 0,
        "label": "تحويل إلى PDF",
        "filename": "output.pdf",
    }


async def _images_to_pdf(input_path, out_path):
    def work():
        import img2pdf
        with open(out_path, "wb") as f:
            f.write(img2pdf.convert([input_path]))

    await asyncio.to_thread(work)


def _display_text(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def _read_text(path):
    for enc in ("utf-8", "utf-8-sig", "cp1256", "windows-1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, OSError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _text_to_pdf(input_path, out_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rlcanvas

    font_path = find_image_font_path(prefer_arabic=True)
    if not font_path:
        raise ConversionError("no_font")
    font_name = "DocFont"
    pdfmetrics.registerFont(TTFont(font_name, font_path))

    raw = _read_text(input_path)
    page_w, page_h = A4
    margin = 48
    font_size = 12
    leading = font_size * 1.5
    chars_per_line = max(10, int((page_w - 2 * margin) / (font_size * 0.62)))
    c = rlcanvas.Canvas(out_path, pagesize=A4)
    y = page_h - margin
    lines = []
    for para in raw.splitlines():
        para = para.strip()
        if not para:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(para, chars_per_line) or [""])
    for line in lines:
        if y < margin + font_size:
            c.showPage()
            y = page_h - margin
        try:
            c.setFont(font_name, font_size)
            c.drawString(margin, y, _display_text(line))
        except Exception:
            c.drawString(margin, y, line.encode("ascii", "replace").decode("ascii"))
        y -= leading
    c.save()


async def _soffice_to_pdf(input_path, out_path):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ConversionError("libreoffice_missing")
    out_dir = os.path.dirname(out_path)
    expected = os.path.join(out_dir, os.path.splitext(os.path.basename(input_path))[0] + ".pdf")
    proc = await asyncio.create_subprocess_exec(
        soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, input_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise ConversionError("libreoffice_failed")
    if not os.path.isfile(expected):
        raise ConversionError("libreoffice_failed")
    os.replace(expected, out_path)