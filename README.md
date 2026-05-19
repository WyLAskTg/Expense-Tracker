# Personal Expense Tracker

A desktop expense tracker built with Python, Tkinter, and SQLite.

## Features

- Add income and expense records
- Store date, type, category, amount, and note
- Track accounts or payment methods for each record
- Edit and delete existing records
- Filter records by month, category, account, and search text
- Display income, expense, balance, and record count summaries
- Review a dashboard with this-month metrics, account balances, recent records, and upcoming recurring rules
- View reports with category spending, account spending, budget progress, and 12-month trend charts
- Click report charts to drill into the matching filtered records
- Set monthly budgets by category and compare budget vs. actual spending
- Manage categories with colors and default monthly budgets
- Manage account balances and transfer money between accounts without counting it as income or expense
- Create recurring rules for daily, weekly, monthly, or yearly bills and income
- Export the current record view to CSV
- Import records from CSV with field mapping, preview, and duplicate detection
- Undo deleted records, deleted transfers, and recent CSV imports
- Switch the app language between English, Chinese, French, and Japanese
- Choose a display currency for all money amounts
- Switch between light and dark themes
- Add an optional password lock and encrypted-at-rest local database vault
- Check GitHub Releases for app updates from inside the app
- Create an automatic daily database backup
- Back up and restore the local SQLite database
- Persist data with SQLite

## Tech Stack

- Python
- Tkinter / ttk
- SQLite

## How to Run

1. Make sure Python is installed.
2. Open this project folder in a terminal.
3. Run the app:

```bash
py -3 main.py
```

On systems where `python` is configured correctly, this also works:

```bash
python main.py
```

## Data Storage

The app stores records in `expense_tracker.db`. On Windows, new app data is saved under:

```text
%LOCALAPPDATA%\PersonalExpenseTracker\expense_tracker.db
```

If an older project-local `expense_tracker.db` exists, the app copies it into the app data folder the first time it starts.

## App Tabs

- `Dashboard`: See this-month totals, net worth, account balances, recent records, and upcoming recurring rules.
- `Records`: Add, edit, delete, filter, import, export, and undo transactions with account tracking.
- `Reports`: Review spending by category/account, budget progress, and income vs. expense over time, with chart drill-down.
- `Budgets`: Set monthly category budgets and track remaining budget.
- `Categories`: Add, rename, color-code, and remove unused categories.
- `Accounts`: Set opening balances and record transfers between accounts.
- `Recurring`: Manage daily, weekly, monthly, or yearly recurring income and bills.
- `Tools`: Change language, currency, theme, password, data encryption, update checks, backups, restores, or open the local data folder.

## Data Encryption

The app can encrypt the local SQLite database when it closes. Enable a password first, then use `Tools` > `Enable Encryption`.
When encryption is enabled, the app writes an encrypted vault next to the local database and removes the plaintext database on close.

## App Icon

The source icon image lives at:

```text
assets/icon-source.jpg
```

The Windows icon used by Tkinter, PyInstaller, and the installer lives at:

```text
assets/app.ico
```

## CSV Import

CSV imports require a header row with these columns:

```text
date,type,category,account,amount,note
```

The `account` and `note` columns are optional. Dates must use `YYYY-MM-DD`, and `type` must be `income` or `expense`.
If your CSV uses different header names, the import dialog lets you map columns before previewing records.

Before importing, the app previews new records and skips duplicate records that match an existing or already-previewed record by date, type, category, account, and amount.

## Tests

Run the local test suite with:

```bash
py -3 -m unittest discover -s tests
```

## Automated Builds

GitHub Actions builds a Windows executable and an Inno Setup installer on pushes to `main`, pull requests, and manual workflow runs. Tag a commit with a version like `v26.5.3.1` to create a GitHub Release with both assets.
