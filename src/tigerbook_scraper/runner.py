"""Collection orchestration; adapters supply observed site-specific behavior."""

import time
from typing import Protocol

from .errors import AccessBlocked, AuthenticationError, DiscoveryError, ExtractionError, FetchError
from .fields import from_mapping
from .models import Fields, ListingPage, ProfileRef
from .state import State


class Adapter(Protocol):
    def list_page(self, cursor: str | None) -> ListingPage: ...
    def profile(self, ref: ProfileRef) -> Fields: ...
    def audit(self, ref: ProfileRef, fields: Fields) -> bool: ...


def collect(adapter: Adapter, state: State, *, limit=None, progress=print) -> None:
    state.note("blocker", None)
    state.retry_failed()
    started = time.monotonic()
    completed_at_start = state.counts()["complete"]

    def process_pending():
        counts = state.counts()

        def save_benchmark():
            state.note(
                "benchmark",
                {
                    "new_profiles": counts["complete"] - completed_at_start,
                    "elapsed_seconds": time.monotonic() - started,
                    "interpretation": "includes discovery, fetching, auditing and local work",
                },
            )

        for ref in state.pending():
            if limit is not None and counts["complete"] >= limit:
                save_benchmark()
                return
            state.attempt(ref.id)
            try:
                fields = from_mapping(adapter.profile(ref))
                audit_count = state.get("audit_count", 0)
                # Check the first ten records and subsequently every 1,000 records.
                audit_key = f"audit_required:{ref.id}"
                if (
                    audit_count < 10
                    or counts["complete"] % 1000 == 0
                    or state.get(audit_key, False)
                ):
                    state.note(audit_key, True)
                    if not adapter.audit(ref, fields):
                        raise ExtractionError("Profile fidelity comparison failed.")
                    state.note("audit_count", audit_count + 1)
                    state.note(audit_key, False)
                state.complete(ref.id, fields)
                counts["complete"] += 1
                state.note(
                    "field_fidelity_verified",
                    state.get("audit_count", 0) > 0
                    and getattr(adapter, "field_coverage_verified", True),
                )
            except (AuthenticationError, AccessBlocked):
                # Keep the current profile pending so a restarted run retries it.
                raise
            except (FetchError, ExtractionError) as error:
                state.fail(ref.id, error.code)
                counts["failed"] += 1
                state.note("field_fidelity_verified", False)
            counts["pending"] -= 1
            if counts["complete"] <= 25 or counts["complete"] % 100 == 0 or counts["failed"]:
                rate = (counts["complete"] - completed_at_start) / max(
                    time.monotonic() - started, 0.001
                )
                progress(
                    f"Discovered {counts['discovered']}; completed {counts['complete']}; "
                    f"failed {counts['failed']}; {rate:.2f} profiles/s"
                )
        save_benchmark()

    mismatched_phases = []
    for phase in ("discovery", "reconciliation"):
        process_pending()
        if limit is not None and state.counts()["complete"] >= limit:
            return
        while not state.checkpoint(phase)["done"]:
            checkpoint = state.checkpoint(phase)
            page = adapter.list_page(checkpoint["cursor"])
            state.save_page(phase, checkpoint["cursor"], page)
            process_pending()
            if limit is not None and state.counts()["complete"] >= limit:
                return
        total = state.get(f"total:{phase}")
        if total is not None and total != state.membership_count(phase):
            # Reconciliation may discover IDs missed by a changing first-pass ordering.
            # Keep the mismatch as a failure, but do not prevent that second enumeration.
            mismatched_phases.append(phase)
    process_pending()
    if mismatched_phases:
        raise DiscoveryError("The listing ended before its reported population was reconciled.")
    # Recover a crash after the last record committed but before its run flag did.
    counts = state.counts()
    if not counts["pending"] and not counts["failed"] and state.get("audit_count", 0) > 0:
        state.note("field_fidelity_verified", getattr(adapter, "field_coverage_verified", True))
