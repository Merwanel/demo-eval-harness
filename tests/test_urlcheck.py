"""URL check for http_get: table of addresses that must pass or fail."""

from __future__ import annotations

import unittest

from harness.urlcheck import check_http_get_url

PASS = [
    "http://web/",
    "http://web",
    "http://web/token.txt",
    "http://web:80/",
    "http://web:80/token.txt",
    "http://web/path?q=1",
]

FAIL = [
    "",
    "https://web/",
    "http://web.example.com/",
    "http://web@elsewhere/",
    "http://elsewhere/",
    "http://127.0.0.1/",
    "http://localhost/",
    "http://web:8080/",
    "http://web:443/",
    "ftp://web/",
    "web/",
    "//web/",
    "http://user:pass@web/",
]


class UrlCheckTests(unittest.TestCase):
    def test_allowed_urls_pass(self) -> None:
        for url in PASS:
            with self.subTest(url=url):
                self.assertIsNone(check_http_get_url(url))

    def test_forbidden_urls_fail(self) -> None:
        for url in FAIL:
            with self.subTest(url=url):
                self.assertIsNotNone(check_http_get_url(url))


if __name__ == "__main__":
    unittest.main()
