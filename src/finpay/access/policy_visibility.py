"""Visibility rules for policy-document retrieval."""

from collections.abc import Iterable

from .scoped_query import AccessDenied, UserContext


def allowed_visibility_tags(
    context: UserContext,
    known_tags: Iterable[str] = (),
) -> frozenset[str]:
    """Return the policy visibility tags permitted for ``context``."""
    # Public users receive a hard public-only boundary before Chroma is queried.
    if context.user_type == "external":
        return frozenset({"public"})

    tags = {"public", "all_internal", f"dept:{context.department}"}
    # Admin visibility is expanded from known metadata, never from the prompt.
    if context.role == "admin":
        tags.add("admin_only")
        tags.update(tag for tag in known_tags if tag.startswith("dept:"))
    return frozenset(tags)


def build_chroma_filter(
    context: UserContext,
    known_tags: Iterable[str] = (),
) -> dict[str, dict[str, list[str]]]:
    """Build an allowlist filter for a Chroma metadata query."""
    tags = sorted(allowed_visibility_tags(context, known_tags))
    return {"visibility": {"$in": tags}}


def can_view_policy(context: UserContext, visibility: str) -> bool:
    """Check one document's visibility before it reaches a language model."""
    if not visibility:
        raise AccessDenied("policy document has no visibility classification")
    return visibility in allowed_visibility_tags(context, (visibility,))