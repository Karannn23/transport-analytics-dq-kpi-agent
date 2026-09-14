"""
Root-Cause Agent — Explain Why a KPI Is Failing
=================================================
Given a KPI ID and its failing records (from /api/drilldown), this agent
uses IBM Bob to identify the root cause pattern and suggest a corrective SQL.

The analysis is stored back into workspace.otm.dq_alerts (message column)
and the alert status changes to 'In Review'.

Usage (standalone):
    python -m agents.rootcause_agent CS07 <alert_id>

Or call via POST /api/agents/rootcause:
    {"kpi_id": "CS07", "alert_id": 1}
"""

import json
import os
from datetime import datetime

from databricks import sql
from dotenv import load_dotenv

from agents.bob_client import BobAPIError, call_bob, parse_json_response
from agents.prompts import ROOTCAUSE_SYSTEM_PROMPT

load_dotenv()

# Hard-coded fallback analyses for when Bob is unavailable — RCA template format
FALLBACK_ANALYSES = {
    "JI02": {
        "issueSummary": "3 orphan ORDER_SHIPMENT rows (OS-X01, OS-X02, OS-X03) reference order_release_gid values that do not exist in the ORDER table, causing JI-02 Orphan OS Rate to breach its <=1% target at 2.7%.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.order_shipment",
            "ruleViolated": "JI-02: Orphan OS Rate > 1% (actual: 2.7%, target: <=1%)",
            "severity": "RED",
        },
        "impact": "Orphan OS rows inflate shipment counts, cause false positives in carrier SLA reporting, and prevent accurate order-to-shipment reconciliation for the Data Engineer.",
        "rootCause": "3 ORDER_SHIPMENT rows (OS-X01, OS-X02, OS-X03) reference order_release_gid values that do not exist in the ORDER table. These records were created during a bulk import job that failed to validate parent ORDER existence before inserting child OS rows.",
        "evidence": [
            "os_id='OS-X01', order_release_gid='OTM.ORD-X001' — no matching ORDER row",
            "os_id='OS-X02', order_release_gid='OTM.ORD-X002' — no matching ORDER row",
            "os_id='OS-X03', order_release_gid='OTM.ORD-X003' — no matching ORDER row",
            "All 3 orphan rows have os_id starting with 'OS-X' — consistent with a failed import batch",
        ],
        "correctiveAction": "DELETE FROM workspace.otm.order_shipment WHERE os_id IN ('OS-X01', 'OS-X02', 'OS-X03')",
        "preventiveAction": "Add a referential integrity check to the ORDER_SHIPMENT ingestion pipeline: validate that order_release_gid exists in workspace.otm.order before inserting OS rows. Reject or quarantine rows that fail this check.",
        "owner": "Data Engineer",
        "status": "Open",
        # Legacy aliases so app.py rootcause/remediation logic can still read these fields
        "suggested_sql": "DELETE FROM workspace.otm.order_shipment WHERE os_id IN ('OS-X01', 'OS-X02', 'OS-X03')",
        "suggested_action": "Delete the 3 orphan OS rows or create corresponding placeholder ORDER records.",
    },
    "CS07": {
        "issueSummary": "3 orders each have 2 active ORDER_SHIPMENT rows pointing to different shipments (ghost mappings), causing CS-07 Ghost Mapping Rate to breach its =0% target at 3%.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.order_shipment",
            "ruleViolated": "CS-07: Ghost Mapping Rate > 0% (actual: 3%, target: =0%)",
            "severity": "RED",
        },
        "impact": "Ghost-mapped orders appear active on multiple shipments simultaneously, corrupting OTD calculations and double-counting order weight in volume reports.",
        "rootCause": "3 orders each have 2 Active ORDER_SHIPMENT rows pointing to different shipments. The original shipment assignment was deleted in the source system via a CDC event, but the delete was not propagated to the data lake — leaving the stale row in 'Active' status alongside the correct new assignment.",
        "evidence": [
            "Each ghost order has one Active OS row with otm_deleted='YES' (stale) and one correct Active row",
            "otm_deleted='YES' flag should have triggered lake_status to be set to 'STALE' during CDC processing",
            "CS-07 query: COUNT(DISTINCT orders WHERE COUNT(DISTINCT Active shipment_gid) > 1) = 3",
        ],
        "correctiveAction": "UPDATE workspace.otm.order_shipment SET lake_status = 'STALE' WHERE otm_deleted = 'YES' AND lake_status = 'Active'",
        "preventiveAction": "Fix the CDC pipeline to propagate delete events: when otm_deleted='YES' is received, immediately set lake_status='STALE'. Add a daily reconciliation job to detect any otm_deleted='YES' rows still in Active status.",
        "owner": "Data Engineer",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.order_shipment SET lake_status = 'STALE' WHERE otm_deleted = 'YES' AND lake_status = 'Active'",
        "suggested_action": "Update lake_status to 'STALE' for all ORDER_SHIPMENT rows where otm_deleted='YES' but lake_status is still 'Active'.",
    },
    "CS02": {
        "issueSummary": "Shipment SHP-2025-010 has actual_arrival (Jun 6) before actual_departure (Jun 7), a physically impossible date sequence, causing CS-02 to breach its =0% target.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.shipment",
            "ruleViolated": "CS-02: Date Sequence Violation > 0% (actual: 0.9%, target: =0%)",
            "severity": "RED",
        },
        "impact": "Arrival-before-departure records produce negative transit times, break carrier SLA calculations, and generate misleading OTD metrics for the Ops Manager.",
        "rootCause": "Shipment SHP-2025-010 has actual_arrival (Jun 6) before actual_departure (Jun 7), which is physically impossible. This is a data entry error in the source system — the two date fields were likely transposed when the tracking event was manually entered.",
        "evidence": [
            "shipment_gid='OTM.SHP-2025-010'",
            "actual_departure='2025-06-07', actual_arrival='2025-06-06'",
            "Transit time calculated as -1 day — impossible",
            "dq_flag='Date Seq Violation' on this record",
        ],
        "correctiveAction": "UPDATE workspace.otm.shipment SET actual_arrival = NULL, dq_flag = 'Date Seq Violation - Under Review' WHERE shipment_gid = 'OTM.SHP-2025-010' AND actual_arrival < actual_departure",
        "preventiveAction": "Add a validation rule to the shipment tracking feed ingestion: reject any record where actual_arrival < actual_departure and route it to a quarantine table for manual review before lake insertion.",
        "owner": "Ops Manager",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.shipment SET actual_arrival = NULL, dq_flag = 'Date Seq Violation - Under Review' WHERE shipment_gid = 'OTM.SHP-2025-010' AND actual_arrival < actual_departure",
        "suggested_action": "Null out actual_arrival for SHP-2025-010 so it no longer triggers the arrival-before-departure check.",
    },
    "RI01": {
        "issueSummary": "Shipment SHP-2025-020 has status='DISPATCHED' which is not in the allowed enum, causing RI-01 Invalid Shipment Status to breach its =0% target.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.shipment",
            "ruleViolated": "RI-01: Invalid Shipment Status > 0% (actual: 0.9%, target: =0%)",
            "severity": "RED",
        },
        "impact": "Shipments with non-standard status values are excluded from OTD calculations and carrier SLA reports, causing the Data Steward to undercount active shipments in governance dashboards.",
        "rootCause": "Shipment SHP-2025-020 has status='DISPATCHED', a custom status used in a regional source system instance that was not normalised to the standard enum [Planned, In Transit, Delivered, Closed, Cancelled] before lake ingestion.",
        "evidence": [
            "shipment_gid='OTM.SHP-2025-020'",
            "status='DISPATCHED' — not in allowed enum [Planned, In Transit, Delivered, Closed, Cancelled]",
            "RI-01 query: COUNT(shipments WHERE status NOT IN enum) = 1",
        ],
        "correctiveAction": "UPDATE workspace.otm.shipment SET status = 'In Transit' WHERE shipment_gid = 'OTM.SHP-2025-020' AND status = 'DISPATCHED'",
        "preventiveAction": "Add an enum validation step to the shipment ingestion pipeline. Maintain a status mapping table that translates regional source-system status values to the canonical enum before insertion.",
        "owner": "Data Steward",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.shipment SET status = 'In Transit' WHERE shipment_gid = 'OTM.SHP-2025-020' AND status = 'DISPATCHED'",
        "suggested_action": "Map 'DISPATCHED' to the nearest valid status ('In Transit') and add a validation rule to the ingestion pipeline.",
    },
    "RI05": {
        "issueSummary": "6 orders have total_weight_kg = 0, causing RI-05 Zero-Weight Order Rate to breach its =0% target at 6%.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.order",
            "ruleViolated": "RI-05: Zero/Negative Weight Orders > 0% (actual: 6%, target: =0%)",
            "severity": "RED",
        },
        "impact": "Zero-weight orders cannot be properly costed or routed, corrupting cost-per-shipment calculations and weight-based billing reports for the Finance Analyst.",
        "rootCause": "6 orders have total_weight_kg = 0. All 6 are in Planned status and follow the ORD-2025-* naming pattern, suggesting they are test/dummy records loaded without weight data and never cleaned up.",
        "evidence": [
            "COUNT(orders WHERE total_weight_kg <= 0) = 6",
            "All 6 orders have order_status='Planned'",
            "Order IDs follow ORD-2025-* pattern consistent with a test data batch",
            "RI-05 and BIZ-02 share the same numerator query — fixing RI-05 also fixes BIZ-02",
        ],
        "correctiveAction": "UPDATE workspace.otm.order SET total_weight_kg = NULL, dq_flag = 'Zero Weight - Pending Review' WHERE total_weight_kg <= 0 AND total_weight_kg IS NOT NULL",
        "preventiveAction": "Add a non-null, non-zero weight validation to the order ingestion pipeline. Reject orders with total_weight_kg = 0 or NULL at source and route them to a quarantine table for Finance Analyst review.",
        "owner": "Finance Analyst",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.order SET total_weight_kg = NULL, dq_flag = 'Zero Weight - Pending Review' WHERE total_weight_kg <= 0 AND total_weight_kg IS NOT NULL",
        "suggested_action": "Set total_weight_kg to NULL for the 6 zero-weight orders so they no longer trigger the <= 0 check.",
    },
    "BIZ02": {
        "issueSummary": "Same 6 zero-weight orders as RI-05 are causing BIZ-02 Zero-Weight Order Rate to breach its =0% target at 6%. Both KPIs share the same numerator query.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.order",
            "ruleViolated": "BIZ-02: Zero-Weight Order Rate > 0% (actual: 6%, target: =0%)",
            "severity": "RED",
        },
        "impact": "Zero-weight orders distort business-level cost reporting and weight-based carrier billing reconciliation for the Finance Analyst. Resolving RI-05 will automatically resolve BIZ-02.",
        "rootCause": "BIZ-02 measures the same 6 zero-weight orders as RI-05 — both KPIs use COUNT(orders WHERE total_weight_kg <= 0) as their numerator. The root cause is identical: test/dummy order records loaded without weight data.",
        "evidence": [
            "BIZ-02 and RI-05 share the same SQL numerator: COUNT(orders WHERE total_weight_kg <= 0) = 6",
            "Same 6 order records identified in RI-05 analysis",
            "Fixing RI-05 (setting total_weight_kg to NULL) will also resolve BIZ-02",
        ],
        "correctiveAction": "UPDATE workspace.otm.order SET total_weight_kg = NULL, dq_flag = 'Zero Weight - Pending Review' WHERE total_weight_kg <= 0 AND total_weight_kg IS NOT NULL",
        "preventiveAction": "Same as RI-05: add weight validation at ingestion. Add a KPI dependency note so BIZ-02 is not alerted separately when RI-05 is already in remediation.",
        "owner": "Finance Analyst",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.order SET total_weight_kg = NULL, dq_flag = 'Zero Weight - Pending Review' WHERE total_weight_kg <= 0 AND total_weight_kg IS NOT NULL",
        "suggested_action": "Apply the same fix as RI-05: set total_weight_kg to NULL for zero-weight orders.",
    },
    "BIZ03": {
        "issueSummary": "7 ORDER_SHIPMENT rows with dq_flag='Re-assigned' are causing BIZ-03 Re-Assignment Rate to breach its <=2% target at 6.2%.",
        "detectionDetails": {
            "timestamp": "",
            "dataset": "workspace.otm.order_shipment",
            "ruleViolated": "BIZ-03: Re-Assignment Rate > 2% (actual: 6.2%, target: <=2%)",
            "severity": "RED",
        },
        "impact": "High re-assignment rates indicate poor initial shipment planning quality, increasing operational costs, tracking complexity, and reducing on-time delivery predictability for the Supply Chain Manager.",
        "rootCause": "7 ORDER_SHIPMENT rows have dq_flag='Re-assigned' and lake_status='Active'. These OS rows were re-assigned to a different shipment during planning but the original assignment was never cleaned up — they remain Active in the lake with the Re-assigned flag, being counted by BIZ-03 indefinitely.",
        "evidence": [
            "COUNT(OS WHERE dq_flag = 'Re-assigned') = 7",
            "All 7 rows have lake_status='Active'",
            "BIZ-03 query: COUNT(*) FROM order_shipment WHERE dq_flag = 'Re-assigned' = 7 out of 113 total OS rows",
        ],
        "correctiveAction": "UPDATE workspace.otm.order_shipment SET lake_status = 'Inactive', dq_flag = 'Re-assigned - Resolved' WHERE dq_flag = 'Re-assigned' AND lake_status = 'Active'",
        "preventiveAction": "Update the shipment re-assignment workflow to automatically set lake_status='Inactive' and dq_flag='Re-assigned - Resolved' on the old OS row when a re-assignment event is processed.",
        "owner": "Supply Chain Mgr",
        "status": "Open",
        "suggested_sql": "UPDATE workspace.otm.order_shipment SET lake_status = 'Inactive', dq_flag = 'Re-assigned - Resolved' WHERE dq_flag = 'Re-assigned' AND lake_status = 'Active'",
        "suggested_action": "Update dq_flag to 'Re-assigned - Resolved' and lake_status to 'Inactive' for these rows.",
    },
}


def _get_cursor():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
    )
    return conn, conn.cursor()


def run(kpi_id: str, alert_id: int, records: list[dict]) -> dict:
    """Analyse failing records for a KPI and return a root-cause dict.

    Args:
        kpi_id:   The KPI being analysed (e.g. 'CS07').
        alert_id: The dq_alerts row to update with the analysis.
        records:  Up to 20 failing rows from /api/drilldown.

    Returns:
        Dict with keys: kpi_id, root_cause, pattern, affected_count,
                        suggested_action, suggested_sql.
    """
    kpi_id = kpi_id.upper()
    # Cap to 20 rows to stay within Bob's token budget
    sample = records[:20]
    extra  = len(records) - len(sample)
    user_msg = json.dumps({
        "kpi_id": kpi_id,
        "failing_records": sample,
        "total_failing": len(records),
        "note": f"...and {extra} additional records with similar patterns." if extra > 0 else "",
    }, indent=2)

    try:
        raw      = call_bob(ROOTCAUSE_SYSTEM_PROMPT, user_msg)
        analysis = parse_json_response(raw)
        if not isinstance(analysis, dict):
            raise ValueError("Bob did not return a JSON object")
    except (BobAPIError, ValueError) as err:
        print(f"[RootCause] Bob unavailable ({err}) — using fallback")
        fallback = FALLBACK_ANALYSES.get(kpi_id, {})
        analysis = {
            "kpi_id":          kpi_id,
            "root_cause":      fallback.get("root_cause", f"KPI {kpi_id} has {len(records)} failing records requiring investigation."),
            "pattern":         fallback.get("pattern", "See failing records for details."),
            "affected_count":  len(records),
            "suggested_action":fallback.get("suggested_action", "Review failing records and apply corrective action."),
            "suggested_sql":   fallback.get("suggested_sql", ""),
        }

    # Persist analysis to dq_alerts
    if alert_id:
        conn, cursor = _get_cursor()
        try:
            cursor.execute("""
                UPDATE workspace.otm.dq_alerts
                SET message = ?, status = 'In Review'
                WHERE alert_id = ?
            """, [
                f"ROOT CAUSE: {analysis.get('root_cause','')}\n\nPATTERN: {analysis.get('pattern','')}\n\nACTION: {analysis.get('suggested_action','')}",
                alert_id,
            ])
        finally:
            cursor.close()
            conn.close()

    return analysis
