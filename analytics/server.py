import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIRECTORY = Path(__file__).parent
DATABASE = Path("/data/reports.sqlite3")


def validate_period(payload: dict) -> str:
    start = date.fromisoformat(payload["periodStart"])
    end = date.fromisoformat(payload["periodEnd"])
    if (
        start.weekday() != 0
        or end - start != timedelta(days=7)
        or start.isoformat() != payload["periodStart"]
        or end.isoformat() != payload["periodEnd"]
    ):
        raise ValueError("Нужны даты двух соседних понедельников в формате YYYY-MM-DD.")
    return start.isoformat()


def validate_row(row: dict) -> None:
    if not isinstance(row["source"], str) or not row["source"]:
        raise ValueError("У строки должно быть имя источника.")
    for field in ("visits", "leads", "taken"):
        if type(row[field]) is not int or row[field] < 0:
            raise ValueError(f"В поле {field} нужно целое неотрицательное число.")
    rate = row["per100"]
    if row["visits"] == 0:
        if rate is not None:
            raise ValueError("Для строки без визитов передайте per100 равным null.")
    elif type(rate) not in (int, float) or not math.isfinite(rate):
        raise ValueError("В поле per100 нужно число.")


class ReportHandler(BaseHTTPRequestHandler):
    def reply(self, status: int, data: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, status: int, payload: object) -> None:
        self.reply(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path == "/":
            self.reply(200, (DIRECTORY / "index.html").read_bytes(), "text/html")
            return
        if self.path == "/visits.json":
            self.reply(200, (DIRECTORY / "visits.json").read_bytes(), "application/json")
            return

        with closing(sqlite3.connect(DATABASE)) as db:
            if self.path == "/alerts":
                alerts = db.execute("SELECT payload FROM alerts ORDER BY id DESC")
                self.json(200, [json.loads(row[0]) for row in alerts])
                return
            if self.path == "/reports/latest":
                row = db.execute("SELECT payload FROM reports ORDER BY start DESC LIMIT 1").fetchone()
            elif self.path.startswith("/reports/"):
                row = db.execute("SELECT payload FROM reports WHERE start = ?", (self.path[9:],)).fetchone()
            else:
                row = None
        if row is None:
            self.json(404, {"error": "Данные по этому адресу отсутствуют."})
        else:
            self.reply(200, row[0].encode(), "application/json")

    def do_POST(self) -> None:
        if self.path not in {"/reports", "/alerts"}:
            self.json(404, {"error": "Неизвестный адрес."})
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 1024 * 1024:
                raise ValueError("Ожидается тело JSON размером до 1 МБ.")
            data = json.loads(self.rfile.read(size))
            period = validate_period(data)
            if self.path == "/reports":
                if not isinstance(data["rows"], list):
                    raise ValueError("В поле rows нужен массив строк.")
                for row in [*data["rows"], data["total"]]:
                    validate_row(row)
            elif not isinstance(data["reason"], str) or not data["reason"].strip():
                raise ValueError("В поле reason укажите причину сбоя.")
            data["updatedAt"] = datetime.now(UTC).isoformat(timespec="seconds")
            content = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (KeyError, TypeError, ValueError) as error:
            self.json(400, {"error": str(error)})
            return
        with closing(sqlite3.connect(DATABASE)) as db, db:
            if self.path == "/reports":
                db.execute(
                    "INSERT INTO reports(start, payload) VALUES (?, ?) "
                    "ON CONFLICT(start) DO UPDATE SET payload=excluded.payload",
                    (period, content),
                )
            else:
                db.execute("INSERT INTO alerts(payload) VALUES (?)", (content,))
        self.json(200, data)


if __name__ == "__main__":
    with closing(sqlite3.connect(DATABASE)) as connection:
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS reports(start TEXT PRIMARY KEY, payload TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, payload TEXT NOT NULL);"
        )
    ThreadingHTTPServer(("0.0.0.0", 8000), ReportHandler).serve_forever()
