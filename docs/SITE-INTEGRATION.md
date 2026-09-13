# Authenticated integration checkpoint

Attended login has now yielded two directory pages and three profile snapshots. A local `private/site-contract.json` records the observed listing URL. The TigerNet adapter is implemented and tested synthetically, but has not yet completed a live collection run. The contract and captured data remain local and are not distributed with the implementation.

The adapter reads directory IDs from the observed structured listing, opens each observed canonical profile route, and captures the normal profile JSON responses. It handles community pagination, section-labelled fields, nested education/employment records, and privacy exclusions. The original generic DOM/JSON adapters described below remain separate alternatives.

Outstanding issues include last-activity ordering (one duplicate across the first two pages), scope-filter semantics, independent field coverage, self-only fields, and additional badge pages. These prevent verified-complete reporting. The next checkpoint is a 15-profile attended run, not a full scrape.

## Next experiment

Run `python -m tigerbook_scraper.local_env --limit 15 --allow-interactive`. Enter credentials privately and approve normal MFA. Attended authentication is now authorized by the author, while the deviation from the original assessment remains documented.

If login reaches the directory, inspect protected content and a small, varied profile sample. Establish stable IDs/URLs, permitted visibility, pagination/caps, the meaning of totals, tabs or expandable sections, and requests per profile. Compare ordinary structured responses with fully rendered profiles.

## Current adapter capabilities

The contract describes observed structures, not a field list. It requires the target, mode, and sanitized observation evidence. A true `exhaustive` flag requires `enumeration_evidence`; `field_coverage_evidence` references independent inspection of permitted field coverage.

- DOM mode supports profile cards, canonical links, a count-only total, and next-page links. It extracts visible sections with heading and label/value rows. Selectors belong to an observed contract, never a guessed default.
- JSON mode supports an observed GET listing with IDs and profile URLs, a next URL or null, and a total. It extracts the permitted profile object at an observed object path, preserving its keys and nested values.
- The current JSON adapter expects a discovered profile URL to return JSON and support a rendered fidelity comparison. Sites often use separate API/display URLs and different label keys. If TigerNet does, implement the observed mapping and comparison before selecting JSON mode. Do not guess URL templates or bypass audits.
- Other pagination, separate API/display URLs, tabs, unlabeled profile elements, and repeated DOM record groups require site-specific implementation and tests after observation. The generic DOM row parser does not establish coverage of those layouts.

Paths and selectors in `tests/test_adapter.py` are invented fixtures. They are not evidence of TigerNet interfaces and must not become a production contract.

Keep any final contract free of personal data, tokens, tickets, signed URLs, and secrets. Raw inspections stay local. Package a reviewed production contract and necessary parser changes only after observations exist. Then rehearse fresh login, a small export, independent comparisons, and interruption/resume before full collection.
