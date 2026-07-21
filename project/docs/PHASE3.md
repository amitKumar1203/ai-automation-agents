# Phase 3 — AI Vision Agents

Phase 3 delivers four on-demand vision agents (Claude Sonnet 4.5) aligned with the proposal **§4 Agent Catalogue** and **§5 Human-in-the-Loop** defaults.

## Agents

| Agent | Code name | Endpoint | Risky statuses (HITL) | Post-approve write-back |
|-------|-----------|----------|----------------------|-------------------------|
| AI Rendering | `ai_rendering` | `POST /api/phase3/rendering/analyze` | `READY_FOR_REVIEW`, `LOW_CONFIDENCE` | Owner email with design brief |
| AI Mock-up | `ai_mockup` | `POST /api/phase3/mockup/analyze` | `READY_FOR_EXTERNAL_SHARE`, `LOW_CONFIDENCE` | Owner email (external share gate) |
| Photo Analysis | `photo_analysis` | `POST /api/phase3/photo-analysis/analyze` | `ISSUES_FOUND`, `LOW_CONFIDENCE` | Owner notify + optional Monday notes |
| Installation QC | `installation_qc` | `POST /api/phase3/installation-qc/analyze` | `FAIL`, `NEEDS_REVIEW`, `LOW_CONFIDENCE` | Owner notify + Monday QC status |

All agents follow the **artwork vision** pattern: multipart image upload → Claude structured tool output → Supervisor audit log → human approve when risky → `action_executor` write-back when `write_back_mode=live`.

## Scope note (generative vs analysis)

The platform uses **Anthropic vision analysis** (no OpenAI / DALL·E). Rendering and mock-up agents produce structured design assessments, alternatives, and readiness judgments for designer review — not pixel-generated PNG files. Actual generative image APIs can be wired behind the same HITL gates in a follow-on sprint.

## UI

Dashboard: **`/vision-agents`** — tabbed upload for all four agents.

## Tests

```bash
cd project && python3 -m pytest tests/test_phase3_agents.py tests/test_phase3_vision.py -q
```

## Build checklist (plan.md)

- AP-05 `ai_mockup` — done
- AP-06 `installation_qc` — done
- AP-07 `ai_rendering` — done
- AP-08 `photo_analysis` — done
