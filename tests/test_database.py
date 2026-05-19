import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import (
    database_init,
    delete_category,
    delete_record,
    delete_transfer,
    decrypt_database,
    encrypt_database,
    generate_due_recurring_records,
    get_accounts,
    get_setting,
    insert_record,
    insert_transfer,
    load_account_balances,
    load_categories,
    load_recurring_rules,
    load_records,
    load_transfers,
    restore_record,
    restore_transfer,
    run_auto_backup,
    save_account,
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

    def test_account_balances_include_transfers(self):
        save_account("Cash", opening_balance_cents=10000)
        save_account("Card", opening_balance_cents=5000)
        insert_record("income", "Salary", 20000, "", "2026-05-18", account="Cash")
        insert_record("expense", "Food", 2500, "", "2026-05-18", account="Card")
        insert_transfer("2026-05-18", "Cash", "Card", 3000, "top up")

        balances = {row["name"]: row["balance_cents"] for row in load_account_balances()}

        self.assertEqual(balances["Cash"], 27000)
        self.assertEqual(balances["Card"], 5500)

    def test_deleted_record_and_transfer_can_be_restored(self):
        record_id = insert_record("expense", "Food", 1234, "lunch", "2026-05-18", account="Cash")
        record = load_records()[0]
        self.assertEqual(delete_record(record_id), 1)
        restore_record(record)
        self.assertEqual(load_records()[0]["id"], record_id)

        transfer_id = insert_transfer("2026-05-18", "Cash", "Card", 500, "move")
        transfer = load_transfers()[0]
        self.assertEqual(delete_transfer(transfer_id), 1)
        restore_transfer(transfer)
        self.assertEqual(load_transfers()[0]["id"], transfer_id)

    def test_weekly_recurring_rule_uses_next_due_date(self):
        upsert_recurring_rule(
            "Allowance",
            "income",
            "Salary",
            "Cash",
            1000,
            "",
            1,
            frequency="weekly",
            interval_count=1,
            start_date="2026-05-01",
        )

        self.assertEqual(generate_due_recurring_records(today=date(2026, 5, 15)), 3)
        records = load_records(category="Salary", account="Cash")
        rules = load_recurring_rules()

        self.assertEqual(len(records), 3)
        self.assertEqual(rules[0]["last_generated_date"], "2026-05-15")
        self.assertEqual(rules[0]["next_due_date"], "2026-05-22")

    def test_database_encryption_round_trip(self):
        insert_record("expense", "Food", 1234, "lunch", "2026-05-18", account="Cash")
        encrypted = encrypt_database("secret", remove_plaintext=True)

        self.assertTrue(encrypted.exists())
        self.assertFalse(Path(self.db_path).exists())

        decrypt_database("secret")
        self.assertEqual(load_records()[0]["category"], "Food")


if __name__ == "__main__":
    unittest.main()
