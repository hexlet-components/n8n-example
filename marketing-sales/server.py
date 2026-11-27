import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID


WEBHOOK_BASE = os.environ.get("N8N_WEBHOOK_BASE", "http://127.0.0.1:5678/webhook")
PAGE = Path(__file__).with_name("index.html")


class RegistrationHandler(BaseHTTPRequestHandler):
    def reply(self, status: int, text: str, mime: str = "text/plain") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        self.reply(200, PAGE.read_text(encoding="utf-8"), "text/html")

    def do_POST(self) -> None:
        if self.path != "/register":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= 8192:
            self.send_error(400)
            return
        try:
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            email = form["email"][0].strip()
            if "@" not in email:
                raise ValueError("email")
            registered_at = form["registeredAt"][0]
            datetime.fromisoformat(registered_at.replace("Z", "+00:00"))
            registration = {
                "registrationId": str(UUID(form["registrationId"][0])),
                "registeredAt": registered_at,
                "email": email,
                "marketingConsent": form.get("marketingConsent") == ["yes"],
                "source": "event-site",
                "campaignId": form.get("campaignId", [""])[0],
            }
        except (KeyError, ValueError):
            self.reply(400, "Проверьте адрес и откройте форму в браузере с JavaScript.")
            return

        request = Request(
            f"{WEBHOOK_BASE.rstrip('/')}/event-registration",
            data=json.dumps(registration).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.load(response)
            if not isinstance(result, dict) or result.get("registrationId") != registration["registrationId"]:
                raise ValueError("registrationId")
        except (URLError, TimeoutError, ValueError):
            self.reply(502, "Подтверждение регистрации не пришло. Проверьте историю выполнения в n8n.")
            return
        self.reply(200, f"Регистрация принята. Ваш номер {registration['registrationId']}.")


if __name__ == "__main__":
    print("Форма регистрации: http://127.0.0.1:8001", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8001), RegistrationHandler).serve_forever()
