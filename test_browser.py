"""Real Chromium tests against an isolated local server, with mocked AI only."""

from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

import app
import core
from test_integration import IsolatedApp, example_item


class BrowserTests(IsolatedApp):
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
                page.locator("summary").first.click()
                self.assertEqual(page.locator("#price-table input").count(), len(core.CATEGORIES))
                self.assertEqual(page.locator("[data-category=maglietta]").input_value(), "5")
                self.assertEqual(page.locator("[data-category=felpa]").input_value(), "15")
                page.locator("[data-category=giacca]").fill("23")
                page.locator("#settings").click()
                page.wait_for_function(
                    "document.querySelector('#toast').textContent.includes('salvate')"
                )
                self.assertEqual(core.config()["pricing"]["base"]["giacca"], 23)
                with patch("subprocess.run") as dialog:
                    dialog.return_value.returncode = 0
                    dialog.return_value.stdout = str(self.folder)
                    page.locator("#pick").click()
                    page.wait_for_function(
                        '(value)=>document.querySelector("#folder").value===value',
                        arg=str(self.folder),
                    )
                page.locator("#settings").click()
                page.locator("#scan").click()
                page.wait_for_selector(".card")
                self.assertEqual(page.locator(".card").count(), 1)
                self.assertEqual(page.locator("[name=category]").input_value(), "felpa")
                page.locator("[name=category]").select_option("maglietta")
                page.locator("[name=title]").fill('<img src=x onerror="window.injected=true">')
                page.locator("button[type=submit]").click()
                page.wait_for_function(
                    "document.querySelector('.card form h3').textContent.trim() === '€ 5.00'"
                )
                self.assertEqual(
                    page.locator(".badge").last.text_content(), "Pronto per esportazione"
                )
                self.assertFalse(page.evaluate("Boolean(window.injected)"))
                page.get_by_role("button", name="Esporta foto e annuncio").click()
                page.wait_for_function(
                    "document.querySelector('#toast').textContent.includes('Esportato')"
                )
                self.assertEqual(len(list((self.data / "exports").glob("*/annuncio.json"))), 1)
                page.reload()
                page.wait_for_selector(".card")
                self.assertEqual(page.locator("[name=category]").input_value(), "maglietta")
                self.assertTrue(
                    page.locator(".images img").evaluate(
                        "(img)=>img.complete && img.naturalWidth>0"
                    )
                )
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
