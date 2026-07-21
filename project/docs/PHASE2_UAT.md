# Phase 2 production gate — UAT checklist & sign-off

Aligned with **AI_Automation.docx** Phase 2: Storefront Search, Intake &
Classification, Installer Matching, Automated Follow-Up.

See also: [`PHASE2.md`](PHASE2.md) (scope summary) · [`INTAKE_ROLLOUT.md`](INTAKE_ROLLOUT.md) (Intake worker detail)

## Deployed endpoints

| Service | URL |
|---------|-----|
| API | https://ai-automation-agents-api.vercel.app |
| Dashboard | https://ai-automation-agents-plum.vercel.app |
| Monday workspace | softude-cast.monday.com |

## Phase 2 env (Vercel API project)

| Variable | Agent | Status |
|----------|-------|--------|
| `MONDAY_STOREFRONT_BOARD_ID` | Storefront Search | Set (`5030067646`) |
| `MONDAY_INSTALL_PROJECTS_BOARD_ID` | Installer Matching | Set (`5030067898`) |
| `MONDAY_INSTALLERS_BOARD_ID` | Installer Matching | Set (`5030067966`) |
| `MONDAY_INTAKE_*_BOARD_ID` (×5) | Intake routing | See Intake boards checklist below |
| `ANTHROPIC_API_KEY` | Intake classify | Required; verify credits |
| `GOOGLE_PLACES_API_KEY` | Storefront imagery | Optional (fallback URLs when unset) |
| `WRITE_BACK_MODE` | All approve paths | `live` for production side effects |

Shared Phase 1 secrets still apply: `API_KEY`, `CRON_SECRET`, `MONDAY_API_TOKEN`,
`DATABASE_URL`, Salesforce/Gmail tokens. Management RBAC: [`MANAGEMENT_SIGNOFF.md`](MANAGEMENT_SIGNOFF.md).

---

## Storefront Search UAT

**Board:** Storefront Projects (`5030067646`)  
**Columns:** Project ID · Store Address · Storefront Image (link)  
**Route:** `/storefront-agent` · `GET /api/storefront-agent/run`

### Checklist

- [ ] Run from dashboard → tasks appear with `FOUND` / `LOW_CONFIDENCE` / `NOT_FOUND`
- [ ] Risky rows land in Audit log **Needs review** tab (latest run per task only)
- [ ] Reviewer approves one row → `execution_status=SUCCESS` (when `WRITE_BACK_MODE=live`)
- [ ] Monday item **Storefront Image** column updates with image URL
- [ ] Re-run same project → stale pending entries auto-rejected as `superseded-by-rerun`
- [ ] (Optional) With `GOOGLE_PLACES_API_KEY` → live Places imagery instead of fallback URLs

### Quick API smoke

```bash
curl -sS -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/storefront-agent/run"
```

---

## Installer Matching UAT

**Boards:** Install Projects (`5030067898`) · Installer Roster (`5030067966`)  
**Project columns:** Project ID · Install Region · **Assigned Installer** (Text, not People)  
**Roster columns:** Region · Capacity · Active Jobs · Email (item name = installer name)  
**Route:** `/installer-agent` · `GET /api/installer-agent/run`

### Checklist

- [ ] Run from dashboard → projects ranked by region fit + spare capacity
- [ ] `MATCHED` / `LOW_CONFIDENCE` rows appear in Audit log
- [ ] Approve → Monday **Assigned Installer** text column updates
- [ ] Approve → owner draft outreach email planned (notify path)
- [ ] Reject → no Monday write-back
- [ ] Low-capacity / no-match projects surface as `NO_MATCH` or `LOW_CONFIDENCE`

### Quick API smoke

```bash
curl -sS -H "X-API-Key: $API_KEY" \
  "https://ai-automation-agents-api.vercel.app/api/installer-agent/run"
```

**Verified assignments (production smoke):** INST-101 → Austin Signs Co · INST-102/105 → Chicago Field Team · INST-104 → Pacific Northwest Installers · INST-103 rejected (empty assignee).

---

## Automated Follow-Up UAT

**Route:** `/followup-agent` · Salesforce + owner notify  
**Config:** Owner email via Admin DB (`get_followup_notify_email()`)

### Checklist

- [ ] Run / cron poll surfaces stale Salesforce opportunities or activities
- [ ] Follow-up tasks appear in Audit log when status is risky
- [ ] Approve → owner notification sent (or `DRY_RUN` when mode is dry_run)
- [ ] No direct client auto-reply from follow-up agent

---

## Intake & Classification UAT

**Route:** `/intake-agent` · async worker via `/api/cron/intake`  
**Detail:** [`INTAKE_ROLLOUT.md`](INTAKE_ROLLOUT.md)

### Prerequisites

- [ ] `DATABASE_URL` (PostgreSQL) migrated
- [ ] `ANTHROPIC_API_KEY` funded
- [ ] All five Intake Monday boards created and env-set (checklist below)
- [ ] Category owner emails or `NOTIFY_OWNER_EMAIL` configured
- [ ] `INTAKE_WEBHOOK_SECRET` set if using signed webhook producer

### Checklist

- [ ] Dashboard submit → `202` queued; submission visible in list/detail
- [ ] Cron drains jobs → classification + routing complete
- [ ] High-confidence safe categories route automatically
- [ ] Support / unclassified / low-confidence wait for reviewer action
- [ ] Reviewer category correction → item moves to correct board with cross-link
- [ ] `intake_check_existing_records=true` → duplicate submitter email upserts same-board item
- [ ] Approve with `WRITE_BACK_MODE=live` → correct Monday board + owner email
- [ ] Dead job retry from reviewer UI after fixing provider fault

### Automated tests

```bash
cd project
python3 -m pytest \
  tests/test_intake_classification_agent.py \
  tests/test_intake_persistence_queue.py \
  tests/test_intake_workflow_worker.py \
  tests/test_monday_intake_routing.py -v
```

---

## Intake Monday boards checklist

Create **five separate boards** (one per category). Each board needs the same column
set unless you override per-board column IDs in env.

| # | Category | Env var | Board ID | Created | Env set | Columns OK | Dry-run test | Live test |
|---|----------|---------|----------|:-------:|:-------:|:------------:|:------------:|:---------:|
| 1 | `new_project` | `MONDAY_INTAKE_NEW_PROJECT_BOARD_ID` | | [ ] | [ ] | [ ] | [ ] | [ ] |
| 2 | `quote_request` | `MONDAY_INTAKE_QUOTE_REQUEST_BOARD_ID` | | [ ] | [ ] | [ ] | [ ] | [ ] |
| 3 | `support_issue` | `MONDAY_INTAKE_SUPPORT_ISSUE_BOARD_ID` | | [ ] | [ ] | [ ] | [ ] | [ ] |
| 4 | `general_inquiry` | `MONDAY_INTAKE_GENERAL_INQUIRY_BOARD_ID` | | [ ] | [ ] | [ ] | [ ] | [ ] |
| 5 | `unclassified` | `MONDAY_INTAKE_UNCLASSIFIED_BOARD_ID` | | [ ] | [ ] | [ ] | [ ] | [ ] |

### Required columns (shared or per-board override)

| Column purpose | Default env var | Column type |
|----------------|-----------------|-------------|
| External submission ID | `MONDAY_INTAKE_EXTERNAL_SUBMISSION_ID_COLUMN_ID` | Text |
| Category | `MONDAY_INTAKE_CATEGORY_COLUMN_ID` | Text |
| Submitted by | `MONDAY_INTAKE_SUBMITTED_BY_COLUMN_ID` | Text |
| Submission text | `MONDAY_INTAKE_SUBMISSION_TEXT_COLUMN_ID` | Long text |
| Owner | `MONDAY_INTAKE_OWNER_COLUMN_ID` | People |
| Previous item ID (optional) | `MONDAY_INTAKE_PREVIOUS_ITEM_ID_COLUMN_ID` | Text |
| Replacement item ID (optional) | `MONDAY_INTAKE_REPLACEMENT_ITEM_ID_COLUMN_ID` | Text |

### Per-category owner (optional Monday person IDs)

| Category | Env var |
|----------|---------|
| new_project | `MONDAY_INTAKE_NEW_PROJECT_OWNER_ID` |
| quote_request | `MONDAY_INTAKE_QUOTE_REQUEST_OWNER_ID` |
| support_issue | `MONDAY_INTAKE_SUPPORT_ISSUE_OWNER_ID` |
| general_inquiry | `MONDAY_INTAKE_GENERAL_INQUIRY_OWNER_ID` |
| unclassified | `MONDAY_INTAKE_UNCLASSIFIED_OWNER_ID` |

### Board setup steps

1. Create board in workspace **softude-cast**.
2. Add columns from the table above (titles can match defaults in `.env.example`).
3. Copy board ID → set env on Vercel API project → redeploy.
4. Set optional `MONDAY_INTAKE_{CATEGORY}_OWNER_ID` for default assignee.
5. Run one submission per category in `WRITE_BACK_MODE=dry_run`; confirm audit detail.
6. Switch to `live`; send one controlled submission per category; verify board + email.

---

## Audit log UX (Phase 2)

- [ ] Tabs: **Needs review** · **Approved** · **Rejected** · **All history**
- [ ] Needs review shows latest pending run per task (deduped)
- [ ] New agent run auto-rejects older pending as `superseded-by-rerun`
- [ ] Approve/reject requires reviewer or admin role

---

## Sign-off

| Agent / capability | Engineering verified | Ops / UAT verified | Notes |
|--------------------|:--------------------:|:------------------:|-------|
| Storefront Search | [ ] | [ ] | Board `5030067646` |
| Installer Matching | [ ] | [ ] | Boards `5030067898` / `5030067966` |
| Automated Follow-Up | [ ] | [ ] | Salesforce token refresh as needed |
| Intake & Classification | [ ] | [ ] | Blocked until 5 boards + Anthropic |
| Intake existing-record check | [ ] | [ ] | Admin toggle default `true` |

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product / doc owner | | | |
| Engineering | | | |
| Ops / UAT | | | |

**Completion estimate:** Storefront + Installer + Follow-Up ≈ **100%** built and production-verified. Intake ≈ **90%** (code live; full prod UAT pending board setup + Anthropic credits).

**Post sign-off (optional):**

- `GOOGLE_PLACES_API_KEY` for real storefront imagery
- Phase 3 agents (Rendering, Mock-up, Photo QC, Install QC)
