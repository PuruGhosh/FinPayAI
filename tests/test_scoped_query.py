import sqlite3
import unittest

from src.finpay.access.scoped_query import AccessDenied, UserContext, scoped_select


class ScopedQueryTests(unittest.TestCase):
    def setUp(self):
        # Use an isolated database so tests prove scoping without demo-data state.
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE employees (
                employee_id TEXT, full_name TEXT, department_id TEXT,
                access_role TEXT, email TEXT, phone TEXT, salary REAL
            );
            CREATE TABLE transactions (
                txn_id TEXT, customer_id TEXT, department_owner TEXT,
                status TEXT
            );
            INSERT INTO employees VALUES
                ('EMP-FIN', 'Finance User', 'FIN', 'employee', 'fin@example.test', '1111111111', 100),
                ('EMP-HR', 'HR User', 'HR', 'employee', 'hr@example.test', '2222222222', 200);
            INSERT INTO transactions VALUES
                ('TXN-FIN', 'CUST-1', 'FIN', 'completed'),
                ('TXN-HR', 'CUST-2', 'HR', 'completed');
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_external_user_is_denied_before_query(self):
        # External sessions must fail before any structured data is returned.
        context = UserContext("anonymous", "", None, "external")
        with self.assertRaises(AccessDenied):
            scoped_select(self.connection, context, "employees")

    def test_employee_is_limited_to_department_and_own_pii(self):
        context = UserContext("EMP-FIN", "employee", "FIN")
        rows = scoped_select(self.connection, context, "employees")
        self.assertEqual(["EMP-FIN"], [row["employee_id"] for row in rows])
        self.assertEqual("fin@example.test", rows[0]["email"])

    def test_internal_users_see_directory_contacts_but_sensitive_pii_is_masked(self):
        # Directory contacts are useful internally; financial and identity PII is not.
        context = UserContext("EMP-ADMIN", "admin", "EXEC")
        rows = scoped_select(self.connection, context, "employees")
        self.assertEqual({"EMP-FIN", "EMP-HR"}, {row["employee_id"] for row in rows})
        self.assertEqual(
            {"fin@example.test", "hr@example.test"},
            {row["email"] for row in rows},
        )
        self.assertEqual({"1111111111", "2222222222"}, {row["phone"] for row in rows})
        self.assertTrue(all(row["salary"] == "[MASKED]" for row in rows))

    def test_employee_cannot_read_another_department_transaction(self):
        context = UserContext("EMP-FIN", "employee", "FIN")
        rows = scoped_select(self.connection, context, "transactions")
        self.assertEqual(["TXN-FIN"], [row["txn_id"] for row in rows])


if __name__ == "__main__":
    unittest.main()