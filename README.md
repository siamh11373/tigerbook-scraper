# TigerBook Directory Scraper

Project scaffold for an automated directory export tool. The intended result is a single-command run that authenticates through a supported method, discovers the permitted profile population, captures fields dynamically, and produces a validated UTF-8 CSV.

**Status: planning and repository setup. The scraper is not implemented.** No live TigerBook login, profile collection, or export has been performed as part of this project setup.

## Start here

- [THINKING.md](THINKING.md): reserved for the author's direct thoughts and input.
- [Discovery log](docs/EXPERIMENTS.md): prioritized experiments and a template for recording actual results.
- [Source layout](src/README.md): proposed components and their responsibilities.
- [Validation plan](tests/README.md): planned coverage and acceptance checks.

## Prerequisites and installation

Git is sufficient to clone and read the current scaffold. The runtime, dependency versions, and installation procedure will be selected after the discovery experiments.

`requirements.txt` is a placeholder dependency manifest. It currently installs no application and does not represent a finalized language or library choice. If a different runtime is selected, replace it with that runtime's manifest.

## Credentials

Credential configuration is not implemented. The planned interface will read credentials from environment variables or an explicitly ignored local configuration file. Exact variable names and setup instructions must be documented when authentication is implemented.

Never place credentials, MFA material, cookies, browser storage, or authentication traces in commits, issue reports, or AI prompts. A reusable session is sensitive even if it contains no password. Each operator must use an account authorized for the target service and purpose.

## Running the scraper

There is no runnable scraping command yet. Before claiming the implementation is ready, document and test the exact installation and single-command execution steps from a clean checkout with a fresh session.

## Intended behavior and output

1. Validate configuration and the permitted collection scope.
2. Establish an authorized session without manual login or pasted cookies.
3. Discover profile identifiers and persist collection progress.
4. Fetch profiles at a conservative rate, capture fields dynamically, and record failures separately from missing values.
5. Resume unfinished work without duplicating profiles.
6. Validate coverage and generate a CSV plus a run report.

The planned local output directory is `output/`, which Git ignores. The CSV should contain one row per stable profile identifier, deterministic columns covering all discovered fields, correctly escaped UTF-8 text, and empty cells for missing values. The report should distinguish a validated export from a partial or blocked run. Final filenames are still to be selected.

Google Sheets upload is a manual delivery step. Verify import fidelity and share only with explicitly authorized recipients using approved storage. No live export or Sheet exists yet.

## Architecture

The proposed pipeline is configuration → authentication → discovery → durable work queue → throttled fetching → dynamic extraction → validation → CSV export. See [src/README.md](src/README.md) for the planned responsibilities. These components are a design sketch, not implemented modules.

## Known limitations and open questions

- The exact current target URL and eligible population still need confirmation.
- Fresh unattended authentication, MFA behavior, and session renewal have not been tested.
- Exhaustive profile enumeration, stable identifiers, pagination, and any result limits are unknown.
- API availability, permission, freshness, and field coverage have not been verified.
- No implementation, automated tests, full run, or completeness claim exists yet.
- Collection and external sharing permission must be resolved before collecting a dataset.

## Repository contents

```text
README.md             Project status and operator documentation
THINKING.md           Author's direct thoughts and input
requirements.txt      Placeholder dependency manifest
.gitignore            Excludes credentials and local data artifacts
docs/EXPERIMENTS.md    Discovery checklist and experiment records
src/README.md         Proposed source responsibilities
tests/README.md       Validation plan
```

This public repository contains project-authored documentation and, as development proceeds, source code and synthetic tests. Keep confidential source documents, private reference libraries, real profiles, exports, and session artifacts local. Review staged changes before every commit; ignore rules alone are not a guarantee against accidental disclosure.

## Development checks

For the current documentation scaffold, review links and run `git diff --check`. Application tests, formatting, linting, and type-check commands must be added when an implementation exists. Record actual check results rather than listing planned tests as passing.
