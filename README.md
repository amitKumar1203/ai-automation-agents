# AI Automation Agents

Multi-agent automation platform with a **Supervisor + Agents** architecture. Sits alongside Monday.com, Salesforce, and Gmail — detects operational risk, routes work to specialized agents, and keeps every action in an auditable **human-in-the-loop** workflow.

Application code lives in [`project/`](project/).

## Production

| Service | URL |
|---------|-----|
| Dashboard | https://ai-automation-agents-plum.vercel.app |
| API | https://ai-automation-agents-api.vercel.app |

## Agent catalogue

| Phase | Agent | Dashboard | Data source |
|:-----:|-------|-----------|-------------|
| 1 | Email Reply Monitoring | `/email-agent` | Gmail |
| 1 | Vendor Follow-Up | `/vendor-agent` | Monday.com |
| 1 | Purchase Order Automation | `/po-agent` | Salesforce |
| 1 | Artwork Verification | `/artwork-agent` | On-demand (numeric + vision) |
| 2 | Intake & Classification | `/intake-agent` | Form / webhook → Claude |
| 2 | Storefront Search | `/storefront-agent` | Monday.com |
| 2 | Installer Matching | `/installer-agent` | Monday.com |
| 2 | Automated Follow-Up | `/followup-agent` | Salesforce |
| 3 | AI Rendering | `/vision-agents` | Image upload → Claude |
| 3 | AI Mock-up | `/vision-agents` | Image upload → Claude |
| 3 | Photo Analysis | `/vision-agents` | Image upload → Claude |
| 3 | Installation QC | `/vision-agents` | Image upload → Claude |
| — | **AI Supervisor** | `/supervisor` | Routes, queues, retries all agents |

Shared UI: **Overview** (`/`), **Audit Log** (`/audit-log`), **Admin** (`/admin`).

## Architecture

```
Gmail / Monday / Salesforce / Webhooks
              ↓
       AI Supervisor (routing, approvals, audit)
              ↓
    Specialized agents (12 business functions)
              ↓
   Human approve → write-back (dry_run or live)
```

Agents propose; risky or low-confidence actions wait in **Audit Log → Needs review** before any outbound email, PO release, or system update.

## Quick start

### Backend

```bash
cd project
pip3 install -r requirements.txt
python3 -m uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd project/frontend
cp .env.local.example .env.local
npm install
npm run dev
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs

Copy `project/.env.example` → `project/.env` for integrations. Use `WRITE_BACK_MODE=dry_run` until UAT sign-off.

### Tests

```bash
cd project
python3 -m pytest tests/ -v
```

## Repository structure

| Path | Purpose |
|------|---------|
| `project/backend/` | FastAPI routes and services |
| `project/frontend/` | Next.js operations dashboard |
| `project/agents/` | Agent implementations |
| `project/supervisor/` | Routing, approvals, audit, write-back |
| `project/integrations/` | Gmail, Monday, Salesforce, Claude vision |
| `project/persistence/` | PostgreSQL / SQLite, migrations |
| `project/tests/` | Automated test suite |
| `project/docs/` | UAT, rollout, and phase documentation |

## Documentation

| Doc | Purpose |
|-----|---------|
| [`project/README.md`](project/README.md) | Full setup, endpoints, and integration guides |
| [`project/docs/PHASE1_SUPERVISOR.md`](project/docs/PHASE1_SUPERVISOR.md) | Supervisor responsibilities |
| [`project/docs/PHASE1_UAT.md`](project/docs/PHASE1_UAT.md) | Phase 1 production gate |
| [`project/docs/PHASE2_UAT.md`](project/docs/PHASE2_UAT.md) | Phase 2 + Intake boards |
| [`project/docs/PHASE3.md`](project/docs/PHASE3.md) | Vision agents |
| [`project/docs/INTAKE_ROLLOUT.md`](project/docs/INTAKE_ROLLOUT.md) | Intake worker rollout |
| [`project/docs/UAT_SIGNOFF_REPORT.md`](project/docs/UAT_SIGNOFF_REPORT.md) | Engineering sign-off status |

## Security notes

- Secrets (`.env`, OAuth tokens, API keys) are gitignored — never commit them.
- Production uses `API_KEY` (backend), `DASHBOARD_PASSWORD` (frontend), and role-based operator accounts.
- Start with `WRITE_BACK_MODE=dry_run`; switch to `live` only after controlled UAT.
