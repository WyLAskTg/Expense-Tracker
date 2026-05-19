import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANT = Decimal("1")
TYPE_OPTIONS = ("expense", "income")


def amount_to_cents(raw_amount):
    raw_amount = str(raw_amount).strip().replace(",", "")
    if not raw_amount:
        raise ValueError("Amount must be non-empty.")

    try:
        amount = Decimal(raw_amount)
    except InvalidOperation as exc:
        raise ValueError("Amount must be a valid number.") from exc

    if amount <= 0:
        raise ValueError("Amount must be positive.")

    return int((amount * 100).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def parse_record_date(raw_date):
    raw_date = str(raw_date).strip()
    if not raw_date:
        raise ValueError("Date must be non-empty.")

    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def parse_month(raw_month):
    raw_month = str(raw_month).strip()
    if not raw_month:
        return None

    try:
        datetime.strptime(raw_month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM format.") from exc

    return raw_month


def money_text(cents, currency_symbol="$"):
    cents = int(cents or 0)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{currency_symbol}{cents // 100}.{cents % 100:02d}"


def amount_entry_text(cents):
    cents = abs(int(cents or 0))
    return f"{cents // 100}.{cents % 100:02d}"


def record_signature(record):
    return (
        record["date"],
        record["type"],
        record["category"].strip().casefold(),
        record.get("account", "Cash").strip().casefold(),
        int(record["amount_cents"]),
    )


def csv_headers(path):
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("CSV file is missing a header row.")
        return [name for name in reader.fieldnames if name]


def default_csv_mapping(headers):
    normalized = {header.strip().lower(): header for header in headers}
    return {
        "date": normalized.get("date"),
        "type": normalized.get("type"),
        "category": normalized.get("category"),
        "account": normalized.get("account") or normalized.get("payment") or normalized.get("payment method"),
        "amount": normalized.get("amount"),
        "note": normalized.get("note") or normalized.get("description"),
    }


def parse_csv_records(path, mapping=None):
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("CSV file is missing a header row.")

        mapping = mapping or default_csv_mapping(reader.fieldnames)
        required = ("date", "type", "category", "amount")
        missing = [name for name in required if not mapping.get(name)]
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}.")

        imported = []
        errors = []
        for row_number, row in enumerate(reader, start=2):
            try:
                record_type = (row[mapping["type"]] or "").strip().lower()
                if record_type not in TYPE_OPTIONS:
                    raise ValueError("type must be income or expense")

                category = (row[mapping["category"]] or "").strip()
                if not category:
                    raise ValueError("category must be non-empty")

                account = (row.get(mapping.get("account") or "", "") or "").strip() or "Cash"

                imported.append(
                    {
                        "date": parse_record_date(row[mapping["date"]] or ""),
                        "type": record_type,
                        "category": category,
                        "account": account,
                        "amount_cents": amount_to_cents(row[mapping["amount"]] or ""),
                        "note": (row.get(mapping.get("note") or "", "") or "").strip(),
                    }
                )
            except ValueError as exc:
                errors.append(f"Row {row_number}: {exc}")

        if errors:
            detail = "\n".join(errors[:8])
            if len(errors) > 8:
                detail += f"\n...and {len(errors) - 8} more error(s)."
            raise ValueError(detail)

        return imported


def split_new_and_duplicate_records(imported_records, existing_records):
    existing_signatures = {record_signature(record) for record in existing_records}
    seen_signatures = set()
    new_records = []
    duplicates = []

    for record in imported_records:
        signature = record_signature(record)
        if signature in existing_signatures or signature in seen_signatures:
            duplicates.append(record)
            continue

        seen_signatures.add(signature)
        new_records.append(record)

    return new_records, duplicates
