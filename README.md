# TigerNet directory scraper

A Python application for resumable, permitted directory collection and validated UTF-8 CSV export. The repository keeps the assessment's original TigerBook name; the author confirmed **https://tigernet.princeton.edu/** as the target and confirmed bulk collection and sharing permission.

**Status: core implementation and synthetic tests are available. Live collection is blocked on credential configuration and authenticated site inspection.** There is no verified production directory adapter, live CSV, or Google Sheet yet. Passing synthetic tests do not prove unattended TigerNet authentication or exhaustive coverage.

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

Set both `TIGERNET_USERNAME` and `TIGERNET_PASSWORD` in the process environment using local credential tooling. Alternatively, create the ignored `credentials.local.json` in the repository root and edit it locally:

```json
{"username": "", "password": ""}
```

Both environment variables take precedence when present. A partially configured environment is an error. Never put real values in commands saved to shell history, Git, screenshots, or AI prompts. Restrict the local file to your OS account, for example with `chmod 600 credentials.local.json` on macOS/Linux.

The next available live command is:

```bash
python -m tigerbook_scraper --inspect
```

It starts a fresh browser context, drives the observed CAS form, and saves a small **private** inspection under `output/inspection/`. A directory link alone is not proof of authenticated access. Inspect protected content to establish the actual listing, profile structures, session behavior, and scope before implementing the final site contract. Inspection files can contain personal data or sensitive page state; keep them local.

Human MFA, passkey, or security-key challenges cause an explicit blocker. The application does not bypass them, use pasted cookies, or reuse a saved browser session. An interactive login would still leave the assessment's unattended requirement unmet.

See [site integration](docs/SITE-INTEGRATION.md) for the remaining work. Once that integration is verified, `--check-auth` checks a fresh session against a directory listing and an accessible profile. It currently requires the missing verified contract.

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

`--output-dir` selects a separate run root. Use a directory outside the checkout, or inside an ignored directory. `--credentials-file` selects a private credential file. `--site-contract` selects reviewed parser configuration; the eventual default is `src/tigerbook_scraper/site_contract.json`, which does not exist yet.

The full run uses `output/full/`; each limit uses `output/sample-N/`. A run cannot be reused with a different account, target, scope, limit, or parser contract. Choose a new output directory for a new collection. An OS lock prevents two writers from sharing a run. Interrupt with Ctrl+C, then restart the same command. Resumed runs authenticate in a new browser context. Failed profiles are retried on restart; completed profiles are retained.

Exit codes: `0` means a validated complete collection or successful requested diagnostic; `2` means a valid but partial export; `3` means a blocker; `130` means interruption. Read `report.json` rather than relying on process termination as proof of completeness.

## Persistence, retries, and fields

The pipeline is authentication → discovery → SQLite work queue → fetching/extraction → reconciliation → CSV validation. Discovered IDs and the page checkpoint commit together. Profiles use stable source IDs, never names. Records are updated by ID; failed retrievals remain distinct from absent fields.

Collection is sequential. Explicit data fetches and browser navigations are paced at one per second. Transient network errors, HTTP 429, and server errors receive up to four attempts with increasing delays and jitter. `Retry-After` is honored; waits above five minutes stop the run for later resumption. HTTP 403 and persistent rate limiting stop collection. Each expired-session operation allows one supported reauthentication. Structured responses are disposed after parsing.

Browser-generated background requests need inspection before claiming a site-wide request rate. If they produce additional directory/profile calls, the final adapter must pace those too. Check this and stricter service limits before a full run.

Field names come from the observed profile object or recognized section/label/value structures. There is no fixed profile-field list. Section/label separators are escaped; original labels are retained. Repeated and nested values use JSON inside CSV cells. Links and image URLs inside recognized fields are preserved. Unknown structures raise an extraction problem. Private or inaccessible fields are outside scope.

## Export and evidence

Each run directory contains:

- `run.sqlite`: durable IDs, URLs, attempts, outcomes, fields, and checkpoints.
- `profiles.csv`: deterministic columns and rows, one row per successfully extracted ID.
- `report.json`: status, unresolved counts, source totals, audits, timing, CSV hash, import cautions, and partial-run reasons.

CSV headers include `profile_id`, `profile_url`, and the sorted union of discovered field keys prefixed with `field/`. Missing values produce empty cells. CSV escaping preserves Unicode, commas, quotes, and multiline text. The exporter streams records and verifies every exported cell against SQLite before replacing the CSV atomically.

A complete report requires finished discovery and reconciliation, enumeration evidence, matching accessible totals when available, consistent ID membership, no unresolved profiles, and field-coverage evidence plus sample checks. Limited runs are always partial. Empty populations require review. The observation of 131,892 members is a reference only; it is not an expected count in code.

Coverage spans a collection window, not an atomic source snapshot. Membership changes produce a partial report. Sampling checks fidelity but does not prove enumeration. Repeating a parser is also insufficient: the site contract must reference independent profile-coverage inspection. Expired pagination cursors or changed parser contracts may require a new run after investigation.

## Google Sheets and submission

Upload the CSV manually to an approved destination. Google Sheets permits [up to 10 million cells or 18,278 columns](https://support.google.com/drive/answer/37603). The report includes required cells, columns, maximum cell length, and cells resembling formulas or numbers. Check current service limits before import. If the dataset does not fit, agree on an alternative instead of truncating it.

Preserve values as text during import, including disabling conversion to numbers, dates, or formulas when offered. CSV quoting alone does not prevent formula evaluation or numeric conversion. Verify leading zeros, `+` prefixes, formula-like strings, dates, Unicode, and multiline values. Keep the CSV and database as the source of truth. The report leaves `manual_sheet_import_verified` false; a human must document import/sharing checks and provide the actual Sheet link.

## Development and remaining acceptance work

```bash
python -m pytest
ruff check .
ruff format --check .
git diff --check
```

Tests use invented profiles and intercepted traffic, with an unusable proxy preventing browser tests from reaching real services. See [test coverage](tests/README.md). No Princeton credentials are needed.

Remaining live acceptance steps:

1. Configure credentials and establish supported unattended login.
2. Inspect permitted responses and implement the verified contract or necessary site-specific adapter changes.
3. Validate a small authenticated export, compare varied profiles, and rehearse interruption/resume.
4. Measure requests and elapsed time, estimate collection duration, then run the permitted collection.
5. Audit coverage and field fidelity; rehearse installation plus fresh authentication from a new checkout.
6. Manually import and verify the Sheet; provide verified repository and Sheet links.

[THINKING.md](THINKING.md) is reserved for the author's direct thoughts. [The experiment log](docs/EXPERIMENTS.md) records factual experiments and AI assistance. Credentials, sessions, confidential assessments, local knowledge bases, real fixtures, databases, exports, and inspection files must remain outside the public repository. Review staged contents before every push; ignore rules alone do not guarantee privacy.
