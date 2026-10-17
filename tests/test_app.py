import os
import tempfile
import unittest
from app import app, init_db

class ExpenseTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.tmp.name
        app.config["SECRET_KEY"] = "test-secret"
        init_db()
        self.client = app.test_client()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def register(self, email="test@example.com"):
        return self.client.post("/register", data={
            "name": "Test User", "email": email, "password": "testpassword123"
        }, follow_redirects=True)

    def test_register_and_dashboard(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your money dashboard", response.data)

    def test_transaction_flow(self):
        self.register()
        with self.client.session_transaction() as sess:
            user_id = sess["user_id"]
        # Seed categories are created on registration; obtain category ID via test DB.
        import sqlite3
        db = sqlite3.connect(app.config["DATABASE"])
        category_id = db.execute(
            "SELECT id FROM categories WHERE user_id=? AND name='Salary' AND kind='Income'",
            (user_id,)
        ).fetchone()[0]
        db.close()
        response = self.client.post("/transactions/add", data={
            "kind": "Income", "category_id": str(category_id), "amount": "25000",
            "transaction_date": "2026-01-15", "description": "Monthly salary"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Monthly salary", response.data)

    def test_login_required(self):
        self.client.get("/logout")
        response = self.client.get("/transactions")
        self.assertEqual(response.status_code, 302)

if __name__ == "__main__":
    unittest.main()
