import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from .fields import csv_value, needs_text_import
from .presentation import KNOWN_FIELDS, readable_fields, spreadsheet_value
from .state import State, now


def _export_csv(state: State, directory: Path, *, readable: bool) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    keys = set()
    for _, _, fields in state.records():
        keys.update(readable_fields(fields) if readable else fields)
    # Source fields are namespaced so a real "profile_id" can never overwrite metadata.
    if readable:
        extras = sorted(keys - set(KNOWN_FIELDS), key=lambda key: (key.casefold(), key))
        keys = [*KNOWN_FIELDS, *extras]
        headers = ["Profile ID", "Profile URL", *keys]
    else:
        keys = sorted(keys)
        headers = ["profile_id", "profile_url", *(f"field/{key}" for key in keys)]
    render = spreadsheet_value if readable else csv_value
    destination = directory / ("profiles.csv" if readable else "profiles.raw.csv")
    fd, temporary = tempfile.mkstemp(prefix=".profiles-", suffix=".tmp", dir=directory)
    text_sensitive = 0
    max_cell_characters = 0
    rows = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for profile_id, url, fields in state.records():
                values_by_key = readable_fields(fields) if readable else fields
                values = [
                    render(profile_id),
                    render(url),
                    *(render(values_by_key.get(key)) for key in keys),
                ]
                text_sensitive += sum(needs_text_import(value) for value in values)
                max_cell_characters = max(max_cell_characters, *(len(value) for value in values))
                writer.writerow(values)
                rows += 1
            handle.flush()
            os.fsync(handle.fileno())
        # Stream a readback against the database; verify each value and ID, not just counts.
        csv.field_size_limit(sys.maxsize)
        with open(temporary, encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            if next(reader) != headers:
                raise ValueError("CSV header validation failed.")
            for profile_id, url, fields in state.records():
                values_by_key = readable_fields(fields) if readable else fields
                expected = [
                    render(profile_id),
                    render(url),
                    *(render(values_by_key.get(key)) for key in keys),
                ]
                if next(reader, None) != expected:
                    raise ValueError("CSV record validation failed.")
            if next(reader, None) is not None:
                raise ValueError("CSV contains extra records.")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    digest = hashlib.sha256()
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "rows": rows,
        "columns": len(headers),
        "csv_roundtrip_verified": True,
        "csv_sha256": digest.hexdigest(),
        "text_sensitive_cells": text_sensitive,
        "max_cell_characters": max_cell_characters,
        "sheet_cells_required": (rows + 1) * len(headers),
        "fits_google_sheets_10m_cells": (rows + 1) * len(headers) <= 10_000_000,
    }


def export_run(state: State, directory: Path) -> dict:
    raw = _export_csv(state, directory, readable=False)
    display = _export_csv(state, directory, readable=True)
    known_values = {key: 0 for key in KNOWN_FIELDS}
    for _, _, fields in state.records():
        values = readable_fields(fields)
        for key in KNOWN_FIELDS:
            known_values[key] += bool(values[key])
    reasons = []
    counts = state.counts()
    if state.get("identity")["limit"] is not None:
        reasons.append("limited_run")
    for phase in ("discovery", "reconciliation"):
        if not state.checkpoint(phase)["done"]:
            reasons.append(f"{phase}_unfinished")
        if not state.get(f"exhaustive:{phase}", False):
            reasons.append(f"{phase}_coverage_unproven")
        total = state.get(f"total:{phase}")
        if total is not None and total != state.membership_count(phase):
            reasons.append(f"{phase}_count_mismatch")
    if state.membership_differences() or state.get("source_changed", False):
        reasons.append("source_membership_changed")
    if counts["pending"] or counts["failed"]:
        reasons.append("unresolved_profiles")
    if state.get("blocker"):
        reasons.append(state.get("blocker"))
    if not counts["discovered"]:
        reasons.append("empty_population_requires_review")
    if not state.get("field_fidelity_verified", False):
        reasons.append("field_fidelity_not_verified")
    if state.get("direct_browser_mismatches", 0):
        reasons.append("direct_browser_mismatch")
    if state.get("collection_mode") == "direct_requests_fixed_header":
        reasons.append("fixed_header_field_subset")
    report = {
        **display,
        "raw_export": {"file": "profiles.raw.csv", **raw},
        "display_format": "known_fields_then_dynamic_v2",
        "known_field_coverage": {
            "required_columns": list(KNOWN_FIELDS),
            "profiles_with_values": known_values,
            "fields_without_values": [key for key, count in known_values.items() if count == 0],
        },
        "status": "complete" if not reasons else "partial",
        "reasons": sorted(set(reasons)),
        "counts": counts,
        "started_at": state.get("started_at"),
        "exported_at": now(),
        "manual_sheet_import_verified": False,
        "scope": state.get("identity")["scope"],
        "benchmark": state.get("benchmark"),
        "audited_profiles": state.get("audit_count", 0),
        "collection_mode": state.get("collection_mode", "browser"),
        "direct_browser_comparisons": state.get("direct_browser_comparisons", 0),
        "direct_browser_mismatches": state.get("direct_browser_mismatches", 0),
        "startup_profiles_skipped": state.get("startup_profiles_skipped", 0),
        "browser_sessions": state.get("browser_sessions", 1),
        "fixed_base_fields": state.get("fixed_base_fields"),
        "observed_totals": {
            phase: state.get(f"total:{phase}") for phase in ("discovery", "reconciliation")
        },
        "snapshot_semantics": "collection_window_not_an_atomic_source_snapshot",
    }
    report_path = directory / "report.json"
    fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, report_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report
