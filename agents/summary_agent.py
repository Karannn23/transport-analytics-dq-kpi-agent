"""
Summary Agent — AI Executive Summary Generator
===============================================
Given the current KPI payload from /api/kpis, this agent uses IBM Bob to
generate a 3-4 sentence plain-English executive summary of the data quality state.

Usage:
    from agents.summary_agent import run
    summary = run(kpis_data)
"""

import json

from agents.bob_client import BobAPIError, call_bob
from agents.prompts import SUMMARY_SYSTEM_PROMPT


def _fallback_summary(kpis_data: dict) -> str:
    """Generate a rule-based summary when Bob is unavailable.

    Covers both lower-is-better and higher-is-better KPIs when detecting RED status.
    """
    overall = kpis_data.get("overall_score", 0)
    kpis    = kpis_data.get("kpis", {})

    def _is_red(kid: str, k: dict) -> bool:
        """True only for genuine RED (not AMBER). Matches dashboard rag() logic."""
        v, t, hib = k.get("value", 0), k.get("target_val", 0), k.get("higher_is_better", False)
        if hib:
            return v < t * 0.95
        # lower-is-better: RED only if breaches by more than 2× (zero-target: any breach is RED)
        return v > 0 if t == 0 else v > t * 2

    def _deviation(kid: str, k: dict) -> float:
        """Normalised distance from target — higher = worse, regardless of direction."""
        v, t, hib = k.get("value", 0), k.get("target_val", 100), k.get("higher_is_better", False)
        if hib:
            return (t - v) / max(t, 1)
        return (v - t) / max(t, 1) if t > 0 else v

    # Find worst RED KPI across both directions
    red_kpis = [(kid, k) for kid, k in kpis.items() if _is_red(kid, k)]
    worst = max(red_kpis, key=lambda x: _deviation(x[0], x[1]), default=None) if red_kpis else None

    # Find best GREEN KPI across both directions
    green_kpis = [
        (kid, k) for kid, k in kpis.items()
        if (k.get("higher_is_better", False) and k.get("value", 0) >= k.get("target_val", 0))
        or (not k.get("higher_is_better", False) and k.get("value", 0) == 0)
    ]

    summary_parts = [
        f"The Transport Analytics data quality platform is currently scoring {overall}% overall across 15 KPIs, indicating significant data integrity issues that require attention.",
    ]
    if worst:
        kid, k = worst
        summary_parts.append(
            f"The most critical issue is {kid} ({k.get('value',0)}% — target {k.get('target','= 0%')}), which is causing data reliability concerns in the supply chain pipeline."
        )
    if green_kpis:
        kid, k = green_kpis[0]
        summary_parts.append(
            f"On the positive side, {kid} is performing perfectly at {k.get('value',0)}%, meeting its target of {k.get('target','0%')}."
        )
    summary_parts.append(
        "Recommended action: Use the 'Run Monitor Agent' button to generate detailed alerts, then click 'Explain' on the critical KPI to get an AI-powered root-cause analysis."
    )
    return " ".join(summary_parts)


def run(kpis_data: dict) -> str:
    """Generate a 3-4 sentence executive summary of the current DQ state.

    Args:
        kpis_data: Full JSON payload from /api/kpis.

    Returns:
        Plain-English summary string (no JSON, no markdown).
    """
    user_msg = json.dumps(kpis_data, indent=2)
    try:
        return call_bob(SUMMARY_SYSTEM_PROMPT, user_msg, temperature=0.3)
    except (BobAPIError, ValueError) as err:
        print(f"[Summary] Bob unavailable ({err}) — using fallback summary")
        return _fallback_summary(kpis_data)
