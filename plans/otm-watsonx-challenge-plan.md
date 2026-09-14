# Transport Analytics Live DQ Dashboard — IBM watsonx Challenge 2026 Elevation Plan

## Overview

**Goal**: Elevate the Transport Analytics (Transport Analytics) Live Data Quality Dashboard from a
read-only monitoring tool into an AI-powered, agentic data quality operations platform for the
IBM watsonx Challenge 2026 (July 8–22).

**Important: Static Data Constraint**
The Databricks tables (`workspace.otm.ORDER`, `ORDER_SHIPMENT`, `SHIPMENT`) contain seeded,
static sample data that does not change between runs. This is by design — the data represents
a realistic snapshot of an Transport Analytics deployment with intentional DQ anomalies baked in. All features
must work correctly with static data:
- Historical trending is achieved by **pre-seeding synthetic snapshot rows** into
  `kpi_snapshots` that simulate how metrics evolved over 7 days leading to today's state.
- The Monitor Agent runs **on-demand** (triggered by a button or API call), not as a cron job.
- The Remediation Agent's "Apply Fix" executes a real SQL UPDATE against the seeded data,
  which does change the data — this is intentional and is the **demo centrepiece** (user sees
  a RED KPI go GREEN after approving the fix).
- Auto-refresh in the dashboard is **disabled by default** (no point polling static data);
  replaced with a manual "Re-compute KPIs" button.

**Scope**: The existing project has a solid foundation — a Flask + Databricks SQL backend, 12
KPIs across 5 quality dimensions, and a live HTML dashboard. The elevation adds four layers:

1. **Agentic AI Layer** — A three-tier agent system (Monitor → Root-Cause → Remediation) powered
   by IBM Bob (IBM Consulting Advantage API) that detects RED KPIs, explains why, suggests fixes,
   and allows human-in-the-loop remediation approval against the static dataset.
2. **Historical Trending Layer** — Pre-seeded 7-day KPI snapshot history in Databricks with
   sparkline charts in the dashboard, simulating a realistic week of operations.
3. **Expanded KPI Framework** — Three new business-level KPIs: On-Time Delivery %, Zero-Weight
   Order Rate, and Shipment Re-Assignment Rate, bringing the total to 15 KPIs.
4. **Dashboard Intelligence Layer** — Drill-down tables on RED KPI cards, an AI-narrated
   executive summary panel, and a chat interface so users can ask questions about the data.

**Challenge Alignment**:
- Practicality: Solves a real supply-chain DQ pain — ghost shipments, orphan records, date
  violations — that exist in every Transport Analytics deployment. Static data proves the concept cleanly.
- Effectiveness: Automated root-cause analysis and remediation suggestions cut manual
  investigation time from hours to seconds, demonstrated live on the seeded anomalies.
- Design: Dashboard-first UX — all AI insights surface inline, no separate tool required.
- Creativity: Fully agentic DQ pipeline built on IBM Bob is novel in the supply-chain space.

**Approach**: Backend-first, then data layer, then agent layer, then dashboard enhancements.
Each sub-task is independently reviewable and deployable.

**Non-goals**:
- Real-time data ingestion or CDC pipeline (data is static/seeded)
- Cron-based polling (on-demand triggering only)
- Multi-tenant support
- Production-grade OAuth2 authentication
- Mobile-first redesign

---

## Sub-Task 1 — Data Layer: KPI Snapshot Table + Synthetic History Seed

**Intent**
Create a new Databricks table `workspace.otm.kpi_snapshots` and pre-populate it with 8 rows of
synthetic history (7 "past days" + 1 "today") that simulate how the Transport Analytics Data Quality metrics
evolved over a realistic week. Since the underlying data is static and does not change between
runs, historical trending is achieved through a one-time seed script that hard-codes plausible
day-by-day KPI values showing a gradual degradation pattern — mirroring how ghost shipments and
orphan records would accumulate in a real deployment. This table is the data foundation for all
sparkline charts and AI anomaly detection downstream.

**Expected Outcomes**
- `workspace.otm.kpi_snapshots` table exists with columns for timestamp, overall_score,
  all 15 KPI values (after ST-4 adds the 3 new KPIs), and all pillar scores.
- `seed_kpi_history.py` script inserts 8 synthetic rows representing Jun 14–Jul 20, 2025,
  with KPI values that tell a coherent story: metrics start clean (~88%), degrade over the
  week as ghost mappings accumulate, ending at today's observed 74%.
- The "today" row (Jul 20) exactly matches the values returned by `/api/kpis` so the
  sparkline's last data point is consistent with the live KPI panel.
- A `/api/snapshot` POST endpoint exists so a user can manually capture a new snapshot
  after approving a remediation fix (ST-8) — this is the only time new rows are added during
  the demo.
- `app.py /api/kpis` response is unchanged — snapshot logic is additive.

**Todo List**
- [ ] Create `create_kpi_snapshot_table.py` — DDL for `workspace.otm.kpi_snapshots`:
      `snapshot_id` (BIGINT auto-increment), `captured_at` (TIMESTAMP), `overall_score` (FLOAT),
      `pillar_join` (FLOAT), `pillar_completeness` (FLOAT), `pillar_consistency` (FLOAT),
      `pillar_timeliness` (FLOAT), `pillar_referential` (FLOAT),
      `ji01`, `ji02`, `ji03`, `cp01`, `cp02`, `cp05`, `cs01`, `cs02`, `cs07`,
      `ri01`, `ri05`, `tp01` (all FLOAT), nullable columns `biz01`, `biz02`, `biz03` (FLOAT)
      for the 3 new business KPIs added in ST-4, plus `label` (STRING) for human-readable tags
      like "Baseline", "Day 3 — Ghost detected", "Post-fix".
- [ ] Run `create_kpi_snapshot_table.py` against Databricks to verify table creation.
- [ ] Create `seed_kpi_history.py` — inserts 8 hard-coded rows with realistic values:
      Day 1 (Jun 14): overall=88, JI01=99, JI02=0.8, CS07=0 (clean baseline)
      Day 2 (Jun 17): overall=86, JI01=98, JI02=1.2, CS07=1 (first ghost appears)
      Day 3 (Jun 20): overall=83, JI01=97, JI02=1.8, CS07=1.5 (degrading)
      Day 4 (Jun 23): overall=81, JI01=96, JI02=2.0, CS07=2 (orphans growing)
      Day 5 (Jun 27): overall=79, JI01=95, JI02=2.3, CS07=2.5 (continued drift)
      Day 6 (Jul 03): overall=77, JI01=94, JI02=2.5, CS07=3 (RED threshold crossed)
      Day 7 (Jul 13): overall=75, JI01=94, JI02=2.7, CS07=3 (plateau at RED)
      Day 8 / Today (Jul 20): overall=74 — exact values from live `/api/kpis` response.
      All other KPI columns (CP01, CP02, RI01, etc.) stay constant across all rows since
      they are driven by static data — only the ghost/orphan KPIs drift.
- [ ] Add `POST /api/snapshot` endpoint to `app.py`: re-computes all KPIs (calls the same
      CTE query used by `/api/kpis`), inserts a new row into `kpi_snapshots` with
      `captured_at = NOW()` and label `"Post-fix"`. Returns the new row's `snapshot_id`.
      This endpoint is called automatically by ST-8 after a remediation fix is applied.
- [ ] Document in `seed_kpi_history.py` header comment that these rows are synthetic for
      demo purposes and that the "Post-fix" row is appended dynamically during the demo.

**Relevant Context**
- `databricks_connection.py` — reuse `DatabricksManager` for all DB operations.
- `app.py` — `/api/kpis` response structure is the source of truth for column mapping.
- Databricks schema: `workspace.otm.*`.
- The synthetic degradation story (ghost mappings accumulating over 6 days) mirrors exactly
  what `CS-07 Ghost Mapping Rate` and `JI-02 Orphan OS Rate` are detecting in the live data.
  This makes the history believable and consistent with the seeded anomalies.

**Status** — `[x] done`

---

## Sub-Task 2 — Backend: Historical Trending API Endpoint

**Intent**
Expose a new `/api/history` endpoint that returns the KPI snapshot rows from
`workspace.otm.kpi_snapshots` (pre-seeded in ST-1). Since the data is static the table contents
are fixed between demos; the endpoint simply reads and returns all rows ordered oldest-first.
The only time the row count grows is when a user approves a remediation fix (ST-8 appends a
"Post-fix" row via `/api/snapshot`).

**Expected Outcomes**
- `GET /api/history` returns a JSON array of all snapshot rows, ordered oldest-first.
- Each row contains `captured_at`, `label`, `overall_score`, all pillar scores, and all KPI
  values.
- Response is fast (<200 ms) because the table has at most ~10 rows at demo time.
- If the table is empty (seed not yet run), returns `{ "snapshots": [], "count": 0 }` without
  error, and the dashboard shows a placeholder message instead of sparklines.

**Todo List**
- [ ] Add `GET /api/history` route to `app.py`.
- [ ] Query: `SELECT * FROM workspace.otm.kpi_snapshots ORDER BY captured_at ASC` — no LIMIT
      needed since the table is small by design.
- [ ] Return JSON: `{ "snapshots": [...], "count": N }`.
- [ ] No caching needed — data is static and the table is tiny; a direct query on every load
      is acceptable and simpler.

**Relevant Context**
- `app.py` — follow the same pattern as `/api/kpis` for route and cursor reuse.
- `get_cursor()` helper already handles reconnect logic — reuse it.
- Cache pattern: use a module-level `dict` with `{"data": ..., "fetched_at": datetime}`.

**Status** — `[x] done`

---

## Sub-Task 3 — Dashboard: Sparkline Trend Charts + Snapshot History Panel

**Intent**
Add a trend section to `otm_live_dashboard.html` that shows mini sparkline charts for Overall
Score and each of the 5 pillar scores, sourced from the pre-seeded `kpi_snapshots` table. A
compact history table below the sparklines shows each snapshot row with its label, timestamp,
overall score, and delta vs. previous row — telling the degradation story visually.

Since data is static, this section loads once on page open and does not need to refresh.
The auto-refresh countdown timer in the existing dashboard is **removed** (replaced with a
single "Re-compute KPIs" manual button) because polling a static database adds no value.

**Expected Outcomes**
- Dashboard calls `/api/history` once on load alongside `/api/kpis` using `Promise.all`.
- A "Data Quality Trend" section appears below the Pillar Scores grid with 6 sparkline SVG
  charts (Overall + 5 pillars), each 140×50 px inline SVG rendered in pure JavaScript.
- A compact history table below the sparklines shows each snapshot row: label, date, score,
  colour-coded Δ (delta vs. previous row). The "today" row (Jul 20) is highlighted.
- If `/api/history` returns < 2 rows, the section shows a yellow notice: "Trend data not yet
  seeded — run seed_kpi_history.py" instead of charts.
- The existing 5-minute auto-refresh countdown and progress bar are **removed** from the
  dashboard; replaced with a "Re-compute KPIs" button (calls `/api/kpis` on demand).
- After a remediation fix is approved (ST-8), the sparkline section re-fetches `/api/history`
  and appends the new "Post-fix" data point to each chart, making the improvement visible.

**Todo List**
- [ ] Remove the `startCountdown()` function, the auto-refresh progress bar HTML, and the
      `setInterval` call from `otm_live_dashboard.html`.
- [ ] Replace with a `<button id="recompute-btn">Re-compute KPIs</button>` that calls
      `loadData()` on click and shows a loading spinner while in flight.
- [ ] Add `loadHistory()` async function that fetches `/api/history`.
- [ ] Call `loadHistory()` in parallel with `loadData()` on page load using `Promise.all`.
- [ ] Write `renderSparkline(containerId, values, labels, colorHex)` — a pure-JS function
      that draws an inline SVG polyline given an array of numeric values; scales min/max to the
      SVG viewport; adds a tooltip on hover showing the label and value.
- [ ] Write `renderHistoryTable(snapshots)` — renders a compact `<table>` with columns:
      Label, Date, Score, Δ — with green/red colour on Δ cell; "today" row bolded.
- [ ] Add HTML section `<section id="trend-section">` with 6 sparkline containers and a
      history table placeholder `<div id="history-table-container">`.
- [ ] Style: sparkline containers are small cards matching the existing pillar card style,
      arranged in a 3-column grid (same grid as pillar scores).
- [ ] Store history data on `window._historyData` after first load so ST-8 can re-render
      sparklines by calling `renderSparkline` again without a new fetch.

**Relevant Context**
- `otm_live_dashboard.html` — `render()`, `loadData()` are the integration points.
- No external charting library — use inline SVG to keep the dashboard self-contained.
- Pillar score keys: `join_integrity`, `completeness`, `consistency`, `timeliness`, `referential`.

**Status** — `[x] done`

---

## Sub-Task 4 — Backend: Three New Business KPIs

**Intent**
Add three business-level KPIs that go beyond data quality into operational performance, giving
the challenge submission a stronger business impact story:

- **BIZ-01: On-Time Delivery %** — `COUNT(shipments where actual_arrival <= planned_delivery
  AND actual_arrival IS NOT NULL)` / `COUNT(non-cancelled closed shipments)`. Target ≥ 95%.
- **BIZ-02: Zero-Weight Order Rate** — Already partially covered by RI-05 but split to isolate
  orders (`COUNT(orders where total_weight_kg = 0)` / total orders). Target = 0%. Rename
  existing RI-05 to cover shipments only, add BIZ-02 for orders.
- **BIZ-03: Shipment Re-Assignment Rate** — `COUNT(ORDER_SHIPMENT rows with dq_flag =
  'Re-assigned')` / total OS rows. Target ≤ 2%. Measures how often a shipment assignment is
  corrected, a leading indicator of planning quality.

**Expected Outcomes**
- Three new KPI fields (`biz01`, `biz02`, `biz03`) appear in the `/api/kpis` JSON response
  under the `kpis` dict with `value`, `num`, `den`, `target`, `target_val`, `higher_is_better`.
- Overall score recomputed as average of 15 KPI scores (previously 12).
- A new "Business Performance" pillar score appears in `pillar_scores` (avg of BIZ-01..03).
- `kpi_snapshots` table columns `biz01`, `biz02`, `biz03` (reserved in ST-1) are now populated
  in `archive_snapshot.py`.

**Todo List**
- [ ] Add `biz01`, `biz02`, `biz03` computations to the batched CTE query in `app.py`.
      BIZ-01: `COUNT(CASE WHEN s.actual_arrival <= s.planned_delivery AND s.actual_arrival IS
      NOT NULL AND s.status = 'Closed' THEN 1 END)` / `COUNT(CASE WHEN s.status = 'Closed'
      THEN 1 END)`.
      BIZ-02: `COUNT(CASE WHEN o.total_weight_kg = 0 THEN 1 END)` / total_orders (already have
      this as `ri05_ord` — alias and expose separately).
      BIZ-03: `COUNT(CASE WHEN os.dq_flag = 'Re-assigned' THEN 1 END)` / total_os.
- [ ] Add `biz_score` to `pillar_scores` in the JSON response.
- [ ] Recompute `overall_score` to include all 15 KPI scores.
- [ ] Update `kpi_score` calls list to include the 3 new KPIs.
- [ ] Update `archive_snapshot.py` to read and store `biz01`, `biz02`, `biz03` from the API.

**Relevant Context**
- `app.py` — CTE query block; `kpi_scores` list; `pillar_scores` dict construction.
- `workspace.otm.SHIPMENT` columns: `planned_delivery`, `actual_arrival`, `status`.
- `workspace.otm.ORDER` columns: `total_weight_kg`.
- `workspace.otm.ORDER_SHIPMENT` columns: `dq_flag`.

**Status** — `[x] done`

---

## Sub-Task 5 — Dashboard: Drill-Down Tables for RED KPIs

**Intent**
Add a new `/api/drilldown/<kpi_id>` endpoint and a modal panel in the dashboard so clicking any
RED or AMBER KPI card opens a table showing the exact failing records. This makes the dashboard
actionable — users can immediately see which orders/shipments are causing a KPI to be RED without
writing SQL.

**Expected Outcomes**
- `GET /api/drilldown/JI02` returns up to 50 rows from `workspace.otm.ORDER_SHIPMENT` where
  `order_release_gid` has no match in `workspace.otm.ORDER`, with columns: `os_id`,
  `order_release_gid`, `shipment_gid`, `dq_flag`.
- Similar drill-down queries exist for: JI01, CS07, CS02, RI01, RI05, TP01, BIZ01, BIZ02,
  BIZ03. Each returns the affected entity rows with relevant columns.
- Clicking a RED/AMBER KPI card on the dashboard opens a modal overlay showing the drill-down
  table.
- Modal has a close button and a "Copy as CSV" button.
- If no failing records exist (KPI is GREEN), clicking shows "No issues found ✓".

**Todo List**
- [ ] Add `GET /api/drilldown/<kpi_id>` route to `app.py`.
- [ ] Write a `DRILLDOWN_QUERIES` dict mapping each KPI ID to a SQL template string that
      returns the relevant failing rows (up to 50, ordered by most-recently-created or by
      severity).
      JI01: OS-less orders; JI02: orphan OS rows; CS07: ghost-mapped orders;
      CS02: date-seq-violated shipments; RI01: invalid-status shipments;
      RI05: zero-weight shipments; TP01: late shipments; BIZ01: on-time delivery detail;
      BIZ02: zero-weight orders; BIZ03: re-assigned OS rows.
- [ ] Return JSON: `{ "kpi_id": "JI02", "records": [...], "columns": [...], "count": N }`.
- [ ] Add a `<dialog id="drilldown-modal">` element to `otm_live_dashboard.html` with a header,
      a dynamic `<table>` body, and footer buttons (Close, Copy CSV).
- [ ] Add `openDrilldown(kpiId, label)` JS function: fetches `/api/drilldown/{kpiId}`, renders
      the table, opens the dialog.
- [ ] Make KPI cards clickable: add `onclick="openDrilldown('JI02', 'Orphan OS Rate')"` to
      each card's container `<div>`.
- [ ] Show a spinner inside the modal while the fetch is in flight.
- [ ] Add `copyCsv()` function: converts the rendered table to CSV string, writes to clipboard
      via `navigator.clipboard.writeText()`.

**Relevant Context**
- `app.py` — add route alongside `/api/kpis`; reuse `get_cursor()`.
- `otm_live_dashboard.html` — `kpiCard()` function generates each card; add onclick there.
- `<dialog>` element has native browser support in all modern browsers — no JS modal library
  needed.

**Status** — `[x] done`

---

## Sub-Task 6 — Agentic AI: Monitor Agent (KPI Alerting)

**Intent**
Build the first of three agents: the **Monitor Agent**. Since the underlying data is static and
does not change on its own, this agent runs **on-demand** — triggered either by clicking a
"Run Monitor Agent" button in the dashboard or by calling `POST /api/agents/monitor`. It reads
the current `/api/kpis` snapshot, compares each KPI against its target, and uses IBM Bob to
produce structured plain-English alerts explaining what is wrong and why it matters.

Alerts are written to `workspace.otm.dq_alerts` so they persist across page loads and can be
acted on by the Root-Cause (ST-7) and Remediation (ST-8) agents. For the demo, running the
Monitor Agent once at the start populates a realistic set of open alerts that the rest of the
demo flow resolves.

**Expected Outcomes**
- `agents/monitor_agent.py` exists and can be imported and called from `app.py`.
- `POST /api/agents/monitor` endpoint triggers the agent, writes alerts to `dq_alerts`,
  returns the list of newly created alerts as JSON.
- Alerts written to `workspace.otm.dq_alerts`: `alert_id`, `created_at`, `kpi_id`,
  `kpi_value`, `target_value`, `severity` (RED/AMBER), `message` (Bob's explanation),
  `status` (Open/Acknowledged/Resolved).
- `GET /api/alerts` returns all open alerts ordered by severity then `created_at`.
- Dashboard Alerts Panel has a "Run Monitor Agent" button that calls the POST endpoint,
  shows a spinner, then populates the alerts list. Subsequent clicks do not duplicate alerts
  (agent checks if an open alert for that KPI already exists before inserting).
- If Bob API is unavailable, the agent falls back to a rule-based generator that creates
  canned-text alerts for each RED/AMBER KPI without an LLM call.

**Todo List**
- [ ] Create `workspace.otm.dq_alerts` table via `create_dq_alerts_table.py`.
- [ ] Create `agents/` directory; create `agents/__init__.py`.
- [ ] Create `agents/monitor_agent.py`:
      - Load `.env` for Bob API URL and API key (`BOB_API_URL`, `BOB_API_KEY`).
      - Fetch `/api/kpis` (requires Flask running, or import and call the logic directly).
      - Build system prompt: describes the KPI schema, targets, and asks Bob to return a JSON
        array of alerts for every RED/AMBER KPI, with fields `kpi_id`, `severity`, `message`,
        `recommendation`. Instruct Bob that the data is a static Transport Analytics sample with known anomalies.
      - Call Bob API via `requests.post()` with the system prompt + KPI JSON as user message.
      - Parse the response JSON array.
      - For each alert, check if an Open alert for that `kpi_id` already exists in `dq_alerts`;
        skip if it does (deduplication). Insert only new alerts.
      - If `BOB_API_KEY` not set, run rule-based fallback: any KPI with RAG=RED → insert alert
        with a canned message string (no LLM call).
- [ ] Create `agents/bob_client.py`: thin wrapper around the Bob API HTTP call with retry logic
      (max 3 retries, exponential backoff). Accepts `system_prompt`, `user_message`, returns
      parsed JSON or raises `BobAPIError`.
- [ ] Add `POST /api/agents/monitor` route to `app.py` that calls monitor agent logic inline.
- [ ] Add `GET /api/alerts` route to `app.py`: `SELECT * FROM workspace.otm.dq_alerts WHERE
      status = 'Open' ORDER BY severity DESC, created_at DESC`.
- [ ] Add an **Alerts Panel** to `otm_live_dashboard.html`: replaces the current hard-coded
      "Active Issues Log" table with a live panel that shows alerts from `/api/alerts`, each
      row having severity badge, KPI ID, message, and "Explain" + "Fix" buttons.
- [ ] Add "Run Monitor Agent" button to the dashboard (top of Alerts Panel) that calls
      `POST /api/agents/monitor`, shows a spinner, then reloads the alerts panel.
- [ ] Update `.env.example` with `BOB_API_URL` and `BOB_API_KEY` placeholder entries.

**Relevant Context**
- IBM Bob / IBM Consulting Advantage API: REST endpoint, Bearer token auth. See Bob Docs for
  the current API schema. The agent sends a `messages` array (system + user) and expects the
  model to return valid JSON.
- `databricks_connection.py` — reuse for alert writes.
- Since data is static, the Monitor Agent is run once per demo session, not continuously.
  The deduplication check ensures re-running it doesn't flood the alerts table.

**Status** — `[x] done`

---

## Sub-Task 7 — Agentic AI: Root-Cause Agent (Explain + Analyse)

**Intent**
Build the second agent: the **Root-Cause Agent**. When a RED alert is raised (by the Monitor
Agent or by the user clicking "Explain" on an alert), this agent: (1) fetches the drill-down
records for that KPI, (2) asks Bob to analyse the records and identify patterns (e.g., "all 3
orphan OS rows reference order IDs starting with OS-X, suggesting a bulk import failure"),
(3) returns a structured explanation with `root_cause`, `affected_records`, `pattern`, and
`suggested_action` fields.

**Expected Outcomes**
- `agents/rootcause_agent.py` script exists.
- `POST /api/agents/rootcause` endpoint accepts `{ "kpi_id": "JI02", "alert_id": "..." }`.
- Endpoint fetches drill-down records, passes them to Bob, returns a JSON analysis object.
- Response is stored in `workspace.otm.dq_alerts` — the `message` column is updated with the
  root-cause analysis, `status` changes to `In Review`.
- In the dashboard Alerts Panel, each alert row has an "Explain" button that calls this
  endpoint and renders the analysis inline below the alert row (expandable).

**Todo List**
- [ ] Create `agents/rootcause_agent.py`:
      - Accept `kpi_id` as input.
      - Fetch drill-down data from `/api/drilldown/{kpi_id}` (or call the DB query directly).
      - Build system prompt: "You are a data quality analyst for Transport Analytics.
        Given these failing records for KPI {kpi_id}, identify the root cause pattern,
        explain in 2-3 sentences, and suggest one corrective SQL action."
      - Call `bob_client.py` with records as user message (JSON-serialised, max 20 records to
        stay within token limits).
      - Return structured JSON: `{ "kpi_id", "root_cause", "pattern", "affected_count",
        "suggested_action", "suggested_sql" }`.
- [ ] Add `POST /api/agents/rootcause` route to `app.py` that calls `rootcause_agent.py` logic
      inline (not subprocess), updates the alert row in `dq_alerts`.
- [ ] Add "Explain" button to each alert row in the Alerts Panel; clicking it calls the
      endpoint and shows a loading spinner, then renders the analysis in an expandable section
      below the row.
- [ ] Cap drill-down records passed to Bob at 20 rows; if more exist, add a note "...and N
      additional records with the same pattern" to the user message.

**Relevant Context**
- `agents/bob_client.py` — reuse from ST-6.
- `app.py /api/drilldown/<kpi_id>` — reuse from ST-5 for record fetching.
- `workspace.otm.dq_alerts` — `message` and `status` columns to update.
- Bob system prompt design: Be specific about the expected JSON output format to ensure
  parseable responses; include a JSON schema example in the prompt.

**Status** — `[x] done`

---

## Sub-Task 8 — Agentic AI: Remediation Agent (Human-in-the-Loop SQL Fix)

**Intent**
Build the third agent: the **Remediation Agent**. Given the root-cause analysis from ST-7, this
agent drafts a corrective SQL statement (e.g., `UPDATE workspace.otm.order_shipment SET
lake_status = 'STALE' WHERE os_id IN ('OS-X01', 'OS-X02', 'OS-X03')`), presents it to the user
for approval in the dashboard, and — upon approval — executes it against Databricks and
triggers a fresh `/api/kpis` refresh to validate the fix improved the score.

This is the highest-impact demo: a single analyst can go from "RED KPI" to "fix approved and
applied" in under 60 seconds using only the dashboard.

**Expected Outcomes**
- `agents/remediation_agent.py` exists.
- `POST /api/agents/remediate` accepts `{ "alert_id", "approve": true/false }`.
  - If `approve: false`: generates and returns a draft SQL fix (does NOT execute).
  - If `approve: true`: executes the SQL, triggers a snapshot, returns the new KPI values.
- In the dashboard, the root-cause analysis panel (from ST-7) includes a "Generate Fix" button.
- Clicking "Generate Fix" calls `/api/agents/remediate` with `approve: false`, shows the
  draft SQL in a code block with syntax highlighting.
- An "Apply Fix" button (with a red confirmation step: "Are you sure?") calls
  `/api/agents/remediate` with `approve: true`.
- After a successful fix, the dashboard auto-refreshes KPIs and the relevant KPI card
  animates from RED to GREEN (or AMBER).
- A `remediation_log` column in `dq_alerts` records the applied SQL and timestamp.

**Todo List**
- [ ] Create `agents/remediation_agent.py`:
      - Accept `kpi_id`, `root_cause_analysis` (from ST-7 output) as input.
      - Build system prompt: "You are a Databricks SQL engineer. Given this root-cause
        analysis for KPI {kpi_id}, write a single safe UPDATE or DELETE SQL statement that
        corrects the data quality issue. Only use tables in workspace.otm. Return JSON with
        fields: `sql`, `explanation`, `risk_level` (LOW/MEDIUM/HIGH), `rows_affected_estimate`."
      - Call `bob_client.py`.
      - Return the draft SQL without executing.
- [ ] Add `POST /api/agents/remediate` route to `app.py`.
      - On `approve: false`: call `remediation_agent.py` logic, return draft SQL + metadata.
      - On `approve: true`: execute the SQL via `get_cursor()`, trigger `/api/snapshot`, return
        updated KPI values. Wrap execution in a try/except — on failure return error without
        committing.
- [ ] Add `remediation_log` TEXT column to `workspace.otm.dq_alerts` (ALTER TABLE or recreate).
- [ ] In the dashboard, add "Generate Fix" → SQL preview → "Apply Fix" UI flow below the
      root-cause panel. Use a `<pre><code>` block for SQL display.
- [ ] Add a "Remediation History" mini-table below the Alerts Panel showing the last 5 applied
      fixes with timestamp, KPI, and SQL snippet.
- [ ] Safety guard: if Bob returns a SQL containing `DROP`, `TRUNCATE`, or `DELETE FROM` (full
      table), reject it automatically and return an error to the user.

**Relevant Context**
- `agents/bob_client.py` — reuse from ST-6.
- `get_cursor()` in `app.py` — reuse for SQL execution.
- Safety is critical: only UPDATE/INSERT/DELETE WHERE statements with explicit WHERE clauses
  should be approved for execution.
- The human-in-the-loop approval step is the key differentiator from a fully autonomous agent
  — keep it prominent in the UI.

**Status** — `[x] done`

---

## Sub-Task 9 — Dashboard: AI Executive Summary Panel + Chat Interface

**Intent**
Add two AI-powered UX features to the dashboard:

1. **AI Executive Summary**: A panel at the top of the dashboard (below the Overall Score card)
   that shows a 3-4 sentence plain-English summary of the current data quality state, generated
   by Bob from the live KPI JSON. Refreshes with each data load.
2. **Ask the Data Agent** chat interface: A collapsible chat panel in the bottom-right corner
   of the dashboard. Users type natural-language questions (e.g., "Which orders are causing the
   Ghost Mapping issue?", "What is the trend in Join Integrity over the past week?") and receive
   answers from Bob, which has access to the KPI data, history data, and drill-down data as
   tools.

**Expected Outcomes**
- `POST /api/agents/summary` endpoint accepts the current KPI JSON and returns a 3-4 sentence
  executive summary string from Bob.
- The summary panel renders below the overall score, with a "Regenerate" button.
- `POST /api/agents/chat` endpoint accepts `{ "message": "...", "context": {...} }` where
  `context` contains the current KPI snapshot, last 7 history rows, and open alerts.
- The chat panel renders at bottom-right, toggleable by a chat icon button.
- Bob is instructed to: answer from the provided context data only, cite specific KPI values,
  and suggest using the "Explain" or "Generate Fix" features for actionable items.
- Chat history (last 5 exchanges) is stored in `sessionStorage` and pre-pended to each new
  request so Bob has conversation context.
- Both summary and chat have graceful degradation: if Bob API is unavailable, summary shows
  "AI summary unavailable — API key not configured" and chat shows an offline message.

**Todo List**
- [ ] Create `agents/summary_agent.py`:
      - Accept KPI JSON dict as input.
      - System prompt: "You are an IBM data quality analyst. Given these KPI metrics for an
        Transport Analytics system, write a 3-4 sentence executive summary. Mention the
        overall score, the most critical RED KPI, and one positive finding. Be concise and
        professional."
      - Call `bob_client.py`, return summary string.
- [ ] Add `POST /api/agents/summary` route to `app.py`.
- [ ] Create `agents/chat_agent.py`:
      - Accept `message`, `context` (KPI + history + alerts JSON), `history` (list of
        previous exchanges) as input.
      - System prompt defines Bob's role and available data, instructs to answer in ≤ 150 words.
      - Call `bob_client.py` with conversation history included in messages array.
      - Return `{ "reply": "...", "cited_kpis": [...] }`.
- [ ] Add `POST /api/agents/chat` route to `app.py`.
- [ ] Add AI Summary panel HTML to `otm_live_dashboard.html` — a styled card with an AI icon,
      the summary text, and a "Regenerate" button. Call `POST /api/agents/summary` after each
      `loadData()` completion.
- [ ] Add chat UI to `otm_live_dashboard.html`: a floating button (bottom-right), a chat panel
      that expands on click, message input, send button, and message history area. Style with
      IBM Carbon-inspired colours.
- [ ] Add `sendChatMessage()` JS function: reads input, appends user bubble, calls
      `/api/agents/chat`, appends Bob reply bubble. Stores history in `sessionStorage`.

**Relevant Context**
- `agents/bob_client.py` — reuse; pass `messages` array (system + alternating user/assistant).
- `otm_live_dashboard.html` — add after overall score card in the layout flow.
- Token budget: keep context passed to chat < 2000 tokens. Summarise history data if needed.
- Chat panel Z-index should be above all other elements; use `position: fixed`.

**Status** — `[x] done`

---

## Sub-Task 10 — Submission Packaging: Documentation + Demo Script + Pitch File

**Intent**
Prepare all challenge submission artefacts: a `README.md` with setup instructions, an
`ARCHITECTURE.md` with a system diagram description, a `DEMO_SCRIPT.md` with a step-by-step
demo walkthrough, and a `SUBMISSION.md` with the solution statement, technical statement, and
impact assessment required by the challenge submission form.

**Expected Outcomes**
- `README.md` (root): Project overview, setup steps (pip install, .env config, Flask start,
  run `seed_kpi_history.py`, Flask serves dashboard), screenshot/GIF placeholder. Includes a
  note that data is seeded/static and explains how to reset the demo (re-run seed scripts).
- `ARCHITECTURE.md`: Describes the 4-layer architecture (Data → API → Agents → Dashboard),
  lists all components and their interactions, explains the Bob API integration, and notes the
  static data design decision.
- `DEMO_SCRIPT.md`: 5-minute demo walkthrough for **static data**:
  (1) Open dashboard — see 74% overall, 4 RED KPIs, sparklines showing week-long degradation.
  (2) Click "Run Monitor Agent" — Bob generates 5 plain-English alerts in seconds.
  (3) Click "Explain" on the CS-07 Ghost Mapping alert — Bob identifies the 3 ghost OS rows.
  (4) Click "Generate Fix" — Bob drafts a corrective UPDATE SQL statement.
  (5) Click "Apply Fix" + confirm — SQL executes, `/api/snapshot` fires, KPI refreshes.
  (6) Watch CS-07 card turn GREEN, overall score tick up, sparkline gains a "Post-fix" point.
  (7) Ask chat "What changed after the fix?" — Bob answers from the new snapshot data.
  Includes fallback script if Bob API is unavailable (use rule-based mode + cached responses).
- `SUBMISSION.md`: Pre-written solution statement (≤ 500 words), technical statement (≤ 300
  words), and impact assessment. Notes that static data was used intentionally to create a
  reproducible, consistent demo environment — as recommended by the challenge guidelines.
- `AGENTS.md`: Three-agent architecture, Bob prompt design rationale, human-in-the-loop safety
  model, and note that static data makes the demo deterministic and judging-friendly.
- All Python files have docstrings. All agent prompt strings in `agents/prompts.py`.

**Todo List**
- [ ] Create `agents/prompts.py` — extract all Bob system prompts from all agents into named
      constants: `MONITOR_SYSTEM_PROMPT`, `ROOTCAUSE_SYSTEM_PROMPT`, `REMEDIATION_SYSTEM_PROMPT`,
      `SUMMARY_SYSTEM_PROMPT`, `CHAT_SYSTEM_PROMPT`. Each prompt includes a note that the data
      is a static Transport Analytics sample with known anomalies so Bob contextualises answers appropriately.
- [ ] Write `README.md` with: project description, architecture overview (text), prerequisites,
      setup steps (including `seed_kpi_history.py`), running instructions, demo reset procedure,
      challenge context.
- [ ] Write `ARCHITECTURE.md` with: component list, data flow description, Bob API integration
      details, static data design rationale.
- [ ] Write `DEMO_SCRIPT.md` with: the 7-step narrative demo (see above), expected UI state at
      each step, fallback script for no-Bob-API mode (rule-based alerts + canned responses).
- [ ] Write `SUBMISSION.md` with challenge-required fields pre-filled: solution statement,
      technical statement, impact areas, before/after time estimate. Call out the static-data
      approach explicitly as a deliberate reproducibility choice.
- [ ] Write `AGENTS.md` with: agent descriptions, prompt design, safety model, static data note.
- [ ] Add docstrings to `app.py`, all `agents/*.py` files, `databricks_connection.py`.
- [ ] Create `.env.example`: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`,
      `BOB_API_URL`, `BOB_API_KEY`, `FLASK_PORT` (default 5000).

**Relevant Context**
- Challenge judging criteria: Practicality, Effectiveness, Design, Creativity.
- Submission deadline: July 22 at 10 a.m. ET.
- Required pitch file: video or PDF (≤ specified length limit) — `DEMO_SCRIPT.md` is the
  script for the pitch video.

**Status** — `[x] done`

---

## Implementation Notes

### Dependency Order
```
ST-1 (Snapshot Table) → ST-2 (History API) → ST-3 (Sparklines)
ST-4 (Business KPIs)  → ST-5 (Drill-Down)  → ST-6 (Monitor Agent)
ST-6 (Monitor Agent)  → ST-7 (Root-Cause)   → ST-8 (Remediation)
ST-5 + ST-7           → ST-9 (Chat/Summary)
All                   → ST-10 (Documentation)
```

### File Structure After All Sub-Tasks

```
Transport Analytics/
├── app.py                              # Flask API (routes: /api/kpis, /api/history,
│                                       #   /api/alerts, /api/drilldown/<id>,
│                                       #   /api/agents/summary, /api/agents/chat,
│                                       #   /api/agents/rootcause, /api/agents/remediate,
│                                       #   /api/snapshot)
├── agents/
│   ├── __init__.py
│   ├── bob_client.py                   # Bob API wrapper (retry logic)
│   ├── prompts.py                      # All Bob system prompt constants
│   ├── monitor_agent.py                # KPI alert generation agent
│   ├── rootcause_agent.py              # Root-cause analysis agent
│   ├── remediation_agent.py            # SQL fix generation + execution agent
│   ├── summary_agent.py                # Executive summary generator
│   └── chat_agent.py                   # Conversational Q&A agent
├── otm_live_dashboard.html             # Enhanced dashboard (v3 — full agentic UI)
├── otm_live_dq_dashboard.html          # Static v1 (reference snapshot, unchanged)
├── archive_snapshot.py                 # Daily KPI snapshot archival script
├── create_kpi_snapshot_table.py        # DDL for kpi_snapshots table
├── create_dq_alerts_table.py           # DDL for dq_alerts table
├── kpi_compute.py                      # Standalone CLI KPI report (unchanged)
├── databricks_connection.py            # DB manager (unchanged)
├── create_*_table.py (3 files)         # Original schema setup (unchanged)
├── insert_*_data.py (6 files)          # Original seed scripts (unchanged)
├── requirements.txt                    # + requests, python-dotenv (already there)
├── .env                                # Secrets (gitignored)
├── .env.example                        # Template for new setups
├── README.md                           # Setup + overview
├── ARCHITECTURE.md                     # System design doc
├── AGENTS.md                           # Agent design doc
├── DEMO_SCRIPT.md                      # 5-minute pitch walkthrough
├── SUBMISSION.md                       # Challenge submission text
└── plans/
    ├── Transport Analytics-improvements-plan.md        # Previous plan (all done)
    └── Transport Analytics-watsonx-challenge-plan.md   # This plan
```

### KPI Reference (Full 15-KPI Framework After ST-4)

| ID    | Name                         | Pillar        | Target  | Higher Better |
|-------|------------------------------|---------------|---------|---------------|
| JI-01 | Order-to-Shipment Match      | Join          | ≥ 98%   | Yes           |
| JI-02 | Orphan OS Rate               | Join          | ≤ 1%    | No            |
| JI-03 | Shipment Execution Match     | Join          | ≥ 98%   | Yes           |
| CP-01 | Order Release GID Nulls      | Completeness  | = 0%    | No            |
| CP-02 | Shipment GID Nulls           | Completeness  | = 0%    | No            |
| CP-05 | Actual Dates Completeness    | Completeness  | ≤ 3%    | No            |
| CS-01 | Weight Mismatch              | Consistency   | ≤ 2%    | No            |
| CS-02 | Date Sequence Violation      | Consistency   | = 0%    | No            |
| CS-07 | Ghost Mapping Rate ★         | Consistency   | = 0%    | No            |
| RI-01 | Invalid Shipment Status      | Referential   | = 0%    | No            |
| RI-05 | Zero/Neg Quantity            | Referential   | = 0%    | No            |
| TP-01 | Late Delivery Rate           | Timeliness    | = 0%    | No            |
| BIZ-01| On-Time Delivery %           | Business      | ≥ 95%   | Yes           |
| BIZ-02| Zero-Weight Order Rate       | Business      | = 0%    | No            |
| BIZ-03| Shipment Re-Assignment Rate  | Business      | ≤ 2%    | No            |

### Bob API Integration Pattern

All agents follow the same pattern via `bob_client.py`:
1. Build a `messages` array: `[{"role": "system", "content": PROMPT}, {"role": "user", "content": data_json}]`
2. POST to `BOB_API_URL` with `Authorization: Bearer {BOB_API_KEY}` header.
3. Parse the `choices[0].message.content` from the response.
4. All agents instruct Bob to return **valid JSON** so responses are machine-parseable.
5. `bob_client.py` wraps the call in a try/except: on failure, raises `BobAPIError` which
   callers handle with a rule-based fallback.

### Challenge Submission Story

**Problem**: In every Transport Analytics deployment, ghost shipments, orphan records, and date violations
accumulate silently in the data lake — corrupting OTD metrics and misleading planners.
Traditional data quality monitoring shows a dashboard but requires a DBA to investigate and fix.

**Solution**: The Transport Analytics AI-Powered DQ Platform uses IBM Bob as an intelligent copilot for data
quality operations. Bob monitors KPIs, explains root causes in plain English, drafts corrective
SQL, and waits for human approval — closing the loop from detection to remediation in one tool.

**Impact**:
- Manual DQ investigation: ~4 hours/week → ~15 minutes/week (Bob explains in seconds)
- Time-to-fix for known patterns: ~1 day → ~2 minutes (human-approved auto-remediation)
- KPI blind spots: 0 historical context → 7-day trends + sparklines for proactive monitoring
- Analyst skill requirement: Senior DBA → Any analyst with dashboard access

**Built 100% with IBM Bob**: Every agent prompt, the architecture design, and the code were
developed in collaboration with IBM Bob during the challenge window.
