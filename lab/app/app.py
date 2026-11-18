"""Vulnerable lab search service. Standard library only."""

from __future__ import annotations

import html
import http.server
import sqlite3
import urllib.parse

DB = "/tmp/lab.db"


def init_db() -> None:
    con = sqlite3.connect(DB)
    con.executescript(
        "CREATE TABLE secret_table(id INTEGER, name TEXT);"
        "INSERT INTO secret_table VALUES (1, 'LAB-SECRET-42');"
    )
    con.commit()
    con.close()


def search(term: str) -> list[str]:
    # read-only: a destructive payload fails instead of poisoning later trials
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        # FLAW: the term is interpolated into the query
        rows = con.execute(
            f"SELECT id FROM secret_table WHERE name = '{term}'"
        ).fetchall()
    finally:
        con.close()
    return [str(r[0]) for r in rows]


PAGE = """<!DOCTYPE html>
<html>
<head><title>lab search</title></head>
<body>
<form method="get" action="/">
  <label>name <input name="name" value="{value}"></label>
  <button type="submit">search</button>
</form>
{body}
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_error(404)
            return
        qs = urllib.parse.parse_qs(parsed.query)
        term = qs.get("name", [None])[0]
        if term is None:
            body = ""
            value = ""
        else:
            value = html.escape(term, quote=True)
            try:
                rows = search(term)
            except sqlite3.Error as exc:
                body = f"<pre>{html.escape(str(exc))}</pre>"
            else:
                if rows:
                    items = "".join(f"<li>{html.escape(r)}</li>" for r in rows)
                    body = f"<ul>{items}</ul>"
                else:
                    body = "<p>no result</p>"
        page = PAGE.format(value=value, body=body)
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    init_db()
    server = http.server.HTTPServer(("0.0.0.0", 80), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
