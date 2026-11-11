from __future__ import annotations

import base64
import json

from shared.auth.handoff import Handoff


def encode_handoff(handoff: Handoff) -> str:
    """Compact URL-safe reference for the Telegram startapp parameter.

    The token is hex, so it contains no underscores. The reference is only a
    lookup key; the API still validates Telegram's signed initData and checks
    that the server-side handoff belongs to that user.
    """
    raw = json.dumps(
        {"t": handoff.token, "u": handoff.uid, "s": handoff.slot},
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