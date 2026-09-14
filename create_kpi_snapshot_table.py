"""
Create workspace.otm.kpi_snapshots table
=========================================
Stores one KPI snapshot row per capture event.

- 8 synthetic rows are pre-seeded by seed_kpi_history.py to simulate a
  7-day degradation trend ending at the current "live" state (74% overall).
- The only time new rows are added during the demo is when the Remediation
  Agent (ST-8) applies a fix and calls POST /api/snapshot — this appends a
  "Post-fix" row so the sparkline shows the improvement.

Usage:
    python create_kpi_snapshot_table.py
"""

import os
from databricks import sql
from dotenv import load_dotenv

load_dotenv()

conn = sql.connect(
    server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
    http_path=os.getenv("DATABRICKS_HTTP_PATH"),
    access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
)
cursor = conn.cursor()

create_sql = """
CREATE TABLE IF NOT EXISTS workspace.otm.kpi_snapshots (
    snapshot_id     BIGINT GENERATED ALWAYS AS IDENTITY,
    captured_at     TIMESTAMP,
    label           STRING,

    -- Aggregate scores
    overall_score   DOUBLE,
    pillar_join     DOUBLE,
    pillar_comp     DOUBLE,
    pillar_cons     DOUBLE,
    pillar_time     DOUBLE,
    pillar_ref      DOUBLE,

    -- Join Integrity KPIs
    ji01            DOUBLE,
    ji02            DOUBLE,
    ji03            DOUBLE,

    -- Completeness KPIs
    cp01            DOUBLE,
    cp02            DOUBLE,
    cp05            DOUBLE,

    -- Consistency KPIs
    cs01            DOUBLE,
    cs02            DOUBLE,
    cs07            DOUBLE,

    -- Referential Integrity KPIs
    ri01            DOUBLE,
    ri05            DOUBLE,

    -- Timeliness KPI
    tp01            DOUBLE,

    -- Business KPIs (populated after ST-4; nullable until then)
    biz01           DOUBLE,
    biz02           DOUBLE,
    biz03           DOUBLE
)
"""

print("Creating table workspace.otm.kpi_snapshots ...")
cursor.execute(create_sql)
print("[SUCCESS] Table workspace.otm.kpi_snapshots created (or already exists)")

# Verify
cursor.execute("SHOW TABLES IN workspace.otm")
rows = cursor.fetchall()
print(f"\nTables in workspace.otm ({len(rows)} total):")
print("-" * 40)
for r in rows:
    print(f"  - {r[1]}")

cursor.close()
conn.close()
