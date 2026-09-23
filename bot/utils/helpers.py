import os
import re
import shutil
import uuid
from datetime import datetime, timezone


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def even(value):
    v = int(value)
    if v < 2:
        return 2
    return v - (v % 2)


def human_size(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def safe_name(name):
    name = os.path.basename(str(name or "file"))
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name[:120] or "file"


def ext_of(path):
    name = os.path.basename(str(path))
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def new_id():
    return uuid.uuid4().hex


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def make_job_dir(label=""):
    root = _work_root()
    ensure_dir(root)
    d = os.path.join(root, f"{label}_{new_id()}" if label else new_id())
    ensure_dir(d)
    return d


_work_root_value = None


def _work_root():
    global _work_root_value
    if _work_root_value is None:
        from bot.config import cfg
        _work_root_value = cfg.work_dir
    return _work_root_value


def cleanup_tree(path):
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def cleanup_file(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def fs_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0