import tkinter as tk
import sqlite3

root = tk.Tk()

root.title("Expense Tracker")
root.geometry("800x600")

version = tk.Label(root, text="This is Version 0.9")
version.pack()

status = tk.Label(root, text="Add your first record")
status.pack()

type_label = tk.Label(root, text="Type")
type_label.pack()

type_entry = tk.Entry(root)
type_entry.pack()

cat_label = tk.Label(root, text="Category")
cat_label.pack()

cat_entry = tk.Entry(root)
cat_entry.pack()

amt_label = tk.Label(root, text="Amount")
amt_label.pack()

amt_entry = tk.Entry(root)
amt_entry.pack()

note_label = tk.Label(root, text="Note")
note_label.pack()

note_entry = tk.Entry(root)
note_entry.pack()

data = tk.Listbox(root)
data.pack()

records = []

def database_init():
    db = sqlite3.connect("expense_tracker.db")
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

def read_record():

    tp = type_entry.get().strip()
    cat = cat_entry.get().strip()
    amt = amt_entry.get().strip()
    note = note_entry.get().strip()

    if not tp:
        status.config(text="Type must be non-empty")
        return
    if not cat:
        status.config(text="Category must be non-empty")
        return
    try:
        x = float(amt)
        if x <= 0:
            status.config(text="Invalid! Amount must be positive.")
            return
    except ValueError:
        status.config(text="Invalid! Amount must be a number.")
        return
    
    record_insert(tp, cat, x, note)

    type_entry.delete(0, tk.END)
    cat_entry.delete(0, tk.END)
    amt_entry.delete(0, tk.END)
    note_entry.delete(0, tk.END)

def record_insert(tp, cat, amt, note):
    db = sqlite3.connect("expense_tracker.db")
    cursor = db.cursor()
    cursor.execute("""INSERT INTO Records (type, category, amount, note)
               VALUES (?, ?, ?, ?)
               """, (tp, cat, amt, note))
    new_id = cursor.lastrowid
    new = {
        "id": new_id,
        "type": tp,
        "category": cat,
        "amount": amt,
        "note": note
    }
    
    db.commit()
    db.close()

    records.append(new)
    data.insert(tk.END, f"{tp} | {cat} | {amt} | {note}")
    status.config(text="Added successfully!")

def record_load():
    records.clear()
    data.delete(0, tk.END)

    db = sqlite3.connect("expense_tracker.db")
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Records")
    rows = cursor.fetchall()
    db.close()

    for row in rows:
        data.insert(tk.END, f"{row[1]} | {row[2]} | {row[3]} | {row[4]}")
        new = {
            "id": row[0],
            "type": row[1],
            "category": row[2],
            "amount": row[3],
            "note": row[4]
        }
        records.append(new)

def record_delete():
    selected = data.curselection()
    if not selected:
        status.config(text="Please select a record to delete.")
        return
    else:
        idx = selected[0]
        db = sqlite3.connect("expense_tracker.db")
        db.execute("DELETE FROM Records WHERE id = ?", (records[idx]["id"], ))
        db.commit()
        db.close()

        del records[idx]
        data.delete(idx)

        status.config(text="Record deleted.")

delete = tk.Button(root, text="Delete", command=record_delete)
delete.pack()

submit = tk.Button(root, text="Submit", command=read_record)
submit.pack()


database_init()
record_load()

root.mainloop()