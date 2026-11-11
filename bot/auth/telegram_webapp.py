from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import unquote


class InitDataError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramWebAppUser:
    telegram_id: int
    username: str | None


def verify_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 300,
) -> TelegramWebAppUser:
    """Verify Telegram WebApp initData and return its signed user.

    The API must never establish identity from request JSON; this signed
    value is the only trusted source for telegram_id and username.
    """
    if not init_data:
        raise InitDataError("missing initData")

    try:
        pairs = dict(part.split("=", 1) for part in init_data.split("&"))
        parsed = {key: unquote(value) for key, value in pairs.items()}
    except Exception as exc:
        raise InitDataError("malformed initData") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("invalid auth_date") from exc
    if auth_date <= 0 or time.time() - auth_date > max_age_seconds:
        raise InitDataError("stale initData")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("invalid signature")

    raw_user = parsed.get("user")
    if not raw_user:
        raise InitDataError("initData has no user")
    try:
        user = json.loads(raw_user)
        telegram_id = int(user["id"])
    except Exception as exc:
        raise InitDataError("invalid telegram user") from exc
    if telegram_id <= 0:
        raise InitDataError("invalid telegram user id")
    return TelegramWebAppUser(telegram_id=telegram_id, username=user.get("username"))