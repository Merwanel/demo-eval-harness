"""Reply normalizer against recorded provider payloads."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from harness.normalize import NormalizeError, normalize_reply

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class NormalizeTests(unittest.TestCase):
    def test_http_get_tool_call(self) -> None:
        body = load("reply_http_get_index.json")
        step = normalize_reply(body)
        self.assertEqual(step["tool"], "http_get")
        self.assertIn("http://web/", step["tool_input"])

    def test_token_page_tool_call(self) -> None:
        body = load("reply_http_get_token.json")
        step = normalize_reply(body)
        self.assertEqual(step["tool"], "http_get")
        self.assertIn("token.txt", step["tool_input"])

    def test_no_tool_call_raises(self) -> None:
        body = load("reply_no_tool_call.json")
        with self.assertRaises(NormalizeError) as ctx:
            normalize_reply(body)
        self.assertIs(ctx.exception.body, body)

    def test_malformed_tool_call_raises_with_body(self) -> None:
        body = load("reply_malformed_tool_call.json")
        with self.assertRaises(NormalizeError) as ctx:
            normalize_reply(body)
        self.assertEqual(ctx.exception.body, body)
        self.assertIn("failed_generation", ctx.exception.body)


if __name__ == "__main__":
    unittest.main()
