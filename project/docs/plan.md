# AI Supervisor — Build Plan (validated against proposal scope)

**Proposal:** The AI Supervisor has exactly **8 responsibilities** (task routing, queue management, approvals, escalations, monitoring, logging, error recovery, status tracking).

**Validation basis:** Current codebase (`supervisor/*`, `backend/services/agent_job_worker.py`, `backend/routes/{webhooks,cron,supervisor,audit}.py`, `docs/PHASE1_SUPERVISOR.md`) plus open UAT items in `PHASE1_UAT.md`, `PHASE2_UAT.md`, and `MANAGEMENT_SIGNOFF.md`.

**Key finding — Task routing & Approvals:** Both are **implemented in code** and are what separate this system from standalone agent scripts. Remaining work is **UAT hardening**, **dashboard visibility**, **Intake dual-queue alignment**, and **Phase 3 agent gaps** (mock-up share + QC sign-off).

---

## Task routing & Approvals — explicit confirmation

| Capability | Implemented? | Where | Remaining gap |
|------------|:------------:|-------|---------------|
| **Task routing** | ✅ Yes | `supervisor/router.py` `route_event()` maps `gmail` / `monday` / `salesforce` / `followup` / `storefront` / `installer` / `all` → `poll_*` jobs; `backend/routes/webhooks.py` + `backend/routes/cron.py` enqueue via router (never call agents inline) | Intake uses a **separate** async queue (`intake_workflow.py`), not `route_event`. Dashboard manual runs call `Supervisor.run_batch()` directly (still audited). |
| **Approvals (HITL)** | ✅ Yes (Phase 1–3) | `supervisor/approval_policy.py` `requires_human_approval()` + `RISKY_STATUS_MAP`; audit approve → `action_executor.py` | Intake has a **parallel** reviewer workflow on `/intake-agent`, not the main audit log. |

---

## Full to-do list (complete — not truncated)

### A. Session / ops (recent)

| ID | To-do | Status |
|----|-------|--------|
| SF-01 | Refresh Salesforce OAuth token locally and sync `SALESFORCE_REFRESH_TOKEN` + `SALESFORCE_INSTANCE_URL` to Vercel | ✅ Done |
| SF-02 | Smoke-test production PO Agent + Follow-up Agent against live Salesforce after token sync | ⬜ Pending |
| UI-01 | Deploy updated dashboard theme (soft dark) to Vercel production | ✅ Done |

### B. Supervisor core — implementation & regression

| ID | To-do | Status |
|----|-------|--------|
| TR-01 | **Task routing UAT:** Verify webhooks (`/api/webhooks/gmail`, `monday`, `salesforce`, `all`) and cron `/api/cron/poll-all` call `route_event()` → enqueue `agent_poll` jobs (not inline agent runs) | ⬜ Pending |
| TR-02 | **Intake routing alignment:** Either register `intake` in `supervisor/router.py` + unified event catalog, **or** document Intake’s separate `background_jobs` queue as an approved architectural exception in `PHASE1_SUPERVISOR.md` | ✅ Done |
| TR-03 | **Dashboard routing regression:** Assert all agent “Run Analysis” paths use `Supervisor.execute_task` / `run_batch` and always write `audit_entries` (extend `tests/test_supervisor.py` or `tests/test_phase1_complete.py`) | ✅ Done |
| QM-01 | **Queue visibility:** Expose and verify `queue_depth_summary()` on `GET /api/supervisor/status` in production | ⬜ Pending |
| QM-02 | **Poll frequency (ops):** Configure Make.com → `POST /api/webhooks/all` (or Vercel Pro cron) if sub-daily polling is required (Hobby cron = daily 06:00 UTC) | ⬜ Pending |
| QM-03 | **Dead-letter handling UAT:** Dead poll job → `POST /api/supervisor/jobs/{id}/retry` (reviewer/admin) on production | ⬜ Pending |
| AP-01 | **Approvals UAT — risky statuses:** Verify each HITL gate lands in Audit **Needs review**: `UNANSWERED`, `PO_READY_FOR_RELEASE`, `SEND_REMINDER`/`ESCALATE`, `MISMATCH`/`UNCERTAIN`, `SEND_FOLLOWUP`/`ESCALATE`, `FOUND`/`LOW_CONFIDENCE`, `MATCHED`/`LOW_CONFIDENCE` | ⬜ Pending |
| AP-02 | **Approvals UAT — low confidence:** Verify confidence &lt; threshold (default 0.75) forces approval for any agent | ⬜ Pending |
| AP-03 | **Approvals UAT — write-back:** Approve one item in `dry_run`, then in `live`; confirm `execution_status` + `execution_detail` on audit row | ⬜ Pending |
| AP-04 | **Intake HITL UAT:** Reviewer approve/reject/correct-category on `/intake-agent` → Monday routing + owner email (separate from audit log) | ⬜ Pending |
| AP-05 | **Phase 3 — AI mock-up agent:** Implement `ai_mockup` + `READY_FOR_EXTERNAL_SHARE` write-back | ✅ Done |
| AP-06 | **Phase 3 — Installation QC agent:** Implement `installation_qc` + `FAIL`/`NEEDS_REVIEW` write-back | ✅ Done |
| AP-08 | **Phase 3 — AI Rendering + Photo Analysis agents** + approval policy + `/vision-agents` UI | ✅ Done |
| AP-07 | **Live email HITL:** Re-consent Gmail with `gmail.send`; UAT owner notify + optional `CLIENT_AUTO_ACK_ENABLED` after approve | ⬜ Pending |
| ES-01 | **Escalation markers:** Verify agent `ESCALATE` statuses merge escalation payload via `merge_escalation_marker()` on approve | ⬜ Pending |
| ES-02 | **Stale approvals:** Verify `escalate_stale_pending()` runs on `/api/cron/poll-all` and notifies owner | ⬜ Pending |
| ES-03 | **Dead job escalation:** Verify dead `agent_poll` jobs trigger owner notification path | ⬜ Pending |
| MO-01 | **Supervisor monitoring UI:** Add dashboard page (or expand Overview) consuming `GET /api/supervisor/status` — queue, `last_run_by_agent`, `open_escalations`, `recent_failures` | ✅ Done |
| MO-02 | **Management drill-down:** Link open escalations / dead jobs from Overview to audit log or new Supervisor view | 🟡 Partial (Supervisor alerts → audit log; Overview link TBD) |
| LG-01 | **Logging UAT:** Confirm every agent execution persists audit row with `timestamp`, `input_json`, `result_data`, `approval_status`, `execution_status` | ⬜ Pending |
| LG-02 | **Supersede on re-run:** Verify stale pending audit entries auto-rejected when same `task_id` is re-run | ⬜ Pending |
| ER-01 | **Poll retry:** Verify failed poll jobs retry with backoff then land in `dead` status | ⬜ Pending |
| ER-02 | **Write-back retry:** Verify failed approve write-back auto-enqueues `writeback_retry` job | ⬜ Pending |
| ER-03 | **Operator recovery UI:** Expose dead-job list + retry in dashboard for reviewer/admin (API exists; UI missing) | ✅ Done |
| ST-01 | **Task status UI:** Build task/project detail view wired to `GET /api/supervisor/tasks/{task_id}` (audit + related jobs end-to-end) | ✅ Done |
| ST-02 | **Audit ↔ task link:** From audit log row, deep-link to task status view by `task_id` | 🟡 Partial (Supervisor lookup + link to audit; audit row → supervisor TBD) |

### C. Production UAT & sign-off (from existing checklists)

| ID | To-do | Status |
|----|-------|--------|
| UAT-01 | Complete all items in `docs/PHASE1_UAT.md` § Functional UAT (11 checks) | ⬜ Pending |
| UAT-02 | Complete Storefront Search checklist in `docs/PHASE2_UAT.md` | ⬜ Pending |
| UAT-03 | Complete Installer Matching checklist in `docs/PHASE2_UAT.md` | ⬜ Pending |
| UAT-04 | Complete Automated Follow-Up checklist in `docs/PHASE2_UAT.md` | ⬜ Pending |
| UAT-05 | Complete Intake & Classification checklist in `docs/PHASE2_UAT.md` | ⬜ Pending |
| UAT-06 | Complete Admin panel UAT in `docs/PHASE1_UAT.md` § Admin panel (5 checks) | ⬜ Pending |
| UAT-07 | Complete role matrix in `docs/MANAGEMENT_SIGNOFF.md` (Operator / Reviewer / Admin / Security) | ⬜ Pending |
| UAT-08 | Management sign-off table (Product, Engineering, Ops) | ⬜ Pending |

**Total: 35 to-dos** (9 done, 2 partial, 24 pending)

---

## Mapping: 8 Supervisor responsibilities → to-dos

| # | Proposal responsibility | Covered by to-do(s) | Status |
|---|-------------------------|---------------------|--------|
| 1 | **Task routing** — evaluate incoming events and route to specialised agents | TR-01, TR-02, TR-03, QM-02; code: `router.py`, `webhooks.py`, `cron.py` | 🟡 **Partial** — core routing ✅; Intake parallel queue + dashboard direct-run paths need alignment/UAT |
| 2 | **Queue management** — manage pending agent task queue | QM-01, QM-02, QM-03, ER-01, ER-03; code: `agent_job_worker.py`, `background_jobs` | 🟡 **Partial** — queue ✅ in API; ops cadence + dashboard visibility pending |
| 3 | **Approvals** — HITL before outbound email, PO release, mock-up share, QC sign-off, low confidence | AP-01, AP-02, AP-03, AP-04, AP-05, AP-06, AP-07, AP-08; code: `approval_policy.py`, `audit.py`, `action_executor.py` | 🟡 **Partial** — all Phase 1–3 agent gates ✅ in code; production UAT + live email pending |
| 4 | **Escalations** — stuck / failed / overdue items | ES-01, ES-02, ES-03; code: `escalation.py` | 🟡 **Partial** — logic ✅; production notify UAT pending |
| 5 | **Monitoring** — live status of all agents and workflows | MO-01, MO-02, QM-01; code: `GET /api/supervisor/status`, dashboard overview | 🟡 **Partial** — API ✅; no dedicated Supervisor UI page |
| 6 | **Logging** — timestamp, input, output, outcome for every action | LG-01, LG-02; code: `audit_log.py`, `Supervisor.execute_task` | ✅ **Full** (code complete; UAT confirmation via LG-01/LG-02) |
| 7 | **Error recovery** — retry/recover without manual intervention | ER-01, ER-02, ER-03, QM-03; code: job backoff, `writeback_retry`, retry endpoint | 🟡 **Partial** — auto-retry ✅; operator UI for dead letters pending |
| 8 | **Status tracking** — end-to-end task/project state | ST-01, ST-02; code: `GET /api/supervisor/tasks/{task_id}` | 🟡 **Partial** — API ✅; frontend task journey view missing |

### Status legend

- ✅ **Full** — Responsibility implemented; remaining work is verification/docs only
- 🟡 **Partial** — Core path exists; gaps are UI, UAT, Phase 3 agents, or Intake alignment
- ❌ **Missing** — No implementation (none of the 8 are fully missing; worst case is 🟡)

---

## New to-dos added to close proposal gaps

These were **not** adequately covered before this validation:

| ID | Why added | Closes responsibility |
|----|-----------|----------------------|
| TR-02 | Intake not in `route_event()` | #1 Task routing |
| AP-05 | `ai_mockup` agent + external share write-back | #3 Approvals | ✅ Done |
| AP-06 | `installation_qc` agent + QC sign-off write-back | #3 Approvals | ✅ Done |
| AP-08 | `ai_rendering` + `photo_analysis` agents + `/vision-agents` UI | #3 Approvals + proposal Phase 3 | ✅ Done |
| MO-01 | No Supervisor monitoring page in dashboard | #5 Monitoring |
| ST-01 | `GET /api/supervisor/tasks/{id}` not exposed in UI | #8 Status tracking |
| ST-02 | Audit log not linked to task journey | #8 Status tracking |
| ER-03 | Dead-job retry API exists but no dashboard UI | #7 Error recovery |

---

## Recommended build order (after approval)

1. **UAT hardening (no new code):** TR-01, AP-01–AP-04, LG-01, ES-01–ES-02, ER-01–ER-02, SF-02, UAT-01–UAT-07  
2. **Supervisor visibility (frontend):** MO-01, ST-01, ST-02, ER-03  
3. **Architecture decision:** TR-02 (unify Intake routing vs document exception)  
4. **Phase 3 agents (proposal completion):** AP-05, AP-06  
5. **Sign-off:** UAT-08  

---

## Code anchors (for reviewers)

| Responsibility | Primary files |
|----------------|---------------|
| Task routing | `supervisor/router.py`, `backend/routes/webhooks.py`, `backend/routes/cron.py` |
| Queue management | `backend/services/agent_job_worker.py`, `persistence/repositories.py` (JobRepository) |
| Approvals | `supervisor/approval_policy.py`, `backend/routes/audit.py`, `supervisor/action_executor.py` |
| Escalations | `supervisor/escalation.py` |
| Monitoring | `backend/routes/supervisor.py`, `supervisor/audit_log.py` `get_dashboard_overview()` |
| Logging | `supervisor/audit_log.py`, `supervisor/supervisor.py` |
| Error recovery | `agent_job_worker.py` (backoff/dead), `writeback_retry` queue |
| Status tracking | `backend/routes/supervisor.py` `GET /tasks/{task_id}` |

Automated tests: `tests/test_supervisor_phase1_gaps.py`, `tests/test_approval_policy.py`, `tests/test_phase1_complete.py`, `tests/test_rbac_matrix.py`
