import sqlite3

conn = sqlite3.connect("expense_tracker.db")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS Records(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               type TEXT NOT NULL,
               category TEXT NOT NULL,
               amount REAL NOT NULL,
               note TEXT
               )
""")

cursor.execute("""INSERT INTO Records (type, category, amount, note)
               VALUES (?, ?, ?, ?)
               """, ("expense", "food", 12.5, "lunch"))

cursor.execute("SELECT * FROM Records")

rows = cursor.fetchall()

print(rows)

for row in rows:
    print(row)

conn.commit()

conn.close()