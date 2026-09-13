# Source layout

| Module | Responsibility |
| --- | --- |
| `__main__.py`, `config.py`, `locking.py` | CLI, credentials, isolated scopes, single-writer lock, safe reporting. |
| `auth.py` | Observed CAS form, submission-origin checks, challenges, SSO renewal. |
| `inspection.py` | Bounded private capture for authenticated site discovery. |
| `adapter.py` | Structured/rendered listing and profile parsing. Production contract remains missing. |
| `fetch.py` | Pacing, bounded retries, Retry-After, session-loss detection, response disposal. |
| `runner.py` | Discovery/reconciliation, profile processing, audits, progress and timing. |
| `state.py`, `models.py` | Transactional SQLite queue, identity, IDs, attempts, outcomes and records. |
| `fields.py` | Dynamic keys, repeated/nested values, CSV cell encoding. |
| `export.py` | Field union, deterministic CSV, streaming readback, atomic replacement, coverage report. |
| `errors.py` | Categorical errors that avoid exposing secrets or personal data. |

The pipeline is authentication → discovery → durable queue → extraction → reconciliation → validated export. SQLite stores source records before export so late fields can appear in a consistent schema.

Site integration remains blocked on authenticated observations. Generic adapters and synthetic tests exist; live compatibility is not established. See [the integration checkpoint](../docs/SITE-INTEGRATION.md).
