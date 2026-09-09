# Engineering thinking and AI collaboration

## Status and authorship

Started 2026-09-09. These initial notes were drafted with Codex from a strategy discussion, then added to the repository at the author's request. They are a starting record of proposed decisions, not a claim that the author independently reached every conclusion or that the proposed design has been validated.

No live TigerBook authentication, profile discovery, extraction, recovery test, or export has been performed during this setup. The implementation language and dependencies have not been finalized. Future entries should replace assumptions with evidence and preserve the actual sequence of decisions.

Confidential source documents and real personal data are not part of this public record.

## 1. Problem decomposition

The project depends on six questions, in this order:

1. **Scope:** What is the exact current service, which data can be collected, and who may receive it?
2. **Authentication:** Can a fresh process obtain and renew access through supported methods without human interaction?
3. **Discovery:** Is there an exhaustive listing or another demonstrably complete way to enumerate the permitted profiles?
4. **Extraction:** Which source representation exposes all permitted profile fields, including fields that vary by profile?
5. **Resilience:** How can failures and interruptions be recovered without lost or duplicate work?
6. **Validation:** What evidence distinguishes a finished process from a complete and accurate export?

The intended collection behavior includes dynamic fields, one row per profile, consistent UTF-8 CSV columns, rate control, retries, and durable progress. These are project objectives, not observations of how TigerBook works.

### Unknowns that matter most

- The exact current target URL and eligible population.
- Whether fresh authentication requires human MFA approval.
- Whether every permitted profile can be enumerated, rather than only found through capped searches.
- Whether HTML, rendered content, or a permitted API contains the full field set.
- Stable identifiers, session renewal, ordering guarantees, and source counts.
- Explicit permission for bulk collection and sharing with the intended recipients.

## 2. Approach exploration

An API is a data source, while HTTP and browser automation are interaction methods. These choices can overlap.

| Approach | Why consider it | Evidence needed | Likely failure or maintenance cost |
| --- | --- | --- | --- |
| Direct HTTP and HTML parsing | Low overhead and straightforward retries. | Supported unattended authentication and complete content in server responses. | Complex login state, JavaScript-only data, and HTML changes. |
| Browser automation | Follows observable page behavior and handles rendering. | Permitted automation, unattended authentication, exhaustive navigation, and acceptable runtime. | Selectors, synchronization, browser installation, and slower collection. |
| Permitted API | Structured fields and potentially clearer identifiers and pagination. | Current permission, equivalent population and fields, supported authentication, and acceptable freshness. | Incomplete summaries, stale data, access delays, or undocumented interface changes. |
| Hybrid | Browser authentication with HTTP/API collection where verified. | Session sharing and matching field coverage. | Additional session/token coordination and inconsistent extraction paths. |

### Provisional starting approach

Use a small browser-based discovery and authentication prototype first. If fresh authentication works and ordinary structured requests contain complete permitted records, use a hybrid. If direct HTTP works cleanly, simplify to it. Keep browser extraction only where the observed content requires it.

This is a recommendation from the planning conversation. It is not a final implementation choice.

### Switch conditions

- Prefer direct HTTP when both authentication and complete extraction are proven without browser-only behavior.
- Prefer a permitted API when population, fields, freshness, and authentication satisfy the project scope.
- Retain browser collection if rendering is necessary and the measured runtime is acceptable.
- Revisit the discovery strategy if queries are capped, continuation is unstable, or the source provides no evidence of exhaustive coverage.
- Treat required human MFA as a requirement blocker unless the responsible operator provides an approved alternative. A cached session does not prove fresh unattended authentication.

## 3. Technical tradeoffs

### Coverage confidence versus collection simplicity

Faster HTTP or API requests are useful only if they preserve the same permitted population and fields. Compare representations before optimizing throughput. A successful response does not establish a successful extraction.

### Dynamic fields versus arbitrary page changes

Avoid a fixed field allowlist. Discover keys within recognized profile structures and preserve section context, repeated values, and original labels. Generic field discovery still requires site-specific structure recognition. An unfamiliar layout should produce an explicit warning, not silent omissions.

### Durable state versus direct CSV streaming

Propose storing profile records and progress locally, then generating the CSV from the union of field keys. This adds state management but prevents late-discovered fields from being dropped and makes resume behavior easier to reason about. SQLite is a candidate, not a committed dependency decision.

### Conservative collection versus concurrency

Start sequentially with a conservative request rate. Measure runtime before adding concurrency. Retry transient failures with bounded delays, but distinguish permission failures, authentication challenges, and malformed profiles from ordinary network errors.

### Completion versus evidence of completeness

Track discovered IDs, successfully extracted IDs, failed outcomes, and exported IDs separately. Compare identifiers as well as counts. Do not hide a failed profile behind a row of empty values. If the source has no exhaustive enumeration mechanism, state that limitation instead of claiming full coverage.

## 4. Public-source findings and limits

The initial Codex discussion consulted the following public documentation on 2026-09-09:

- [Princeton sign-in announcement](https://oit.princeton.edu/news/new-sign-experience): many applications changed sign-in experience in August 2026. This does not establish TigerBook's current flow.
- [Princeton two-factor authentication guidance](https://princeton.service-now.com/service?id=kb_article&sys_id=13fd70e4976e4750115171611153af51): CAS applications use Duo. The actual account and application challenge still needs observation.
- [TigerApps resources](https://tigerapps.org/resources/): a TigerBook API is documented. Its current availability, permission, population, and complete field coverage remain unverified. No existing TigerBook scraper was used as a starting point.
- [Playwright request-context documentation](https://playwright.dev/docs/api/class-apirequestcontext): browser-associated requests can share browser cookies. This supports a possible hybrid design, but does not prove TigerBook session compatibility.
- [Princeton directory-use guidance](https://itpolicy.princeton.edu/guidelines): restrictions on directory database creation raise a material scope question. Confirm the applicable permission with the responsible data owner before collection and external sharing.

These findings are dated research notes. Recheck relevant documentation and actual permitted site behavior before implementation. Do not infer additional authorization from an API response or from possession of a login.

## 5. Experiments, obstacles, and decisions

The first planned technical experiment is a fresh automated login with no manual MFA action, after confirming the target and permitted scope. If it cannot complete, record the challenge and seek a supported arrangement rather than treating a remembered session as a solution.

The second critical experiment is proving exhaustive profile discovery. Scraping a few profiles successfully does not resolve that problem.

See [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for the two-hour discovery plan and the evidence template. All live experiments are currently marked planned. There are no observed TigerBook failures or fixes to report yet.

### Actual decisions made during repository setup

- Create a dedicated public project folder instead of publishing the existing local reference library, which contains confidential materials and unrelated sources.
- Include documentation and a source/test layout without presenting placeholder files as a working scraper.
- Add ignore rules before the first commit to exclude credentials, session state, local data, exports, and source documents.
- Start with an honest initial commit. Do not manufacture earlier experiments, backdate commits, or claim that future tests have already passed.

## 6. AI collaboration record

### 2026-09-09: strategy exploration

- **Tool:** OpenAI Codex desktop assistant.
- **Human request, summarized:** Read the supplied brief, compare HTTP, browser, API, and hybrid strategies, prioritize discovery experiments, challenge assumptions, and stay at strategy level before implementation.
- **Useful prompt constraints:** Separate requirements from observed behavior; avoid invented endpoints; make recommendations conditional on evidence; address MFA, permitted scope, resumability, dynamic fields, and completeness.
- **AI contribution:** Read the brief, compare alternatives, consult public documentation, identify authentication and enumeration as early risks, and propose a local architecture and validation plan.
- **Verification performed:** Document reading and public-source research. No live TigerBook behavior was verified.
- **What remains provisional:** Runtime, authentication method, extraction source, identifiers, pagination, state implementation, and the ability to prove full coverage.
- **Human override or failed prompt:** None documented yet. Do not invent one for this section.

### 2026-09-09: repository scaffold

- **Tool:** OpenAI Codex desktop assistant.
- **Human request, summarized:** Create a GitHub repository containing the required project files, including THINKING.md.
- **AI contribution:** Prepare the initial README, thinking record, discovery log, ignore rules, placeholder manifest, and source/test documentation.
- **Checks performed:** Verified the seven-file publication list, UTF-8 decoding, eight local documentation links, whitespace, absence of local filesystem paths, and common credential patterns. Checked that 23 representative credential/data/artifact paths are ignored and that the intended files are publishable. Reviewed the staged diff and ran `git diff --cached --check`. These are scaffold checks, not application tests.
- **Boundary:** Repository setup is distinct from implementing authentication, collecting profiles, or producing an export.
- **Follow-up:** Record actual implementation prompts, accepted and rejected suggestions, check results, and observed failures as development proceeds. Avoid copying raw prompts containing confidential documents, credentials, or personal data into this public log.

## 7. Seven-day working plan

| Day | Intended checkpoint |
| --- | --- |
| 1 | Resolve target and permission questions; test fresh authentication, source representations, and enumeration; select an approach. |
| 2 | Implement a small end-to-end slice through local persistence and CSV generation. |
| 3 | Add resume behavior, deduplication, throttling, retry classification, and synthetic failure tests. |
| 4 | Begin the first permitted full run and measure runtime and coverage. |
| 5 | Audit gaps and field fidelity; test interrupted recovery; fix and rerun affected work. |
| 6 | Rehearse clean installation and a fresh session; validate manual Sheets import; finish operator documentation. |
| 7 | Reserve time for final fixes, verification, repository review, and authorized delivery. |

Update this plan when evidence changes the critical path. Commit coherent increments with accurate messages and review staged content. Keep raw experiment notes as work happens, then edit the narrative for clarity without inventing a cleaner history.
