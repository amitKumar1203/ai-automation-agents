# AI Automation Dashboard (Next.js)

Operations dashboard for the multi-agent automation platform. Connects to the FastAPI backend via a BFF proxy (`/api/backend/*`) so the browser never sees the API key.

## Prerequisites

Start the FastAPI backend first (from the `project/` directory):

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

## Setup

```bash
cd frontend
cp .env.local.example .env.local
npm install
```

## Run locally

```bash
npm run dev
```

Open **http://localhost:3000** — login gate, then role-aware Overview.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Overview — KPIs, pending counts, agent links |
| `/email-agent` | Gmail thread monitoring |
| `/vendor-agent` | Monday vendor quote follow-up |
| `/po-agent` | Salesforce PO readiness |
| `/artwork-agent` | Numeric + vision artwork verification |
| `/intake-agent` | Intake submit, review, category correction |
| `/storefront-agent` | Storefront image search |
| `/installer-agent` | Installer matching |
| `/followup-agent` | Stalled project follow-up |
| `/vision-agents` | Phase 3 vision agents (4 tabs) |
| `/supervisor` | Queue, jobs, retries, escalations |
| `/audit-log` | Approve / reject across all agents |
| `/admin` | Write-back mode, approval rules, operators (admin only) |
| `/login` | Dashboard password gate |

## Environment

Local `.env.local` (see `.env.local.example`):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
BACKEND_API_KEY=<same as backend API_KEY>
DASHBOARD_PASSWORD=<dashboard login password>
```

Production uses `API_BASE_URL` or `NEXT_PUBLIC_API_URL` pointing at the deployed API. The BFF attaches `BACKEND_API_KEY` server-side.

## Production

- Dashboard: https://ai-automation-agents-plum.vercel.app
- API: https://ai-automation-agents-api.vercel.app

Set strong `DASHBOARD_PASSWORD` and `BACKEND_API_KEY` on the Vercel frontend project. Restrict FastAPI `CORS_ALLOWED_ORIGINS` to the exact dashboard origin.

See [`../docs/PHASE1_UAT.md`](../docs/PHASE1_UAT.md) for the full production gate checklist.
