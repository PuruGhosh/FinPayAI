import unittest

from src.finpay.access.scoped_query import UserContext
from src.finpay.graph.workflow import build_graph


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph()

    def test_external_user_cannot_enter_internal_routes(self):
        state = self.graph.invoke(
            {
                "user_context": UserContext("anonymous", "", None, "external"),
                "intent": "structured_data",
            }
        )
        self.assertEqual("external", state["route"])
        self.assertIn("public-only", state["response"])

    def test_internal_policy_request_routes_to_policy_node(self):
        state = self.graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "intent": "policy",
            }
        )
        self.assertEqual("policy", state["route"])

    def test_unknown_internal_intent_is_denied(self):
        state = self.graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "intent": "unknown",
            }
        )
        self.assertEqual("denied", state["route"])
        self.assertIn("denied", state["response"])


if __name__ == "__main__":
    unittest.main()