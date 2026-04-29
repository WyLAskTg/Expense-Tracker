import tkinter as tk
import sqlite3

root = tk.Tk()

root.title("Expense Tracker")
root.geometry("900x650")
root.resizable(False, False)

records = []

# =============================TOP SECTION============================
top_frame = tk.Frame(root, padx=15, pady=10)
top_frame.pack(fill="x")

version = tk.Label(top_frame, text="Expense Tracker 0.9")
version.pack(anchor="w")

status = tk.Label(top_frame, text="Add your first record")
status.pack(anchor="w", pady=(5, 0))

# =============================FORM SECTION============================
form_frame = tk.Frame(root, padx=15, pady=10)
form_frame.pack(fill="x")

type_label = tk.Label(form_frame, text="Type", width=12, anchor="w")
type_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

type_choose = tk.StringVar()
type_choose.set("expense")
type_menu = tk.OptionMenu(form_frame, type_choose, "income", "expense")
type_menu.config(width=18)
type_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

cat_label = tk.Label(form_frame, text="Category", width=12, anchor="w")
cat_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")

cat_entry = tk.Entry(form_frame)
cat_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

amt_label = tk.Label(form_frame, text="Amount")
amt_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")

amt_entry = tk.Entry(form_frame)
amt_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

note_label = tk.Label(form_frame, text="Note")
note_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")

note_entry = tk.Entry(form_frame)
note_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")

# =============================BUTTON SECTION============================
button_frame = tk.Frame(root, padx=15, pady=5)
button_frame.pack(fill="x")

# =============================SUMMARY SECTION============================
summary_frame = tk.Frame(root, padx=15, pady=10)
summary_frame.pack(fill="x")

total_expense = tk.Label(summary_frame, text="Total expense: $0.0", anchor="w", width=25)
total_expense.grid(row=0, column=0, padx=5, pady=3, sticky="w")

total_income = tk.Label(summary_frame, text="Total income: $0.0", anchor="w", width=25)
total_income.grid(row=1, column=0, padx=5, pady=3, sticky="w")

balance = tk.Label(summary_frame, text="Balance: $0.0", anchor="w", width=25)
balance.grid(row=2, column=0, padx=5, pady=3, sticky="w")

# =============================LIST SECTION============================
list_frame = tk.Frame(root, padx=15, pady=10)
list_frame.pack(fill="both", expand=True)

data = tk.Listbox(list_frame, width=90, height=18)
data.grid(row=0, column=0, sticky="nsew")

scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=data.yview)
scrollbar.grid(row=0, column=1, sticky="ns")

data.config(yscrollcommand=scrollbar.set)

list_frame.grid_rowconfigure(0, weight=1)
list_frame.grid_columnconfigure(0, weight=1)

# =============================DATABASE / LOGIC============================
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

def calculate(records):
    expense = 0
    income = 0

    for record in records:
        if record["type"] == "income":
            income += record["amount"]
        else:
            expense += record["amount"]

    bal = income - expense

    total_expense.config(text=f"Total expense: ${expense}")
    total_income.config(text=f"Total income: ${income}")
    balance.config(text=f"Total balance: ${bal}")

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

    calculate(records)

def read_record():
    tp = type_choose.get()
    cat = cat_entry.get().strip()
    amt = amt_entry.get().strip()
    note = note_entry.get().strip()

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
    calculate(records)

    type_choose.set("expense")
    cat_entry.delete(0, tk.END)
    amt_entry.delete(0, tk.END)
    note_entry.delete(0, tk.END)

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
        calculate(records)
        status.config(text="Record deleted.")

# =============================BUTTONS============================

delete = tk.Button(button_frame, text="Delete", width=12, command=record_delete)
delete.pack(side="left", padx=5)

submit = tk.Button(button_frame, text="Submit", width=12, command=read_record)
submit.pack(side="left", padx=5)

# =============================STARTUP============================
database_init()
record_load()

root.mainloop()