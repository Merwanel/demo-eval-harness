"""Execute the two agent tools: http_get and submit."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from harness.urlcheck import check_http_get_url


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """Parse the JSON arguments string from a tool call."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"tool arguments are not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be a JSON object")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn redirects into HTTPError so the lab cannot bounce a fetch away."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def http_get(url: str) -> str:
    """Fetch *url* when it passes the lab URL check; never follow redirects."""
    error = check_http_get_url(url)
    if error is not None:
        return error

    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            return "http_get error: redirects are not followed"
        return f"http_get error: HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return f"http_get error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 — observation for the agent
        return f"http_get error: {exc}"

    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")

def run_tool(name: str, arguments_json: str) -> tuple[str, str | None]:
    """Run a tool. Returns ``(observation, submit_answer_or_None)``."""
    try:
        arguments = parse_tool_arguments(arguments_json)
    except ValueError as exc:
        return (str(exc), None)

    if name == "http_get":
        url = arguments.get("url")
        if not isinstance(url, str):
            return ("http_get error: missing string url", None)
        return (http_get(url), None)

    if name == "submit":
        answer = arguments.get("answer")
        if not isinstance(answer, str):
            return ("submit error: missing string answer", None)
        return ("submitted", answer)

    return (f"unknown tool: {name}", None)
