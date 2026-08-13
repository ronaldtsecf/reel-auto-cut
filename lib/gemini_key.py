"""Resolve the Gemini API key without logging or persisting its value."""

from __future__ import annotations

import os
from collections.abc import Mapping


# Google documents GOOGLE_API_KEY as taking precedence when both official
# variables exist.  GOOGLE_AI_API_KEY is retained only for older installs.
ENV_NAMES = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY")


def resolve_gemini_key(environ: Mapping[str, str] | None = None) -> tuple[str | None, str | None]:
    env = os.environ if environ is None else environ
    for name in ENV_NAMES:
        value = env.get(name)
        if value:
            return value, name
    return None, None
