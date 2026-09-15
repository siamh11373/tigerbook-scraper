## Problem decomposition

I split the project into authentication, discovery, extraction, recovery, and verification. The
main goal was not just to create a CSV, but to prove that it covered the directory and could resume
after interruptions.

TigerNet showed 131,892 members. Each profile can contain many fields, including employment,
education, contact information, social links, activities, and communities. The scraper therefore
needed dynamic field extraction instead of a fixed field list.

## Approach exploration

I tested browser collection, direct requests, multiple sessions, higher request rates, and raw
HTML. Raw HTML did not contain the full record. Extra sessions did not create a separate request
allowance. High request rates caused HTTP 429 responses and long cooldowns.

The best approach was to authenticate in a browser, verify the requests used by TigerNet, and then
collect through those observed requests. This avoids rendering every profile while keeping the
same authorized session and field checks.

## Main challenge: request limiting

Request limiting was the biggest problem. Each profile requires several requests, so small rate
changes have a large effect across roughly 131,000 profiles. Trying to force a higher rate made the
scraper slower because TigerNet responded with throttling and cooldowns.

The latest saved benchmark completed 1,846 profiles in 3,309 seconds, or about 0.56 profiles per
second. At that pace, scraping multiple fields from the full directory is possible in roughly 65
hours. This is an estimate. Duo approvals, interruptions, cooldowns, retries, and reconciliation
can add time.

I accepted the slower pace because it was the fastest complete-record approach that remained
stable. The scraper now starts conservatively, adjusts its rate from live responses, honors
`Retry-After`, and stops on persistent throttling.

## Data quality and recovery

Progress is stored in SQLite. Completed profiles are not collected again after restart, and failed
profiles remain visible for review. Two discovery passes are compared before the run can be marked
complete.

The known fields control CSV column order, but they do not limit extraction. New permitted fields
are added dynamically. I fixed an earlier version where labelled sections were dynamic but extra
header fields still came from a fixed subset.

The scraper writes a raw CSV for exact validation and a spreadsheet-safe CSV for Google Sheets.
Because about 131,000 rows across the observed field count may exceed Google's 10-million-cell
limit, the final data may need to be split across linked Sheets without dropping any fields.

## Authentication and security

Princeton CAS requires Duo approval, so authentication is attended. The scraper does not bypass
MFA. Reviewers use their own authorized accounts, and credentials stay local. Credentials,
cookies, profile records, databases, and CSV files are excluded from the public repository.

## AI collaboration

I used Codex to compare approaches, implement and test the scraper, inspect failures, improve the
CSV, preserve dynamic fields, and test request rates. I verified changes using saved results,
browser comparisons, tests, and field review.

I rejected suggestions that did not fit the task. A bulk export was not scraping, raw HTML was
incomplete, and multiple sessions did not provide independent capacity. I also changed the
original unattended plan after Duo showed that human approval was required.

The remaining work is operational: finish the resumable collection, reconcile the second discovery
pass, validate the final CSV, and import it into the approved spreadsheet destination.
