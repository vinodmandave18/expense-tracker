import os
import sqlite3
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "expense_tracker.db")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")
app.config["DATABASE"] = DATABASE

DEFAULT_CATEGORIES = [
    ("Salary", "Income"), ("Freelance", "Income"), ("Other Income", "Income"),
    ("Food", "Expense"), ("Travel", "Expense"), ("Rent", "Expense"),
    ("Education", "Expense"), ("Shopping", "Expense"), ("Bills", "Expense"),
    ("Health", "Expense"), ("Entertainment", "Expense"), ("Other Expense", "Expense")
]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('Income','Expense')),
        UNIQUE(user_id, name, kind),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('Income','Expense')),
        amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
        transaction_date TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE RESTRICT
    );
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER,
        month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
        year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 2100),
        amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE,
        UNIQUE(user_id, category_id, month, year)
    );
    CREATE INDEX IF NOT EXISTS idx_transactions_user_date
        ON transactions(user_id, transaction_date);
    CREATE INDEX IF NOT EXISTS idx_transactions_user_category
        ON transactions(user_id, category_id);
    """)
    db.commit()
    db.close()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def money_to_paise(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError("Enter a valid amount.")
    if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000000"):
        raise ValueError("Amount must be greater than zero and within the allowed limit.")
    return int((amount * 100).quantize(Decimal("1")))

def money(paise):
    return f"₹{(int(paise or 0) / 100):,.2f}"

@app.template_filter("inr")
def inr_filter(paise):
    return money(paise)

def seed_categories(db, user_id):
    db.executemany(
        "INSERT OR IGNORE INTO categories(user_id,name,kind) VALUES(?,?,?)",
        [(user_id, name, kind) for name, kind in DEFAULT_CATEGORIES]
    )

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email, and a password of at least 8 characters.", "danger")
            return render_template("register.html")
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                (name, email, generate_password_hash(password))
            )
            seed_categories(db, cur.lastrowid)
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash("An account with that email already exists.", "danger")
            return render_template("register.html")
        session.clear()
        session["user_id"] = cur.lastrowid
        session["user_name"] = name
        flash("Account created. Welcome!", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    if len(month) != 7 or month[4:5] != "-":
        month = date.today().strftime("%Y-%m")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = date.today().strftime("%Y-%m")
    start = month + "-01"
    end = (date(int(month[:4]) + (int(month[5:]) == 12), (int(month[5:]) % 12) + 1, 1)).isoformat()
    totals = db.execute("""
        SELECT kind, COALESCE(SUM(amount_paise),0) total
        FROM transactions
        WHERE user_id=? AND transaction_date>=? AND transaction_date<?
        GROUP BY kind
    """, (uid, start, end)).fetchall()
    totals_map = {r["kind"]: r["total"] for r in totals}
    income = totals_map.get("Income", 0)
    expense = totals_map.get("Expense", 0)
    recent = db.execute("""
        SELECT t.*, c.name category_name FROM transactions t
        JOIN categories c ON c.id=t.category_id
        WHERE t.user_id=? ORDER BY t.transaction_date DESC, t.id DESC LIMIT 8
    """, (uid,)).fetchall()
    category_rows = db.execute("""
        SELECT c.name, SUM(t.amount_paise) total
        FROM transactions t JOIN categories c ON c.id=t.category_id
        WHERE t.user_id=? AND t.kind='Expense'
          AND t.transaction_date>=? AND t.transaction_date<?
        GROUP BY c.id, c.name ORDER BY total DESC
    """, (uid, start, end)).fetchall()
    budget_rows = db.execute("""
        SELECT b.*, c.name category_name FROM budgets b
        LEFT JOIN categories c ON c.id=b.category_id
        WHERE b.user_id=? AND b.month=? AND b.year=?
    """, (uid, int(month[5:]), int(month[:4]))).fetchall()
    overall_budget = sum(r["amount_paise"] for r in budget_rows if r["category_id"] is None)
    return render_template("dashboard.html", month=month, income=income, expense=expense,
        balance=income-expense, recent=recent, category_rows=category_rows,
        budget_rows=budget_rows, overall_budget=overall_budget)

@app.route("/transactions")
@login_required
def transactions():
    db = get_db()
    uid = session["user_id"]
    kind = request.args.get("kind", "")
    month = request.args.get("month", "")
    query = """SELECT t.*, c.name category_name FROM transactions t
               JOIN categories c ON c.id=t.category_id WHERE t.user_id=?"""
    params = [uid]
    if kind in ("Income", "Expense"):
        query += " AND t.kind=?"
        params.append(kind)
    if month:
        try:
            datetime.strptime(month, "%Y-%m")
            query += " AND substr(t.transaction_date,1,7)=?"
            params.append(month)
        except ValueError:
            month = ""
    query += " ORDER BY t.transaction_date DESC, t.id DESC"
    rows = db.execute(query, params).fetchall()
    return render_template("transactions.html", rows=rows, kind=kind, month=month)

@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    db = get_db()
    uid = session["user_id"]
    categories = db.execute("SELECT * FROM categories WHERE user_id=? ORDER BY kind,name", (uid,)).fetchall()
    if request.method == "POST":
        kind = request.form.get("kind", "")
        category_id = request.form.get("category_id", type=int)
        tx_date = request.form.get("transaction_date", "")
        description = request.form.get("description", "").strip()[:300]
        try:
            amount_paise = money_to_paise(request.form.get("amount", ""))
            datetime.strptime(tx_date, "%Y-%m-%d")
            category = db.execute("SELECT * FROM categories WHERE id=? AND user_id=?", (category_id, uid)).fetchone()
            if kind not in ("Income", "Expense") or not category or category["kind"] != kind:
                raise ValueError("Choose a category matching the transaction type.")
        except (ValueError, TypeError):
            flash("Please check the amount, date, type, and category.", "danger")
            return render_template("transaction_form.html", categories=categories, today=date.today().isoformat())
        db.execute("""INSERT INTO transactions(user_id,category_id,kind,amount_paise,transaction_date,description)
                      VALUES(?,?,?,?,?,?)""", (uid, category_id, kind, amount_paise, tx_date, description))
        db.commit()
        flash("Transaction added successfully.", "success")
        return redirect(url_for("transactions"))
    return render_template("transaction_form.html", categories=categories, today=date.today().isoformat())

@app.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(tx_id):
    db = get_db()
    uid = session["user_id"]
    tx = db.execute("SELECT * FROM transactions WHERE id=? AND user_id=?", (tx_id, uid)).fetchone()
    if tx is None:
        flash("Transaction not found.", "danger")
        return redirect(url_for("transactions"))
    categories = db.execute("SELECT * FROM categories WHERE user_id=? ORDER BY kind,name", (uid,)).fetchall()
    if request.method == "POST":
        kind = request.form.get("kind", "")
        category_id = request.form.get("category_id", type=int)
        tx_date = request.form.get("transaction_date", "")
        description = request.form.get("description", "").strip()[:300]
        try:
            amount_paise = money_to_paise(request.form.get("amount", ""))
            datetime.strptime(tx_date, "%Y-%m-%d")
            category = db.execute("SELECT * FROM categories WHERE id=? AND user_id=?", (category_id, uid)).fetchone()
            if kind not in ("Income", "Expense") or not category or category["kind"] != kind:
                raise ValueError()
        except (ValueError, TypeError):
            flash("Please check the amount, date, type, and category.", "danger")
            return render_template("transaction_form.html", categories=categories, tx=tx, today=date.today().isoformat())
        db.execute("""UPDATE transactions SET category_id=?,kind=?,amount_paise=?,transaction_date=?,description=?
                    WHERE id=? AND user_id=?""",
                (category_id, kind, amount_paise, tx_date, description, tx_id, uid))
        db.commit()
        flash("Transaction updated.", "success")
        return redirect(url_for("transactions"))
    return render_template("transaction_form.html", categories=categories, tx=tx, today=date.today().isoformat())

@app.route("/transactions/<int:tx_id>/delete", methods=["POST"])
@login_required
def delete_transaction(tx_id):
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id, session["user_id"]))
    db.commit()
    flash("Transaction deleted if it existed.", "info")
    return redirect(url_for("transactions"))

@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    db = get_db()
    uid = session["user_id"]
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:40]
        kind = request.form.get("kind", "")
        if not name or kind not in ("Income", "Expense"):
            flash("Enter a category name and type.", "danger")
        else:
            try:
                db.execute("INSERT INTO categories(user_id,name,kind) VALUES(?,?,?)", (uid, name, kind))
                db.commit()
                flash("Category created.", "success")
            except sqlite3.IntegrityError:
                flash("That category already exists.", "warning")
        return redirect(url_for("categories"))
    rows = db.execute("SELECT * FROM categories WHERE user_id=? ORDER BY kind,name", (uid,)).fetchall()
    return render_template("categories.html", rows=rows)


@app.route("/categories/<int:category_id>/update", methods=["POST"])
@login_required
def update_category(category_id):
    db = get_db()
    uid = session["user_id"]

    category = db.execute(
        "SELECT * FROM categories WHERE id=? AND user_id=?",
        (category_id, uid)
    ).fetchone()

    if category is None:
        flash("Category not found.", "danger")
        return redirect(url_for("categories"))

    name = request.form.get("name", "").strip()[:40]
    kind = request.form.get("kind", "")

    if not name or kind not in ("Income", "Expense"):
        flash("Enter a valid category name and type.", "danger")
        return redirect(url_for("categories"))

    if kind != category["kind"]:
        used = db.execute(
            "SELECT 1 FROM transactions WHERE category_id=? LIMIT 1",
            (category_id,)
        ).fetchone()

        if used:
            flash("Cannot change type because transactions use this category.", "warning")
            return redirect(url_for("categories"))

    try:
        db.execute(
            "UPDATE categories SET name=?, kind=? WHERE id=? AND user_id=?",
            (name, kind, category_id, uid)
        )
        db.commit()
        flash("Category updated successfully.", "success")

    except sqlite3.IntegrityError:
        db.rollback()
        flash("This category name already exists for that type.", "warning")

    return redirect(url_for("categories"))


@app.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    db = get_db()
    uid = session["user_id"]

    try:
        cursor = db.execute(
            "DELETE FROM categories WHERE id=? AND user_id=?",
            (category_id, uid)
        )
        db.commit()

        if cursor.rowcount:
            flash("Category deleted successfully.", "success")
        else:
            flash("Category not found.", "warning")

    except sqlite3.IntegrityError:
        db.rollback()
        flash(
            "Cannot delete this category because existing transactions use it.",
            "danger"
        )

    return redirect(url_for("categories"))


@app.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    db = get_db()
    uid = session["user_id"]
    categories = db.execute("SELECT * FROM categories WHERE user_id=? AND kind='Expense' ORDER BY name", (uid,)).fetchall()
    if request.method == "POST":
        try:
            amount_paise = money_to_paise(request.form.get("amount", ""))
            month = int(request.form.get("month", ""))
            year = int(request.form.get("year", ""))
            category_raw = request.form.get("category_id", "")
            category_id = int(category_raw) if category_raw else None
            if not 1 <= month <= 12 or not 2000 <= year <= 2100:
                raise ValueError()
            if category_id is not None:
                exists = db.execute("SELECT id FROM categories WHERE id=? AND user_id=? AND kind='Expense'", (category_id, uid)).fetchone()
                if not exists:
                    raise ValueError()
            db.execute("""INSERT INTO budgets(user_id,category_id,month,year,amount_paise)
                VALUES(?,?,?,?,?) ON CONFLICT(user_id,category_id,month,year)
                DO UPDATE SET amount_paise=excluded.amount_paise""",
                (uid, category_id, month, year, amount_paise))
            db.commit()
            flash("Budget saved.", "success")
        except (ValueError, TypeError, sqlite3.IntegrityError):
            flash("Please enter a valid budget, month, year, and category.", "danger")
        return redirect(url_for("budgets"))
    rows = db.execute("""SELECT b.*, c.name category_name FROM budgets b
        LEFT JOIN categories c ON c.id=b.category_id WHERE b.user_id=?
        ORDER BY b.year DESC,b.month DESC""", (uid,)).fetchall()
    return render_template("budgets.html", rows=rows, categories=categories, now=date.today())


@app.route("/budgets/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete_budget(budget_id):
    db = get_db()
    uid = session["user_id"]

    db.execute(
        "DELETE FROM budgets WHERE id=? AND user_id=?",
        (budget_id, uid)
    )
    db.commit()

    flash("Budget deleted successfully.", "success")
    return redirect(url_for("budgets"))

@app.route("/budgets/<int:budget_id>/edit", methods=["GET", "POST"])
@login_required
def edit_budget(budget_id):
    db = get_db()
    uid = session["user_id"]

    budget = db.execute(
        "SELECT * FROM budgets WHERE id=? AND user_id=?",
        (budget_id, uid)
    ).fetchone()

    if budget is None:
        flash("Budget not found.", "danger")
        return redirect(url_for("budgets"))

    categories = db.execute(
        "SELECT * FROM categories WHERE user_id=? AND kind='Expense' ORDER BY name",
        (uid,)
    ).fetchall()

    if request.method == "POST":
        try:
            amount_paise = money_to_paise(request.form.get("amount", ""))
            month = int(request.form.get("month", ""))
            year = int(request.form.get("year", ""))
            raw_category = request.form.get("category_id", "")
            category_id = int(raw_category) if raw_category else None

            if not 1 <= month <= 12 or not 2000 <= year <= 2100:
                raise ValueError()

            if category_id is not None:
                category = db.execute(
                    "SELECT id FROM categories WHERE id=? AND user_id=? AND kind='Expense'",
                    (category_id, uid)
                ).fetchone()

                if category is None:
                    raise ValueError()

            db.execute(
                """UPDATE budgets
                   SET amount_paise=?, category_id=?, month=?, year=?
                   WHERE id=? AND user_id=?""",
                (amount_paise, category_id, month, year, budget_id, uid)
            )
            db.commit()
            flash("Budget updated successfully.", "success")
            return redirect(url_for("budgets"))

        except (ValueError, TypeError, sqlite3.IntegrityError):
            db.rollback()
            flash("Please enter valid budget details.", "danger")

    return render_template(
        "edit_budget.html",
        budget=budget,
        categories=categories
    )


@app.route("/reports")
@login_required
def reports():
    db = get_db()
    uid = session["user_id"]
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = date.today().strftime("%Y-%m")
    rows = db.execute("""
        SELECT c.name category_name, t.kind, SUM(t.amount_paise) total, COUNT(*) count
        FROM transactions t JOIN categories c ON c.id=t.category_id
        WHERE t.user_id=? AND substr(t.transaction_date,1,7)=?
        GROUP BY c.name,t.kind ORDER BY t.kind,c.name
    """, (uid, month)).fetchall()
    return render_template("reports.html", rows=rows, month=month)

@app.route("/export.csv")
@login_required
def export_csv():
    db = get_db()
    rows = db.execute("""
        SELECT t.transaction_date,t.kind,c.name,t.amount_paise,t.description
        FROM transactions t JOIN categories c ON c.id=t.category_id
        WHERE t.user_id=? ORDER BY t.transaction_date DESC,t.id DESC
    """, (session["user_id"],)).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Type", "Category", "Amount (INR)", "Description"])
    for row in rows:
        writer.writerow([row["transaction_date"], row["kind"], row["name"],
                         f'{row["amount_paise"]/100:.2f}', row["description"]])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=expense_transactions.csv"})

@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database initialized.")

init_db()

if __name__ == "__main__":
    app.run(debug=True)
