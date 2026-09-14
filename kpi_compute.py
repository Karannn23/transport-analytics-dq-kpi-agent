"""
Transport Analytics Data Quality KPI Compute Script
=====================================
Queries workspace.otm (ORDER, ORDER_SHIPMENT, SHIPMENT) and computes
all live DQ KPIs used in the Transport Analytics Live Data Quality Dashboard.

Tables:
  - workspace.otm.order
  - workspace.otm.order_shipment
  - workspace.otm.shipment

Requirements:
    pip install databricks-sql-connector python-dotenv
"""

from dotenv import load_dotenv
import os
from databricks import sql

load_dotenv()

conn = sql.connect(
    server_hostname=os.getenv('DATABRICKS_SERVER_HOSTNAME'),
    http_path=os.getenv('DATABRICKS_HTTP_PATH'),
    access_token=os.getenv('DATABRICKS_ACCESS_TOKEN')
)
cursor = conn.cursor()

def q(sql_str):
    cursor.execute(sql_str)
    return cursor.fetchall()

def pct(n, d):
    return round(n / d * 100, 1) if d else 0

# ── Row counts ─────────────────────────────────────────────────────────────
total_orders = q("SELECT COUNT(*) FROM workspace.otm.order")[0][0]
total_os     = q("SELECT COUNT(*) FROM workspace.otm.order_shipment")[0][0]
total_shp    = q("SELECT COUNT(*) FROM workspace.otm.shipment")[0][0]

print("=" * 60)
print("TRANSPORT ANALYTICS DATA QUALITY KPI REPORT")
print("=" * 60)
print(f"  workspace.otm.order          : {total_orders} rows")
print(f"  workspace.otm.order_shipment : {total_os} rows")
print(f"  workspace.otm.shipment       : {total_shp} rows")
print()

# ── JOIN INTEGRITY ─────────────────────────────────────────────────────────
# JI-01: Orders with at least 1 active OS row
ji01 = q("""
    SELECT COUNT(DISTINCT o.order_release_gid)
    FROM workspace.otm.order o
    JOIN workspace.otm.order_shipment os
      ON o.order_release_gid = os.order_release_gid
    WHERE os.lake_status = 'Active'
""")[0][0]

# JI-02: Orphan OS rows (no matching ORDER)
ji02 = q("""
    SELECT COUNT(*) FROM workspace.otm.order_shipment os
    LEFT JOIN workspace.otm.order o
      ON os.order_release_gid = o.order_release_gid
    WHERE o.order_release_gid IS NULL
""")[0][0]

# JI-03: OS rows resolving to a SHIPMENT
ji03 = q("""
    SELECT COUNT(*) FROM workspace.otm.order_shipment os
    JOIN workspace.otm.shipment s ON os.shipment_gid = s.shipment_gid
""")[0][0]

print("JOIN INTEGRITY")
print(f"  JI-01 Order-to-Shipment Match Rate    : {ji01}/{total_orders} = {pct(ji01, total_orders)}%  (Target ≥ 98%)")
print(f"  JI-02 Orphan Order_Shipment Rate       : {ji02}/{total_os} = {pct(ji02, total_os)}%  (Target ≤ 1%)")
print(f"  JI-03 Shipment Execution Match Rate    : {ji03}/{total_os} = {pct(ji03, total_os)}%  (Target ≥ 98%)")
print()

# ── COMPLETENESS ───────────────────────────────────────────────────────────
cp01 = q("SELECT COUNT(*) FROM workspace.otm.order WHERE order_release_gid IS NULL")[0][0]
cp02 = q("SELECT COUNT(*) FROM workspace.otm.shipment WHERE shipment_gid IS NULL")[0][0]
cp04 = q("SELECT COUNT(*) FROM workspace.otm.shipment WHERE planned_pickup IS NULL OR planned_delivery IS NULL")[0][0]
cp05_denom = q("SELECT COUNT(*) FROM workspace.otm.shipment WHERE status NOT IN ('Cancelled','Planned')")[0][0]
cp05_num   = q("SELECT COUNT(*) FROM workspace.otm.shipment WHERE status NOT IN ('Cancelled','Planned') AND actual_arrival IS NULL")[0][0]

print("COMPLETENESS")
print(f"  CP-01 Order Release GID Null Rate      : {cp01}/{total_orders} = {pct(cp01, total_orders)}%  (Target = 0%)")
print(f"  CP-02 Shipment GID Null Rate           : {cp02}/{total_shp} = {pct(cp02, total_shp)}%  (Target = 0%)")
print(f"  CP-04 Planned Dates Null Rate          : {cp04}/{total_shp} = {pct(cp04, total_shp)}%  (Target ≤ 1%)")
print(f"  CP-05 Actual Arrival Null Rate         : {cp05_num}/{cp05_denom} = {pct(cp05_num, cp05_denom)}%  (Target ≤ 3%)")
print()

# ── CONSISTENCY ────────────────────────────────────────────────────────────
# CS-07: Ghost mapping — orders with multiple distinct active shipment_gids
cs07 = q("""
    SELECT COUNT(*) FROM (
        SELECT order_release_gid
        FROM workspace.otm.order_shipment
        WHERE lake_status = 'Active'
        GROUP BY order_release_gid
        HAVING COUNT(DISTINCT shipment_gid) > 1
    ) x
""")[0][0]

# CS-01: Weight mismatch — SUM(OS qty) vs ORDER weight (tolerance ±5%)
cs01 = q("""
    SELECT COUNT(*) FROM (
        SELECT o.order_release_gid
        FROM workspace.otm.order o
        JOIN workspace.otm.order_shipment os
          ON o.order_release_gid = os.order_release_gid
        WHERE os.lake_status = 'Active'
        GROUP BY o.order_release_gid, o.total_weight_kg
        HAVING ABS(SUM(os.quantity_kg) - o.total_weight_kg) > (o.total_weight_kg * 0.05)
    ) x
""")[0][0]

# CS-02: Date sequence violations (arrival before departure)
cs02 = q("""
    SELECT COUNT(*) FROM workspace.otm.shipment
    WHERE actual_departure IS NOT NULL
      AND actual_arrival IS NOT NULL
      AND actual_arrival < actual_departure
""")[0][0]

print("CONSISTENCY")
print(f"  CS-07 Ghost Mapping Rate (★ Critical)  : {cs07}/{total_orders} = {pct(cs07, total_orders)}%  (Target = 0%)")
print(f"  CS-01 Weight Mismatch Rate             : {cs01}/{total_orders} = {pct(cs01, total_orders)}%  (Target ≤ 2%)")
print(f"  CS-02 Date Sequence Violation Rate     : {cs02}/{total_shp} = {pct(cs02, total_shp)}%  (Target = 0%)")
print()

# ── REFERENTIAL INTEGRITY ──────────────────────────────────────────────────
# RI-01: Invalid shipment status
ri01 = q("""
    SELECT COUNT(*) FROM workspace.otm.shipment
    WHERE status NOT IN ('Planned','In Transit','Delivered','Closed','Cancelled')
""")[0][0]

# RI-05: Zero / negative weight
ri05_ord = q("SELECT COUNT(*) FROM workspace.otm.order WHERE total_weight_kg <= 0")[0][0]
ri05_shp = q("SELECT COUNT(*) FROM workspace.otm.shipment WHERE weight_kg <= 0")[0][0]

print("REFERENTIAL INTEGRITY")
print(f"  RI-01 Invalid Shipment Status Rate     : {ri01}/{total_shp} = {pct(ri01, total_shp)}%  (Target = 0%)")
print(f"  RI-05 Zero Weight Orders               : {ri05_ord}/{total_orders} = {pct(ri05_ord, total_orders)}%  (Target = 0%)")
print(f"  RI-05 Zero Weight Shipments            : {ri05_shp}/{total_shp} = {pct(ri05_shp, total_shp)}%  (Target = 0%)")
print()

# ── BREAKDOWN SUMMARIES ────────────────────────────────────────────────────
print("ORDER STATUS BREAKDOWN")
for row in q("SELECT order_status, COUNT(*) FROM workspace.otm.order GROUP BY order_status ORDER BY 2 DESC"):
    print(f"  {row[0]:<20} : {row[1]}")

print("\nORDER DQ FLAG BREAKDOWN")
for row in q("SELECT dq_flag, COUNT(*) FROM workspace.otm.order GROUP BY dq_flag ORDER BY 2 DESC"):
    print(f"  {row[0]:<30} : {row[1]}")

print("\nSHIPMENT STATUS BREAKDOWN")
for row in q("SELECT status, COUNT(*) FROM workspace.otm.shipment GROUP BY status ORDER BY 2 DESC"):
    print(f"  {row[0]:<20} : {row[1]}")

print("\nSHIPMENT DQ FLAG BREAKDOWN")
for row in q("SELECT dq_flag, COUNT(*) FROM workspace.otm.shipment GROUP BY dq_flag ORDER BY 2 DESC"):
    print(f"  {row[0]:<40} : {row[1]}")

print("\nORDER_SHIPMENT DQ FLAG BREAKDOWN")
for row in q("SELECT dq_flag, COUNT(*) FROM workspace.otm.order_shipment GROUP BY dq_flag ORDER BY 2 DESC"):
    print(f"  {row[0]:<40} : {row[1]}")

print("\n" + "=" * 60)
print("[SUCCESS] KPI compute complete")
print("=" * 60)

cursor.close()
conn.close()
