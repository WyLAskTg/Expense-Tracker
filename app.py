import csv
import os
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from app_config import (
    APP_ICON,
    APP_VERSION,
    CURRENT_BACKUP_KEEP,
    CURRENCY_OPTIONS,
    DEFAULT_ACCOUNT,
    DEFAULT_LANGUAGE,
    THEME_OPTIONS,
)
from database import (
    backup_database,
    database_init,
    delete_budget,
    delete_category,
    delete_record,
    delete_recurring_rule,
    generate_due_recurring_records,
    get_accounts,
    get_categories,
    get_db_path,
    get_months,
    get_setting,
    insert_record,
    load_account_spending,
    load_budgets,
    load_budget_progress,
    load_categories,
    load_category_spending,
    load_monthly_summary,
    load_recurring_rules,
    load_records,
    restore_database,
    run_auto_backup,
    save_category,
    set_setting,
    update_record,
    upsert_recurring_rule,
    upsert_budget,
)
from i18n import LANGUAGES, translate
from record_utils import (
    TYPE_OPTIONS,
    amount_entry_text,
    amount_to_cents,
    csv_headers,
    default_csv_mapping,
    money_text,
    parse_csv_records,
    parse_month,
    parse_record_date,
    split_new_and_duplicate_records,
)
from security import hash_password, verify_password


CURRENT_MONTH = date.today().strftime("%Y-%m")

LIGHT_PALETTE = {
    "background": "#f6f8fa",
    "surface": "#ffffff",
    "text": "#24292f",
    "muted": "#57606a",
    "border": "#d0d7de",
    "income": "#18794e",
    "expense": "#b42318",
    "warning": "#9a6700",
    "accent": "#0969da",
}

DARK_PALETTE = {
    "background": "#1f2328",
    "surface": "#2d333b",
    "text": "#f0f3f6",
    "muted": "#adbac7",
    "border": "#444c56",
    "income": "#57ab5a",
    "expense": "#e5534b",
    "warning": "#c69026",
    "accent": "#539bf5",
}

def resource_path(relative_path):
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


class ExpenseTrackerApp:
    def __init__(self, root):
        self.root = root
        self.records = []
        self.budgets = []
        self.categories = []
        self.accounts = []
        self.recurring_rules = []
        self.category_chart_data = []
        self.monthly_chart_data = []
        self.account_chart_data = []
        self.budget_progress_data = []
        self.editing_record_id = None
        self.editing_category_id = None
        self.editing_recurring_id = None
        self.startup_messages = []

        database_init()
        self.language_code = get_setting("language", DEFAULT_LANGUAGE)
        if self.language_code not in LANGUAGES:
            self.language_code = DEFAULT_LANGUAGE
        self.currency_code = get_setting("currency", "USD")
        if self.currency_code not in CURRENCY_OPTIONS:
            self.currency_code = "USD"
        self.currency_symbol = CURRENCY_OPTIONS[self.currency_code]
        self.theme_name = get_setting("theme", "Light")
        if self.theme_name not in THEME_OPTIONS:
            self.theme_name = "Light"
        self.palette = LIGHT_PALETTE if self.theme_name == "Light" else DARK_PALETTE

        self.root.title(self.t("app_title"))
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)
        self.set_window_icon()

        if not self.unlock_app():
            self.root.destroy()
            return

        self.run_startup_jobs()
        self.build_ui()
        self.bind_shortcuts()
        self.refresh_all("; ".join(self.startup_messages) if self.startup_messages else self.t("ready"))

    def t(self, key, **kwargs):
        return translate(self.language_code, key, **kwargs)

    def money_text(self, cents):
        return money_text(cents, self.currency_symbol)

    def set_window_icon(self):
        icon_path = resource_path(APP_ICON)
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

    def has_password(self):
        return bool(get_setting("password_hash") and get_setting("password_salt"))

    def unlock_app(self):
        digest = get_setting("password_hash")
        salt = get_setting("password_salt")
        if not digest or not salt:
            return True

        self.root.withdraw()
        for _ in range(3):
            password = simpledialog.askstring(
                self.t("unlock_required"),
                self.t("password_prompt"),
                show="*",
                parent=self.root,
            )
            if password is None:
                return False
            if verify_password(password, salt, digest):
                self.root.deiconify()
                return True
            messagebox.showerror(self.t("unlock_required"), self.t("invalid_password"), parent=self.root)
        return False

    def run_startup_jobs(self):
        try:
            backup_path = run_auto_backup(CURRENT_BACKUP_KEEP)
            if backup_path:
                self.startup_messages.append(self.t("backup_created"))
        except OSError as exc:
            self.startup_messages.append(f"{self.t('backup_failed')}: {exc}")

        generated = generate_due_recurring_records()
        if generated:
            self.startup_messages.append(self.t("recurring_generated", count=generated))

    def build_ui(self):
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.apply_theme()

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.build_header()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        self.records_tab = ttk.Frame(self.notebook)
        self.reports_tab = ttk.Frame(self.notebook)
        self.budgets_tab = ttk.Frame(self.notebook)
        self.categories_tab = ttk.Frame(self.notebook)
        self.recurring_tab = ttk.Frame(self.notebook)
        self.tools_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.records_tab, text=self.t("records"))
        self.notebook.add(self.reports_tab, text=self.t("reports"))
        self.notebook.add(self.budgets_tab, text=self.t("budgets"))
        self.notebook.add(self.categories_tab, text=self.t("categories"))
        self.notebook.add(self.recurring_tab, text=self.t("recurring"))
        self.notebook.add(self.tools_tab, text=self.t("tools"))

        self.build_records_tab()
        self.build_reports_tab()
        self.build_budgets_tab()
        self.build_categories_tab()
        self.build_recurring_tab()
        self.build_tools_tab()
        self.build_status_bar()

    def apply_theme(self):
        self.palette = LIGHT_PALETTE if self.theme_name == "Light" else DARK_PALETTE
        self.root.configure(background=self.palette["background"])
        self.style.configure(".", background=self.palette["background"], foreground=self.palette["text"])
        self.style.configure("TFrame", background=self.palette["background"])
        self.style.configure("TLabel", background=self.palette["background"], foreground=self.palette["text"])
        self.style.configure("TLabelframe", background=self.palette["background"], foreground=self.palette["text"])
        self.style.configure("TLabelframe.Label", background=self.palette["background"], foreground=self.palette["text"])
        self.style.configure("TNotebook", background=self.palette["background"], bordercolor=self.palette["border"])
        self.style.configure("TNotebook.Tab", padding=(12, 6))
        self.style.configure(
            "Treeview",
            background=self.palette["surface"],
            fieldbackground=self.palette["surface"],
            foreground=self.palette["text"],
            bordercolor=self.palette["border"],
        )
        self.style.configure("Treeview.Heading", background=self.palette["background"], foreground=self.palette["text"])
        self.style.map("Treeview", background=[("selected", self.palette["accent"])])

    def build_header(self):
        header = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=self.t("app_title"), font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        ttk.Label(header, text=self.t("language")).grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.language_var = tk.StringVar(value=self.language_code)
        language_combo = ttk.Combobox(
            header,
            textvariable=self.language_var,
            values=list(LANGUAGES.keys()),
            state="readonly",
            width=5,
        )
        language_combo.grid(row=0, column=2, sticky="e", padx=(0, 12))
        language_combo.bind("<<ComboboxSelected>>", self.change_language)

        self.version_label = ttk.Label(header, text=APP_VERSION)
        self.version_label.grid(row=0, column=3, sticky="e")

    def change_language(self, event=None):
        new_language = self.language_var.get()
        if new_language not in LANGUAGES or new_language == self.language_code:
            return

        self.language_code = new_language
        set_setting("language", new_language)
        for child in self.root.winfo_children():
            child.destroy()
        self.build_ui()
        self.bind_shortcuts()
        self.refresh_all(self.t("ready"))

    def change_language_from_settings(self, event=None):
        self.language_var.set(self.settings_language_var.get())
        self.change_language()

    def change_currency(self, event=None):
        new_currency = self.currency_var.get()
        if new_currency not in CURRENCY_OPTIONS or new_currency == self.currency_code:
            return

        self.currency_code = new_currency
        self.currency_symbol = CURRENCY_OPTIONS[new_currency]
        set_setting("currency", new_currency)
        self.refresh_all(self.t("ready"))

    def change_theme(self, event=None):
        new_theme = self.theme_var.get()
        if new_theme not in THEME_OPTIONS or new_theme == self.theme_name:
            return

        self.theme_name = new_theme
        set_setting("theme", new_theme)
        for child in self.root.winfo_children():
            child.destroy()
        self.build_ui()
        self.bind_shortcuts()
        self.refresh_all(self.t("ready"))

    def build_records_tab(self):
        self.records_tab.columnconfigure(0, weight=1)
        self.records_tab.rowconfigure(3, weight=1)

        self.build_record_editor()
        self.build_record_filters()
        self.build_record_table()

    def build_record_editor(self):
        editor = ttk.LabelFrame(self.records_tab, text=self.t("record"), padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        for column in range(9):
            editor.columnconfigure(column, weight=1)

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.type_var = tk.StringVar(value="expense")
        self.category_var = tk.StringVar()
        self.account_var = tk.StringVar(value=DEFAULT_ACCOUNT)
        self.amount_var = tk.StringVar()
        self.note_var = tk.StringVar()

        ttk.Label(editor, text=self.t("date")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.date_entry = ttk.Entry(editor, textvariable=self.date_var, width=12)
        self.date_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("type")).grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.type_combo = ttk.Combobox(
            editor,
            textvariable=self.type_var,
            values=TYPE_OPTIONS,
            state="readonly",
            width=10,
        )
        self.type_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("category")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(editor, textvariable=self.category_var, width=18)
        self.category_combo.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("account")).grid(row=0, column=3, sticky="w", padx=(0, 6))
        self.account_combo = ttk.Combobox(editor, textvariable=self.account_var, width=14)
        self.account_combo.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("amount")).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.amount_entry = ttk.Entry(editor, textvariable=self.amount_var, width=12)
        self.amount_entry.grid(row=1, column=4, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("note")).grid(row=0, column=5, sticky="w", padx=(0, 6))
        self.note_entry = ttk.Entry(editor, textvariable=self.note_var)
        self.note_entry.grid(row=1, column=5, columnspan=2, sticky="ew", padx=(0, 10), pady=(3, 0))

        self.save_button = ttk.Button(editor, text=self.t("add_record"), command=self.save_record)
        self.save_button.grid(row=1, column=7, sticky="ew", padx=(0, 8), pady=(3, 0))

        clear_button = ttk.Button(editor, text=self.t("clear"), command=self.clear_form)
        clear_button.grid(row=1, column=8, sticky="ew", pady=(3, 0))

    def build_record_filters(self):
        filters = ttk.Frame(self.records_tab, padding=(10, 0, 10, 8))
        filters.grid(row=1, column=0, sticky="ew")
        filters.columnconfigure(8, weight=1)

        self.month_filter_var = tk.StringVar()
        self.category_filter_var = tk.StringVar()
        self.account_filter_var = tk.StringVar()
        self.search_var = tk.StringVar()

        ttk.Label(filters, text=self.t("month")).grid(row=0, column=0, sticky="w")
        self.month_filter = ttk.Combobox(filters, textvariable=self.month_filter_var, width=10)
        self.month_filter.grid(row=0, column=1, sticky="w", padx=(6, 14))

        ttk.Label(filters, text=self.t("category")).grid(row=0, column=2, sticky="w")
        self.category_filter = ttk.Combobox(
            filters,
            textvariable=self.category_filter_var,
            width=18,
        )
        self.category_filter.grid(row=0, column=3, sticky="w", padx=(6, 14))

        ttk.Label(filters, text=self.t("account")).grid(row=0, column=4, sticky="w")
        self.account_filter = ttk.Combobox(
            filters,
            textvariable=self.account_filter_var,
            width=14,
        )
        self.account_filter.grid(row=0, column=5, sticky="w", padx=(6, 14))

        ttk.Label(filters, text=self.t("search")).grid(row=0, column=6, sticky="w")
        ttk.Entry(filters, textvariable=self.search_var, width=22).grid(
            row=0, column=7, sticky="w", padx=(6, 14)
        )

        ttk.Button(filters, text=self.t("apply"), command=lambda: self.refresh_records()).grid(
            row=0, column=9, sticky="e", padx=(0, 8)
        )
        ttk.Button(filters, text=self.t("reset"), command=self.reset_filters).grid(
            row=0, column=10, sticky="e"
        )

        summary = ttk.Frame(self.records_tab, padding=(10, 0, 10, 8))
        summary.grid(row=2, column=0, sticky="ew")
        for column in range(4):
            summary.columnconfigure(column, weight=1)

        self.total_expense_var = tk.StringVar(value=f"{self.t('expense')}: $0.00")
        self.total_income_var = tk.StringVar(value=f"{self.t('income')}: $0.00")
        self.balance_var = tk.StringVar(value=f"{self.t('balance')}: $0.00")
        self.count_var = tk.StringVar(value=f"{self.t('count')}: 0")

        ttk.Label(summary, textvariable=self.total_expense_var).grid(row=0, column=0, sticky="w")
        ttk.Label(summary, textvariable=self.total_income_var).grid(row=0, column=1, sticky="w")
        ttk.Label(summary, textvariable=self.balance_var).grid(row=0, column=2, sticky="w")
        ttk.Label(summary, textvariable=self.count_var).grid(row=0, column=3, sticky="e")

    def build_record_table(self):
        table_frame = ttk.Frame(self.records_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=3, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("date", "type", "category", "account", "amount", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("date", text=self.t("date"))
        self.tree.heading("type", text=self.t("type"))
        self.tree.heading("category", text=self.t("category"))
        self.tree.heading("account", text=self.t("account"))
        self.tree.heading("amount", text=self.t("amount"))
        self.tree.heading("note", text=self.t("note"))

        self.tree.column("date", width=110, minwidth=90, anchor="w")
        self.tree.column("type", width=90, minwidth=80, anchor="w")
        self.tree.column("category", width=160, minwidth=120, anchor="w")
        self.tree.column("account", width=130, minwidth=100, anchor="w")
        self.tree.column("amount", width=120, minwidth=100, anchor="e")
        self.tree.column("note", width=340, minwidth=180, anchor="w")

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

        ttk.Button(actions, text=self.t("edit"), command=self.start_edit).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text=self.t("delete"), command=self.delete_selected).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text=self.t("export_csv"), command=self.export_csv).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text=self.t("import_csv"), command=self.import_csv).grid(row=0, column=3)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda event: self.start_edit())
        self.tree.bind("<Delete>", lambda event: self.delete_selected())

    def build_reports_tab(self):
        self.reports_tab.columnconfigure(0, weight=1)
        self.reports_tab.columnconfigure(1, weight=1)
        self.reports_tab.rowconfigure(2, weight=1)
        self.reports_tab.rowconfigure(3, weight=1)

        controls = ttk.Frame(self.reports_tab, padding=(10, 10, 10, 8))
        controls.grid(row=0, column=0, columnspan=2, sticky="ew")
        controls.columnconfigure(4, weight=1)

        self.report_month_var = tk.StringVar(value=CURRENT_MONTH)
        ttk.Label(controls, text=self.t("month")).grid(row=0, column=0, sticky="w")
        self.report_month_combo = ttk.Combobox(controls, textvariable=self.report_month_var, width=10)
        self.report_month_combo.grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Button(controls, text=self.t("refresh"), command=lambda: self.refresh_reports()).grid(
            row=0, column=2, sticky="w"
        )

        metrics = ttk.Frame(self.reports_tab, padding=(10, 0, 10, 8))
        metrics.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            metrics.columnconfigure(column, weight=1)

        self.report_income_var = tk.StringVar(value=f"{self.t('income')}: $0.00")
        self.report_expense_var = tk.StringVar(value=f"{self.t('expense')}: $0.00")
        self.report_balance_var = tk.StringVar(value=f"{self.t('balance')}: $0.00")
        self.report_top_category_var = tk.StringVar(value=f"{self.t('top_category')}: -")

        ttk.Label(metrics, textvariable=self.report_income_var).grid(row=0, column=0, sticky="w")
        ttk.Label(metrics, textvariable=self.report_expense_var).grid(row=0, column=1, sticky="w")
        ttk.Label(metrics, textvariable=self.report_balance_var).grid(row=0, column=2, sticky="w")
        ttk.Label(metrics, textvariable=self.report_top_category_var).grid(row=0, column=3, sticky="e")

        self.category_canvas = self.create_report_canvas()
        self.trend_canvas = self.create_report_canvas()
        self.account_canvas = self.create_report_canvas()
        self.budget_canvas = self.create_report_canvas()
        self.category_canvas.grid(row=2, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        self.trend_canvas.grid(row=2, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.account_canvas.grid(row=3, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        self.budget_canvas.grid(row=3, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.category_canvas.bind("<Configure>", lambda event: self.draw_category_chart())
        self.trend_canvas.bind("<Configure>", lambda event: self.draw_trend_chart())
        self.account_canvas.bind("<Configure>", lambda event: self.draw_account_chart())
        self.budget_canvas.bind("<Configure>", lambda event: self.draw_budget_progress_chart())

    def create_report_canvas(self):
        return tk.Canvas(
            self.reports_tab,
            background=self.palette["surface"],
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )

    def build_budgets_tab(self):
        self.budgets_tab.columnconfigure(0, weight=1)
        self.budgets_tab.rowconfigure(2, weight=1)

        editor = ttk.LabelFrame(self.budgets_tab, text=self.t("monthly_budget"), padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        for column in range(7):
            editor.columnconfigure(column, weight=1)

        self.budget_month_var = tk.StringVar(value=CURRENT_MONTH)
        self.budget_category_var = tk.StringVar()
        self.budget_amount_var = tk.StringVar()

        ttk.Label(editor, text=self.t("month")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.budget_month_combo = ttk.Combobox(editor, textvariable=self.budget_month_var, width=10)
        self.budget_month_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("category")).grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.budget_category_combo = ttk.Combobox(editor, textvariable=self.budget_category_var, width=18)
        self.budget_category_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("amount")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.budget_amount_var, width=12).grid(
            row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Button(editor, text=self.t("save_budget"), command=self.save_budget).grid(
            row=1, column=3, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Button(editor, text=self.t("clear"), command=self.clear_budget_form).grid(
            row=1, column=4, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Button(editor, text=self.t("delete"), command=self.delete_selected_budget).grid(
            row=1, column=5, sticky="ew", pady=(3, 0)
        )

        self.budget_summary_var = tk.StringVar(value="")
        ttk.Label(self.budgets_tab, textvariable=self.budget_summary_var, padding=(10, 0, 10, 8)).grid(
            row=1, column=0, sticky="ew"
        )

        table_frame = ttk.Frame(self.budgets_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("category", "budget", "spent", "remaining", "usage")
        self.budget_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.budget_tree.heading("category", text=self.t("category"))
        self.budget_tree.heading("budget", text=self.t("budget"))
        self.budget_tree.heading("spent", text=self.t("spent"))
        self.budget_tree.heading("remaining", text=self.t("remaining"))
        self.budget_tree.heading("usage", text=self.t("usage"))

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
        self.budget_category_combo.bind("<<ComboboxSelected>>", self.apply_default_budget)

    def build_categories_tab(self):
        self.categories_tab.columnconfigure(0, weight=1)
        self.categories_tab.rowconfigure(1, weight=1)

        editor = ttk.LabelFrame(self.categories_tab, text=self.t("category"), padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        for column in range(7):
            editor.columnconfigure(column, weight=1)

        self.category_name_var = tk.StringVar()
        self.category_color_var = tk.StringVar(value="#2f6f8f")
        self.category_default_budget_var = tk.StringVar()

        ttk.Label(editor, text=self.t("name")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.category_name_var, width=18).grid(
            row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Label(editor, text=self.t("color")).grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.category_color_combo = ttk.Combobox(
            editor,
            textvariable=self.category_color_var,
            values=(
                "#b42318",
                "#2f6f8f",
                "#9a6700",
                "#18794e",
                "#8250df",
                "#57606a",
                "#0969da",
                "#1f883d",
            ),
            width=10,
        )
        self.category_color_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("default_budget")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.category_default_budget_var, width=12).grid(
            row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        self.category_save_button = ttk.Button(editor, text=self.t("save_category"), command=self.save_category)
        self.category_save_button.grid(row=1, column=3, sticky="ew", padx=(0, 8), pady=(3, 0))

        ttk.Button(editor, text=self.t("clear"), command=self.clear_category_form).grid(
            row=1, column=4, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Button(editor, text=self.t("delete_unused"), command=self.delete_selected_category).grid(
            row=1, column=5, sticky="ew", pady=(3, 0)
        )

        table_frame = ttk.Frame(self.categories_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("name", "color", "default_budget", "records", "budgets")
        self.category_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.category_tree.heading("name", text=self.t("name"))
        self.category_tree.heading("color", text=self.t("color"))
        self.category_tree.heading("default_budget", text=self.t("default_budget"))
        self.category_tree.heading("records", text=self.t("records"))
        self.category_tree.heading("budgets", text=self.t("budgets"))

        self.category_tree.column("name", width=200, minwidth=140, anchor="w")
        self.category_tree.column("color", width=110, minwidth=90, anchor="w")
        self.category_tree.column("default_budget", width=140, minwidth=110, anchor="e")
        self.category_tree.column("records", width=90, minwidth=70, anchor="e")
        self.category_tree.column("budgets", width=90, minwidth=70, anchor="e")

        category_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.category_tree.yview)
        self.category_tree.configure(yscrollcommand=category_scroll.set)
        self.category_tree.grid(row=0, column=0, sticky="nsew")
        category_scroll.grid(row=0, column=1, sticky="ns")

        self.category_tree.bind("<<TreeviewSelect>>", self.on_category_select)
        self.category_tree.bind("<Delete>", lambda event: self.delete_selected_category())

    def build_recurring_tab(self):
        self.recurring_tab.columnconfigure(0, weight=1)
        self.recurring_tab.rowconfigure(1, weight=1)

        editor = ttk.LabelFrame(self.recurring_tab, text=self.t("recurring_rules"), padding=12)
        editor.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        for column in range(10):
            editor.columnconfigure(column, weight=1)

        self.recurring_name_var = tk.StringVar()
        self.recurring_day_var = tk.StringVar(value=str(date.today().day))
        self.recurring_type_var = tk.StringVar(value="expense")
        self.recurring_category_var = tk.StringVar()
        self.recurring_account_var = tk.StringVar(value=DEFAULT_ACCOUNT)
        self.recurring_amount_var = tk.StringVar()
        self.recurring_note_var = tk.StringVar()
        self.recurring_active_var = tk.BooleanVar(value=True)

        ttk.Label(editor, text=self.t("rule_name")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.recurring_name_var, width=18).grid(
            row=1, column=0, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Label(editor, text=self.t("day_of_month")).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Spinbox(editor, from_=1, to=31, textvariable=self.recurring_day_var, width=6).grid(
            row=1, column=1, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Label(editor, text=self.t("type")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Combobox(
            editor,
            textvariable=self.recurring_type_var,
            values=TYPE_OPTIONS,
            state="readonly",
            width=10,
        ).grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("category")).grid(row=0, column=3, sticky="w", padx=(0, 6))
        self.recurring_category_combo = ttk.Combobox(editor, textvariable=self.recurring_category_var, width=16)
        self.recurring_category_combo.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("account")).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.recurring_account_combo = ttk.Combobox(editor, textvariable=self.recurring_account_var, width=14)
        self.recurring_account_combo.grid(row=1, column=4, sticky="ew", padx=(0, 10), pady=(3, 0))

        ttk.Label(editor, text=self.t("amount")).grid(row=0, column=5, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.recurring_amount_var, width=12).grid(
            row=1, column=5, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Label(editor, text=self.t("note")).grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Entry(editor, textvariable=self.recurring_note_var).grid(
            row=1, column=6, sticky="ew", padx=(0, 10), pady=(3, 0)
        )

        ttk.Checkbutton(editor, text=self.t("active"), variable=self.recurring_active_var).grid(
            row=1, column=7, sticky="w", padx=(0, 10), pady=(3, 0)
        )

        self.recurring_save_button = ttk.Button(editor, text=self.t("save_rule"), command=self.save_recurring_rule)
        self.recurring_save_button.grid(row=1, column=8, sticky="ew", padx=(0, 8), pady=(3, 0))
        ttk.Button(editor, text=self.t("clear"), command=self.clear_recurring_form).grid(
            row=1, column=9, sticky="ew", pady=(3, 0)
        )

        table_frame = ttk.Frame(self.recurring_tab, padding=(10, 0, 10, 10))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("name", "day", "type", "category", "account", "amount", "status", "last", "note")
        self.recurring_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for column, label_key in (
            ("name", "rule_name"),
            ("day", "day_of_month"),
            ("type", "type"),
            ("category", "category"),
            ("account", "account"),
            ("amount", "amount"),
            ("status", "status"),
            ("last", "last_generated"),
            ("note", "note"),
        ):
            self.recurring_tree.heading(column, text=self.t(label_key))

        self.recurring_tree.column("name", width=160, minwidth=120, anchor="w")
        self.recurring_tree.column("day", width=90, minwidth=70, anchor="e")
        self.recurring_tree.column("type", width=90, minwidth=80, anchor="w")
        self.recurring_tree.column("category", width=140, minwidth=110, anchor="w")
        self.recurring_tree.column("account", width=120, minwidth=100, anchor="w")
        self.recurring_tree.column("amount", width=110, minwidth=90, anchor="e")
        self.recurring_tree.column("status", width=90, minwidth=80, anchor="w")
        self.recurring_tree.column("last", width=110, minwidth=90, anchor="w")
        self.recurring_tree.column("note", width=260, minwidth=160, anchor="w")

        recurring_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.recurring_tree.yview)
        self.recurring_tree.configure(yscrollcommand=recurring_scroll.set)
        self.recurring_tree.grid(row=0, column=0, sticky="nsew")
        recurring_scroll.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(table_frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions.columnconfigure(3, weight=1)
        ttk.Button(actions, text=self.t("edit"), command=self.start_recurring_edit).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text=self.t("delete"), command=self.delete_selected_recurring_rule).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(actions, text=self.t("generate_due_now"), command=self.generate_recurring_now).grid(
            row=0, column=2
        )

        self.recurring_tree.bind("<<TreeviewSelect>>", self.on_recurring_select)
        self.recurring_tree.bind("<Double-1>", lambda event: self.start_recurring_edit())
        self.recurring_tree.bind("<Delete>", lambda event: self.delete_selected_recurring_rule())

    def build_tools_tab(self):
        self.tools_tab.columnconfigure(0, weight=1)

        settings_frame = ttk.LabelFrame(self.tools_tab, text=self.t("settings"), padding=12)
        settings_frame.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)

        self.settings_language_var = tk.StringVar(value=self.language_code)
        self.currency_var = tk.StringVar(value=self.currency_code)
        self.theme_var = tk.StringVar(value=self.theme_name)

        ttk.Label(settings_frame, text=self.t("language")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        settings_language_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.settings_language_var,
            values=list(LANGUAGES.keys()),
            state="readonly",
            width=10,
        )
        settings_language_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        settings_language_combo.bind("<<ComboboxSelected>>", self.change_language_from_settings)

        ttk.Label(settings_frame, text=self.t("currency")).grid(row=0, column=2, sticky="w", padx=(0, 8))
        currency_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.currency_var,
            values=list(CURRENCY_OPTIONS.keys()),
            state="readonly",
            width=10,
        )
        currency_combo.grid(row=0, column=3, sticky="w")
        currency_combo.bind("<<ComboboxSelected>>", self.change_currency)

        ttk.Label(settings_frame, text=self.t("theme")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(12, 0))
        theme_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.theme_var,
            values=THEME_OPTIONS,
            state="readonly",
            width=10,
        )
        theme_combo.grid(row=1, column=1, sticky="w", padx=(0, 20), pady=(12, 0))
        theme_combo.bind("<<ComboboxSelected>>", self.change_theme)

        ttk.Label(settings_frame, text=self.t("password")).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(12, 0))
        self.password_status_var = tk.StringVar(
            value=self.t("password_enabled") if self.has_password() else self.t("password_not_enabled")
        )
        ttk.Label(settings_frame, textvariable=self.password_status_var).grid(
            row=1, column=3, sticky="w", pady=(12, 0)
        )
        ttk.Button(settings_frame, text=self.t("change_password"), command=self.change_password).grid(
            row=1, column=4, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        ttk.Button(settings_frame, text=self.t("remove_password"), command=self.remove_password).grid(
            row=1, column=5, sticky="w", padx=(8, 0), pady=(12, 0)
        )

        data_frame = ttk.LabelFrame(self.tools_tab, text=self.t("data"), padding=12)
        data_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        data_frame.columnconfigure(1, weight=1)

        self.db_path_var = tk.StringVar(value=str(get_db_path()))
        ttk.Label(data_frame, text=self.t("database")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(data_frame, textvariable=self.db_path_var).grid(row=0, column=1, sticky="ew")

        ttk.Button(data_frame, text=self.t("backup_database"), command=self.backup_data).grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Button(data_frame, text=self.t("restore_database"), command=self.restore_data).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        ttk.Button(data_frame, text=self.t("open_data_folder"), command=self.open_data_folder).grid(
            row=1, column=2, sticky="w", padx=(8, 0), pady=(12, 0)
        )

    def build_status_bar(self):
        self.status_var = tk.StringVar(value=self.t("ready"))
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(16, 6))
        status.grid(row=2, column=0, sticky="ew")

    def bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda event: self.save_current_tab())
        self.root.bind("<Escape>", lambda event: self.clear_current_tab())

    def set_status(self, message):
        self.status_var.set(message)

    def type_text(self, record_type):
        return self.t(record_type) if record_type in TYPE_OPTIONS else record_type

    def refresh_all(self, status_message=None):
        self.refresh_records(status_message)
        self.refresh_reports(update_status=False)
        self.refresh_budgets(update_status=False)
        self.refresh_categories(update_status=False)
        self.refresh_recurring(update_status=False)
        self.update_picker_options()

    def update_picker_options(self):
        categories = get_categories()
        accounts = get_accounts()
        months = get_months()
        if CURRENT_MONTH not in months:
            months = [CURRENT_MONTH] + months

        self.accounts = accounts
        self.category_combo.configure(values=categories)
        self.category_filter.configure(values=[""] + categories)
        self.account_combo.configure(values=accounts)
        self.account_filter.configure(values=[""] + accounts)
        self.budget_category_combo.configure(values=categories)
        self.recurring_category_combo.configure(values=categories)
        self.recurring_account_combo.configure(values=accounts)
        self.month_filter.configure(values=[""] + months)
        self.report_month_combo.configure(values=[""] + months)
        self.budget_month_combo.configure(values=months)

    def save_current_tab(self):
        current = self.notebook.select()
        if current == str(self.records_tab):
            self.save_record()
        elif current == str(self.budgets_tab):
            self.save_budget()
        elif current == str(self.categories_tab):
            self.save_category()
        elif current == str(self.recurring_tab):
            self.save_recurring_rule()
        else:
            self.set_status(self.t("nothing_to_save"))

    def clear_current_tab(self):
        current = self.notebook.select()
        if current == str(self.records_tab):
            self.clear_form()
        elif current == str(self.budgets_tab):
            self.clear_budget_form()
        elif current == str(self.categories_tab):
            self.clear_category_form()
        elif current == str(self.recurring_tab):
            self.clear_recurring_form()
        else:
            self.set_status(self.t("nothing_to_clear"))

    def filters(self):
        month = parse_month(self.month_filter_var.get())
        category = self.category_filter_var.get().strip() or None
        account = self.account_filter_var.get().strip() or None
        search = self.search_var.get().strip() or None
        return month, category, account, search

    def refresh_records(self, status_message=None):
        try:
            month, category, account, search = self.filters()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        self.records = load_records(month=month, category=category, account=account, search=search)
        self.populate_table()
        self.update_summary()
        self.update_picker_options()
        self.set_status(status_message or f"{self.t('count')}: {len(self.records)}")

    def populate_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for record in self.records:
            amount = self.money_text(record["amount_cents"])
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
                    self.type_text(record["type"]),
                    record["category"],
                    record.get("account") or DEFAULT_ACCOUNT,
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

        self.total_expense_var.set(f"{self.t('expense')}: {self.money_text(expense)}")
        self.total_income_var.set(f"{self.t('income')}: {self.money_text(income)}")
        self.balance_var.set(f"{self.t('balance')}: {self.money_text(balance)}")
        self.count_var.set(f"{self.t('count')}: {len(self.records)}")

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
        account = self.account_var.get().strip() or DEFAULT_ACCOUNT
        amount_cents = amount_to_cents(self.amount_var.get())
        note = self.note_var.get().strip()

        if record_type not in TYPE_OPTIONS:
            raise ValueError("Type must be income or expense.")
        if not category:
            raise ValueError("Category must be non-empty.")
        if not account:
            raise ValueError("Account must be non-empty.")

        return record_type, category, account, amount_cents, note, record_date

    def save_record(self):
        try:
            record_type, category, account, amount_cents, note, record_date = self.read_form()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        if self.editing_record_id is None:
            insert_record(record_type, category, amount_cents, note, record_date, account=account)
            self.clear_form(reset_status=False)
            self.refresh_all(self.t("record_added"))
            return

        updated = update_record(
            self.editing_record_id,
            record_type,
            category,
            amount_cents,
            note,
            record_date,
            account=account,
        )
        self.clear_form(reset_status=False)
        self.refresh_all(self.t("record_updated") if updated else "Record was not found.")

    def start_edit(self):
        record = self.selected_record()
        if not record:
            self.set_status("Select a record to edit.")
            return

        self.editing_record_id = record["id"]
        self.date_var.set(record["date"])
        self.type_var.set(record["type"])
        self.category_var.set(record["category"])
        self.account_var.set(record.get("account") or DEFAULT_ACCOUNT)
        self.amount_var.set(amount_entry_text(record["amount_cents"]))
        self.note_var.set(record["note"] or "")
        self.save_button.configure(text=self.t("update_record"))
        self.set_status(f"Editing record #{record['id']}.")
        self.notebook.select(self.records_tab)
        self.date_entry.focus_set()

    def clear_form(self, reset_status=True):
        self.editing_record_id = None
        self.date_var.set(date.today().isoformat())
        self.type_var.set("expense")
        self.category_var.set("")
        self.account_var.set(DEFAULT_ACCOUNT)
        self.amount_var.set("")
        self.note_var.set("")
        self.save_button.configure(text=self.t("add_record"))
        self.tree.selection_remove(self.tree.selection())
        if reset_status:
            self.set_status(self.t("form_cleared"))

    def delete_selected(self):
        record = self.selected_record()
        if not record:
            self.set_status("Select a record to delete.")
            return

        confirmed = messagebox.askyesno(
            "Delete record",
            f"Delete {record['category']} {self.money_text(record['amount_cents'])} on {record['date']}?",
        )
        if not confirmed:
            self.set_status("Delete cancelled.")
            return

        delete_record(record["id"])
        if self.editing_record_id == record["id"]:
            self.clear_form(reset_status=False)
        self.refresh_all(self.t("record_deleted"))

    def reset_filters(self):
        self.month_filter_var.set("")
        self.category_filter_var.set("")
        self.account_filter_var.set("")
        self.search_var.set("")
        self.refresh_records(self.t("filters_reset"))

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
            writer.writerow(["date", "type", "category", "account", "amount", "note"])
            for record in self.records:
                writer.writerow(
                    [
                        record["date"],
                        record["type"],
                        record["category"],
                        record.get("account") or DEFAULT_ACCOUNT,
                        amount_entry_text(record["amount_cents"]),
                        record["note"] or "",
                    ]
                )

        self.set_status(f"Exported {len(self.records)} record(s) to CSV.")

    def import_csv(self):
        path = filedialog.askopenfilename(
            title=self.t("import_csv"),
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            self.set_status(self.t("import_cancelled"))
            return

        try:
            headers = csv_headers(path)
            mapping = self.show_csv_mapping_dialog(headers)
            if mapping is None:
                self.set_status(self.t("import_cancelled"))
                return
            parsed_records = parse_csv_records(path, mapping=mapping)
            records, duplicates = split_new_and_duplicate_records(parsed_records, load_records())
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.t("import_failed"), str(exc))
            self.set_status(self.t("import_failed"))
            return

        if not records:
            messagebox.showinfo(
                self.t("import_preview"),
                self.t("import_summary", new_count=0, duplicate_count=len(duplicates)),
            )
            self.set_status(self.t("import_cancelled"))
            return

        confirmed = self.show_import_preview(records, duplicates)
        if not confirmed:
            self.set_status(self.t("import_cancelled"))
            return

        for record in records:
            insert_record(
                record["type"],
                record["category"],
                record["amount_cents"],
                record["note"],
                record["date"],
                account=record.get("account") or DEFAULT_ACCOUNT,
            )

        self.refresh_all(f"Imported {len(records)} record(s).")

    def read_csv_records(self, path):
        return parse_csv_records(path)

    def show_csv_mapping_dialog(self, headers):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("csv_mapping"))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        mapping = default_csv_mapping(headers)
        selected = {key: tk.StringVar(value=value or "") for key, value in mapping.items()}
        result = {"mapping": None}
        choices = [""] + headers

        ttk.Label(dialog, text=self.t("csv_mapping_help"), padding=(12, 10)).grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )

        fields = ("date", "type", "category", "account", "amount", "note")
        for row, field in enumerate(fields, start=1):
            label = self.t(field)
            if field in {"date", "type", "category", "amount"}:
                label = f"{label} *"
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=(12, 8), pady=4)
            ttk.Combobox(
                dialog,
                textvariable=selected[field],
                values=choices,
                state="readonly",
                width=28,
            ).grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=4)

        actions = ttk.Frame(dialog, padding=(12, 8, 12, 12))
        actions.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(0, weight=1)

        def accept():
            candidate = {field: selected[field].get() or None for field in fields}
            missing = [field for field in ("date", "type", "category", "amount") if not candidate[field]]
            if missing:
                messagebox.showerror(
                    self.t("csv_mapping"),
                    self.t("csv_missing_required", fields=", ".join(missing)),
                    parent=dialog,
                )
                return
            result["mapping"] = candidate
            dialog.destroy()

        ttk.Button(actions, text=self.t("confirm"), command=accept).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text=self.t("cancel"), command=dialog.destroy).grid(row=0, column=2)

        self.root.wait_window(dialog)
        return result["mapping"]

    def show_import_preview(self, records, duplicates):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("import_preview"))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("760x480")
        dialog.minsize(680, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        confirmed = {"value": False}

        summary = self.t(
            "import_summary",
            new_count=len(records),
            duplicate_count=len(duplicates),
        )
        ttk.Label(dialog, text=summary, padding=(12, 10)).grid(row=0, column=0, sticky="ew")

        preview_tabs = ttk.Notebook(dialog)
        preview_tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))

        new_frame = ttk.Frame(preview_tabs)
        duplicate_frame = ttk.Frame(preview_tabs)
        preview_tabs.add(new_frame, text=f"{self.t('new_records')} ({len(records)})")
        preview_tabs.add(duplicate_frame, text=f"{self.t('duplicates')} ({len(duplicates)})")

        self.build_preview_table(new_frame, records)
        self.build_preview_table(duplicate_frame, duplicates)

        actions = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        actions.grid(row=2, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        def accept():
            confirmed["value"] = True
            dialog.destroy()

        ttk.Button(actions, text=self.t("confirm"), command=accept).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text=self.t("cancel"), command=dialog.destroy).grid(row=0, column=2)

        self.root.wait_window(dialog)
        return confirmed["value"]

    def build_preview_table(self, parent, records):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        columns = ("date", "type", "category", "account", "amount", "note")
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        for column, label_key in (
            ("date", "date"),
            ("type", "type"),
            ("category", "category"),
            ("account", "account"),
            ("amount", "amount"),
            ("note", "note"),
        ):
            tree.heading(column, text=self.t(label_key))

        tree.column("date", width=100, anchor="w")
        tree.column("type", width=90, anchor="w")
        tree.column("category", width=140, anchor="w")
        tree.column("account", width=110, anchor="w")
        tree.column("amount", width=110, anchor="e")
        tree.column("note", width=220, anchor="w")

        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        for record in records[:200]:
            tree.insert(
                "",
                tk.END,
                values=(
                    record["date"],
                    self.type_text(record["type"]),
                    record["category"],
                    record.get("account") or DEFAULT_ACCOUNT,
                    self.money_text(record["amount_cents"]),
                    record["note"],
                ),
            )

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
        self.account_chart_data = load_account_spending(month=month)
        self.budget_progress_data = load_budget_progress(month or CURRENT_MONTH)

        self.report_income_var.set(f"{self.t('income')}: {self.money_text(income)}")
        self.report_expense_var.set(f"{self.t('expense')}: {self.money_text(expense)}")
        self.report_balance_var.set(f"{self.t('balance')}: {self.money_text(balance)}")

        if self.category_chart_data:
            top = self.category_chart_data[0]
            self.report_top_category_var.set(
                f"{self.t('top_category')}: {top['category']} ({self.money_text(top['spent_cents'])})"
            )
        else:
            self.report_top_category_var.set(f"{self.t('top_category')}: -")

        self.draw_category_chart()
        self.draw_trend_chart()
        self.draw_account_chart()
        self.draw_budget_progress_chart()
        self.update_picker_options()
        if update_status:
            self.set_status(self.t("reports_refreshed"))

    def draw_category_chart(self):
        canvas = self.category_canvas
        canvas.delete("all")
        canvas.configure(background=self.palette["surface"], highlightbackground=self.palette["border"])
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 260)
        left = 120
        right = 24
        top = 44
        row_height = 30

        canvas.create_text(
            16,
            16,
            anchor="w",
            text=self.t("category_spending"),
            font=("Segoe UI", 11, "bold"),
            fill=self.palette["text"],
        )

        rows = self.category_chart_data[:8]
        if not rows:
            canvas.create_text(width / 2, height / 2, text=self.t("no_expense_data"), fill=self.palette["muted"])
            return

        max_value = max(row["spent_cents"] or 0 for row in rows) or 1
        bar_width = max(width - left - right, 120)
        colors = ["#b42318", "#2f6f8f", "#9a6700", "#18794e", "#8250df", "#57606a"]

        for index, row in enumerate(rows):
            y = top + index * row_height
            value = int(row["spent_cents"] or 0)
            length = max(int(bar_width * value / max_value), 2)
            color = row.get("color") or colors[index % len(colors)]
            canvas.create_text(16, y + 10, anchor="w", text=row["category"], fill=self.palette["text"])
            canvas.create_rectangle(left, y, left + length, y + 18, fill=color, outline="")
            canvas.create_text(left + length + 8, y + 9, anchor="w", text=self.money_text(value), fill=self.palette["muted"])

    def draw_trend_chart(self):
        canvas = self.trend_canvas
        canvas.delete("all")
        canvas.configure(background=self.palette["surface"], highlightbackground=self.palette["border"])
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 260)
        left = 44
        right = 20
        top = 44
        bottom = 40

        canvas.create_text(16, 16, anchor="w", text=self.t("trend"), font=("Segoe UI", 11, "bold"), fill=self.palette["text"])
        rows = self.monthly_chart_data
        if not rows:
            canvas.create_text(width / 2, height / 2, text=self.t("no_monthly_data"), fill=self.palette["muted"])
            return

        max_value = max(
            max(int(row["income_cents"] or 0), int(row["expense_cents"] or 0))
            for row in rows
        ) or 1
        chart_width = max(width - left - right, 120)
        chart_height = max(height - top - bottom, 120)
        slot = chart_width / max(len(rows), 1)

        canvas.create_line(left, top + chart_height, width - right, top + chart_height, fill=self.palette["border"])
        canvas.create_text(left, top - 8, anchor="w", text=self.money_text(max_value), fill=self.palette["muted"])
        canvas.create_text(width - right - 140, 18, anchor="w", text=self.t("income"), fill=self.palette["income"])
        canvas.create_rectangle(width - right - 160, 12, width - right - 146, 24, fill=self.palette["income"], outline="")
        canvas.create_text(width - right - 68, 18, anchor="w", text=self.t("expense"), fill=self.palette["expense"])
        canvas.create_rectangle(width - right - 88, 12, width - right - 74, 24, fill=self.palette["expense"], outline="")

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
                fill=self.palette["income"],
                outline="",
            )
            canvas.create_rectangle(
                x + bar_w + 4,
                top + chart_height - expense_h,
                x + bar_w * 2 + 4,
                top + chart_height,
                fill=self.palette["expense"],
                outline="",
            )
            canvas.create_text(
                x + bar_w,
                top + chart_height + 14,
                text=row["month"][5:],
                fill=self.palette["muted"],
            )

    def draw_account_chart(self):
        canvas = self.account_canvas
        canvas.delete("all")
        canvas.configure(background=self.palette["surface"], highlightbackground=self.palette["border"])
        width = max(canvas.winfo_width(), 360)
        left = 120
        right = 24
        top = 44
        row_height = 30

        canvas.create_text(
            16,
            16,
            anchor="w",
            text=self.t("account_spending"),
            font=("Segoe UI", 11, "bold"),
            fill=self.palette["text"],
        )
        rows = self.account_chart_data[:8]
        if not rows:
            canvas.create_text(width / 2, 130, text=self.t("no_account_data"), fill=self.palette["muted"])
            return

        max_value = max(int(row["spent_cents"] or 0) for row in rows) or 1
        bar_width = max(width - left - right, 120)
        for index, row in enumerate(rows):
            y = top + index * row_height
            value = int(row["spent_cents"] or 0)
            length = max(int(bar_width * value / max_value), 2)
            canvas.create_text(16, y + 10, anchor="w", text=row["account"], fill=self.palette["text"])
            canvas.create_rectangle(left, y, left + length, y + 18, fill=self.palette["accent"], outline="")
            canvas.create_text(left + length + 8, y + 9, anchor="w", text=self.money_text(value), fill=self.palette["muted"])

    def draw_budget_progress_chart(self):
        canvas = self.budget_canvas
        canvas.delete("all")
        canvas.configure(background=self.palette["surface"], highlightbackground=self.palette["border"])
        width = max(canvas.winfo_width(), 360)
        left = 120
        right = 72
        top = 44
        row_height = 30

        canvas.create_text(
            16,
            16,
            anchor="w",
            text=self.t("budget_progress"),
            font=("Segoe UI", 11, "bold"),
            fill=self.palette["text"],
        )
        rows = self.budget_progress_data[:8]
        if not rows:
            canvas.create_text(width / 2, 130, text=self.t("no_budget_data"), fill=self.palette["muted"])
            return

        bar_width = max(width - left - right, 120)
        for index, row in enumerate(rows):
            y = top + index * row_height
            budget = int(row["budget_cents"] or 0)
            spent = int(row["spent_cents"] or 0)
            usage = spent / budget if budget else 0
            length = max(min(int(bar_width * usage), bar_width), 2 if spent else 0)
            color = self.palette["expense"] if usage > 1 else self.palette["warning"] if usage >= 0.8 else self.palette["income"]
            canvas.create_text(16, y + 10, anchor="w", text=row["category"], fill=self.palette["text"])
            canvas.create_rectangle(left, y, left + bar_width, y + 18, fill=self.palette["background"], outline=self.palette["border"])
            if length:
                canvas.create_rectangle(left, y, left + length, y + 18, fill=color, outline="")
            canvas.create_text(
                left + bar_width + 8,
                y + 9,
                anchor="w",
                text=f"{usage * 100:.0f}%",
                fill=self.palette["muted"],
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

    def apply_default_budget(self, event=None):
        if self.budget_amount_var.get().strip():
            return

        category_name = self.budget_category_var.get().strip()
        category = next(
            (item for item in self.categories if item["name"] == category_name),
            None,
        )
        if category and category["default_budget_cents"]:
            self.budget_amount_var.set(amount_entry_text(category["default_budget_cents"]))

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
                    self.money_text(budget["amount_cents"]),
                    self.money_text(spent),
                    self.money_text(remaining),
                    f"{usage * 100:.0f}%",
                ),
                tags=(tag,),
            )

        if self.budgets:
            self.budget_summary_var.set(
                f"{month}: {self.t('spent')} {self.money_text(total_spent)} / "
                f"{self.t('budget')} {self.money_text(total_budget)}; {over_count} over."
            )
        else:
            self.budget_summary_var.set(f"{self.t('budgets')}: 0 ({month})")

        self.update_picker_options()
        if update_status:
            self.set_status(self.t("budgets_refreshed"))

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
        self.set_status(self.t("budget_saved"))

    def clear_budget_form(self, reset_status=True):
        self.budget_category_var.set("")
        self.budget_amount_var.set("")
        self.budget_tree.selection_remove(self.budget_tree.selection())
        if reset_status:
            self.set_status(self.t("form_cleared"))

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
        self.set_status(self.t("budget_deleted"))

    def refresh_categories(self, update_status=True):
        self.categories = load_categories()

        for item in self.category_tree.get_children():
            self.category_tree.delete(item)

        for category in self.categories:
            self.category_tree.insert(
                "",
                tk.END,
                iid=str(category["id"]),
                values=(
                    category["name"],
                    category["color"],
                    self.money_text(category["default_budget_cents"]),
                    category["record_count"],
                    category["budget_count"],
                ),
            )

        self.update_picker_options()
        if update_status:
            self.set_status(self.t("categories_refreshed"))

    def selected_category(self):
        selected = self.category_tree.selection()
        if not selected:
            return None

        category_id = int(selected[0])
        return next((category for category in self.categories if category["id"] == category_id), None)

    def on_category_select(self, event=None):
        category = self.selected_category()
        if not category:
            return

        self.editing_category_id = category["id"]
        self.category_name_var.set(category["name"])
        self.category_color_var.set(category["color"])
        if category["default_budget_cents"]:
            self.category_default_budget_var.set(amount_entry_text(category["default_budget_cents"]))
        else:
            self.category_default_budget_var.set("")
        self.category_save_button.configure(text=self.t("update_category"))
        self.set_status(f"Selected category #{category['id']}.")

    def read_category_form(self):
        name = self.category_name_var.get().strip()
        if not name:
            raise ValueError("Category name must be non-empty.")

        color = self.category_color_var.get().strip() or "#2f6f8f"
        if not color.startswith("#") or len(color) != 7:
            raise ValueError("Color must use hex format like #2f6f8f.")

        raw_default = self.category_default_budget_var.get().strip()
        default_budget_cents = amount_to_cents(raw_default) if raw_default else 0
        return name, color, default_budget_cents

    def save_category(self):
        try:
            name, color, default_budget_cents = self.read_category_form()
            save_category(
                name,
                color=color,
                default_budget_cents=default_budget_cents,
                category_id=self.editing_category_id,
            )
        except ValueError as exc:
            self.set_status(str(exc))
            return

        self.clear_category_form(reset_status=False)
        self.refresh_all(self.t("category_saved"))

    def clear_category_form(self, reset_status=True):
        self.editing_category_id = None
        self.category_name_var.set("")
        self.category_color_var.set("#2f6f8f")
        self.category_default_budget_var.set("")
        self.category_save_button.configure(text=self.t("save_category"))
        self.category_tree.selection_remove(self.category_tree.selection())
        if reset_status:
            self.set_status(self.t("form_cleared"))

    def delete_selected_category(self):
        category = self.selected_category()
        if not category:
            self.set_status("Select a category to delete.")
            return

        confirmed = messagebox.askyesno(
            "Delete category",
            f"Delete unused category {category['name']}?",
        )
        if not confirmed:
            self.set_status("Delete cancelled.")
            return

        try:
            delete_category(category["id"])
        except ValueError as exc:
            self.set_status(str(exc))
            return

        self.clear_category_form(reset_status=False)
        self.refresh_all(self.t("category_deleted"))

    def refresh_recurring(self, update_status=True):
        self.recurring_rules = load_recurring_rules()

        for item in self.recurring_tree.get_children():
            self.recurring_tree.delete(item)

        for rule in self.recurring_rules:
            status = self.t("active") if rule["active"] else self.t("inactive")
            self.recurring_tree.insert(
                "",
                tk.END,
                iid=str(rule["id"]),
                values=(
                    rule["name"],
                    rule["day_of_month"],
                    self.type_text(rule["type"]),
                    rule["category"],
                    rule["account"],
                    self.money_text(rule["amount_cents"]),
                    status,
                    rule["last_generated_month"] or "-",
                    rule["note"] or "",
                ),
            )

        self.update_picker_options()
        if update_status:
            self.set_status(self.t("recurring_refreshed"))

    def selected_recurring_rule(self):
        selected = self.recurring_tree.selection()
        if not selected:
            return None

        rule_id = int(selected[0])
        return next((rule for rule in self.recurring_rules if rule["id"] == rule_id), None)

    def on_recurring_select(self, event=None):
        rule = self.selected_recurring_rule()
        if rule:
            self.set_status(f"Selected recurring rule #{rule['id']}.")

    def read_recurring_form(self):
        name = self.recurring_name_var.get().strip()
        record_type = self.recurring_type_var.get()
        category = self.recurring_category_var.get().strip()
        account = self.recurring_account_var.get().strip() or DEFAULT_ACCOUNT
        amount_cents = amount_to_cents(self.recurring_amount_var.get())
        note = self.recurring_note_var.get().strip()

        if not name:
            raise ValueError("Rule name must be non-empty.")
        if record_type not in TYPE_OPTIONS:
            raise ValueError("Type must be income or expense.")
        if not category:
            raise ValueError("Category must be non-empty.")

        try:
            day_of_month = int(self.recurring_day_var.get())
        except ValueError as exc:
            raise ValueError("Day of month must be a number.") from exc
        if not 1 <= day_of_month <= 31:
            raise ValueError("Day of month must be between 1 and 31.")

        return name, record_type, category, account, amount_cents, note, day_of_month, self.recurring_active_var.get()

    def save_recurring_rule(self):
        try:
            name, record_type, category, account, amount_cents, note, day_of_month, active = self.read_recurring_form()
        except ValueError as exc:
            self.set_status(str(exc))
            return

        upsert_recurring_rule(
            name,
            record_type,
            category,
            account,
            amount_cents,
            note,
            day_of_month,
            active=active,
            rule_id=self.editing_recurring_id,
        )
        self.clear_recurring_form(reset_status=False)
        self.refresh_all(self.t("recurring_saved"))

    def start_recurring_edit(self):
        rule = self.selected_recurring_rule()
        if not rule:
            self.set_status("Select a recurring rule to edit.")
            return

        self.editing_recurring_id = rule["id"]
        self.recurring_name_var.set(rule["name"])
        self.recurring_day_var.set(str(rule["day_of_month"]))
        self.recurring_type_var.set(rule["type"])
        self.recurring_category_var.set(rule["category"])
        self.recurring_account_var.set(rule["account"])
        self.recurring_amount_var.set(amount_entry_text(rule["amount_cents"]))
        self.recurring_note_var.set(rule["note"] or "")
        self.recurring_active_var.set(bool(rule["active"]))
        self.recurring_save_button.configure(text=self.t("update_rule"))
        self.notebook.select(self.recurring_tab)
        self.set_status(f"Editing recurring rule #{rule['id']}.")

    def clear_recurring_form(self, reset_status=True):
        self.editing_recurring_id = None
        self.recurring_name_var.set("")
        self.recurring_day_var.set(str(date.today().day))
        self.recurring_type_var.set("expense")
        self.recurring_category_var.set("")
        self.recurring_account_var.set(DEFAULT_ACCOUNT)
        self.recurring_amount_var.set("")
        self.recurring_note_var.set("")
        self.recurring_active_var.set(True)
        self.recurring_save_button.configure(text=self.t("save_rule"))
        self.recurring_tree.selection_remove(self.recurring_tree.selection())
        if reset_status:
            self.set_status(self.t("form_cleared"))

    def delete_selected_recurring_rule(self):
        rule = self.selected_recurring_rule()
        if not rule:
            self.set_status("Select a recurring rule to delete.")
            return

        confirmed = messagebox.askyesno(
            "Delete recurring rule",
            f"Delete recurring rule {rule['name']}?",
        )
        if not confirmed:
            self.set_status("Delete cancelled.")
            return

        delete_recurring_rule(rule["id"])
        self.clear_recurring_form(reset_status=False)
        self.refresh_all(self.t("recurring_deleted"))

    def generate_recurring_now(self):
        generated = generate_due_recurring_records()
        self.refresh_all(
            self.t("recurring_generated", count=generated) if generated else self.t("no_recurring_due")
        )

    def verify_current_password(self):
        digest = get_setting("password_hash")
        salt = get_setting("password_salt")
        if not digest or not salt:
            return True

        current = simpledialog.askstring(
            self.t("current_password"),
            self.t("password_prompt"),
            show="*",
            parent=self.root,
        )
        if current is None:
            return False
        if verify_password(current, salt, digest):
            return True

        messagebox.showerror(self.t("password"), self.t("invalid_password"), parent=self.root)
        return False

    def change_password(self):
        if not self.verify_current_password():
            self.set_status(self.t("password_unchanged"))
            return

        new_password = simpledialog.askstring(
            self.t("new_password"),
            self.t("new_password"),
            show="*",
            parent=self.root,
        )
        if not new_password:
            self.set_status(self.t("password_unchanged"))
            return
        confirm = simpledialog.askstring(
            self.t("confirm_password"),
            self.t("confirm_password"),
            show="*",
            parent=self.root,
        )
        if new_password != confirm:
            messagebox.showerror(self.t("password"), self.t("password_mismatch"), parent=self.root)
            self.set_status(self.t("password_unchanged"))
            return

        salt, digest = hash_password(new_password)
        set_setting("password_salt", salt)
        set_setting("password_hash", digest)
        if hasattr(self, "password_status_var"):
            self.password_status_var.set(self.t("password_enabled"))
        self.set_status(self.t("password_saved"))

    def remove_password(self):
        if not self.has_password():
            self.set_status(self.t("password_not_enabled"))
            return
        if not self.verify_current_password():
            self.set_status(self.t("password_unchanged"))
            return

        set_setting("password_salt", "")
        set_setting("password_hash", "")
        if hasattr(self, "password_status_var"):
            self.password_status_var.set(self.t("password_not_enabled"))
        self.set_status(self.t("password_removed"))

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
