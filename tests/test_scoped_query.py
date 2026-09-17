import sqlite3
import unittest

from src.finpay.access.scoped_query import AccessDenied, UserContext, scoped_select


class ScopedQueryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE employees (
                employee_id TEXT, full_name TEXT, department_id TEXT,
                access_role TEXT, email TEXT, salary REAL
            );
            CREATE TABLE transactions (
                txn_id TEXT, customer_id TEXT, department_owner TEXT,
                status TEXT
            );
            INSERT INTO employees VALUES
                ('EMP-FIN', 'Finance User', 'FIN', 'employee', 'fin@example.test', 100),
                ('EMP-HR', 'HR User', 'HR', 'employee', 'hr@example.test', 200);
            INSERT INTO transactions VALUES
                ('TXN-FIN', 'CUST-1', 'FIN', 'completed'),
                ('TXN-HR', 'CUST-2', 'HR', 'completed');
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_external_user_is_denied_before_query(self):
        context = UserContext("anonymous", "", None, "external")
        with self.assertRaises(AccessDenied):
            scoped_select(self.connection, context, "employees")

    def test_employee_is_limited_to_department_and_own_pii(self):
        context = UserContext("EMP-FIN", "employee", "FIN")
        rows = scoped_select(self.connection, context, "employees")
        self.assertEqual(["EMP-FIN"], [row["employee_id"] for row in rows])
        self.assertEqual("fin@example.test", rows[0]["email"])

    def test_admin_sees_all_departments_but_pii_is_masked(self):
        context = UserContext("EMP-ADMIN", "admin", "EXEC")
        rows = scoped_select(self.connection, context, "employees")
        self.assertEqual({"EMP-FIN", "EMP-HR"}, {row["employee_id"] for row in rows})
        self.assertTrue(all(row["email"] == "[MASKED]" for row in rows))

    def test_employee_cannot_read_another_department_transaction(self):
        context = UserContext("EMP-FIN", "employee", "FIN")
        rows = scoped_select(self.connection, context, "transactions")
        self.assertEqual(["TXN-FIN"], [row["txn_id"] for row in rows])


if __name__ == "__main__":
    unittest.main()