import tempfile
import unittest
from pathlib import Path

from record_utils import (
    amount_to_cents,
    money_text,
    parse_csv_records,
    parse_month,
    parse_record_date,
    split_new_and_duplicate_records,
)


class RecordUtilsTest(unittest.TestCase):
    def test_amount_to_cents_rounds_half_up(self):
        self.assertEqual(amount_to_cents("12.345"), 1235)
        self.assertEqual(amount_to_cents("1,000.00"), 100000)

    def test_money_text_uses_currency_symbol(self):
        self.assertEqual(money_text(1234, "¥"), "¥12.34")
        self.assertEqual(money_text(-1234, "€"), "-€12.34")

    def test_date_and_month_parsing(self):
        self.assertEqual(parse_record_date("2026-05-18"), "2026-05-18")
        self.assertEqual(parse_month("2026-05"), "2026-05")
        self.assertIsNone(parse_month(""))

    def test_csv_parse_and_duplicate_split(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8", delete=False) as tmp:
            tmp.write("date,type,category,amount,note\n")
            tmp.write("2026-05-18,expense,Food,12.34,lunch\n")
            tmp.write("2026-05-18,expense,Food,12.34,duplicate note\n")
            path = tmp.name

        try:
            parsed = parse_csv_records(path)
            new_records, duplicates = split_new_and_duplicate_records(parsed, [])
            self.assertEqual(len(new_records), 1)
            self.assertEqual(len(duplicates), 1)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_csv_reports_row_errors(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8", delete=False) as tmp:
            tmp.write("date,type,category,amount\n")
            tmp.write("2026-05-18,bad,Food,12.34\n")
            path = tmp.name

        try:
            with self.assertRaises(ValueError) as ctx:
                parse_csv_records(path)
            self.assertIn("Row 2", str(ctx.exception))
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
