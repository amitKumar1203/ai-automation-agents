# Phase 1 — AI Supervisor

Maps the proposal's **8 Supervisor responsibilities** to code paths.

## Responsibilities

| # | Responsibility | Implementation |
|---|----------------|----------------|
| 1 | Task routing | [`supervisor/router.py`](../supervisor/router.py) `route_event` → webhook/cron enqueue |
| 2 | Queue management | [`backend/services/agent_job_worker.py`](../backend/services/agent_job_worker.py) on `background_jobs` (`agent_poll`, `writeback_retry`) |
| 3 | Approvals | [`supervisor/approval_policy.py`](../supervisor/approval_policy.py) + audit approve → [`action_executor.py`](../supervisor/action_executor.py). Outbound email HITL: `UNANSWERED` risky; client ack only after approve when `CLIENT_AUTO_ACK_ENABLED=true` (default **false**). Phase 3 stubs: `ai_mockup`, `installation_qc` |
| 4 | Escalations | [`supervisor/escalation.py`](../supervisor/escalation.py) — agent `ESCALATE` markers, dead jobs, stale pending approvals |
| 5 | Monitoring | `GET /api/supervisor/status` + overview `queue` / `open_escalations` |
| 6 | Logging | `audit_entries` — timestamp, `input_json`, `result_data`, approval + `execution_status` |
| 7 | Error recovery | Job fail → exponential backoff → dead; write-back FAIL → auto `writeback_retry`; operator retry for dead only |
| 8 | Status tracking | `GET /api/supervisor/tasks/{task_id}` merges audit + related jobs |

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
| External mock-up share | Policy stub `ai_mockup` (agent TBD Phase 3) |
| Final QC sign-off | Policy stub `installation_qc` (agent TBD Phase 3) |

## Tests

```bash
cd project
python3 -m pytest tests/test_supervisor_phase1_gaps.py tests/test_approval_policy.py tests/test_client_ack.py -v
```
