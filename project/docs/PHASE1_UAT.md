# Phase 1 production gate — UAT checklist

## Deployed endpoints

- API: `https://ai-automation-agents-api.vercel.app`
- Dashboard: `https://ai-automation-agents-plum.vercel.app`

## Env (Vercel API project)

| Variable | Purpose |
|----------|---------|
| `API_KEY` / `CRON_SECRET` | Protect approve/reject, webhooks, cron |
| `NOTIFY_OWNER_EMAIL` | Owner digest / post-approval notifies |
| `WRITE_BACK_MODE` | `dry_run` (safe) or `live` |
| `MONDAY_PO_COLUMN_TITLE` | Optional; default `PO Number` |
| `GOOGLE_TOKEN_JSON` | Must stay `gmail.readonly` until send re-consent |

## Frontend (Vercel UI project)

| Variable | Purpose |
|----------|---------|
| `API_BASE_URL` or `NEXT_PUBLIC_API_URL` | Backend origin for BFF proxy |
| `BACKEND_API_KEY` (or `API_KEY`) | Must match backend `API_KEY`; BFF attaches `X-API-Key` |
| `DASHBOARD_PASSWORD` | Password for `/login` gate |

## Make.com / webhooks

```bash
# Header: X-Cron-Secret: <CRON_SECRET>
curl -X POST https://ai-automation-agents-api.vercel.app/api/webhooks/gmail \
  -H "X-Cron-Secret: $CRON_SECRET"
curl -X POST .../api/webhooks/monday -H "X-Cron-Secret: $CRON_SECRET"
curl -X POST .../api/webhooks/salesforce -H "X-Cron-Secret: $CRON_SECRET"
curl -X POST .../api/webhooks/all -H "X-Cron-Secret: $CRON_SECRET"
```

Vercel Cron hits `GET /api/cron/poll-all` daily at 06:00 UTC on Hobby
(`0 6 * * *`). For more frequent polls, use Make.com → `POST /api/webhooks/all`
or upgrade Vercel Pro.

## Live write-back checklist

1. Keep `WRITE_BACK_MODE=dry_run` until smoke tests pass in dry-run.
2. Approve one vendor escalate + one PO release; confirm `execution_status=DRY_RUN` and detail JSON.
3. For live email: local re-consent with `SEND_SCOPES`, upload new `GOOGLE_TOKEN_JSON`.
4. Set `WRITE_BACK_MODE=live`, approve again, verify Monday PO column + SF `PO_Exists__c`.
5. Rollback: set `WRITE_BACK_MODE=dry_run` and redeploy/env update.

## Functional UAT

- [ ] Overview shows pending + cached KPIs after a `/run` or webhook
- [ ] Unanswered email → Audit **Needs review** (HITL); approve → owner notify
- [ ] Client auto-ack only after approve when `CLIENT_AUTO_ACK_ENABLED=true` (default off)
- [ ] Vendor approve → owner notify (+ Monday Escalate when live)
- [ ] PO approve → SF mark + Monday PO Number sync (when live)
- [ ] Cron `/api/cron/poll-all` enqueues via Supervisor router then drains jobs
- [ ] `GET /api/supervisor/status` shows queue depth + last runs
- [ ] Dead job → `POST /api/supervisor/jobs/{id}/retry` (reviewer/admin)
- [ ] Audit entry includes `input` snapshot + result + outcome
- [ ] Approve/reject without trusted identity returns 403 for operators
- [ ] Health `GET /` stays public

See also **`docs/PHASE1_SUPERVISOR.md`** for the 8 Supervisor responsibilities.

## Management & RBAC (Sprint 5)

See **`docs/MANAGEMENT_SIGNOFF.md`** for full role matrix and sign-off table.

| Check | Operator | Reviewer | Admin |
|-------|:--------:|:--------:|:-----:|
| Home view | Operator Workspace | Review Queue | Management Overview |
| Audit approve/reject | No | Yes | Yes |
| `/admin` settings | No | No | Yes |
| Edit owners / write-back / approval rules | No | No | Yes |

Automated: `pytest tests/test_rbac_matrix.py`

### Admin panel UAT

- [ ] `/admin` lists operators; role + active toggles persist
- [ ] Write-back mode editable (`dry_run` / `live`) without redeploy
- [ ] Category owner emails editable per intake category
- [ ] Confidence threshold + risky statuses editable per agent
- [ ] `GET /api/admin/config/audit` shows change history

### Required env (management)

| Variable | Project | Purpose |
|----------|---------|---------|
| `TRUSTED_IDENTITY_SECRET` | API + Frontend | Signed role headers from BFF |
| `AUTH_ALLOWED_DOMAINS` | Frontend | Google login domain gate |
| `DATABASE_URL` | API | Operators + system_config persistence |
