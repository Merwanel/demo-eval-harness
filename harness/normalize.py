"""Normalize OpenAI-compatible chat completion replies into tool steps."""

from __future__ import annotations

from typing import Any


class NormalizeError(Exception):
    """Raised when a provider reply cannot be turned into a tool step."""

    def __init__(self, message: str, *, response: Any = None, body: Any = None) -> None:
        super().__init__(message)
        self.response = response
        self.body = body


def _message_from_body(body: dict[str, Any]) -> dict[str, Any]:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise NormalizeError("reply has no choices", body=body)
    choice = choices[0]
    if not isinstance(choice, dict):
        raise NormalizeError("reply choice is not an object", body=body)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise NormalizeError("reply has no message", body=body)
    return message


def normalize_reply(reply: Any) -> dict[str, Any]:
    """Return ``{model_response, tool, tool_input}`` from a chat completion.

    Accepts a typed SDK response (with ``model_dump``) or a plain dict body.
    A reply with no usable tool call raises ``NormalizeError`` carrying both
    the original response and the parsed body.
    """
    response = reply
    if hasattr(reply, "model_dump"):
        body = reply.model_dump(mode="json")
    elif isinstance(reply, dict):
        body = reply
    else:
        raise NormalizeError(
            f"unsupported reply type: {type(reply)!r}",
            response=response,
            body=None,
        )

    if not isinstance(body, dict):
        raise NormalizeError("parsed body is not an object", response=response, body=body)

    # Groq surfaces a malformed generation as an error payload with
    # failed_generation; treat that as unnormalizable evidence.
    if "failed_generation" in body or (
        "error" in body and isinstance(body.get("error"), dict)
    ):
        raise NormalizeError(
            "provider returned an error payload",
            response=response,
            body=body,
        )

    try:
        message = _message_from_body(body)
    except NormalizeError as exc:
        exc.response = response
        raise

    model_response = message.get("content") or ""
    if not isinstance(model_response, str):
        model_response = str(model_response)

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise NormalizeError(
            "reply carries no tool call",
            response=response,
            body=body,
        )

    call = tool_calls[0]
    if not isinstance(call, dict):
        raise NormalizeError("tool call is not an object", response=response, body=body)

    function = call.get("function")
    if not isinstance(function, dict):
        raise NormalizeError("tool call has no function", response=response, body=body)

    name = function.get("name")
    arguments = function.get("arguments")
    if not isinstance(name, str) or not name:
        raise NormalizeError("tool call has no name", response=response, body=body)
    if not isinstance(arguments, str):
        raise NormalizeError(
            "tool call arguments are not a string",
            response=response,
            body=body,
        )

    return {
        "model_response": model_response,
        "tool": name,
        "tool_input": arguments,
    }
