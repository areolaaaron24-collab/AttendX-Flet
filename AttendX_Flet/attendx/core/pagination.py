from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def fetch_all_pages(
    fetch_page: Callable[[int, int], Sequence[T]],
    *,
    page_size: int = 500,
    max_items: int = 10_000,
) -> list[T]:
    """Fetch deterministic offset pages without exceeding a caller-defined safety cap.

    `fetch_page(offset, limit)` must return at most `limit` items from a stable order.
    The cap protects UI memory and keeps a single action from loading an unbounded table.
    """
    if page_size < 1 or max_items < 1:
        raise ValueError("page_size and max_items must be positive")
    rows: list[T] = []
    offset = 0
    while offset < max_items:
        limit = min(page_size, max_items - offset)
        page = list(fetch_page(offset, limit))
        if not page:
            break
        rows.extend(page[:limit])
        offset += min(len(page), limit)
        if len(page) < limit:
            break
    return rows
