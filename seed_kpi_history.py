"""
Seed synthetic KPI history into workspace.otm.kpi_snapshots
=============================================================
Inserts 8 pre-computed rows representing Jun 14 – Jul 20, 2025.

Since the underlying Transport Analytics data is static (seeded sample data), historical
trending is achieved by pre-loading plausible day-by-day KPI values that
tell a coherent story:
  - Jun 14: Clean baseline (~88% overall, no ghosts, no orphans)
  - Jun 14 → Jul 13: Gradual degradation as ghost mappings and orphan OS
    rows accumulate (mirroring the anomalies baked into the seeded data)
  - Jul 20 (today): Exactly matches the live /api/kpis values (74% overall)

KPIs driven by static data (CP01, CP02, JI03, CS01, RI01, TP01) stay
constant across all rows — only the ghost/orphan KPIs drift.

The only additional row added during the demo is "Post-fix" (appended by
POST /api/snapshot after a Remediation Agent fix is applied in ST-8).

Usage:
    python seed_kpi_history.py          # inserts all 8 rows
    python seed_kpi_history.py --reset  # drops and recreates rows (idempotent)
"""

import os
import sys
from datetime import datetime
from databricks import sql
from dotenv import load_dotenv

load_dotenv()

# ── Synthetic snapshot rows ────────────────────────────────────────────────
# Fields: (captured_at, label, overall, pillar_join, pillar_comp, pillar_cons,
#          pillar_time, pillar_ref,
#          ji01, ji02, ji03, cp01, cp02, cp05,
#          cs01, cs02, cs07, ri01, ri05, tp01,
#          biz01, biz02, biz03)
#
# Notes:
#   - All values are percentages (0–100) matching /api/kpis units
#   - biz01/02/03 are NULL here; they become populated after ST-4
#   - ji03, cp01, cp02, cs01, ri01 never change (static data)
#   - Ghost (cs07) and orphan (ji02) drift upward; ji01 drifts down

SNAPSHOTS = [
    # Day 1 — Jun 14: Clean baseline (no ghost mappings, no orphans, BIZ KPIs healthy)
    (
        "2025-06-14 09:00:00", "Jun 14 — Baseline",
        93,    # overall
        99, 99, 99, 100, 97,  # pillars: join, comp, cons, time, ref
        99.0,  # ji01 — 99/100 orders matched
        0.0,   # ji02 — no orphans yet
        100.0, # ji03
        0.0,   # cp01
        0.0,   # cp02
        1.1,   # cp05
        0.0,   # cs01
        0.9,   # cs02
        0.0,   # cs07 — no ghost mappings yet
        0.9,   # ri01
        6.0,   # ri05 (zero-weight orders are static — always present)
        0.0,   # tp01
        100.0, 6.0, 1.8,  # biz01=100%, biz02=6%(static), biz03=1.8%(below target)
    ),
    # Day 2 — Jun 17: First ghost mapping detected
    (
        "2025-06-17 09:00:00", "Jun 17 — First ghost detected",
        91,
        98, 99, 98, 100, 97,
        98.0, 0.9, 100.0,   # ji01 slipping, ji02 ticking up
        0.0, 0.0, 1.1,
        0.0, 0.9,
        1.0,                  # cs07 = 1% (1 ghost order)
        0.9, 6.0, 0.0,
        100.0, 6.0, 2.7,      # biz03 crossing amber
    ),
    # Day 3 — Jun 20: Degradation continues
    (
        "2025-06-20 09:00:00", "Jun 20 — Orphans growing",
        90,
        97, 99, 97, 100, 97,
        97.0, 1.8, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        1.5,                  # cs07 = 1.5%
        0.9, 6.0, 0.0,
        100.0, 6.0, 3.5,
    ),
    # Day 4 — Jun 23
    (
        "2025-06-23 09:00:00", "Jun 23 — Ghost count rising",
        89,
        96, 99, 96, 100, 97,
        96.0, 2.0, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        2.0,
        0.9, 6.0, 0.0,
        100.0, 6.0, 4.4,
    ),
    # Day 5 — Jun 27
    (
        "2025-06-27 09:00:00", "Jun 27 — Continued drift",
        88,
        95, 99, 95, 100, 97,
        95.0, 2.3, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        2.5,
        0.9, 6.0, 0.0,
        100.0, 6.0, 5.3,
    ),
    # Day 6 — Jul 03: CS-07 hits 3% RED; BIZ-03 also RED
    (
        "2025-07-03 09:00:00", "Jul 03 — RED threshold crossed",
        87,
        94, 99, 95, 100, 97,
        94.0, 2.5, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        3.0,                  # cs07 = 3% RED ★
        0.9, 6.0, 0.0,
        100.0, 6.0, 6.2,      # biz03 = 6.2% RED (matches live)
    ),
    # Day 7 — Jul 13: Plateau — no cleanup done
    (
        "2025-07-13 09:00:00", "Jul 13 — No remediation yet",
        86,
        94, 99, 95, 100, 97,
        94.0, 2.7, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        3.0,
        0.9, 6.0, 0.0,
        100.0, 6.0, 6.2,
    ),
    # Day 8 — Jul 20: TODAY — exactly matches live /api/kpis values
    # Live: overall=85%, join=97%, comp=100%, cons=99%, time=100%, ref=97%
    # business=66% (BIZ-02 and BIZ-03 both RED drag it down)
    (
        "2025-07-20 09:00:00", "Jul 20 — Today (live)",
        85,
        97, 100, 99, 100, 97,
        94.0, 2.7, 100.0,
        0.0, 0.0, 1.1,
        0.0, 0.9,
        3.0,
        0.9, 6.0, 0.0,
        100.0, 6.0, 6.2,      # biz01=100%(GREEN), biz02=6%(RED), biz03=6.2%(RED)
    ),
]

INSERT_SQL = """
INSERT INTO workspace.otm.kpi_snapshots (
    captured_at, label,
    overall_score,
    pillar_join, pillar_comp, pillar_cons, pillar_time, pillar_ref,
    ji01, ji02, ji03, cp01, cp02, cp05,
    cs01, cs02, cs07, ri01, ri05, tp01,
    biz01, biz02, biz03
) VALUES (
    CAST(? AS TIMESTAMP), ?,
    ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?
)
"""


def connect():
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
    )


def reset_snapshots(cursor):
    """Delete all existing snapshot rows so we can re-seed cleanly."""
    print("Resetting existing rows from workspace.otm.kpi_snapshots ...")
    cursor.execute("DELETE FROM workspace.otm.kpi_snapshots")
    print("[OK] Existing rows cleared")


def seed(reset=False):
    """Insert the 8 synthetic history rows.

    Idempotent by default: each row is skipped if a snapshot with the same
    captured_at timestamp already exists.  Pass reset=True (--force flag) to
    delete the seeded rows first and re-insert them cleanly.
    """
    conn = connect()
    cursor = conn.cursor()

    try:
        if reset:
            reset_snapshots(cursor)

        # Fetch existing captured_at values so we can skip duplicates
        cursor.execute("SELECT captured_at FROM workspace.otm.kpi_snapshots")
        existing_ts = {str(r[0])[:19] for r in cursor.fetchall()}  # normalise to "YYYY-MM-DD HH:MM:SS"

        inserted = 0
        skipped  = 0
        print(f"Seeding {len(SNAPSHOTS)} synthetic snapshot rows ...")
        for i, row in enumerate(SNAPSHOTS, 1):
            ts    = row[0][:19]   # "YYYY-MM-DD HH:MM:SS"
            label = row[1]
            overall = row[2]
            if ts in existing_ts and not reset:
                print(f"  [{i:02d}] SKIP  {label}  (already exists)")
                skipped += 1
                continue
            cursor.execute(INSERT_SQL, list(row))
            print(f"  [{i:02d}] INSERT {label}  =>  overall={overall}%")
            inserted += 1

        print(f"\n[SUCCESS] {inserted} rows inserted, {skipped} rows skipped (already existed)")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM workspace.otm.kpi_snapshots")
        count = cursor.fetchone()[0]
        print(f"[INFO] Total rows in table now: {count}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # --force: delete seeded rows first (safe reset for demo)
    # --reset kept as alias for backwards compatibility
    reset_flag = "--force" in sys.argv or "--reset" in sys.argv
    if reset_flag:
        print("Running in FORCE/RESET mode — existing seeded rows will be deleted first.")
    seed(reset=reset_flag)
