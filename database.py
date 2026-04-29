import sqlite3

DB_NAME = "expense_tracker.db"

def database_init():
    db = sqlite3.connect(DB_NAME)
    cursor = db.cursor()
    cursor.execute("""
                CREATE TABLE IF NOT EXISTS Records(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT
                )
    """)
    db.commit()
    db.close()

def insert_record(tp, cat, amt, note):
    db = sqlite3.connect(DB_NAME)
    cursor = db.cursor()
    cursor.execute("""INSERT INTO Records (type, category, amount, note)
               VALUES (?, ?, ?, ?)
               """, (tp, cat, amt, note))
    new_id = cursor.lastrowid
    
    db.commit()
    db.close()

    return new_id

def load_records():
    db = sqlite3.connect("expense_tracker.db")
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Records")
    rows = cursor.fetchall()
    db.close()

    return rows

def delete_record(record_id):
    db = sqlite3.connect(DB_NAME)
    cursor = db.cursor()
    cursor.execute("DELETE FROM Records WHERE id = ?", (record_id, ))
    db.commit()
    db.close()