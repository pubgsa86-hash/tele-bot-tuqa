from collections import OrderedDict

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.config import cfg

BAR_FILL = "█"
BAR_EMPTY = "░"


def progress_bar(pct, width=12):
    pct = max(0, min(100, int(pct)))
    filled = int(round(width * pct / 100))
    return BAR_FILL * filled + BAR_EMPTY * (width - filled)


def _b(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def _id_or_x(pid):
    return pid or "x"


# ------------------------------------------------------------------
# Format / option labels
# ------------------------------------------------------------------

VIDEO_FORMAT_LABELS = OrderedDict([
    ("mp4", "MP4"),
    ("mkv", "MKV"),
    ("webm", "WEBM"),
    ("mov", "MOV"),
    ("avi", "AVI"),
])

AUDIO_FORMAT_LABELS = OrderedDict([
    ("mp3", "MP3"),
    ("wav", "WAV"),
    ("ogg", "OGG"),
    ("m4a", "M4A"),
])

IMAGE_FORMAT_LABELS = OrderedDict([
    ("png", "PNG"),
    ("jpg", "JPG"),
    ("webp", "WEBP"),
])

STICKER_TYPE_LABELS = OrderedDict([
    ("webp", "ملصق WEBP"),
    ("png", "ملصق PNG"),
])

RESIZE_SIZE_LABELS = OrderedDict([
    ("512", "512×512"),
    ("1024", "1024×1024"),
    ("1920x1080", "1920×1080"),
    ("1080x1920", "1080×1920"),
])

RESIZE_MODE_LABELS = OrderedDict([
    ("contain", "📦 الحفاظ على الأبعاد"),
    ("cover", "✂️ قص لملء الإطار"),
])

WATERMARK_POSITION_LABELS = OrderedDict([
    ("tl", "أعلى يسار"), ("tc", "أعلى وسط"), ("tr", "أعلى يمين"),
    ("ml", "منتصف يسار"), ("mc", "الوسط"), ("mr", "منتصف يمين"),
    ("bl", "أسفل يسار"), ("bc", "أسفل وسط"), ("br", "أسفل يمين"),
])

WATERMARK_SIZE_OPTIONS = OrderedDict([
    ("small", "صغير"), ("medium", "متوسط"),
    ("large", "كبير"), ("xlarge", "كبير جدًا"),
])

WATERMARK_OPACITY_OPTIONS = OrderedDict([
    ("light", "خفيف"), ("medium", "متوسط"),
    ("strong", "قوي"), ("full", "كامل"),
])


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 أهلاً بك في <b>بوت محوّل الوسائط</b> 🎬\n\n"
    "أرسل لي فيديو أو صورة أو صوتًا أو ملفًا وسأساعدك في تحويله إلى الصيغة التي تريدها.\n\n"
    "⭐ أهم ميزة: <b>تحويل الفيديو إلى فيديو دائري (Video Note)</b> مع محرر احترافي!\n\n"
    "👇 اختر ما تريد فعله:"
)

HELP_TEXT = (
    "❓ <b>المساعدة</b>\n\n"
    "الأوامر:\n"
    "• <b>/start</b> — فتح القائمة الرئيسية\n"
    "• <b>/menu</b> — فتح القائمة\n"
    "• <b>/help</b> — عرض هذه المساعدة\n"
    "• <b>/cancel</b> — إنهاء الجلسة\n\n"
    "• أرسل <b>فيديو</b> → فيديو دائري، استخراج الصوت، GIF، تغيير الصيغة، علامة مائية.\n"
    "• أرسل <b>صوت (MP3)</b> → بصمة صوتية أو تغيير الصيغة.\n"
    "• أرسل <b>بصمة صوتية</b> → MP3.\n"
    "• أرسل <b>صورة</b> → ملصق، PNG، تغيير الحجم، علامة مائية، تغيير الصيغة.\n"
    "• أرسل <b>ملصقًا</b> → صورة.\n"
    "• أرسل <b>مستندًا</b> → PDF.\n\n"
    "كل شاشة تحتوي زر <b>🔙 رجوع</b> للعودة لخطوة واحدة، وزر <b>🚪 إنهاء الجلسة</b> لبدء جديد.\n\n"
    f"⚙️ الحد الأقصى لحجم الملف: {cfg.max_file_size // (1024 * 1024)}MB\n"
    f"⏱ الحد الأقصى لمدة الفيديو: {cfg.max_video_duration} ثانية\n"
)

SETTINGS_TEXT = (
    "⚙️ <b>الإعدادات</b>\n\n"
    f"• محرك معالجة الفيديو: <b>{cfg.media_engine.capitalize()}</b>\n"
    f"• الحد الأقصى لحجم الملف: <b>{cfg.max_file_size // (1024 * 1024)}MB</b>\n"
    f"• الحد الأقصى لمدة الفيديو: <b>{cfg.max_video_duration} ثانية</b>\n"
    f"• مدة الفيديو الدائري: <b>60 ثانية كحد أقصى</b>\n\n"
    "يمكنك مسح سجل التحويلات من زر «التحويلات الأخيرة»."
)

MSG_UNAVAILABLE = "⚠️ الخدمة غير متاحة حاليًا، حاول لاحقًا."
MSG_HISTORY_EMPTY = "📭 لا توجد تحويلات مسجلة بعد."
MSG_HISTORY_CLEARED = "🗑 تم مسح سجل التحويلات."

MSG_ON_VIDEO = "🎬 تم استلام الفيديو ✅\n\nماذا تريد أن تفعل به؟"
MSG_ON_AUDIO = "🎵 تم استلام الصوت ✅\n\nماذا تريد أن تفعل به؟"
MSG_ON_VOICE = "🎤 تم استلام البصمة الصوتية ✅\n\nماذا تريد أن تفعل به؟"
MSG_ON_IMAGE = "🖼 تم استلام الصورة ✅\n\nماذا تريد أن تفعل بها؟"
MSG_ON_STICKER = "🎟 تم استلام الملصق ✅\n\nماذا تريد أن تفعل به؟"
MSG_ON_DOC = "📄 تم استلام المستند ✅\n\nماذا تريد أن تفعل به؟"

MSG_PROCESSING = "⏳ جاري معالجة الملف، انتظر قليلًا..."
MSG_QUEUED = "📥 تمت إضافة المهمة إلى قائمة الانتظار."
MSG_CONVERTING = "⏳ جاري التحويل...\n\n{bar}\n<b>{pct}%</b>"
MSG_SUCCESS = "✅ <b>تم التحويل بنجاح!</b>"
MSG_ERROR = "❌ حدث خطأ أثناء التحويل."
MSG_CANCEL = "❌ تم إلغاء العملية."
MSG_ENDED = "✅ <b>تم إنهاء الجلسة.</b>\n\nأرسل ملفًا جديدًا لبدء تحويل جديد، أو اختر من القائمة:"

MSG_ASK_TEXT = "✍️ أرسل الآن نص العلامة المائية:"
MSG_ASK_POS = "📍 اختر موضع العلامة المائية:"
MSG_ASK_SIZE = "🔠 اختر حجم العلامة المائية:"
MSG_ASK_OPACITY = "🌫 اختر شفافية العلامة المائية:"
MSG_ASK_FORMAT = "🔄 اختر الصيغة النهائية:"
MSG_ASK_RESIZE_SIZE = "📐 اختر الحجم النهائي:"
MSG_ASK_RESIZE_MODE = "🧩 اختر طريقة المعالجة:"
MSG_ASK_STICKER_TYPE = "🎟 اختر نوع الملصق:"

ERR_MESSAGES = {
    "no_video_input": "الملف المطلوب لم يعد متاحًا، أرسل الفيديو مجددًا.",
    "no_audio_input": "الملف المطلوب لم يعد متاحًا، أرسل الصوت مجددًا.",
    "no_image_input": "الملف المطلوب لم يعد متاحًا، أرسل الصورة مجددًا.",
    "expired_session": "انتهت صلاحية الملف (مر عليه وقت طويل). أرسله مجددًا لمواصلة تحويله.",
    "too_large": "حجم الملف أكبر من الحد المسموح به.",
    "empty": "الملف فارغ أو تالف.",
    "unsupported": "الصيغة غير مدعومة.",
    "libreoffice_missing": "محرك التحويل غير متوفر حاليًا.",
    "no_text": "نص العلامة المائية فارغ.",
    "cloudflare_not_configured": "محرك معالجة الفيديو السحابي غير مكوّن حاليًا.",
    "default": "حدث خطأ غير متوقع، حاول مرة أخرى.",
}


# ------------------------------------------------------------------
# Keyboards
# ------------------------------------------------------------------

def main_menu_kb():
    """القائمة الرئيسية — يظهر زر الرجوع في القوائم الفرعية فقط."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🎬 الفيديو", "m:video"), _b("🎵 الصوت", "m:audio")],
        [_b("🖼 الصور", "m:image"), _b("📄 الملفات", "m:doc")],
        [_b("📋 التحويلات الأخيرة", "m:hist"), _b("⚙️ الإعدادات", "m:sett")],
        [_b("❓ المساعدة", "m:help")],
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🔙 رجوع", "m:back")],
    ])


def home_end_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def result_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🔄 تحويل مرة أخرى", "m:again")],
        [_b("✏️ تعديل الإعدادات", "m:edit")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🔙 رجوع", "m:back")],
    ])


def video_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("⭕ تخصيص الفيديو الدائري 🎨", f"act:vnote:{tid}")],
        [_b("🎵 استخراج الصوت", f"act:va:{tid}"), _b("🎞 تحويل إلى GIF", f"act:gif:{tid}")],
        [_b("🔄 تغيير الصيغة", f"act:vfmt:{tid}"), _b("💧 علامة مائية", f"act:vwm:{tid}")],
        [_b("🔇 إزالة الصوت", f"act:vna:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def audio_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🎤 تحويل إلى بصمة صوتية", f"act:a2voice:{tid}")],
        [_b("🔄 تغيير الصيغة", f"act:afmt:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def voice_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🎵 تحويل إلى MP3", f"act:v2mp3:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def image_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🎟 تحويل إلى ملصق", f"act:i2stk:{tid}"), _b("🖼 تحويل إلى PNG", f"act:i2png:{tid}")],
        [_b("📐 تغيير الحجم", f"act:irz:{tid}"), _b("💧 علامة مائية", f"act:iwm:{tid}")],
        [_b("🔄 تغيير الصيغة", f"act:ifmt:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def sticker_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🖼 تحويل الملصق إلى صورة", f"act:s2img:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def doc_actions_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("📄 تحويل إلى PDF", f"act:d2pdf:{tid}")],
        [_b("🏠 القائمة الرئيسية", "m:home"), _b("🚪 إنهاء الجلسة", "m:end")],
        [_b("🔙 رجوع", "m:back")],
    ])


def format_kb(kind, tid=None):
    tid = _id_or_x(tid)
    labels = {
        "video": VIDEO_FORMAT_LABELS,
        "audio": AUDIO_FORMAT_LABELS,
        "image": IMAGE_FORMAT_LABELS,
    }.get(kind, VIDEO_FORMAT_LABELS)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"run:fconv:{kind}:{key}:{tid}") for key, label in labels.items()],
        [_b("🔙 رجوع", "m:back")],
    ])


def resize_size_kb(tid=None):
    tid = _id_or_x(tid)
    items = list(RESIZE_SIZE_LABELS.items())
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"rzs:{size}:{tid}") for size, label in items[i:i + 2]] for i in range(0, len(items), 2)
    ] + [
        [_b("🔙 رجوع", "m:back")],
    ])


def resize_mode_kb(tid, size):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"rzm:{mode}:{size}:{tid}") for mode, label in RESIZE_MODE_LABELS.items()],
        [_b("🔙 رجوع", "m:back")],
    ])


def sticker_type_kb(tid=None):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"stk:{key}:{tid}") for key, label in STICKER_TYPE_LABELS.items()],
        [_b("🔙 رجوع", "m:back")],
    ])


def wm_pos_kb(tid):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(WATERMARK_POSITION_LABELS[p], f"wmpos:{p}:{tid}") for p in ("tl", "tc", "tr")],
        [_b(WATERMARK_POSITION_LABELS[p], f"wmpos:{p}:{tid}") for p in ("ml", "mc", "mr")],
        [_b(WATERMARK_POSITION_LABELS[p], f"wmpos:{p}:{tid}") for p in ("bl", "bc", "br")],
        [_b("🔙 رجوع", "m:back")],
    ])


def wm_size_kb(tid):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"wmsize:{key}:{tid}") for key, label in WATERMARK_SIZE_OPTIONS.items()],
        [_b("🔙 رجوع", "m:back")],
    ])


def wm_opacity_kb(tid):
    tid = _id_or_x(tid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b(label, f"wmop:{key}:{tid}") for key, label in WATERMARK_OPACITY_OPTIONS.items()],
        [_b("🔙 رجوع", "m:back")],
    ])