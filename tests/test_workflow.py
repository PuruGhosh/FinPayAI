import unittest

from src.finpay.access.scoped_query import UserContext
from src.finpay.graph.workflow import build_graph


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # The default graph is used to verify deny-by-default routing.
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

    def test_notice_period_question_routes_to_policy_agent(self):
        graph = build_graph(
            classifier=lambda message: "unknown",
            policy_tool=lambda context, query: [{"text": "authorized policy"}],
        )
        state = graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "user_message": "What is our notice period?",
            }
        )

        self.assertEqual("policy", state["route"])
        self.assertEqual([{ "text": "authorized policy"}], state["results"])

    def test_structured_request_uses_injected_tool_and_returns_results(self):
        calls = []

        def structured_tool(context, resource, filters):
            calls.append((context, resource, filters))
            return [{"employee_id": context.user_id}]

        graph = build_graph(structured_tool=structured_tool)
        state = graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "intent": "structured_data",
                "resource": "employees",
                "filters": {"department_id": "FIN"},
            }
        )

        self.assertEqual("structured_data", state["route"])
        self.assertEqual([{"employee_id": "EMP-FIN"}], state["results"])
        self.assertEqual("employees", calls[0][1])
        self.assertEqual({"department_id": "FIN"}, calls[0][2])

    def test_self_service_overrides_requested_employee_filter(self):
        # A prompt cannot substitute another employee's ID for the session user.
        calls = []

        def structured_tool(context, resource, filters):
            calls.append((resource, filters))
            return []

        graph = build_graph(structured_tool=structured_tool)
        graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "intent": "self_service",
                "resource": "employees",
                "filters": {"employee_id": "EMP-HR"},
            }
        )

        self.assertEqual([("employees", {"employee_id": "EMP-FIN"})], calls)

    def test_unknown_internal_intent_is_denied(self):
        state = self.graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "intent": "unknown",
            }
        )
        self.assertEqual("denied", state["route"])
        self.assertIn("denied", state["response"])

    def test_employee_directory_question_uses_scoped_employee_data(self):
        calls = []

        def structured_tool(context, resource, filters):
            calls.append((context, resource, filters))
            return [{"employee_id": "EMP-COMPANY"}]

        graph = build_graph(
            classifier=lambda message: "policy",
            structured_tool=structured_tool,
        )
        state = graph.invoke(
            {
                "user_context": UserContext("EMP-COMP", "employee", "COMPLIANCE"),
                "user_message": "Who is the most senior person in my department?",
            }
        )

        self.assertEqual("structured_data", state["route"])
        self.assertEqual(
            [("employees", None)],
            [(resource, filters) for _, resource, filters in calls],
        )

    def test_answer_agent_output_passes_through_guardrail_agent(self):
        graph = build_graph(
            classifier=lambda message: "policy",
            policy_tool=lambda context, query: [{"text": "authorized"}],
            answer_generator=lambda message, route, results: "Account: GB29NWBK60161331926819",
        )
        state = graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "user_message": "What is the policy?",
            }
        )

        self.assertIn("protected personal data", state["response"])

    def test_answer_agent_falls_back_to_authorized_results(self):
        # Provider failure must not turn into a data-access failure or invention.
        def unavailable_answer(message, route, results):
            raise RuntimeError("LLM unavailable")

        graph = build_graph(
            classifier=lambda message: "policy",
            policy_tool=lambda context, query: [{"text": "Notice period is 30 days."}],
            answer_generator=unavailable_answer,
        )
        state = graph.invoke(
            {
                "user_context": UserContext("EMP-FIN", "employee", "FIN"),
                "user_message": "What is our notice period?",
            }
        )

        self.assertIn("Notice period is 30 days.", state["response"])


if __name__ == "__main__":
    unittest.main()