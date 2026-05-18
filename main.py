import tkinter as tk

from app import ExpenseTrackerApp


def main():
    root = tk.Tk()
    ExpenseTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
