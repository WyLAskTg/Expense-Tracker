import csv
import os
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from tkinter import filedialog, messagebox, ttk

from database import (
    backup_database,
    database_init,
    delete_budget,
    delete_record,
    get_categories,
    get_db_path,
    get_months,
    insert_record,
    load_budgets,
    load_category_spending,
    load_monthly_summary,
    load_records,
    restore_database,
    update_record,
    upsert_budget,
)


MONEY_QUANT = Decimal("1")
TYPE_OPTIONS = ("expense", "income")
CURRENT_MONTH = date.today().strftime("%Y-%m")


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
        raise ValueError("Month must use YYYY-MM format.") from exc

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
        self.budgets = []
        self.category_chart_data = []
        self.monthly_chart_data = []
        self.editing_record_id = None

        self.root.title("Expense Tracker")
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)

        database_init()
        self.build_ui()
        self.bind_shortcuts()
        self.refresh_all("Ready.")

    def build_ui(self):
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.build_header()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        self.records_tab = ttk.Frame(self.notebook)
        self.reports_tab = ttk.Frame(self.notebook)
        self.budgets_tab = ttk.Frame(self.notebook)
        self.tools_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.records_tab, text="Records")
        self.notebook.add(self.reports_tab, text="Reports")
        self.notebook.add(self.budgets_tab, text="Budgets")
        self.notebook.add(self.tools_tab, text="Tools")

        self.build_records_tab()
        self.build_reports_tab()
        self.build_budgets_tab()
        self.build_tools_tab()
        self.build_status_bar()

    def build_header(self):
        header = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Expense Tracker", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        self.version_label = ttk.Label(header, text="v26.6")
        self.version_label.grid(row=0, column=1, sticky="e")

    def build_records_tab(self):
        self.records_tab.columnconfigure(0, weight=1)
        self.records_tab.rowconfigure(3, weight=1)

        self.build_record_editor()
        self.build_record_filters()
        self.build_record_table()

    def build_record_editor(self):
        editor = ttk.LabelFrame(self.records_tab, text="Record", padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
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

    def build_record_filters(self):
        filters = ttk.Frame(self.records_tab, padding=(10, 0, 10, 8))
        filters.grid(row=1, column=0, sticky="ew")
        filters.columnconfigure(6, weight=1)

        self.month_filter_var = tk.StringVar()
        self.category_filter_var = tk.StringVar()
        self.search_var = tk.StringVar()

        ttk.Label(filters, text="Month").grid(row=0, column=0, sticky="w")
        self.month_filter = ttk.Combobox(filters, textvariable=self.month_filter_var, width=10)
        self.month_filter.grid(row=0, column=1, sticky="w", padx=(6, 14))

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

        summary = ttk.Frame(self.records_tab, padding=(10, 0, 10, 8))
        summary.grid(row=2, column=0, sticky="ew")
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

    def build_record_table(self):
        table_frame = ttk.Frame(self.records_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=3, column=0, sticky="nsew")
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

    def build_reports_tab(self):
        self.reports_tab.columnconfigure(0, weight=1)
        self.reports_tab.columnconfigure(1, weight=1)
        self.reports_tab.rowconfigure(2, weight=1)

        controls = ttk.Frame(self.reports_tab, padding=(10, 10, 10, 8))
        controls.grid(row=0, column=0, columnspan=2, sticky="ew")
        controls.columnconfigure(4, weight=1)

        self.report_month_var = tk.StringVar(value=CURRENT_MONTH)
        ttk.Label(controls, text="Month").grid(row=0, column=0, sticky="w")
        self.report_month_combo = ttk.Combobox(controls, textvariable=self.report_month_var, width=10)
        self.report_month_combo.grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Button(controls, text="Refresh", command=lambda: self.refresh_reports()).grid(
            row=0, column=2, sticky="w"
        )

        metrics = ttk.Frame(self.reports_tab, padding=(10, 0, 10, 8))
        metrics.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            metrics.columnconfigure(column, weight=1)

        self.report_income_var = tk.StringVar(value="Income: $0.00")
        self.report_expense_var = tk.StringVar(value="Expense: $0.00")
        self.report_balance_var = tk.StringVar(value="Balance: $0.00")
        self.report_top_category_var = tk.StringVar(value="Top category: -")

        ttk.Label(metrics, textvariable=self.report_income_var).grid(row=0, column=0, sticky="w")
        ttk.Label(metrics, textvariable=self.report_expense_var).grid(row=0, column=1, sticky="w")
        ttk.Label(metrics, textvariable=self.report_balance_var).grid(row=0, column=2, sticky="w")
        ttk.Label(metrics, textvariable=self.report_top_category_var).grid(row=0, column=3, sticky="e")

        self.category_canvas = tk.Canvas(self.reports_tab, background="#ffffff", highlightthickness=1, highlightbackground="#d0d7de")
        self.trend_canvas = tk.Canvas(self.reports_tab, background="#ffffff", highlightthickness=1, highlightbackground="#d0d7de")
        self.category_canvas.grid(row=2, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        self.trend_canvas.grid(row=2, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.category_canvas.bind("<Configure>", lambda event: self.draw_category_chart())
        self.trend_canvas.bind("<Configure>", lambda event: self.draw_trend_chart())

    def build_budgets_tab(self):
        self.budgets_tab.columnconfigure(0, weight=1)
        self.budgets_tab.rowconfigure(2, weight=1)

        editor = ttk.LabelFrame(self.budgets_tab, text="Monthly Budget", padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        for column in range(7):
            editor.columnconfigure(column, weight=1)

        self.budget_month_var = tk.StringVar(value=CURRENT_MONTH)
        self.budget_category_var = tk.StringVar()
        self.budget_amount_var = tk.StringVar()

        ttk.Label(editor, text="Month").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.budget_month_combo = ttk.Combobox(editor, textvariable=self.budget_month_var, width=10)
        self.budget_month_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Category").grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.budget_category_combo = ttk.Combobox(editor, textvariable=self.budget_category_var, width=18)
        self.budget_category_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text="Amount").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.budget_amount_var, width=12).grid(
            row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Button(editor, text="Save Budget", command=self.save_budget).grid(
            row=1, column=3, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Button(editor, text="Clear", command=self.clear_budget_form).grid(
            row=1, column=4, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Button(editor, text="Delete", command=self.delete_selected_budget).grid(
            row=1, column=5, sticky="ew", pady=(3, 0)
        )

        self.budget_summary_var = tk.StringVar(value="No budgets for this month.")
        ttk.Label(self.budgets_tab, textvariable=self.budget_summary_var, padding=(10, 0, 10, 8)).grid(
            row=1, column=0, sticky="ew"
        )

        table_frame = ttk.Frame(self.budgets_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("category", "budget", "spent", "remaining", "usage")
        self.budget_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.budget_tree.heading("category", text="Category")
        self.budget_tree.heading("budget", text="Budget")
        self.budget_tree.heading("spent", text="Spent")
        self.budget_tree.heading("remaining", text="Remaining")
        self.budget_tree.heading("usage", text="Usage")

        self.budget_tree.column("category", width=180, minwidth=130, anchor="w")
        self.budget_tree.column("budget", width=120, minwidth=100, anchor="e")
        self.budget_tree.column("spent", width=120, minwidth=100, anchor="e")
        self.budget_tree.column("remaining", width=120, minwidth=100, anchor="e")
        self.budget_tree.column("usage", width=100, minwidth=80, anchor="e")

        self.budget_tree.tag_configure("ok", foreground="#18794e")
        self.budget_tree.tag_configure("near", foreground="#9a6700")
        self.budget_tree.tag_configure("over", foreground="#b42318")

        budget_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.budget_tree.yview)
        self.budget_tree.configure(yscrollcommand=budget_scroll.set)
        self.budget_tree.grid(row=0, column=0, sticky="nsew")
        budget_scroll.grid(row=0, column=1, sticky="ns")

        self.budget_tree.bind("<<TreeviewSelect>>", self.on_budget_select)
        self.budget_tree.bind("<Delete>", lambda event: self.delete_selected_budget())

    def build_tools_tab(self):
        self.tools_tab.columnconfigure(0, weight=1)

        data_frame = ttk.LabelFrame(self.tools_tab, text="Data", padding=12)
        data_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        data_frame.columnconfigure(1, weight=1)

        self.db_path_var = tk.StringVar(value=str(get_db_path()))
        ttk.Label(data_frame, text="Database").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(data_frame, textvariable=self.db_path_var).grid(row=0, column=1, sticky="ew")

        ttk.Button(data_frame, text="Backup Database", command=self.backup_data).grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Button(data_frame, text="Restore Database", command=self.restore_data).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        ttk.Button(data_frame, text="Open Data Folder", command=self.open_data_folder).grid(
            row=1, column=2, sticky="w", padx=(8, 0), pady=(12, 0)
        )

    def build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(16, 6))
        status.grid(row=2, column=0, sticky="ew")

    def bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda event: self.save_current_tab())
        self.root.bind("<Escape>", lambda event: self.clear_current_tab())

    def set_status(self, message):
        self.status_var.set(message)

    def refresh_all(self, status_message=None):
        self.refresh_records(status_message)
        self.refresh_reports(update_status=False)
        self.refresh_budgets(update_status=False)
        self.update_picker_options()

    def update_picker_options(self):
        categories = get_categories()
        months = get_months()
        if CURRENT_MONTH not in months:
            months = [CURRENT_MONTH] + months

        self.category_combo.configure(values=categories)
        self.category_filter.configure(values=[""] + categories)
        self.budget_category_combo.configure(values=categories)
        self.month_filter.configure(values=[""] + months)
        self.report_month_combo.configure(values=[""] + months)
        self.budget_month_combo.configure(values=months)

    def save_current_tab(self):
        current = self.notebook.select()
        if current == str(self.records_tab):
            self.save_record()
        elif current == str(self.budgets_tab):
            self.save_budget()
        else:
            self.set_status("Nothing to save on this tab.")

    def clear_current_tab(self):
        current = self.notebook.select()
        if current == str(self.records_tab):
            self.clear_form()
        elif current == str(self.budgets_tab):
            self.clear_budget_form()
        else:
            self.set_status("Nothing to clear on this tab.")

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
        self.update_picker_options()
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
            self.refresh_all("Record added.")
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
        self.refresh_all("Record updated." if updated else "Record was not found.")

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
        self.notebook.select(self.records_tab)
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
        self.refresh_all("Record deleted.")

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

    def refresh_reports(self, update_status=True):
        try:
            month = parse_month(self.report_month_var.get())
        except ValueError as exc:
            self.set_status(str(exc))
            return

        records = load_records(month=month)
        income = sum(record["amount_cents"] for record in records if record["type"] == "income")
        expense = sum(record["amount_cents"] for record in records if record["type"] == "expense")
        balance = income - expense

        self.category_chart_data = load_category_spending(month=month)
        self.monthly_chart_data = load_monthly_summary(limit=12)

        self.report_income_var.set(f"Income: {money_text(income)}")
        self.report_expense_var.set(f"Expense: {money_text(expense)}")
        self.report_balance_var.set(f"Balance: {money_text(balance)}")

        if self.category_chart_data:
            top = self.category_chart_data[0]
            self.report_top_category_var.set(
                f"Top category: {top['category']} ({money_text(top['spent_cents'])})"
            )
        else:
            self.report_top_category_var.set("Top category: -")

        self.draw_category_chart()
        self.draw_trend_chart()
        self.update_picker_options()
        if update_status:
            self.set_status("Reports refreshed.")

    def draw_category_chart(self):
        canvas = self.category_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 260)
        left = 120
        right = 24
        top = 44
        row_height = 30

        canvas.create_text(16, 16, anchor="w", text="Category Spending", font=("Segoe UI", 11, "bold"), fill="#24292f")

        rows = self.category_chart_data[:8]
        if not rows:
            canvas.create_text(width / 2, height / 2, text="No expense data for this view.", fill="#57606a")
            return

        max_value = max(row["spent_cents"] or 0 for row in rows) or 1
        bar_width = max(width - left - right, 120)
        colors = ["#b42318", "#2f6f8f", "#9a6700", "#18794e", "#8250df", "#57606a"]

        for index, row in enumerate(rows):
            y = top + index * row_height
            value = int(row["spent_cents"] or 0)
            length = max(int(bar_width * value / max_value), 2)
            color = colors[index % len(colors)]
            canvas.create_text(16, y + 10, anchor="w", text=row["category"], fill="#24292f")
            canvas.create_rectangle(left, y, left + length, y + 18, fill=color, outline="")
            canvas.create_text(left + length + 8, y + 9, anchor="w", text=money_text(value), fill="#57606a")

    def draw_trend_chart(self):
        canvas = self.trend_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 260)
        left = 44
        right = 20
        top = 44
        bottom = 40

        canvas.create_text(16, 16, anchor="w", text="12-Month Trend", font=("Segoe UI", 11, "bold"), fill="#24292f")
        rows = self.monthly_chart_data
        if not rows:
            canvas.create_text(width / 2, height / 2, text="No monthly data yet.", fill="#57606a")
            return

        max_value = max(
            max(int(row["income_cents"] or 0), int(row["expense_cents"] or 0))
            for row in rows
        ) or 1
        chart_width = max(width - left - right, 120)
        chart_height = max(height - top - bottom, 120)
        slot = chart_width / max(len(rows), 1)

        canvas.create_line(left, top + chart_height, width - right, top + chart_height, fill="#d0d7de")
        canvas.create_text(left, top - 8, anchor="w", text=money_text(max_value), fill="#57606a")
        canvas.create_text(width - right - 140, 18, anchor="w", text="Income", fill="#18794e")
        canvas.create_rectangle(width - right - 160, 12, width - right - 146, 24, fill="#18794e", outline="")
        canvas.create_text(width - right - 68, 18, anchor="w", text="Expense", fill="#b42318")
        canvas.create_rectangle(width - right - 88, 12, width - right - 74, 24, fill="#b42318", outline="")

        for index, row in enumerate(rows):
            x = left + index * slot + slot * 0.18
            income = int(row["income_cents"] or 0)
            expense = int(row["expense_cents"] or 0)
            income_h = chart_height * income / max_value
            expense_h = chart_height * expense / max_value
            bar_w = max(slot * 0.24, 5)

            canvas.create_rectangle(
                x,
                top + chart_height - income_h,
                x + bar_w,
                top + chart_height,
                fill="#18794e",
                outline="",
            )
            canvas.create_rectangle(
                x + bar_w + 4,
                top + chart_height - expense_h,
                x + bar_w * 2 + 4,
                top + chart_height,
                fill="#b42318",
                outline="",
            )
            canvas.create_text(
                x + bar_w,
                top + chart_height + 14,
                text=row["month"][5:],
                fill="#57606a",
            )

    def read_budget_form(self):
        month = parse_month(self.budget_month_var.get())
        if month is None:
            raise ValueError("Budget month must be non-empty.")

        category = self.budget_category_var.get().strip()
        if not category:
            raise ValueError("Budget category must be non-empty.")

        amount_cents = amount_to_cents(self.budget_amount_var.get())
        return month, category, amount_cents

    def refresh_budgets(self, update_status=True):
        try:
            month = parse_month(self.budget_month_var.get()) or CURRENT_MONTH
        except ValueError as exc:
            self.set_status(str(exc))
            return

        self.budget_month_var.set(month)
        self.budgets = load_budgets(month=month)
        spending = {row["category"]: int(row["spent_cents"] or 0) for row in load_category_spending(month=month)}

        for item in self.budget_tree.get_children():
            self.budget_tree.delete(item)

        total_budget = 0
        total_spent = 0
        over_count = 0

        for budget in self.budgets:
            spent = spending.get(budget["category"], 0)
            remaining = budget["amount_cents"] - spent
            usage = spent / budget["amount_cents"] if budget["amount_cents"] else 0
            total_budget += budget["amount_cents"]
            total_spent += spent
            if remaining < 0:
                tag = "over"
                over_count += 1
            elif usage >= 0.8:
                tag = "near"
            else:
                tag = "ok"

            self.budget_tree.insert(
                "",
                tk.END,
                iid=str(budget["id"]),
                values=(
                    budget["category"],
                    money_text(budget["amount_cents"]),
                    money_text(spent),
                    money_text(remaining),
                    f"{usage * 100:.0f}%",
                ),
                tags=(tag,),
            )

        if self.budgets:
            self.budget_summary_var.set(
                f"{month}: {money_text(total_spent)} spent of {money_text(total_budget)} budgeted; "
                f"{over_count} over budget."
            )
        else:
            self.budget_summary_var.set(f"No budgets for {month}.")

        self.update_picker_options()
        if update_status:
            self.set_status("Budgets refreshed.")

    def selected_budget(self):
        selected = self.budget_tree.selection()
        if not selected:
            return None

        budget_id = int(selected[0])
        return next((budget for budget in self.budgets if budget["id"] == budget_id), None)

    def on_budget_select(self, event=None):
        budget = self.selected_budget()
        if not budget:
            return

        self.budget_month_var.set(budget["month"])
        self.budget_category_var.set(budget["category"])
        self.budget_amount_var.set(amount_entry_text(budget["amount_cents"]))
        self.set_status(f"Selected budget #{budget['id']}.")

    def save_budget(self):
        try:
            month, category, amount_cents = self.read_budget_form()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        upsert_budget(month, category, amount_cents)
        self.clear_budget_form(reset_status=False)
        self.budget_month_var.set(month)
        self.refresh_budgets(update_status=False)
        self.refresh_reports(update_status=False)
        self.set_status("Budget saved.")

    def clear_budget_form(self, reset_status=True):
        self.budget_category_var.set("")
        self.budget_amount_var.set("")
        self.budget_tree.selection_remove(self.budget_tree.selection())
        if reset_status:
            self.set_status("Budget form cleared.")

    def delete_selected_budget(self):
        budget = self.selected_budget()
        if not budget:
            self.set_status("Select a budget to delete.")
            return

        confirmed = messagebox.askyesno(
            "Delete budget",
            f"Delete {budget['month']} budget for {budget['category']}?",
        )
        if not confirmed:
            self.set_status("Delete cancelled.")
            return

        delete_budget(budget["id"])
        self.clear_budget_form(reset_status=False)
        self.refresh_budgets(update_status=False)
        self.set_status("Budget deleted.")

    def backup_data(self):
        default_name = f"expense-tracker-backup-{date.today().isoformat()}.db"
        path = filedialog.asksaveasfilename(
            title="Backup database",
            defaultextension=".db",
            initialfile=default_name,
            filetypes=(("SQLite database", "*.db"), ("All files", "*.*")),
        )
        if not path:
            self.set_status("Backup cancelled.")
            return

        destination = backup_database(path)
        self.set_status(f"Backup saved to {destination}.")

    def restore_data(self):
        path = filedialog.askopenfilename(
            title="Restore database",
            filetypes=(("SQLite database", "*.db"), ("All files", "*.*")),
        )
        if not path:
            self.set_status("Restore cancelled.")
            return

        confirmed = messagebox.askyesno(
            "Restore database",
            "Restore this backup and replace the current local database?",
        )
        if not confirmed:
            self.set_status("Restore cancelled.")
            return

        try:
            destination = restore_database(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Restore failed", str(exc))
            self.set_status("Restore failed.")
            return

        self.db_path_var.set(str(destination))
        self.clear_form(reset_status=False)
        self.clear_budget_form(reset_status=False)
        self.refresh_all("Database restored.")

    def open_data_folder(self):
        folder = get_db_path().parent
        if os.name == "nt":
            os.startfile(folder)
        else:
            self.set_status(f"Data folder: {folder}")
