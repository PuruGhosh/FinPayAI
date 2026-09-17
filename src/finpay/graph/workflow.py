"""Minimal access-first conversation graph.

This graph routes requests before any retrieval or database tool is called.
It intentionally does not classify free-form text yet; a later LLM classifier
must write one of the supported intents into the state.
"""

from typing import Literal
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from src.finpay.access.scoped_query import UserContext


Intent = Literal["policy", "structured_data", "self_service", "public", "unknown"]
Route = Literal["external", "policy", "structured_data", "self_service", "denied"]


class ConversationState(TypedDict, total=False):
    user_context: UserContext
    user_message: str
    intent: Intent
    route: Route
    response: str


def _route_node(state: ConversationState) -> ConversationState:
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


def _external_node(state: ConversationState) -> ConversationState:
    return {
        "response": "External request routed to public-only tools.",
    }


def _policy_node(state: ConversationState) -> ConversationState:
    return {"response": "Internal request routed to scoped policy retrieval."}


def _structured_data_node(state: ConversationState) -> ConversationState:
    return {"response": "Internal request routed to scoped structured-data access."}


def _self_service_node(state: ConversationState) -> ConversationState:
    return {"response": "Internal request routed to self-scoped lookup."}


def _denied_node(state: ConversationState) -> ConversationState:
    return {"response": "Request denied because its access scope is unclear."}


def _next_route(state: ConversationState) -> Route:
    return state["route"]


def build_graph():
    """Build and compile the access-first conversation graph."""
    graph = StateGraph(ConversationState)
    graph.add_node("route", _route_node)
    graph.add_node("external", _external_node)
    graph.add_node("policy", _policy_node)
    graph.add_node("structured_data", _structured_data_node)
    graph.add_node("self_service", _self_service_node)
    graph.add_node("denied", _denied_node)
    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        _next_route,
        {
            "external": "external",
            "policy": "policy",
            "structured_data": "structured_data",
            "self_service": "self_service",
            "denied": "denied",
        },
    )
    for node in ("external", "policy", "structured_data", "self_service", "denied"):
        graph.add_edge(node, END)
    return graph.compile()