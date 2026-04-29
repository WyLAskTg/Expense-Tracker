# Personal Expense Tracker
A desktop expense tracker built with Python, Tkinter, and SQLite.

This project allows users to add, view, and delete expense records through a graphical user interface.  
It stores data persistently using SQLite, so records are automatically loaded when the program starts.

## Features
- Add records with:
  - type
  - category
  - amount
  - note
- Validate user input before submission
- Display records in a list inside the GUI
- Delete selected records
- Save records in a SQLite database
- Automatically load existing records when the program starts

## Tech Stack
- Python
- Tkinter
- SQLite

## How to Run
1. Make sure Python is installed on your computer.
2. Clone this repository or download the project files.
3. Open the project folder in VS Code or another editor.
4. Run the main Python file:

```bash
python gui.py