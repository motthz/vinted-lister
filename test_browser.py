"""Real Chromium tests for the simplified flow, isolated from real services."""

import os
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

import app
import core
from test_integration import IsolatedApp, example_item


class BrowserTests(IsolatedApp):
    def test_change_key_form_survives_polling(self):
        with (
            sync_playwright() as p,
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-existing-key"}),
        ):
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.url)
                page.wait_for_selector("#price-table input", state="attached")
                self.assertFalse(page.locator("#setup").is_visible())
                page.locator("#open-settings").click()
                page.locator("summary").filter(has_text="Avanzate").click()
                page.locator("#change-key").click()
                page.locator("#api-key").fill("test-new-value")
                page.evaluate("refresh(false)")
                self.assertTrue(page.locator("#api-key").is_visible())
                self.assertEqual(page.locator("#api-key").input_value(), "test-new-value")
            finally:
                browser.close()

    def test_full_workflow_desktop_and_mobile(self):
        self.add_photo()
        with sync_playwright() as p, patch.object(app, "analyze", return_value=example_item()):
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.url)
                page.wait_for_selector("#price-table input", state="attached")
                page.locator("#open-settings").click()
                self.assertEqual(page.locator("#price-table input").count(), len(core.CATEGORIES))
                self.assertEqual(page.locator("[data-category=maglietta]").input_value(), "5")
                self.assertEqual(page.locator("[data-category=felpa]").input_value(), "15")
                page.locator("summary").filter(has_text="Listino prezzi").click()
                page.locator("[data-category=giacca]").fill("23")
                page.locator("#settings").click()
                page.wait_for_function("!document.querySelector('#settings-dialog').open")
                self.assertEqual(core.config()["pricing"]["base"]["giacca"], 23)
                with patch("subprocess.run") as dialog:
                    dialog.return_value.returncode = 0
                    dialog.return_value.stdout = str(self.folder)
                    page.locator("#choose-folder").click()
                    page.wait_for_selector(".card")
                self.assertTrue(core.config()["watch"])
                self.assertEqual(page.locator(".card").count(), 1)
                self.assertEqual(page.locator(".badge").text_content(), "Pronto per esportazione")
                page.locator(".card summary").click()
                page.locator("[name=category]").select_option("maglietta")
                page.locator("[name=title]").fill('<img src=x onerror="window.injected=true">')
                # No save click: the new flow persists automatically.
                page.wait_for_function(
                    "document.querySelector('.price').textContent.startsWith('5,00')"
                )
                self.assertFalse(page.evaluate("Boolean(window.injected)"))
                page.get_by_role("button", name="Esporta questo capo").click()
                page.wait_for_function(
                    "document.querySelector('#toast').textContent.includes('Esportato')"
                )
                self.assertEqual(len(list((self.data / "exports").glob("*/annuncio.json"))), 1)
                with page.expect_download() as result:
                    page.locator("#download").click()
                download = result.value
                self.assertEqual(download.suggested_filename, "annunci-vinted.zip")
                self.assertIsNone(download.failure())
                page.reload()
                page.wait_for_selector(".card")
                self.assertEqual(page.locator("[name=category]").input_value(), "maglietta")
                page.wait_for_function("document.querySelector('.images img').naturalWidth > 0")
                artifacts = Path("artifacts")
                artifacts.mkdir(exist_ok=True)
                page.screenshot(path=str(artifacts / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(
                    page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                )
                page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_photo_picker_imports_and_analyzes_without_manual_scan(self):
        photo = self.add_photo()
        with sync_playwright() as p, patch.object(app, "analyze", return_value=example_item()):
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.url)
                page.wait_for_selector("#price-table input", state="attached")
                page.locator("#upload").set_input_files(str(photo))
                page.wait_for_selector(".card")
                self.assertEqual(page.locator(".card").count(), 1)
                self.assertTrue(any(self.folder.glob("capo-*")))
                self.assertTrue(page.locator("#download").is_visible())
            finally:
                browser.close()

    def test_missing_fields_only_and_bulk_defaults(self):
        item = self.seed()
        item["size"] = ""
        item["package_size"] = ""
        core.write_json(app.DB, {"sample": item})
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(self.url)
                page.wait_for_selector(".card")
                self.assertTrue(page.locator("[name=size]").is_visible())
                self.assertFalse(page.locator("[name=title]").is_visible())
                page.locator("#open-settings").click()
                page.locator("[name=default-size]").fill("M")
                page.locator("[name=default-package_size]").fill("medio")
                page.locator("#settings").click()
                page.wait_for_function(
                    "document.querySelector('.badge').textContent === 'Pronto per esportazione'"
                )
                self.assertEqual(core.read_json(app.DB)["sample"]["size"], "M")
                page.locator("[data-filter=todo]").click()
                self.assertEqual(page.locator(".card").count(), 0)
                page.locator("[data-filter=ready]").click()
                self.assertEqual(page.locator(".card").count(), 1)
            finally:
                browser.close()
