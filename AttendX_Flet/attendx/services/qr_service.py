from __future__ import annotations

import base64
import io
from typing import Any

import qrcode
from supabase import Client

from attendx.core.config import Settings
from attendx.services.supabase_client import BackendError, rpc


class QRService:
    """QR-pass adapter for the current AttendX-Web QR token RPC."""

    def __init__(self, client: Client, actor_id: str, role: str, settings: Settings):
        self.client = client
        self.actor_id = actor_id
        self.role = role.upper()
        self.settings = settings

    def issue_student_pass(self, schedule_id: str) -> tuple[str, str]:
        if self.role != "STUDENT":
            raise BackendError("Only the signed-in student can issue their personal QR pass.")
        token = rpc(self.client, "get_or_create_student_qr_token", {
            "p_schedule_id": str(schedule_id),
        })
        if isinstance(token, list) and token:
            token = token[0]
        if isinstance(token, dict):
            token = token.get("get_or_create_student_qr_token") or token.get("token")
        token = str(token or "").strip()
        if not token:
            raise BackendError("AttendX did not return a QR pass. Confirm that you joined this class.")
        return token, self.to_data_uri(token)

    @staticmethod
    def to_data_uri(text: str) -> str:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=7,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#09264A", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    def issue_session_token(self) -> str:
        raise BackendError(
            "Teacher session QR is not supported by the existing AttendX-Web backend yet. "
            "Use a student's personal QR pass for teacher-side scanning."
        )
