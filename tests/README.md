# Validation

```bash
python -m pytest
ruff check .
ruff format --check .
git diff --check
```

Install Chromium with `python -m playwright install chromium`. Tests use invented records and intercepted browser responses. An unusable local proxy prevents accidental unmocked browser traffic from reaching real services.

| Tests | Evidence |
| --- | --- |
| `test_auth.py` | CAS form and hidden fields, challenges, rejection, unexpected submission origin, SSO renewal. |
| `test_fetch.py` | Login disguised as HTTP 200, bounded renewal/retries, Retry-After, failures, disposal, redirects and origin restrictions. |
| `test_adapter.py` | Invented DOM/JSON listings, URL identity, pagination, dynamic fields, links/photos, repeated/nested values, structure failure and missing contract. |
| `test_core.py` | Credential privacy, scope mismatch, overlapping pages, loop/stall detection, crash rollback, pending batches, dynamic union, Unicode/large cells, partial reporting. |
| `test_runner.py` | Equivalent resumed/uninterrupted records, completed profiles retained, sample limits, failed-profile retry and auth blockers. |
| `test_cli.py` | Help, missing credentials, offline export without browser imports, single-writer lock. |

These checks do not establish TigerNet authentication, field coverage, exhaustive enumeration, live throughput, or a correct Google Sheets import.

Before a full run, perform a small authenticated export and interruption/resume rehearsal. Afterward, reconcile ID sets/totals for the same scope, independently review varied profiles, and verify manual import. Record actual results in `docs/EXPERIMENTS.md` without personal data or secrets.
