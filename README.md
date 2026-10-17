# Expense Tracker System — MCA Major Project

A web-based personal finance tracker built with Python, Flask, and SQLite.

## Features
- Registration and login with password hashing
- Per-user transaction privacy
- Add, view, edit, and delete income/expense transactions
- Default and custom categories
- Monthly dashboard and category breakdown
- Overall and category-specific monthly budgets
- Monthly report and CSV export
- SQLite foreign keys, constraints, and indexes

## Requirements
- Python 3.10 or newer
- pip
- A modern browser

## Run on Windows
1. Extract the ZIP and open the `expense_tracker_mca` folder in VS Code.
2. Open Terminal in that folder.
3. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt:
   ```bat
   .venv\Scripts\activate.bat
   ```
4. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
5. Start the app:
   ```bash
   python app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.
7. Register a new account and start recording sample transactions.

The SQLite database `expense_tracker.db` is created automatically on first run.

## Run on macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## Demo walkthrough
1. Register an account.
2. Add Income: Salary, amount 25000, choose today's date.
3. Add Expense: Food, amount 1200, choose today's date.
4. Open Dashboard and verify income, expenses, and balance.
5. Add a monthly budget (for example 10000 INR).
6. Open Reports and download the CSV file.

Expected dashboard totals for those two entries: income ₹25,000.00; expenses ₹1,200.00; balance ₹23,800.00, assuming no other transactions in the selected month.

## Project structure
```text
expense_tracker_mca/
├── app.py
├── requirements.txt
├── README.md
├── expense_tracker.db        # created on first run
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── transactions.html
│   ├── transaction_form.html
│   ├── categories.html
│   ├── budgets.html
│   └── reports.html
├── static/style.css
└── tests/test_app.py
```

## Notes for academic use
- Change `SECRET_KEY` to a long random environment variable before deployment.
- Flask's debug mode is for local development only; do not enable it on a public server.
- SQLite is appropriate for a small academic demo. MySQL can be considered as a future enhancement.
- This is an educational project, not financial advice or a production banking application.
