"""Streamlit interface for the FinPay access-controlled chatbot."""

from pathlib import Path
import os
import sqlite3
from typing import Any

import chromadb
import streamlit as st
from dotenv import load_dotenv

from src.finpay.access.scoped_query import UserContext
from src.finpay.graph.llm import GroqLLM
from src.finpay.graph.workflow import build_graph


ROOT_DIR = Path(__file__).resolve().parent
# Keep runtime paths relative to the repository so the app works on any machine.
DB_PATH = ROOT_DIR / "data" / "db" / "finpay_poc.db"
CHROMA_DIR = ROOT_DIR / "data" / "chroma"
load_dotenv(ROOT_DIR / ".env")


@st.cache_resource
def create_database_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database not found at {DB_PATH}. Run data/scripts/seed_data.py first."
        )
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


@st.cache_resource
def create_chroma_client() -> Any:
    host = os.getenv("CHROMA_HOST")
    if host:
        try:
            # Prefer the shared Chroma server when it is reachable.
            client = chromadb.HttpClient(
                host=host,
                port=int(os.getenv("CHROMA_PORT", "8000")),
            )
            client.heartbeat()
            return client
        except Exception:
            # Local persistent storage keeps the POC usable without a server.
            pass
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


@st.cache_resource
def create_llm() -> GroqLLM:
    return GroqLLM()


def employee_options(connection: sqlite3.Connection, department: str, role: str) -> list[tuple[str, str]]:
    if role == "external":
        return [("anonymous", "External user")]
    rows = connection.execute(
        """
        SELECT employee_id, full_name
        FROM employees
        WHERE department_id = ? AND access_role = ?
        ORDER BY employee_id
        """,
        (department, role),
    ).fetchall()
    return [(row["employee_id"], f'{row["employee_id"]} - {row["full_name"]}') for row in rows]


def build_user_context(
    user_type: str,
    role: str,
    department: str | None,
    user_id: str,
) -> UserContext:
    # External identity is fixed here; chat text cannot turn into an employee.
    if user_type == "external":
        return UserContext("anonymous", "", None, "external")
    return UserContext(user_id, role, department)


def main() -> None:
    st.set_page_config(page_title="FinPay AI", page_icon="F", layout="wide")
    st.title("FinPay AI")
    st.caption("Access-controlled policy and operations assistant")

    try:
        connection = create_database_connection()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("Session")
        user_type = st.selectbox("User type", ["internal", "external"])
        if user_type == "external":
            role = ""
            department = None
            selected_user_id = "anonymous"
            st.caption("Public policies only")
        else:
            role = st.selectbox("Role", ["employee", "manager", "admin"])
            departments = [
                row["department_id"]
                for row in connection.execute(
                    "SELECT department_id FROM departments ORDER BY department_id"
                ).fetchall()
            ]
            department = st.selectbox("Department", departments)
            options = employee_options(connection, department, role)
            if not options:
                st.error("No demo user exists for this role and department.")
                st.stop()
            selected_user_id = st.selectbox(
                "User", [user_id for user_id, _ in options],
                format_func=lambda user_id: dict(options)[user_id],
            )

        resource = st.selectbox(
            "Structured-data resource",
            ["employees", "customers", "transactions", "offers", "support_tickets"],
        )
        st.caption("The resource is passed to the scoped application tool, not chosen by SQL.")

    # Build trusted session identity once before any message reaches the graph.
    context = build_user_context(user_type, role, department, selected_user_id)
    try:
        chroma_client = create_chroma_client()
        llm = create_llm()
        graph = build_graph(
            connection=connection,
            chroma_client=chroma_client,
            llm=llm,
        )
    except Exception as exc:
        st.error(f"Application setup failed: {exc}")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about a policy or authorized data"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # The graph receives identity and the selected resource separately from
        # the natural-language request, preserving the authorization boundary.
        state = {
            "user_context": context,
            "user_message": prompt,
            "resource": resource,
        }
        try:
            result = graph.invoke(state)
            response = result.get("response", "No response was generated.")
        except Exception as exc:
            response = f"The request could not be completed: {exc}"

        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)


if __name__ == "__main__":
    main()
