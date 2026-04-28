import tkinter as tk

root = tk.Tk()

root.title("Expense Tracker")
root.geometry("800x600")

version = tk.Label(root, text="This is Version 0.1")
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

    rc = {
        "type": tp,
        "category": cat,
        "amount": x,
        "note": note
    }

    print(rc)
    records.append(rc)
    status.config(text="Added successfully!")
    data.insert(tk.END, f"{tp} | {cat} | {x} | {note}")

    type_entry.delete(0, tk.END)
    cat_entry.delete(0, tk.END)
    amt_entry.delete(0, tk.END)
    note_entry.delete(0, tk.END)

def record_delete():
    selected = data.curselection()
    if not selected:
        status.config(text="Please select a record to delete")
        return
    else:
        del records[selected[0]]
        data.delete(selected[0])
        status.config(text="Record deleted.")

delete = tk.Button(root, text="Delete", command=record_delete)
delete.pack()

submit = tk.Button(root, text="Submit", command=read_record)
submit.pack()

root.mainloop()