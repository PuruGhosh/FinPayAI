import unittest

from src.finpay.graph.guardrail import contains_pii_pattern, guard_response
from src.finpay.access.scoped_query import UserContext


class GuardrailTests(unittest.TestCase):
    def test_email_is_detected(self):
    # Basic contact patterns are treated as protected by default.
        self.assertTrue(contains_pii_pattern("Contact fin@example.test"))

    def test_iban_is_detected(self):
        self.assertTrue(contains_pii_pattern("Account GB29NWBK60161331926819"))

    def test_masked_values_are_allowed(self):
        self.assertFalse(contains_pii_pattern("Email: [MASKED]"))
        self.assertEqual("Safe answer", guard_response("Safe answer"))

    def test_internal_directory_email_is_allowed(self):
        # Trusted internal directory responses are the explicit exception.
        context = UserContext("EMP-FIN", "employee", "FIN")
        self.assertFalse(contains_pii_pattern("Contact fin@example.test", context))
        self.assertEqual(
            "Contact fin@example.test",
            guard_response("Contact fin@example.test", context),
        )

    def test_external_directory_email_is_blocked(self):
        context = UserContext("anonymous", "", None, "external")
        self.assertTrue(contains_pii_pattern("Contact fin@example.test", context))

    def test_response_with_pii_is_blocked(self):
        self.assertIn("protected personal data", guard_response("Email: fin@example.test"))


if __name__ == "__main__":
    unittest.main()
