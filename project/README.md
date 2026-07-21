# AI Automation Agents

Multi-agent automation system with a Supervisor + Agents architecture.

## Email Reply Monitoring Agent

Rule-based agent that flags client email threads where the last message is from the client and has been pending for more than 24 hours.

### Real Gmail Integration

Optional live inbox source for the email agent. Monitoring uses
`gmail.readonly`; post-approval owner notifications also request `gmail.send`.
**Agent runs themselves never send mail to clients by default** — only a
fixed **template acknowledgment** (no AI) may go to the client when a thread
is ``UNANSWERED``, and only when ``WRITE_BACK_MODE=live`` and
``CLIENT_AUTO_ACK_ENABLED=true`` (default on). Owner digest notify still uses
the approve / batch notify path. Re-consent with ``gmail.send`` before live
sends.

- Endpoint: `GET /api/email-agent/run` (live Gmail by default; `?source=mock` for tests)
- Credentials: set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in
  `project/.env` (copy from `.env.example`) — **gitignored**
- Optional fallback: `project/credentials.json` (Desktop OAuth download)
- First successful live run opens a browser for one-time Google consent and
  writes `project/token.json` (also **gitignored**) for later runs
- After upgrading scopes, delete `token.json` and re-consent so `gmail.send` is
  granted
- To revoke access: https://myaccount.google.com/permissions → remove the app,
  then delete `token.json` to re-authenticate
- Gmail failures return HTTP **502** with a clear message (no silent mock fallback)
- **Sender classification** (domain matching against the authenticated user's
  address from `users.getProfile`):
  - `team` — the authenticated user's own email
  - `internal` — same email domain (colleagues); does **not** trigger unanswered alerts
  - `client` — external domains only; these can be flagged unanswered after the threshold
- Extracted message text is automatically cleaned to remove signatures,
  disclaimers, and quoted reply chains for readability.
- **Optional demo filters** (live Gmail only): `?sender_filter=...` and/or
  `?keyword_filter=...` on the API, or use the **Filters** panel on the
  `/email-agent` dashboard. These narrow which fetched threads are shown —
  they do **not** change Gmail permissions.

```bash
curl 'http://localhost:8000/api/email-agent/run'
curl 'http://localhost:8000/api/email-agent/run?source=mock'
curl 'http://localhost:8000/api/email-agent/run?sender_filter=nirmal&keyword_filter=order%20status'
```

The dashboard `/email-agent` always runs against **live Gmail**.

### Testing with real Gmail

Live inbox messages are often newer than 24h, so nothing may show as
`UNANSWERED` during a demo. Temporarily lower the reply threshold via env
(restart the API after changing it):

```bash
# ~1 minute (fractional hours)
export EMAIL_THRESHOLD_HOURS=0.0167

# or put it in project/.env
# EMAIL_THRESHOLD_HOURS=0.0167
```

Default remains **24** when unset. Remove the override (or set back to `24`)
after the demo so production behavior stays intact.

## Vendor Follow-Up Agent

Rule-based agent that tracks vendor quote requests:

| Status | Condition | Approval |
|--------|-----------|----------|
| `OK` | Quote already received | Agent: no |
| `WAITING` | Pending ≤ 48h | Agent: no |
| `SEND_REMINDER` | Pending > 48h and ≤ 96h | Agent: yes |
| `ESCALATE` | Pending > 96h | Agent: yes |
| `INVALID_DATE` | `request_sent_at` is in the future (board data error) | Agent: no |

Registered as `vendor_followup`. Approval is status-aware via
`RISKY_STATUS_MAP`: only `SEND_REMINDER` and `ESCALATE` force human approval.
`OK`, `WAITING`, and `INVALID_DATE` auto-process when confidence is high.
`INVALID_DATE` is a data-quality flag (fix the Monday.com date) — not treated
as a risky follow-up action.

### Test the vendor agent

```bash
cd project
python3 -m pytest tests/test_vendor_followup_agent.py -v
```

### API endpoint

```bash
curl 'http://localhost:8000/api/vendor-agent/run'
curl 'http://localhost:8000/api/vendor-agent/run?source=mock'
```

### Real Monday.com Integration

Optional live board source for the vendor follow-up agent. Board **reads** on
every `/run`. Status **writes** only happen after a human approves an
`ESCALATE` action with ``WRITE_BACK_MODE=live``.

- Endpoint: `GET /api/vendor-agent/run` (live Monday.com by default;
  `?source=mock` for tests)
- Credentials: set `MONDAY_API_TOKEN` and `MONDAY_BOARD_ID` in
  `project/.env` (copy from `.env.example`) — **gitignored**
- Board setup: columns must be titled exactly **Project ID**, **Quote Received**,
  **Request Sent Date**, and **Budget** (Budget is fetched but not used by the
  agent yet)
- **Quote Received** must be a status column whose labels include **Received**
  (maps to `quote_received=True`); **Pending** and **Escalate** map to
  `quote_received=False` — the agent recalculates urgency from hours pending
- Monday.com failures return HTTP **502** with a clear message (no silent mock
  fallback)

The dashboard `/vendor-agent` always runs against **live Monday.com**.

## Purchase Order Automation Agent

Rule-based agent that prepares PO drafts for client-approved projects that
do not yet have a Purchase Order. It never releases a PO automatically.

| Status | Condition | Approval |
|--------|-----------|----------|
| `ALREADY_EXISTS` | PO already created | Agent: no |
| `PO_READY_FOR_RELEASE` | Approved project, no PO yet | Agent: yes (always) |

Registered as `po_automation`. `RISKY_STATUS_MAP` includes
`PO_READY_FOR_RELEASE` only — `ALREADY_EXISTS` is not risky.

### Test the PO agent

```bash
cd project
python3 -m pytest tests/test_po_automation_agent.py -v
```

### API endpoint

```bash
curl 'http://localhost:8000/api/po-agent/run'
curl 'http://localhost:8000/api/po-agent/run?source=mock'
```

### Real Salesforce Integration

Optional live org source for the PO automation agent. Project **reads** on
every `/run`. On approve of `PO_READY_FOR_RELEASE` with ``WRITE_BACK_MODE=live``,
the executor sets `PO_Exists__c=true` (and optionally creates a row in
``SALESFORCE_PO_OBJECT`` if configured).

- Endpoint: `GET /api/po-agent/run` (live Salesforce by default;
  `?source=mock` for tests)
- Credentials in `project/.env` (**gitignored**):
  - `SALESFORCE_CLIENT_ID` / `SALESFORCE_CLIENT_SECRET` (Connected App)
  - `SALESFORCE_DOMAIN` (your My Domain host, e.g. `xxx.my.salesforce.com`)
- **Preferred auth (recommended):** browser OAuth + refresh token
  1. Connected App → Callback URL must include exactly
     `http://localhost:8765/callback` (and optionally
     `http://127.0.0.1:8765/callback`)
  2. Selected OAuth scopes: `api`, `refresh_token`, `offline_access`
  3. Run once: `cd project && python3 -m integrations.salesforce_client login`
     (uses PKCE — no Username-Password toggle required)
  4. This writes `project/salesforce_token.json` (**gitignored**)
  5. Sync to Vercel: `./scripts/sync_salesforce_token_to_vercel.sh`
- **One active refresh token only:** If a teammate runs `login` on another
  laptop, Salesforce often invalidates the previous refresh token. Then
  production PO agent returns `expired access/refresh token`. Always sync to
  Vercel from the machine that just logged in, and avoid parallel logins.
- **Optional legacy auth:** Username-Password flow if enabled under
  Setup → OAuth and OpenID Connect Settings → **Allow OAuth Username-Password
  Flows**. Then set `SALESFORCE_USERNAME` / `SALESFORCE_PASSWORD` (password +
  security token). Many Summer ’23+ orgs block this by default.
- Custom object **Approved_Project__c** must expose:
  `Client_Name__c`, `Vendor_Name__c`, `Approved_Date__c`, `PO_Exists__c`,
  `Estimated_Amount__c` (Name is the project id)
- Salesforce failures return HTTP **502** with a clear message (no silent mock
  fallback)

The dashboard `/po-agent` always runs against **live Salesforce**.

## Intake & Classification Agent

Intake is a durable asynchronous workflow. Dashboard and signed webhook
submissions are persisted and queued before the API returns `202`; Claude and
external providers are never called inline. Claude (`claude-sonnet-4-5`)
classifies into:

- `new_project`
- `quote_request`
- `support_issue`
- `general_inquiry`

Safe categories at or above `INTAKE_AUTO_ROUTE_CONFIDENCE` route to their
dedicated Monday boards. Low-confidence, support, and unclassified results wait
for reviewer/admin approval or correction. Workers use leased jobs, bounded
retries/dead letters, optimistic versions, and idempotent Monday/Gmail effects.

```bash
# Dashboard/API submission
curl -i -X POST http://localhost:8000/api/intake-agent/classify \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"submission_id":"dashboard-1","submitted_by":"client@example.com","text":"How much would a new lobby sign cost?"}'

# Apply local SQLite or configured PostgreSQL migrations.
python3 -m persistence.migrate

# Drain a worker batch (Vercel also invokes this every minute).
curl 'http://localhost:8000/api/cron/intake?limit=10' \
  -H "Authorization: Bearer $CRON_SECRET"

python3 -m pytest tests/test_intake_*.py tests/test_monday_intake_routing.py -v
```

Production requires shared PostgreSQL, Anthropic, five Intake Monday boards,
Google OAuth with Gmail send scope, category owner emails, API/cron/identity
secrets, a separate webhook HMAC secret, and exact CORS origins. Begin with
`WRITE_BACK_MODE=dry_run`; switch to `live` only after mocked-provider and UI
UAT. Exact signed-webhook commands, Google OAuth setup, board columns, worker
tuning, migrations, rollout, and recovery are in
[`docs/INTAKE_ROLLOUT.md`](docs/INTAKE_ROLLOUT.md).

## Artwork Verification Agent

Enter artwork vs spec dimensions (±0.25 in) or upload an image for vision
analysis. Both paths are **on-demand** — no hardcoded sample batch.

| Status | Condition | Approval |
|--------|-----------|----------|
| `MATCH` | Width and height within ±0.25 in | Agent: no |
| `MISMATCH` | Either dimension exceeds tolerance | Agent: yes |

Registered as `artwork_verification`. `MISMATCH` and `UNCERTAIN` are in
`RISKY_STATUS_MAP` (UNCERTAIN applies to the vision path).

### Test the artwork agent

```bash
cd project
python3 -m pytest tests/test_artwork_verification_agent.py -v
```

### API endpoints

```bash
# Numeric (user-entered inches)
curl -X POST http://localhost:8000/api/artwork-agent/verify-numeric \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"project_id":"PRJ-100","artwork_width_inches":48,"artwork_height_inches":36,"spec_width_inches":48,"spec_height_inches":36}'
```

## Vision-Based Artwork Verification

Phase 3 concept from the original proposal: a **vision agent** that reads
actual artwork images (not just pre-extracted numbers) and compares them to
window/storefront expectations. Implemented as an **additive** path alongside
the rule-based numeric check above — use numeric comparison when dimensions
are already known; use vision when you have an image to inspect.

| Status | Meaning | Approval |
|--------|---------|----------|
| `MATCH` | Image clearly meets the spec | Agent: no (Supervisor still escalates if confidence < 0.75) |
| `MISMATCH` | Clear dimension / design / quality problem | Always human review |
| `UNCERTAIN` | Image quality or labeling makes judgment unreliable | Always human review |

**Requirements**

- Set `ANTHROPIC_API_KEY` in `project/.env` (Claude vision via the Anthropic SDK)
- Per-image API costs apply (unlike the free rule-based numeric checks)
- Manual upload only in this pass — Gmail/Monday/Salesforce image fetch is future work

**API**

```bash
curl -X POST http://localhost:8000/api/artwork-agent/verify-vision \
  -F "artwork_image=@/path/to/artwork.png" \
  -F "spec_description=48in x 36in navy logo centered on white" \
  -F "project_id=PRJ-100" \
  -F "spec_image=@/path/to/reference.png"   # optional
```

Dashboard: **Artwork Agent → Image Upload** tab.

```bash
python3 -m pytest tests/test_vision_verification.py -v
```

Human-in-the-loop remains the default for anything that is not a clear MATCH:
`MISMATCH` and `UNCERTAIN` always go through approval, consistent with the
rest of the supervisor system.

### Run locally (CLI)

```bash
cd project
python3 main.py
```

### Run tests

```bash
cd project
python3 -m pytest tests/ -v
```

## Supervisor

The Supervisor sits above individual agents and handles routing, execution,
approval policy, and audit logging. Individual agents focus on task logic;
the Supervisor decides whether human approval is required.

### What it does

- **Agent registry** — maps agent names (e.g. `email_reply_monitoring`) to agent instances
- **Task routing** — `execute_task(agent_name, task, task_id)` runs the correct agent
- **Approval policy** — per-status risk rules (`RISKY_STATUS_MAP`) plus low
  confidence (< 0.75) or the agent's own `requires_approval` flag

  Example for `vendor_followup`:

  ```python
  RISKY_STATUS_MAP = {
      "vendor_followup": {"SEND_REMINDER", "ESCALATE"},
      "po_automation": {"PO_READY_FOR_RELEASE"},
      "artwork_verification": {"MISMATCH", "UNCERTAIN"},
  }
  ```

  Only those statuses force approval. Agents not listed (e.g.
  `email_reply_monitoring`) use confidence / agent flag only.
- **Audit log** — every execution is persisted to PostgreSQL in production
  (`DATABASE_URL`) with a local SQLite fallback
- **Batch runs** — `run_batch()` executes multiple tasks and returns aggregated counts

### Audit Log Persistence

The supervisor audit log uses **PostgreSQL in production**:

- Set `DATABASE_URL` to a standard PostgreSQL connection URL
- Designed for serverless deployments: all instances share the same audit rows
- Without `DATABASE_URL`, local development uses
  `project/data/audit_log.db` (gitignored)
- Each entry has a UUID `id` and `approval_status` defaulting to `PENDING`
- Columns `approved_by` / `approved_at` store who acted and when

### Approve / Reject Actions

Human decisions are a **one-way** transition: `PENDING` → `APPROVED` or `REJECTED`.
Already-decided entries cannot be changed again (API returns HTTP 409).

**On APPROVED**, the supervisor also runs a post-approval action executor:

| Agent | Action |
|-------|--------|
| `vendor_followup` (`SEND_REMINDER` / `ESCALATE`) | Notify `NOTIFY_OWNER_EMAIL`; on escalate, set Monday Quote Received → Escalate |
| `po_automation` (`PO_READY_FOR_RELEASE`) | Mark Salesforce `PO_Exists__c`; optional PO object create |
| `email_reply_monitoring` | Owner notify email |
| `artwork_verification` (`MISMATCH` / `UNCERTAIN`) | Owner notify (or log-only if no owner email) |

Controlled by env:

```bash
# default — plan the side effect, do not call external APIs
WRITE_BACK_MODE=dry_run

# real side effects
WRITE_BACK_MODE=live
NOTIFY_OWNER_EMAIL=ops@yourcompany.com
# optional
# SALESFORCE_PO_OBJECT=Purchase_Order__c
```

Execution outcome is stored on the audit row as `execution_status`
(`SKIPPED` / `DRY_RUN` / `SUCCESS` / `FAILED`) and `execution_detail`.

```bash
# Approve
curl -X POST http://localhost:8000/api/audit-log/<entry_id>/approve \
  -H 'Content-Type: application/json' \
  -d '{"approved_by":"amit"}'

# Reject
curl -X POST http://localhost:8000/api/audit-log/<entry_id>/reject \
  -H 'Content-Type: application/json' \
  -d '{"approved_by":"amit"}'
```

- Missing entry → **404**
- Already decided → **409**
- UI actions live on `/audit-log` (and pending counts on `/`)

```bash
curl http://localhost:8000/api/audit-log
curl http://localhost:8000/api/dashboard/overview
```

### Test the Supervisor

```bash
cd project
python3 -m pytest tests/test_supervisor.py -v
```

### API endpoints (via Supervisor)

```bash
# Run email agent batch through Supervisor
curl http://localhost:8000/api/email-agent/run

# Run vendor follow-up agent batch through Supervisor
curl http://localhost:8000/api/vendor-agent/run

# Run PO automation agent batch through Supervisor
curl http://localhost:8000/api/po-agent/run

# Run numeric artwork check (user-entered dimensions)
curl -X POST http://localhost:8000/api/artwork-agent/verify-numeric \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"artwork_width_inches":48,"artwork_height_inches":36,"spec_width_inches":48,"spec_height_inches":36}'

# View audit log
curl http://localhost:8000/api/audit-log
```

### Adding a new agent later

```python
from supervisor.agent_registry import register_agent
from agents.some_new_agent import SomeNewAgent

register_agent("some_new_agent", SomeNewAgent())
```

No changes to `Supervisor` core logic are required.

## Authentication

Two layers keep the public demo URLs locked:

### 1. Backend API key (`X-API-Key`)

- Env: **`API_KEY`** (long random string) on the FastAPI / Vercel API project.
- All agent, audit, and dashboard routes require header `X-API-Key: <API_KEY>`.
- **Public:** `GET /` (health only).
- **Webhooks / cron:** use **`CRON_SECRET`** (falls back to `API_KEY`) via
  `X-Cron-Secret`, `Authorization: Bearer …`, or `X-API-Key` — not left open.
- Local pytest leaves `API_KEY` unset so tests stay simple; **production must set it**.

### 2. Frontend dashboard password

- Env: **`DASHBOARD_PASSWORD`** on the Next.js / Vercel frontend project.
- Visiting the site without the login cookie redirects to `/login`.
- Successful login sets an **httpOnly** `dashboard_auth` cookie (30 days).
- Browser never sees the backend key. The Next BFF (`/api/backend/*`) adds
  **`BACKEND_API_KEY`** (must equal backend `API_KEY`; falls back to `API_KEY`
  if you already set that name on the frontend project).

Set strong random values in **both** Vercel projects, then redeploy. Never commit
passwords or API keys.

## Frontend (Next.js)

The dashboard lives in `frontend/` and runs separately from the API.

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open **http://localhost:3000** (Operations Overview). Agent pages and Audit are
in the top nav.

For production, the dashboard calls same-origin `/api/backend/*` (BFF) which
forwards to the FastAPI API and attaches `API_KEY` server-side. See
[`docs/PHASE1_UAT.md`](docs/PHASE1_UAT.md).

The FastAPI backend must be running on port 8000 first. Local development
allows the two localhost dashboard origins. Production allows only the exact,
comma-separated `CORS_ALLOWED_ORIGINS` values; wildcard origins are rejected.

See `frontend/README.md` for full setup details.

## REST API (FastAPI)

The API exposes the Email Reply Monitoring Agent for frontend dashboards.

### Install dependencies

```bash
cd project
pip3 install -r requirements.txt
```

### Start the server

```bash
cd project
python3 -m uvicorn backend.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Test the email agent endpoint

```bash
curl http://localhost:8000/api/email-agent/run
```

Health check:

```bash
curl http://localhost:8000/
```

### Example response shape

```json
{
  "total_threads": 3,
  "unanswered_count": 1,
  "ok_count": 2,
  "results": [
    {
      "thread_id": "ORD-1042",
      "status": "UNANSWERED",
      "last_sender": "client",
      "last_message_text": "Hi, can you confirm my order status?",
      "last_message_timestamp": "2026-07-13T06:00:00+00:00",
      "hours_pending": 30.0,
      "confidence": 1.0,
      "requires_approval": false,
      "reasoning": "Client message pending reply for 30.0 hours (threshold: 24h)"
    },
    {
      "thread_id": "ORD-1043",
      "status": "OK",
      "last_sender": "client",
      "last_message_text": "Thanks for the quick response earlier!",
      "last_message_timestamp": "2026-07-14T04:00:00+00:00",
      "hours_pending": 8.0,
      "confidence": 1.0,
      "requires_approval": false,
      "reasoning": "No action needed: client message is within 24h threshold (8.0 hours pending)"
    }
  ]
}
```
