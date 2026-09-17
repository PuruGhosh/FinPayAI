"""Scope-aware policy retrieval from Chroma collections."""

from typing import Any

from src.finpay.access.policy_visibility import (
    build_chroma_filter,
    can_view_policy,
)
from src.finpay.access.scoped_query import AccessDenied, UserContext


PUBLIC_COLLECTION = "finpay_public_policies"
INTERNAL_COLLECTION = "finpay_internal_policies"


def _known_visibility_tags(collection: Any) -> set[str]:
    # Discover tags from stored metadata so admin filters cover current documents.
    records = collection.get(include=["metadatas"])
    return {
        str(metadata["visibility"])
        for metadata in records.get("metadatas", [])
        if metadata and metadata.get("visibility")
    }


def retrieve_policies(
    client: Any,
    context: UserContext,
    query: str,
    n_results: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve policy chunks authorized for ``context``.

    Collection selection and metadata filtering are controlled by the trusted
    user context. Returned records are checked again before leaving this tool.
    """
    if n_results < 1:
        raise ValueError("n_results must be positive")

    # Physical collection choice is the first boundary; metadata filtering is the second.
    collection_name = (
        PUBLIC_COLLECTION
        if context.user_type == "external"
        else INTERNAL_COLLECTION
    )
    collection = client.get_collection(collection_name)
    known_tags = _known_visibility_tags(collection)
    visibility_filter = build_chroma_filter(context, known_tags)
    result = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=visibility_filter,
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    records: list[dict[str, Any]] = []
    # Re-check every result because a vector store response is not itself trusted.
    for index, (document, metadata) in enumerate(zip(documents, metadatas)):
        metadata = metadata or {}
        try:
            permitted = can_view_policy(
                context,
                str(metadata.get("visibility", "")),
            )
        except AccessDenied:
            permitted = False
        if not permitted:
            continue
        record = {
            "text": document,
            "metadata": metadata,
        }
        if index < len(distances):
            record["distance"] = distances[index]
        records.append(record)
    return records


def build_policy_tool(client: Any, n_results: int = 5):
    """Build the graph-compatible policy tool for a Chroma client."""
    def policy_tool(context: UserContext, query: str) -> list[dict[str, Any]]:
        return retrieve_policies(client, context, query, n_results)

    return policy_tool
