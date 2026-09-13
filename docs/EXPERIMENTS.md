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

## 2026-09-13: implementation observations

### Public authentication inspection

- Target: TigerNet, confirmed by the author. Collection and recipient permissions were confirmed by the author in the planning conversation.
- Method: followed the public `/login` link in a fresh Playwright Chromium context without submitting credentials.
- Observed result: redirect to `https://fed.princeton.edu/cas/login`. The form contains username and password inputs, hidden execution/event fields, and a LOGIN submit button.
- Decision: drive the observed CAS form through the browser and let the browser maintain its hidden values and session state. Never submit credentials to an unobserved identity-provider origin.
- Limitation: this verifies the public login form only. MFA behavior, authenticated navigation, population counts, and profile/API structures remain unverified.
- Credential configuration: an ignored local JSON template was created with empty values. No credential values were printed or committed.

### Durable collection and export core

- Implemented transactional SQLite discovery checkpoints, stable-ID records, isolated scope/account identity, dynamic field storage, streamed CSV generation and readback, and a completion report.
- Implemented rate pacing, bounded transient retries, Retry-After handling, one reauthentication per failed request, and response disposal.
- Validation: 26 synthetic tests passed on Python 3.12.14. Ruff lint/format and Git whitespace checks passed.
- Important distinction: these synthetic tests establish local behavior, not TigerNet compatibility or a complete live dataset.
- AI contribution: Codex wrote the implementation and synthetic tests. THINKING.md remains author-provided text only.

## Completed authenticated experiments

None yet. Credentials are required before inspecting the directory and validating its extraction adapter.
