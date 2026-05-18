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
- Export the current record view to CSV
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
- `Tools`: Back up, restore, or open the local data folder.
