from __future__ import annotations

import base64
import json

from bot.auth.handoff import Handoff


def encode_handoff(handoff: Handoff) -> str:
    """Compact URL-safe reference for the Telegram startapp parameter.

    The deployed Mini App splits start_param on underscores and treats the
    last segment as the bot username. The token therefore must not contain
    underscores; token_urlsafe() may emit them, so normalise to urlsafe hex.
    The reference is only a lookup key. The API still validates Telegram's
    signature and checks that the Redis record belongs to that user.
    """
    token = handoff.token.replace("_", "")
    raw = json.dumps(
        {"t": token, "u": handoff.uid, "s": handoff.slot},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_handoff(reference: str) -> dict | None:
    try:
        padded = reference + "=" * (-len(reference) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if not isinstance(data, dict) or not data.get("t"):
            return None
        return data
    except Exception:
        return None