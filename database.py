import json
import os
import shutil
import sqlite3
import zipfile
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from crypto_utils import decrypt_file, encrypt_file


APP_NAME = "PersonalExpenseTracker"
DB_NAME = "expense_tracker.db"
VALID_TYPES = {"income", "expense"}
DEFAULT_ACCOUNT = "Cash"
RECURRING_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
DEFAULT_CATEGORY_COLORS = (
    "#b42318",
    "#2f6f8f",
    "#9a6700",
    "#18794e",
    "#8250df",
    "#57606a",
    "#0969da",
    "#1f883d",
)


def _app_data_dir():
    override = os.getenv("EXPENSE_TRACKER_DB")
    if override:
        return Path(override).expanduser().resolve().parent

    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share"

    return Path(base) / APP_NAME


def get_db_path():
    override = os.getenv("EXPENSE_TRACKER_DB")
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    data_dir = _app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / DB_NAME

    legacy_path = Path(__file__).resolve().parent / DB_NAME
    encrypted_path = db_path.with_suffix(db_path.suffix + ".enc")
    if not db_path.exists() and not encrypted_path.exists() and legacy_path.exists():
        shutil.copy2(legacy_path, db_path)

    return db_path


def get_encrypted_db_path():
    return get_db_path().with_suffix(get_db_path().suffix + ".enc")


def encrypted_database_exists():
    return get_encrypted_db_path().exists()


def get_attachments_dir():
    folder = get_db_path().parent / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def store_attachment(source_path):
    source = Path(source_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)

    destination_dir = get_attachments_dir()
    safe_stem = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in source.stem).strip("_")
    safe_stem = safe_stem or "attachment"
    suffix = source.suffix.lower()
    destination = destination_dir / f"{safe_stem}{suffix}"
    counter = 1
    while destination.exists():
        destination = destination_dir / f"{safe_stem}-{counter}{suffix}"
        counter += 1
    shutil.copy2(source, destination)
    return destination


@contextmanager
def _connect():
    db = sqlite3.connect(get_db_path())
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def _today():
    return date.today().isoformat()


def _table_columns(cursor):
    cursor.execute("PRAGMA table_info(Records)")
    return {row["name"] for row in cursor.fetchall()}


def _columns_for_table(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in cursor.fetchall()}


def _category_color(name):
    total = sum(ord(char) for char in name)
    return DEFAULT_CATEGORY_COLORS[total % len(DEFAULT_CATEGORY_COLORS)]


def _ensure_category(cursor, name, color=None, default_budget_cents=0):
    name = name.strip()
    if not name:
        return

    cursor.execute(
        """
        INSERT OR IGNORE INTO Categories
            (name, color, default_budget_cents, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, color or _category_color(name), default_budget_cents, _now(), _now()),
    )


def _sync_categories(cursor):
    cursor.execute(
        """
        SELECT DISTINCT category
        FROM Records
        WHERE category IS NOT NULL AND TRIM(category) != ''
        """
    )
    names = {row["category"] for row in cursor.fetchall()}
    cursor.execute(
        """
        SELECT DISTINCT category
        FROM Budgets
        WHERE category IS NOT NULL AND TRIM(category) != ''
        """
    )
    names.update(row["category"] for row in cursor.fetchall())

    for name in sorted(names, key=str.casefold):
        _ensure_category(cursor, name)


def _ensure_account(cursor, name):
    name = (name or DEFAULT_ACCOUNT).strip() or DEFAULT_ACCOUNT
    cursor.execute(
        """
        INSERT OR IGNORE INTO Accounts (name, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        (name, _now(), _now()),
    )


def _sync_accounts(cursor):
    cursor.execute(
        """
        SELECT DISTINCT account
        FROM Records
        WHERE account IS NOT NULL AND TRIM(account) != ''
        """
    )
    names = {row["account"] for row in cursor.fetchall()}
    names.add(DEFAULT_ACCOUNT)
    for name in sorted(names, key=str.casefold):
        _ensure_account(cursor, name)


def _migrate_accounts_table(cursor):
    columns = _columns_for_table(cursor, "Accounts")
    if "opening_balance_cents" not in columns:
        cursor.execute("ALTER TABLE Accounts ADD COLUMN opening_balance_cents INTEGER NOT NULL DEFAULT 0")
    if "type" not in columns:
        cursor.execute("ALTER TABLE Accounts ADD COLUMN type TEXT NOT NULL DEFAULT 'asset'")
    if "icon" not in columns:
        cursor.execute("ALTER TABLE Accounts ADD COLUMN icon TEXT NOT NULL DEFAULT ''")
    if "archived" not in columns:
        cursor.execute("ALTER TABLE Accounts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    if "sort_order" not in columns:
        cursor.execute("ALTER TABLE Accounts ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")

    cursor.execute("UPDATE Accounts SET type = 'asset' WHERE type IS NULL OR TRIM(type) = ''")
    cursor.execute("UPDATE Accounts SET icon = '' WHERE icon IS NULL")
    cursor.execute("UPDATE Accounts SET archived = 0 WHERE archived IS NULL")
    cursor.execute("UPDATE Accounts SET sort_order = 0 WHERE sort_order IS NULL")


def _migrate_transfers_table(cursor):
    columns = _columns_for_table(cursor, "Transfers")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE Transfers ADD COLUMN created_at TEXT")
    if "updated_at" not in columns:
        cursor.execute("ALTER TABLE Transfers ADD COLUMN updated_at TEXT")

    now = _now()
    cursor.execute(
        "UPDATE Transfers SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
        (now,),
    )
    cursor.execute(
        "UPDATE Transfers SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''",
        (now,),
    )


def _migrate_recurring_rules_table(cursor):
    columns = _columns_for_table(cursor, "RecurringRules")
    if "frequency" not in columns:
        cursor.execute("ALTER TABLE RecurringRules ADD COLUMN frequency TEXT NOT NULL DEFAULT 'monthly'")
    if "interval_count" not in columns:
        cursor.execute("ALTER TABLE RecurringRules ADD COLUMN interval_count INTEGER NOT NULL DEFAULT 1")
    if "start_date" not in columns:
        cursor.execute("ALTER TABLE RecurringRules ADD COLUMN start_date TEXT")
    if "end_date" not in columns:
        cursor.execute("ALTER TABLE RecurringRules ADD COLUMN end_date TEXT")
    if "last_generated_date" not in columns:
        cursor.execute("ALTER TABLE RecurringRules ADD COLUMN last_generated_date TEXT")

    cursor.execute("UPDATE RecurringRules SET frequency = 'monthly' WHERE frequency IS NULL OR TRIM(frequency) = ''")
    cursor.execute("UPDATE RecurringRules SET interval_count = 1 WHERE interval_count IS NULL OR interval_count < 1")


def _migrate_records_table(cursor):
    columns = _table_columns(cursor)

    if "date" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN date TEXT")
    if "amount_cents" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN amount_cents INTEGER")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN created_at TEXT")
    if "updated_at" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN updated_at TEXT")
    if "account" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN account TEXT")
    if "tags" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN tags TEXT")
    if "attachment_path" not in columns:
        cursor.execute("ALTER TABLE Records ADD COLUMN attachment_path TEXT")

    today = _today()
    now = _now()
    cursor.execute("UPDATE Records SET date = ? WHERE date IS NULL OR date = ''", (today,))
    cursor.execute(
        """
        UPDATE Records
        SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER)
        WHERE amount_cents IS NULL
        """
    )
    cursor.execute("UPDATE Records SET note = '' WHERE note IS NULL")
    cursor.execute("UPDATE Records SET tags = '' WHERE tags IS NULL")
    cursor.execute("UPDATE Records SET attachment_path = '' WHERE attachment_path IS NULL")
    cursor.execute(
        "UPDATE Records SET account = ? WHERE account IS NULL OR TRIM(account) = ''",
        (DEFAULT_ACCOUNT,),
    )
    cursor.execute(
        "UPDATE Records SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
        (now,),
    )
    cursor.execute(
        "UPDATE Records SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''",
        (now,),
    )


def database_init():
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Records(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                account TEXT NOT NULL,
                amount REAL NOT NULL,
                amount_cents INTEGER NOT NULL,
                note TEXT,
                tags TEXT,
                attachment_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_records_table(cursor)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Budgets(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(month, category)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Categories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL,
                default_budget_cents INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Accounts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL DEFAULT 'asset',
                icon TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_accounts_table(cursor)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Transfers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                from_account TEXT NOT NULL,
                to_account TEXT NOT NULL,
                amount REAL NOT NULL,
                amount_cents INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_transfers_table(cursor)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS RecurringRules(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                account TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                note TEXT,
                day_of_month INTEGER NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'monthly',
                interval_count INTEGER NOT NULL DEFAULT 1,
                start_date TEXT,
                end_date TEXT,
                last_generated_month TEXT,
                last_generated_date TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_recurring_rules_table(cursor)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ClassificationRules(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'expense',
                category TEXT NOT NULL,
                account TEXT NOT NULL DEFAULT 'Cash',
                tags TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(keyword, type)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS AuditLog(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                record_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        _sync_categories(cursor)
        _sync_accounts(cursor)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON Records(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_category ON Records(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_account ON Records(account)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON Records(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_amount ON Records(amount_cents)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_tags ON Records(tags)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transfers_date ON Transfers(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transfers_from_account ON Transfers(from_account)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transfers_to_account ON Transfers(to_account)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_budgets_month ON Budgets(month)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON AuditLog(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_keyword ON ClassificationRules(keyword)")
        db.commit()


def _validate_type(record_type):
    if record_type not in VALID_TYPES:
        raise ValueError(f"Invalid record type: {record_type}")


def insert_record(
    record_type,
    category,
    amount_cents,
    note,
    record_date,
    account=DEFAULT_ACCOUNT,
    tags="",
    attachment_path="",
    record_id=None,
):
    _validate_type(record_type)
    now = _now()

    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        _ensure_account(cursor, account)
        if record_id is None:
            cursor.execute(
                """
                INSERT INTO Records
                    (date, type, category, account, amount, amount_cents, note, tags, attachment_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_date,
                    record_type,
                    category,
                    account,
                    amount_cents / 100,
                    amount_cents,
                    note,
                    tags or "",
                    attachment_path or "",
                    now,
                    now,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO Records
                    (id, date, type, category, account, amount, amount_cents, note, tags, attachment_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    record_date,
                    record_type,
                    category,
                    account,
                    amount_cents / 100,
                    amount_cents,
                    note,
                    tags or "",
                    attachment_path or "",
                    now,
                    now,
                ),
            )
        db.commit()
        return cursor.lastrowid


def update_record(
    record_id,
    record_type,
    category,
    amount_cents,
    note,
    record_date,
    account=DEFAULT_ACCOUNT,
    tags="",
    attachment_path="",
):
    _validate_type(record_type)

    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        _ensure_account(cursor, account)
        cursor.execute(
            """
            UPDATE Records
            SET date = ?,
                type = ?,
                category = ?,
                account = ?,
                amount = ?,
                amount_cents = ?,
                note = ?,
                tags = ?,
                attachment_path = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                record_date,
                record_type,
                category,
                account,
                amount_cents / 100,
                amount_cents,
                note,
                tags or "",
                attachment_path or "",
                _now(),
                record_id,
            ),
        )
        db.commit()
        return cursor.rowcount


def _record_filter_sql(
    month=None,
    category=None,
    account=None,
    tag=None,
    record_type=None,
    search=None,
    date_from=None,
    date_to=None,
    amount_min_cents=None,
    amount_max_cents=None,
):
    clauses = []
    params = []

    if month:
        clauses.append("date LIKE ?")
        params.append(f"{month}-%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if account:
        clauses.append("account = ?")
        params.append(account)
    if tag:
        clauses.append("(',' || tags || ',') LIKE ?")
        params.append(f"%,{tag},%")
    if record_type:
        clauses.append("type = ?")
        params.append(record_type)
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    if amount_min_cents is not None:
        clauses.append("amount_cents >= ?")
        params.append(amount_min_cents)
    if amount_max_cents is not None:
        clauses.append("amount_cents <= ?")
        params.append(amount_max_cents)
    if search:
        clauses.append("(category LIKE ? OR account LIKE ? OR tags LIKE ? OR note LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def load_records(
    month=None,
    category=None,
    account=None,
    tag=None,
    record_type=None,
    search=None,
    date_from=None,
    date_to=None,
    amount_min_cents=None,
    amount_max_cents=None,
    limit=None,
    offset=0,
):
    where, params = _record_filter_sql(
        month=month,
        category=category,
        account=account,
        tag=tag,
        record_type=record_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
        amount_min_cents=amount_min_cents,
        amount_max_cents=amount_max_cents,
    )
    paging = ""
    if limit is not None:
        paging = "LIMIT ? OFFSET ?"
        params = [*params, int(limit), int(offset or 0)]

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, date, type, category, account, amount_cents, note, tags, attachment_path, created_at, updated_at
            FROM Records
            {where}
            ORDER BY date DESC, id DESC
            {paging}
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def count_records(
    month=None,
    category=None,
    account=None,
    tag=None,
    record_type=None,
    search=None,
    date_from=None,
    date_to=None,
    amount_min_cents=None,
    amount_max_cents=None,
):
    where, params = _record_filter_sql(
        month=month,
        category=category,
        account=account,
        tag=tag,
        record_type=record_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
        amount_min_cents=amount_min_cents,
        amount_max_cents=amount_max_cents,
    )

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(f"SELECT COUNT(*) AS total FROM Records {where}", params)
        return int(cursor.fetchone()["total"] or 0)


def get_categories():
    with _connect() as db:
        cursor = db.cursor()
        _sync_categories(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT name
            FROM Categories
            ORDER BY name COLLATE NOCASE
            """
        )
        return [row["name"] for row in cursor.fetchall()]


def get_accounts(include_archived=False):
    with _connect() as db:
        cursor = db.cursor()
        _sync_accounts(cursor)
        db.commit()
        where = "" if include_archived else "WHERE archived = 0"
        cursor.execute(
            f"""
            SELECT name
            FROM Accounts
            {where}
            ORDER BY sort_order, name COLLATE NOCASE
            """
        )
        return [row["name"] for row in cursor.fetchall()]


def save_account(
    name,
    opening_balance_cents=None,
    account_id=None,
    account_type="asset",
    icon="",
    archived=False,
    sort_order=0,
):
    name = (name or DEFAULT_ACCOUNT).strip()
    if not name:
        raise ValueError("Account name must be non-empty.")
    account_type = (account_type or "asset").strip() or "asset"
    if account_type not in {"asset", "liability", "credit"}:
        raise ValueError("Account type must be asset, liability, or credit.")
    now = _now()
    with _connect() as db:
        cursor = db.cursor()
        if account_id is None:
            _ensure_account(cursor, name)
            cursor.execute(
                """
                UPDATE Accounts
                SET opening_balance_cents = COALESCE(?, opening_balance_cents),
                    type = ?,
                    icon = ?,
                    archived = ?,
                    sort_order = ?,
                    updated_at = ?
                WHERE name = ?
                """,
                (
                    opening_balance_cents,
                    account_type,
                    icon or "",
                    1 if archived else 0,
                    int(sort_order or 0),
                    now,
                    name,
                ),
            )
            db.commit()
            cursor.execute("SELECT id FROM Accounts WHERE name = ?", (name,))
            return cursor.fetchone()["id"]

        cursor.execute("SELECT name FROM Accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Account was not found.")

        old_name = row["name"]
        try:
            cursor.execute(
                """
                UPDATE Accounts
                SET name = ?,
                    opening_balance_cents = COALESCE(?, opening_balance_cents),
                    type = ?,
                    icon = ?,
                    archived = ?,
                    sort_order = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    opening_balance_cents,
                    account_type,
                    icon or "",
                    1 if archived else 0,
                    int(sort_order or 0),
                    now,
                    account_id,
                ),
            )
            cursor.execute("UPDATE Records SET account = ? WHERE account = ?", (name, old_name))
            cursor.execute("UPDATE RecurringRules SET account = ? WHERE account = ?", (name, old_name))
            cursor.execute("UPDATE Transfers SET from_account = ? WHERE from_account = ?", (name, old_name))
            cursor.execute("UPDATE Transfers SET to_account = ? WHERE to_account = ?", (name, old_name))
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError("Account name conflicts with existing data.") from exc
        return account_id


def load_accounts_detail(include_archived=True):
    with _connect() as db:
        cursor = db.cursor()
        _sync_accounts(cursor)
        db.commit()
        where = "" if include_archived else "WHERE Accounts.archived = 0"
        cursor.execute(
            f"""
            SELECT
                Accounts.id,
                Accounts.name,
                Accounts.opening_balance_cents,
                Accounts.type,
                Accounts.icon,
                Accounts.archived,
                Accounts.sort_order,
                COALESCE(SUM(CASE WHEN Records.type = 'income' THEN Records.amount_cents ELSE 0 END), 0) AS income_cents,
                COALESCE(SUM(CASE WHEN Records.type = 'expense' THEN Records.amount_cents ELSE 0 END), 0) AS expense_cents,
                COUNT(Records.id) AS record_count
            FROM Accounts
            LEFT JOIN Records ON Records.account = Accounts.name
            {where}
            GROUP BY Accounts.id, Accounts.name, Accounts.opening_balance_cents
            ORDER BY Accounts.archived, Accounts.sort_order, Accounts.name COLLATE NOCASE
            """
        )
        accounts = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT to_account AS account, COALESCE(SUM(amount_cents), 0) AS transfer_in_cents
            FROM Transfers
            GROUP BY to_account
            """
        )
        transfer_in = {row["account"]: int(row["transfer_in_cents"] or 0) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT from_account AS account, COALESCE(SUM(amount_cents), 0) AS transfer_out_cents
            FROM Transfers
            GROUP BY from_account
            """
        )
        transfer_out = {row["account"]: int(row["transfer_out_cents"] or 0) for row in cursor.fetchall()}

    for account in accounts:
        name = account["name"]
        account["transfer_in_cents"] = transfer_in.get(name, 0)
        account["transfer_out_cents"] = transfer_out.get(name, 0)
        account["balance_cents"] = (
            int(account["opening_balance_cents"] or 0)
            + int(account["income_cents"] or 0)
            - int(account["expense_cents"] or 0)
            + account["transfer_in_cents"]
            - account["transfer_out_cents"]
        )
    return accounts


def load_account_balances():
    return load_accounts_detail(include_archived=False)


def archive_account(account_id, archived=True):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE Accounts SET archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, _now(), account_id),
        )
        db.commit()
        return cursor.rowcount


def insert_transfer(transfer_date, from_account, to_account, amount_cents, note=""):
    from_account = (from_account or "").strip()
    to_account = (to_account or "").strip()
    if not from_account or not to_account:
        raise ValueError("Transfer accounts must be non-empty.")
    if from_account == to_account:
        raise ValueError("Transfer accounts must be different.")
    if int(amount_cents) <= 0:
        raise ValueError("Transfer amount must be positive.")

    now = _now()
    with _connect() as db:
        cursor = db.cursor()
        _ensure_account(cursor, from_account)
        _ensure_account(cursor, to_account)
        cursor.execute(
            """
            INSERT INTO Transfers
                (date, from_account, to_account, amount, amount_cents, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer_date,
                from_account,
                to_account,
                amount_cents / 100,
                amount_cents,
                note,
                now,
                now,
            ),
        )
        db.commit()
        return cursor.lastrowid


def load_transfers(limit=None):
    limit_clause = "LIMIT ?" if limit else ""
    params = [limit] if limit else []
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, date, from_account, to_account, amount_cents, note, created_at, updated_at
            FROM Transfers
            ORDER BY date DESC, id DESC
            {limit_clause}
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_transfer(transfer_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM Transfers WHERE id = ?", (transfer_id,))
        db.commit()
        return cursor.rowcount


def restore_transfer(transfer):
    with _connect() as db:
        cursor = db.cursor()
        _ensure_account(cursor, transfer["from_account"])
        _ensure_account(cursor, transfer["to_account"])
        now = _now()
        cursor.execute(
            """
            INSERT INTO Transfers
                (id, date, from_account, to_account, amount, amount_cents, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer.get("id"),
                transfer["date"],
                transfer["from_account"],
                transfer["to_account"],
                int(transfer["amount_cents"]) / 100,
                int(transfer["amount_cents"]),
                transfer.get("note") or "",
                now,
                now,
            ),
        )
        db.commit()
        return cursor.lastrowid


def load_categories():
    with _connect() as db:
        cursor = db.cursor()
        _sync_categories(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT
                Categories.id,
                Categories.name,
                Categories.color,
                Categories.default_budget_cents,
                (
                    SELECT COUNT(*)
                    FROM Records
                    WHERE Records.category = Categories.name
                ) AS record_count,
                (
                    SELECT COUNT(*)
                    FROM Budgets
                    WHERE Budgets.category = Categories.name
                ) AS budget_count
            FROM Categories
            ORDER BY Categories.name COLLATE NOCASE
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def save_category(name, color=None, default_budget_cents=0, category_id=None):
    name = name.strip()
    if not name:
        raise ValueError("Category name must be non-empty.")

    color = (color or _category_color(name)).strip()
    now = _now()

    with _connect() as db:
        cursor = db.cursor()
        if category_id is None:
            cursor.execute(
                """
                INSERT INTO Categories (name, color, default_budget_cents, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name)
                DO UPDATE SET
                    color = excluded.color,
                    default_budget_cents = excluded.default_budget_cents,
                    updated_at = excluded.updated_at
                """,
                (name, color, default_budget_cents, now, now),
            )
            db.commit()
            cursor.execute("SELECT id FROM Categories WHERE name = ?", (name,))
            return cursor.fetchone()["id"]

        cursor.execute("SELECT name FROM Categories WHERE id = ?", (category_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Category was not found.")

        old_name = row["name"]
        try:
            cursor.execute(
                """
                UPDATE Categories
                SET name = ?, color = ?, default_budget_cents = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, color, default_budget_cents, now, category_id),
            )
            cursor.execute("UPDATE Records SET category = ? WHERE category = ?", (name, old_name))
            cursor.execute("UPDATE Budgets SET category = ? WHERE category = ?", (name, old_name))
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError("Category name conflicts with existing data.") from exc
        return category_id


def delete_category(category_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("SELECT name FROM Categories WHERE id = ?", (category_id,))
        row = cursor.fetchone()
        if row is None:
            return 0

        name = row["name"]
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM Records WHERE category = ?) AS record_count,
                (SELECT COUNT(*) FROM Budgets WHERE category = ?) AS budget_count
            """,
            (name, name),
        )
        usage = cursor.fetchone()
        if usage["record_count"] or usage["budget_count"]:
            raise ValueError("Only unused categories can be deleted.")

        cursor.execute("DELETE FROM Categories WHERE id = ?", (category_id,))
        db.commit()
        return cursor.rowcount


def get_months():
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT month
            FROM (
                SELECT DISTINCT SUBSTR(date, 1, 7) AS month
                FROM Records
                WHERE date IS NOT NULL AND date != ''

                UNION

                SELECT DISTINCT month
                FROM Budgets
                WHERE month IS NOT NULL AND month != ''
            )
            ORDER BY month DESC
            """
        )
        return [row["month"] for row in cursor.fetchall()]


def load_monthly_summary(limit=12):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT
                SUBSTR(date, 1, 7) AS month,
                SUM(CASE WHEN type = 'income' THEN amount_cents ELSE 0 END) AS income_cents,
                SUM(CASE WHEN type = 'expense' THEN amount_cents ELSE 0 END) AS expense_cents
            FROM Records
            GROUP BY SUBSTR(date, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        rows.reverse()
        return rows


def load_category_spending(month=None):
    clauses = ["type = 'expense'"]
    params = []

    if month:
        clauses.append("date LIKE ?")
        params.append(f"{month}-%")

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT
                Records.category,
                SUM(Records.amount_cents) AS spent_cents,
                Categories.color AS color
            FROM Records
            LEFT JOIN Categories ON Categories.name = Records.category
            WHERE {' AND '.join(clauses)}
            GROUP BY Records.category
            ORDER BY spent_cents DESC, category COLLATE NOCASE
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def load_account_spending(month=None):
    clauses = ["type = 'expense'"]
    params = []
    if month:
        clauses.append("date LIKE ?")
        params.append(f"{month}-%")

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT account, SUM(amount_cents) AS spent_cents
            FROM Records
            WHERE {' AND '.join(clauses)}
            GROUP BY account
            ORDER BY spent_cents DESC, account COLLATE NOCASE
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def load_budget_progress(month):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT
                Budgets.category,
                Budgets.amount_cents AS budget_cents,
                COALESCE((
                    SELECT SUM(Records.amount_cents)
                    FROM Records
                    WHERE Records.type = 'expense'
                      AND Records.category = Budgets.category
                      AND Records.date LIKE ?
                ), 0) AS spent_cents
            FROM Budgets
            WHERE Budgets.month = ?
            ORDER BY Budgets.category COLLATE NOCASE
            """,
            (f"{month}-%", month),
        )
        return [dict(row) for row in cursor.fetchall()]


def load_budget_alerts(month, threshold=0.8):
    alerts = []
    for row in load_budget_progress(month):
        budget = int(row["budget_cents"] or 0)
        spent = int(row["spent_cents"] or 0)
        if not budget:
            continue
        usage = spent / budget
        if usage >= threshold:
            item = dict(row)
            item["usage"] = usage
            item["status"] = "over" if usage >= 1 else "near"
            alerts.append(item)
    alerts.sort(key=lambda item: item["usage"], reverse=True)
    return alerts


def load_budgets(month=None):
    clauses = []
    params = []

    if month:
        clauses.append("month = ?")
        params.append(month)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, month, category, amount_cents, created_at, updated_at
            FROM Budgets
            {where}
            ORDER BY month DESC, category COLLATE NOCASE
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def upsert_budget(month, category, amount_cents):
    now = _now()

    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        cursor.execute(
            """
            INSERT INTO Budgets (month, category, amount_cents, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(month, category)
            DO UPDATE SET
                amount_cents = excluded.amount_cents,
                updated_at = excluded.updated_at
            """,
            (month, category, amount_cents, now, now),
        )
        db.commit()
        cursor.execute(
            "SELECT id FROM Budgets WHERE month = ? AND category = ?",
            (month, category),
        )
        return cursor.fetchone()["id"]


def delete_budget(budget_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM Budgets WHERE id = ?", (budget_id,))
        db.commit()
        return cursor.rowcount


def delete_record(record_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM Records WHERE id = ?", (record_id,))
        db.commit()
        return cursor.rowcount


def restore_record(record):
    return insert_record(
        record["type"],
        record["category"],
        int(record["amount_cents"]),
        record.get("note") or "",
        record["date"],
        account=record.get("account") or DEFAULT_ACCOUNT,
        tags=record.get("tags") or "",
        attachment_path=record.get("attachment_path") or "",
        record_id=record.get("id"),
    )


def log_activity(action, detail="", record_id=None):
    action = (action or "").strip()
    if not action:
        return None
    database_init()
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO AuditLog (action, detail, record_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (action, detail or "", record_id, _now()),
        )
        db.commit()
        return cursor.lastrowid


def load_activity_logs(limit=100):
    database_init()
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, action, detail, record_id, created_at
            FROM AuditLog
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit or 100),),
        )
        return [dict(row) for row in cursor.fetchall()]


def save_classification_rule(
    keyword,
    record_type,
    category,
    account=DEFAULT_ACCOUNT,
    tags="",
    active=True,
    rule_id=None,
):
    keyword = (keyword or "").strip().lower()
    category = (category or "").strip()
    account = (account or DEFAULT_ACCOUNT).strip() or DEFAULT_ACCOUNT
    tags = ",".join(tag.strip().lower() for tag in (tags or "").split(",") if tag.strip())
    _validate_type(record_type)
    if not keyword:
        raise ValueError("Keyword must be non-empty.")
    if not category:
        raise ValueError("Category must be non-empty.")

    now = _now()
    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        _ensure_account(cursor, account)
        if rule_id is None:
            cursor.execute(
                """
                INSERT INTO ClassificationRules
                    (keyword, type, category, account, tags, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(keyword, type)
                DO UPDATE SET
                    category = excluded.category,
                    account = excluded.account,
                    tags = excluded.tags,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (keyword, record_type, category, account, tags, 1 if active else 0, now, now),
            )
            cursor.execute(
                "SELECT id FROM ClassificationRules WHERE keyword = ? AND type = ?",
                (keyword, record_type),
            )
            saved_id = cursor.fetchone()["id"]
        else:
            cursor.execute(
                """
                UPDATE ClassificationRules
                SET keyword = ?, type = ?, category = ?, account = ?, tags = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (keyword, record_type, category, account, tags, 1 if active else 0, now, rule_id),
            )
            saved_id = rule_id
        db.commit()
        return saved_id


def load_classification_rules(active_only=False):
    database_init()
    where = "WHERE active = 1" if active_only else ""
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, keyword, type, category, account, tags, active, created_at, updated_at
            FROM ClassificationRules
            {where}
            ORDER BY active DESC, keyword COLLATE NOCASE
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_classification_rule(rule_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM ClassificationRules WHERE id = ?", (rule_id,))
        db.commit()
        return cursor.rowcount


def match_classification_rule(text, record_type="expense"):
    haystack = (text or "").lower()
    if not haystack:
        return None
    rules = load_classification_rules(active_only=True)
    matching = [
        rule
        for rule in rules
        if (not record_type or rule["type"] == record_type) and rule["keyword"].lower() in haystack
    ]
    if not matching:
        return None
    matching.sort(key=lambda rule: len(rule["keyword"]), reverse=True)
    return matching[0]


def split_record(record_id, splits):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, date, type, category, account, amount_cents, note, tags, attachment_path
            FROM Records
            WHERE id = ?
            """,
            (record_id,),
        )
        original = cursor.fetchone()
        if original is None:
            raise ValueError("Record was not found.")

        cleaned = []
        for item in splits:
            category = (item.get("category") or "").strip()
            amount_cents = int(item.get("amount_cents") or 0)
            if not category or amount_cents <= 0:
                raise ValueError("Each split needs a category and positive amount.")
            cleaned.append(
                {
                    "category": category,
                    "amount_cents": amount_cents,
                    "note": (item.get("note") or original["note"] or "").strip(),
                    "tags": (item.get("tags") or original["tags"] or "").strip(),
                }
            )
        if not cleaned:
            raise ValueError("At least one split line is required.")
        if sum(item["amount_cents"] for item in cleaned) != int(original["amount_cents"]):
            raise ValueError("Split amounts must equal the original amount.")

        now = _now()
        new_ids = []
        for item in cleaned:
            _ensure_category(cursor, item["category"])
            cursor.execute(
                """
                INSERT INTO Records
                    (date, type, category, account, amount, amount_cents, note, tags, attachment_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    original["date"],
                    original["type"],
                    item["category"],
                    original["account"],
                    item["amount_cents"] / 100,
                    item["amount_cents"],
                    item["note"],
                    item["tags"],
                    original["attachment_path"] or "",
                    now,
                    now,
                ),
            )
            new_ids.append(cursor.lastrowid)
        cursor.execute("DELETE FROM Records WHERE id = ?", (record_id,))
        cursor.execute(
            """
            INSERT INTO AuditLog (action, detail, record_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("split_record", f"Split record #{record_id} into {len(new_ids)} records.", record_id, now),
        )
        db.commit()
        return {"original": dict(original), "new_ids": new_ids}


def find_duplicate_records():
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT date, type, category, account, amount_cents, COUNT(*) AS duplicate_count
            FROM Records
            GROUP BY date, type, category, account, amount_cents
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, date DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def merge_category_records(source_category, target_category):
    source_category = source_category.strip()
    target_category = target_category.strip()
    if not source_category or not target_category:
        raise ValueError("Category names must be non-empty.")
    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, target_category)
        cursor.execute("UPDATE Records SET category = ?, updated_at = ? WHERE category = ?", (target_category, _now(), source_category))
        record_count = cursor.rowcount
        cursor.execute("UPDATE Budgets SET category = ?, updated_at = ? WHERE category = ?", (target_category, _now(), source_category))
        budget_count = cursor.rowcount
        cursor.execute("UPDATE RecurringRules SET category = ?, updated_at = ? WHERE category = ?", (target_category, _now(), source_category))
        rule_count = cursor.rowcount
        db.commit()
        return {"records": record_count, "budgets": budget_count, "rules": rule_count}


def merge_account_records(source_account, target_account):
    source_account = source_account.strip()
    target_account = target_account.strip()
    if not source_account or not target_account:
        raise ValueError("Account names must be non-empty.")
    with _connect() as db:
        cursor = db.cursor()
        _ensure_account(cursor, target_account)
        cursor.execute("UPDATE Records SET account = ?, updated_at = ? WHERE account = ?", (target_account, _now(), source_account))
        record_count = cursor.rowcount
        cursor.execute("UPDATE RecurringRules SET account = ?, updated_at = ? WHERE account = ?", (target_account, _now(), source_account))
        rule_count = cursor.rowcount
        cursor.execute("UPDATE Transfers SET from_account = ?, updated_at = ? WHERE from_account = ?", (target_account, _now(), source_account))
        transfer_from_count = cursor.rowcount
        cursor.execute("UPDATE Transfers SET to_account = ?, updated_at = ? WHERE to_account = ?", (target_account, _now(), source_account))
        transfer_to_count = cursor.rowcount
        db.commit()
        return {
            "records": record_count,
            "rules": rule_count,
            "transfers": transfer_from_count + transfer_to_count,
        }


def cleanup_tags():
    updated = 0
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("SELECT id, tags FROM Records WHERE tags IS NOT NULL AND TRIM(tags) != ''")
        rows = cursor.fetchall()
        for row in rows:
            tags = sorted({tag.strip().lower() for tag in row["tags"].split(",") if tag.strip()})
            cleaned = ",".join(tags)
            if cleaned != row["tags"]:
                cursor.execute("UPDATE Records SET tags = ?, updated_at = ? WHERE id = ?", (cleaned, _now(), row["id"]))
                updated += 1
        db.commit()
    return updated


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_with_day(year, month, day):
    return date(year, month, min(int(day), monthrange(year, month)[1]))


def _add_months(value, months, day=None):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return _date_with_day(year, month, day or value.day)


def _add_period(value, frequency, interval_count, day_of_month):
    interval_count = max(int(interval_count or 1), 1)
    if frequency == "daily":
        return value + timedelta(days=interval_count)
    if frequency == "weekly":
        return value + timedelta(weeks=interval_count)
    if frequency == "yearly":
        return _add_months(value, interval_count * 12, day_of_month)
    return _add_months(value, interval_count, day_of_month)


def next_recurring_due_date(rule, today=None):
    if not int(rule.get("active", 1)):
        return None

    today = today or date.today()
    frequency = (rule.get("frequency") or "monthly").lower()
    if frequency not in RECURRING_FREQUENCIES:
        frequency = "monthly"
    interval_count = max(int(rule.get("interval_count") or 1), 1)
    day_of_month = int(rule.get("day_of_month") or today.day)
    end_date = _parse_date(rule.get("end_date"))

    last_generated = _parse_date(rule.get("last_generated_date"))
    if last_generated is None and rule.get("last_generated_month"):
        year, month = (int(part) for part in rule["last_generated_month"].split("-", 1))
        last_generated = _date_with_day(year, month, day_of_month)

    if last_generated is not None:
        candidate = _add_period(last_generated, frequency, interval_count, day_of_month)
    else:
        start_date = _parse_date(rule.get("start_date"))
        if start_date is not None:
            candidate = start_date
        elif frequency in {"monthly", "yearly"}:
            candidate = _date_with_day(today.year, today.month, day_of_month)
        else:
            candidate = today

    if end_date and candidate > end_date:
        return None
    return candidate.isoformat()


def load_recurring_rules():
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, name, type, category, account, amount_cents, note,
                   day_of_month, frequency, interval_count, start_date, end_date,
                   last_generated_month, last_generated_date, active, created_at, updated_at
            FROM RecurringRules
            ORDER BY active DESC, name COLLATE NOCASE
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]
    for row in rows:
        row["next_due_date"] = next_recurring_due_date(row)
    return rows


def upsert_recurring_rule(
    name,
    record_type,
    category,
    account,
    amount_cents,
    note,
    day_of_month,
    frequency="monthly",
    interval_count=1,
    start_date=None,
    end_date=None,
    active=True,
    rule_id=None,
):
    _validate_type(record_type)
    if not 1 <= int(day_of_month) <= 31:
        raise ValueError("Day of month must be between 1 and 31.")
    frequency = (frequency or "monthly").lower()
    if frequency not in RECURRING_FREQUENCIES:
        raise ValueError("Invalid recurring frequency.")
    interval_count = max(int(interval_count or 1), 1)

    now = _now()
    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        _ensure_account(cursor, account)
        if rule_id is None:
            cursor.execute(
                """
                INSERT INTO RecurringRules
                    (name, type, category, account, amount_cents, note, day_of_month,
                     frequency, interval_count, start_date, end_date, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    record_type,
                    category,
                    account,
                    amount_cents,
                    note,
                    int(day_of_month),
                    frequency,
                    interval_count,
                    start_date or None,
                    end_date or None,
                    1 if active else 0,
                    now,
                    now,
                ),
            )
            db.commit()
            return cursor.lastrowid

        cursor.execute(
            """
            UPDATE RecurringRules
            SET name = ?, type = ?, category = ?, account = ?, amount_cents = ?,
                note = ?, day_of_month = ?, frequency = ?, interval_count = ?,
                start_date = ?, end_date = ?, active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                record_type,
                category,
                account,
                amount_cents,
                note,
                int(day_of_month),
                frequency,
                interval_count,
                start_date or None,
                end_date or None,
                1 if active else 0,
                now,
                rule_id,
            ),
        )
        db.commit()
        return rule_id


def delete_recurring_rule(rule_id):
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM RecurringRules WHERE id = ?", (rule_id,))
        db.commit()
        return cursor.rowcount


def generate_due_recurring_records(today=None):
    today = today or date.today()
    generated = 0

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT *
            FROM RecurringRules
            WHERE active = 1
            """
        )
        rules = cursor.fetchall()

        for rule in rules:
            rule_dict = dict(rule)
            while True:
                due_date_text = next_recurring_due_date(rule_dict, today=today)
                if due_date_text is None:
                    break
                due_date = _parse_date(due_date_text)
                if due_date > today:
                    break

                _ensure_category(cursor, rule["category"])
                _ensure_account(cursor, rule["account"])
                cursor.execute(
                    """
                    INSERT INTO Records
                        (date, type, category, account, amount, amount_cents, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        due_date_text,
                        rule["type"],
                        rule["category"],
                        rule["account"],
                        rule["amount_cents"] / 100,
                        rule["amount_cents"],
                        rule["note"] or rule["name"],
                        _now(),
                        _now(),
                    ),
                )
                cursor.execute(
                    """
                    UPDATE RecurringRules
                    SET last_generated_month = ?, last_generated_date = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (due_date.strftime("%Y-%m"), due_date_text, _now(), rule["id"]),
                )
                rule_dict["last_generated_month"] = due_date.strftime("%Y-%m")
                rule_dict["last_generated_date"] = due_date_text
                generated += 1

                if generated > 250:
                    break

        db.commit()
    return generated


def backup_database(destination_path):
    database_init()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_database_file(get_db_path())
    shutil.copy2(get_db_path(), destination)
    return destination


def create_backup_archive(destination_path):
    database_init()
    source = validate_database_file(get_db_path())
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "app": APP_NAME,
        "created_at": _now(),
        "database": source.name,
        "integrity": "ok",
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, arcname=source.name)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return destination


def restore_backup_archive(source_path):
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    with zipfile.ZipFile(source, "r") as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".db")]
        if not candidates:
            raise ValueError("Backup archive does not contain a database file.")
        extracted = get_db_path().parent / "_restore_candidate.db"
        with archive.open(candidates[0]) as src, open(extracted, "wb") as dst:
            shutil.copyfileobj(src, dst)
    try:
        return restore_database(extracted)
    finally:
        extracted.unlink(missing_ok=True)


def encrypt_database(password, remove_plaintext=False):
    database_init()
    source = get_db_path()
    destination = get_encrypted_db_path()
    encrypt_file(source, destination, password)
    if remove_plaintext:
        source.unlink(missing_ok=True)
    return destination


def decrypt_database(password):
    source = get_encrypted_db_path()
    if not source.exists():
        return None

    destination = get_db_path()
    decrypt_file(source, destination, password)
    validate_database_file(destination)
    database_init()
    return destination


def run_auto_backup(keep=7, today=None):
    database_init()
    today = today or date.today()
    today_text = today.isoformat()
    if get_setting("last_auto_backup_date") == today_text:
        return None

    backup_dir = get_db_path().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"expense-tracker-auto-{today_text}.db"
    validate_database_file(get_db_path())
    shutil.copy2(get_db_path(), destination)

    custom_backup_folder = get_setting("auto_backup_folder")
    if custom_backup_folder:
        custom_dir = Path(custom_backup_folder).expanduser().resolve()
        custom_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(get_db_path(), custom_dir / destination.name)

    backups = sorted(backup_dir.glob("expense-tracker-auto-*.db"), key=lambda path: path.stat().st_mtime)
    for old_backup in backups[:-keep]:
        old_backup.unlink(missing_ok=True)

    set_setting("last_auto_backup_date", today_text)
    return destination


def validate_database_file(source_path):
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    try:
        db = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            cursor = db.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            if result != "ok":
                raise ValueError(f"Database integrity check failed: {result}")
            cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'Records'")
            if cursor.fetchone() is None:
                raise ValueError("Backup does not contain a Records table.")
        finally:
            db.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("Selected file is not a valid SQLite database.") from exc

    return source


def restore_database(source_path):
    source = validate_database_file(source_path)
    destination = get_db_path()
    shutil.copy2(source, destination)
    database_init()
    return destination


def get_setting(key, default=None):
    database_init()
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute("SELECT value FROM Settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    database_init()
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO Settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        db.commit()
