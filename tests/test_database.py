import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import (
    archive_account,
    cleanup_tags,
    count_records,
    create_backup_archive,
    database_init,
    delete_category,
    delete_classification_rule,
    delete_record,
    delete_transfer,
    decrypt_database,
    encrypt_database,
    find_duplicate_records,
    generate_due_recurring_records,
    get_accounts,
    get_attachments_dir,
    get_setting,
    insert_record,
    insert_transfer,
    load_account_balances,
    load_accounts_detail,
    load_activity_logs,
    load_budget_alerts,
    load_categories,
    load_classification_rules,
    load_recurring_rules,
    load_records,
    load_transfers,
    log_activity,
    match_classification_rule,
    merge_account_records,
    merge_category_records,
    restore_backup_archive,
    restore_record,
    restore_transfer,
    run_auto_backup,
    save_account,
    save_category,
    save_classification_rule,
    set_setting,
    split_record,
    store_attachment,
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
        shutil.rmtree(Path(self.db_path).parent / "attachments", ignore_errors=True)
        (Path(self.db_path).parent / "backup.zip").unlink(missing_ok=True)
        (Path(self.db_path).parent / "receipt.txt").unlink(missing_ok=True)
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

    def test_records_support_tags_attachments_and_advanced_filters(self):
        insert_record(
            "expense",
            "Food",
            1234,
            "client lunch",
            "2026-05-18",
            account="Card",
            tags="food,work",
            attachment_path="receipt.pdf",
        )
        insert_record("income", "Salary", 200000, "pay", "2026-05-19", account="Bank", tags="pay")

        records = load_records(
            tag="food",
            record_type="expense",
            search="work",
            date_from="2026-05-01",
            date_to="2026-05-31",
            amount_min_cents=1000,
            amount_max_cents=2000,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tags"], "food,work")
        self.assertEqual(records[0]["attachment_path"], "receipt.pdf")

    def test_record_count_supports_pagination_filters(self):
        for index in range(3):
            insert_record("expense", "Food", 100 + index, f"lunch {index}", "2026-05-18", tags="food")

        records = load_records(tag="food", limit=2, offset=1)

        self.assertEqual(count_records(tag="food"), 3)
        self.assertEqual(len(records), 2)

    def test_account_metadata_and_archive_state_are_saved(self):
        account_id = save_account(
            "Credit Card",
            opening_balance_cents=-5000,
            account_type="credit",
            icon="CC",
            archived=True,
            sort_order=5,
        )

        details = {row["name"]: row for row in load_accounts_detail(include_archived=True)}

        self.assertEqual(details["Credit Card"]["type"], "credit")
        self.assertEqual(details["Credit Card"]["icon"], "CC")
        self.assertEqual(details["Credit Card"]["sort_order"], 5)
        self.assertTrue(details["Credit Card"]["archived"])
        self.assertNotIn("Credit Card", get_accounts())

        archive_account(account_id, archived=False)
        self.assertIn("Credit Card", get_accounts())

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

    def test_auto_backup_can_copy_to_custom_folder(self):
        with tempfile.TemporaryDirectory() as custom_folder:
            set_setting("auto_backup_folder", custom_folder)
            backup = run_auto_backup(keep=2, today=date(2026, 5, 17))

            copied = Path(custom_folder) / Path(backup).name
            self.assertTrue(copied.exists())

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

    def test_budget_alerts_and_data_quality_helpers(self):
        insert_record("expense", "Food", 9000, "lunch", "2026-05-18", account="Card", tags="Food, work,food")
        insert_record("expense", "Food", 9000, "duplicate", "2026-05-18", account="Card")
        upsert_budget("2026-05", "Food", 10000)

        alerts = load_budget_alerts("2026-05")
        duplicates = find_duplicate_records()
        tag_updates = cleanup_tags()
        category_counts = merge_category_records("Food", "Meals")
        account_counts = merge_account_records("Card", "Cash")
        records = load_records(category="Meals", account="Cash")

        self.assertEqual(alerts[0]["category"], "Food")
        self.assertGreaterEqual(alerts[0]["usage"], 1)
        self.assertEqual(duplicates[0]["duplicate_count"], 2)
        self.assertEqual(tag_updates, 1)
        self.assertEqual(category_counts["records"], 2)
        self.assertEqual(account_counts["records"], 2)
        self.assertEqual(len(records), 2)

    def test_classification_rules_activity_and_split_records(self):
        rule_id = save_classification_rule("starbucks", "expense", "Coffee", "Card", tags="coffee")
        rule = match_classification_rule("Morning Starbucks run", "expense")

        self.assertEqual(rule["category"], "Coffee")
        self.assertEqual(load_classification_rules()[0]["id"], rule_id)

        record_id = insert_record("expense", "Groceries", 3000, "mixed cart", "2026-05-18", account="Card")
        outcome = split_record(
            record_id,
            [
                {"category": "Food", "amount_cents": 2000, "note": "food"},
                {"category": "Home", "amount_cents": 1000, "note": "soap"},
            ],
        )
        log_activity("test_action", "detail", outcome["new_ids"][0])

        self.assertEqual(len(outcome["new_ids"]), 2)
        self.assertEqual(count_records(), 2)
        self.assertEqual(load_activity_logs()[0]["action"], "test_action")
        self.assertEqual(delete_classification_rule(rule_id), 1)

    def test_attachment_store_and_backup_archive_restore(self):
        source = Path(self.db_path).parent / "receipt.txt"
        source.write_text("receipt", encoding="utf-8")
        stored = store_attachment(source)
        insert_record("expense", "Food", 1234, "lunch", "2026-05-18", attachment_path=str(stored))

        archive = Path(self.db_path).parent / "backup.zip"
        create_backup_archive(archive)
        delete_record(load_records()[0]["id"])
        restore_backup_archive(archive)

        self.assertTrue(stored.exists())
        self.assertEqual(stored.parent, get_attachments_dir())
        self.assertEqual(load_records()[0]["category"], "Food")

    def test_database_encryption_round_trip(self):
        insert_record("expense", "Food", 1234, "lunch", "2026-05-18", account="Cash")
        encrypted = encrypt_database("secret", remove_plaintext=True)

        self.assertTrue(encrypted.exists())
        self.assertFalse(Path(self.db_path).exists())

        decrypt_database("secret")
        self.assertEqual(load_records()[0]["category"], "Food")


if __name__ == "__main__":
    unittest.main()
