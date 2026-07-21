# AI Automation Dashboard (Next.js)

Dark-themed dashboard for the multi-agent automation system. Connects to the FastAPI backend for email thread analysis and supervisor audit logs.

## Prerequisites

Start the FastAPI backend first (from the `project/` directory):

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

The backend must expose:

- `GET /api/email-agent/run`
- `GET /api/audit-log`

CORS is already enabled on the backend with `allow_origins=["*"]` for local development. **Restrict this in production.**

## Setup

```bash
cd frontend
cp .env.local.example .env.local
npm install
```

## Run the dashboard

```bash
npm run dev
```

Open **http://localhost:3000** — it redirects to `/email-agent`.

## Pages

| Route | Description |
|-------|-------------|
| `/email-agent` | Main dashboard with stats, thread cards, and Run Analysis |
| `/vendor-agent` | Vendor follow-up dashboard with reminder/escalation status |
| `/po-agent` | Purchase order drafts for approved projects awaiting release |
| `/artwork-agent` | Numeric artwork vs spec dimension verification |
| `/audit-log` | Table view of supervisor audit log entries |

## Environment

Set the API base URL in `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If unset, the app falls back to `http://localhost:8000`.

## Production note

Update `NEXT_PUBLIC_API_URL` to your deployed API URL and tighten FastAPI CORS to only allow your frontend domain.
