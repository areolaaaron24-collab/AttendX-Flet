from __future__ import annotations

from typing import Any
from supabase import Client

from attendx.services.supabase_client import BackendError, query_data, rpc, safe_message


class AuditService:
    def __init__(self, client: Client):
        self.client = client

    def record(self, action: str, entity_type: str | None = None, entity_id: str | None = None,
               details: dict[str, Any] | None = None) -> None:
        try:
            rpc(self.client, "write_audit_event", {
                "p_action": action,
                "p_entity_type": entity_type,
                "p_entity_id": entity_id,
                "p_details": details or {},
            })
        except BackendError:
            # Business operations must not be falsely reported as failed solely because a
            # best-effort audit message could not be written; failures stay in local logs.
            import logging
            logging.getLogger(__name__).exception("Audit event could not be recorded: %s", action)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            return query_data(
                self.client.table("audit_logs").select("*").order("created_at", desc=True).limit(min(max(limit, 1), 500))
            )
        except Exception as exc:
            raise BackendError(f"Could not load audit log: {safe_message(exc)}") from exc

    def health(self) -> dict[str, Any]:
        result = rpc(self.client, "attendx_health_check", {})
        if isinstance(result, list) and result:
            return result[0]
        return result or {"ok": False, "message": "The health check returned no data."}
