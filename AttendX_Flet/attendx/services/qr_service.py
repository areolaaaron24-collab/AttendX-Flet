from __future__ import annotations

import base64
import io
import secrets
from typing import Any

import qrcode
from supabase import Client

from attendx.core.config import Settings
from attendx.services.supabase_client import BackendError, rpc, safe_message


class QRService:
    def __init__(self, client: Client, actor_id: str, role: str, settings: Settings):
        self.client = client
        self.actor_id = actor_id
        self.role = role.upper()
        self.settings = settings

    def issue_student_pass(self, schedule_id: str) -> tuple[str, str]:
        if self.role != "STUDENT":
            raise BackendError("Only the signed-in student can issue their personal QR pass.")
        token = secrets.token_urlsafe(32)
        rpc(self.client, "issue_student_qr_token", {
            "p_schedule_id": schedule_id,
            "p_token_text": token,
            "p_ttl_days": self.settings.qr_token_ttl_days,
        })
        return token, self.to_data_uri(token)

    @staticmethod
    def to_data_uri(text: str) -> str:
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=7, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#09264A", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    def issue_session_token(self) -> str:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can create a class session QR token.")
        return secrets.token_urlsafe(32)
