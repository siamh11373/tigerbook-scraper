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

### Clean-checkout rehearsal and final recovery review

- Related commit: `f70e3b1`, pushed to the existing public repository.
- Cloned the public repository into a new temporary directory. Created a new Python 3.12.14 environment with `python -m venv`, installed `requirements.txt` using pip, and ran the documented Playwright browser installation command. The browser binary was already present in the machine's Playwright cache.
- Ran all 49 tests in that fresh checkout: passed. Ruff lint/format, Git whitespace checks, and the installed CLI's expected missing-credentials error (exit 3) passed. The import resolved to the fresh checkout, not the development copy.
- This rehearses installation and synthetic operation only. A fresh authenticated reviewer run remains blocked on credentials and verified site integration.
- Final code review found that a failed fidelity audit could fall outside the sampling interval on restart. Persisted the requirement to repeat that profile's audit and added a regression test. A successful later profile cannot clear that obligation.
- Also tested interruption immediately after the final record commit. Resume now restores the verified-report flag from durable audit evidence after reconciling all records, avoiding a permanently stale partial report.
- THINKING.md remained unchanged. Staged files were reviewed to exclude credentials, personal records, exports, sessions, databases, and confidential sources.

## Completed authenticated experiments

The author ran the local credential launcher and reported
`interactive_authentication_required: Authentication requires an MFA interaction.`
This establishes an interactive challenge in the observed flow, not verified
directory access. No credential values were supplied to the agent.

The author subsequently authorized attended authentication. Added an opt-in
`--allow-interactive` mode: a visible browser waits up to five minutes for the user
to complete normal MFA, then continues. The same policy applies to session renewal.
Unattended mode still stops at a challenge. This changes the project requirement;
it does not satisfy the original assessment's unattended-authentication requirement.

Synthetic tests cover successful continuation after a simulated user handoff,
bounded timeout, and the existing unattended rejection. Live attended login and
directory integration remain unverified at that checkpoint. These changes remain local, with no push.

### Attended directory inspection

- The author's attended run produced local HTML, text, a screenshot, and eight JSON responses. Inspection artifacts were examined locally; no credential or profile values were printed in tool output or published.
- The ordinary directory response contains 18 users and reports `total_items` of 131,892. The observed listing path is `/frontoffice/api/users`, with page/per-page parameters. Rendered links reference `/users/<numeric ID>`, and the UI exposes a Next page button.
- The request carries location-related parameters, including exclusion of users without locations. The reported total is not yet proof that the listing includes every accessible profile; filter semantics and coverage require investigation.
- Extended the private inspection to follow the observed Next page control and three observed profile links. It records per-stage timings and responses, without guessing profile API endpoints. Added exclusion of token-service JSON payloads from future captures.
- Two synthetic inspection tests passed, including deduplicated sample links, pagination capture, and exclusion of token payloads. Ruff lint/format and whitespace checks passed.
- The next live checkpoint requires rerunning the attended inspection because the previous process and its in-memory credentials have ended. Full profile field structure, API mapping, and exhaustive discovery remain unverified. No push or upload was performed.

### Expanded inspection and observed adapter

- The next attended run saved two directory pages and three detailed profile captures. The listing pages contain 35 unique IDs across 36 results, with ordering by `last_seen_at`. Earlier concern about a nonempty location parameter was imprecise: `query[last_location]` is the literal string `false`. The interaction with `include_users_with_no_locations=false` still needs scope verification.
- Profiles use separate base, header, section/contact, badge, and followed-community responses. One profile has eight community memberships but only three were in its initial response. Native repeated records include ten employment records in one sample and four education records in another.
- Implemented the observed hybrid adapter and a dynamic metadata-based field parser, preserving repeated record associations and skipping restricted fields. Unknown structures stop extraction. Community pages are followed and reconciled by unique ID and reported total. Additional badge pages remain an explicit unsupported case.
- Profile requests are paced, and the browser response listener checks the subject profile ID even when a response URL retains an earlier route prefix. Request handlers now use Playwright's documented fallback behavior to preserve other handlers and test isolation.
- Created an ignored local site contract directly from the observed listing request. No personal IDs or credentials were inserted into source files. No commit or upload was made.
- Offline validation on the saved snapshots produced `output/inspection-preview/profiles.csv`: two rows, 52 columns, explicitly partial. The third profile failed because its community snapshot was incomplete. It was not silently exported with missing memberships.
- All 69 tests passed; Ruff lint/format and whitespace checks passed. The new adapter's live request-context compatibility, community pagination, runtime, and resume behavior still require the 25-profile live checkpoint.
- Full coverage and independent field-fidelity flags remain false. Identity matching and successful parsing are not presented as proof of complete field coverage. THINKING.md remains unchanged.

### Publication and next validation checkpoint

- The author authorized publishing the implementation with its synthetic tests, while keeping all real credentials, sessions, and collected data local. Earlier no-push statements above describe those earlier checkpoints.
- The author selected a 15-profile validation run. Updated the current instructions to use isolated `output/sample-15/` state. No live result is claimed for this run yet.

### Readable export after the 15-profile run

- The local run exported 15 profiles with 57 columns and no recorded profile failures. Three additional discovered profiles remain pending at the sample limit. Coverage and independent field fidelity remain unverified.
- The author found the JSON-filled CSV difficult to read. Added a presentation layer: decoded section headings, name columns first, line-separated lists, and numbered nested records. It applies to every discovered field without changing extraction or stored records.
- `profiles.csv` now contains readable values; `profiles.raw.csv` retains the previous exact keys and structured JSON representation. Both are verified against SQLite before replacement. No new dependency or authenticated request is needed to regenerate these files.

### Same-day throughput investigation

- The measured collection phase completed 15 profiles in 213.95 seconds, about 14.26 seconds per profile. A linear projection for the initially reported 131,892 members is 21.77 days, excluding later interruptions and reconciliation.
- The current adapter requires five observed profile-data responses per profile, sometimes additional community pages, and browser navigation. Even with zero other overhead, five requests at the configured one-request-per-second pace would require 7.63 days. This pace is our conservative configuration, not a verified TigerNet service limit.
- Completing that population in ten hours would require at least 18.32 profile-data requests per second, before directory requests, retries, and reconciliation. No evidence currently establishes that this load is supported. The global pacing and throttling protections remain in place.
- Removed profile image, media, and font downloads while preserving their URLs in extracted profile structures and the DOM. Scripts, stylesheets, and data responses are retained. No live speedup is claimed until measured.
- The saved directory capture did not expose a labelled bulk-export control. Official Hivebrite documentation describes separately provisioned partner administrator access, which is not established by ordinary TigerNet login. An approved bulk export remains a candidate requiring administrator confirmation: https://docs.hivebrite.com/authentication

### Concurrent scraper implementation

- The author rejected the bulk-export alternative and relaxed the dynamic-field requirement. Implemented `--fast` as a scraper using observed GET request templates, not an administrator export. Its main performance change is removing per-profile browser rendering and overlapping network waits; metadata field discovery itself was not the bottleneck.
- Normal login and three rendered reference profiles establish request paths and in-memory authentication headers. Direct requests must agree on labelled sections, introductions, memberships, badges, and repeated records before collection proceeds. This startup comparison is automated inside the full run and is not proof of every field's coverage.
- One async request context shares the in-memory browser session. A global adaptive request-start gate, a separate in-flight cap, bounded retries, and cancellation on access blocking apply across workers. SQLite writes occur on one thread. Every completed profile is committed before the next worker operation.
- Supplementary header fields use a fixed observed subset of name, headline, photo URL, and cover-photo URL. Contacts still require their labelled field privacy policy; unlabelled base contact values are not copied by fast mode. The report explicitly marks this field-coverage compromise. THINKING.md is unchanged.
- Fast runs use separate state under `output/fast-full/` and preserve the existing browser sample. They enumerate first, collect, then reconcile. Last-activity sorting and listing-scope semantics remain unresolved completeness limitations.
- The configurable ceiling can reach 20 requests/second, starting from 1 and increasing gradually. That value is not a claimed server-supported rate. Live compatibility and elapsed time remain unverified until the author's next attended run.
- Added a bounded probe of the observed `per_page` parameter at 100 records. Fast mode only adopts it if the returned size, unique IDs, reference membership, and total agree. Silent server caps fall back to the original size. The chosen pagination URL is retained across resume; no larger live page has been verified yet.
- Verification: the 90-test suite passed, followed by two additional full-scope checks for changed membership and resuming after authentication failure. Ruff and whitespace checks passed. A real Playwright async transport check used a loopback-only server with invented cookies and headers; no live TigerNet speed result is claimed. Its initial synthetic cookie omitted required storage-state fields; correcting the fixture to the actual Playwright schema resolved that test failure.

### Known-field coverage and readable export revision

- The author supplied 39 fields that must be checked at minimum and reported that the generic Education and Experience cells were unsatisfactory. These names now form a stable readable-output contract, while extraction remains label-driven and accepts additional fields.
- Employment, education, contact, social, address, and community structures are promoted into their named columns. `Record N` prefixes align values from the same repeated source record across columns. Unexpected native, custom, employer, institution, and community attributes become additional columns. The raw companion remains unchanged and lossless.
- Offline regeneration of the 15-profile sample produced 15 rows and 68 unique columns. The 39 required columns appear first. Thirty-seven required fields have at least one accessible value in the sample. `Family Name (if different from current name)` and `Marital Status` have no accessible sample value; the inspected schema marked those entries restricted, so their columns remain blank rather than exporting restricted backend values.
- The report now contains `known_field_coverage`, including the required columns, per-field profiles-with-values counts, and fields without values. This distinguishes checking for a field from actually observing an accessible value. No new authenticated collection was required for this export-only change, and THINKING.md remains unchanged.

### Higher adaptive starting rate

- The author requested starting at 20 requests/second and scaling upward when no problems occur. The initial fast-rate version defaulted to 20/s with 32 in-flight request slots and a 40/s ceiling.
- At that checkpoint, the global gate increased by 2/s after 2,000 consecutive successful responses. A transient network or server failure reset that streak and reduced the rate by 20 percent. HTTP 429 halved the rate and applied the shared cooldown. The configurable hard maximum was 50/s.
- These are client-side limits, not evidence of a supported TigerNet rate. The first live run must establish actual throughput and throttling behavior. Checkpointing and explicit partial reports remain unchanged.

### Fast startup failure and route correction

- The first full fast run stopped before discovery with `unrecognized_profile`. Its local report contained zero discovered and completed profiles, so the adaptive request-rate collection had not begun.
- Review found that body and community request templates replaced both numeric user path segments. The first segment identifies the signed-in viewer; only the second identifies the target profile. The template now preserves the observed viewer ID.
- An incompatible startup profile is now skipped while the remainder of the first listing page is tried. Direct/browser differences and individual extraction failures are recorded locally and produce a partial report, while collection continues. Authentication denial, persistent throttling, and an unusable request shape still stop because continuing cannot produce authorized records.

### First full-run extraction benchmark

- Discovery reached 131,890 unique accessible IDs against a displayed total of 131,892. Extraction then produced an initial group of completed profiles but appeared idle while 32 profile workers each queued five requests behind 32 request slots.
- The live aggregate showed 155 HTTP 429 responses. The prior controller halved the rate for every concurrent 429 in the burst, reducing 20/s to the 0.25/s floor. At that rate, five base requests for each remaining profile would take about 30 days before retries or additional community pages.
- The controller now applies at most one multiplicative reduction per fixed 30-second throttling epoch. Later 429s extend the shared cooldown without rolling that reduction window forward. Request/body operations and response cleanup add caller-side timeouts, while Playwright's driver remains the transport boundary. Profile concurrency is derived from the five-request fanout, and an independent heartbeat exposes retry progress.
- The evidence-based restart begins at 2/s and adds 2/s after every 100 clean responses, up to 40/s. This replaces the rejected 20/s starting assumption while allowing rapid measured recovery toward a rate TigerNet accepts.
- Multiple scraper processes were rejected at this checkpoint. They would contend for the same observed service limit, require multiple authenticated sessions, and cannot safely write the same SQLite queue. True sharding would require a frozen ID manifest, isolated shard databases, a shared aggregate rate budget, and a verified merge.
