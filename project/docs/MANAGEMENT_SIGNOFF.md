# Management & RBAC — doc sign-off

Aligned with **AI_Automation** management vision: role-based views, human-in-the-loop
approvals, admin-configurable routing, and audited operator governance.

## Production URLs

| Service | URL |
|---------|-----|
| API | https://ai-automation-agents-api.vercel.app |
| Dashboard | https://ai-automation-agents-plum.vercel.app |

## Role matrix (expected behavior)

| Capability | Operator | Reviewer | Admin |
|------------|:--------:|:--------:|:-----:|
| View home dashboard | Yes | Yes (Review Queue) | Yes (Management) |
| Run agent screens | Yes | Yes | Yes |
| Read audit log | Yes | Yes | Yes |
| Approve / reject audit entries | No | Yes | Yes |
| Intake approve / reject | No | Yes | Yes |
| Admin settings (`/admin`) | No | No | Yes |
| Manage operator roles | No | No | Yes |
| Edit owners / write-back / approval rules | No | No | Yes |

Automated coverage: `tests/test_rbac_matrix.py`

## Sprint deliverables (doc-complete)

| Sprint | Scope | Status |
|--------|-------|--------|
| 1 | Audit RBAC, admin route protection, `CRON_SECRET` in prod | Done |
| 2 | DB-backed owners & write-back config (admin UI) | Done |
| 3 | DB-backed approval rules & confidence threshold | Done |
| 4 | Role-based home + sidebar views | Done |
| 5 | UAT checklist + role matrix tests + sign-off | Done |

## Manual UAT checklist (production)

Sign each after verifying on https://ai-automation-agents-plum.vercel.app

### Authentication & roles

- [ ] Google login restricted to allowed domain(s)
- [ ] First login creates `operator` in `operator_accounts`
- [ ] Admin can promote user to `reviewer` / `admin` from `/admin`
- [ ] Logout + login refreshes role in session

### Operator (`operator` role)

- [ ] Home shows **Operator Workspace** (not management KPIs)
- [ ] Sidebar: no **Admin** link
- [ ] Audit log: read-only (no Approve/Reject buttons)
- [ ] Direct `/admin` redirects to home

### Reviewer (`reviewer` role)

- [ ] Home shows **Review Queue** with pending CTA when items exist
- [ ] Sidebar: **Approvals** near top
- [ ] Audit log: can approve/reject; actor = signed-in email
- [ ] `/admin` blocked

### Admin (`admin` role)

- [ ] Home shows **Management Overview** + Admin shortcut
- [ ] `/admin`: operator list, editable owners, write-back mode
- [ ] `/admin`: confidence threshold + per-agent risky statuses save
- [ ] Config changes appear in audit trail (`GET /api/admin/config/audit`)

### Security

- [ ] `CRON_SECRET` set on API project (cron without secret returns 503)
- [ ] `TRUSTED_IDENTITY_SECRET` set on API + frontend
- [ ] `API_KEY` / `BACKEND_API_KEY` match between projects
- [ ] Operator API call to `/api/admin/*` returns 403

### Write-back (when ready for live)

- [ ] Default `WRITE_BACK_MODE=dry_run` (or set via Admin UI)
- [ ] Approve one risky item → `execution_status=DRY_RUN`
- [ ] Switch to `live` via Admin → re-approve → real side effects
- [ ] Rollback to `dry_run` via Admin

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product / doc owner | | | |
| Engineering | | | |
| Ops / UAT | | | |

**Completion estimate:** ~100% vs AI_Automation management requirements (Phase 1).

Remaining optional enhancements (post sign-off):

- SSO group → role auto-mapping (Okta/Google groups)
- Per-agent dashboard widgets tuned by department
- Email send scope re-consent for production `WRITE_BACK_MODE=live`
