"""Browser adapter: login manuale, nessuna API privata o elusione di CAPTCHA.
I selettori devono essere verificati sulla versione corrente del sito prima dell'uso.
"""

import argparse
import os
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from core import DATA, ROOT, missing, read_json, write_json


@contextmanager
def publication_lock():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = DATA / "publisher.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(
            "Un altro publisher è attivo. Se è stato interrotto, verifica gli annunci su Vinted prima di rimuovere data/publisher.lock."
        ) from None
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def main():
    with publication_lock():
        run()


def run():
    parser = argparse.ArgumentParser(
        description="Compilazione browser Vinted (integrazione da configurare e verificare)"
    )
    parser.add_argument("id", nargs="?", help="ID annuncio, visibile nel file esportato")
    parser.add_argument("--login", action="store_true")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Invia dopo la compilazione; richiede selettori verificati",
    )
    args = parser.parse_args()
    item = None
    mapping = read_json(ROOT / "vinted-selectors.json", {})
    if not args.login:
        item = read_json(DATA / "items.json", {}).get(args.id)
        if not item:
            parser.error("ID annuncio non trovato")
        if item.get("status") in ("published", "publishing"):
            parser.error("Annuncio già pubblicato o invio da verificare: nessun nuovo invio")
        if missing(item):
            parser.error("Dati mancanti: " + ", ".join(missing(item)))
        required = [
            "title",
            "description",
            "price",
            "category",
            "brand",
            "size",
            "condition",
            "color",
            "material",
            "package_size",
            "photos",
        ]
        if any(not mapping.get(k, {}).get("selector") for k in required):
            parser.error(
                "Configura e verifica vinted-selectors.json: mancano selettori per uno o più campi. Vedi README."
            )
        if args.publish and not all(
            mapping.get(k, {}).get("selector") for k in ("publish", "success")
        ):
            parser.error("Per pubblicare servono i selettori publish e success verificati.")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(ROOT / "browser-profile"), headless=False
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://www.vinted.it/items/new")
            if args.login:
                input("Accedi dal browser, poi premi Invio qui per salvare la sessione. ")
                return
            page.locator(mapping["photos"]["selector"]).set_input_files(item["photos"])
            for field in required:
                if field == "photos":
                    continue
                spec = mapping[field]
                value = str(item[field])
                locator = page.locator(spec["selector"])
                action = spec.get("action", "fill")
                if action == "fill":
                    locator.fill(value)
                elif action == "select":
                    locator.select_option(label=spec.get("values", {}).get(value, value))
                elif action == "click_option":
                    locator.click()
                    option = spec.get("values", {}).get(value, value)
                    page.get_by_text(option, exact=True).click()
                else:
                    raise ValueError("Azione sconosciuta: " + action)
            if not args.publish:
                input(
                    "Controlla tutti i dati nel browser. Puoi pubblicare manualmente. Invio per chiudere. "
                )
                return
            # Persist before clicking: a timeout must never trigger an automatic duplicate.
            items = read_json(DATA / "items.json", {})
            items[item["id"]]["status"] = "publishing"
            write_json(DATA / "items.json", items)
            page.locator(mapping["publish"]["selector"]).click()
            page.locator(mapping["success"]["selector"]).wait_for(state="visible", timeout=30000)
            items = read_json(DATA / "items.json", {})
            items[item["id"]].update(status="published", published_url=page.url)
            write_json(DATA / "items.json", items)
            print("Pubblicato:", page.url)
        finally:
            context.close()


if __name__ == "__main__":
    main()
