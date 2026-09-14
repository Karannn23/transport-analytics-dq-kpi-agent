"""
Remediation Agent — Draft + Execute SQL Fixes with Human-in-the-Loop
======================================================================
Given a root-cause analysis, this agent uses IBM Bob to draft a corrective
SQL statement. The SQL is presented to the user for approval in the dashboard.
On approval, the SQL is executed and a post-fix KPI snapshot is captured.

Safety guards:
- Bob is instructed never to generate DROP/TRUNCATE/full-table DELETE
- This agent double-checks the generated SQL before execution
- Rejected SQL patterns: DROP, TRUNCATE, DELETE without WHERE

Usage via POST /api/agents/remediate:
    {"alert_id": 1, "approve": false}  → returns draft SQL (no execution)
    {"alert_id": 1, "approve": true}   → executes SQL, captures snapshot
"""

import json
import os
import re
from datetime import datetime

from databricks import sql
from dotenv import load_dotenv

from agents.bob_client import BobAPIError, call_bob, parse_json_response
from agents.prompts import REMEDIATION_SYSTEM_PROMPT

load_dotenv()

# SQL patterns that are never allowed to execute regardless of context.
# Note: \w+ won't match dotted Databricks names (workspace.otm.table) so we
# use broad keyword matching and rely on the WHERE-clause backstop for safety.
BLOCKED_PATTERNS = [
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",      # no schema changes
    r"\bDELETE\b",     # all DELETEs go through the WHERE-clause backstop below
]


def _is_safe_sql(sql_str: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Rejects dangerous SQL patterns.

    Checks applied (in order):
    1. Keyword blocklist — DROP, TRUNCATE, ALTER always blocked
    2. Multi-statement guard — only one statement allowed per fix
    3. DELETE without WHERE — backstop catches what the pattern misses
    """
    upper = sql_str.upper().strip()

    # 1. Keyword blocklist (DROP / TRUNCATE / ALTER always blocked)
    for pattern in BLOCKED_PATTERNS[:3]:  # DROP, TRUNCATE, ALTER
        if re.search(pattern, upper, re.IGNORECASE | re.MULTILINE):
            return False, f"Blocked keyword detected: {pattern.strip(r'\\b')}"

    # 2. Multi-statement guard — reject SQL containing more than one statement
    #    Split on ; and ignore empty trailing tokens
    statements = [s.strip() for s in sql_str.split(";") if s.strip()]
    if len(statements) > 1:
        return False, "Only a single SQL statement is allowed per remediation fix"

    # 3. DELETE must have a WHERE clause
    if re.search(r"\bDELETE\b", upper, re.IGNORECASE | re.MULTILINE):
        if not re.search(r"\bWHERE\b", upper, re.IGNORECASE | re.MULTILINE):
            return False, "DELETE without WHERE clause is not allowed"

    return True, ""


def _get_cursor():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
    )
    return conn, conn.cursor()


def draft(alert_id: int, root_cause_analysis: dict) -> dict:
    """Ask Bob to generate a draft SQL fix (no execution).

    Args:
        alert_id:            dq_alerts row ID being fixed.
        root_cause_analysis: Output dict from rootcause_agent.run().

    Returns:
        Dict with keys: sql, explanation, risk_level, rows_affected_estimate,
                        safe, safety_reason.
    """
    user_msg = json.dumps(root_cause_analysis, indent=2)
    try:
        raw  = call_bob(REMEDIATION_SYSTEM_PROMPT, user_msg)
        plan = parse_json_response(raw)
        if not isinstance(plan, dict):
            raise ValueError("Bob did not return a JSON object")
    except (BobAPIError, ValueError) as err:
        print(f"[Remediation] Bob unavailable ({err}) — using fallback SQL from root cause")
        plan = {
            "sql":                    root_cause_analysis.get("suggested_sql", ""),
            "explanation":            f"Fallback: {root_cause_analysis.get('suggested_action', '')}",
            "risk_level":             "MEDIUM",
            "rows_affected_estimate": root_cause_analysis.get("affected_count", 0),
        }

    sql_str = plan.get("sql", "")
    is_safe, reason = _is_safe_sql(sql_str)
    plan["safe"]          = is_safe
    plan["safety_reason"] = reason
    plan["alert_id"]      = alert_id
    return plan


def execute(alert_id: int, sql_str: str, explanation: str) -> dict:
    """Execute a pre-approved SQL fix and capture a post-fix snapshot.

    Args:
        alert_id:    The dq_alerts row being resolved.
        sql_str:     The SQL to execute (already safety-checked by draft()).
        explanation: Human-readable description of what the SQL does.

    Returns:
        Dict with keys: executed, rows_affected, new_overall_score, error.
    """
    is_safe, reason = _is_safe_sql(sql_str)
    if not is_safe:
        return {"executed": False, "error": f"SQL rejected by safety guard: {reason}"}

    conn, cursor = _get_cursor()
    try:
        cursor.execute(sql_str)
        rows_affected = getattr(cursor, "rowcount", -1)

        # Update alert status to Resolved
        log_entry = f"{datetime.utcnow().isoformat()} | SQL: {sql_str} | {explanation}"
        cursor.execute("""
            UPDATE workspace.otm.dq_alerts
            SET status = 'Resolved', remediation_log = ?,
                resolved_at = CAST(? AS TIMESTAMP)
            WHERE alert_id = ?
        """, [log_entry, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), alert_id])

        return {
            "executed":      True,
            "rows_affected": rows_affected,
            "error":         None,
        }

    except Exception as exc:
        return {"executed": False, "rows_affected": 0, "error": str(exc)}
    finally:
        cursor.close()
        conn.close()
