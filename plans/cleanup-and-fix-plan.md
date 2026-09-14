# Transport Analytics DQ Platform — Cleanup & Fix Plan

## Overview

**Goal**: Fix all confirmed bugs, medium issues, and code-quality problems across the Transport Analytics
project in priority order, with a benchmark test after each sub-task to confirm the fix works.

**Scope**: All bugs identified in the comprehensive audit, grouped into logical, independently
deployable sub-tasks. Each sub-task is followed by a specific test command.

**Non-goals**:
- No new features
- No database schema changes beyond fixing NULL biz01/02/03 in snapshots
- No migration to a logging framework (print-based logging stays, just ensure errors print)
- No unit-test framework (manual benchmark tests only)

**Static data constraint**: Databricks data is seeded/static. All tests are REST calls or
Python script runs, not live data mutations.

**File being served**: `app.py` serves `otm_live_dashboard.html` — NOT `otm_live_dq_dashboard.html`.

---

## Sub-Task 1 — requirements.txt: Add missing `cryptography` dependency

**Intent**
`agents/bob_client.py` line 104 imports `from cryptography.hazmat.primitives.ciphers.aead import AESGCM`
for DPAPI token decryption. This package is not listed in `requirements.txt`, meaning a fresh
`pip install -r requirements.txt` will fail at runtime with ImportError when Bob token decryption
is attempted. Add it.

**Expected Outcomes**
- `requirements.txt` lists `cryptography` as a dependency
- `pip install -r requirements.txt` succeeds without errors

**Todo List**
- [ ] Add `cryptography` to `requirements.txt`

**Relevant Context**
- `requirements.txt` — currently: flask, databricks-sql-connector, python-dotenv, requests
- `agents/bob_client.py` line 104 — `from cryptography.hazmat.primitives.ciphers.aead import AESGCM`

**Benchmark Test**
```
pip install -r requirements.txt   # should complete without errors
python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print('OK')"
```

**Status** — `[ ] pending`

---

## Sub-Task 2 — bob_client.py: Guard DPAPI decrypt failures + add Direct HTTP retry

**Intent**
Two issues in `agents/bob_client.py`:

1. `_dpapi_decrypt()` (lines 67–75) calls `windll.crypt32.CryptUnprotectData` with zero error
   handling. If the DPAPI call fails (e.g., wrong user context, corrupt store), it silently
   returns garbage bytes or crashes — causing a cascade failure rather than a graceful fallback
   to Bob Shell.

2. `_call_via_http()` (lines 216–223) iterates through header options but only tries each once
   with no retry loop. A transient network error on the first attempt immediately discards the
   OAuth strategy and raises `BobAPIError`.

**Expected Outcomes**
- `_read_bob_oauth_token()` wraps the entire DPAPI + AES-GCM block in a try/except and returns `""`
  on any failure (the existing outer `except Exception` only covers the SQLite/file open, not the
  inner DPAPI/AES calls which can raise native Windows errors)
- `_call_via_http()` wraps each `requests.post()` call with `MAX_RETRIES` (currently 3) and
  exponential backoff — same pattern as Bob Shell strategy
- `_build_http_headers()` returns an empty dict when neither token nor key is available — this
  is already the case; add a comment noting the empty-dict means "skip this option"
- No change to public API (`call_bob`, `BobAPIError`, `parse_json_response`)

**Todo List**
- [ ] In `_dpapi_decrypt()`, wrap the `windll` call in try/except, return empty bytes on failure
- [ ] In `_read_bob_oauth_token()`, wrap the `AESGCM(...).decrypt(...)` and `json.loads` calls
  in their own inner try/except so decrypt failure returns `""` not an exception
- [ ] In `_call_via_http()`, replace the single `requests.post()` attempt per header with a
  retry loop using `MAX_RETRIES` and `RETRY_DELAY_S * attempt` sleep

**Relevant Context**
- `agents/bob_client.py` lines 62–111 (DPAPI + OAuth token reading)
- `agents/bob_client.py` lines 189–224 (Direct HTTP strategy)
- `MAX_RETRIES = 3`, `RETRY_DELAY_S = 2` — already defined at module level

**Benchmark Test**
```
python -c "from agents.bob_client import _read_bob_oauth_token; tok = _read_bob_oauth_token(); print('Token len:', len(tok))"
python test_bob.py
```

**Status** — `[ ] pending`

---

## Sub-Task 3 — app.py: Fix ri05_shp index bug in /api/snapshot

**Intent**
In `/api/snapshot` (lines 590–605), the CTE SELECT returns 17 columns:
`total_orders[0], total_os[1], total_shp[2], ji01[3], ji02[4], ji03[5], cp01[6], cp02[7],
cp05_denom[8], cp05_num[9], cs07[10], cs01[11], cs02[12], ri01[13], ri05_ord[14], ri05_shp[15], tp01[16]`

Line 605 is: `ri01 = r[13]; ri05 = r[14]; tp01 = r[16]`

`r[15]` (ri05_shp) is never read into a variable. On line 611, the referential integrity
pillar formula uses `ri05` (which correctly = ri05_ord at r[14]), so the pillar score itself
is correct. However the snapshot's `ri05` KPI value is being set to `ri05_ord` (order-level)
rather than the combined value used in `/api/kpis`. This is a data accuracy issue —
the snapshot will not match the live KPI panel's RI05 value.

Additionally, `r[16]` for `tp01` skips index 15 without assigning `ri05_shp` — the index
access works correctly, but it is fragile and confusing. Fix by reading all columns explicitly.

**Expected Outcomes**
- `ri05_shp = r[15]` is read and the snapshot pillar formula matches `/api/kpis`
- `tp01 = r[16]` confirmed correct
- Snapshot RI05 value equals `/api/kpis` RI05 value after re-running

**Todo List**
- [ ] On line 605, change to:
  `ri01 = r[13]; ri05_ord = r[14]; ri05_shp = r[15]; tp01 = r[16]`
- [ ] On line 611, confirm referential pillar uses `ri05_ord` (orders) consistent with
  `/api/kpis` which uses `ri05_ord` for RI05 KPI value — no change needed to pillar formula

**Relevant Context**
- `app.py` lines 586–605 (snapshot CTE and index assignments)
- `/api/kpis` uses `ri05_ord` for RI05 value (line 343) — snapshot must match

**Benchmark Test**
```
# After fix:
POST http://localhost:5000/api/snapshot  → check response overall_score matches GET /api/kpis overall_score
curl -s http://localhost:5000/api/kpis | python -c "import sys,json; d=json.load(sys.stdin); print('RI05:', d['kpis']['RI05']['value'])"
curl -s -X POST http://localhost:5000/api/snapshot | python -c "import sys,json; d=json.load(sys.stdin); print('snapshot overall:', d['overall_score'])"
```

**Status** — `[ ] pending`

---

## Sub-Task 4 — app.py: Fix biz01/02/03 NULLs in /api/snapshot INSERT

**Intent**
`/api/snapshot` (line 644) inserts `NULL, NULL, NULL` for `biz01`, `biz02`, `biz03` columns.
The Business Performance KPIs are computed in `/api/kpis` (lines 280–287) but the snapshot
CTE does not include biz01/02/03. This means post-fix snapshot rows have no business KPI
values, breaking sparkline charts for BIZ01/BIZ02/BIZ03.

The fix is to extend the snapshot CTE to include the same biz01/02/03 sub-queries that `/api/kpis`
already has, capture those values, and substitute them for the NULLs.

**Expected Outcomes**
- `POST /api/snapshot` response includes non-null `biz01`, `biz02`, `biz03` values
- Sparkline charts for BIZ01, BIZ02, BIZ03 include "Post-fix" data point
- Snapshot CTE SELECT matches the same business KPI logic as `/api/kpis`

**Todo List**
- [ ] In the `/api/snapshot` CTE, add the same three business KPI sub-queries:
  - `biz01_num` = `COUNT(CASE WHEN s.actual_arrival <= s.planned_delivery AND s.actual_arrival IS NOT NULL AND s.status = 'Closed' THEN 1 END)` from SHIPMENT
  - `biz01_den` = `COUNT(CASE WHEN s.status = 'Closed' THEN 1 END)` from SHIPMENT
  - `biz02_num` = same as `ri05_ord` (zero-weight orders) — already available as `r[14]`
  - `biz03_num` = `COUNT(CASE WHEN os.dq_flag = 'Re-assigned' THEN 1 END)` from ORDER_SHIPMENT
- [ ] Read the new columns from the result row
- [ ] Replace `NULL, NULL, NULL` with computed `biz01_pct`, `biz02_pct`, `biz03_pct` values
- [ ] Add `biz_score` pillar computation (average of 3 biz KPI scores) to snapshot response

**Relevant Context**
- `app.py` lines 130–175 — `/api/kpis` biz01/02/03 CTE sub-queries to replicate
- `app.py` lines 630–654 — snapshot INSERT target
- `workspace.otm.SHIPMENT` — `actual_arrival`, `planned_delivery`, `status`
- `workspace.otm.ORDER_SHIPMENT` — `dq_flag`

**Benchmark Test**
```
curl -s -X POST http://localhost:5000/api/snapshot | python -c "import sys,json; d=json.load(sys.stdin); print('biz01:', d.get('biz01'), 'biz02:', d.get('biz02'), 'biz03:', d.get('biz03'))"
# Should print non-null float values, not None
```

**Status** — `[ ] pending`

---

## Sub-Task 5 — remediation_agent.py: Fix SQL safety guard regex

**Intent**
The `BLOCKED_PATTERNS` list in `agents/remediation_agent.py` (lines 32–37) has two issues:

1. Pattern `r"\bDELETE\s+FROM\s+\w+\s*$"` uses `$` to match end-of-string. In Python `re`,
   `$` matches end-of-string OR before a trailing newline — but does NOT match mid-string in
   a multi-statement SQL like `DELETE FROM table;\nUPDATE table SET x=1`. The secondary check
   on line 47 (`"DELETE" in upper and "WHERE" not in upper`) provides a backstop for this, but
   the pattern itself is misleading.

2. `\w+` in the pattern only matches a single-word identifier. Databricks tables use dotted
   names like `workspace.otm.order_shipment`. The regex will not match those, so `DELETE FROM
   workspace.otm.order_shipment` would bypass pattern 35 (though the backstop on line 47 still
   catches it via the `WHERE` check).

The existing line-47 backstop (`DELETE … WHERE` check) is correct and comprehensive. The
patterns themselves should be simplified and the `re.MULTILINE` flag should be passed to
ensure `$` works as expected.

**Expected Outcomes**
- `DELETE FROM workspace.otm.table_name;` (no WHERE) is blocked
- `DELETE FROM workspace.otm.table WHERE 1=1` is allowed (has WHERE clause)
- `DROP TABLE workspace.otm.orders` is blocked
- `UPDATE workspace.otm.order_shipment SET dq_flag='ORPHAN' WHERE os_id IN ('X')` is allowed
- Multiline SQL does not bypass checks

**Todo List**
- [ ] Replace the two DELETE patterns with a single `r"\bDELETE\b"` that flags any DELETE
  for secondary validation by the WHERE check (simpler and safer)
- [ ] Pass `re.IGNORECASE | re.MULTILINE` to all `re.search()` calls in `_is_safe_sql()`
- [ ] Add a pattern to block `\bALTER\b` (ALTER TABLE could corrupt schema)
- [ ] Keep the existing `"DELETE" in upper and "WHERE" not in upper` backstop — it is correct
- [ ] Add a check: if SQL contains multiple `;`-separated statements, reject it ("one statement only")

**Relevant Context**
- `agents/remediation_agent.py` lines 31–49
- The table name format in Databricks is `workspace.otm.<tablename>` — three-part dotted name

**Benchmark Test**
```python
# After fix, run these assertions:
python -c "
from agents.remediation_agent import _is_safe_sql
# Should be blocked
assert not _is_safe_sql('DROP TABLE workspace.otm.orders')[0], 'DROP should be blocked'
assert not _is_safe_sql('DELETE FROM workspace.otm.order_shipment')[0], 'DELETE without WHERE should be blocked'
assert not _is_safe_sql('TRUNCATE TABLE workspace.otm.orders')[0], 'TRUNCATE should be blocked'
assert not _is_safe_sql('ALTER TABLE workspace.otm.orders ADD COLUMN x INT')[0], 'ALTER should be blocked'
assert not _is_safe_sql('UPDATE t SET x=1; DROP TABLE t')[0], 'Multi-statement should be blocked'
# Should be allowed
assert _is_safe_sql('UPDATE workspace.otm.order_shipment SET dq_flag=\\'ORPHAN\\' WHERE os_id IN (\\'X\\')')[0], 'Safe UPDATE should be allowed'
assert _is_safe_sql('DELETE FROM workspace.otm.order_shipment WHERE os_id IN (\\'X\\')')[0], 'DELETE with WHERE should be allowed'
print('All safety guard assertions passed')
"
```

**Status** — `[ ] pending`

---

## Sub-Task 6 — monitor_agent.py: Fix AMBER fallback logic

**Intent**
`_build_fallback_alerts()` in `agents/monitor_agent.py` line 138 hardcodes `is_amber = False`
for all lower-is-better KPIs. This means the fallback mode never generates AMBER alerts —
only RED. In live data, AMBER KPIs (JI-01, BIZ-03) are present but the fallback ignores them.

Also, the RAG thresholds for lower-is-better AMBER should be consistent with the dashboard:
a KPI is AMBER if it exceeds its target but by less than 2× the target value (i.e., it's
"close to RED"). For example, BIZ-03 target is ≤ 2%; value of 2.5% is AMBER, value of 5%
is RED.

**Expected Outcomes**
- Fallback mode generates AMBER alerts for KPIs that exceed target by < 2× (e.g., 2.5% vs 2% target)
- Fallback mode generates RED alerts for KPIs that exceed target by ≥ 2× (e.g., 5% vs 2% target)
- Higher-is-better AMBER logic unchanged: AMBER if below target but within 5%
- All existing unit-level assertions still pass

**Todo List**
- [ ] For lower-is-better KPIs in `_build_fallback_alerts()`, define:
  - `is_red = value > target * 2 and value > 0` (or `value > target` if target is 0)
  - `is_amber = not is_red and value > target`
  - Special case: if `target == 0`, any `value > 0` is RED (not AMBER) — there is no AMBER band for zero-target KPIs
- [ ] Update the `sev` assignment when using FALLBACK_MESSAGES to honour `is_red`/`is_amber`
  rather than using the hardcoded severity from the dict — the dict severity may disagree
  with the live threshold

**Relevant Context**
- `agents/monitor_agent.py` lines 125–148
- Dashboard RAG thresholds (in `otm_live_dashboard.html` `ragFromKpi()` function) — the
  fallback should match these thresholds exactly

**Benchmark Test**
```
# Start server, run Monitor Agent, check alerts response includes AMBER entries
curl -s http://localhost:5000/api/alerts | python -c "import sys,json; d=json.load(sys.stdin); ambers=[a for a in d['alerts'] if a['severity']=='AMBER']; print('AMBER alerts:', len(ambers), [a['kpi_id'] for a in ambers])"
```

**Status** — `[ ] pending`

---

## Sub-Task 7 — summary_agent.py: Fix RED KPI detection for higher-is-better KPIs

**Intent**
`_fallback_summary()` in `agents/summary_agent.py` line 24–27 only looks for RED KPIs where
`higher_is_better=False`. This means failing KPIs like JI-01 (target ≥ 98%), JI-03 (target ≥ 98%),
and BIZ-01 (target ≥ 95%) are completely ignored by the fallback summary, even if they are the
worst-performing KPIs.

Also, the "best GREEN KPI" logic (lines 31–33) also only looks at `higher_is_better=False`
KPIs that are exactly 0% — this misses green higher-is-better KPIs at their target.

**Expected Outcomes**
- Fallback summary correctly identifies the worst failing KPI regardless of direction
- "Worst RED" uses a direction-aware comparison: for lower-is-better, worst = highest value above target; for higher-is-better, worst = furthest below target
- "Best GREEN" includes both directions

**Todo List**
- [ ] Rewrite `red_kpis` list comprehension to cover both directions:
  - Include `higher_is_better=False` KPIs where `value > target_val`
  - Include `higher_is_better=True` KPIs where `value < target_val * 0.95`
- [ ] Rewrite `worst` ranking to use a normalised deviation score so both directions are comparable
- [ ] Rewrite `green_kpis` list comprehension to cover both directions

**Relevant Context**
- `agents/summary_agent.py` lines 18–50
- KPI direction reference: JI01, JI03, BIZ01 are `higher_is_better=True`

**Benchmark Test**
```
# Manually test fallback by mocking a scenario where JI01 is the worst KPI
python -c "
from agents.summary_agent import _fallback_summary
mock = {'overall_score': 70, 'kpis': {'JI01': {'value': 80, 'target_val': 98, 'higher_is_better': True, 'target': '>= 98%'}, 'CS07': {'value': 0, 'target_val': 0, 'higher_is_better': False, 'target': '= 0%'}}}
s = _fallback_summary(mock)
print('Summary:', s)
assert 'JI01' in s, 'JI01 (higher-is-better RED) should appear in summary'
print('PASS')
"
```

**Status** — `[ ] pending`

---

## Sub-Task 8 — otm_live_dashboard.html: Wire missing drill-down cards + fix drag hint

**Intent**
Four KPIs have `DRILLDOWN_QUERIES` defined in `app.py` but are missing from the `drilldownKpis`
array in the dashboard (line 578). Adding them makes those cards clickable when RED:
- CP01 (Order GID Null Rate)
- CP02 (Shipment GID Null Rate)
- CP05 (Actual Dates Completeness)
- CS01 (Weight Mismatch Rate)

Additionally:
- The drill-down modal subtitle (line 979) says "Drag header to move" but there is no drag
  handler implemented in JavaScript — this is misleading UI text, remove it.
- The `PLAIN_ENGLISH` dict (confirmed present at line 955) is missing entries for CP01, CP02,
  CP05, CS01 — add plain-English descriptions for these four KPIs so the modal shows context.

**Expected Outcomes**
- CP01, CP02, CP05, CS01 cards are clickable when RED/AMBER, opening the drill-down modal
- The modal shows a plain-English description for each of the four new KPIs
- Modal subtitle no longer says "Drag header to move"
- The four KPIs' drill-down data loads correctly from the existing `/api/drilldown/<kpi_id>`
  endpoint (queries already exist in `app.py` `DRILLDOWN_QUERIES`)

**Todo List**
- [ ] In `otm_live_dashboard.html` line 578, add `'CP01','CP02','CP05','CS01'` to the
  `drilldownKpis` array
- [ ] Add four entries to the `PLAIN_ENGLISH` dict (line 955 area) for CP01, CP02, CP05, CS01
- [ ] Remove the "Drag header to move" text from the modal subtitle (line 979)

**Relevant Context**
- `otm_live_dashboard.html` line 578 — `drilldownKpis` array
- `otm_live_dashboard.html` lines 955–966 — `PLAIN_ENGLISH` dict
- `otm_live_dashboard.html` line 979 — modal subtitle
- `app.py` lines 363–455 — `DRILLDOWN_QUERIES` dict (CP01, CP02, CP05, CS01 already present)

**Benchmark Test**
```
# After fix, manually open dashboard and click a RED CP01/CP02/CP05/CS01 card
# Or: verify the drilldownKpis list includes the new IDs
grep -o "drilldownKpis.*;" otm_live_dashboard.html  # should show the 4 new IDs
```

**Status** — `[ ] pending`

---

## Sub-Task 9 — app.py: Read Flask port from env var + minor hardcoded fixes

**Intent**
`app.py` line 857 hardcodes `port=5000`. The `.env.example` defines `FLASK_PORT=5000` but the
app never reads it. Also `debug=False` is hardcoded — should be `FLASK_DEBUG` env var.

**Expected Outcomes**
- `app.run(port=int(os.getenv("FLASK_PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")`
- No behaviour change when `.env` is not set (defaults to port 5000, debug off)

**Todo List**
- [ ] Replace line 857 with env-var-driven port and debug settings

**Relevant Context**
- `app.py` line 857
- `.env.example` — `FLASK_PORT=5000` already documented

**Benchmark Test**
```
python -c "import subprocess, os; os.environ['FLASK_PORT']='5001'; print('Port reading test — manual verify')"
# Then: FLASK_PORT=5001 python app.py  → should bind to 5001
```

**Status** — `[ ] pending`

---

## Sub-Task 10 — seed_kpi_history.py: Prevent duplicate rows on re-run

**Intent**
Re-running `python seed_kpi_history.py` inserts duplicate snapshot rows with the same
`captured_at` timestamps and labels. This breaks sparkline charts (duplicate X-axis labels)
and inflates the history table with redundant rows.

Fix: before inserting, check if rows already exist for the seeded date range. If they do,
skip insertion (idempotent). Add a `--force` flag to override.

**Expected Outcomes**
- Running `seed_kpi_history.py` twice produces exactly 8 rows (not 16)
- A `--force` flag deletes existing seeded rows before re-inserting (for demo reset)
- Script prints how many rows were skipped vs inserted

**Todo List**
- [ ] Before each INSERT, check if a row with the same `captured_at` exists; skip if found
- [ ] Add `--force` CLI argument: if passed, DELETE all rows with `label LIKE 'Jun%' OR label LIKE 'Jul%'`
  before inserting (preserves "Post-fix" rows)
- [ ] Print summary: "N rows inserted, M rows skipped (already exist)"

**Relevant Context**
- `seed_kpi_history.py` — INSERT block (line ~154–170)
- `workspace.otm.kpi_snapshots` — no UNIQUE constraint on `captured_at` (Databricks Delta doesn't enforce)

**Benchmark Test**
```
python seed_kpi_history.py    # first run: 8 inserted, 0 skipped
python seed_kpi_history.py    # second run: 0 inserted, 8 skipped
python seed_kpi_history.py --force  # 8 inserted after delete
```

**Status** — `[ ] pending`

---

## Sub-Task 11 — Cleanup: Remove orphaned files + add print-based error logging

**Intent**
- `otm_live_dq_dashboard.html` is an orphaned file (the active dashboard is `otm_live_dashboard.html`).
  It should be deleted to avoid confusion.
- The challenge submission HTML (`Transport Analytics-ai-powered-data-quality-platform-ibm-watsonx-challenge-2026.html`)
  should be moved to `plans/` where other submission artefacts live.
- All Flask routes that catch `Exception` silently print nothing. Add `print(f"[ERROR] {e}", flush=True)`
  before each `return jsonify({"error": str(e)}), 500` so errors are visible in the console.

**Expected Outcomes**
- `otm_live_dq_dashboard.html` is deleted
- Challenge HTML moved to `plans/`
- Every `except Exception as e: return jsonify({"error": str(e)}), 500` block has a preceding
  `print(f"[ERROR /route] {e}")` line
- No functional change — just visibility improvement

**Todo List**
- [ ] Delete `otm_live_dq_dashboard.html`
- [ ] Move `Transport Analytics-ai-powered-data-quality-platform-ibm-watsonx-challenge-2026.html` to `plans/`
- [ ] In `app.py`, add `print(f"[ERROR] ...")` before each `return jsonify({"error": str(e)}), 500`
  in routes: `/api/kpis`, `/api/drilldown`, `/api/history`, `/api/snapshot`, `/api/alerts`,
  and all 5 agent routes

**Relevant Context**
- `app.py` — every route has `except Exception as e: return jsonify({"error": str(e)}), 500`
- Orphaned file: `otm_live_dq_dashboard.html`
- Pitch file: `Transport Analytics-ai-powered-data-quality-platform-ibm-watsonx-challenge-2026.html`

**Benchmark Test**
```
# Verify orphaned file is gone
python -c "import os; assert not os.path.exists('otm_live_dq_dashboard.html'), 'Should be deleted'; print('Cleanup OK')"
# Trigger a route error and confirm it prints to console
curl -s http://localhost:5000/api/drilldown/INVALID_KPI   # check console for [ERROR] print
```

**Status** — `[ ] pending`

---

## Benchmark Summary (Run After All Sub-Tasks)

```bash
# Full end-to-end health check
python test_bob.py                    # Bob API live
python -m py_compile app.py           # no syntax errors
python -m py_compile agents/bob_client.py
python -m py_compile agents/monitor_agent.py
python -m py_compile agents/rootcause_agent.py
python -m py_compile agents/remediation_agent.py
python -m py_compile agents/summary_agent.py
python -m py_compile agents/chat_agent.py
# Start server and run the full REST test from the session summary script
python app.py &
sleep 5
curl http://localhost:5000/api/kpis
curl http://localhost:5000/api/history
curl http://localhost:5000/api/alerts
curl -X POST http://localhost:5000/api/snapshot
curl -X POST http://localhost:5000/api/agents/monitor -H 'Content-Type: application/json' -d '{}'
```
