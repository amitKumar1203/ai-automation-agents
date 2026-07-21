# Intake production rollout

The production Intake path is asynchronous:

1. `POST /api/intake-agent/classify` (authenticated dashboard) or signed
   `POST /api/webhooks/intake` persists a submission and returns `202`.
2. `/api/cron/intake` claims leased classification/routing jobs.
3. Safe, high-confidence categories route automatically. Support,
   unclassified, and low-confidence results wait for reviewer/admin action.
4. Monday and Gmail effects use durable idempotency records. Failed effects
   are retried; completed effects are replayed without being sent again.

## 1. Database and migrations

Production requires shared PostgreSQL through `DATABASE_URL`. SQLite is only
for local development and tests.

```bash
cd project
export DATABASE_URL='postgresql://...?...sslmode=require'
python3 -m persistence.migrate
```

The runner applies each file in `persistence/migrations/postgres/` once and
records it in `intake_schema_migrations`. Back up PostgreSQL before rollout.
Do not manually mark a migration applied. To recover from a failed migration,
restore the backup or fix the database state, then rerun the same command.

Local migration smoke test:

```bash
cd project
unset DATABASE_URL
python3 -m persistence.migrate
```

## 2. Required secrets and identities

Set these in the backend deployment:

- `DATABASE_URL`, `API_KEY`, `CRON_SECRET`, `TRUSTED_IDENTITY_SECRET`
- `ANTHROPIC_API_KEY`
- `INTAKE_WEBHOOK_SECRET`
- `MONDAY_API_TOKEN` and every `MONDAY_INTAKE_*` board/column value
- Gmail `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_TOKEN_JSON`
- category owner emails (or `NOTIFY_OWNER_EMAIL`)
- `CORS_ALLOWED_ORIGINS` when browsers access the API cross-origin

Set matching `BACKEND_API_KEY` and `TRUSTED_IDENTITY_SECRET` in the frontend.
Start users with `AUTH_DEFAULT_ROLE=operator`; promote reviewer/admin roles in
`operator_accounts` through an audited operational process.

### Google OAuth

Create a **Web application** OAuth client for Auth.js and register the frontend
callback URL (`https://<frontend-domain>/api/auth/callback/google`). Configure
`AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `AUTH_SECRET`, and the allowed Workspace
domain on the frontend.

Gmail worker access is a separate server-side grant. Enable Gmail API and
consent to `gmail.readonly` and `gmail.send` with the existing Desktop OAuth
flow, verify `token.json` contains a refresh token, then store the complete JSON
as `GOOGLE_TOKEN_JSON` in the backend. Never commit `token.json`. If scopes,
client credentials, or access change, revoke the old grant, delete the local
token, consent again, replace the deployment secret, and redeploy.

## 3. Signed webhook

Clients must sign the exact raw request bytes. Required headers:

- `X-Webhook-Timestamp`: current Unix seconds
- `X-Webhook-Source`: stable provider name
- `X-Webhook-Delivery-ID`: unique, stable delivery identifier
- `X-Webhook-Signature`: `sha256=<hex HMAC>`

The signed bytes are:

```text
timestamp + "\n" + source + "\n" + delivery_id + "\n" + raw_body
```

Deliveries outside `WEBHOOK_REPLAY_WINDOW_SECONDS` are rejected. Reusing a
delivery ID with identical bytes returns the original submission as a `202`
replay; reusing it with different bytes returns `409`.

Example:

```bash
body='{"submission_id":"uat-1","submitted_by":"uat@example.com","text":"Please quote a lobby sign."}'
ts="$(date +%s)"
source='uat'
delivery='uat-delivery-1'
sig="$(printf '%s\n%s\n%s\n%s' "$ts" "$source" "$delivery" "$body" |
  openssl dgst -sha256 -hmac "$INTAKE_WEBHOOK_SECRET" -hex |
  awk '{print $2}')"
curl -i -X POST "$API_BASE/api/webhooks/intake" \
  -H 'Content-Type: application/json' \
  -H "X-Webhook-Timestamp: $ts" \
  -H "X-Webhook-Source: $source" \
  -H "X-Webhook-Delivery-ID: $delivery" \
  -H "X-Webhook-Signature: sha256=$sig" \
  --data-binary "$body"
```

## 4. Monday Intake boards

Create separate boards for `new_project`, `quote_request`, `support_issue`,
`general_inquiry`, and `unclassified`. Configure each board ID. Every board
must have a text column for the external submission ID; configure the shared
`MONDAY_INTAKE_EXTERNAL_SUBMISSION_ID_COLUMN_ID` or per-board overrides.

Configure category, submitter, request text, owner, previous item ID, and
replacement item ID columns where used. Owner values are Monday person IDs.
The integration searches all pages on all Intake boards. A category correction
to another board creates the replacement, cross-links when configured, and
archives the old item.

The Monday token needs only the workspaces/boards required for these reads and
writes. Validate board and column IDs in `WRITE_BACK_MODE=dry_run` first.

## 5. Workers and schedules

Vercel invokes `/api/cron/intake` every minute and retains `/api/cron/poll-all`
at its existing schedule. Vercel sends `Authorization: Bearer $CRON_SECRET`.
Other schedulers may use that header, `X-Cron-Secret`, or `X-API-Key`.

Each invocation drains a bounded batch. Tune:

- `INTAKE_CRON_MAX_JOBS` (hard cap per invocation)
- `INTAKE_JOB_LEASE_SECONDS` (must exceed expected provider latency)
- classification/routing max attempts
- retry base/max delay

The endpoint may also be run manually:

```bash
curl -sS "$API_BASE/api/cron/intake?limit=10" \
  -H "Authorization: Bearer $CRON_SECRET"
```

Dead jobs stay visible in submission detail. Reviewer/admin users can retry
them after fixing the provider or configuration fault.

## 6. Dry-run UAT

Keep `WRITE_BACK_MODE=dry_run`. Use test-only provider credentials or mocked
providers; do not point UAT at production Monday boards or owner mailboxes.

```bash
cd project
python3 -m persistence.migrate
python3 -m pytest \
  tests/test_intake_classification_agent.py \
  tests/test_intake_persistence_queue.py \
  tests/test_intake_workflow_worker.py \
  tests/test_monday_intake_routing.py -v
```

Then verify through the UI:

1. Submit one message for each category and observe `202`/queued state.
2. Run the Intake cron until each reaches routing or approval.
3. Correct a category as reviewer; confirm operators receive `403`.
4. Confirm list/detail state, attempts, append-only events, and dead-job retry.
5. Replay the signed delivery and confirm one submission/job.
6. Inject one Monday and Gmail timeout; confirm retry and one completed effect.

## 7. Live rollout and recovery

1. Back up and migrate PostgreSQL.
2. Deploy backend with `WRITE_BACK_MODE=dry_run`; verify health, auth, CORS,
   signed webhook, cron authorization, and persisted list/detail.
3. Deploy frontend with matching backend and identity secrets.
4. Run dry-run UAT and inspect `background_jobs`, `webhook_deliveries`, and
   `effect_executions`.
5. Set `WRITE_BACK_MODE=live`, deploy, and send one controlled submission per
   category. Verify the expected Monday board and owner email.
6. Enable the real webhook producer and monitor dead jobs/provider errors.

To stop side effects, immediately set `WRITE_BACK_MODE=dry_run` and redeploy;
leave ingestion and persistence running. To stop processing too, disable the
Intake cron while retaining queued jobs. Fix credentials/configuration, restore
the cron, and retry dead jobs through the reviewer UI. Completed effects must
not be deleted or reset: their idempotency records prevent duplicate Monday
writes and emails. Restore PostgreSQL from backup only for database corruption
or a failed migration, not for ordinary provider failures.
