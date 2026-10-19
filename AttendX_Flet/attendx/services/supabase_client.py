from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from attendx.core.config import ConfigurationError, Settings, validate_public_key
from attendx.core.pagination import fetch_all_pages

log = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """A backend request failed or the server response was invalid."""


def get_client(settings: Settings | None = None) -> Client:
    config = settings or Settings.from_env()
    validate_public_key(config)
    try:
        # Settings.from_env already prefers the publishable key, then anon.
        # Do not let a second environment variable override a validated public key.
        return create_client(config.supabase_url, config.supabase_key)
    except Exception as exc:
        log.exception("Could not initialize Supabase client")
        raise BackendError(f"Could not initialize the Supabase client: {safe_message(exc)}") from exc


def safe_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lower = message.lower()
    if any(secret in lower for secret in ("service_role", "sb_secret_", "authorization: bearer")):
        return "The backend rejected the request. Check project configuration and permissions."
    return message[:500]


def response_data(response: Any) -> Any:
    if response is None:
        return None
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, dict):
        return response.get("data", response)
    return response


def unwrap(response: Any) -> Any:
    return response_data(response)


def rpc(client: Client, function_name: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return unwrap(client.rpc(function_name, params or {}).execute())
    except Exception as exc:
        log.warning("Supabase RPC %s failed: %s", function_name, exc)
        raise BackendError(f"{function_name.replace('_', ' ').capitalize()} failed: {safe_message(exc)}") from exc


def query_data(query: Any) -> list[dict[str, Any]]:
    try:
        data = unwrap(query.execute())
    except Exception as exc:
        log.warning("Supabase query failed: %s", exc)
        raise BackendError(f"Database query failed: {safe_message(exc)}") from exc
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    return list(data)


def query_paginated(query_factory, *, page_size: int = 500, max_items: int = 10_000) -> list[dict[str, Any]]:
    """Execute a stable Supabase query in pages instead of relying on a single API cap.

    `query_factory` must return a fresh, ordered PostgREST query builder each time.
    The database's RLS policies still apply to every page.
    """
    return fetch_all_pages(
        lambda offset, limit: query_data(query_factory().range(offset, offset + limit - 1)),
        page_size=page_size,
        max_items=max_items,
    )


def query_by_values(client: Client, table_name: str, columns: str, filter_column: str,
                    values: list[Any], *, chunk_size: int = 250) -> list[dict[str, Any]]:
    """Fetch unique rows by chunks of values to keep IN filters/request URLs manageable.

    This helper is intended for internal, hard-coded table/column names and values read
    from authorized database results, not raw user-supplied identifiers.
    """
    distinct: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        if value not in seen:
            distinct.append(value)
            seen.add(value)
    result: list[dict[str, Any]] = []
    for start in range(0, len(distinct), chunk_size):
        chunk = distinct[start : start + chunk_size]
        result.extend(query_data(client.table(table_name).select(columns).in_(filter_column, chunk)))
    return result
