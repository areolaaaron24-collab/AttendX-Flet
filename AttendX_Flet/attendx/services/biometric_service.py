from __future__ import annotations

import importlib.util
import logging
import math
from typing import Any

from supabase import Client

from attendx.services.supabase_client import BackendError, query_data, query_paginated, safe_message

log = logging.getLogger(__name__)


class FaceBiometricService:
    """Stores 128-dimensional face descriptors; no raw face images are uploaded."""

    def __init__(self, client: Client, actor_id: str, role: str):
        self.client = client
        self.actor_id = actor_id
        self.role = role.upper()

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("face_recognition") is not None

    @staticmethod
    def encode_rgb(rgb_image: Any) -> list[float]:
        try:
            import face_recognition
        except ImportError as exc:
            raise BackendError(
                "Face recognition is not installed. Install the optional face-recognition dependency "
                "and its native dlib requirements for this operating system."
            ) from exc
        locations = face_recognition.face_locations(rgb_image, model="hog")
        if len(locations) != 1:
            raise BackendError("Keep exactly one face in view to register or verify attendance.")
        encodings = face_recognition.face_encodings(rgb_image, locations, num_jitters=1)
        if not encodings:
            raise BackendError("The camera frame did not produce a usable face descriptor. Try better lighting.")
        return [float(x) for x in encodings[0].tolist()]

    def register_own_face(self, embedding: list[float]) -> None:
        if self.role != "STUDENT":
            raise BackendError("Face registration is available from the student's own profile.")
        if len(embedding) != 128 or not all(math.isfinite(float(x)) for x in embedding):
            raise BackendError("Invalid face descriptor. Nothing was saved.")
        try:
            # AttendX-Web stores numeric descriptors in a PostgreSQL double precision[].
            # Keep a distinct model_version because face_recognition embeddings are not
            # interchangeable with the browser's face-api descriptors.
            self.client.table("face_templates").upsert({
                "student_id": self.actor_id,
                "descriptor": [float(x) for x in embedding],
                "model_version": "face_recognition-128d-v1",
            }, on_conflict="student_id").execute()
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not save the face descriptor: {safe_message(exc)}") from exc

    def templates_for_current_classes(self, schedule_id: str) -> list[dict[str, Any]]:
        if self.role != "TEACHER":
            raise BackendError("Only the assigned teacher can load face descriptors for a class.")
        if not schedule_id:
            raise BackendError("Select a class schedule before starting face attendance.")
        try:
            response = self.client.rpc("attendx_face_templates_for_schedule", {
                "p_schedule_id": str(schedule_id),
            }).execute()
            rows = response.data or []
            return [
                {"student_id": row["student_id"], "embedding": row["embedding"]}
                for row in rows
                if isinstance(row.get("embedding"), list) and len(row["embedding"]) == 128
            ]
        except Exception as exc:
            raise BackendError(
                "Could not load authorized face templates. Confirm that the AttendX-Web compatibility "
                f"migration is applied: {safe_message(exc)}"
            ) from exc

    def has_own_face(self) -> bool:
        rows = query_data(self.client.table("face_templates").select("student_id").eq("student_id", self.actor_id).limit(1))
        return bool(rows)

    def delete_own_face(self) -> None:
        if self.role != "STUDENT":
            raise BackendError("Only the student can request deletion of their own face template.")
        try:
            self.client.table("face_templates").delete().eq("student_id", self.actor_id).execute()
        except Exception as exc:
            raise BackendError(f"Could not delete face template: {safe_message(exc)}") from exc

    @staticmethod
    def best_match(embedding: list[float], templates: list[dict[str, Any]], tolerance: float = 0.43) -> tuple[str, float] | None:
        """Return unique nearest student only if below a conservative distance threshold."""
        if len(embedding) != 128:
            return None
        ranked: list[tuple[float, str]] = []
        for row in templates:
            known = row.get("embedding")
            if not isinstance(known, list) or len(known) != 128:
                continue
            distance = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(embedding, known)))
            ranked.append((distance, row["student_id"]))
        ranked.sort(key=lambda item: item[0])
        if not ranked or ranked[0][0] > tolerance:
            return None
        # If two templates are almost equally close, do not guess between lookalike faces.
        if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < 0.025:
            return None
        return ranked[0][1], ranked[0][0]
