# Phase 2 — Operational Intelligence

Aligned with **AI_Automation.docx** Phase 2: Storefront Search, Intake &
Classification, Installer Matching, Automated Follow-Up.

## Status

| Agent / capability | Status |
|--------------------|--------|
| Automated Follow-Up | ✅ Live (Salesforce + owner notify) |
| Intake & Classification | ✅ Live (async worker + Monday + owner email) |
| Intake existing-record check | ✅ Same contact lookup on Monday before create |
| Storefront Search | ✅ Agent + API + dashboard (live Monday board) |
| Installer Matching | ✅ Agent + API + dashboard (live Monday boards) |

## Storefront Search

- **Route:** `/storefront-agent` · `GET /api/storefront-agent/run`
- **Env:** `MONDAY_STOREFRONT_BOARD_ID` + columns **Project ID**, **Store Address**, **Storefront Image**
- **Optional:** `GOOGLE_PLACES_API_KEY` for live imagery (otherwise deterministic mock URLs for UAT)
- **Approval:** `FOUND` and `LOW_CONFIDENCE` → Audit log → Approve → Monday link column (live write-back)

## Installer Matching

- **Route:** `/installer-agent` · `GET /api/installer-agent/run`
- **Env:**
  - `MONDAY_INSTALL_PROJECTS_BOARD_ID` — columns **Project ID**, **Install Region**, **Assigned Installer** (optional **Install Date**)
  - `MONDAY_INSTALLERS_BOARD_ID` — columns **Region**, **Capacity**, **Active Jobs**, **Email** (item name = installer)
- **Logic:** Rule-based rank by region fit + spare capacity (`capacity - active_jobs`)
- **Approval:** `MATCHED` and `LOW_CONFIDENCE` → Audit log → Approve → Monday **Assigned Installer** + owner draft outreach email

## Intake existing records

- **Config:** `intake_check_existing_records` in Admin DB (default `true`)
- Before Monday create, matches **submitted-by email** across Intake boards
- Routing result includes `existing_records`; upserts when same-board match exists

## UAT quick paths

```bash
# Storefront (live Monday board)
curl -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/storefront-agent/run"

# Installer (live Monday boards)
curl -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/installer-agent/run"

# Intake (after Anthropic credits + live write-back)
# Dashboard → Intake Agent → submit quote request → Audit approve if needed
```

## UAT & sign-off

Production checklist, Intake board setup table, and sign-off:
[`docs/PHASE2_UAT.md`](PHASE2_UAT.md)
