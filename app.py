import csv
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from tkinter import filedialog, messagebox, ttk

from database import (
    database_init,
    delete_record,
    get_categories,
    insert_record,
    load_records,
    update_record,
)


MONEY_QUANT = Decimal("1")
TYPE_OPTIONS = ("expense", "income")


def amount_to_cents(raw_amount):
    raw_amount = raw_amount.strip().replace(",", "")
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
    raw_date = raw_date.strip()
    if not raw_date:
        raise ValueError("Date must be non-empty.")

    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def parse_month(raw_month):
    raw_month = raw_month.strip()
    if not raw_month:
        return None

    try:
        datetime.strptime(raw_month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month filter must use YYYY-MM format.") from exc

    return raw_month


def money_text(cents):
    cents = int(cents or 0)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


def amount_entry_text(cents):
    cents = abs(int(cents or 0))
    return f"{cents // 100}.{cents % 100:02d}"


class ExpenseTrackerApp:
    def __init__(self, root):
        self.root = root
        self.records = []
        self.editing_record_id = None

        self.root.title("Expense Tracker")
        self.root.geometry("1040x720")
        self.root.minsize(940, 640)

        database_init()
        self.build_ui()
        self.bind_shortcuts()
        self.refresh_records("Ready.")

    def build_ui(self):
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        self.build_header()
        self.build_editor()
        self.build_filters()
        self.build_table()
        self.build_status_bar()

    def build_header(self):
        header = ttk.Frame(self.root, padding=(16, 12, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Expense Tracker", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        self.version_label = ttk.Label(header, text="v26.5")
        self.version_label.grid(row=0, column=1, sticky="e")

    def build_editor(self):
        editor = ttk.LabelFrame(self.root, text="Record", padding=12)
        editor.grid(row=1, column=0, padx=16, pady=(4, 8), sticky="ew")
        for column in range(8):
            editor.columnconfigure(column, weight=1)

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.type_var = tk.StringVar(value="expense")
        self.category_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.note_var = tk.StringVar()

        ttk.Label(editor, text="Date").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.date_entry = ttk.Entry(editor, textvariable=self.date_var, width=12)
        self.date_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Type").grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.type_combo = ttk.Combobox(
            editor,
            textvariable=self.type_var,
            values=TYPE_OPTIONS,
            state="readonly",
            width=10,
        )
        self.type_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Category").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(editor, textvariable=self.category_var, width=18)
        self.category_combo.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Amount").grid(row=0, column=3, sticky="w", padx=(0, 6))
        self.amount_entry = ttk.Entry(editor, textvariable=self.amount_var, width=12)
        self.amount_entry.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Note").grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.note_entry = ttk.Entry(editor, textvariable=self.note_var)
        self.note_entry.grid(row=1, column=4, columnspan=2, sticky="ew", padx=(0, 10), pady=(3, 0))

        self.save_button = ttk.Button(editor, text="Add Record", command=self.save_record)
        self.save_button.grid(row=1, column=6, sticky="ew", padx=(0, 8), pady=(3, 0))

        clear_button = ttk.Button(editor, text="Clear", command=self.clear_form)
        clear_button.grid(row=1, column=7, sticky="ew", pady=(3, 0))

    def build_filters(self):
        filters = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        filters.grid(row=2, column=0, sticky="ew")
        filters.columnconfigure(6, weight=1)

        self.month_filter_var = tk.StringVar()
        self.category_filter_var = tk.StringVar()
        self.search_var = tk.StringVar()

        ttk.Label(filters, text="Month").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.month_filter_var, width=10).grid(
            row=0, column=1, sticky="w", padx=(6, 14)
        )

        ttk.Label(filters, text="Category").grid(row=0, column=2, sticky="w")
        self.category_filter = ttk.Combobox(
            filters,
            textvariable=self.category_filter_var,
            width=18,
        )
        self.category_filter.grid(row=0, column=3, sticky="w", padx=(6, 14))

        ttk.Label(filters, text="Search").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.search_var, width=22).grid(
            row=0, column=5, sticky="w", padx=(6, 14)
        )

        ttk.Button(filters, text="Apply", command=lambda: self.refresh_records()).grid(
            row=0, column=7, sticky="e", padx=(0, 8)
        )
        ttk.Button(filters, text="Reset", command=self.reset_filters).grid(
            row=0, column=8, sticky="e"
        )

        summary = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        summary.grid(row=3, column=0, sticky="ew")
        for column in range(4):
            summary.columnconfigure(column, weight=1)

        self.total_expense_var = tk.StringVar(value="Expense: $0.00")
        self.total_income_var = tk.StringVar(value="Income: $0.00")
        self.balance_var = tk.StringVar(value="Balance: $0.00")
        self.count_var = tk.StringVar(value="Records: 0")

        ttk.Label(summary, textvariable=self.total_expense_var).grid(row=0, column=0, sticky="w")
        ttk.Label(summary, textvariable=self.total_income_var).grid(row=0, column=1, sticky="w")
        ttk.Label(summary, textvariable=self.balance_var).grid(row=0, column=2, sticky="w")
        ttk.Label(summary, textvariable=self.count_var).grid(row=0, column=3, sticky="e")

    def build_table(self):
        table_frame = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        table_frame.grid(row=4, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("date", "type", "category", "amount", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("date", text="Date")
        self.tree.heading("type", text="Type")
        self.tree.heading("category", text="Category")
        self.tree.heading("amount", text="Amount")
        self.tree.heading("note", text="Note")

        self.tree.column("date", width=110, minwidth=90, anchor="w")
        self.tree.column("type", width=90, minwidth=80, anchor="w")
        self.tree.column("category", width=160, minwidth=120, anchor="w")
        self.tree.column("amount", width=120, minwidth=100, anchor="e")
        self.tree.column("note", width=420, minwidth=180, anchor="w")

        self.tree.tag_configure("income", foreground="#18794e")
        self.tree.tag_configure("expense", foreground="#b42318")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        actions = ttk.Frame(table_frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(3, weight=1)

        ttk.Button(actions, text="Edit", command=self.start_edit).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Delete", command=self.delete_selected).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Export CSV", command=self.export_csv).grid(row=0, column=2)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda event: self.start_edit())
        self.tree.bind("<Delete>", lambda event: self.delete_selected())

    def build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(16, 6))
        status.grid(row=5, column=0, sticky="ew")

    def bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda event: self.save_record())
        self.root.bind("<Escape>", lambda event: self.clear_form())

    def set_status(self, message):
        self.status_var.set(message)

    def filters(self):
        month = parse_month(self.month_filter_var.get())
        category = self.category_filter_var.get().strip() or None
        search = self.search_var.get().strip() or None
        return month, category, search

    def refresh_records(self, status_message=None):
        try:
            month, category, search = self.filters()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        self.records = load_records(month=month, category=category, search=search)
        self.populate_table()
        self.update_summary()
        self.update_category_options()
        self.set_status(status_message or f"Showing {len(self.records)} record(s).")

    def populate_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for record in self.records:
            amount = money_text(record["amount_cents"])
            if record["type"] == "expense":
                amount = f"-{amount}"
            else:
                amount = f"+{amount}"

            self.tree.insert(
                "",
                tk.END,
                iid=str(record["id"]),
                values=(
                    record["date"],
                    record["type"].title(),
                    record["category"],
                    amount,
                    record["note"] or "",
                ),
                tags=(record["type"],),
            )

    def update_summary(self):
        income = sum(record["amount_cents"] for record in self.records if record["type"] == "income")
        expense = sum(
            record["amount_cents"] for record in self.records if record["type"] == "expense"
        )
        balance = income - expense

        self.total_expense_var.set(f"Expense: {money_text(expense)}")
        self.total_income_var.set(f"Income: {money_text(income)}")
        self.balance_var.set(f"Balance: {money_text(balance)}")
        self.count_var.set(f"Records: {len(self.records)}")

    def update_category_options(self):
        categories = get_categories()
        self.category_combo.configure(values=categories)
        self.category_filter.configure(values=[""] + categories)

    def selected_record(self):
        selected = self.tree.selection()
        if not selected:
            return None

        record_id = int(selected[0])
        return next((record for record in self.records if record["id"] == record_id), None)

    def on_select(self, event=None):
        record = self.selected_record()
        if record:
            self.set_status(f"Selected record #{record['id']}.")

    def read_form(self):
        record_date = parse_record_date(self.date_var.get())
        record_type = self.type_var.get()
        category = self.category_var.get().strip()
        amount_cents = amount_to_cents(self.amount_var.get())
        note = self.note_var.get().strip()

        if record_type not in TYPE_OPTIONS:
            raise ValueError("Type must be income or expense.")
        if not category:
            raise ValueError("Category must be non-empty.")

        return record_type, category, amount_cents, note, record_date

    def save_record(self):
        try:
            record_type, category, amount_cents, note, record_date = self.read_form()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        if self.editing_record_id is None:
            insert_record(record_type, category, amount_cents, note, record_date)
            self.clear_form(reset_status=False)
            self.refresh_records("Record added.")
            return

        updated = update_record(
            self.editing_record_id,
            record_type,
            category,
            amount_cents,
            note,
            record_date,
        )
        self.clear_form(reset_status=False)
        self.refresh_records("Record updated." if updated else "Record was not found.")

    def start_edit(self):
        record = self.selected_record()
        if not record:
            self.set_status("Select a record to edit.")
            return

        self.editing_record_id = record["id"]
        self.date_var.set(record["date"])
        self.type_var.set(record["type"])
        self.category_var.set(record["category"])
        self.amount_var.set(amount_entry_text(record["amount_cents"]))
        self.note_var.set(record["note"] or "")
        self.save_button.configure(text="Update Record")
        self.set_status(f"Editing record #{record['id']}.")
        self.date_entry.focus_set()

    def clear_form(self, reset_status=True):
        self.editing_record_id = None
        self.date_var.set(date.today().isoformat())
        self.type_var.set("expense")
        self.category_var.set("")
        self.amount_var.set("")
        self.note_var.set("")
        self.save_button.configure(text="Add Record")
        self.tree.selection_remove(self.tree.selection())
        if reset_status:
            self.set_status("Form cleared.")

    def delete_selected(self):
        record = self.selected_record()
        if not record:
            self.set_status("Select a record to delete.")
            return

        confirmed = messagebox.askyesno(
            "Delete record",
            f"Delete {record['category']} {money_text(record['amount_cents'])} on {record['date']}?",
        )
        if not confirmed:
            self.set_status("Delete cancelled.")
            return

        delete_record(record["id"])
        if self.editing_record_id == record["id"]:
            self.clear_form(reset_status=False)
        self.refresh_records("Record deleted.")

    def reset_filters(self):
        self.month_filter_var.set("")
        self.category_filter_var.set("")
        self.search_var.set("")
        self.refresh_records("Filters reset.")

    def export_csv(self):
        if not self.records:
            self.set_status("There are no records to export.")
            return

        default_name = f"expense-records-{date.today().isoformat()}.csv"
        path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            self.set_status("Export cancelled.")
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["date", "type", "category", "amount", "note"])
            for record in self.records:
                writer.writerow(
                    [
                        record["date"],
                        record["type"],
                        record["category"],
                        amount_entry_text(record["amount_cents"]),
                        record["note"] or "",
                    ]
                )

        self.set_status(f"Exported {len(self.records)} record(s) to CSV.")
