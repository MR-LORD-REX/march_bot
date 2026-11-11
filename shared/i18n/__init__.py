"""Central message catalog.

Messages live in ``locales/<language>.json`` so adding a language is a data
change, not a code change. Missing keys fall back to English and then to the
key itself; a missing translation must never break a handler.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"
LANGUAGE_NAMES = {"en": "English"}

_cache: dict[str, dict[str, str]] = {}
_loaded = False


def _flatten(value: Any, prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key.startswith("_"):
                continue
            flattened.update(_flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        flattened[prefix] = "\n".join(str(item) for item in value)
    elif isinstance(value, (str, int, float, bool)):
        flattened[prefix] = str(value)
    return flattened


def _load() -> None:
    global _loaded
    if _loaded:
        return
    for path in LOCALES_DIR.glob("*.json"):
        language = path.stem.lower()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _cache[language] = _flatten(payload)
        except Exception:
            logger.exception("could not load locale %s", path.name)
    _cache.setdefault(DEFAULT_LANGUAGE, {})
    _loaded = True


def available_languages() -> dict[str, str]:
    _load()
    languages = {"en": LANGUAGE_NAMES["en"]}
    for language in sorted(_cache):
        if language not in languages:
            languages[language] = language.upper()
    return languages


def normalize_language(language: str | None) -> str:
    _load()
    value = (language or DEFAULT_LANGUAGE).strip().lower().replace("_", "-")
    if value in _cache:
        return value
    base = value.split("-", 1)[0]
    return base if base in _cache else DEFAULT_LANGUAGE


def t(key: str, lang: str | None = DEFAULT_LANGUAGE, **params: Any) -> str:
    """Return a localized message, falling back to English and then the key.

    Formatting errors also fall back to the raw template: a bad placeholder in
    a translation should be visible as a missing value, not crash a handler.
    """
    _load()
    language = normalize_language(lang)
    template = _cache.get(language, {}).get(key)
    if template is None:
        template = _cache.get(DEFAULT_LANGUAGE, {}).get(key)
    if template is None:
        logger.warning("missing translation key %s for %s", key, language)
        return key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        logger.warning("translation %s in %s has incompatible placeholders", key, language)
        fallback = _cache.get(DEFAULT_LANGUAGE, {}).get(key, template)
        try:
            return fallback.format(**params)
        except (KeyError, IndexError, ValueError):
            return fallback


async def language_for(session, telegram_id: int) -> str:
    """Read a user's language without making callers import the repository."""
    from DB.repo.user_setting_repo import UserSettingsRepo

    settings = await UserSettingsRepo(session).get_user_settings(telegram_id)
    return normalize_language(settings.lang if settings else DEFAULT_LANGUAGE)


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGE_NAMES",
    "available_languages",
    "language_for",
    "normalize_language",
    "t",
]