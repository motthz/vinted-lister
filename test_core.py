import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import CATEGORIES, analyze, config, groups, missing, price, validate_config


class CoreTests(unittest.TestCase):
    def test_fixed_prices_ignore_brand_state_retail(self):
        rules = config()["pricing"]
        for category, expected in [("maglietta", 5), ("felpa", 15)]:
            value, _ = price(
                {
                    "category": category,
                    "condition": "discreto",
                    "brand": "Gucci",
                    "retail_price": 999,
                },
                rules,
            )
            self.assertEqual(value, expected)

    def test_bad_price_is_rejected(self):
        rules = config()["pricing"]
        rules["base"]["maglietta"] = float("nan")
        with self.assertRaises(ValueError):
            price({"category": "maglietta"}, rules)

    def test_grouping_and_content_deduplication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "capo").mkdir()
            (root / "capo" / "1.jpg").write_bytes(b"front")
            (root / "capo" / "2.jpg").write_bytes(b"label")
            first = list(groups(root))
            self.assertEqual(len(first), 1)
            self.assertEqual(len(first[0][2]), 2)
            (root / "capo").rename(root / "renamed")
            self.assertEqual(first[0][0], list(groups(root))[0][0])
            (root / "renamed" / "2.jpg").write_bytes(b"changed")
            self.assertNotEqual(first[0][0], list(groups(root))[0][0])

    def test_missing_values_block_readiness(self):
        self.assertIn("size", missing({"size": ""}))

    def test_no_key_fails_before_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                analyze([], "example")

    def test_all_category_prices_match_price_list(self):
        rules = config()["pricing"]
        for category, amount in CATEGORIES.items():
            with self.subTest(category=category):
                self.assertEqual(price({"category": category}, rules)[0], amount)

    def test_formula_uses_retail_brand_condition_and_margin(self):
        rules = config()["pricing"]
        rules.update(mode="formula", brand={"NIKE": 1.2})
        value, _ = price(
            {"category": "maglietta", "retail_price": 100, "brand": "nike", "condition": "buono"},
            rules,
        )
        self.assertEqual(value, 39.5)
        rules["maximum"] = 10
        self.assertEqual(price({"category": "felpa", "retail_price": 100}, rules)[0], 10)
        rules["minimum"] = 5
        self.assertEqual(price({"category": "felpa", "retail_price": 1}, rules)[0], 5)

    def test_invalid_configs_rejected(self):
        for field, value in [("model", ""), ("watch", "true"), ("folder", None)]:
            cfg = config()
            cfg[field] = value
            with self.assertRaises(ValueError):
                validate_config(cfg)
        cfg = config()
        cfg["pricing"]["mode"] = "unknown"
        with self.assertRaises(ValueError):
            validate_config(cfg)

    def test_content_boundaries_and_photo_reordering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, chunks in [
                ("one", [b"ab", b"c"]),
                ("two", [b"a", b"bc"]),
                ("three", [b"c", b"ab"]),
            ]:
                (root / name).mkdir()
                for index, chunk in enumerate(chunks):
                    (root / name / f"{index}.jpg").write_bytes(chunk)
            ids = {name: ident for ident, name, _ in groups(root)}
            self.assertNotEqual(ids["one"], ids["two"])
            self.assertEqual(ids["one"], ids["three"])

    def test_root_images_and_ignored_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "foto.JPG").write_bytes(b"image")
            (root / "notes.txt").write_text("ignore")
            (root / "empty").mkdir()
            self.assertEqual(len(list(groups(root))), 1)
            with self.assertRaises(ValueError):
                list(groups(root / "missing"))


if __name__ == "__main__":
    unittest.main()
