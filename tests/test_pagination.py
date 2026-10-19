import pytest

from attendx.core.pagination import fetch_all_pages


def test_pagination_retrieves_rows_over_multiple_pages_without_gaps():
    rows = list(range(1_203))
    calls = []

    def fetch(offset, limit):
        calls.append((offset, limit))
        return rows[offset : offset + limit]

    result = fetch_all_pages(fetch, page_size=500, max_items=2_000)
    assert result == rows
    assert calls == [(0, 500), (500, 500), (1000, 500)]


def test_pagination_respects_maximum_row_cap():
    rows = list(range(5_000))
    result = fetch_all_pages(lambda offset, limit: rows[offset : offset + limit], page_size=250, max_items=1_000)
    assert result == rows[:1_000]


def test_pagination_rejects_non_positive_parameters():
    with pytest.raises(ValueError):
        fetch_all_pages(lambda offset, limit: [], page_size=0)
    with pytest.raises(ValueError):
        fetch_all_pages(lambda offset, limit: [], max_items=0)
