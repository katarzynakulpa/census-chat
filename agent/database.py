"""Snowflake database connection and query execution module.

Handles all interactions with the Snowflake US Census dataset:
- Connection management
- Schema discovery and caching
- Read-only query execution with timeout and row limits
"""

import logging
import os
from typing import Any

import snowflake.connector

logger = logging.getLogger(__name__)

MAX_ROWS = 500
QUERY_TIMEOUT_SECONDS = 30


def get_connection_params() -> dict[str, str]:
    """Build Snowflake connection parameters from environment / Streamlit secrets."""
    try:
        import streamlit as st

        secrets = st.secrets.get("snowflake", {})
    except Exception:
        secrets = {}

    return {
        "account": secrets.get("account") or os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        "user": secrets.get("user") or os.environ.get("SNOWFLAKE_USER", ""),
        "password": secrets.get("password") or os.environ.get("SNOWFLAKE_PASSWORD", ""),
        "warehouse": secrets.get("warehouse") or os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": secrets.get("database") or os.environ.get("SNOWFLAKE_DATABASE", "GLOBAL_GOVERNMENT"),
        "schema": secrets.get("schema") or os.environ.get("SNOWFLAKE_SCHEMA", "CYBERSYN"),
    }


def get_connection() -> snowflake.connector.SnowflakeConnection:
    """Create a new Snowflake connection."""
    params = get_connection_params()
    if not params["account"] or not params["user"]:
        raise ConnectionError(
            "Snowflake credentials are not configured. "
            "Set them via environment variables or Streamlit secrets."
        )
    return snowflake.connector.connect(**params)


def discover_schema(conn: snowflake.connector.SnowflakeConnection) -> str:
    """Discover available tables and their columns. Returns a formatted schema string
    suitable for inclusion in an LLM prompt."""
    cur = conn.cursor()
    try:
        cur.execute("SHOW TABLES IN SCHEMA")
        tables = cur.fetchall()

        schema_parts: list[str] = []
        for table_row in tables:
            table_name = table_row[1]  # name is typically column index 1
            schema_parts.append(f"\n-- Table: {table_name}")

            cur.execute(f"SHOW COLUMNS IN TABLE {table_name}")
            columns = cur.fetchall()
            col_descriptions = []
            for col in columns:
                col_name = col[2]  # column_name
                col_type = col[3]  # data_type — may be JSON string
                col_descriptions.append(f"  {col_name} ({col_type})")
            schema_parts.append("\n".join(col_descriptions))

            # Sample a few rows to show the LLM what data looks like
            cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
            sample_rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]
            if sample_rows:
                schema_parts.append(f"  -- Sample ({', '.join(col_names)}):")
                for row in sample_rows:
                    schema_parts.append(f"  -- {row}")

        return "\n".join(schema_parts)
    finally:
        cur.close()


def execute_query(
    conn: snowflake.connector.SnowflakeConnection,
    sql: str,
) -> dict[str, Any]:
    """Execute a read-only SQL query and return results as a dict.

    Returns:
        {"columns": [...], "rows": [...], "row_count": int, "truncated": bool}

    Raises:
        ValueError: If the query attempts to modify data.
        RuntimeError: If the query fails.
    """
    _validate_read_only(sql)

    cur = conn.cursor()
    try:
        cur.execute(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {QUERY_TIMEOUT_SECONDS}")
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS + 1)

        truncated = len(rows) > MAX_ROWS
        if truncated:
            rows = rows[:MAX_ROWS]

        # Convert to serializable types
        serializable_rows = []
        for row in rows:
            serializable_rows.append([_serialize_value(v) for v in row])

        return {
            "columns": columns,
            "rows": serializable_rows,
            "row_count": len(serializable_rows),
            "truncated": truncated,
        }
    except snowflake.connector.errors.ProgrammingError as e:
        raise RuntimeError(f"Query execution failed: {e}") from e
    finally:
        cur.close()


def _validate_read_only(sql: str) -> None:
    """Reject any SQL that could modify data."""
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE"]
    sql_upper = sql.upper().strip()
    for keyword in forbidden:
        if sql_upper.startswith(keyword):
            raise ValueError(f"Only SELECT queries are allowed. Detected forbidden keyword: {keyword}")


def _serialize_value(value: Any) -> Any:
    """Convert Snowflake types to JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)
