"""
Transport Analytics Live Data Quality Dashboard — Flask Backend
================================================
Serves the dashboard HTML and the following API endpoints:

  GET  /api/kpis         — Live KPI computation from Databricks
  GET  /api/history      — KPI snapshot history (pre-seeded + post-fix rows)
  POST /api/snapshot     — Capture a new KPI snapshot (called after a fix)

Usage:
    pip install flask databricks-sql-connector python-dotenv requests
    python create_kpi_snapshot_table.py   # one-time setup
    python seed_kpi_history.py            # one-time seed
    python app.py
Then open: http://localhost:5000
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from databricks import sql
from dotenv import load_dotenv

load_dotenv()

_conn = None
_cursor = None


def get_cursor():
    """Return a live Databricks cursor, reconnecting if the connection went stale.

    The module-level cursor is reused across requests for speed, but Databricks
    SQL warehouse connections can time out after ~1 hour of inactivity.  We
    detect that with a lightweight probe and reconnect transparently so the
    dashboard never shows a stale-connection error after the warehouse idles.
    """
    global _conn, _cursor
    if _cursor is not None:
        # Probe: run a trivial query — if it fails the connection is stale
        try:
            _cursor.execute("SELECT 1")
            _cursor.fetchone()
            return _cursor
        except Exception:
            # Connection is dead — fall through and reconnect
            try:
                _cursor.close()
            except Exception:
                pass
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
            _cursor = None
    try:
        _conn = sql.connect(
            server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
        )
        _cursor = _conn.cursor()
        return _cursor
    except Exception:
        _conn = None
        _cursor = None
        raise


app = Flask(__name__, static_folder=".", static_url_path="")


def pct(n, d):
    return round(n / d * 100, 1) if d else 0



def kpi_score(value, target_val, higher_is_better):
    if higher_is_better:
        # e.g. JI-01 target 98%, actual 94% → 94/98*100 = 95.9, capped at 100
        return min(round(value / target_val * 100, 1), 100) if target_val else 100
    else:
        # Meeting or beating target → 100 (perfect)
        if value <= target_val:
            return 100
        # Zero-tolerance KPIs (target=0): any breach → score scales from 100 down to 0
        # e.g. CS-07=3% → 100 - 3*10 = 70; RI-05=6% → 100 - 6*10 = 40
        # Non-zero target: each 1% above target costs 10 points, floored at 0
        return max(round(100 - (value - target_val) * 10, 1), 0)



@app.route("/")
def index():
    return send_from_directory(".", "otm_live_dashboard.html")


@app.route("/api/kpis")
def kpis():
    try:
        cursor = get_cursor()

        def q(sql_str):
            cursor.execute(sql_str)
            return cursor.fetchall()

        # ── All counts + all KPI numerators in one CTE query ─────────────────
        row = q("""
WITH
  order_cte AS (SELECT * FROM workspace.otm.order),
  os_cte    AS (SELECT * FROM workspace.otm.order_shipment),
  shp_cte   AS (SELECT * FROM workspace.otm.shipment),

  counts AS (
    SELECT
      (SELECT COUNT(*) FROM order_cte)                                     AS total_orders,
      (SELECT COUNT(*) FROM os_cte)                                        AS total_os,
      (SELECT COUNT(*) FROM shp_cte)                                       AS total_shp
  ),

  kpis AS (
    SELECT
      -- JI-01: orders with at least 1 active OS row
      (SELECT COUNT(DISTINCT o.order_release_gid)
       FROM order_cte o JOIN os_cte os ON o.order_release_gid = os.order_release_gid
       WHERE os.lake_status = 'Active')                                     AS ji01,

      -- JI-02: orphan OS rows
      (SELECT COUNT(*) FROM os_cte os
       LEFT JOIN order_cte o ON os.order_release_gid = o.order_release_gid
       WHERE o.order_release_gid IS NULL)                                   AS ji02,

      -- JI-03: OS rows resolving to a shipment
      (SELECT COUNT(*) FROM os_cte os
       JOIN shp_cte s ON os.shipment_gid = s.shipment_gid)                 AS ji03,

      -- CP-01: null order_release_gid
      (SELECT COUNT(*) FROM order_cte WHERE order_release_gid IS NULL)     AS cp01,

      -- CP-02: null shipment_gid
      (SELECT COUNT(*) FROM shp_cte WHERE shipment_gid IS NULL)            AS cp02,

      -- CP-05 denom: non-cancelled, non-planned shipments
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Cancelled','Planned'))                         AS cp05_denom,

      -- CP-05 num: missing actual_arrival
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Cancelled','Planned') AND actual_arrival IS NULL) AS cp05_num,

      -- CS-07: ghost mapping
      (SELECT COUNT(*) FROM (
         SELECT order_release_gid FROM os_cte
         WHERE lake_status = 'Active'
         GROUP BY order_release_gid HAVING COUNT(DISTINCT shipment_gid) > 1
       ) x)                                                                 AS cs07,

      -- CS-01: weight mismatch
      (SELECT COUNT(*) FROM (
         SELECT o.order_release_gid
         FROM order_cte o JOIN os_cte os ON o.order_release_gid = os.order_release_gid
         WHERE os.lake_status = 'Active'
         GROUP BY o.order_release_gid, o.total_weight_kg
         HAVING ABS(SUM(os.quantity_kg) - o.total_weight_kg) > (o.total_weight_kg * 0.05)
       ) x)                                                                 AS cs01,

      -- CS-02: date sequence violation
      (SELECT COUNT(*) FROM shp_cte
       WHERE actual_departure IS NOT NULL AND actual_arrival IS NOT NULL
         AND actual_arrival < actual_departure)                             AS cs02,

      -- RI-01: invalid shipment status
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Planned','In Transit','Delivered','Closed','Cancelled')) AS ri01,

      -- RI-05: zero/negative weight orders
      (SELECT COUNT(*) FROM order_cte WHERE total_weight_kg <= 0)          AS ri05_ord,

      -- RI-05 shp: zero/negative weight shipments (for entity scoring)
      (SELECT COUNT(*) FROM shp_cte WHERE weight_kg <= 0)                  AS ri05_shp,

      -- TP-01: late deliveries (actual_arrival after planned_delivery)
      (SELECT COUNT(*) FROM shp_cte
       WHERE actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL
         AND actual_arrival > planned_delivery)                             AS tp01,

      -- BIZ-01: on-time deliveries (Closed shipments where actual_arrival <= planned_delivery)
      (SELECT COUNT(*) FROM shp_cte
       WHERE status = 'Closed'
         AND actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL
         AND actual_arrival <= planned_delivery)                            AS biz01_num,

      -- BIZ-01 denominator: all Closed shipments with date data
      (SELECT COUNT(*) FROM shp_cte
       WHERE status = 'Closed'
         AND actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL)   AS biz01_den,

      -- BIZ-02: zero-weight orders (exposed separately as a business KPI)
      -- Note: same as ri05_ord — aliased here for clarity in the BIZ pillar
      (SELECT COUNT(*) FROM order_cte WHERE total_weight_kg <= 0)          AS biz02_num,

      -- BIZ-03: re-assigned OS rows (planning quality indicator)
      (SELECT COUNT(*) FROM os_cte WHERE dq_flag = 'Re-assigned')          AS biz03_num
  )

SELECT
  c.total_orders, c.total_os, c.total_shp,
  k.ji01, k.ji02, k.ji03,
  k.cp01, k.cp02, k.cp05_denom, k.cp05_num,
  k.cs07, k.cs01, k.cs02,
  k.ri01, k.ri05_ord, k.ri05_shp, k.tp01,
  k.biz01_num, k.biz01_den, k.biz02_num, k.biz03_num
FROM counts c, kpis k
        """)[0]
        total_orders = row[0]
        total_os     = row[1]
        total_shp    = row[2]
        ji01         = row[3]
        ji02         = row[4]
        ji03         = row[5]
        cp01         = row[6]
        cp02         = row[7]
        cp05_denom   = row[8]
        cp05_num     = row[9]
        cs07         = row[10]
        cs01         = row[11]
        cs02         = row[12]
        ri01         = row[13]
        ri05_ord     = row[14]
        ri05_shp     = row[15]
        tp01         = row[16]
        biz01_num    = row[17]
        biz01_den    = row[18]
        biz02_num    = row[19]
        biz03_num    = row[20]

        # ── BREAKDOWN SUMMARIES ─────────────────────────────────────────────
        order_status_rows = q("SELECT order_status, COUNT(*) FROM workspace.otm.order GROUP BY order_status ORDER BY 2 DESC")
        order_dq_rows     = q("SELECT dq_flag, COUNT(*) FROM workspace.otm.order GROUP BY dq_flag ORDER BY 2 DESC")
        os_dq_rows        = q("SELECT dq_flag, COUNT(*) FROM workspace.otm.order_shipment GROUP BY dq_flag ORDER BY 2 DESC")
        shp_status_rows   = q("SELECT status, COUNT(*) FROM workspace.otm.shipment GROUP BY status ORDER BY 2 DESC")
        shp_dq_rows       = q("SELECT dq_flag, COUNT(*) FROM workspace.otm.shipment GROUP BY dq_flag ORDER BY 2 DESC")

        # ── ENTITY DQ SCORES ────────────────────────────────────────────────
        # Cross-validated from live KPI variables (no dq_flag queries)

        # ORDER score: penalise orders with zero weight, ghost mapping, or no shipment assignment
        orders_bad_live = ri05_ord + cs07 + (total_orders - ji01)
        # Clamp to avoid double-counting (some orders may have multiple issues)
        orders_bad_live = min(orders_bad_live, total_orders)
        order_score = round(pct(total_orders - orders_bad_live, total_orders), 1)

        # ORDER_SHIPMENT score: penalise orphan rows and stale-delete ghost rows
        os_bad_live = ji02 + cs07  # orphans + orders with ghost OS rows
        os_bad_live = min(os_bad_live, total_os)
        os_score = round(pct(total_os - os_bad_live, total_os), 1)

        # SHIPMENT score: penalise invalid status, date seq violations, zero weight shipments
        shp_bad_live = ri01 + cs02 + ri05_shp
        shp_bad_live = min(shp_bad_live, total_shp)
        shp_score = round(pct(total_shp - shp_bad_live, total_shp), 1)

        # ── PILLAR SCORES (proportional: % of records that are clean) ───────
        # Join Integrity: match rate, inverse orphan rate, execution rate
        join_score = round((pct(ji01, total_orders) + (100 - pct(ji02, total_os)) + pct(ji03, total_os)) / 3)

        # Completeness: inverse null rates for each field
        completeness_score = round(((100 - pct(cp01, total_orders)) + (100 - pct(cp02, total_shp)) + (100 - pct(cp05_num, cp05_denom))) / 3)

        # Consistency: ghost-free %, weight-match %, date-seq-clean %
        consistency_score = round(((100 - pct(cs07, total_orders)) + (100 - pct(cs01, total_orders)) + (100 - pct(cs02, total_shp))) / 3)

        # Referential: invalid-status-free %, zero-weight-free %
        referential_score = round(((100 - pct(ri01, total_shp)) + (100 - pct(ri05_ord, total_orders))) / 2)

        # Timeliness: late delivery rate
        timeliness_score = round(100 - pct(tp01, cp05_denom))

        # Business Performance pillar
        biz01_pct = pct(biz01_num, biz01_den)  # On-Time Delivery % (higher is better)
        biz02_pct = pct(biz02_num, total_orders)  # Zero-Weight Order Rate (lower is better)
        biz03_pct = pct(biz03_num, total_os)     # Re-Assignment Rate (lower is better)
        business_score = round(
            (kpi_score(biz01_pct, 95, True) +
             kpi_score(biz02_pct,  0, False) +
             kpi_score(biz03_pct,  2, False)) / 3
        )

        # ── OVERALL SCORE (15 KPIs) ───────────────────────────────────────────
        # Each KPI scores 100 if it meets its target, or scales down proportionally
        # if it misses. This ensures RED KPIs meaningfully drag the overall down.
        kpi_scores = [
            kpi_score(pct(ji01, total_orders),    98, True),   # JI-01
            kpi_score(pct(ji02, total_os),          1, False),  # JI-02
            kpi_score(pct(ji03, total_os),         98, True),   # JI-03
            kpi_score(pct(cp01, total_orders),      0, False),  # CP-01
            kpi_score(pct(cp02, total_shp),         0, False),  # CP-02
            kpi_score(pct(cp05_num, cp05_denom),    3, False),  # CP-05
            kpi_score(pct(cs07, total_orders),      0, False),  # CS-07
            kpi_score(pct(cs01, total_orders),      2, False),  # CS-01
            kpi_score(pct(cs02, total_shp),         0, False),  # CS-02
            kpi_score(pct(ri01, total_shp),         0, False),  # RI-01
            kpi_score(pct(ri05_ord, total_orders),  0, False),  # RI-05
            kpi_score(pct(tp01, cp05_denom),        0, False),  # TP-01
            kpi_score(biz01_pct,                   95, True),   # BIZ-01
            kpi_score(biz02_pct,                    0, False),  # BIZ-02
            kpi_score(biz03_pct,                    2, False),  # BIZ-03
        ]
        overall_score = round(sum(kpi_scores) / len(kpi_scores))

        return jsonify({
            "computed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "counts": {
                "orders": total_orders,
                "order_shipments": total_os,
                "shipments": total_shp,
            },
            "overall_score": overall_score,
            "pillar_scores": {
                "join_integrity":  join_score,
                "completeness":    completeness_score,
                "consistency":     consistency_score,
                "timeliness":      timeliness_score,
                "referential":     referential_score,
                "business":        business_score,
            },
            "entity_scores": {
                "order":           order_score,
                "order_shipment":  os_score,
                "shipment":        shp_score,
            },
            "kpis": {
                "JI01": {"value": pct(ji01, total_orders), "num": ji01, "den": total_orders, "target": "≥ 98%", "target_val": 98, "higher_is_better": True},
                "JI02": {"value": pct(ji02, total_os),     "num": ji02, "den": total_os,     "target": "≤ 1%",  "target_val": 1,  "higher_is_better": False},
                "JI03": {"value": pct(ji03, total_os),     "num": ji03, "den": total_os,     "target": "≥ 98%", "target_val": 98, "higher_is_better": True},
                "CP01": {"value": pct(cp01, total_orders), "num": cp01, "den": total_orders, "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "CP02": {"value": pct(cp02, total_shp),    "num": cp02, "den": total_shp,    "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "CP05": {"value": pct(cp05_num, cp05_denom), "num": cp05_num, "den": cp05_denom, "target": "≤ 3%", "target_val": 3, "higher_is_better": False},
                "CS07": {"value": pct(cs07, total_orders), "num": cs07, "den": total_orders, "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "CS01": {"value": pct(cs01, total_orders), "num": cs01, "den": total_orders, "target": "≤ 2%",  "target_val": 2,  "higher_is_better": False},
                "CS02": {"value": pct(cs02, total_shp),    "num": cs02, "den": total_shp,    "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "RI01": {"value": pct(ri01, total_shp),    "num": ri01, "den": total_shp,    "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "RI05": {"value": pct(ri05_ord, total_orders), "num": ri05_ord, "den": total_orders, "target": "= 0%", "target_val": 0, "higher_is_better": False},
                "TP01":  {"value": pct(tp01, cp05_denom),  "num": tp01,      "den": cp05_denom,    "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "BIZ01": {"value": biz01_pct,               "num": biz01_num, "den": biz01_den,     "target": "≥ 95%", "target_val": 95, "higher_is_better": True},
                "BIZ02": {"value": biz02_pct,               "num": biz02_num, "den": total_orders,  "target": "= 0%",  "target_val": 0,  "higher_is_better": False},
                "BIZ03": {"value": biz03_pct,               "num": biz03_num, "den": total_os,      "target": "≤ 2%",  "target_val": 2,  "higher_is_better": False},
            },
            "breakdowns": {
                "order_status":   [{"label": r[0], "count": r[1]} for r in order_status_rows],
                "order_dq":       [{"label": r[0], "count": r[1]} for r in order_dq_rows],
                "os_dq_flags":    [{"label": r[0], "count": r[1]} for r in os_dq_rows],
                "shipment_status":[{"label": r[0], "count": r[1]} for r in shp_status_rows],
                "shipment_dq":    [{"label": r[0], "count": r[1]} for r in shp_dq_rows],
            },
        })

    except Exception as e:
        print(f"[ERROR /api/kpis] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


# ── Drill-down queries: return up to 50 failing rows per KPI ──────────────
DRILLDOWN_QUERIES = {
    "JI01": """
        SELECT o.order_release_gid, o.order_status, o.dq_flag,
               CAST(o.order_date AS STRING) AS order_date
        FROM workspace.otm.order o
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace.otm.order_shipment os
            WHERE os.order_release_gid = o.order_release_gid
              AND os.lake_status = 'Active'
        )
        LIMIT 50
    """,
    "JI02": """
        SELECT os.os_id, os.order_release_gid, os.shipment_gid,
               os.dq_flag, os.lake_status
        FROM workspace.otm.order_shipment os
        LEFT JOIN workspace.otm.order o
          ON os.order_release_gid = o.order_release_gid
        WHERE o.order_release_gid IS NULL
        LIMIT 50
    """,
    "CS07": """
        SELECT o.order_release_gid, o.order_status,
               COUNT(DISTINCT os.shipment_gid) AS active_shipment_count,
               MIN(os.shipment_gid) AS shipment_gid_sample
        FROM workspace.otm.order o
        JOIN workspace.otm.order_shipment os
          ON o.order_release_gid = os.order_release_gid
        WHERE os.lake_status = 'Active'
        GROUP BY o.order_release_gid, o.order_status
        HAVING COUNT(DISTINCT os.shipment_gid) > 1
        LIMIT 50
    """,
    "CS02": """
        SELECT shipment_gid, status,
               CAST(actual_departure AS STRING) AS actual_departure,
               CAST(actual_arrival   AS STRING) AS actual_arrival,
               dq_flag
        FROM workspace.otm.shipment
        WHERE actual_departure IS NOT NULL AND actual_arrival IS NOT NULL
          AND actual_arrival < actual_departure
        LIMIT 50
    """,
    "RI01": """
        SELECT shipment_gid, status, dq_flag,
               CAST(planned_pickup AS STRING) AS planned_pickup
        FROM workspace.otm.shipment
        WHERE status NOT IN ('Planned','In Transit','Delivered','Closed','Cancelled')
        LIMIT 50
    """,
    "RI05": """
        SELECT order_release_gid, total_weight_kg, order_status, dq_flag,
               CAST(order_date AS STRING) AS order_date
        FROM workspace.otm.order
        WHERE total_weight_kg <= 0
        LIMIT 50
    """,
    "TP01": """
        SELECT shipment_gid, status,
               CAST(planned_delivery  AS STRING) AS planned_delivery,
               CAST(actual_arrival    AS STRING) AS actual_arrival,
               dq_flag
        FROM workspace.otm.shipment
        WHERE actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL
          AND actual_arrival > planned_delivery
        LIMIT 50
    """,
    "BIZ01": """
        SELECT shipment_gid, status,
               CAST(planned_delivery AS STRING) AS planned_delivery,
               CAST(actual_arrival   AS STRING) AS actual_arrival,
               DATEDIFF(actual_arrival, planned_delivery) AS days_early_or_late
        FROM workspace.otm.shipment
        WHERE status = 'Closed'
          AND actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL
          AND actual_arrival <= planned_delivery
        ORDER BY actual_arrival DESC
        LIMIT 50
    """,
    "BIZ02": """
        SELECT order_release_gid, total_weight_kg, order_status, dq_flag,
               CAST(order_date AS STRING) AS order_date
        FROM workspace.otm.order
        WHERE total_weight_kg <= 0
        LIMIT 50
    """,
    "BIZ03": """
        SELECT os_id, order_release_gid, shipment_gid, dq_flag, lake_status
        FROM workspace.otm.order_shipment
        WHERE dq_flag = 'Re-assigned'
        LIMIT 50
    """,
    "CP01": """
        SELECT order_release_gid, order_status, dq_flag,
               CAST(order_date AS STRING) AS order_date
        FROM workspace.otm.order
        WHERE order_release_gid IS NULL
        LIMIT 50
    """,
    "CP02": """
        SELECT shipment_gid, status, dq_flag,
               CAST(planned_pickup AS STRING) AS planned_pickup
        FROM workspace.otm.shipment
        WHERE shipment_gid IS NULL
        LIMIT 50
    """,
    "CP05": """
        SELECT shipment_gid, status,
               CAST(planned_delivery AS STRING) AS planned_delivery,
               CAST(actual_arrival   AS STRING) AS actual_arrival,
               dq_flag
        FROM workspace.otm.shipment
        WHERE status NOT IN ('Cancelled','Planned')
          AND actual_arrival IS NULL
        LIMIT 50
    """,
    "CS01": """
        SELECT o.order_release_gid, o.total_weight_kg AS order_weight_kg,
               SUM(os.quantity_kg) AS shipment_weight_sum_kg,
               ABS(SUM(os.quantity_kg) - o.total_weight_kg) AS discrepancy_kg,
               o.dq_flag
        FROM workspace.otm.order o
        JOIN workspace.otm.order_shipment os
          ON o.order_release_gid = os.order_release_gid
        WHERE os.lake_status = 'Active'
        GROUP BY o.order_release_gid, o.total_weight_kg, o.dq_flag
        HAVING ABS(SUM(os.quantity_kg) - o.total_weight_kg) > (o.total_weight_kg * 0.05)
        LIMIT 50
    """,
}


@app.route("/api/drilldown/<kpi_id>")
def drilldown(kpi_id):
    """Return up to 50 failing records for the given KPI ID.

    Used by the dashboard drill-down modal (ST-5) and the Root-Cause Agent
    (ST-7) to obtain the exact rows causing a KPI to fail.
    """
    kpi_id_upper = kpi_id.upper()
    if kpi_id_upper not in DRILLDOWN_QUERIES:
        return jsonify({"error": f"No drill-down query for KPI '{kpi_id}'"}), 404
    try:
        cursor = get_cursor()
        cursor.execute(DRILLDOWN_QUERIES[kpi_id_upper])
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        records = [dict(zip(columns, row)) for row in rows]
        for rec in records:
            for k, v in rec.items():
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    rec[k] = str(v)
        return jsonify({"kpi_id": kpi_id_upper, "columns": columns, "records": records, "count": len(records)})
    except Exception as e:
        print(f"[ERROR /api/drilldown] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def history():
    """Return all KPI snapshot rows ordered oldest-first.

    The table is small (≤~10 rows at demo time) so no caching or pagination
    is needed. Returns an empty list gracefully if the table has not been
    seeded yet.
    """
    try:
        cursor = get_cursor()
        cursor.execute("""
            SELECT
                snapshot_id, captured_at, label,
                overall_score,
                pillar_join, pillar_comp, pillar_cons, pillar_time, pillar_ref,
                ji01, ji02, ji03, cp01, cp02, cp05,
                cs01, cs02, cs07, ri01, ri05, tp01,
                biz01, biz02, biz03
            FROM workspace.otm.kpi_snapshots
            ORDER BY captured_at ASC
        """)
        rows = cursor.fetchall()
        snapshots = []
        for r in rows:
            snapshots.append({
                "snapshot_id":   r[0],
                "captured_at":   str(r[1]),
                "label":         r[2] or "",
                "overall_score": r[3],
                "pillar_join":   r[4],
                "pillar_comp":   r[5],
                "pillar_cons":   r[6],
                "pillar_time":   r[7],
                "pillar_ref":    r[8],
                "ji01": r[9],  "ji02": r[10], "ji03": r[11],
                "cp01": r[12], "cp02": r[13], "cp05": r[14],
                "cs01": r[15], "cs02": r[16], "cs07": r[17],
                "ri01": r[18], "ri05": r[19], "tp01": r[20],
                "biz01": r[21], "biz02": r[22], "biz03": r[23],
            })
        return jsonify({"snapshots": snapshots, "count": len(snapshots)})
    except Exception as e:
        print(f"[ERROR /api/history] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/snapshot", methods=["POST"])
def snapshot():
    """Capture a new KPI snapshot by re-running the live KPI query.

    Called automatically by the Remediation Agent (ST-8) after a fix is
    applied, so the sparkline gains a 'Post-fix' data point.
    Accepts an optional JSON body: { "label": "Post-fix" }
    """
    try:
        body = request.get_json(silent=True) or {}
        label = body.get("label", "Post-fix")

        cursor = get_cursor()

        # Re-use the same CTE query from /api/kpis to get fresh values
        row = cursor.execute("""
WITH
  order_cte AS (SELECT * FROM workspace.otm.order),
  os_cte    AS (SELECT * FROM workspace.otm.order_shipment),
  shp_cte   AS (SELECT * FROM workspace.otm.shipment),
  counts AS (
    SELECT
      (SELECT COUNT(*) FROM order_cte) AS total_orders,
      (SELECT COUNT(*) FROM os_cte)    AS total_os,
      (SELECT COUNT(*) FROM shp_cte)   AS total_shp
  ),
  kpis AS (
    SELECT
      (SELECT COUNT(DISTINCT o.order_release_gid)
       FROM order_cte o JOIN os_cte os ON o.order_release_gid = os.order_release_gid
       WHERE os.lake_status = 'Active')                                      AS ji01,
      (SELECT COUNT(*) FROM os_cte os
       LEFT JOIN order_cte o ON os.order_release_gid = o.order_release_gid
       WHERE o.order_release_gid IS NULL)                                    AS ji02,
      (SELECT COUNT(*) FROM os_cte os
       JOIN shp_cte s ON os.shipment_gid = s.shipment_gid)                  AS ji03,
      (SELECT COUNT(*) FROM order_cte WHERE order_release_gid IS NULL)      AS cp01,
      (SELECT COUNT(*) FROM shp_cte WHERE shipment_gid IS NULL)             AS cp02,
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Cancelled','Planned'))                          AS cp05_denom,
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Cancelled','Planned') AND actual_arrival IS NULL) AS cp05_num,
      (SELECT COUNT(*) FROM (
         SELECT order_release_gid FROM os_cte WHERE lake_status = 'Active'
         GROUP BY order_release_gid HAVING COUNT(DISTINCT shipment_gid) > 1
       ) x)                                                                  AS cs07,
      (SELECT COUNT(*) FROM (
         SELECT o.order_release_gid
         FROM order_cte o JOIN os_cte os ON o.order_release_gid = os.order_release_gid
         WHERE os.lake_status = 'Active'
         GROUP BY o.order_release_gid, o.total_weight_kg
         HAVING ABS(SUM(os.quantity_kg) - o.total_weight_kg) > (o.total_weight_kg * 0.05)
       ) x)                                                                  AS cs01,
      (SELECT COUNT(*) FROM shp_cte
       WHERE actual_departure IS NOT NULL AND actual_arrival IS NOT NULL
         AND actual_arrival < actual_departure)                              AS cs02,
      (SELECT COUNT(*) FROM shp_cte
       WHERE status NOT IN ('Planned','In Transit','Delivered','Closed','Cancelled')) AS ri01,
      (SELECT COUNT(*) FROM order_cte WHERE total_weight_kg <= 0)           AS ri05_ord,
      (SELECT COUNT(*) FROM shp_cte WHERE weight_kg <= 0)                   AS ri05_shp,
      (SELECT COUNT(*) FROM shp_cte
       WHERE actual_arrival IS NOT NULL AND planned_delivery IS NOT NULL
         AND actual_arrival > planned_delivery)                              AS tp01
  )
SELECT c.total_orders, c.total_os, c.total_shp,
       k.ji01, k.ji02, k.ji03, k.cp01, k.cp02,
       k.cp05_denom, k.cp05_num, k.cs07, k.cs01, k.cs02,
       k.ri01, k.ri05_ord, k.ri05_shp, k.tp01
FROM counts c, kpis k
        """)
        r = cursor.fetchone()

        total_orders, total_os, total_shp = r[0], r[1], r[2]
        ji01     = r[3];  ji02    = r[4];  ji03 = r[5]
        cp01     = r[6];  cp02    = r[7]
        cp05d    = r[8];  cp05n   = r[9]
        cs07     = r[10]; cs01    = r[11]; cs02 = r[12]
        ri01     = r[13]; ri05_ord = r[14]; ri05_shp = r[15]; tp01 = r[16]  # ST-3: read all indices

        # Fetch business KPIs — each computed independently to avoid cross-join inflation
        cursor.execute("""
            SELECT
              COUNT(CASE WHEN actual_arrival <= planned_delivery
                          AND actual_arrival IS NOT NULL
                          AND status = 'Closed' THEN 1 END)  AS biz01_num,
              COUNT(CASE WHEN status = 'Closed' THEN 1 END)  AS biz01_den
            FROM workspace.otm.shipment
        """)
        br1 = cursor.fetchone()
        biz01_num, biz01_den = br1[0] or 0, br1[1] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM workspace.otm.order_shipment
            WHERE dq_flag = 'Re-assigned'
        """)
        biz03_num = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM workspace.otm.order
            WHERE total_weight_kg <= 0
        """)
        biz02_num = cursor.fetchone()[0] or 0

        biz01_pct = pct(biz01_num, biz01_den)
        biz02_pct = pct(biz02_num, total_orders)
        biz03_pct = pct(biz03_num, total_os)

        # Recompute pillar scores using same formulas as /api/kpis
        join_s  = round((pct(ji01, total_orders) + (100 - pct(ji02, total_os)) + pct(ji03, total_os)) / 3)
        comp_s  = round(((100 - pct(cp01, total_orders)) + (100 - pct(cp02, total_shp)) + (100 - pct(cp05n, cp05d))) / 3)
        cons_s  = round(((100 - pct(cs07, total_orders)) + (100 - pct(cs01, total_orders)) + (100 - pct(cs02, total_shp))) / 3)
        ref_s   = round(((100 - pct(ri01, total_shp)) + (100 - pct(ri05_ord, total_orders))) / 2)
        time_s  = round(100 - pct(tp01, cp05d))
        biz_s   = round((kpi_score(biz01_pct, 95, True) + kpi_score(biz02_pct, 0, False) + kpi_score(biz03_pct, 2, False)) / 3)

        kpi_scores = [
            kpi_score(pct(ji01, total_orders),  98, True),
            kpi_score(pct(ji02, total_os),        1, False),
            kpi_score(pct(ji03, total_os),        98, True),
            kpi_score(pct(cp01, total_orders),     0, False),
            kpi_score(pct(cp02, total_shp),        0, False),
            kpi_score(pct(cp05n, cp05d),           3, False),
            kpi_score(pct(cs07, total_orders),     0, False),
            kpi_score(pct(cs01, total_orders),     2, False),
            kpi_score(pct(cs02, total_shp),        0, False),
            kpi_score(pct(ri01, total_shp),        0, False),
            kpi_score(pct(ri05_ord, total_orders), 0, False),
            kpi_score(pct(tp01, cp05d),            0, False),
            kpi_score(biz01_pct, 95, True),
            kpi_score(biz02_pct,  0, False),
            kpi_score(biz03_pct,  2, False),
        ]
        overall = round(sum(kpi_scores) / len(kpi_scores))

        cursor.execute("""
            INSERT INTO workspace.otm.kpi_snapshots (
                captured_at, label,
                overall_score,
                pillar_join, pillar_comp, pillar_cons, pillar_time, pillar_ref, pillar_biz,
                ji01, ji02, ji03, cp01, cp02, cp05,
                cs01, cs02, cs07, ri01, ri05, tp01,
                biz01, biz02, biz03
            ) VALUES (
                CAST(? AS TIMESTAMP), ?,
                ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
        """, [
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), label,
            overall,
            join_s, comp_s, cons_s, time_s, ref_s, biz_s,
            pct(ji01, total_orders), pct(ji02, total_os), pct(ji03, total_os),
            pct(cp01, total_orders), pct(cp02, total_shp), pct(cp05n, cp05d),
            pct(cs01, total_orders), pct(cs02, total_shp), pct(cs07, total_orders),
            pct(ri01, total_shp), pct(ri05_ord, total_orders), pct(tp01, cp05d),
            biz01_pct, biz02_pct, biz03_pct,
        ])

        return jsonify({
            "captured": True,
            "label": label,
            "overall_score": overall,
            "captured_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        })

    except Exception as e:
        print(f"[ERROR /api/snapshot] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


# ── Agent routes ──────────────────────────────────────────────────────────────

@app.route("/api/alerts")
def get_alerts():
    """Return all Open alerts from dq_alerts, ordered by severity then created_at."""
    try:
        cursor = get_cursor()
        cursor.execute("""
            SELECT alert_id, created_at, kpi_id, kpi_value, target_value,
                   severity, message, recommendation, status, remediation_log
            FROM workspace.otm.dq_alerts
            WHERE status != 'Resolved'
            ORDER BY
                CASE severity WHEN 'RED' THEN 1 WHEN 'AMBER' THEN 2 ELSE 3 END,
                created_at DESC
        """)
        rows = cursor.fetchall()
        alerts = []
        for r in rows:
            alerts.append({
                "alert_id":        r[0],
                "created_at":      str(r[1]),
                "kpi_id":          r[2],
                "kpi_value":       r[3],
                "target_value":    r[4],
                "severity":        r[5],
                "message":         r[6],
                "recommendation":  r[7],
                "status":          r[8],
                "remediation_log": r[9],
            })
        return jsonify({"alerts": alerts, "count": len(alerts)})
    except Exception as e:
        print(f"[ERROR /api/alerts] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/monitor", methods=["POST"])
def agent_monitor():
    """Run the Monitor Agent on-demand. Inserts alerts for RED/AMBER KPIs.

    Skips KPIs that already have an Open alert (deduplication).
    """
    try:
        from agents.monitor_agent import run as monitor_run
        # Fetch live KPI data (reuse the /api/kpis logic inline)
        kpis_resp = kpis()
        kpis_data = kpis_resp.get_json()
        if "error" in kpis_data:
            return jsonify({"error": kpis_data["error"]}), 500
        new_alerts = monitor_run(kpis_data)
        return jsonify({"inserted": len(new_alerts), "alerts": new_alerts})
    except Exception as e:
        print(f"[ERROR /api/agents/monitor] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/rootcause", methods=["POST"])
def agent_rootcause():
    """Run the Root-Cause Agent for a specific KPI alert.

    Body: { "kpi_id": "CS07", "alert_id": 1 }
    """
    try:
        from agents.rootcause_agent import run as rca_run
        body     = request.get_json(silent=True) or {}
        kpi_id   = body.get("kpi_id", "")
        alert_id = body.get("alert_id", 0)
        if not kpi_id:
            return jsonify({"error": "kpi_id is required"}), 400
        kpi_id_upper = kpi_id.upper()
        if kpi_id_upper not in DRILLDOWN_QUERIES:
            return jsonify({"error": f"No drill-down data for KPI '{kpi_id}'"}), 404

        # Fetch failing records
        cursor = get_cursor()
        cursor.execute(DRILLDOWN_QUERIES[kpi_id_upper])
        rows    = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        records = [dict(zip(columns, r)) for r in rows]
        for rec in records:
            for k, v in rec.items():
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    rec[k] = str(v)

        analysis = rca_run(kpi_id_upper, alert_id, records)
        return jsonify(analysis)
    except Exception as e:
        print(f"[ERROR /api/agents/rootcause] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/remediate", methods=["POST"])
def agent_remediate():
    """Draft or execute a SQL fix for a dq_alert.

    Body: { "alert_id": 1, "approve": false }  → returns draft SQL only
    Body: { "alert_id": 1, "approve": true, "sql": "UPDATE ...", "explanation": "..." }  → executes
    """
    try:
        from agents.remediation_agent import draft, execute
        from agents.rootcause_agent import run as rca_run
        body     = request.get_json(silent=True) or {}
        alert_id = body.get("alert_id", 0)
        approve  = body.get("approve", False)

        if not approve:
            # Draft mode: fetch root-cause first, then generate SQL
            kpi_id = body.get("kpi_id", "")
            if not kpi_id:
                return jsonify({"error": "kpi_id required for draft mode"}), 400
            kpi_id_upper = kpi_id.upper()
            # Get drill-down records
            if kpi_id_upper in DRILLDOWN_QUERIES:
                cursor  = get_cursor()
                cursor.execute(DRILLDOWN_QUERIES[kpi_id_upper])
                rows    = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
                records = [dict(zip(columns, r)) for r in rows]
                for rec in records:
                    for k, v in rec.items():
                        if v is not None and not isinstance(v, (str, int, float, bool)):
                            rec[k] = str(v)
            else:
                records = []
            rca = rca_run(kpi_id_upper, 0, records)
            plan = draft(alert_id, rca)
            return jsonify(plan)

        else:
            # Execute mode: apply the approved SQL
            sql_str     = body.get("sql", "")
            explanation = body.get("explanation", "User-approved remediation fix")
            if not sql_str:
                return jsonify({"error": "sql is required for approve mode"}), 400
            result = execute(alert_id, sql_str, explanation)
            if result.get("executed"):
                # Capture a post-fix snapshot
                snapshot()
            return jsonify(result)

    except Exception as e:
        print(f"[ERROR /api/agents/remediate] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/summary", methods=["POST"])
def agent_summary():
    """Generate an AI executive summary of the current KPI state.

    Body: the full /api/kpis payload (or empty — will re-fetch).
    """
    try:
        from agents.summary_agent import run as summary_run
        body = request.get_json(silent=True) or {}
        if not body.get("overall_score"):
            # Re-fetch live KPIs
            kpis_resp = kpis()
            kpis_data = kpis_resp.get_json()
        else:
            kpis_data = body
        if "error" in kpis_data:
            return jsonify({"error": kpis_data["error"]}), 500
        summary = summary_run(kpis_data)
        return jsonify({"summary": summary})
    except Exception as e:
        print(f"[ERROR /api/agents/summary] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/chat", methods=["POST"])
def agent_chat():
    """Answer a natural-language question about the Transport Analytics DQ data.

    Body: { "message": "...", "context": {...}, "history": [...] }
    """
    try:
        from agents.chat_agent import run as chat_run
        body    = request.get_json(silent=True) or {}
        message = body.get("message", "")
        context = body.get("context", {})
        history = body.get("history", [])
        if not message:
            return jsonify({"error": "message is required"}), 400
        result = chat_run(message, context, history)
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR /api/agents/chat] {e}", flush=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print("=" * 60)
    print("Transport Analytics Live DQ Dashboard — AI-Powered Edition")
    print(f"Open: http://localhost:{port}")
    print("=" * 60)
    app.run(debug=debug, port=port, threaded=True)
