"""Final response checks for accidental PII disclosure."""

import re

from src.finpay.access.scoped_query import UserContext

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", re.IGNORECASE)
_LONG_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[ -]?){10,18}(?!\d)")


def contains_pii_pattern(
    response: str,
    context: UserContext | None = None,
) -> bool:
    """Return whether a response contains a likely raw PII value."""
    # Internal directory contacts are approved; financial identifiers remain blocked.
    patterns = (_IBAN_RE,)
    if context is None or context.user_type == "external":
        patterns = (_EMAIL_RE, _IBAN_RE, _LONG_NUMBER_RE)
    return any(pattern.search(response) for pattern in patterns)


def guard_response(
    response: str,
    context: UserContext | None = None,
) -> str:
    """Block responses containing likely raw PII before display."""
    if contains_pii_pattern(response, context):
        return "I cannot provide that response because it may contain protected personal data."
    return response
