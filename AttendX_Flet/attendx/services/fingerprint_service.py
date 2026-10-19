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
        if self.role != "STUDENT":
            raise BackendError("Fingerprint enrollment must be initiated from the student's account.")
        finger_name = " ".join((finger_name or "").strip().split())
        if not finger_name or len(finger_name) > 40:
            raise BackendError("Enter a finger label, such as Right Index.")
        template_id = self.hardware.enroll()
        try:
            self.client.rpc("save_fingerprint_template", {
                "p_sensor_template_id": template_id,
                "p_finger_name": finger_name,
            }).execute()
            return template_id
        except Exception as exc:
            # Hardware enrolment succeeded but database mapping did not. Explain the orphaned
            # sensor template so a teacher can remove it from the sensor, rather than report success.
            raise BackendError(
                f"The sensor stored template #{template_id}, but the server mapping failed: {safe_message(exc)}. "
                "Do not use it for attendance until the mapping is repaired."
            ) from exc

    def mappings_for_schedule(self, schedule_id: str) -> list[dict[str, Any]]:
        if self.role != "TEACHER":
            raise BackendError("Only the assigned teacher can load fingerprint mappings.")
        try:
            return query_paginated(lambda: self.client.table("fingerprint_credentials").select("student_id,sensor_template_id,finger_name").order("student_id"), max_items=10_000)
        except Exception as exc:
            raise BackendError(f"Could not load fingerprint mappings: {safe_message(exc)}") from exc
