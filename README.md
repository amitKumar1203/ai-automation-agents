# AI Automation Agents

Multi-agent automation platform with a Supervisor + Agents architecture.

This repository is organized with the main application code inside `project/`.

## Repository Structure

- `project/backend/` - FastAPI backend and API routes
- `project/frontend/` - Next.js operations dashboard
- `project/agents/` - Agent implementations
- `project/supervisor/` - Routing, approvals, and audit workflow
- `project/persistence/` - Database and migrations
- `project/tests/` - Automated test suite
- `project/docs/` - Rollout and phase documentation

## Main Documentation

The complete setup, architecture, endpoints, and rollout guidance is here:

- [`project/README.md`](project/README.md)

Key docs:

- [`project/docs/PHASE1_SUPERVISOR.md`](project/docs/PHASE1_SUPERVISOR.md)
- [`project/docs/PHASE1_UAT.md`](project/docs/PHASE1_UAT.md)
- [`project/docs/INTAKE_ROLLOUT.md`](project/docs/INTAKE_ROLLOUT.md)

## Quick Start

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

Frontend: `http://localhost:3000`  
Backend API docs: `http://localhost:8000/docs`

## Notes

- Secrets and tokens are intentionally gitignored.
- Use `WRITE_BACK_MODE=dry_run` first for safe testing.
