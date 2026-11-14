import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import core
import publisher
from test_integration import example_item


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.item = dict(
            example_item(), id="sample", photos=["example.jpg"], status="ready", price=15
        )
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(publisher, "ROOT", self.root))
        self.stack.enter_context(patch.object(publisher, "DATA", self.data))
        self.save()
        self.specs = {
            key: {"selector": "#" + key, "action": "fill"}
            for key in core.FIELDS + ["price", "photos", "publish", "success"]
        }
        self.specs["category"].update(action="select")
        self.specs["condition"].update(action="click_option", values={"buono": "Buono"})
        core.write_json(self.root / "vinted-selectors.json", self.specs)
        self.playwright = MagicMock()
        self.context = (
            self.playwright.__enter__.return_value.chromium.launch_persistent_context.return_value
        )
        self.page = self.context.pages[0]
        self.page.url = "https://www.vinted.it/items/123"
        self.stack.enter_context(
            patch.object(publisher, "sync_playwright", return_value=self.playwright)
        )
        self.stack.enter_context(patch("builtins.input", return_value=""))

    def save(self):
        core.write_json(self.data / "items.json", {"sample": self.item})

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def run_cli(self, *args):
        with patch("sys.argv", ["publisher.py", *args]):
            publisher.main()

    def test_login_releases_lock_and_closes_browser(self):
        self.run_cli("--login")
        self.context.close.assert_called_once()
        self.assertFalse((self.data / "publisher.lock").exists())

    def test_preview_fills_and_never_clicks_publish(self):
        self.run_cli("sample")
        self.page.locator.assert_any_call("#photos")
        self.page.get_by_text.assert_called_once_with("Buono", exact=True)
        self.assertNotIn(unittest.mock.call("#publish"), self.page.locator.call_args_list)
        self.assertEqual(core.read_json(self.data / "items.json")["sample"]["status"], "ready")

    def test_publish_persists_success(self):
        self.run_cli("sample", "--publish")
        saved = core.read_json(self.data / "items.json")["sample"]
        self.assertEqual(saved["status"], "published")
        self.assertEqual(saved["published_url"], self.page.url)
        self.context.close.assert_called_once()

    def test_timeout_preserves_uncertain_state_and_blocks_retry(self):
        self.page.locator.return_value.wait_for.side_effect = TimeoutError("Timeout")
        with self.assertRaises(TimeoutError):
            self.run_cli("sample", "--publish")
        self.assertEqual(core.read_json(self.data / "items.json")["sample"]["status"], "publishing")
        self.assertFalse((self.data / "publisher.lock").exists())
        with self.assertRaises(SystemExit):
            self.run_cli("sample", "--publish")

    def test_missing_selectors_and_missing_fields_fail_before_browser(self):
        self.specs["size"]["selector"] = ""
        core.write_json(self.root / "vinted-selectors.json", self.specs)
        with self.assertRaises(SystemExit):
            self.run_cli("sample")
        self.playwright.__enter__.assert_not_called()
        self.item["size"] = ""
        self.save()
        with self.assertRaises(SystemExit):
            self.run_cli("sample")

    def test_missing_publish_selectors_block_send(self):
        self.specs["success"]["selector"] = ""
        core.write_json(self.root / "vinted-selectors.json", self.specs)
        with self.assertRaises(SystemExit):
            self.run_cli("sample", "--publish")
        self.playwright.__enter__.assert_not_called()

    def test_lock_blocks_second_publisher(self):
        with publisher.publication_lock():
            with self.assertRaises(RuntimeError):
                self.run_cli("--login")
        self.assertFalse((self.data / "publisher.lock").exists())

    def test_unknown_action_closes_context_without_sending(self):
        self.specs["title"]["action"] = "unknown"
        core.write_json(self.root / "vinted-selectors.json", self.specs)
        with self.assertRaises(ValueError):
            self.run_cli("sample", "--publish")
        self.context.close.assert_called_once()
        self.assertEqual(core.read_json(self.data / "items.json")["sample"]["status"], "ready")
