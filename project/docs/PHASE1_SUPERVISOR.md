# Phase 1 — AI Supervisor

Maps the proposal's **8 Supervisor responsibilities** to code paths.

## Responsibilities

| # | Responsibility | Implementation |
|---|----------------|----------------|
| 1 | Task routing | [`supervisor/router.py`](../supervisor/router.py) `route_event` → webhook/cron enqueue |
| 2 | Queue management | [`backend/services/agent_job_worker.py`](../backend/services/agent_job_worker.py) on `background_jobs` (`agent_poll`, `writeback_retry`) |
| 3 | Approvals | [`supervisor/approval_policy.py`](../supervisor/approval_policy.py) + audit approve → [`action_executor.py`](../supervisor/action_executor.py). Phase 3 vision agents: `ai_rendering`, `ai_mockup`, `photo_analysis`, `installation_qc` — see [`PHASE3.md`](PHASE3.md) |
| 4 | Escalations | [`supervisor/escalation.py`](../supervisor/escalation.py) — agent `ESCALATE` markers, dead jobs, stale pending approvals |
| 5 | Monitoring | `GET /api/supervisor/status` + overview `queue` / `open_escalations` |
| 6 | Logging | `audit_entries` — timestamp, `input_json`, `result_data`, approval + `execution_status` |
| 7 | Error recovery | Job fail → exponential backoff → dead; write-back FAIL → auto `writeback_retry`; operator retry for dead only |
| 8 | Status tracking | `GET /api/supervisor/tasks/{task_id}` merges audit + related jobs |

## Intake — approved dual-queue exception (TR-02)

Intake & Classification uses a **separate durable queue** (`intake_submissions` +
`background_jobs` for `classify` / `route` / owner notify), not
`supervisor/router.py` `route_event()` poll targets. This is intentional:

| Path | Trigger | Queue | HITL |
|------|---------|-------|------|
| Agent polls (email, vendor, PO, …) | Webhook/cron → `route_event()` | `agent_poll` | Audit log approve/reject |
| Intake | Dashboard submit / signed webhook | Intake worker jobs | `/intake-agent` reviewer approve |

Both paths share PostgreSQL persistence, RBAC, and write-back mode from Admin.
Intake is **not** a bypass of Supervisor policy — it is a specialised async
workflow for LLM classification + Monday routing. Future unification would add
an `intake` event source to `router.py` that enqueues classify jobs only.

## Triggers

```bash
# Cron — enqueue all + drain + stale escalation scan
curl -H "Authorization: Bearer $CRON_SECRET" \
  "https://ai-automation-agents-api.vercel.app/api/cron/poll-all"

# Webhook — route one source through Supervisor queue
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "https://ai-automation-agents-api.vercel.app/api/webhooks/gmail"

# Live status / jobs / retry
curl -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/supervisor/status"
curl -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/supervisor/jobs?status=dead"
curl -X POST -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/supervisor/jobs/{id}/retry"
```

## Env

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_POLL_MAX_ATTEMPTS` | 5 | Poll job retries before dead |
| `WRITEBACK_RETRY_MAX_ATTEMPTS` | 5 | Failed approve write-back retries |
| `AGENT_JOB_LEASE_SECONDS` | 120 | Claim lease |
| `AGENT_CRON_MAX_JOBS` | 50 | Drain drain cap |
| `SUPERVISOR_STALE_PENDING_HOURS` | 48 | Escalate pending approvals |
| `CLIENT_AUTO_ACK_ENABLED` | false | Post-approval client template ack |

## HITL matrix (Supervisor)

| Action | Gate |
|--------|------|
| Outbound owner notify (email unanswered) | Approve `UNANSWERED` |
| Client auto-ack | Approve + `CLIENT_AUTO_ACK_ENABLED=true` |
| Vendor reminder / escalate | Approve `SEND_REMINDER` / `ESCALATE` |
| PO release | Approve `PO_READY_FOR_RELEASE` |
| Low confidence (any agent) | Always approve |
| External mock-up share | `ai_mockup` — `READY_FOR_EXTERNAL_SHARE` → owner notify after approve |
| Final QC sign-off | `installation_qc` — `FAIL` / `NEEDS_REVIEW` → owner notify + Monday QC status |

## Tests

```bash
cd project
python3 -m pytest tests/test_supervisor_phase1_gaps.py tests/test_approval_policy.py tests/test_client_ack.py -v
```
