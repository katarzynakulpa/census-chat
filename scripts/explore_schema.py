"""Utility script to explore the Snowflake Census dataset schema.

Run this after setting up your Snowflake credentials to discover
available tables, columns, and sample data. Use the output to refine
prompts and understand what questions the agent can answer.

Usage:
    python -m scripts.explore_schema
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from agent.database import get_connection, discover_schema


def main():
    print("Connecting to Snowflake...")
    conn = get_connection()
    print("Connected!\n")

    print("=" * 80)
    print("SCHEMA DISCOVERY")
    print("=" * 80)

    schema = discover_schema(conn)
    print(schema)

    # Also list all databases and schemas for orientation
    print("\n" + "=" * 80)
    print("AVAILABLE DATABASES")
    print("=" * 80)
    cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    for row in cur.fetchall():
        print(f"  {row[1]}")

    print("\n" + "=" * 80)
    print("SCHEMAS IN CURRENT DATABASE")
    print("=" * 80)
    cur.execute("SHOW SCHEMAS")
    for row in cur.fetchall():
        print(f"  {row[1]}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
