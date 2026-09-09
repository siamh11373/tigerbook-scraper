# Discovery and experiment log

Created 2026-09-09. The entries below are planned experiments. No live TigerBook experiments have been run during repository setup.

## First two hours

| ID | Time budget | Question and small experiment | Decision informed | Status |
| --- | --- | --- | --- | --- |
| E01 | 10 minutes | Confirm the target URL, eligible account, intended population, permitted collection, and authorized sharing. | Whether and where live investigation can proceed. | Planned |
| E02 | 25 minutes | Attempt an automated login from a clean browser context with configured credentials and no human MFA action. Observe challenge types without logging secret values. | Whether the unattended requirement is achievable through the observed supported flow. | Planned |
| E03 | 25 minutes | Compare original HTML, rendered content, and ordinary network responses for a few permitted profiles with different structures. | HTML, browser, API, or hybrid extraction. | Planned |
| E04 | 25 minutes | Inspect listing continuation, ordering, stable IDs, duplicate results, result caps, and any authoritative count. | Whether exhaustive discovery can be demonstrated. | Planned |
| E05 | 20 minutes | Retrieve one observed profile through the candidate collection path; test detection of authentication loss in a disposable context. | Session sharing and recovery design. | Planned |
| E06 | 15 minutes | Measure a small permitted sample's latency, requests, unique IDs, and fields; document the selected approach. | Runtime estimate and initial implementation scope. | Planned |

If scope or authentication blocks live investigation, continue with public documentation and synthetic cases. Elapsed time does not establish permission. Do not deliberately provoke rate limits, account lockouts, or repeated MFA notifications.

## Completed experiment template

Copy this template only when recording an actual experiment. Keep hypotheses, observations, and conclusions distinct.

### E__: Short descriptive title

- **Date and environment:**
- **Question:**
- **Hypothesis:**
- **Permission/scope relevant to this experiment:**
- **Method:** Minimal actions taken, with secret values omitted.
- **Observed result:** What actually happened, including failures.
- **Evidence:** Synthetic fixture, sanitized summary, command/check result, or private evidence reference with no sensitive content.
- **Decision:** What changes as a result.
- **Remaining uncertainty:**
- **Switch condition:** What evidence would reverse the decision.
- **Related commit:** Add only an actual commit identifier.
- **AI involvement:** Tool, sanitized prompt summary, accepted/rejected advice, and verification.

## Completed live experiments

None yet.
