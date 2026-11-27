"""Локальные формы курса и учёт принятых заявок."""

import json
import os
import sqlite3
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
WEBHOOK = os.getenv("N8N_WEBHOOK_BASE", "http://localhost:5678/webhook").rstrip("/")
DB_PATH = os.getenv("METRIKA_DB", str(Path.home() / ".hexlet-metrika.sqlite"))
SITES = {"school": "service", "event": "section"}
TYPES = {"html": "text/html", "js": "text/javascript"}
ASSETS = {"index.html", "form.html", "thanks.html", "counter.js", "form.js", "source.js"}


def notify(path, record):
    request = Request(
        f"{WEBHOOK}/metrika-{path}",
        data=json.dumps(record).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        response.read()


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urlsplit(self.path).path.strip("/").split("/")
        if len(parts) == 1 and parts[0] in SITES:
            self.send_response(302)
            self.send_header("Location", f"/{parts[0]}/index.html")
            self.end_headers()
            return
        if len(parts) == 2 and parts[0] in SITES and parts[1] in ASSETS:
            file = ROOT.joinpath(*parts)
            if file.is_file():
                body = file.read_bytes()
                if file.name == "index.html" and urlsplit(self.path).query == "rejected=1":
                    body = body.replace(b'<p role="status"></p>',
                                        '<p role="status">Заявка отклонена</p>'.encode())
                self.reply(200, body, TYPES[file.suffix[1:]])
                return
        self.send_error(404)

    def do_POST(self):
        parts = urlsplit(self.path).path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in SITES or parts[1] != "apply":
            self.send_error(404)
            return
        site = parts[0]
        is_json = self.headers.get_content_type() == "application/json"
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError()
            body = self.rfile.read(size).decode()
            data = json.loads(body) if is_json else {
                key: values[0] for key, values in parse_qs(body).items()
            }
            field = SITES[site]
            if not isinstance(data, dict) or data.get("refuse") or data.get(field) not in {
                "english" if site == "school" else "design", "media"
            }:
                raise ValueError()
            record = {"id": uuid4().hex, "site": site, field: data[field]}
            for key in ("ClientID", "utm_source", "utm_medium", "utm_campaign"):
                if isinstance(data.get(key), str):
                    record[key] = data[key]
        except (ValueError, UnicodeError):
            if is_json:
                self.send_error(422, "Application rejected")
            else:
                self.send_response(303)
                self.send_header("Location", f"/{site}/index.html?rejected=1")
                self.end_headers()
            return
        try:
            notify("application", record)
        except (URLError, TimeoutError):
            self.send_error(HTTPStatus.BAD_GATEWAY, "Check the n8n webhook")
            return
        with db:
            db.execute("INSERT INTO applications(id, record) VALUES (?, ?)",
                       (record["id"], json.dumps(record)))
        if is_json:
            self.reply(201, json.dumps({"id": record["id"]}).encode())
        else:
            self.send_response(303)
            self.send_header("Location", f"/{site}/thanks.html")
            self.end_headers()
        print(f"Принята заявка {record['id']}", flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", metavar="ID", help="Отметить обработку заявки")
    args = parser.parse_args()
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS applications "
               "(id TEXT PRIMARY KEY, record TEXT NOT NULL, processed_at INTEGER, sent INTEGER DEFAULT 0)")
    if args.process:
        with db:
            updated = db.execute("UPDATE applications SET processed_at=coalesce(processed_at, ?) "
                                 "WHERE id=? AND sent=0", (int(time.time()), args.process))
            if not updated.rowcount:
                parser.exit(1, "Заявка отсутствует или уже обработана\n")
            raw, timestamp = db.execute("SELECT record, processed_at FROM applications WHERE id=?",
                                        (args.process,)).fetchone()
            record = dict(json.loads(raw), processed_at=timestamp, status="processed")
        with db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT sent FROM applications WHERE id=?", (args.process,)).fetchone()[0]:
                parser.exit(1, "Заявка уже обработана\n")
            try:
                notify("processed", record)
            except (URLError, TimeoutError) as exc:
                parser.exit(1, f"Проверьте выполнение в n8n перед повтором: {exc}\n")
            db.execute("UPDATE applications SET sent=1 WHERE id=?", (args.process,))
        print("Событие передано в n8n")
    else:
        print("http://localhost:8000/school/index.html", flush=True)
        HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
