# TigerNet Directory Scraper

A resumable Python scraper for authorized collection from Princeton TigerNet. The project keeps
the assessment's original TigerBook name, but the verified target is
`https://tigernet.princeton.edu/`.

The scraper discovers profiles, collects permitted fields dynamically, saves progress in SQLite,
and creates validated UTF-8 CSV files. Credentials, cookies, student data, databases, and exports
are excluded from Git.

## Current status

The biggest problem is TigerNet's request limiting. Higher rates, extra browser sessions, and raw
HTML did not produce a faster complete-record method. The latest benchmark completed 1,846
profiles in 3,309 seconds, or about 0.56 profiles per second.

At that measured rate, scraping multiple fields from roughly 131,000 profiles is possible in about
65 hours. This is an estimate, not a guarantee. Duo approvals, server cooldowns, interruptions,
failed profiles, and final reconciliation can increase the total time.

The scraper handles this with throttling, automatic rate adjustment, retries, cooldowns, dynamic
field extraction, and resumable state. The full export is not complete until both discovery passes
agree and every profile has either completed or been resolved.

## Requirements

- Python 3.11 or newer
- Google Chrome or Playwright Chromium
- An account authorized to access TigerNet
- Manual Duo approval when requested

## Install

```bash
git clone https://github.com/siamh11373/tigerbook-scraper.git
cd tigerbook-scraper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Run

The recommended full run is:

```bash
python -m tigerbook_scraper.local_env --fast --allow-interactive
```

The command securely prompts for a NetID and password, opens a browser for Duo when needed, and
resumes the saved full run. Credentials remain in the local process and are not written to Git.

Keep the computer awake and the terminal open. Press `Ctrl+C` to stop safely. Run the same command
again to resume without refetching completed profiles.

### Other commands

```bash
# Small attended sample
python -m tigerbook_scraper.local_env --limit 15 --allow-interactive

# Standard sequential collection
python -m tigerbook_scraper

# Rebuild the full CSV from saved data
python -m tigerbook_scraper --fast --export-only

# Check authentication
python -m tigerbook_scraper --check-auth --allow-interactive

# Show all options
python -m tigerbook_scraper --help
```

## How collection works

1. Authenticate through Princeton CAS and Duo.
2. Discover stable profile IDs from the directory.
3. Save IDs and progress in SQLite.
4. Collect each profile's permitted fields.
5. Add new field labels dynamically instead of relying on a fixed schema.
6. Repeat discovery and reconcile the final population.
7. Validate and export the CSV.

Fast mode begins conservatively and adjusts its request rate using live responses. A transient
failure lowers the rate. HTTP 429 triggers a shared cooldown and slower recovery. Persistent
throttling or HTTP 403 stops the run so it can resume later instead of producing unreliable data.

The known field list controls column order only. It does not limit collection. New permitted
fields are added automatically, including repeated employment, education, contact, social, and
community fields.

## Outputs

The full fast run uses:

```text
output/fast-full/run.sqlite
output/fast-full/profiles.csv
output/fast-full/profiles.raw.csv
output/fast-full/report.json
```

- `run.sqlite` stores resumable progress.
- `profiles.csv` is spreadsheet-safe.
- `profiles.raw.csv` preserves exact extracted values.
- `report.json` records counts, validation, failures, and completion status.

All output files are ignored by Git.

## Completion and exit codes

A run is complete only when discovery and reconciliation finish, both passes agree, accessible
totals match, field checks pass, and no profile remains unresolved.

- `0`: validated complete run or successful diagnostic
- `2`: valid but partial output
- `3`: authentication, access, or configuration blocker
- `130`: interrupted

The observed population is 131,892 members, but it is a reference value rather than a hardcoded
expected count.

## Google Sheets

The final width may exceed Google Sheets' 10-million-cell limit. If it does, keep the complete CSV
and split the data across linked Sheets instead of dropping profiles or fields.

## Tests

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

See [THINKING.md](THINKING.md) for the main decisions, experiments, and limitations.
