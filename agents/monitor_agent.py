"""
Monitor Agent — On-Demand KPI Alert Generation
================================================
Reads the current KPI values and uses IBM Bob to generate plain-English
alerts for every RED or AMBER KPI. Alerts are stored in workspace.otm.dq_alerts (Transport Analytics schema).

Since the underlying data is static, this agent is run ON-DEMAND (not as a cron
job) — triggered by the "Run Monitor Agent" button in the dashboard or by calling
POST /api/agents/monitor.

Deduplication: if an Open alert already exists for a given KPI, the agent skips
it so re-runs don't flood the table.

Usage (standalone):
    python -m agents.monitor_agent
"""

import json
import os
from datetime import datetime

from databricks import sql
from dotenv import load_dotenv

from agents.bob_client import BobAPIError, call_bob, parse_json_response
from agents.prompts import MONITOR_SYSTEM_PROMPT

load_dotenv()


# ── Rule-based fallback alert messages (used when Bob API is unavailable) ────
FALLBACK_MESSAGES = {
    "JI01": ("AMBER", "94% of orders have an active shipment assignment (target ≥ 98%). 6 orders have no active ORDER_SHIPMENT row — these orders will not appear in shipment execution reports.", "Review orders with no active OS rows and create missing assignments."),
    "JI02": ("RED",   "2.7% of ORDER_SHIPMENT rows (3/113) have no matching ORDER record. These orphan rows indicate a data ingestion issue — likely a bulk import that created OS records without parent orders.", "Delete or reconcile the 3 orphan OS rows (OS-X01, OS-X02, OS-X03)."),
    "CS07": ("RED",   "3% of orders (3/100) are ghost-mapped — ORDER_SHIPMENT stale-delete rows were not propagated from the source system to the data lake, causing these orders to appear active on multiple shipments.", "Replay CDC delete events or run the remediation UPDATE to mark stale OS rows."),
    "CS02": ("RED",   "0.9% of shipments (1/111) have actual_arrival before actual_departure — a physical impossibility indicating a data entry error in SHP-2025-010.", "Correct the dates for SHP-2025-010: set actual_arrival to a date after actual_departure."),
    "RI01": ("RED",   "0.9% of shipments (1/111) have an invalid status value 'DISPATCHED'. This value is not in the allowed enum [Planned, In Transit, Delivered, Closed, Cancelled].", "Update SHP-2025-020 to use a valid status value."),
    "RI05": ("RED",   "6% of orders (6/100) have total_weight_kg = 0. These appear to be test/dummy records that were not cleaned up before the dataset was loaded.", "Flag these 6 orders as test data or update their weight values."),
    "BIZ02": ("RED",  "6% of orders have zero weight (same records as RI-05). From a business perspective this means 6 orders cannot be properly costed or routed.", "Remove or correct the 6 zero-weight order records."),
    "BIZ03": ("AMBER","Some ORDER_SHIPMENT rows have been re-assigned, indicating planning quality issues. Re-assignments increase operational costs and tracking complexity.", "Review the root causes of shipment re-assignments to improve planning accuracy."),
}


def _get_cursor():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
    )
    return conn, conn.cursor()


def _existing_open_alerts(cursor) -> set:
    """Return set of kpi_id values that already have an Open alert."""
    cursor.execute("SELECT kpi_id FROM workspace.otm.dq_alerts WHERE status = 'Open'")
    return {r[0] for r in cursor.fetchall()}


def _insert_alert(cursor, kpi_id: str, kpi_value: float, target_value: float,
                  severity: str, message: str, recommendation: str):
    cursor.execute("""
        INSERT INTO workspace.otm.dq_alerts
        (created_at, kpi_id, kpi_value, target_value, severity, message, recommendation, status)
        VALUES (CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?, ?, 'Open')
    """, [
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        kpi_id, kpi_value, target_value, severity, message, recommendation,
    ])


def run(kpis_data: dict) -> list[dict]:
    """Generate and store alerts for all RED/AMBER KPIs.

    Args:
        kpis_data: The full JSON payload from /api/kpis.

    Returns:
        List of newly inserted alert dicts.
    """
    conn, cursor = _get_cursor()
    inserted = []

    try:
        existing = _existing_open_alerts(cursor)
        kpis = kpis_data.get("kpis", {})

        # Try Bob first
        try:
            raw = call_bob(MONITOR_SYSTEM_PROMPT, json.dumps(kpis_data, indent=2))
            alerts = parse_json_response(raw)
            if not isinstance(alerts, list):
                raise ValueError("Bob did not return a JSON array")
        except (BobAPIError, ValueError) as err:
            print(f"[Monitor] Bob unavailable ({err}) — using rule-based fallback")
            alerts = _build_fallback_alerts(kpis)

        for alert in alerts:
            kpi_id = alert.get("kpi_id", "").upper()
            if not kpi_id or kpi_id in existing:
                continue  # skip already-alerted KPIs
            kpi_obj = kpis.get(kpi_id, {})
            _insert_alert(
                cursor,
                kpi_id        = kpi_id,
                kpi_value     = kpi_obj.get("value", 0),
                target_value  = kpi_obj.get("target_val", 0),
                severity      = alert.get("severity", "RED"),
                message       = alert.get("message", ""),
                recommendation= alert.get("recommendation", ""),
            )
            inserted.append({
                "kpi_id":      kpi_id,
                "severity":    alert.get("severity", "RED"),
                "message":     alert.get("message", ""),
            })
            print(f"[Monitor] Alert inserted: {kpi_id} ({alert.get('severity')})")

    finally:
        cursor.close()
        conn.close()

    return inserted


def _build_fallback_alerts(kpis: dict) -> list[dict]:
    """Build rule-based alerts when Bob API is unavailable.

    RAG thresholds match the dashboard ragFromKpi() logic:
    - lower-is-better, target=0  : any value > 0 is RED (no AMBER band at zero)
    - lower-is-better, target>0  : value > target*2 → RED; value > target → AMBER
    - higher-is-better           : value < target*0.95 → RED; value < target → AMBER
    """
    alerts = []
    for kpi_id, kpi in kpis.items():
        value  = kpi.get("value", 0)
        target = kpi.get("target_val", 0)
        hib    = kpi.get("higher_is_better", False)

        if hib:
            is_red   = value < target * 0.95
            is_amber = not is_red and value < target
        else:
            if target == 0:
                # Zero-tolerance KPIs: any breach is RED, no AMBER band
                is_red   = value > 0
                is_amber = False
            else:
                is_red   = value > target * 2
                is_amber = not is_red and value > target

        if not is_red and not is_amber:
            continue

        # Use severity from fallback dict if available; otherwise derive from thresholds
        if kpi_id in FALLBACK_MESSAGES:
            _sev, msg, rec = FALLBACK_MESSAGES[kpi_id]
            sev = _sev  # trust the explicit fallback severity
        else:
            msg = f"KPI {kpi_id} value {value}% does not meet target {target}%."
            rec = "Investigate the failing records using the drill-down feature."
            sev = "RED" if is_red else "AMBER"
        alerts.append({"kpi_id": kpi_id, "severity": sev, "message": msg, "recommendation": rec})
    return alerts


if __name__ == "__main__":
    import requests as req_lib
    kpis_data = req_lib.get("http://localhost:5000/api/kpis").json()
    results = run(kpis_data)
    print(f"\n[Monitor] {len(results)} new alert(s) inserted.")
