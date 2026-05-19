# Personal Expense Tracker

A desktop expense tracker built with Python, Tkinter, and SQLite.

## Features

- Add income and expense records
- Store date, type, category, amount, note, tags, and receipt attachments
- Track accounts or payment methods for each record
- Edit and delete existing records
- Split one transaction into multiple category lines
- Use keyword rules to auto-fill category, account, and tags while recording expenses
- Filter records by month, category, account, type, tag, date range, amount range, and search text
- Browse large record sets with paged results
- Display income, expense, balance, and record count summaries
- Review a dashboard with this-month metrics, budget alerts, account balances, recent records, and upcoming recurring rules
- View reports with category spending, account spending, budget progress, and 12-month trend charts
- Hover and click report charts to inspect values and drill into matching filtered records
- Export reports to Excel or PDF
- Set monthly budgets by category, optional rollover, and annual spending targets
- Manage categories with colors and default monthly budgets
- Manage account balances, account types, icons, archived accounts, and transfers without counting them as income or expense
- Create recurring rules for daily, weekly, monthly, or yearly bills and income
- Use a quick-add dialog for fast transaction entry
- Export the current record view to CSV
- Import records from CSV with field mapping, reusable templates, preview, and duplicate detection
- Undo deleted records, deleted transfers, and recent CSV imports
- Switch the app language between English, Chinese, French, and Japanese
- Choose a display currency for all money amounts
- Switch between light and dark themes
- Add an optional password lock and encrypted-at-rest local database vault
- Check GitHub Releases for app updates from inside the app and open the installer download
- Create an automatic daily database backup, optionally copied to a folder you choose
- Create integrity-checked ZIP backups and restore from ZIP backups
- Run data quality tools for duplicate checks, tag cleanup, category/account merging, and activity review
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

- `Dashboard`: See this-month totals, budget alerts, net worth, account balances, recent records, and upcoming recurring rules.
- `Records`: Add, edit, split, delete, filter, import, export, attach receipts, tag, and undo transactions with account tracking.
- `Reports`: Review spending by category/account, budget progress, and income vs. expense over time, with chart hover, drill-down, PDF export, and Excel export.
- `Budgets`: Set monthly category budgets, rollover behavior, annual targets, and track remaining budget.
- `Categories`: Add, rename, color-code, and remove unused categories.
- `Accounts`: Set opening balances, account types, icons, sort order, archived state, and transfers.
- `Recurring`: Manage daily, weekly, monthly, or yearly recurring income and bills.
- `Tools`: Change language, currency, theme, password, data encryption, update checks, backups, restores, backup folder, auto-classification rules, activity history, data quality tools, or open the local data folder.

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
date,type,category,account,tags,amount,attachment_path,note
```

The `account`, `tags`, `attachment_path`, and `note` columns are optional. Dates must use `YYYY-MM-DD`, and `type` must be `income` or `expense`.
If your CSV uses different header names, the import dialog lets you map columns and save reusable templates before previewing records.

Before importing, the app previews new records and skips duplicate records that match an existing or already-previewed record by date, type, category, account, and amount.

## Tests

Run the local test suite with:

```bash
py -3 -m unittest discover -s tests
```

## Automated Builds

GitHub Actions builds a Windows executable and an Inno Setup installer on pushes to `main`, pull requests, and manual workflow runs. Tag a commit with a version like `v26.5.4` to create a GitHub Release with both assets.
