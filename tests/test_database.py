import os
import tempfile
import unittest
from pathlib import Path

from database import (
    database_init,
    delete_category,
    get_setting,
    insert_record,
    load_categories,
    load_records,
    save_category,
    set_setting,
    upsert_budget,
)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        Path(self.db_path).unlink()
        os.environ["EXPENSE_TRACKER_DB"] = self.db_path
        database_init()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)
        os.environ.pop("EXPENSE_TRACKER_DB", None)

    def test_category_rename_updates_records_and_budgets(self):
        category_id = save_category("Food", color="#18794e", default_budget_cents=5000)
        insert_record("expense", "Food", 1234, "lunch", "2026-05-18")
        upsert_budget("2026-05", "Food", 5000)

        save_category("Meals", color="#b42318", default_budget_cents=6000, category_id=category_id)

        records = load_records(category="Meals")
        categories = load_categories()
        meals = next(category for category in categories if category["name"] == "Meals")

        self.assertEqual(len(records), 1)
        self.assertEqual(meals["record_count"], 1)
        self.assertEqual(meals["budget_count"], 1)
        self.assertEqual(meals["default_budget_cents"], 6000)

    def test_unused_category_can_be_deleted(self):
        category_id = save_category("Unused", color="#57606a")
        self.assertEqual(delete_category(category_id), 1)

    def test_settings_round_trip(self):
        set_setting("language", "ja")
        self.assertEqual(get_setting("language"), "ja")


if __name__ == "__main__":
    unittest.main()
