from __future__ import annotations

import re


def clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_price(text: str | float | int | None) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(text))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def short(text: str, limit: int = 1000) -> str:
    text = clean(text)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
