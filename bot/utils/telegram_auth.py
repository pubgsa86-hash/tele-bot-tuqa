import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from bot.config import cfg


def _derive_secret_key(bot_token):
    return hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()


def validate_init_data(init_data):
    if not init_data or not cfg.bot_token:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = _derive_secret_key(cfg.bot_token)
    computed = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    try:
        user = json.loads(parsed.get("user", "{}"))
    except (TypeError, ValueError):
        user = {}
    return {
        "user_id": user.get("id"),
        "username": user.get("username"),
        "init_data": init_data,
    }