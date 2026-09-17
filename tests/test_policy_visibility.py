import unittest

from src.finpay.access.policy_visibility import (
    build_chroma_filter,
    can_view_policy,
)
from src.finpay.access.scoped_query import AccessDenied, UserContext


class PolicyVisibilityTests(unittest.TestCase):
    def test_external_user_can_only_view_public_documents(self):
    # Public users must be limited to the public visibility tag.
        context = UserContext("anonymous", "", None, "external")
        self.assertTrue(can_view_policy(context, "public"))
        self.assertFalse(can_view_policy(context, "all_internal"))
        self.assertEqual(
            {"visibility": {"$in": ["public"]}},
            build_chroma_filter(context),
        )

    def test_employee_can_view_own_department_documents(self):
        context = UserContext("EMP-FIN", "employee", "FIN")
        self.assertTrue(can_view_policy(context, "public"))
        self.assertTrue(can_view_policy(context, "all_internal"))
        self.assertTrue(can_view_policy(context, "dept:FIN"))
        self.assertFalse(can_view_policy(context, "dept:HR"))
        self.assertFalse(can_view_policy(context, "admin_only"))

    def test_admin_can_view_all_known_department_documents(self):
        # Admin expansion comes from known metadata, not user-provided tags.
        context = UserContext("EMP-ADMIN", "admin", "EXEC")
        known_tags = {"dept:FIN", "dept:HR", "dept:ENG"}
        self.assertTrue(can_view_policy(context, "dept:HR"))
        self.assertTrue(can_view_policy(context, "admin_only"))
        self.assertEqual(
            {
                "visibility": {
                    "$in": [
                        "admin_only",
                        "all_internal",
                        "dept:ENG",
                        "dept:EXEC",
                        "dept:FIN",
                        "dept:HR",
                        "public",
                    ]
                }
            },
            build_chroma_filter(context, known_tags),
        )

    def test_unclassified_document_is_denied(self):
        # Missing classification is a deny-by-default condition.
        context = UserContext("EMP-FIN", "employee", "FIN")
        with self.assertRaises(AccessDenied):
            can_view_policy(context, "")


if __name__ == "__main__":
    unittest.main()