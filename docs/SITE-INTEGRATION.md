# Authenticated TigerNet integration

TigerNet uses Princeton CAS and requires Duo Push MFA in the observed login flow. The application enters the configured username and password programmatically, pauses for normal human approval, then verifies protected directory content. Fully unattended authentication was not possible in the observed supported flow. The author approved attended login and records this assessment deviation in `THINKING.md`.

Reviewers use their own authorized Princeton accounts. They configure credentials locally through the hidden launcher prompt, environment variables, `.env.local`, or the ignored credential file. The repository contains no author account information, saved session, cookie, MFA material, or profile record.

The sanitized `site-contract.json` contains the observed listing URL and parser mode. `field-validation.json` records the author's coverage review. Raw observations remain ignored because they can contain directory data and authenticated state.

The full run is underway in ignored SQLite state. Its last measured useful pace was about 0.56 completed profiles per second, producing a rough 65-hour collection estimate. Higher sustained request rates, additional browser sessions, raw HTML, and the observed multi-ID search candidate did not establish a faster complete-record path. TigerNet throttling remains the practical limit for the tested implementation.

## Current adapter capabilities

The contract describes observed structures, not a field list. It requires the target, mode, and sanitized observation evidence. A true `exhaustive` flag requires enumeration evidence. Field coverage requires separate author review plus fresh direct and browser comparison.

- TigerNet mode reads stable IDs from the observed structured listing, fetches the five observed profile response types, follows community pagination, and extracts section labels dynamically.
- Repeated employment and education records remain grouped. Header values are selected per profile from permitted header content, without a fixed key subset. Restricted and unfamiliar privacy structures are excluded or recorded for review.
- Profile-level incompatibilities remain durable failures while the queue continues. Authentication denial, persistent throttling, and an invalid request contract stop the run because further requests would not produce reliable authorized records.
- DOM and generic JSON modes remain tested alternatives for other observed contracts. Their synthetic selectors and paths are not evidence of TigerNet interfaces.

Before claiming completion, finish the second enumeration pass, reconcile every ID and outcome, regenerate the CSV, and check the final Google Sheets cell count. The working submission tracker contains no profile rows. Final sharing is deferred until the completed data has been imported and reviewed.
