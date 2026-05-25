"""Quick exploration of the Census dataset."""
from dotenv import load_dotenv
load_dotenv()

import snowflake.connector
import os

conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
)
cur = conn.cursor()

DB = "US_CENSUS_DATA__DEMOGRAPHIC_INSIGHTS__FREE_DATASET"

print(f"=== SCHEMAS in {DB} ===")
cur.execute(f"SHOW SCHEMAS IN DATABASE {DB}")
schemas = cur.fetchall()
for r in schemas:
    print(f"  {r[1]}")

print()
for schema_row in schemas:
    schema_name = schema_row[1]
    if schema_name in ("INFORMATION_SCHEMA",):
        continue
    print(f"=== TABLES in {DB}.{schema_name} ===")
    cur.execute(f"SHOW TABLES IN {DB}.{schema_name}")
    tables = cur.fetchall()
    for t in tables:
        print(f"  {t[1]}")

    print()
    for t in tables:
        tname = t[1]
        print(f"--- COLUMNS: {tname} ---")
        cur.execute(f"SELECT * FROM {DB}.{schema_name}.{tname} LIMIT 1")
        if cur.description:
            for col in cur.description:
                print(f"  {col[0]} ({col[1].__name__ if hasattr(col[1], '__name__') else col[1]})")

        print(f"--- SAMPLE ROW ---")
        row = cur.fetchone()
        if row:
            for i, col in enumerate(cur.description):
                print(f"  {col[0]}: {row[i]}")
        print()

cur.close()
conn.close()
