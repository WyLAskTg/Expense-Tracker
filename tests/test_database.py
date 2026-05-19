import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import (
    database_init,
    delete_category,
    generate_due_recurring_records,
    get_accounts,
    get_setting,
    insert_record,
    load_categories,
    load_recurring_rules,
    load_records,
    run_auto_backup,
    save_category,
    set_setting,
    upsert_recurring_rule,
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
        shutil.rmtree(Path(self.db_path).parent / "backups", ignore_errors=True)
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

    def test_accounts_are_saved_and_filterable(self):
        insert_record("expense", "Food", 1234, "lunch", "2026-05-18", account="Card")
        insert_record("expense", "Food", 500, "cash", "2026-05-18", account="Cash")

        self.assertIn("Card", get_accounts())
        records = load_records(account="Card")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["account"], "Card")

    def test_recurring_rules_generate_once_per_month(self):
        upsert_recurring_rule(
            "Rent",
            "expense",
            "Housing",
            "Bank",
            120000,
            "monthly rent",
            1,
        )

        self.assertEqual(generate_due_recurring_records(today=date(2026, 5, 19)), 1)
        self.assertEqual(generate_due_recurring_records(today=date(2026, 5, 19)), 0)
        records = load_records(month="2026-05", category="Housing", account="Bank")
        rules = load_recurring_rules()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount_cents"], 120000)
        self.assertEqual(rules[0]["last_generated_month"], "2026-05")

    def test_auto_backup_runs_once_per_day(self):
        first_backup = run_auto_backup(keep=2, today=date(2026, 5, 18))
        second_backup = run_auto_backup(keep=2, today=date(2026, 5, 18))

        self.assertIsNotNone(first_backup)
        self.assertTrue(Path(first_backup).exists())
        self.assertIsNone(second_backup)


if __name__ == "__main__":
    unittest.main()
