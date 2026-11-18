"""Pin the vulnerable search() behaviours against a temporary SQLite file."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "lab" / "app" / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("lab_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["lab_app"] = module
    spec.loader.exec_module(module)
    return module


class LabAppSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.app = load_app()
        self.app.DB = self._tmp.name
        self.app.init_db()
        self.search = self.app.search

    def tearDown(self) -> None:
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_catalogue_returns_nothing(self) -> None:
        self.assertEqual(self.search("catalogue"), [])

    def test_percent_returns_nothing(self) -> None:
        self.assertEqual(self.search("%"), [])

    def test_union_leaks_the_secret(self) -> None:
        self.assertIn(
            "LAB-SECRET-42",
            self.search("' UNION SELECT name FROM secret_table--"),
        )

    def test_or_true_returns_only_the_id(self) -> None:
        self.assertEqual(self.search("' OR 1=1--"), ["1"])

    def test_syntax_error_raises_sqlite_error(self) -> None:
        with self.assertRaises(sqlite3.Error):
            self.search("'")

    def test_sqlite_master_leaks_schema(self) -> None:
        rows = self.search("' UNION SELECT sql FROM sqlite_master--")
        self.assertTrue(any("secret_table" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
