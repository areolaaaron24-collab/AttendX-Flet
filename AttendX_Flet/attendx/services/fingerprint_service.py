from __future__ import annotations

import importlib.util
import logging
import time
from typing import Any

from supabase import Client

from attendx.core.config import Settings
from attendx.services.supabase_client import BackendError, query_data, query_paginated, safe_message

log = logging.getLogger(__name__)


class FingerprintHardware:
    """Optional AS608/R307-compatible UART/USB-serial adapter via pyfingerprint.

    The sensor must expose a serial port and use a compatible protocol/baud rate.
    A laptop's built-in fingerprint reader and phone fingerprint sensor are not supported.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def is_installed() -> bool:
        return importlib.util.find_spec("pyfingerprint") is not None and importlib.util.find_spec("serial") is not None

    def _connect(self):
        if not self.is_installed():
            raise BackendError("Install optional dependencies with: pip install pyserial pyfingerprint")
        try:
            from pyfingerprint.pyfingerprint import PyFingerprint
            sensor = PyFingerprint(
                self.settings.fingerprint_port,
                self.settings.fingerprint_baudrate,
                self.settings.fingerprint_address,
                self.settings.fingerprint_password,
            )
            if not sensor.verifyPassword():
                raise BackendError("Fingerprint sensor password verification failed. Check address/password settings.")
            return sensor
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(
                f"Could not connect to a compatible fingerprint sensor on {self.settings.fingerprint_port}: {exc}"
            ) from exc

    @staticmethod
    def _close_sensor(sensor: Any | None) -> None:
        """Close the serial port even if a scan fails or times out."""
        if sensor is None:
            return
        candidates = [getattr(sensor, "close", None)]
        for name in ("_PyFingerprint__connection", "_connection", "connection"):
            candidates.append(getattr(sensor, name, None))
        for candidate in candidates:
            try:
                close = candidate if callable(candidate) else getattr(candidate, "close", None)
                if callable(close):
                    close()
                    return
            except Exception:
                continue

    def check_device(self) -> dict[str, Any]:
        sensor = None
        try:
            sensor = self._connect()
            count = sensor.getTemplateCount()
            capacity = sensor.getStorageCapacity()
            return {"available": True, "port": self.settings.fingerprint_port, "templates": count, "capacity": capacity}
        except Exception as exc:
            return {"available": False, "port": self.settings.fingerprint_port, "message": str(exc)}
        finally:
            self._close_sensor(sensor)

    def enroll(self, timeout_seconds: int = 45) -> int:
        sensor = self._connect()
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                if sensor.readImage():
                    sensor.convertImage(0x01)
                    try:
                        position, _score = sensor.searchTemplate()
                        if position >= 0:
                            raise BackendError("This fingerprint is already enrolled on the sensor.")
                    except BackendError:
                        raise
                    except Exception:
                        pass
                    break
                time.sleep(0.15)
            else:
                raise BackendError("Timed out waiting for the first fingerprint scan.")
            while sensor.readImage():
                time.sleep(0.15)
            while time.monotonic() < deadline:
                if sensor.readImage():
                    sensor.convertImage(0x02)
                    break
                time.sleep(0.15)
            else:
                raise BackendError("Timed out waiting for the second fingerprint scan.")
            sensor.createTemplate()
            position = int(sensor.storeTemplate())
            return position
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Fingerprint enrolment failed: {exc}") from exc
        finally:
            self._close_sensor(sensor)

    def identify(self, timeout_seconds: int = 25) -> tuple[int, int] | None:
        sensor = self._connect()
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                if sensor.readImage():
                    sensor.convertImage(0x01)
                    position, score = sensor.searchTemplate()
                    if position >= 0:
                        return int(position), int(score)
                    return None
                time.sleep(0.15)
            return None
        except Exception as exc:
            raise BackendError(f"Fingerprint scan failed: {exc}") from exc
        finally:
            self._close_sensor(sensor)


class FingerprintService:
    def __init__(self, client: Client, actor_id: str, role: str, settings: Settings):
        self.client, self.actor_id, self.role, self.settings = client, actor_id, role.upper(), settings
        self.hardware = FingerprintHardware(settings)

    def register_own_fingerprint(self, finger_name: str) -> int:
        raise BackendError(
            "Fingerprint registration is teacher-managed in the shared AttendX-Web database. "
            "Ask your teacher to select your class and use Enroll Student Fingerprint on the "
            "computer connected to the AS608/R307 reader."
        )

    def register_student_fingerprint(self, student_id: str, schedule_id: str) -> int:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can enroll a student's fingerprint.")
        if not student_id or not schedule_id:
            raise BackendError("Select a class schedule and enrolled student first.")
        device_id = self.settings.fingerprint_port.strip()
        if not device_id or len(device_id) > 64:
            raise BackendError("Configure a valid fingerprint reader device ID in FINGERPRINT_PORT.")
        template_position = self.hardware.enroll()
        # AttendX-Web's mapping schema reserves sensor_slot 1..255. The hardware
        # library reports its position zero-based, so persist position+1 and reverse
        # that mapping during attendance scans.
        sensor_slot = template_position + 1
        if sensor_slot > 255:
            raise BackendError(
                f"The reader stored template #{template_position}, but AttendX supports slots 1–255. "
                "Do not use this template until the reader slot is reconciled."
            )
        try:
            response = self.client.functions.invoke(
                "register-fingerprint",
                invoke_options={"body": {
                    "scheduleId": str(schedule_id),
                    "studentId": str(student_id),
                    "deviceId": device_id,
                    "sensorSlot": sensor_slot,
                }},
            )
            result = response.data if hasattr(response, "data") else response
            if isinstance(result, dict) and result.get("ok") is not True:
                raise BackendError(str(result.get("error") or "Fingerprint mapping was rejected."))
            return template_position
        except Exception as exc:
            raise BackendError(
                f"The sensor stored template #{template_position}, but the server mapping failed: "
                f"{safe_message(exc)}. Do not use it for attendance until the mapping is repaired."
            ) from exc

    def mappings_for_schedule(self, schedule_id: str) -> list[dict[str, Any]]:
        if self.role != "TEACHER":
            raise BackendError("Only the assigned teacher can load fingerprint mappings.")
        try:
            enrolled = query_paginated(
                lambda: self.client.table("enrollments").select("student_id")
                .eq("schedule_id", str(schedule_id)), max_items=10_000
            )
            student_ids = {str(row["student_id"]) for row in enrolled}
            if not student_ids:
                return []
            rows = query_paginated(
                lambda: self.client.table("fingerprint_templates")
                .select("student_id,device_id,sensor_slot").order("student_id"),
                max_items=10_000
            )
            return [
                {
                    "student_id": str(row["student_id"]),
                    "sensor_template_id": int(row["sensor_slot"]) - 1,
                    "finger_name": "Registered fingerprint",
                    "device_id": row.get("device_id", ""),
                }
                for row in rows
                if str(row.get("student_id")) in student_ids
                and str(row.get("device_id", "")) == self.settings.fingerprint_port
            ]
        except Exception as exc:
            raise BackendError(f"Could not load fingerprint mappings: {safe_message(exc)}") from exc
