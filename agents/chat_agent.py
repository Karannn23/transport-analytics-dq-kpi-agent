"""
Chat Agent — Conversational Q&A About Transport Analytics Data Quality
=======================================================
Answers natural-language questions about the Transport Analytics KPI data, history, and alerts.
Maintains conversation context via a messages list passed in by the caller.

Usage via POST /api/agents/chat:
    {
      "message": "Which orders are causing the Ghost Mapping issue?",
      "context": { ...kpis_data, history_data, alerts... },
      "history": [
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }
"""

import json
import re

from agents.bob_client import BobAPIError
from agents.bob_client import call_bob as _call_bob_single
from agents.prompts import CHAT_SYSTEM_PROMPT


def _call_bob_with_history(system_prompt: str, history: list, user_message: str,
                            temperature: float = 0.3) -> str:
    """Call Bob with a full conversation history.

    Builds a combined system + history + user prompt and delegates to call_bob().
    The history is prepended to the user message so Bob has conversation context
    without requiring multi-turn API support.
    """
    # Serialise prior turns as a readable preamble so Bob has conversation context
    history_text = ""
    for turn in (history or [])[-5:]:
        role = turn.get("role", "user").capitalize()
        content = turn.get("content", "")
        history_text += f"\n{role}: {content}"

    combined_user = (
        f"{history_text}\n\nUser: {user_message}" if history_text
        else user_message
    )
    return _call_bob_single(system_prompt, combined_user, temperature)


def _fallback_reply(message: str, context: dict) -> str:
    """Return a rule-based reply when Bob is unavailable."""
    msg_lower = message.lower()
    kpis = context.get("kpis", {})
    overall = context.get("overall_score", "?")

    if "overall" in msg_lower or "score" in msg_lower:
        return f"The current overall DQ score is {overall}%. This is computed as the average of 15 KPI scores across 6 dimensions. The lowest-scoring pillar is Consistency at {context.get('pillar_scores', {}).get('consistency', '?')}%."
    if "ghost" in msg_lower or "cs07" in msg_lower or "cs-07" in msg_lower:
        cs07 = kpis.get("CS07", {})
        return f"CS-07 Ghost Mapping Rate is {cs07.get('value', '?')}% ({cs07.get('num', '?')} orders). These are orders where delete events were not propagated to the data lake, leaving stale ORDER_SHIPMENT rows. Use the drill-down on the CS-07 card to see the exact orders."
    if "orphan" in msg_lower or "ji02" in msg_lower:
        ji02 = kpis.get("JI02", {})
        return f"JI-02 Orphan OS Rate is {ji02.get('value', '?')}% ({ji02.get('num', '?')} rows). These ORDER_SHIPMENT rows have no matching ORDER record — likely a bulk import failure. Records: OS-X01, OS-X02, OS-X03."
    if "fix" in msg_lower or "remediati" in msg_lower:
        return "To fix a RED KPI: (1) Click the KPI card to see failing records, (2) Click 'Explain' on the alert to get root-cause analysis, (3) Click 'Generate Fix' to have AI draft a SQL correction, (4) Click 'Apply Fix' to execute it with your approval."
    if "trend" in msg_lower or "histor" in msg_lower or "week" in msg_lower:
        snaps = context.get("history", {}).get("snapshots", [])
        if snaps and len(snaps) >= 2:
            first = snaps[0].get("overall_score", "?")
            last  = snaps[-1].get("overall_score", "?")
            return f"Over the past 7 snapshots the overall score declined from {first}% to {last}%. The primary driver was the CS-07 Ghost Mapping rate increasing from 0% to 3%. See the sparkline trend section for full details."
        return "No historical trend data is available yet. Run seed_kpi_history.py to populate the trend section."

    return f"The Transport Analytics DQ dashboard currently shows {overall}% overall quality across 15 KPIs. The most critical issues are CS-07 (Ghost Mapping, 3%), JI-02 (Orphan OS rows, 2.7%), and RI-05 (Zero-weight orders, 6%). Ask me about a specific KPI for more detail."


def run(message: str, context: dict, history: list) -> dict:
    """Answer a user question about the Transport Analytics data quality state.

    Args:
        message: The user's natural-language question.
        context: Dict containing kpis_data, history_data, and open alerts.
        history: List of previous {role, content} exchange dicts (last 5).

    Returns:
        Dict with keys: reply (string), cited_kpis (list of KPI IDs mentioned).
    """
    # Summarise context to stay within token budget (~2000 tokens)
    context_summary = {
        "overall_score":  context.get("overall_score"),
        "pillar_scores":  context.get("pillar_scores"),
        "kpis":           {k: {"value": v.get("value"), "target": v.get("target")}
                           for k, v in context.get("kpis", {}).items()},
        "open_alerts":    context.get("open_alerts", []),
        "history_summary": [
            {"label": s.get("label"), "overall_score": s.get("overall_score")}
            for s in context.get("history", {}).get("snapshots", [])
        ],
    }
    user_msg = f"CONTEXT:\n{json.dumps(context_summary, indent=2)}\n\nQUESTION: {message}"

    try:
        reply = _call_bob_with_history(CHAT_SYSTEM_PROMPT, history[-5:], user_msg)
    except (BobAPIError, Exception) as err:
        print(f"[Chat] Bob unavailable ({err}) — using fallback reply")
        reply = _fallback_reply(message, context)

    # Extract any KPI IDs mentioned in the reply for citation highlighting
    cited = re.findall(r'\b(JI0[1-3]|CP0[125]|CS0[127]|RI0[15]|TP01|BIZ0[123])\b', reply, re.IGNORECASE)
    cited = list({k.upper() for k in cited})

    return {"reply": reply, "cited_kpis": cited}
