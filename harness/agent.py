"""Tool-calling agent loop against a hosted OpenAI-compatible model."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from harness.constants import (
    EXPECTED_ANSWER,
    GOAL,
    GROQ_BASE_URL,
    PROVIDER,
    REASONING_EFFORT,
    RETRY_MAX_CONSECUTIVE_429,
    RETRY_MAX_WAIT_SECONDS,
    START_URL,
    STEP_LIMIT,
    TOOLS,
)
from harness.normalize import NormalizeError, normalize_reply
from harness.tools import parse_tool_arguments, run_tool

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "agent.txt"

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Fetch a URL inside the lab and return its body.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Absolute http URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "End the trial by reporting the lab token exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "The exact lab token string",
                    }
                },
                "required": ["answer"],
            },
        },
    },
]


def load_system_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Prompt file is the reviewable wording; constants stay the source of the
    # values the rest of the harness scores against.
    if GOAL not in text or START_URL not in text:
        raise RuntimeError("prompts/agent.txt must state the goal and start URL")
    for name in TOOLS:
        if name not in text:
            raise RuntimeError(f"prompts/agent.txt must mention tool {name}")
    return text


def _raw_body(reply: Any) -> Any:
    if hasattr(reply, "model_dump"):
        return reply.model_dump(mode="json")
    return reply


def _tool_input_for_trace(tool: str, arguments_json: str) -> str:
    try:
        arguments = parse_tool_arguments(arguments_json)
    except ValueError:
        return arguments_json
    if tool == "http_get" and isinstance(arguments.get("url"), str):
        return arguments["url"]
    if tool == "submit" and isinstance(arguments.get("answer"), str):
        return arguments["answer"]
    return arguments_json


def _retry_after_seconds(exc: APIStatusError) -> float:
    headers = getattr(exc, "headers", None) or {}
    raw = None
    if hasattr(headers, "get"):
        raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(float(raw), 0.0)
    except (TypeError, ValueError):
        return 1.0


def call_model(client: OpenAI, model: str, messages: list[dict[str, Any]]) -> Any:
    """One chat completion with 429 retry. Does not consume a trial step on 429."""
    waited = 0.0
    consecutive_429 = 0
    while True:
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                stream=False,
                extra_body={"reasoning_effort": REASONING_EFFORT},
            )
        except RateLimitError as exc:
            consecutive_429 += 1
            delay = _retry_after_seconds(exc)
            if consecutive_429 >= RETRY_MAX_CONSECUTIVE_429:
                raise RuntimeError(
                    f"gave up after {consecutive_429} consecutive 429 responses"
                ) from exc
            if waited + delay > RETRY_MAX_WAIT_SECONDS:
                raise RuntimeError(
                    f"gave up after {waited + delay:.1f}s waiting on 429 "
                    f"(budget {RETRY_MAX_WAIT_SECONDS}s)"
                ) from exc
            time.sleep(delay)
            waited += delay
        except APIStatusError:
            raise
        except APIConnectionError:
            raise


def run_trial(client: OpenAI, model: str, *, step_limit: int = STEP_LIMIT) -> dict[str, Any]:
    """Run one trial. Returns a run record with outcome, answer, and steps."""
    system_prompt = load_system_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"{GOAL} Start at {START_URL}.",
        },
    ]
    steps: list[dict[str, Any]] = []

    try:
        for _ in range(step_limit):
            try:
                reply = call_model(client, model, messages)
            except (APIStatusError, APIConnectionError, RuntimeError, OSError) as exc:
                return {
                    "outcome": "harness_error",
                    "answer": "",
                    "steps": steps,
                    "error": str(exc),
                }

            raw_reply = _raw_body(reply)
            try:
                normalized = normalize_reply(reply)
            except NormalizeError as exc:
                # A reply that returns but carries no usable tool call still
                # consumes a step. The trial continues with an error observation;
                # only API/transport failures become harness_error.
                body = exc.body if exc.body is not None else raw_reply
                model_response = ""
                if isinstance(body, dict):
                    try:
                        model_response = (
                            body.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content")
                            or ""
                        )
                    except Exception:  # noqa: BLE001
                        model_response = ""
                observation = (
                    f"error: {exc}. Call exactly one tool "
                    f"({', '.join(TOOLS)}) per turn."
                )
                steps.append(
                    {
                        "model_response": model_response
                        if isinstance(model_response, str)
                        else "",
                        "tool": "",
                        "tool_input": "",
                        "observation": observation,
                        "raw_reply": body,
                    }
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": model_response
                        if isinstance(model_response, str) and model_response
                        else None,
                    }
                )
                messages.append({"role": "user", "content": observation})
                continue

            tool = normalized["tool"]
            arguments_json = normalized["tool_input"]
            observation, submitted = run_tool(tool, arguments_json)
            step = {
                "model_response": normalized["model_response"],
                "tool": tool,
                "tool_input": _tool_input_for_trace(tool, arguments_json),
                "observation": observation,
                "raw_reply": raw_reply,
            }
            steps.append(step)

            if submitted is not None:
                outcome = (
                    "success" if submitted == EXPECTED_ANSWER else "agent_failure"
                )
                return {"outcome": outcome, "answer": submitted, "steps": steps}

            # Feed the tool result back for the next model turn.
            tool_call_id = "call"
            try:
                tool_call_id = reply.choices[0].message.tool_calls[0].id or "call"
            except Exception:  # noqa: BLE001
                tool_call_id = "call"

            messages.append(
                {
                    "role": "assistant",
                    "content": normalized["model_response"] or None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": arguments_json,
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": observation,
                }
            )
        return {"outcome": "agent_failure", "answer": "", "steps": steps}
    except Exception as exc:  # noqa: BLE001 — record as harness_error
        return {
            "outcome": "harness_error",
            "answer": "",
            "steps": steps,
            "error": str(exc),
        }


def make_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def provider_name() -> str:
    return PROVIDER
