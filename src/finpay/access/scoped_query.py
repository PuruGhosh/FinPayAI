"""Centralized, allowlisted access to FinPay's structured data."""

from dataclasses import dataclass
import sqlite3
from typing import Any, Mapping


class AccessDenied(Exception):
    """Raised when a request is outside the user's permitted data scope."""


@dataclass(frozen=True)
class UserContext:
    user_id: str
    role: str
    department: str | None
    user_type: str = "internal"

    def __post_init__(self) -> None:
        valid_roles = {"employee", "manager", "admin"}
        if self.user_type not in {"internal", "external"}:
            raise ValueError("user_type must be 'internal' or 'external'")
        if self.user_type == "internal" and self.role not in valid_roles:
            raise ValueError("internal role is invalid")
        if self.user_type == "internal" and not self.department:
            raise ValueError("internal users require a department")


PII_COLUMNS = {
    "employees": {"email", "phone", "address", "salary", "bank_account", "national_id"},
    "customers": {"email", "phone", "address", "national_id", "linked_bank_account"},
}

RESOURCE_CONFIG = {
    "employees": {
        "table": "employees",
        "scope_column": "department_id",
        "id_column": "employee_id",
    },
    "customers": {
        "table": "customers",
        "scope_column": "home_department_owner",
        "id_column": "customer_id",
    },
    "transactions": {
        "table": "transactions",
        "scope_column": "department_owner",
        "id_column": "txn_id",
    },
    "offers": {
        "table": "offers",
        "scope_column": "department_owner",
        "id_column": "offer_id",
    },
    "support_tickets": {
        "table": "support_tickets",
        "scope_column": "department_owner",
        "id_column": "ticket_id",
    },
}


def scoped_select(
    connection: sqlite3.Connection,
    context: UserContext,
    resource: str,
    filters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return rows visible to ``context`` from one allowlisted resource.

    Filters are equality predicates only. The function never accepts SQL from
    the caller, and scope predicates are always added before execution.
    """
    if context.user_type == "external":
        raise AccessDenied("external users cannot access structured data")
    if resource not in RESOURCE_CONFIG:
        raise ValueError(f"unsupported resource: {resource}")

    config = RESOURCE_CONFIG[resource]
    filters = filters or {}
    allowed_filter_columns = {config["id_column"], config["scope_column"]}
    if resource == "employees":
        allowed_filter_columns.add("access_role")
    if resource == "transactions":
        allowed_filter_columns.update({"status", "customer_id"})
    if resource == "offers":
        allowed_filter_columns.update({"visibility", "status"})
    if resource == "support_tickets":
        allowed_filter_columns.update({"status", "assigned_employee_id"})

    unknown_columns = set(filters) - allowed_filter_columns
    if unknown_columns:
        raise ValueError(f"unsupported filter columns: {sorted(unknown_columns)}")

    where = ["1 = 1"]
    values: list[Any] = []
    if context.role == "admin":
        if resource == "offers":
            where.append("visibility IN ('public', 'all_internal')")
    else:
        where.append(f"{config['scope_column']} = ?")
        values.append(context.department)

    for column, value in filters.items():
        where.append(f"{column} = ?")
        values.append(value)

    query = f"SELECT * FROM {config['table']} WHERE {' AND '.join(where)}"
    rows = [dict(row) for row in connection.execute(query, values).fetchall()]

    for row in rows:
        can_view_own_pii = resource == "employees" and (
            context.role != "admin" and row[config["id_column"]] == context.user_id
        )
        if not can_view_own_pii:
            for column in PII_COLUMNS.get(resource, set()):
                if column in row:
                    row[column] = "[MASKED]"

    return rows

