import glob
import os


def _found_fonts():
    bases = [
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "C:/Windows/Fonts",
    ]
    found = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        try:
            for pattern in ("**/*.ttf", "**/*.ttc", "*.ttf", "*.ttc"):
                for p in glob.glob(os.path.join(base, pattern)):
                    if not os.path.isfile(p):
                        continue
                    name = os.path.basename(p).lower()
                    if any(x in name for x in ("bold", "light", "medium", "black", "italic", "oblique")):
                        continue
                    found.append(p)
        except Exception:
            continue
    return found


def _pick(fonts, keywords):
    for kw in keywords:
        for p in fonts:
            if kw in os.path.basename(p).lower():
                return p
    return None


def find_font_path(prefer_arabic=False):
    fonts = _found_fonts()
    if not fonts:
        return None
    if prefer_arabic:
        p = _pick(fonts, [
            "notonaskharabic", "notosansarabic", "amiri",
            "scheherazade", "kacstar", "dejavusans",
        ])
        if p:
            return p
    p = _pick(fonts, ["dejavusans", "arial", "liberationsans", "notosans"])
    if p:
        return p
    return fonts[0]


def find_image_font_path(prefer_arabic=False):
    return find_font_path(prefer_arabic)


def ffmpeg_font_path(prefer_arabic=False):
    path = find_font_path(prefer_arabic)
    if not path:
        return None
    path = path.replace("\\", "/")
    return path