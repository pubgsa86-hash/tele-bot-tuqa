"""Per-user navigation stack and last-operation memory.

The bot keeps a lightweight screen stack per user so that "back" returns
exactly one step (and not always to /start). The last operation is also
remembered so "convert again" can repeat it without asking the user again.
"""
import threading

_SCREENS = {}
_LAST_OP = {}
_LOCK = threading.Lock()


def push(user_id, screen):
    if not screen:
        return
    with _LOCK:
        stack = _SCREENS.setdefault(user_id, [])
        if stack and stack[-1] == screen:
            return
        stack.append(screen)


def top(user_id):
    with _LOCK:
        stack = _SCREENS.get(user_id)
        return stack[-1] if stack else None


def pop(user_id):
    with _LOCK:
        stack = _SCREENS.get(user_id)
        if not stack:
            return None
        stack.pop()
        if stack:
            return stack[-1]
        _SCREENS.pop(user_id, None)
        return None


def reset(user_id):
    with _LOCK:
        _SCREENS.pop(user_id, None)


def enter_result(user_id):
    with _LOCK:
        stack = _SCREENS.setdefault(user_id, [])
        if stack and stack[-1] == "result":
            return
        stack.append("result")


def record_op(user_id, op):
    if op:
        with _LOCK:
            _LAST_OP[user_id] = op


def last_op(user_id):
    with _LOCK:
        return _LAST_OP.get(user_id)


def drop(user_id):
    with _LOCK:
        _SCREENS.pop(user_id, None)
        _LAST_OP.pop(user_id, None)


def sweep(limit=1000):
    with _LOCK:
        if len(_SCREENS) > limit:
            for uid in list(_SCREENS)[: len(_SCREENS) - limit]:
                _SCREENS.pop(uid, None)