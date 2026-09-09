# Validation plan

No application tests have been implemented or run. This file records planned checks, not passing results.

Use synthetic fixtures for public tests. Do not commit real profiles, copied personal details, credentials, cookies, or unsanitized network recordings.

## Planned cases

| Area | Cases to verify |
| --- | --- |
| Authentication | Fresh unattended session; redirect to login disguised as a successful response; required human challenge; session loss. |
| Discovery | Multiple pages; overlapping results; repeated continuation tokens; missing or expired cursors; capped results. |
| Identity | Same ID encountered twice; two people with the same display name; missing stable identifier. |
| Fields | New field appearing late; missing field; duplicate labels in separate sections; repeated values; unrecognized profile structure. |
| CSV | Unicode; commas; quotes; embedded newlines; empty values; deterministic headers and row identity. |
| Recovery | Timeout; rate-limit response; bounded retry exhaustion; interruption around a checkpoint; restart without missing or duplicate records. |
| Coverage | Discovered IDs reconciled with stored and exported IDs; unresolved records force partial status. |

## Acceptance evidence

1. A clean installation follows the README successfully.
2. A fresh session establishes access without human intervention through a supported method.
3. Discovery exhausts the agreed scope using verified source behavior.
4. Every discovered profile has an explicit outcome, with unresolved work reported.
5. The export contains unique IDs and all captured field keys.
6. A varied sample agrees with the permitted source representation.
7. An interrupted synthetic run and an uninterrupted run produce equivalent records.
8. A manual Google Sheets import preserves the values, including text that could be interpreted as formulas, dates, or numbers.

Live validation depends on permission and an eligible account. Simulate failures locally instead of deliberately triggering production throttling or account lockouts.

Add exact test, lint, formatting, and type-check commands here and in the README when the runtime and implementation are selected.
