"""URL check for http_get: table of addresses that must pass or fail."""

from __future__ import annotations

import unittest

from harness.urlcheck import check_http_get_url

PASS = [
    "http://app/",
    "http://app",
    "http://app/?name=x",
    "http://app:80/",
    "http://app:80/?name=x",
    "http://app/path?q=1",
]

FAIL = [
    "",
    "https://app/",
    "http://app.example.com/",
    "http://app@elsewhere/",
    "http://elsewhere/",
    "http://127.0.0.1/",
    "http://localhost/",
    "http://web/",
    "http://app:8080/",
    "http://app:443/",
    "ftp://app/",
    "app/",
    "//app/",
    "http://user:pass@app/",
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
