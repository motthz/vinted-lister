import base64
import io
import json
import mimetypes
import os
import re
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from core import (
    DATA,
    FIELDS,
    ROOT,
    analyze,
    apply_defaults,
    config,
    groups,
    missing,
    number,
    price,
    read_json,
    validate_config,
    write_json,
)
from credentials import remember_key, restore_key

LOCK = threading.RLock()
STATE = {"busy": False, "message": "Pronto", "errors": []}
DB = DATA / "items.json"
TOKEN = os.urandom(24).hex()


def export_item(item, parent):
    import shutil

    if missing(item):
        raise ValueError("Completa prima: " + ", ".join(missing(item)))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]):
        raise ValueError("ID non valido")
    dest = parent / item["id"]
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for index, file in enumerate(item["photos"]):
        name = f"{index + 1:02}{Path(file).suffix.lower()}"
        shutil.copy2(file, dest / name)
        names.append(name)
    exported = dict(item, photos=names)
    write_json(dest / "annuncio.json", exported)
    (dest / "annuncio.txt").write_text(
        "\n\n".join(f"{f}: {item.get(f, '')}" for f in FIELDS + ["price"]), encoding="utf-8"
    )
    return dest


def import_photos(body):
    photos = body.get("photos")
    if not isinstance(photos, list) or not 1 <= len(photos) <= 20:
        raise ValueError("Scegli da 1 a 20 foto dello stesso capo")
    images = []
    total = 0
    for photo in photos:
        if not isinstance(photo, dict) or not isinstance(photo.get("data"), str):
            raise ValueError("Foto non valida")
        raw = base64.b64decode(photo["data"], validate=True)
        total += len(raw)
        if total > 20 * 1024 * 1024:
            raise ValueError("Massimo 20 MB per capo")
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Usa foto JPG, PNG o WEBP")
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[im.format]
            im.verify()
        images.append((raw, extension))
    folder = (ROOT / config()["folder"]).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("La cartella scelta non è disponibile: scegline una dalle impostazioni")
    dest = folder / ("capo-" + uuid.uuid4().hex[:12])
    dest.mkdir()
    try:
        for index, (raw, extension) in enumerate(images):
            (dest / f"{index + 1:02}{extension}").write_bytes(raw)
    except OSError:
        import shutil

        shutil.rmtree(dest)
        raise
    return dest


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
                item = apply_defaults(analyze(files, cfg["model"]), cfg)
                item.update(
                    id=ident,
                    name=name,
                    photos=[str(p) for p in files],
                    status="ready" if not missing(item) else "draft",
                )
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
        if url.path in ("/app.js", "/style.css"):
            file = ROOT / url.path[1:]
            return self.send(
                file.read_bytes(), kind="text/javascript" if file.suffix == ".js" else "text/css"
            )
        if url.path == "/api/state":
            with LOCK:
                return self.send(
                    {
                        "config": config(),
                        "app": "vinted-studio",
                        "items": list(read_json(DB, {}).values()),
                        "state": STATE,
                        "has_key": bool(os.environ.get("OPENAI_API_KEY")),
                        "categories": list(config()["pricing"]["base"]),
                        "remember_key": os.name == "nt",
                        "missing": {key: missing(item) for key, item in read_json(DB, {}).items()},
                    }
                )
        if url.path == "/download":
            import tempfile

            with LOCK:
                items = [
                    i
                    for i in read_json(DB, {}).values()
                    if i.get("status") == "ready" and not missing(i)
                ]
            if not items:
                return self.send({"error": "Nessun annuncio pronto"}, 400)
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    parent = Path(tmp)
                    for item in items:
                        export_item(item, parent)
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
                        for file in sorted(parent.rglob("*")):
                            if file.is_file():
                                archive.write(file, file.relative_to(parent).as_posix())
                return self.send(buf.getvalue(), kind="application/zip")
            except (ValueError, OSError) as exc:
                return self.send({"error": str(exc)}, 400)
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
            limit = 29 * 1024 * 1024 if self.path == "/api/import" else 1000000
            if length > limit:
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
            elif self.path == "/api/key":
                key = body.get("key", "")
                if (
                    not isinstance(key, str)
                    or not key.strip()
                    or len(key) > 500
                    or any(c.isspace() for c in key.strip())
                ):
                    raise ValueError("Inserisci una chiave API valida, senza spazi")
                key = key.strip()
                if body.get("remember"):
                    remember_key(DATA / "api-key.dpapi", key)
                else:
                    (DATA / "api-key.dpapi").unlink(missing_ok=True)
                os.environ["OPENAI_API_KEY"] = key
                return self.send({"ok": True})
            elif self.path == "/api/import":
                with LOCK:
                    if (DATA / "publisher.lock").exists():
                        raise ValueError("Attendi la fine della compilazione browser")
                    dest = import_photos(body)
                if not STATE["busy"]:
                    start_scan()
                else:
                    # An in-flight folder iterator may not include the new folder.
                    threading.Thread(target=scan_after_current, daemon=True).start()
                return self.send({"ok": True, "name": dest.name})
            elif self.path == "/api/defaults":
                with LOCK:
                    if (DATA / "publisher.lock").exists():
                        raise ValueError("Attendi la fine della compilazione browser")
                    cfg = config()
                    items = read_json(DB, {})
                    for item in items.values():
                        if item.get("status") in ("draft", "ready"):
                            apply_defaults(item, cfg)
                            item["price"], item["price_reason"] = price(item, cfg["pricing"])
                            item["status"] = "draft" if missing(item) else "ready"
                    write_json(DB, items)
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
                dest = export_item(item, DATA / "exports")
                return self.send({"ok": True, "path": str(dest)})
            else:
                return self.send({"error": "Non trovato"}, 404)
            self.send({"ok": True})
        except Exception as exc:
            self.send({"error": str(exc)}, 400)

    def local_host(self):
        # Protect localhost API against DNS rebinding; browsers cannot forge Host.
        return self.headers.get("Host", "").split(":")[0].lower() in ("127.0.0.1", "localhost")


def scan_after_current():
    while STATE["busy"]:
        time.sleep(0.2)
    start_scan()


if __name__ == "__main__":
    (ROOT / "photos").mkdir(exist_ok=True)
    restore_key(DATA / "api-key.dpapi")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    except OSError:
        from urllib.request import urlopen

        try:
            with urlopen("http://127.0.0.1:8765/api/state", timeout=3) as response:
                if json.load(response).get("app") != "vinted-studio":
                    raise RuntimeError("Porta 8765 occupata da un’altra applicazione")
            webbrowser.open("http://127.0.0.1:8765")
            raise SystemExit(0)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                "Porta 8765 occupata: chiudi l’altra applicazione e riprova"
            ) from exc
    threading.Thread(target=watcher, daemon=True).start()
    print("Vinted Studio: http://127.0.0.1:8765", flush=True)
    webbrowser.open("http://127.0.0.1:8765")
    server.serve_forever()
