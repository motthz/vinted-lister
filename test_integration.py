"""Isolated integration tests: no real account, external API or personal files."""

import copy
import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

import app
import core


def example_item():
    return dict(
        title="Felpa blu",
        description="Felpa con cappuccio.",
        category="felpa",
        brand="Esempio",
        size="M",
        condition="buono",
        color="blu",
        material="cotone",
        package_size="medio",
        uncertainties=[],
        retail_price=None,
    )


class IsolatedApp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.folder = self.root / "photos"
        self.folder.mkdir()
        self.cfg = json.loads((core.ROOT / "config.json").read_text(encoding="utf-8"))
        (self.root / "config.json").write_text(json.dumps(self.cfg), encoding="utf-8")
        (self.root / "index.html").write_text(
            (core.ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8"
        )
        for asset in ("app.js", "style.css"):
            (self.root / asset).write_bytes((core.ROOT / asset).read_bytes())
        self.stack = ExitStack()
        for module, name, value in [
            (core, "ROOT", self.root),
            (core, "DATA", self.data),
            (app, "ROOT", self.root),
            (app, "DATA", self.data),
            (app, "DB", self.data / "items.json"),
        ]:
            self.stack.enter_context(patch.object(module, name, value))
        self.stack.enter_context(
            patch.object(app, "STATE", {"busy": False, "message": "Pronto", "errors": []})
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.stack.close()
        self.temp.cleanup()

    def call(self, path, body=None, token=True, raw=None, headers=None):
        hdr = dict(headers or {})
        payload = (
            raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        )
        if token:
            hdr["X-App-Token"] = app.TOKEN
        req = Request(self.url + path, data=payload, headers=hdr)
        try:
            res = urlopen(req, timeout=10)
        except HTTPError as exc:
            res = exc
        with res:
            data = res.read()
            return res.status, json.loads(data) if "application/json" in res.headers.get(
                "Content-Type", ""
            ) else data

    def add_photo(self):
        folder = self.folder / "capo"
        folder.mkdir(exist_ok=True)
        file = folder / "foto.jpg"
        Image.new("RGB", (40, 60), "blue").save(file)
        return file

    def seed(self, status="draft"):
        file = self.add_photo()
        item = dict(
            example_item(),
            id="sample",
            name="Capo",
            status=status,
            photos=[str(file)],
            price=15,
            price_reason="Test",
        )
        core.write_json(app.DB, {"sample": item})
        return item


class ApiTests(IsolatedApp):
    def test_home_state_and_not_found(self):
        status, page = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(app.TOKEN.encode(), page)
        self.assertNotIn(b"__TOKEN__", page)
        status, state = self.call("/api/state")
        self.assertEqual(state["items"], [])
        self.assertEqual(self.call("/unknown")[0], 404)
        self.assertEqual(self.call("/unknown", {})[0], 404)

    def test_security_tokens_host_and_malformed_json(self):
        self.assertEqual(self.call("/api/scan", {}, token=False)[0], 403)
        self.assertEqual(self.call("/api/state", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("/api/scan", {}, headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("/api/config", raw=b"{bad")[0], 400)
        self.assertEqual(self.call("/api/config", raw=b"[]")[0], 400)
        self.assertEqual(self.call("/api/config", raw=b"x" * 1000001)[0], 413)

    def test_configuration_persists_privately_and_validates_entire_table(self):
        original = (self.root / "config.json").read_bytes()
        cfg = copy.deepcopy(self.cfg)
        cfg["pricing"]["base"]["giacca"] = 22
        self.assertEqual(self.call("/api/config", cfg)[0], 200)
        self.assertEqual(core.config()["pricing"]["base"]["giacca"], 22)
        self.assertEqual((self.root / "config.json").read_bytes(), original)
        for bad in (-1, 0, "non-numero", 12.345, 10001, True):
            cfg["pricing"]["base"]["felpa"] = bad
            self.assertEqual(self.call("/api/config", cfg)[0], 400, str(bad))
        self.assertEqual(core.config()["pricing"]["base"]["felpa"], 15)

    def test_config_busy_and_folder_invalid(self):
        app.STATE["busy"] = True
        self.assertEqual(self.call("/api/config", self.cfg)[0], 400)
        app.STATE["busy"] = False
        self.cfg["folder"] = "nonexistent"
        self.assertEqual(self.call("/api/config", self.cfg)[0], 400)

    def test_item_save_reprice_export_photos(self):
        item = self.seed()
        item["category"] = "maglietta"
        self.assertEqual(self.call("/api/item", item)[0], 200)
        saved = core.read_json(app.DB)["sample"]
        self.assertEqual(saved["price"], 5)
        self.assertEqual(saved["status"], "ready")
        self.assertEqual(self.call("/photo?id=sample&n=0")[0], 200)
        for query in ("id=sample&n=-1", "id=sample&n=9", "id=no&n=0", "n=0", "id=sample&n=bad"):
            self.assertEqual(self.call("/photo?" + query)[0], 404)
        status, result = self.call("/api/export", {"id": "sample"})
        self.assertEqual(status, 200)
        exported = Path(result["path"])
        self.assertTrue((exported / "01.jpg").exists())
        self.assertEqual(core.read_json(exported / "annuncio.json")["photos"], ["01.jpg"])
        self.assertIn("price: 5", (exported / "annuncio.txt").read_text())

    def test_invalid_item_not_written_and_missing_blocks_export(self):
        item = self.seed()
        original = app.DB.read_bytes()
        for bad in ([], {}, None, 3):
            invalid = dict(item, title=bad)
            self.assertEqual(self.call("/api/item", invalid)[0], 400)
            self.assertEqual(app.DB.read_bytes(), original)
        self.assertEqual(self.call("/api/item", dict(item, retail_price=-2))[0], 400)
        self.assertEqual(self.call("/api/item", dict(item, size=""))[0], 200)
        self.assertEqual(self.call("/api/export", {"id": "sample"})[0], 400)
        self.assertEqual(self.call("/api/item", {"id": "unknown"})[0], 400)

    def test_published_and_uncertain_send_cannot_be_edited(self):
        for status in ("published", "publishing"):
            self.seed(status)
            self.assertEqual(self.call("/api/item", {"id": "sample", "title": "Cambiato"})[0], 400)
            self.assertEqual(core.read_json(app.DB)["sample"]["title"], "Felpa blu")

    def test_scan_deduplicates_preserves_edits_and_updates_moved_photos(self):
        self.add_photo()
        with patch.object(app, "analyze", return_value=example_item()) as ai:
            app.scan()
            items = core.read_json(app.DB)
            ident = next(iter(items))
            items[ident]["title"] = "Titolo corretto"
            core.write_json(app.DB, items)
            (self.folder / "capo").rename(self.folder / "rinominato")
            app.scan()
            self.assertEqual(ai.call_count, 1)
            saved = core.read_json(app.DB)[ident]
            self.assertEqual(saved["title"], "Titolo corretto")
            self.assertTrue(Path(saved["photos"][0]).exists())
            self.assertFalse(app.STATE["busy"])

    def test_scan_errors_are_visible_and_do_not_destroy_items(self):
        self.seed()
        with patch.object(app, "analyze", side_effect=ValueError("API non disponibile")):
            app.scan()
        self.assertIn("API non disponibile", app.STATE["errors"][0])
        self.assertIn("errori", app.STATE["message"])
        self.assertFalse(app.STATE["busy"])
        self.assertIn("sample", core.read_json(app.DB))

    def test_async_scan_starts_once(self):
        self.add_photo()
        gate = threading.Event()

        def analyze(*_):
            gate.wait(3)
            return example_item()

        with patch.object(app, "analyze", side_effect=analyze) as ai:
            try:
                self.assertEqual(self.call("/api/scan", {})[0], 200)
                self.assertEqual(self.call("/api/scan", {})[0], 200)
                self.assertTrue(app.STATE["busy"])
            finally:
                gate.set()
                deadline = time.monotonic() + 5
                while app.STATE["busy"] and time.monotonic() < deadline:
                    time.sleep(0.01)
            self.assertEqual(ai.call_count, 1)
            self.assertFalse(app.STATE["busy"])

    def test_native_folder_dialog_result_and_cancel(self):
        from subprocess import CompletedProcess

        for folder in ("C:/foto di prova/è", ""):
            with patch("subprocess.run", return_value=CompletedProcess([], 0, folder + "\n", "")):
                self.assertEqual(self.call("/api/folder", {})[1]["folder"], folder)


class VisionTests(unittest.TestCase):
    def test_request_contains_images_and_response_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            photo = Path(folder) / "test.png"
            Image.new("RGB", (2200, 1800), "red").save(photo)
            response_item = dict(
                example_item(),
                category="inventata",
                condition="come nuova",
                uncertainties="bad",
                brand=["bad"],
            )
            response = {
                "status": "completed",
                "output": [
                    {"content": [{"type": "output_text", "text": json.dumps(response_item)}]}
                ],
            }

            def fake_urlopen(req, timeout):
                payload = json.loads(req.data)
                self.assertEqual(req.full_url, "https://api.openai.com/v1/responses")
                self.assertFalse(payload["store"])
                self.assertEqual(timeout, 120)
                content = payload["input"][0]["content"]
                self.assertIn("piumino", content[0]["text"])
                self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
                return io.BytesIO(json.dumps(response).encode())

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}),
                patch.object(core, "urlopen", side_effect=fake_urlopen),
            ):
                item = core.analyze([photo], "test-model")
            self.assertEqual(item["category"], "altro")
            self.assertEqual(item["brand"], "")
            self.assertEqual(item["condition"], "")
            self.assertIsInstance(item["uncertainties"], list)

    def test_invalid_and_incomplete_vision_responses(self):
        with tempfile.TemporaryDirectory() as folder:
            photo = Path(folder) / "test.png"
            Image.new("RGB", (10, 10)).save(photo)
            responses = [
                {"status": "incomplete"},
                {"status": "completed", "output": []},
                {
                    "status": "completed",
                    "output": [{"content": [{"type": "output_text", "text": "[]"}]}],
                },
            ]
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}):
                for response in responses:
                    with patch.object(
                        core, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())
                    ):
                        with self.assertRaises(ValueError):
                            core.analyze([photo], "test-model")
                for photos in ([], [photo] * 21):
                    with self.assertRaises(ValueError):
                        core.analyze(photos, "test-model")


if __name__ == "__main__":
    unittest.main()
