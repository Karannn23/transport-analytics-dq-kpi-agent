# Agent Architecture — IBM Bob Integration

## Overview

The Transport Analytics DQ Platform uses **IBM Bob** (IBM Consulting Advantage API) as the
intelligence backbone for all five agents. Each agent follows the same pattern:

1. Build a specific system prompt (defined in `agents/prompts.py`)
2. Call Bob via `agents/bob_client.py` with the prompt + structured data
3. Parse the JSON response and store results in Databricks
4. Gracefully fall back to rule-based logic if Bob API is unavailable

---

## The Three-Tier Agentic Pipeline

```
Dashboard: "Run Monitor Agent"
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  TIER 1: Monitor Agent (agents/monitor_agent.py)                        │
│  Trigger: "Run Monitor Agent" button → POST /api/agents/monitor         │
│  Input:   15 KPI values from /api/kpis (live Databricks query)          │
│  Output:  Plain-English alerts stored in workspace.otm.dq_alerts        │
│  Bob:     Translates KPI numbers into business-impact alert messages    │
│           addressed to the responsible persona (e.g. "For the Data      │
│           Engineer: 3% of orders are ghost-mapped…")                    │
│  Fallback: Pre-written alert text in FALLBACK_MESSAGES dict             │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ alert_id + kpi_id
                              ▼  User clicks "Explain"
┌─────────────────────────────────────────────────────────────────────────┐
│  TIER 2: Root-Cause Agent (agents/rootcause_agent.py)                   │
│  Trigger: "Explain" button on an alert → POST /api/agents/rootcause     │
│  Input:   Failing database records from /api/drilldown/<kpi_id>         │
│  Output:  root_cause, pattern, affected_count,                          │
│           suggested_action, suggested_sql                                │
│  Bob:     Reads the actual failing rows and identifies the root cause   │
│           pattern tailored to the KPI owner persona                     │
│  Fallback: Pre-written analyses in FALLBACK_ANALYSES dict               │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ root_cause analysis dict
                              ▼  User clicks "Generate Fix"
┌─────────────────────────────────────────────────────────────────────────┐
│  TIER 3: Remediation Agent (agents/remediation_agent.py)                │
│  Trigger: "Generate Fix" → POST /api/agents/remediate (approve=false)  │
│           "Apply Fix"    → POST /api/agents/remediate (approve=true)    │
│  Input:   Root-cause dict from Tier 2                                   │
│  Output:  Draft SQL → User approves → Execution + Post-fix snapshot    │
│  Bob:     Writes a safe, targeted UPDATE SQL fix                        │
│  Human-in-the-loop: User MUST click "Apply Fix" to execute             │
│  Safety guards: DROP/TRUNCATE/DELETE-without-WHERE → blocked           │
│  Fallback: Uses suggested_sql from root-cause analysis                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Supporting Agents

| Agent | File | Trigger | Bob's Role | Fallback |
|-------|------|---------|-----------|----------|
| Summary | `agents/summary_agent.py` | Page load + Regenerate btn | 3-4 sentence plain-English executive summary | Rule-based summary from worst/best KPI values |
| Chat | `agents/chat_agent.py` | Chat panel user question | Answer questions with KPI + history context | Keyword-matching canned replies |

---

## KPI → Persona → Agent Ownership

Every KPI in the platform is owned by a specific persona. The agents use this
mapping to address the right stakeholder in their messages.

| KPI ID | Name | Persona | Why They Own It |
|--------|------|---------|----------------|
| JI-01  | Order-to-Shipment Match Rate | **Data Engineer** | Pipeline completeness — every order must reach a shipment |
| JI-02  | Orphan OS Rate               | **Data Engineer** | Referential integrity in ingestion pipelines |
| JI-03  | Shipment Execution Match     | **Data Engineer** | End-to-end ORDER→OS→SHIPMENT chain linkage |
| CP-01  | Order GID Null Rate          | **Data Steward**  | Business keys must be populated before downstream use |
| CP-02  | Shipment GID Null Rate       | **Data Steward**  | Null GIDs break all downstream joins and reports |
| CP-05  | Actual Dates Completeness    | **Ops Manager**   | Missing actual dates hide late deliveries from OTD |
| CS-01  | Weight Mismatch Rate         | **Data Engineer** | Weight reconciliation ensures billing accuracy |
| CS-02  | Date Sequence Violation      | **Ops Manager**   | Impossible dates indicate tracking feed errors |
| CS-07  | Ghost Mapping Rate ★         | **Data Engineer** | Ghost rows corrupt OTD and double-count weight |
| RI-01  | Invalid Shipment Status      | **Data Steward**  | Invalid enums break status-based BI filters |
| RI-03  | GID Domain Conformance       | **Data Steward**  | GID format required for Transport Analytics cross-system lookups |
| RI-05  | Zero/Negative Weight Rate    | **Finance Analyst**| Zero-weight orders cannot be costed or invoiced |
| TP-01  | Late Delivery Rate           | **Logistics Planner** | Primary SLA metric for carrier contracts |
| BIZ-01 | On-Time Delivery %           | **Supply Chain Mgr** | Drives customer satisfaction and contract KPIs |
| BIZ-02 | Zero-Weight Order Rate       | **Finance Analyst** | Skews cost-per-shipment and utilisation reports |
| BIZ-03 | Re-Assignment Rate           | **Supply Chain Mgr** | Signals planning instability and rework cost |

---

## Persona Badges (Dashboard UI)

Each KPI card displays a colour-coded persona badge:

| CSS Class | Colour | Persona | Meaning |
|-----------|--------|---------|---------|
| `persona-de`  | Blue  | ⚙ Data Engineer       | Owns pipeline, CDC, join integrity |
| `persona-ds`  | Green | 🔍 Data Steward        | Owns field conformance, null policy |
| `persona-ops` | Red   | 🏭 Ops Manager         | Owns tracking dates, OTD completeness |
| `persona-fa`  | Yellow| 💰 Finance Analyst     | Owns weight/cost accuracy |
| `persona-lp`  | Orange| 🚚 Logistics Planner   | Owns carrier SLA, late delivery |
| `persona-sc`  | Purple| 📊 Supply Chain Mgr    | Owns end-to-end OTD %, planning quality |

---

## AI Highlight Animations (Dashboard UX)

When an agent examines a KPI, the corresponding card pulses to draw attention:

| Event | CSS Class | Visual Effect |
|-------|-----------|---------------|
| Monitor Agent identifies alert | `ai-highlight` | Blue pulse, 3× over 3.6 seconds |
| Explain / Generate Fix running | `ai-highlight` | Blue pulse while agent is working |
| Fix successfully applied | `ai-fixed` | Green glow for 6 seconds |

Chat agent replies also trigger `ai-highlight` on any KPI card cited in the response.

---

## Prompt Design Principles

All prompts are in `agents/prompts.py`. Key design decisions:

1. **JSON output mode** — Every agent instructs Bob to return valid JSON so
   responses are machine-parseable. `parse_json_response()` strips markdown
   code fences that some LLMs add around JSON.

2. **Persona-aware language** — Each prompt includes the full KPI→persona
   ownership map. Bob addresses the responsible stakeholder directly in its
   output (e.g. "For the Data Engineer: …").

3. **Static data context** — Each prompt includes a note that the data is a
   static Transport Analytics sample with known anomalies, making Bob's answers specific and
   grounded rather than generic.

4. **Temperature** — 0.2 for structured JSON outputs (monitor, rootcause,
   remediation), 0.3 for natural-language outputs (summary, chat).

5. **Token budget** — Root-cause agent caps drill-down records at 20 rows.
   Chat agent summarises context to stay under ~2,000 tokens per request.

---

## Human-in-the-Loop Safety Model

The Remediation Agent never executes SQL without explicit user confirmation:

```
Generate Fix          →  User reads SQL and risk level
   (draft shown)              ↓
                         Apply Fix button clicked
                              ↓
                         Confirm dialog ("cannot be undone")
                              ↓
                         SQL executes on Databricks
                              ↓
                         KPIs recompute + Post-fix snapshot saved
                              ↓
                         CS-07 card turns GREEN (ai-fixed)
```

Additional safety guards in `agents/remediation_agent.py`:

- **Blocked patterns**: `DROP`, `TRUNCATE`, bare `DELETE` without `WHERE`
- **Schema restriction**: Only `workspace.otm.*` tables are targeted
- **Risk labelling**: Bob rates each fix LOW / MEDIUM / HIGH before the user
  sees the confirm button

---

## Fallback Mode (No Bob API)

All agents have a rule-based fallback activated when `BOB_API_KEY` is not set
or when the API call fails after 3 retries. The full demo flow works without
Bob credentials.

| Agent | Fallback source |
|-------|----------------|
| Monitor | `FALLBACK_MESSAGES` dict in `monitor_agent.py` |
| Root-Cause | `FALLBACK_ANALYSES` dict in `rootcause_agent.py` |
| Remediation | Uses `suggested_sql` from root-cause analysis |
| Summary | `_fallback_summary()` function in `summary_agent.py` |
| Chat | `_fallback_reply()` keyword-matching in `chat_agent.py` |

Fallbacks are logged as: `[Agent] Bob unavailable — using fallback`

---

## File Reference

```
agents/
├── __init__.py             — package marker
├── bob_client.py           — IBM Bob API wrapper (retry, parse, BobAPIError)
├── prompts.py              — all system prompts (persona-aware, JSON-output)
├── monitor_agent.py        — Tier 1: alert generation
├── rootcause_agent.py      — Tier 2: root-cause analysis
├── remediation_agent.py    — Tier 3: SQL draft + safe execution
├── summary_agent.py        — executive summary generator
└── chat_agent.py           — conversational Q&A with history
```
