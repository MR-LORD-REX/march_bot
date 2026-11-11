"""Deprecated Phase 0 shim.

The live webhook and Mini App routes moved to ``bot.api.webhook`` and
``bot.api.routes.mini_app``. They use server-side handoffs instead of
trusting client-supplied destination chat and message ids.

This module intentionally exposes no app factory or route registration.
Do not import it from runtime code; it exists only so old stray imports fail
closed rather than mounting the legacy, less safe implementation.
"""

from __future__ import annotations


def __getattr__(name: str):
    raise ImportError(
        "bot.core.webhook is retired; use bot.api.webhook.create_app instead"
    )