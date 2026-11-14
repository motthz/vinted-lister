import base64
import io
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import app
import core
import credentials
from test_integration import IsolatedApp, example_item


class LazyApiTests(IsolatedApp):
    def wait_for_scan(self):
        deadline = time.monotonic() + 5
        while app.STATE["busy"] and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(app.STATE["busy"])

    def test_import_creates_group_then_analyzes_automatically(self):
        photo = self.add_photo()
        encoded = base64.b64encode(photo.read_bytes()).decode()
        with patch.object(app, "analyze", return_value=example_item()):
            status, result = self.call(
                "/api/import", {"photos": [{"data": encoded}, {"data": encoded}]}
            )
            self.assertEqual(status, 200)
            self.wait_for_scan()
        self.assertEqual(len(list((self.folder / result["name"]).glob("*.jpg"))), 2)
        self.assertEqual(len(core.read_json(app.DB)), 2)
        self.assertTrue(all(i["status"] == "ready" for i in core.read_json(app.DB).values()))

    def test_import_rejects_invalid_payloads_without_creating_folders(self):
        invalid = [
            {},
            {"photos": []},
            {"photos": [{}]},
            {"photos": [{"data": "@@invalid"}]},
            {"photos": [{"data": base64.b64encode(b"not an image").decode()}]},
        ]
        for payload in invalid:
            self.assertEqual(self.call("/api/import", payload)[0], 400)
        self.assertFalse(list(self.folder.glob("capo-*")))

    def test_import_does_not_trust_filenames(self):
        photo = self.add_photo()
        with patch.object(app, "analyze", return_value=example_item()):
            status, _ = self.call(
                "/api/import",
                {
                    "photos": [
                        {
                            "name": "../../escape.exe",
                            "data": base64.b64encode(photo.read_bytes()).decode(),
                        }
                    ]
                },
            )
            self.assertEqual(status, 200)
            self.wait_for_scan()
        self.assertFalse((self.root / "escape.exe").exists())

    def test_defaults_fill_only_empty_fields_and_reprice(self):
        item = self.seed()
        item.update(size="", package_size="")
        core.write_json(app.DB, {"sample": item})
        cfg = self.cfg | {
            "defaults": {"size": "L", "package_size": "medio", "brand": "NON SOVRASCRIVERE"}
        }
        cfg["pricing"]["base"]["felpa"] = 17
        self.assertEqual(self.call("/api/config", cfg)[0], 200)
        self.assertEqual(self.call("/api/defaults", {})[0], 200)
        saved = core.read_json(app.DB)["sample"]
        self.assertEqual(saved["size"], "L")
        self.assertEqual(saved["brand"], "Esempio")
        self.assertEqual(saved["price"], 17)
        self.assertEqual(saved["status"], "ready")

    def test_defaults_do_not_change_published_items(self):
        self.seed(status="published")
        self.assertEqual(self.call("/api/defaults", {})[0], 200)
        self.assertEqual(core.read_json(app.DB)["sample"]["status"], "published")

    def test_bulk_download_contains_only_ready_items_and_relative_photo_paths(self):
        ready = self.seed("ready")
        draft = dict(ready, id="draft", size="", status="draft")
        core.write_json(app.DB, {"sample": ready, "draft": draft})
        status, raw = self.call("/download")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"sample/01.jpg", "sample/annuncio.json", "sample/annuncio.txt"},
            )
            self.assertNotIn(str(self.root).encode(), archive.read("sample/annuncio.json"))
        self.seed("draft")
        self.assertEqual(self.call("/download")[0], 400)

    def test_api_key_is_never_returned_in_state_or_saved_plaintext(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                self.call("/api/key", {"key": "test-session-key", "remember": False})[0], 200
            )
            state = self.call("/api/state")[1]
            self.assertTrue(state["has_key"])
            self.assertNotIn("test-session-key", str(state))
            self.assertFalse((self.data / "api-key.dpapi").exists())
            self.assertEqual(self.call("/api/key", {"key": "bad key"})[0], 400)

    def test_session_only_key_removes_previous_remembered_value(self):
        with patch.dict(os.environ, {}, clear=True):
            self.data.mkdir()
            saved = self.data / "api-key.dpapi"
            saved.write_bytes(b"old-encrypted-value")
            self.assertEqual(
                self.call("/api/key", {"key": "new-session-only", "remember": False})[0], 200
            )
            self.assertFalse(saved.exists())

    def test_default_validation_rejects_unknown_fields_and_states(self):
        for defaults in ({"title": "wrong"}, {"size": []}, {"condition": "inventato"}):
            self.assertEqual(self.call("/api/config", self.cfg | {"defaults": defaults})[0], 400)

    def test_static_assets_and_unlisted_paths(self):
        self.assertEqual(self.call("/app.js")[0], 200)
        self.assertEqual(self.call("/style.css")[0], 200)
        self.assertEqual(self.call("/credentials.py")[0], 404)


class CredentialTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_windows_key_round_trip_is_encrypted(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            file = Path(folder) / "key.dpapi"
            credentials.remember_key(file, "test-only-value")
            self.assertNotIn(b"test-only-value", file.read_bytes())
            self.assertTrue(credentials.restore_key(file))
            self.assertEqual(os.environ["OPENAI_API_KEY"], "test-only-value")

    def test_corrupt_saved_key_does_not_break_startup(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            file = Path(folder) / "key.dpapi"
            file.write_bytes(b"corrupt")
            self.assertFalse(credentials.restore_key(file))
