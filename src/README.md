# Proposed source responsibilities

No scraper modules exist yet. Keep the eventual implementation small and separate these responsibilities where useful:

| Component | Responsibility |
| --- | --- |
| Command/configuration | Validate inputs, initialize the run, and report an accurate exit status. |
| Authentication | Establish and renew an authorized session; distinguish an interactive challenge from success. |
| Discovery | Follow observed, permitted listing mechanisms; persist unique profile IDs and pagination progress. |
| Fetching | Apply rate limits, timeouts, bounded retries, and response validation. |
| Extraction | Capture discovered fields from recognized profile structures without a fixed field allowlist. |
| State | Persist work status and records; make retries and restart processing safe. |
| Validation/export | Reconcile IDs and outcomes, assemble the union of fields, and write the CSV and coverage report. |

## Data flow

Configuration → authentication → profile discovery → durable queue → fetching → extraction → stored records → validation → CSV and run report.

Discovery and profile processing both checkpoint progress. A page's discovered IDs must be stored before, or atomically with, advancing its discovery checkpoint.

## Provisional data decisions

- Prefer a verified stable source identifier; otherwise investigate canonical profile URLs. Do not deduplicate by name.
- Store variable profile fields as a map, preserving original labels and enough section context to avoid collisions.
- Distinguish an absent value from a fetch or parsing failure.
- Preserve repeated values with a reversible encoding.
- Generate headers from the union of successfully extracted fields after collection.
- Consider local SQLite for durable state if the selected runtime supports it simply.
- Start with sequential, conservatively throttled work. Add concurrency only if evidence justifies it.
- Treat unfinished profiles and discovery failures as a partial run, not a complete export.

These decisions remain subject to observations recorded in [THINKING.md](../THINKING.md) and the [discovery log](../docs/EXPERIMENTS.md).
