from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProfileRef:
    id: str
    url: str


@dataclass(frozen=True)
class ListingPage:
    profiles: tuple[ProfileRef, ...]
    next_cursor: str | None
    total: int | None = None
    # True only when the adapter has evidence of an exhaustive listing mechanism.
    exhaustive: bool = False


Fields = dict[str, Any]
