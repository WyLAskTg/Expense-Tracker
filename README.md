# Personal Expense Tracker

A desktop expense tracker built with Python, Tkinter, and SQLite.

## Features

- Add income and expense records
- Store date, type, category, amount, and note
- Edit and delete existing records
- Filter records by month, category, and search text
- Display income, expense, balance, and record count summaries
- View reports with category spending and 12-month trend charts
- Set monthly budgets by category and compare budget vs. actual spending
- Manage categories with colors and default monthly budgets
- Export the current record view to CSV
- Import records from CSV with preview and duplicate detection
- Switch the app language between English, Chinese, French, and Japanese
- Choose a display currency for all money amounts
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

- `Records`: Add, edit, delete, filter, and export transactions.
- `Reports`: Review spending by category and compare income vs. expense over time.
- `Budgets`: Set monthly category budgets and track remaining budget.
- `Categories`: Add, rename, color-code, and remove unused categories.
- `Tools`: Change settings, back up, restore, or open the local data folder.

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
date,type,category,amount,note
```

The `note` column is optional. Dates must use `YYYY-MM-DD`, and `type` must be `income` or `expense`.

Before importing, the app previews new records and skips duplicate records that match an existing or already-previewed record by date, type, category, and amount.

## Tests

Run the local test suite with:

```bash
py -3 -m unittest discover -s tests
```

## Automated Builds

GitHub Actions builds a Windows executable and an Inno Setup installer on pushes to `main`, pull requests, and manual workflow runs. Tag a commit with a version like `v26.5.2` to create a GitHub Release with both assets.
