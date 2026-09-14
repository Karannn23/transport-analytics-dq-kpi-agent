"""
Demo Reset Script
=================
Resets the Transport Analytics demo to its initial "broken" state so the fix flow can be
demonstrated again cleanly.

What this does:
  1. Reverts the ghost-mapping fix: sets lake_status back to 'Active' for any
     ORDER_SHIPMENT rows where otm_deleted='YES' and lake_status='STALE'
  2. Reverts the invalid-status fix: sets status back to 'DISPATCHED' for SHP-2025-020
  3. Clears the dq_alerts table (deletes all rows so Monitor Agent starts fresh)
  4. Deletes any Post-fix rows from kpi_snapshots (keeps seeded history rows)

Usage:
    python reset_demo.py                 — full reset
    python reset_demo.py --alerts-only   — only clear alerts (keep data fixes)
    python reset_demo.py --dry-run       — print what would be done, no changes
"""

import os
import sys
from datetime import datetime

from databricks import sql
from dotenv import load_dotenv

load_dotenv()

DRY_RUN     = "--dry-run"     in sys.argv
ALERTS_ONLY = "--alerts-only" in sys.argv

SEP = "=" * 60


def connect():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
    )
    return conn, conn.cursor()


def run(cursor, sql_str: str, label: str):
    print(f"  {'[DRY-RUN] WOULD EXECUTE' if DRY_RUN else 'Executing'}: {label}")
    if DRY_RUN:
        print(f"    SQL: {sql_str.strip()}")
        return
    cursor.execute(sql_str)
    affected = getattr(cursor, "rowcount", "?")
    print(f"    -> {affected} row(s) affected")


def main():
    print(SEP)
    print("Transport Analytics Demo Reset Script")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if DRY_RUN:
        print("MODE: DRY-RUN (no changes will be made)")
    if ALERTS_ONLY:
        print("MODE: ALERTS-ONLY (data fixes will NOT be reverted)")
    print(SEP)

    conn, cursor = connect()
    try:
        if not ALERTS_ONLY:
            print("\n[1/6] Reverting Ghost Mapping fix (CS-07)")
            run(cursor,
                "UPDATE workspace.otm.order_shipment "
                "SET lake_status = 'Active' "
                "WHERE otm_deleted = 'YES' AND lake_status = 'STALE'",
                "Restore ghost OS rows to Active status")

            print("\n[2/6] Reverting Invalid Status fix (RI-01)")
            run(cursor,
                "UPDATE workspace.otm.shipment "
                "SET status = 'DISPATCHED', dq_flag = 'Invalid Status' "
                "WHERE shipment_gid = 'OTM.SHP-2025-020' AND status = 'In Transit'",
                "Restore SHP-2025-020 status to DISPATCHED")

            print("\n[3/6] Reverting Zero-Weight fix (RI-05 / BIZ-02)")
            run(cursor,
                "UPDATE workspace.otm.order "
                "SET total_weight_kg = 0, dq_flag = 'Zero Weight' "
                "WHERE dq_flag = 'Zero Weight - Pending Review' AND total_weight_kg IS NULL",
                "Restore zero-weight orders (set total_weight_kg back to 0)")

            print("\n[4/6] Reverting Re-Assignment fix (BIZ-03)")
            run(cursor,
                "UPDATE workspace.otm.order_shipment "
                "SET lake_status = 'Active', dq_flag = 'Re-assigned' "
                "WHERE dq_flag = 'Re-assigned - Resolved' AND lake_status = 'Inactive'",
                "Restore re-assigned OS rows to Active/Re-assigned")

            print("\n[5/6] Reverting Date Sequence fix (CS-02)")
            run(cursor,
                "UPDATE workspace.otm.shipment "
                "SET actual_arrival = CAST('2025-06-06' AS DATE), "
                "    dq_flag = 'Date Seq Violation' "
                "WHERE shipment_gid = 'OTM.SHP-2025-010' "
                "AND actual_arrival IS NULL",
                "Restore actual_arrival to Jun 6 for SHP-2025-010 (arrival before departure anomaly)")
        else:
            print("\n[1/6] Skipped — data fix revert (--alerts-only)")
            print("[2/6] Skipped — data fix revert (--alerts-only)")
            print("[3/6] Skipped — data fix revert (--alerts-only)")
            print("[4/6] Skipped — data fix revert (--alerts-only)")
            print("[5/6] Skipped — data fix revert (--alerts-only)")

        print("\n[6/6] Clearing dq_alerts table")
        run(cursor,
            "DELETE FROM workspace.otm.dq_alerts WHERE alert_id IS NOT NULL",
            "Delete all alerts (Monitor Agent will regenerate on next run)")

        print("\n[7/7] Removing Post-fix snapshot rows")
        run(cursor,
            "DELETE FROM workspace.otm.kpi_snapshots WHERE label LIKE '%Post-fix%'",
            "Remove any Post-fix snapshot rows (keeps seeded history)")

    finally:
        cursor.close()
        conn.close()

    print("\n" + SEP)
    print("Reset complete. Dashboard is ready for a fresh demo run.")
    print("Next steps:")
    print("  1. python app.py")
    print("  2. Open http://localhost:5000")
    print("  3. Click 'Run Monitor Agent' to generate fresh alerts")
    print(SEP)


if __name__ == "__main__":
    main()
