"""Access-first conversation graph with injected, scoped data tools."""

import logging
import sqlite3
from typing import Literal
from typing import Any, Callable, Mapping
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from src.finpay.access.scoped_query import UserContext, scoped_select
from src.finpay.graph.guardrail import guard_response
from src.finpay.policies.retrieval import build_policy_tool


Intent = Literal["policy", "structured_data", "self_service", "public", "unknown"]
Route = Literal["external", "policy", "structured_data", "self_service", "denied"]


class ConversationState(TypedDict, total=False):
    user_context: UserContext
    user_message: str
    intent: Intent
    route: Route
    resource: str
    filters: Mapping[str, Any]
    results: list[dict[str, Any]]
    response: str


StructuredTool = Callable[
    [UserContext, str, Mapping[str, Any] | None], list[dict[str, Any]]
]
PolicyTool = Callable[[UserContext, str], list[dict[str, Any]]]
IntentClassifier = Callable[[str], Intent]
AnswerGenerator = Callable[[str, str, list[dict[str, Any]]], str]
Guardrail = Callable[[str, UserContext], str]
LOGGER = logging.getLogger(__name__)


def _looks_like_employee_lookup(user_message: str) -> bool:
    # Handle common directory questions deterministically when classification is uncertain.
    message = user_message.lower()
    lookup_terms = ("who", "person", "employee", "staff", "head", "senior", "manager")
    organization_terms = ("department", "team", "lead", "role", "title")
    return any(term in message for term in lookup_terms) and any(
        term in message for term in organization_terms
    )


def _looks_like_policy_question(user_message: str) -> bool:
    # Known policy phrases get the safe policy route without trusting model guesses.
    message = user_message.lower()
    policy_terms = (
        "notice period",
        "probation",
        "leave policy",
        "expense policy",
        "employee handbook",
        "code of conduct",
        "privacy policy",
        "terms of service",
        "aml policy",
        "payroll policy",
    )
    return any(term in message for term in policy_terms)


def _classify_node(
    state: ConversationState,
    classifier: IntentClassifier | None,
) -> ConversationState:
    # Identity and obvious security-sensitive routing are resolved before the LLM.
    if state.get("intent") or state["user_context"].user_type == "external":
        return {}
    if not state.get("user_message"):
        return {"intent": "unknown"}
    if _looks_like_employee_lookup(state["user_message"]):
        return {"intent": "structured_data", "resource": "employees"}
    if _looks_like_policy_question(state["user_message"]):
        return {"intent": "policy"}
    if classifier is None:
        return {"intent": "unknown"}
    try:
        intent = classifier(state["user_message"])
    except RuntimeError:
        intent = "unknown"
    if intent == "unknown" and _looks_like_employee_lookup(state["user_message"]):
        return {"intent": "structured_data", "resource": "employees"}
    return {"intent": intent}


def _route_node(state: ConversationState) -> ConversationState:
    # This node is the application-owned authorization gate for all subgraphs.
    context = state["user_context"]
    if context.user_type == "external":
        return {"route": "external"}

    intent = state.get("intent", "unknown")
    if intent == "policy":
        return {"route": "policy"}
    if intent == "structured_data":
        return {"route": "structured_data"}
    if intent == "self_service":
        return {"route": "self_service"}
    return {"route": "denied"}


def _external_node(
    state: ConversationState,
    policy_tool: PolicyTool | None,
) -> ConversationState:
    if policy_tool is None:
        return {"response": "External request routed to public-only tools; retrieval is unavailable."}
    results = policy_tool(state["user_context"], state.get("user_message", ""))
    return {
        "results": results,
        "response": "Public request routed to public-only tools.",
    }


def _policy_node(
    state: ConversationState,
    policy_tool: PolicyTool | None,
) -> ConversationState:
    if policy_tool is None:
        return {"response": "Internal policy retrieval is unavailable."}
    results = policy_tool(state["user_context"], state.get("user_message", ""))
    return {
        "results": results,
        "response": "Internal request routed to scoped policy retrieval.",
    }


def _structured_data_node(
    state: ConversationState,
    structured_tool: StructuredTool,
) -> ConversationState:
    resource = state.get("resource")
    if not resource:
        return {"response": "Structured-data request denied because no resource was specified."}
    results = structured_tool(
        state["user_context"],
        resource,
        state.get("filters"),
    )
    return {
        "results": results,
        "response": "Internal request routed to scoped structured-data access.",
    }


def _self_service_node(
    state: ConversationState,
    structured_tool: StructuredTool,
) -> ConversationState:
    results = structured_tool(
        state["user_context"],
        "employees",
        {"employee_id": state["user_context"].user_id},
    )
    return {
        "results": results,
        "response": "Internal request routed to self-scoped lookup.",
    }


def _denied_node(state: ConversationState) -> ConversationState:
    return {"response": "Request denied because its access scope is unclear."}


def _answer_node(
    state: ConversationState,
    answer_generator: AnswerGenerator | None,
) -> ConversationState:
    if answer_generator is None or "results" not in state:
        return {}
    # Synthesis is optional; retrieval has already enforced the data boundary.
    try:
        response = answer_generator(
            state.get("user_message", ""),
            state["route"],
            state["results"],
        )
    except RuntimeError as exc:
        LOGGER.warning("Answer agent failed; using authorized-results fallback: %s", exc)
        response = _authorized_results_fallback(state["results"])
    return {"response": response}


def _authorized_results_fallback(results: list[dict[str, Any]]) -> str:
    """Return safe tool results when response synthesis is unavailable."""
    # Degrade to the tool output rather than inventing an answer or exposing data.
    if not results:
        return "No authorized information was found for this request."
    lines = []
    for result in results:
        if "text" in result:
            lines.append(str(result["text"]))
        else:
            lines.append(str(result))
    return "LLM answer generation is unavailable. Authorized information:\n\n" + "\n\n".join(lines)


def _guardrail_node(
    state: ConversationState,
    guardrail: Guardrail,
) -> ConversationState:
    return {
        "response": guardrail(
            state.get("response", ""),
            state["user_context"],
        )
    }


def _next_route(state: ConversationState) -> Route:
    return state["route"]


def build_graph(
    connection: sqlite3.Connection | None = None,
    policy_tool: PolicyTool | None = None,
    structured_tool: StructuredTool | None = None,
    classifier: IntentClassifier | None = None,
    answer_generator: AnswerGenerator | None = None,
    guardrail: Guardrail = guard_response,
    llm: Any | None = None,
    chroma_client: Any | None = None,
    policy_top_k: int = 5,
):
    """Build the graph with application-owned, scope-enforcing tool calls.

    ``policy_tool`` is expected to apply ``policy_visibility`` before querying
    Chroma. The default structured tool delegates to ``scoped_select``.
    """
    if llm is not None:
        classifier = classifier or llm.classify
        answer_generator = answer_generator or llm.answer
    if policy_tool is None and chroma_client is not None:
        policy_tool = build_policy_tool(chroma_client, policy_top_k)

    if structured_tool is None:
        if connection is None:
            def unavailable_structured_tool(
                context: UserContext,
                resource: str,
                filters: Mapping[str, Any] | None,
            ) -> list[dict[str, Any]]:
                raise RuntimeError("a database connection is required for structured data")

            structured_tool = unavailable_structured_tool
        else:
            structured_tool = lambda context, resource, filters: scoped_select(
                connection, context, resource, filters
            )

    # Each named node has one responsibility; tools remain the authorization layer.
    graph = StateGraph(ConversationState)
    graph.add_node("intent_agent", lambda state: _classify_node(state, classifier))
    graph.add_node("orchestrator", _route_node)
    graph.add_node("policy_agent", lambda state: _policy_node(state, policy_tool))
    graph.add_node("structured_data_agent", lambda state: _structured_data_node(state, structured_tool))
    graph.add_node("self_service_agent", lambda state: _self_service_node(state, structured_tool))
    graph.add_node("external_agent", lambda state: _external_node(state, policy_tool))
    graph.add_node("denied", _denied_node)
    graph.add_node("answer_agent", lambda state: _answer_node(state, answer_generator))
    graph.add_node("guardrail_agent", lambda state: _guardrail_node(state, guardrail))
    graph.add_edge(START, "intent_agent")
    graph.add_edge("intent_agent", "orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        _next_route,
        {
            "external": "external_agent",
            "policy": "policy_agent",
            "structured_data": "structured_data_agent",
            "self_service": "self_service_agent",
            "denied": "denied",
        },
    )
    for node in (
        "external_agent",
        "policy_agent",
        "structured_data_agent",
        "self_service_agent",
    ):
        graph.add_edge(node, "answer_agent")
    graph.add_edge("answer_agent", "guardrail_agent")
    graph.add_edge("guardrail_agent", END)
    graph.add_edge("denied", END)
    return graph.compile()