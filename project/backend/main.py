# Run from the project/ directory:
#   python3 -m uvicorn backend.main:app --reload --port 8000
# Next.js dashboard: http://127.0.0.1:3000 (see frontend/README.md)

"""FastAPI application entrypoint for the agent REST API."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load project/.env before agent imports so EMAIL_THRESHOLD_HOURS etc. apply.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth import require_api_key, require_roles
from backend.routes import (
    admin,
    artwork_agent,
    audit,
    cron,
    dashboard,
    email_agent,
    followup_agent,
    intake_agent,
    intake_webhook,
    operator_auth,
    phase3_agents,
    po_agent,
    storefront_agent,
    installer_agent,
    supervisor,
    vendor_agent,
    webhooks,
)

app = FastAPI(
    title="AI Automation Agents API",
    description="REST API for running automation agents",
    version="1.0.0",
)


def _allowed_cors_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in (os.getenv("CORS_ALLOWED_ORIGINS") or "").split(",")
        if origin.strip()
    ]
    production = (
        (os.getenv("ENVIRONMENT") or "").lower() == "production"
        or (os.getenv("NODE_ENV") or "").lower() == "production"
        or bool(os.getenv("VERCEL"))
    )
    if production:
        if "*" in configured:
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS cannot contain '*' in production"
            )
        return configured
    return configured or ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent + dashboard + audit: require X-API-Key when API_KEY is set.
_api_key_deps = [Depends(require_api_key)]
_dashboard_deps = [
    Depends(require_api_key),
    Depends(require_roles("operator", "reviewer", "admin")),
]
_admin_deps = [
    Depends(require_api_key),
    Depends(require_roles("admin")),
]

app.include_router(
    email_agent.router,
    prefix="/api/email-agent",
    tags=["email-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    vendor_agent.router,
    prefix="/api/vendor-agent",
    tags=["vendor-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    po_agent.router,
    prefix="/api/po-agent",
    tags=["po-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    artwork_agent.router,
    prefix="/api/artwork-agent",
    tags=["artwork-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    phase3_agents.router,
    prefix="/api/phase3",
    tags=["phase3-vision"],
    dependencies=_dashboard_deps,
)
app.include_router(
    followup_agent.router,
    prefix="/api/followup-agent",
    tags=["followup-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    storefront_agent.router,
    prefix="/api/storefront-agent",
    tags=["storefront-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    installer_agent.router,
    prefix="/api/installer-agent",
    tags=["installer-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    intake_agent.router,
    prefix="/api/intake-agent",
    tags=["intake-agent"],
    dependencies=_dashboard_deps,
)
app.include_router(
    audit.router,
    prefix="/api/audit-log",
    tags=["audit-log"],
    dependencies=_dashboard_deps,
)
app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=_dashboard_deps,
)
app.include_router(
    supervisor.router,
    prefix="/api/supervisor",
    tags=["supervisor"],
    dependencies=_dashboard_deps,
)
app.include_router(
    admin.router,
    prefix="/api/admin",
    tags=["admin"],
    dependencies=_admin_deps,
)
app.include_router(
    operator_auth.router,
    prefix="/api/auth",
    tags=["auth"],
    dependencies=_api_key_deps,
)

# Webhooks / cron use CRON_SECRET (or API_KEY fallback) — not double API-key gate.
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(
    intake_webhook.router,
    prefix="/api/webhooks/intake",
    tags=["webhooks"],
)
app.include_router(cron.router, prefix="/api/cron", tags=["cron"])


@app.get("/")
def health_check() -> dict[str, str]:
    """Simple health check endpoint (public)."""
    return {"status": "ok"}
