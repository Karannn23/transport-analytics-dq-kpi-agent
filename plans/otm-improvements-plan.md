# Transport Analytics Live Dashboard — Improvements Plan
<!-- ALL SUB-TASKS COMPLETE -->

## Overview

Fix all 15 identified issues across the Flask backend (`app.py`) and live dashboard (`otm_live_dashboard.html`).
Work is split into 6 focused sub-tasks ordered by dependency: backend fixes first, then frontend fixes, then additive features.

---

## Sub-Task 1 — Backend: Dead code, threading, requirements.txt

**Intent**
Remove the unused `ri05_shp` variable, move `kpi_score` to module level, enable Flask threading, and add `requirements.txt`.

**Expected Outcomes**
- `ri05_shp` query removed from `app.py`
- `kpi_score()` defined at module level (not re-created per request)
- Flask starts with `threaded=True`
- `requirements.txt` exists with all 3 dependencies

**Todo List**
- [ ] Delete the `ri05_shp` query line in `app.py`
- [ ] Move `kpi_score()` function above the `@app.route` decorator (module level)
- [ ] Change `app.run(debug=False, port=5000)` to `app.run(debug=False, port=5000, threaded=True)`
- [ ] Create `requirements.txt` with `flask`, `databricks-sql-connector`, `python-dotenv`

**Relevant Context**
- `app.py:120` — `ri05_shp` computed but never used in response
- `app.py:167` — `kpi_score` defined inside request handler on every call
- `app.py:247` — `app.run()` missing `threaded=True`

**Status** — `[ ] pending`

---

## Sub-Task 2 — Backend: Connection pooling

**Intent**
Replace the per-request `get_connection()` pattern with a persistent module-level connection that is reused across requests, cutting 3-5 seconds of connection overhead per refresh.

**Expected Outcomes**
- Single Databricks connection established at startup
- Reused on every `/api/kpis` call
- On connection error during a request, attempts one reconnect before returning 500

**Todo List**
- [ ] Create a module-level `_conn` and `_cursor` variable (initially `None`)
- [ ] Write a `get_cursor()` helper that returns the live cursor, reconnecting if the connection is closed/None
- [ ] Replace `conn = get_connection(); cursor = conn.cursor()` in the route with `cursor = get_cursor()`
- [ ] Remove the `cursor.close(); conn.close()` calls from inside the route (connection stays open)
- [ ] Add graceful reconnect: catch `OperationalError` or similar, reset `_conn = None`, retry once

**Relevant Context**
- `app.py:24-29` — `get_connection()` opens fresh TCP on every call
- `app.py:44-45` — connection created at start of every request
- `app.py:194-195` — connection closed at end of every request

**Status** — `[x] done`

---

## Sub-Task 3 — Backend: Batch queries into CTEs + real Timeliness KPI

**Intent**
Replace 18 sequential single-value queries with 3 batched CTE queries. Also add a real Timeliness KPI (TP-01: late delivery rate — shipments where `actual_arrival > planned_delivery`).

**Expected Outcomes**
- All KPI numerators/denominators computed in 3 SQL calls (row counts, KPI metrics, breakdowns)
- `timeliness_score` computed from live data instead of hardcoded 100
- New KPI `TP01` added to the response payload
- Overall score includes TP-01

**Todo List**
- [ ] Write CTE query #1: all row counts (orders, OS, shipments) in one SELECT
- [ ] Write CTE query #2: all KPI numerators in one multi-column SELECT using conditional aggregation (`COUNT(CASE WHEN ... THEN 1 END)`)
- [ ] Write CTE query #3: all 4 breakdown GROUP BYs (already separate, keep as-is — these cannot be batched into a single result set)
- [ ] Add TP-01 timeliness KPI: `COUNT(*) WHERE actual_arrival > planned_delivery AND actual_arrival IS NOT NULL` / total non-cancelled shipments
- [ ] Add `TP01` to the `kpis` dict in the JSON response with `target: "= 0%"`, `target_val: 0`, `higher_is_better: False`
- [ ] Replace `timeliness_score = 100` with computed value: `100 - pct(tp01, cp05_denom)`
- [ ] Add `kpi_score(pct(tp01, cp05_denom), 0, False)` to `kpi_scores` list
- [ ] Add TP-01 card to the frontend timeliness KPI grid (new section or appended to an existing grid)

**Relevant Context**
- `app.py:52-120` — 18 individual queries that can be collapsed
- `app.py:162` — `timeliness_score = 100` hardcoded
- Database columns available: `planned_delivery`, `actual_arrival` on `workspace.otm.shipment`

**Status** — `[x] done`

---

## Sub-Task 4 — Backend: Entity health cross-validation

**Intent**
Entity health scores currently trust the `dq_flag` column which was set at insert time and may be stale. Cross-validate using the live KPI data already computed in the same request.

**Expected Outcomes**
- ORDER score derived from live KPI results (zero-weight orders + no-OS-match orders)
- ORDER_SHIPMENT score derived from orphan rate + ghost mapping rate
- SHIPMENT score derived from invalid status + date violations + zero weight
- `dq_flag`-based queries removed (3 fewer DB calls)

**Todo List**
- [ ] Remove the 3 `dq_flag != 'OK'` queries (`order_bad`, `os_bad`, `shp_bad`)
- [ ] Compute `order_score` from live KPI values: `100 - pct(ri05_ord + cs07 + (total_orders - ji01), total_orders)` — orders with zero weight, ghost mapping, or no shipment match
- [ ] Compute `os_score` from live KPI values: `100 - pct(ji02 + cs07_os, total_os)` where `cs07_os` is the count of stale OS rows (already available from cs07 query)
- [ ] Compute `shp_score` from live KPI values: `100 - pct(ri01 + cs02 + ri05_shp_count, total_shp)`
- [ ] Re-add `ri05_shp` query (was removed in Sub-Task 1) since it is now used for `shp_score`

**Relevant Context**
- `app.py:128-146` — current `dq_flag`-based entity scoring
- Cross-validation uses variables already computed earlier in the same request: `ji01`, `ji02`, `cs07`, `ri01`, `cs02`, `ri05_ord`

**Status** — `[x] done`

---

## Sub-Task 5 — Frontend: Fix KPI value colour + filter pills + progress bar initial state

**Intent**
Fix three UI bugs: (1) KPI value text colour is inverted for lower-is-better KPIs showing green for bad values, (2) entity filter pills do nothing when clicked, (3) auto-refresh progress bar starts full before first data load.

**Expected Outcomes**
- KPI card value text colour matches the RAG status (red value text = red KPI, green = green)
- Clicking ORDER/ORDER_SHIPMENT/SHIPMENT filter pill shows only that entity's KPI sections
- Progress bar starts at 0% width on page load and only fills in after first `startCountdown()` call

**Todo List**
- [ ] Fix `kpiCard()` colour logic: replace `scoreColorClass(kpi.higher_is_better ? kpi.value : 100 - kpi.value)` with a direct RAG-to-colour mapping using the `r` variable already computed
- [ ] Add `onclick` handlers to the 4 filter pills (All, ORDER, ORDER_SHIPMENT, SHIPMENT)
- [ ] Add JS `filterEntity(entity)` function that shows/hides the Join Integrity, Completeness, Consistency, Referential section-labels and KPI grids based on which entity is selected
- [ ] Change `auto-refresh-progress` initial `style="width:100%"` to `style="width:0%"` so it starts empty before first load

**Relevant Context**
- `otm_live_dashboard.html:388` — `kpiCard()` function, incorrect colour logic
- `otm_live_dashboard.html:177-180` — filter pills with no onclick
- `otm_live_dashboard.html:154` — progress bar initial state `width:100%`
- KPI section IDs: `kpi-join`, `kpi-comp`, `kpi-cons`, `kpi-ref`, plus `sec-label` divs

**Status** — `[x] done`

---

## Sub-Task 6 — Frontend: Delta arrows + ORDER DQ flag distribution tab

**Intent**
(1) Store the previous API response in `localStorage` and show ↑/↓/= delta arrows on each KPI card value when the data changes between refreshes. (2) Add a tab toggle to the DQ Flag Distribution section to switch between ORDER, ORDER_SHIPMENT, and SHIPMENT views.

**Expected Outcomes**
- After the second+ refresh, each KPI card shows a small arrow: `↑ +1.2%` (green), `↓ -0.5%` (red), `=` (grey)
- DQ Flag Distribution section has 3 tab buttons: ORDER / ORDER_SHIPMENT / SHIPMENT
- Clicking a tab swaps the bar chart to that entity's `dq_flag` breakdown
- ORDER dq_flag data already in API response (`breakdowns.os_dq_flags`) — ORDER dq_flags need to be added to the backend response

**Todo List**
- [ ] Add `order_dq_flags` query to `app.py`: `SELECT dq_flag, COUNT(*) FROM workspace.otm.order GROUP BY dq_flag ORDER BY 2 DESC`
- [ ] Add `order_dq` key to `breakdowns` in the JSON response
- [ ] In the frontend `render()`, after rendering, call `localStorage.setItem('otm_prev_kpis', JSON.stringify(kpis))`
- [ ] At start of `render()`, read `prev = JSON.parse(localStorage.getItem('otm_prev_kpis') || 'null')`
- [ ] In `kpiCard()`, accept an optional `prevValue` and render a `<span class="delta">` showing `↑`/`↓`/`=` with the difference
- [ ] Add 3 tab buttons above the DQ bar chart section (ORDER / ORDER_SHIPMENT / SHIPMENT)
- [ ] Add `showDqTab(entity)` JS function that re-renders `dq-bar-rows` with the selected entity's data
- [ ] Store all 3 breakdown datasets on the `window` after first render so tab switching doesn't need a re-fetch

**Relevant Context**
- `app.py:231-234` — `breakdowns` dict; `order_dq` missing
- `otm_live_dashboard.html:414` — `dqBarRows()` function that renders the bars
- `otm_live_dashboard.html:329-333` — DQ Flag Distribution section HTML
- `otm_live_dashboard.html:488-540` — KPI summary table rendering (pattern for delta display)

**Status** — `[x] done`

---

## Implementation Notes

- Sub-Tasks 1, 2, 3, 4 are all backend (`app.py`) — implement in order as each builds on the previous
- Sub-Task 3 depends on Sub-Task 2 (must have stable cursor before batching)
- Sub-Task 4 depends on Sub-Task 3 (re-uses KPI variables computed by the batched queries)
- Sub-Tasks 5 and 6 are frontend-only and can be done after or in parallel with backend
- After each sub-task, kill and restart the Flask server to validate the fix
- Sub-Task 4 note: `ri05_shp` is removed in Sub-Task 1 and re-added in Sub-Task 4 — keep this in mind
