"""Validate URLs before http_get fetches them."""

from __future__ import annotations

from urllib.parse import urlparse


def check_http_get_url(url: str) -> str | None:
    """Return None when *url* may be fetched; otherwise an error observation.

    Allowed: scheme ``http``, host exactly ``web``, port empty or 80.
    Parsing is used instead of a string prefix so ``web.example.com`` and
    ``web@elsewhere`` cannot slip through.
    """
    if not isinstance(url, str) or not url:
        return "http_get error: url must be a non-empty string"
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001 — surface parse failure to the agent
        return f"http_get error: invalid url ({exc})"

    if parsed.scheme != "http":
        return "http_get error: scheme must be http"
    if parsed.hostname != "web":
        return "http_get error: host must be exactly web"
    if parsed.port not in (None, 80):
        return "http_get error: port must be empty or 80"
    if parsed.username is not None or parsed.password is not None:
        return "http_get error: host must be exactly web"
    return None
