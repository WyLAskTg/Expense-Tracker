import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path


APP_NAME = "PersonalExpenseTracker"
DB_NAME = "expense_tracker.db"
VALID_TYPES = {"income", "expense"}


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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON Records(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_category ON Records(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_budgets_month ON Budgets(month)")
        db.commit()


def _validate_type(record_type):
    if record_type not in VALID_TYPES:
        raise ValueError(f"Invalid record type: {record_type}")


def insert_record(record_type, category, amount_cents, note, record_date):
    _validate_type(record_type)
    now = _now()

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO Records
                (date, type, category, amount, amount_cents, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_date,
                record_type,
                category,
                amount_cents / 100,
                amount_cents,
                note,
                now,
                now,
            ),
        )
        db.commit()
        return cursor.lastrowid


def update_record(record_id, record_type, category, amount_cents, note, record_date):
    _validate_type(record_type)

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE Records
            SET date = ?,
                type = ?,
                category = ?,
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
                amount_cents / 100,
                amount_cents,
                note,
                _now(),
                record_id,
            ),
        )
        db.commit()
        return cursor.rowcount


def load_records(month=None, category=None, search=None):
    clauses = []
    params = []

    if month:
        clauses.append("date LIKE ?")
        params.append(f"{month}-%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if search:
        clauses.append("(category LIKE ? OR note LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as db:
        cursor = db.cursor()
        cursor.execute(
            f"""
            SELECT id, date, type, category, amount_cents, note, created_at, updated_at
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
        cursor.execute(
            """
            SELECT DISTINCT category
            FROM Records
            WHERE category IS NOT NULL AND TRIM(category) != ''
            ORDER BY category COLLATE NOCASE
            """
        )
        return [row["category"] for row in cursor.fetchall()]


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
            SELECT category, SUM(amount_cents) AS spent_cents
            FROM Records
            WHERE {' AND '.join(clauses)}
            GROUP BY category
            ORDER BY spent_cents DESC, category COLLATE NOCASE
            """,
            params,
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


def backup_database(destination_path):
    database_init()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_db_path(), destination)
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
