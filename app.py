import json
import mimetypes
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import (
    DATA,
    FIELDS,
    ROOT,
    analyze,
    config,
    groups,
    missing,
    number,
    price,
    read_json,
    validate_config,
    write_json,
)

LOCK = threading.RLock()
STATE = {"busy": False, "message": "Pronto", "errors": []}
DB = DATA / "items.json"
TOKEN = os.urandom(24).hex()


def scan():
    try:
        cfg = config()
        for ident, name, files in groups(ROOT / cfg["folder"]):
            with LOCK:
                items = read_json(DB, {})
                if ident in items:
                    # Preserve edits while keeping photo paths valid after moves/renames.
                    paths = [str(p) for p in files]
                    if items[ident]["photos"] != paths:
                        items[ident]["photos"] = paths
                        write_json(DB, items)
                    continue
                STATE["message"] = f"Analisi: {name}"
            try:
                item = analyze(files, cfg["model"])
                item.update(id=ident, name=name, photos=[str(p) for p in files], status="draft")
                item["price"], item["price_reason"] = price(item, cfg["pricing"])
                with LOCK:
                    items = read_json(DB, {})
                    items[ident] = item
                    write_json(DB, items)
            except Exception as exc:
                with LOCK:
                    STATE["errors"].append(f"{name}: {type(exc).__name__}: {exc}")
        STATE["message"] = (
            "Scansione completata"
            if not STATE["errors"]
            else "Scansione completata con errori: controlla i dettagli"
        )
    except Exception as exc:
        STATE["message"] = str(exc)
    finally:
        with LOCK:
            STATE["busy"] = False


def start_scan():
    with LOCK:
        if not STATE["busy"]:
            STATE.update(busy=True, errors=[], message="Scansione in corso")
            threading.Thread(target=scan, daemon=True).start()


def watcher():
    while True:
        time.sleep(15)
        try:
            if config().get("watch"):
                start_scan()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, body, status=200, kind="application/json"):
        raw = json.dumps(body, ensure_ascii=False).encode() if kind == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header(
            "Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") else "")
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client closed/reloaded the page before the response completed.

    def do_GET(self):
        if not self.local_host():
            return self.send({"error": "Host non consentito"}, 403)
        url = urlparse(self.path)
        if url.path == "/":
            html = (ROOT / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.send(html.encode(), kind="text/html")
        if url.path == "/api/state":
            with LOCK:
                return self.send(
                    {
                        "config": config(),
                        "items": list(read_json(DB, {}).values()),
                        "state": STATE,
                        "has_key": bool(os.environ.get("OPENAI_API_KEY")),
                    }
                )
        if url.path == "/photo":
            q = parse_qs(url.query)
            try:
                item = read_json(DB, {})[q["id"][0]]
                index = int(q["n"][0])
                if index < 0:
                    raise IndexError()
                p = Path(item["photos"][index])
                return self.send(
                    p.read_bytes(), kind=mimetypes.guess_type(p)[0] or "application/octet-stream"
                )
            except (KeyError, IndexError, ValueError, OSError):
                return self.send({"error": "Foto non trovata"}, 404)
        self.send({"error": "Non trovato"}, 404)

    def do_POST(self):
        if not self.local_host() or self.headers.get("X-App-Token") != TOKEN:
            return self.send({"error": "Richiesta non autorizzata"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 1000000:
                # Drain a bounded amount so Windows clients receive the error
                # rather than a TCP reset while still sending a modest upload.
                self.connection.settimeout(5)
                self.rfile.read(min(length, 2000000))
                return self.send({"error": "Richiesta troppo grande"}, 413)
            if length < 0:
                raise ValueError("Richiesta troppo grande")
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Oggetto JSON richiesto")
            if self.path == "/api/scan":
                start_scan()
            elif self.path == "/api/folder":
                import subprocess

                result = subprocess.run(
                    [__import__("sys").executable, str(ROOT / "pick_folder.py")],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=180,
                )
                if result.returncode:
                    raise ValueError("Selezione cartella non disponibile")
                return self.send({"folder": result.stdout.strip()})
            elif self.path == "/api/config":
                validate_config(body)
                folder = Path(body["folder"]).expanduser()
                if not (ROOT / folder).is_dir():
                    raise ValueError("Cartella foto non trovata")
                with LOCK:
                    if STATE["busy"]:
                        raise ValueError("Attendi la fine della scansione")
                    write_json(DATA / "settings.json", body)
            elif self.path == "/api/item":
                with LOCK:
                    items = read_json(DB, {})
                    item = items[body["id"]]
                    if item.get("status") in ("publishing", "published"):
                        raise ValueError(
                            "Annuncio inviato o in verifica: modifica bloccata per evitare duplicati"
                        )
                    if (DATA / "publisher.lock").exists():
                        raise ValueError(
                            "Compilazione browser in corso: attendi prima di modificare gli annunci"
                        )
                    for f in FIELDS + ["retail_price"]:
                        item[f] = body.get(f, item.get(f))
                    if any(
                        not isinstance(item.get(f), str) or len(item[f]) > 10000 for f in FIELDS
                    ):
                        raise ValueError("I campi devono essere testi di massimo 10.000 caratteri")
                    if item.get("retail_price") not in (None, ""):
                        number(item["retail_price"], "Prezzo originale", True)
                    item["price"], item["price_reason"] = price(item, config()["pricing"])
                    item["status"] = "ready" if not missing(item) else "draft"
                    write_json(DB, items)
            elif self.path == "/api/export":
                items = read_json(DB, {})
                item = items[body["id"]]
                if missing(item):
                    raise ValueError("Completa prima: " + ", ".join(missing(item)))
                import shutil

                dest = DATA / "exports" / item["id"]
                dest.mkdir(parents=True, exist_ok=True)
                for i, file in enumerate(item["photos"]):
                    shutil.copy2(file, dest / f"{i + 1:02}{Path(file).suffix}")
                exported = dict(
                    item,
                    photos=[f"{i + 1:02}{Path(f).suffix}" for i, f in enumerate(item["photos"])],
                )
                write_json(dest / "annuncio.json", exported)
                (dest / "annuncio.txt").write_text(
                    "\n\n".join(f"{f}: {item.get(f, '')}" for f in FIELDS + ["price"]),
                    encoding="utf-8",
                )
                return self.send({"ok": True, "path": str(dest)})
            else:
                return self.send({"error": "Non trovato"}, 404)
            self.send({"ok": True})
        except Exception as exc:
            self.send({"error": str(exc)}, 400)

    def local_host(self):
        # Protect localhost API against DNS rebinding; browsers cannot forge Host.
        return self.headers.get("Host", "").split(":")[0].lower() in ("127.0.0.1", "localhost")


if __name__ == "__main__":
    (ROOT / "photos").mkdir(exist_ok=True)
    threading.Thread(target=watcher, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Vinted Studio: http://127.0.0.1:8765", flush=True)
    webbrowser.open("http://127.0.0.1:8765")
    server.serve_forever()
