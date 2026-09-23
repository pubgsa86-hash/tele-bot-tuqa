import time
from dataclasses import dataclass, field

from bot.utils.helpers import new_id


@dataclass
class PendingItem:
    tid: str
    user_id: int
    kind: str
    file_id: str
    file_name: str
    mime: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    created_at: float = field(default_factory=time.time)
    ttl: float = 3600.0


_PENDING: dict = {}
_BY_USER: dict = {}  # user_id -> set(tid)


def push_pending(user_id, kind, file_id, file_name, mime,
                 duration=0.0, width=0, height=0) -> str:
    tid = new_id()
    _PENDING[tid] = PendingItem(
        tid=tid, user_id=user_id, kind=kind, file_id=file_id,
        file_name=file_name, mime=mime, duration=duration,
        width=width, height=height,
    )
    _BY_USER.setdefault(user_id, set()).add(tid)
    return tid


def touch_pending(tid):
    item = _PENDING.get(tid)
    if item is not None:
        item.created_at = time.time()


def get_pending(tid):
    item = _PENDING.get(tid)
    if item is None:
        return None
    if time.time() - item.created_at > item.ttl:
        drop_pending(tid)
        return None
    return item


def drop_pending(tid):
    item = _PENDING.pop(tid, None)
    if item is not None:
        _BY_USER.get(item.user_id, set()).discard(tid)


def drop_user(user_id):
    for tid in _BY_USER.pop(user_id, set()):
        _PENDING.pop(tid, None)


def sweep_pending():
    now = time.time()
    for tid, item in list(_PENDING.items()):
        if now - item.created_at > item.ttl:
            drop_pending(tid)