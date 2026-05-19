import os
import shutil
import sqlite3
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path


APP_NAME = "PersonalExpenseTracker"
DB_NAME = "expense_tracker.db"
VALID_TYPES = {"income", "expense"}
DEFAULT_ACCOUNT = "Cash"
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
    if not db_path.exists() and legacy_path.exists():
        shutil.copy2(legacy_path, db_path)

    return db_path


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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
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
                last_generated_month TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        _sync_categories(cursor)
        _sync_accounts(cursor)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON Records(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_category ON Records(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_account ON Records(account)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_budgets_month ON Budgets(month)")
        db.commit()


def _validate_type(record_type):
    if record_type not in VALID_TYPES:
        raise ValueError(f"Invalid record type: {record_type}")


def insert_record(record_type, category, amount_cents, note, record_date, account=DEFAULT_ACCOUNT):
    _validate_type(record_type)
    now = _now()

    with _connect() as db:
        cursor = db.cursor()
        _ensure_category(cursor, category)
        _ensure_account(cursor, account)
        cursor.execute(
            """
            INSERT INTO Records
                (date, type, category, account, amount, amount_cents, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_date,
                record_type,
                category,
                account,
                amount_cents / 100,
                amount_cents,
                note,
                now,
                now,
            ),
        )
        db.commit()
        return cursor.lastrowid


def update_record(record_id, record_type, category, amount_cents, note, record_date, account=DEFAULT_ACCOUNT):
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
                _now(),
                record_id,
            ),
        )
        db.commit()
        return cursor.rowcount


def load_records(month=None, category=None, account=None, search=None):
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
    if search:
        clauses.append("(category LIKE ? OR account LIKE ? OR note LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, date, type, category, account, amount_cents, note, created_at, updated_at
            FROM Records
            {where}
            ORDER BY date DESC, id DESC
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


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


def get_accounts():
    with _connect() as db:
        cursor = db.cursor()
        _sync_accounts(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT name
            FROM Accounts
            ORDER BY name COLLATE NOCASE
            """
        )
        return [row["name"] for row in cursor.fetchall()]


def save_account(name):
    name = (name or DEFAULT_ACCOUNT).strip()
    if not name:
        raise ValueError("Account name must be non-empty.")
    with _connect() as db:
        cursor = db.cursor()
        _ensure_account(cursor, name)
        db.commit()
        cursor.execute("SELECT id FROM Accounts WHERE name = ?", (name,))
        return cursor.fetchone()["id"]


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


def load_recurring_rules():
    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, name, type, category, account, amount_cents, note,
                   day_of_month, last_generated_month, active, created_at, updated_at
            FROM RecurringRules
            ORDER BY active DESC, name COLLATE NOCASE
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def upsert_recurring_rule(
    name,
    record_type,
    category,
    account,
    amount_cents,
    note,
    day_of_month,
    active=True,
    rule_id=None,
):
    _validate_type(record_type)
    if not 1 <= int(day_of_month) <= 31:
        raise ValueError("Day of month must be between 1 and 31.")

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
                     active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    record_type,
                    category,
                    account,
                    amount_cents,
                    note,
                    int(day_of_month),
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
                note = ?, day_of_month = ?, active = ?, updated_at = ?
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
    month = today.strftime("%Y-%m")
    generated = 0

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT *
            FROM RecurringRules
            WHERE active = 1
              AND (last_generated_month IS NULL OR last_generated_month < ?)
            """,
            (month,),
        )
        rules = cursor.fetchall()

        for rule in rules:
            due_day = min(int(rule["day_of_month"]), monthrange(today.year, today.month)[1])
            if today.day < due_day:
                continue

            due_date = date(today.year, today.month, due_day).isoformat()
            _ensure_category(cursor, rule["category"])
            _ensure_account(cursor, rule["account"])
            cursor.execute(
                """
                INSERT INTO Records
                    (date, type, category, account, amount, amount_cents, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    due_date,
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
                "UPDATE RecurringRules SET last_generated_month = ?, updated_at = ? WHERE id = ?",
                (month, _now(), rule["id"]),
            )
            generated += 1

        db.commit()
    return generated


def backup_database(destination_path):
    database_init()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_db_path(), destination)
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
    shutil.copy2(get_db_path(), destination)

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
