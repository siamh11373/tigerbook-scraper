# TigerNet directory scraper

A Python application for resumable, permitted directory collection and validated UTF-8 CSV export. The repository keeps the assessment's original TigerBook name; the author confirmed **https://tigernet.princeton.edu/** as the target and confirmed bulk collection and sharing permission.

**Status: the resumable full collection is running.** The latest measured extraction pace was about 0.56 profiles per second, giving a rough 65-hour collection window. TigerNet throttling prevents the tested client from sustaining a higher useful request rate. Field accuracy and coverage have been reviewed by the author. The full CSV remains incomplete until collection and reconciliation finish.

The public login flow was inspected in a fresh browser on September 13, 2026. It leads to Princeton CAS at `https://fed.princeton.edu/cas/login`. No authenticated directory or profile endpoint has been guessed. Collection requires a parser contract established from actual authenticated observations.

## Installation

Tested runtime: **Python 3.12.14**, macOS. The package requires Python 3.11 or newer; other versions and operating systems have not been rehearsed.

```bash
git clone https://github.com/siamh11373/tigerbook-scraper.git
cd tigerbook-scraper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Playwright is the only production dependency. SQLite and CSV handling use the standard library. pytest and Ruff are development dependencies. Direct dependency versions are pinned in `pyproject.toml`; `requirements.txt` installs the package and development extras. Editable installation makes `python -m tigerbook_scraper` available.

## Credentials and first live checkpoint

### Raw HTML feasibility probe

Run `python -u -m tigerbook_scraper.html_probe` from the repository root to test whether
one authenticated HTML response contains the values already captured for three saved
profiles (small, median, and large records). This uses `.env.local` or existing credential
configuration and requires one attended MFA login. It reads the full-run database in
read-only mode and writes an ignored report under `output/html-probe/`.

The probe checks text, link attributes, inline scripts, and standalone JSON script blocks.
It prints aggregate counts only. Missing values reject the current raw-HTML approach for
that reference; encoded JavaScript state and source changes may require further inspection.
Even a perfect value-presence match does not prove field labels, associations, permissions,
numeric values, or complete coverage. It never substitutes this diagnostic for collection.

For credentials held only in the running process, use this launcher from your terminal:

```bash
python -m tigerbook_scraper.local_env --inspect --allow-interactive
```

It prompts for your NetID and password with both inputs hidden, sets `TIGERNET_USERNAME` and `TIGERNET_PASSWORD` for the scraper process, and clears those assignments when the run ends. Values are not written to a file or entered as shell commands. Your parent shell is unchanged. Environment variables are not encrypted storage and can be accessible to processes with sufficient privileges. The launcher refuses noninteractive or echoed input.

For an attended run launched by another local process, create the ignored `.env.local` file in the repository root:

```dotenv
TIGERNET_USERNAME=
TIGERNET_PASSWORD=
```

The same launcher reads these two keys without executing the file as shell code and clears them from its process when the run ends. The file stores plaintext credentials on disk. Restrict it to your OS account with `chmod 600 .env.local`, keep it out of screenshots and AI prompts, and delete it when the collection is finished.

Replace `--inspect` with other scraper arguments when the site integration is ready. This is credential configuration, not a manual CAS login or an MFA workaround. Without `.env.local` or configured environment variables, a new invocation prompts again. For already configured environment variables, use the ordinary `python -m tigerbook_scraper` commands below.

The existing ignored JSON credential-file option is still supported, but it stores plaintext on disk. If you choose that option, create `credentials.local.json` locally:

```json
{"username": "", "password": ""}
```

Both environment variables take precedence when present. A partially configured environment is an error. Never put real values in commands saved to shell history, Git, screenshots, or AI prompts. Restrict the local file to your OS account, for example with `chmod 600 credentials.local.json` on macOS/Linux.

The next available live command is:

```bash
python -m tigerbook_scraper --inspect
```

It starts a fresh browser context, drives the observed CAS form, and saves a small **private** inspection under `output/inspection/`. The extended inspection follows the observed Next page button and up to three observed profile links, with per-stage timings and responses. Token-service JSON payloads are excluded. A directory link alone is not proof of authenticated access. Inspect protected content to establish the actual listing, profile structures, session behavior, and scope before implementing the final site contract. Inspection files can contain personal data or sensitive page state; keep them local.

With `--allow-interactive`, a visible browser waits up to five minutes for you to complete normal MFA approval, then continues automatically. The same option applies to session renewal. Without it, interactive challenges still stop the run. No MFA approval or verification code is automated, and no saved browser session is reused. The author has authorized attended authentication for this project; this is a deviation from the original assessment's unattended requirement, not evidence that unattended login works.

See [site integration](docs/SITE-INTEGRATION.md) for the observed integration and remaining checks. `--check-auth` checks a fresh session against a directory listing and an accessible profile. The sanitized parser contract is included as `site-contract.json`. Reviewers authenticate with their own authorized Princeton accounts; no author account information is required or included.

### Bounded performance comparison

`python -u -m tigerbook_scraper.performance_probe` uses one attended login and three
saved profiles to compare browser `fetch()` at concurrency 1 and 3 with request-context
fetches at concurrency 1. Each condition spaces starts by at least 0.5 seconds and runs
sequentially. Ordinary page loading establishes observed requests first. The probe stops
on blocked comparison responses, keeps bodies and authentication in memory, and writes
only diagnostic counts and schema keys to ignored `output/performance-probe/report.json`.
Embedded JSON/JavaScript decoding never executes extracted script text. Script keyword
hints and repeated values do not establish a batch interface or removable request.
The small benchmark does not establish sustained throughput or exhaustive field coverage.
Ordinary browser background traffic is not included in the timing counters, so the stated
pacing applies to the explicitly compared requests, not every request made by the browser.

## Operator commands

These interfaces are implemented. **Network collection requires the verified site contract described above.**

```bash
# Full scope, resuming the same unfinished run
python -m tigerbook_scraper

# At most 25 successful profiles, isolated from the full run
python -m tigerbook_scraper --limit 25

# Regenerate and validate the full-run export without network or credentials
python -m tigerbook_scraper --export-only

# Regenerate the isolated sample export offline
python -m tigerbook_scraper --limit 25 --export-only

python -m tigerbook_scraper --help
```

`--output-dir` selects a separate run root. Use a directory outside the checkout, or inside an ignored directory. `--credentials-file` selects a private credential file. `--site-contract` selects parser configuration; the default is the reviewed `site-contract.json` included in the repository. The contract contains parser structure and a listing URL only. It contains no credentials, cookies, profile records, or captured responses.

The next local validation command is `python -m tigerbook_scraper.local_env --limit 15 --allow-interactive`. It uses authenticated listing requests and captures the profile responses made by the normal browser UI, then follows observed community pagination. It produces an explicitly partial sample under `output/sample-15/`. Profile-data requests are paced, and values are extracted from field metadata rather than a fixed field list. Leave the browser open during collection. Restart the same command to resume an interrupted sample. A partial export exits with code 2; inspect the report to distinguish the intentional sample limit from unresolved failures.

The current listing sorts by last activity, and observed pages can overlap. The run deduplicates stable profile IDs and performs a second discovery pass before final reconciliation. Enumeration remains unproven until that pass finishes and its counts reconcile. The author recorded field-coverage verification in `field-validation.json`; direct responses must also match fresh browser reference profiles at startup. Self-only, admin-only, and otherwise restricted fields are omitted. Unusual privacy or section structures are recorded as profile failures so the remaining queue continues. Additional badge pages remain an explicit incomplete-profile result.

The full run uses `output/full/`; each limit uses `output/sample-N/`. A run cannot be reused with a different account, target, scope, limit, or parser contract. Choose a new output directory for a new collection. An OS lock prevents two writers from sharing a run. Interrupt with Ctrl+C, then restart the same command. Resumed runs authenticate in a new browser context. Failed profiles are retried on restart; completed profiles are retained.

Exit codes: `0` means a validated complete collection or successful requested diagnostic; `2` means a valid but partial export; `3` means a blocker; `130` means interruption. Read `report.json` rather than relying on process termination as proof of completeness.

## Faster request-based collection

### Installed Chrome collection

`python -m tigerbook_scraper.chrome` runs sequential profile navigation in installed Google
Chrome. It reads the existing local credential configuration and waits for human verification
or MFA when required. It resumes the existing `output/fast-full/` database after validating
account, target, scope, and parser contract. Previously completed records are preserved;
the report marks the collection as mixed fast/Chrome. No browser session is saved or exported.
Use `python -m tigerbook_scraper.chrome --limit 15` for a separate `chrome-sample-15` run.

The Chrome path defaults to one-request-per-second data/navigation pacing and retains dynamic field
parser. It does not promise a higher accepted service rate. On HTTP 429 it records the parsed
`Retry-After`, blanks the page to cancel background traffic, and pauses collection for at
least 300 seconds (600 on a second rejection). A third rejection stops with a saved deadline
of at least 1,200 seconds; a server instruction longer than one hour also stops for later
resume. A restart checks the saved deadline before login. HTTP 403 remains a blocking error.
Successful collection is still subject to the existing field-fidelity and coverage checks.

For a bounded pacing experiment, stop any active collector first, then run:

```bash
python -m tigerbook_scraper.chrome --request-rate 2 --benchmark 20
```

Use `--benchmark 100` for a longer test at the same rate.

This saves up to the selected number of additional completed profiles in the existing full-run database and
exports a partial result. It does not change account or collection identity. The same saved
cooldown applies across benchmark and normal runs. Pacing can be set to 1, 2, 3, or 6 with
`--request-rate`; 6 requires a 20-profile benchmark. Omit `--benchmark` to resume full
collection. Short benchmarks do not establish a sustainable service allowance. Default resume
uses one-request-per-second pacing; every rate retains the same cooldown safeguards.

### Direct requests

`--fast` still scrapes the directory. It uses normal browser authentication, captures the actual GET requests for up to three profiles, and compares direct responses against their rendered reference records before continuing. An incompatible startup profile is skipped while other results are tried. A comparison difference is recorded in the partial report instead of terminating collection. After startup, the browser closes and profile fetching uses concurrent requests. Credentials, session cookies, and observed authorization headers stay in process memory and are never written to Git, configuration, or run reports. If the session expires, normal browser authentication reopens; repeated renewal failures without collection progress stop the run.

```bash
# Full request-based collection: start at 2/s and scale to 6/s
python -m tigerbook_scraper.local_env --fast --allow-interactive

# Controlled two-session experiment; requires two MFA approvals
python -m tigerbook_scraper.local_env --fast --allow-interactive --browser-sessions 2

# Regenerate the fast full-run export offline
python -m tigerbook_scraper --fast --export-only
```

Fast mode starts at 2 requests/second. After each 100 consecutive successful responses it adds 2 requests/second, up to the default ceiling of 6. The ceiling follows live evidence from both one-session and two-session runs: 20/s caused a large 429 burst, while the two-session run processed cleanly through 6/s and triggered persistent throttling after reaching 8/s. Transient network or server failures reset the success streak and reduce the rate by 20 percent. HTTP 429 halves the rate and applies a global `Retry-After` cooldown. Concurrent 429 responses in the same 30-second cooldown epoch extend the pause without repeatedly halving the rate. Persistent throttling and HTTP 403 stop collection. All requests and workers share the same pacing gate. In-flight requests are capped independently by `--workers` (default and maximum 32); fast collection schedules roughly one profile worker per five request slots because each profile needs five base requests. Individual fetch and extraction failures are saved against their profile IDs while the remaining queue continues. These rates are operator limits based on limited live evidence, not a documented TigerNet service limit.

Use `--requests-per-second` to change the starting rate and `--max-requests-per-second` to change the ceiling. The implementation rejects a maximum above 50 requests/second and a starting rate above the maximum.

After a 429, the recovery gate drains admitted requests, observes the shared cooldown,
and permits only one recovery request. A successful recovery response reopens normal
paced admission; older in-flight successes cannot reopen it. Cancellation releases its
request lease so the queue does not deadlock.

Fast collection also saves successful base response sections in a new private SQLite
table, `profile_sections_v1`, within the existing run database. On an interrupted-profile
retry, it re-fetches base identity/privacy metadata and discards cached sections if that
response changed. Otherwise it fetches missing sections and applies normal field filtering
to the assembled record. The cache expires as a whole after one hour and is cleared after
successful record storage or an extraction error. Extra community pages are still fetched
normally. This reduces repeated work; it does not remove fields or reduce the five base
requests for a new profile. Cached field-level permissions can change independently of
base metadata, so this provides bounded staleness, not a source-consistent snapshot.

`--browser-sessions 2` authenticates two independent browser sessions sequentially, then assigns each numeric profile ID deterministically to one of two isolated request contexts. One process retains the run lock, discovery checkpoint, SQLite writer, deduplication, and final export. Both sessions share one adaptive request-rate controller, one worker limit, and one global cooldown: the configured rates and workers are totals, and a 429 from either session pauses both. Compare its measured throughput with a one-session run to see whether an additional authenticated session helps; that comparison cannot prove whether TigerNet limits by session, account, or IP. Either session may require renewed MFA. The maximum is two sessions until live evidence establishes session behavior.

Startup also tries 100 records with the observed `per_page` parameter. It only adopts that size if the response has the requested number of unique IDs, the same total, and includes the reference IDs; otherwise it keeps the original page size. The selected URL is saved locally and reused on resume. Discovery enumerates the observed listing before profile collection to shorten the exposure to last-activity ordering changes. After collection, a second pass discovers changed membership and collects newly discovered IDs. This does not prove exhaustive enumeration. Progress and an evolving time projection print about every ten seconds during active operations. The benchmark is also saved in SQLite. Keep the computer awake and Terminal open. Restart the same command to resume.

Fast output is isolated in `output/fast-full/`, or `output/fast-sample-N/` with `--limit N`. The prior browser sample is unchanged. Fast mode preserves metadata-labelled fields, repeated employment and education records, contact privacy controls, and paginated communities. Additional badge pages remain an explicit extraction failure. Supplementary header values are selected separately for every profile by comparing the permitted header response with the base response. This removes the fixed header-field subset. Contact values still require the labelled contact section and its field-level privacy metadata. A new header attribute is included without a code change when its permitted value is present in the header response.

## Persistence, retries, and fields

The pipeline is authentication → discovery → SQLite work queue → fetching/extraction → reconciliation → CSV validation. Discovered IDs and the page checkpoint commit together. Profiles use stable source IDs, never names. Records are updated by ID; failed retrievals remain distinct from absent fields. Fast requests add a caller-side timeout around the request and response-body transfer, plus a bounded cleanup timeout; Playwright's own timeout and driver lifecycle remain the underlying transport boundary. A ten-second heartbeat reports progress even while a worker batch is retrying.

The default browser mode is sequential. Explicit data fetches and browser navigations are paced at one per second. Fast mode uses the separate shared gate described above. Transient network errors, HTTP 429, and server errors receive up to four attempts with increasing delays and jitter. `Retry-After` is honored; waits above five minutes stop the run for later resumption. HTTP 403 and persistent rate limiting stop collection. Each expired-session operation allows one supported reauthentication. Structured responses are disposed after parsing.

Browser-generated background requests need inspection before claiming a site-wide request rate. If they produce additional directory/profile calls, the final adapter must pace those too. Check this and stricter service limits before a full run.

Field names come from the observed profile object or recognized section/label/value structures. There is no extraction allowlist. The 39 supplied names control readable column order and guarantee that those columns exist even when empty. They do not limit collection. Section and label separators are escaped; original labels are retained in SQLite and the raw export. The readable export formats repeated and nested values as labelled multiline text; the raw companion retains JSON inside cells. Links and image URLs inside recognized fields are preserved. Unknown structures record an extraction problem for that profile and collection continues. Private or inaccessible fields are outside scope.

## Export and evidence

Each run directory contains:

- `run.sqlite`: durable IDs, URLs, attempts, outcomes, fields, and checkpoints.
- `profiles.csv`: the 39 known assessment fields first, followed by every additional dynamically discovered field. Repeated job, education, and community values use aligned `Record N` lines. One row per successfully extracted ID. Enable **Wrap text**, freeze the header row, and adjust column widths in your spreadsheet; CSV cannot store widths, row heights, filters, or styling.
- `profiles.raw.csv`: the previous machine-readable format, with original field keys and reversible JSON for nested values. Use this file for downstream code that depended on the original CSV format.
- `report.json`: status, unresolved counts, source totals, audits, timing, CSV hash, import cautions, and partial-run reasons.

The readable file always includes the known minimum fields even when no accessible profile in the run has a value. This is a coverage contract, not an extraction allowlist. Employment records are promoted into Job Title, Employer, Employment Date, Field/Specialty, Position Level, and Work/Board/Military columns. Education records are promoted into Institution, Education Date, Degree Year, Degree, Major, and Academic Level. Social links, emails, addresses, and community names, locations, and member counts are consolidated into their requested columns with source labels retained inside cells. Unknown nested attributes receive additional columns instead of being dropped.

Both files use deterministic ordering and collision-safe headings. The raw headers include `profile_id`, `profile_url`, and original field keys prefixed with `field/`; nested values remain reversible JSON. Repeated records in the readable file retain their source record number across related columns. Missing or inaccessible values produce empty cells. CSV escaping preserves Unicode, commas, quotes, and multiline text. Each file is streamed, verified against its rendering of SQLite records, and replaced atomically. The report includes separate hashes and validation metrics for both files plus counts of profiles with values for each known field.

A complete report requires finished discovery and reconciliation, enumeration evidence, matching accessible totals when available, consistent ID membership, no unresolved profiles, and field-coverage evidence plus sample checks. Limited runs are always partial. Empty populations require review. The observation of 131,892 members is a reference only; it is not an expected count in code.

Coverage spans a collection window, not an atomic source snapshot. Membership changes produce a partial report. Sampling checks fidelity but does not prove enumeration. Repeating a parser is also insufficient: the site contract must reference independent profile-coverage inspection. Expired pagination cursors or changed parser contracts may require a new run after investigation.

## Google Sheets and submission

Upload the CSV manually to an approved destination. Google Sheets permits [up to 10 million cells or 18,278 columns](https://support.google.com/drive/answer/37603). The report includes required cells, columns, maximum cell length, and cells resembling formulas or numbers. At 131,890 rows, 76 columns would require 10,023,716 cells before tracker tabs, so the completed schema must be checked again. If it exceeds the limit, preserve the CSV and use linked partitioned Google Sheets instead of dropping fields or profiles.

The working [TigerNet Scraper Submission Tracker](https://docs.google.com/spreadsheets/d/1aGuCsbjIQW66mlWTE1Ti0UGoFPbIWmlibSR8rn6ueLk/edit) contains four tabs: run status, an import-ready profile header, field coverage, and final import checks. It contains no scraped profile rows. The final data and view permission remain pending until collection completes.

Preserve values as text during import, including disabling conversion to numbers, dates, or formulas when offered. CSV quoting alone does not prevent formula evaluation or numeric conversion. The readable file prefixes formula-like and leading-zero values with an apostrophe; some spreadsheet importers display that apostrophe literally. The raw file retains the original strings without that presentation change. Verify leading zeros, `+` prefixes, formula-like strings, dates, Unicode, and multiline values. Keep the raw CSV and database as the source of truth. The report leaves `manual_sheet_import_verified` false; a human must document import/sharing checks and provide the actual Sheet link.

## Development and remaining acceptance work

```bash
python -m pytest
ruff check .
ruff format --check .
git diff --check
```

Tests use invented profiles and intercepted traffic, with an unusable proxy preventing browser tests from reaching real services. See [test coverage](tests/README.md). No Princeton credentials are needed.

Remaining live acceptance steps:

1. Let the resumable full collection finish at the measured accepted pace.
2. Run the second discovery pass and reconcile discovered, completed, failed, and exported IDs.
3. Resolve or disclose remaining profile failures and regenerate the validated CSV.
4. Rehearse installation and attended authentication from a fresh checkout with a reviewer's own account.
5. Import the final data, update the tracker counts, verify values and sharing, and provide the final Sheet link.

## Architecture map

- `auth.py` and `local_env.py` drive fresh CAS login, local credential loading, and attended Duo handoff.
- `adapter.py` and `tigernet.py` load the observed contract and implement directory and profile access.
- `fast.py`, `chrome.py`, `fetch.py`, and `section_cache.py` handle collection, pacing, throttling, retries, and bounded response reuse.
- `tigernet_fields.py`, `fields.py`, and `presentation.py` perform dynamic extraction and readable field projection.
- `state.py` owns SQLite checkpoints, stable IDs, deduplication, attempts, and run identity.
- `export.py` produces the readable and raw UTF-8 CSVs plus the completion report.
- `runner.py` and `__main__.py` coordinate the single-command workflow and exit status.

[THINKING.md](THINKING.md) is reserved for the author's direct thoughts. [The experiment log](docs/EXPERIMENTS.md) records factual experiments and AI assistance. Credentials, sessions, confidential assessments, local knowledge bases, real fixtures, databases, exports, and inspection files must remain outside the public repository. Review staged contents before every push; ignore rules alone do not guarantee privacy.
