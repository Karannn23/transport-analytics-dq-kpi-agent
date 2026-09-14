# Transport Analytics Dashboard — Comprehensive Feature Test Plan

## Overview

End-to-end test of every user-facing feature and backend interaction in the Transport Analytics AI-Powered Data Quality Platform. Tests are ordered so each builds on a clean, known state. The plan covers: entity filtering, AI summary, score/pillar display, sparklines, KPI cards and drill-downs, DQ flag distribution, Monitor Agent, root-cause analysis, fix generation, fix execution (KPI improvement verification), sparkline post-fix point, chat agent, and full reset + re-verify.

**Prerequisite before starting:** Run `python reset_demo.py` and `python app.py`, then open `http://localhost:5000`.

---

## Sub-Task 1 — Filter Bar & Entity Tabs

**Intent:** Verify entity tabs correctly show/hide sections and the active pill highlights.

**Expected Outcomes:**
- "All" pill starts dark/active on load
- Clicking each entity tab hides irrelevant KPI sections and shows relevant ones
- Clicking "All" restores all sections
- Pill cursor shows pointer on hover

**Todo List:**
1. On page load — confirm "All" pill has `active` class (dark background)
2. Click "ORDER" tab:
   - Join Integrity section → visible (data-entity includes "order")
   - Completeness section → visible (data-entity includes "order")
   - Consistency section → visible (data-entity includes "order")
   - Timeliness section → hidden (data-entity="shipment" only)
   - Business Performance section → hidden (data-entity="all" only)
   - DQ Flag Distribution → visible (data-entity="all order os shipment")
   - AI Alerts → visible (data-entity="all order os shipment")
3. Click "ORDER_SHIPMENT" tab:
   - Join Integrity → visible
   - Completeness → hidden (data-entity="order shipment" — no "os")
   - Consistency → visible
   - Timeliness → hidden
   - Business Performance → hidden
4. Click "SHIPMENT" tab:
   - Join Integrity → visible
   - Completeness → visible
   - Timeliness → visible
   - Business Performance → hidden
5. Click "All" — all sections restore

**Relevant Context:** `filterEntity()` in otm_live_dashboard.html:868, data-entity attributes on section divs lines 341-403, `.filter-pill.active` CSS at line 32.

**Status:** [ ] pending

---

## Sub-Task 2 — AI Executive Summary

**Intent:** Verify the summary panel populates on load and regenerates on demand via Bob.

**Expected Outcomes:**
- Summary text appears within 5s of page load (or immediately if cached)
- Clicking Regenerate triggers a fresh Bob call and replaces the text
- Summary contains: overall score number, a RED KPI name, a positive finding, and a recommendation

**Todo List:**
1. On page load — confirm `#ai-summary-text` is not empty and not showing skeleton
2. Confirm summary mentions "85%" overall score
3. Confirm summary mentions at least one RED KPI (CS-07, RI-05, BIZ-02, BIZ-03, or RI-01)
4. Click "Regenerate" — button disables and shows "Generating…"
5. Wait for response — confirm new text appears (different from previous)
6. If Bob unavailable — confirm fallback text still appears (rule-based summary, not blank)

**Relevant Context:** `regenerateSummary()` at line 1213, `POST /api/agents/summary` at app.py:877, `_fallback_summary()` in summary_agent.py:18.

**Status:** [ ] pending

---

## Sub-Task 3 — Overall Score + Pillar Cards

**Intent:** Verify all 6 pillar scores and overall score display correct values matching the known data state.

**Expected Outcomes:**
- Overall: 85% (amber coloured)
- Join Integrity: 97% (green)
- Completeness: 100% (green)
- Consistency: 99% (green)
- Timeliness: 100% (green)
- Referential: 97% (green)
- Business: 66% (red)
- Progress bars filled proportionally

**Todo List:**
1. Confirm `#overall-score` shows 85 with amber colour (`#f59e0b` or similar)
2. Confirm each pillar card shows the expected value
3. Hover the "ⓘ how scored?" tooltip — confirm tooltip appears explaining scoring method
4. Confirm `#computed-at` shows a recent UTC timestamp

**Relevant Context:** `GET /api/kpis` at app.py:98, pillar score formulas at app.py:264-287, `kpi_score()` function at app.py:79.

**Status:** [ ] pending

---

## Sub-Task 4 — Data Quality Trend (Sparklines + History Table)

**Intent:** Verify 6 sparklines render and the history table shows all 8 pre-seeded snapshots.

**Expected Outcomes:**
- 6 spark-cards render: Overall Score, Join Integrity, Completeness, Consistency, Timeliness, Referential
- Each sparkline shows a downward trend from Jun 14 (93%) to Jul 20 (85%)
- History table shows exactly 8 rows (Jun 14 → Jul 20)
- "Jul 20 — Today (live) ★" row is bold/highlighted
- Delta column shows -1.0% for most recent row

**Todo List:**
1. Confirm 6 spark-card divs are populated (not skeleton)
2. In spark-overall card: last value shows 85%, delta shows -1.0%
3. In history table: count 8 rows — first is "Jun 14 — Baseline" at 93%, last is "Jul 20 — Today (live)" at 85%
4. Confirm "Jul 20" row is visually highlighted (bold/blue background)
5. Confirm no "Post-fix" row exists at this point (clean state)

**Relevant Context:** `loadHistory()` and `renderSparkline()` in dashboard JS, `GET /api/history` at app.py:522, seeded data in seed_kpi_history.py:46-151.

**Status:** [ ] pending

---

## Sub-Task 5 — Entity Health Bars

**Intent:** Verify ORDER/ORDER_SHIPMENT/SHIPMENT entity scores display correctly.

**Expected Outcomes:**
- ORDER: 85% AMBER
- ORDER_SHIPMENT: 94.7% GREEN
- SHIPMENT: 92.8% GREEN

**Todo List:**
1. Confirm ORDER bar width ~85%, badge shows "AMBER"
2. Confirm ORDER_SHIPMENT bar width ~94.7%, badge shows "GREEN"
3. Confirm SHIPMENT bar width ~92.8%, badge shows "GREEN"

**Relevant Context:** Entity score formulas at app.py:248-261, `entity_scores` in API response.

**Status:** [ ] pending

---

## Sub-Task 6 — KPI Cards (All 15)

**Intent:** Verify all 15 KPI cards render with correct value, target, RAG status, persona badge, and change indicator.

**Expected Outcomes for each card (pre-fix state):**

| KPI   | Value  | Status | Persona Badge |
|-------|--------|--------|---------------|
| JI-01 | 94%    | AMBER  | Data Engineer |
| JI-02 | 2.7%   | RED    | Data Engineer |
| JI-03 | 100%   | GREEN  | Data Engineer |
| CP-01 | 0%     | GREEN  | Data Steward  |
| CP-02 | 0%     | GREEN  | Data Steward  |
| CP-05 | 1.1%   | GREEN  | Ops Manager   |
| CS-07 | 3%     | RED ★  | Data Engineer |
| CS-01 | 0%     | GREEN  | Data Engineer |
| CS-02 | 0.9%   | RED    | Ops Manager   |
| RI-01 | 0.9%   | RED    | Data Steward  |
| RI-05 | 6%     | RED    | Finance Analyst |
| TP-01 | 0%     | GREEN  | Logistics Planner |
| BIZ-01| 100%   | GREEN  | Supply Chain Mgr |
| BIZ-02| 6%     | RED    | Finance Analyst |
| BIZ-03| 6.2%   | RED    | Supply Chain Mgr |

**Todo List:**
1. Confirm each of the 15 cards shows the expected value and RAG status from table above
2. Confirm CS-07 card shows purple "RED ★" badge (star KPI) — not regular red
3. Confirm each card shows the correct persona badge colour and label
4. Confirm RED cards show "Click to view failing records" link
5. Confirm GREEN cards do NOT show a drill-down link
6. Change indicator: confirm all show "= no change" (first load, no prev snapshot in localStorage)

**Relevant Context:** `kpiCard()` function in dashboard JS, persona map at line 549, RAG logic at `rag()` line 503.

**Status:** [ ] pending

---

## Sub-Task 7 — KPI Drill-Down Modal

**Intent:** Verify clicking RED KPI cards opens modal with real failing records from Databricks.

**Expected Outcomes:**
- Modal opens with correct title and record count
- Records shown match the known anomalies
- Copy CSV button works
- Modal closes on ✕ or Escape

**Todo List:**
1. Click CS-07 card → modal title "CS-07 · workspace.otm", table shows 3 rows with order_release_gid values showing active_shipment_count = 2
2. Close modal → confirm it closes cleanly
3. Click JI-02 card → table shows 3 rows with os_id values OS-X01, OS-X02, OS-X03
4. Click RI-05 card → table shows 6 rows with total_weight_kg = 0
5. Click BIZ-03 card → table shows 7 rows with dq_flag = 'Re-assigned'
6. Click RI-01 card → table shows 1 row for SHP-2025-020 with status DISPATCHED
7. Click CS-02 card → table shows 1 row for SHP-2025-010 with arrival before departure
8. Click CP-01 card → confirm "No drill-down query available" (CP-01 not in DRILLDOWN_QUERIES)
9. Test Copy CSV button on any open modal — confirm text is copied to clipboard
10. Press Escape key → confirm modal closes

**Relevant Context:** `DRILLDOWN_QUERIES` at app.py:364, `drilldown()` route at app.py:496, modal JS around line 887.

**Status:** [ ] pending

---

## Sub-Task 8 — DQ Flag Distribution Bar

**Intent:** Verify the DQ flag bar chart renders and tabs switch correctly between entities.

**Expected Outcomes:**
- Default tab shows SHIPMENT view
- ORDER tab: shows flags like "Zero Weight", "Ghost Stale Delete", "Re-assigned"
- ORDER_SHIPMENT tab: shows "Ghost Stale Delete" (9), "Re-assigned" (7), "OK" (78)
- SHIPMENT tab: shows "OK" largest bar

**Todo List:**
1. On load — confirm SHIPMENT tab is active and bars render
2. Click "ORDER" tab — confirm title updates and bars show ORDER flags
3. Click "ORDER_SHIPMENT" tab — confirm "Ghost Stale Delete" count = 9, "Re-assigned" = 7
4. Click "SHIPMENT" tab — confirm returns to SHIPMENT view

**Relevant Context:** `showDqTab()` at line 685, breakdown data from `/api/kpis` breakdowns field at app.py:349.

**Status:** [ ] pending

---

## Sub-Task 9 — Monitor Agent (Alert Generation)

**Intent:** Verify the Monitor Agent generates correct persona-addressed alerts for all RED/AMBER KPIs and does NOT alert on GREEN KPIs.

**Expected Outcomes:**
- Alerts generated for: JI-01 (AMBER), JI-02 (RED), CS-07 (RED), CS-02 (RED), RI-01 (RED), RI-05 (RED), BIZ-02 (RED), BIZ-03 (RED)
- NO alert for: JI-03, CP-01, CP-02, CP-05, CS-01, TP-01, BIZ-01 (all GREEN)
- Each alert has the correct persona badge
- Running again with Open alerts already present → 0 new inserts (deduplication)

**Todo List:**
1. Confirm alerts panel is empty before running (clean reset state)
2. Click "▶ Run Monitor Agent" — confirm button shows spinner, meta text shows "Running…"
3. Wait for completion — confirm alert count badge shows 8+ open alerts
4. Verify NO BIZ-01 alert (100% on-time delivery is GREEN — previously bugged, now fixed)
5. Verify CS-07 alert shows "Data Engineer" persona badge and mentions ghost mapping
6. Verify RI-05 alert shows "Finance Analyst" persona badge and mentions zero weight
7. Verify BIZ-03 alert shows "Supply Chain Mgr" persona badge
8. Click "▶ Run Monitor Agent" again → meta shows "0 new alert(s) inserted" (deduplication working)
9. Verify KPI cards for RED KPIs pulsed blue during agent run (ai-highlight animation)

**Relevant Context:** `runMonitorAgent()` in dashboard JS, `POST /api/agents/monitor` at app.py:768, `FALLBACK_MESSAGES` in monitor_agent.py:32, updated RAG rules in MONITOR_SYSTEM_PROMPT at prompts.py:54.

**Status:** [ ] pending

---

## Sub-Task 10 — Root-Cause Analysis

**Intent:** Verify "Explain root cause" fetches actual failing records and renders a persona-appropriate analysis inline.

**Expected Outcomes:**
- Analysis appears inline in the alert card (no page navigation)
- Yellow "What this means in plain English" box renders
- Green "Recommended next step" box renders
- Correct persona addressed
- Alert status changes to "In Review" in the panel

**Todo List:**
1. On the CS-07 alert, click "Explain root cause"
   - Confirm skeleton loader appears then analysis renders
   - Confirm yellow box mentions CDC / Transport Analytics delete events / stale rows
   - Confirm green box recommends updating lake_status to STALE
   - Confirm persona banner says "Data Engineer"
   - Confirm alert status badge changes from "Open" to "In Review"
2. On the JI-02 alert, click "Explain root cause"
   - Confirm analysis mentions OS-X01, OS-X02, OS-X03
   - Confirm persona says "Data Engineer"
3. On the RI-05 alert, click "Explain root cause"
   - Confirm analysis mentions zero-weight / total_weight_kg
   - Confirm persona says "Finance Analyst"
4. On the BIZ-03 alert, click "Explain root cause"
   - Confirm analysis mentions dq_flag = 'Re-assigned' and 7 rows
   - Confirm persona says "Supply Chain Mgr"

**Relevant Context:** `explainAlert()` at line 1326, `POST /api/agents/rootcause` at app.py:788, `FALLBACK_ANALYSES` at rootcause_agent.py:30 (now includes RI05, BIZ02, BIZ03).

**Status:** [ ] pending

---

## Sub-Task 11 — Fix Generation (Draft Mode)

**Intent:** Verify "Generate fix" returns correct SQL for each KPI, shows right risk level, and executes nothing yet.

**Expected Outcomes:**
- Draft SQL shown matches the known correct fix for each KPI
- Risk level label shown (LOW/MEDIUM/HIGH)
- "Nothing has changed yet" warning shown
- Approve & Apply and Cancel buttons present
- No database change at this point

**Todo List:**
1. On CS-07 alert, click "Generate fix (AI draft)"
   - Confirm SQL contains `SET lake_status = 'STALE' WHERE otm_deleted = 'YES'`
   - Confirm risk level is LOW
   - Confirm "Nothing has changed yet" yellow box is present
   - Click "Cancel" — confirm draft panel closes, no DB change
2. On RI-05 alert, click "Generate fix (AI draft)"
   - Confirm SQL targets `workspace.otm.order` and sets `total_weight_kg = NULL`
   - Confirm SQL has WHERE clause `WHERE total_weight_kg <= 0`
3. On BIZ-03 alert, click "Generate fix (AI draft)"
   - Confirm SQL targets `workspace.otm.order_shipment` and sets `dq_flag = 'Re-assigned - Resolved'`
4. On RI-01 alert, click "Generate fix (AI draft)"
   - Confirm SQL sets `status = 'In Transit'` for SHP-2025-020
5. Verify the SQL block is inside a `<details>` collapsible section

**Relevant Context:** `generateFix()` at line 1379, `POST /api/agents/remediate` (approve=false) at app.py:837, KPI→fix mapping in REMEDIATION_SYSTEM_PROMPT at prompts.py:145.

**Status:** [ ] pending

---

## Sub-Task 12 — Fix Execution & KPI Improvement Verification

**Intent:** The core correctness test — apply each fix, verify the corresponding KPI improves, and confirm no unrelated KPIs change.

**Pre-condition:** Alerts and root-cause analyses from Sub-Tasks 9–11 are visible.

**Expected KPI changes after each fix:**

| Fix Applied | KPI Before | KPI After | Also Affects |
|-------------|-----------|-----------|--------------|
| CS-07 fix   | CS-07 = 3% RED | CS-07 = 0% GREEN | Consistency pillar ↑, Overall ↑ |
| RI-05 fix   | RI-05 = 6% RED | RI-05 = 0% GREEN | BIZ-02 also → 0% GREEN |
| BIZ-03 fix  | BIZ-03 = 6.2% RED | BIZ-03 = 0% GREEN | Business pillar ↑ |
| RI-01 fix   | RI-01 = 0.9% RED | RI-01 = 0% GREEN | Referential pillar ↑ |

**Todo List:**

**Fix 1 — CS-07 Ghost Mapping:**
1. Generate fix on CS-07, click "Approve & Apply" → confirm browser dialog, click OK
2. Confirm "Applying…" state then success message with rows_affected = 3
3. Confirm CS-07 card updates to 0% GREEN
4. Confirm CS-07 card glows green (ai-fixed animation for 6 seconds)
5. Confirm Consistency pillar score increases (was 99%, now should be 100%)
6. Confirm Overall score increases from 85%
7. Confirm CS-07 alert disappears from panel (status Resolved)
8. Confirm sparkline history table gained a new "Post-fix" row
9. Confirm Consistency sparkline has a new data point (higher than previous)

**Fix 2 — RI-05 / BIZ-02 Zero Weight:**
1. Generate fix on RI-05, click "Approve & Apply"
2. Confirm RI-05 card updates to 0% GREEN
3. Confirm BIZ-02 card ALSO updates to 0% GREEN (same underlying data)
4. Confirm BOTH RI-05 and BIZ-02 cards glow green simultaneously (linked highlight fix)
5. Confirm Business pillar score increases

**Fix 3 — BIZ-03 Re-Assignment:**
1. Generate fix on BIZ-03, click "Approve & Apply"
2. Confirm BIZ-03 card updates to 0% GREEN
3. Confirm Business pillar score increases further

**Fix 4 — RI-01 Invalid Status:**
1. Generate fix on RI-01, click "Approve & Apply"
2. Confirm RI-01 card updates to 0% GREEN
3. Confirm Referential pillar score increases

**After all 4 fixes:**
5. Confirm Overall score is significantly higher than 85% (expect ~95%+)
6. Confirm sparkline shows clear upward step at Post-fix point
7. Confirm history table shows multiple Post-fix rows (one per fix applied)

**Relevant Context:** `applyFix()` at line 1431, `POST /api/agents/remediate` (approve=true) at app.py:860, `execute()` in remediation_agent.py:114, `markKpiFixed()` and linked RI05↔BIZ02 highlight in dashboard JS, `_is_safe_sql()` safety check at remediation_agent.py:42.

**Status:** [ ] pending

---

## Sub-Task 13 — Sparkline Post-Fix Verification

**Intent:** Verify the sparkline and history table correctly show post-fix improvement.

**Expected Outcomes:**
- Each sparkline's last point is visibly higher than the previous point
- History table shows Post-fix row(s) with higher overall score
- Delta column for Post-fix row shows positive value (green, upward)

**Todo List:**
1. After applying CS-07 fix, check Consistency sparkline — confirm last dot is higher
2. Check overall sparkline — confirm last point is above 85%
3. Check history table bottom row — label contains "Post-fix", score > 85%, delta is positive green
4. Confirm Pre-fix seeded rows (Jun 14 → Jul 20) are untouched

**Relevant Context:** `renderSparklines()` at line 1135, `renderHistoryTable()` at line 1092, `GET /api/history` at app.py:522, `POST /api/snapshot` at app.py:568.

**Status:** [ ] pending

---

## Sub-Task 14 — Chat Agent

**Intent:** Verify the chat panel opens, sends questions to Bob, renders markdown, highlights cited KPIs.

**Expected Outcomes:**
- Chat bubble opens/closes on button click
- Questions receive formatted responses (bold text, bullet lists render — not raw `**`)
- KPI cards mentioned in reply pulse blue
- Conversation history maintained across turns

**Todo List:**
1. Click chat bubble (bottom-right) — confirm panel slides open
2. Send: "What is the overall DQ score and what is the worst KPI?"
   - Confirm response renders with markdown (bold, bullets — not raw `**text**`)
   - Confirm response mentions the overall score
3. Send: "What is causing the ghost mapping issue?"
   - Confirm CS-07 card pulses blue after response
4. Send: "If I'm a Finance Analyst, what should I fix first?"
   - Confirm response focuses on RI-05 / BIZ-02 (zero-weight orders)
5. Send: "What changed after the fix?" (after fixes applied in Sub-Task 12)
   - Confirm response references improved KPIs
6. Click chat bubble again — confirm panel closes
7. Re-open — confirm conversation history is preserved (last messages still visible)

**Relevant Context:** `toggleChat()` and `sendChat()` in dashboard JS, `POST /api/agents/chat` at app.py:901, `markdownToHtml()` function added to dashboard JS, `cited_kpis` extraction in chat_agent.py:107.

**Status:** [ ] pending

---

## Sub-Task 15 — Full Reset & Re-Verify

**Intent:** Verify reset_demo.py fully restores the original broken state so the demo can run again.

**Expected Outcomes:**
- All fixed KPIs revert to original failing values
- Alerts table cleared
- Post-fix snapshots removed
- Dashboard shows 85% overall with all RED KPIs back

**Todo List:**
1. With fixes applied, run `python reset_demo.py` in terminal
2. Confirm output shows 6 steps completing with row counts:
   - Step 1 (CS-07 revert): 3 rows
   - Step 2 (RI-01 revert): 1 row
   - Step 3 (RI-05/BIZ-02 revert): 6 rows
   - Step 4 (BIZ-03 revert): 7 rows
   - Step 5 (alerts clear): N rows deleted
   - Step 6 (snapshots clear): N rows deleted
3. Refresh dashboard — confirm:
   - Overall score back to 85%
   - CS-07 back to 3% RED
   - RI-05 back to 6% RED
   - BIZ-02 back to 6% RED
   - BIZ-03 back to 6.2% RED
   - RI-01 back to 0.9% RED
   - Alerts panel shows 0 open alerts
   - Sparkline history table shows no Post-fix rows (8 rows only)
4. Run Monitor Agent again — confirm fresh alerts generate (dedup count = 0 after first run)
5. Confirm `python reset_demo.py --dry-run` prints SQL but makes no changes
6. Confirm `python reset_demo.py --alerts-only` only clears alerts, leaves data untouched

**Relevant Context:** `reset_demo.py` full file, all 6 SQL statements and their WHERE clauses.

**Status:** [ ] pending
