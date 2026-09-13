# Discovery and experiment log

Created 2026-09-09. The initial table preserves the planned experiments from repository setup. Dated observations below distinguish completed work from outstanding live checks.

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
- Related commit: `7ca15ff` (durable collection state and validated CSV export), pushed to the existing repository.
- Important distinction: these synthetic tests establish local behavior, not TigerNet compatibility or a complete live dataset.
- AI contribution: Codex wrote the implementation and synthetic tests. THINKING.md remains author-provided text only.

### CLI, browser tests, and recovery validation

- Implemented the module CLI, sample/full state isolation, offline export, process locking, CAS form-origin checks, challenge detection, supported SSO renewal, private inspection, and collection orchestration.
- Added generic DOM/JSON adapters that require observed site configuration. No production contract exists. Live discovery, API/display URL mapping, expanded sections, field coverage, and throughput remain unverified.
- A login redirect or directory link is not accepted as authenticated content verification. The authentication diagnostic requires the observed listing and profile parser.
- Failure encountered: mocked HTTP redirects allowed a test to load the public CAS page. Replaced those test redirects with intercepted navigations and configured an unusable proxy so accidental unmocked browser traffic fails closed. These are synthetic credentials and fixtures, not live authentication evidence.
- Failure encountered: an HTML fixture omitted its UTF-8 charset and Chromium displayed mojibake. Corrected the fixture response charset. Unicode CSV readback also has independent coverage.
- Review change: removed repeated whole-population counts from each profile iteration and added bounded pending batches with an indexed status lookup. A 301-record test checks that status updates do not skip records.
- Review change: a repeated parser read only checks consistency. Completion additionally requires independent field-coverage evidence in the site contract. The repository does not claim that evidence exists.
- Validation: 49 synthetic tests passed, including real Chromium with intercepted traffic, interruption/resume equivalence, injected checkpoint rollback, late fields, nested records, large cells, offline export, and safe authentication failures. Ruff lint/format and Git whitespace checks passed.
- AI contribution: Codex implemented code/tests, investigated failures, reviewed the diff, and wrote operator documentation. This log reports that work; it is not the author's personal reflection. THINKING.md was unchanged.
- Remaining blocker: local credentials are still unconfigured. No authenticated benchmark, small live export, full collection, or manually uploaded Sheet exists.

## Completed authenticated experiments

None yet. Credentials are required before inspecting the directory and validating its extraction adapter.
