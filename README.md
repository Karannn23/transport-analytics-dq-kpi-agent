# Transport Analytics AI-Powered Data Quality Platform
## IBM watsonx Challenge 2026

A real-time, AI-augmented data quality monitoring and remediation platform for Transport Analytics — built with IBM Bob.

---

## What It Does

The Transport Analytics DQ Platform turns a static data quality dashboard into an **agentic AI operations centre**. Instead of just showing red/green KPI indicators, the platform:

1. **Monitors** — A Monitor Agent (powered by IBM Bob) scans 15 KPIs and generates plain-English alert explanations in seconds
2. **Explains** — A Root-Cause Agent analyses the actual failing database records and identifies the pattern causing each KPI to fail
3. **Fixes** — A Remediation Agent drafts a corrective SQL statement; the human approves with one click; the fix executes; KPIs recompute live
4. **Trends** — 7-day sparkline charts show how each metric evolved over time, making degradation patterns visible at a glance
5. **Answers** — A chat interface lets analysts ask natural-language questions about the data without writing SQL

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Dashboard (otm_live_dashboard.html)                │
│  • 15-KPI grid  • 6 sparklines  • Drill-down modal  │
│  • AI Summary panel  • Alerts panel  • Chat panel   │
└────────────────────┬────────────────────────────────┘
                     │ fetch()
┌────────────────────▼────────────────────────────────┐
│  Flask API (app.py)                                 │
│  GET  /api/kpis        POST /api/agents/monitor     │
│  GET  /api/history     POST /api/agents/rootcause   │
│  GET  /api/alerts      POST /api/agents/remediate   │
│  GET  /api/drilldown/  POST /api/agents/summary     │
│  POST /api/snapshot    POST /api/agents/chat        │
└────────┬───────────────────────────┬────────────────┘
         │ databricks-sql-connector  │ requests (HTTP)
┌────────▼──────────┐  ┌────────────▼───────────────┐
│  Databricks SQL   │  │  IBM Bob API               │
│  workspace.otm.*  │  │  (IBM Consulting Advantage)│
│  • ORDER (100)    │  │  • Monitor Agent           │
│  • ORDER_SHIP (113)  │  • Root-Cause Agent         │
│  • SHIPMENT (111) │  │  • Remediation Agent       │
│  • kpi_snapshots  │  │  • Summary Agent           │
│  • dq_alerts      │  │  • Chat Agent              │
└───────────────────┘  └────────────────────────────┘
```

---

## Setup

### Prerequisites
- Python 3.10+
- Databricks workspace with `workspace.otm.*` tables (see create scripts)
- IBM Bob API credentials (optional — rule-based fallback works without them)

### Install
```bash
pip install flask databricks-sql-connector python-dotenv requests
```

### Configure
```bash
cp .env.example .env
# Edit .env with your Databricks and Bob credentials
```

### One-time database setup
```bash
python create_kpi_snapshot_table.py   # creates kpi_snapshots table
python create_dq_alerts_table.py      # creates dq_alerts table
python seed_kpi_history.py            # seeds 7-day synthetic history
```

### Run
```bash
python app.py
# Open http://localhost:5000
```

---

## Demo Reset

To reset the demo to its initial state (undo any applied fixes):
```bash
python seed_kpi_history.py --reset    # re-seed history rows
# Re-run the original data insert scripts if fixes were applied to ORDER_SHIPMENT
```

---

## Challenge Context

Built for the **IBM watsonx Challenge 2026** (July 8–22, 2025).
The solution demonstrates how IBM Bob can be used as an intelligent copilot
for data quality operations — not just monitoring, but explaining, fixing,
and learning from data quality issues in a real supply-chain dataset.

All code, architecture, and prompt design was developed in collaboration with IBM Bob.
