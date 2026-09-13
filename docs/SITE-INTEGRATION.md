# Authenticated integration checkpoint

The public CAS form is observed. Authenticated directory structures are not. There is no `site_contract.json`, and collection stops explicitly. This is unfinished site integration, not a supported production adapter hidden behind optional setup.

## Next experiment

After credentials are configured locally, run `python -m tigerbook_scraper --inspect`. It attempts CAS in a fresh browser context. If human MFA is required, record the unresolved unattended requirement and stop that attempt. A cached session cannot resolve it.

If login reaches the directory, inspect protected content and a small, varied profile sample. Establish stable IDs/URLs, permitted visibility, pagination/caps, the meaning of totals, tabs or expandable sections, and requests per profile. Compare ordinary structured responses with fully rendered profiles.

## Current adapter capabilities

The contract describes observed structures, not a field list. It requires the target, mode, and sanitized observation evidence. A true `exhaustive` flag requires `enumeration_evidence`; `field_coverage_evidence` references independent inspection of permitted field coverage.

- DOM mode supports profile cards, canonical links, a count-only total, and next-page links. It extracts visible sections with heading and label/value rows. Selectors belong to an observed contract, never a guessed default.
- JSON mode supports an observed GET listing with IDs and profile URLs, a next URL or null, and a total. It extracts the permitted profile object at an observed object path, preserving its keys and nested values.
- The current JSON adapter expects a discovered profile URL to return JSON and support a rendered fidelity comparison. Sites often use separate API/display URLs and different label keys. If TigerNet does, implement the observed mapping and comparison before selecting JSON mode. Do not guess URL templates or bypass audits.
- Other pagination, separate API/display URLs, tabs, unlabeled profile elements, and repeated DOM record groups require site-specific implementation and tests after observation. The generic DOM row parser does not establish coverage of those layouts.

Paths and selectors in `tests/test_adapter.py` are invented fixtures. They are not evidence of TigerNet interfaces and must not become a production contract.

Keep any final contract free of personal data, tokens, tickets, signed URLs, and secrets. Raw inspections stay local. Package a reviewed production contract and necessary parser changes only after observations exist. Then rehearse fresh login, a small export, independent comparisons, and interruption/resume before full collection.
