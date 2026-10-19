from __future__ import annotations

import base64
import importlib.util
import logging
from typing import Any


from attendx.core.config import Settings
from attendx.services.supabase_client import BackendError

log = logging.getLogger(__name__)


class CameraService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("cv2") is not None

    def open(self):
        try:
            import cv2
        except ImportError as exc:
            raise BackendError("OpenCV is not installed on this platform. For desktop QR scanning, install requirements-desktop.txt. Mobile camera support needs a native camera implementation.") from exc
        camera = cv2.VideoCapture(self.settings.camera_index)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
        if not camera.isOpened():
            camera.release()
            raise BackendError(
                f"Could not open camera index {self.settings.camera_index}. Check permissions, close other apps using it, or change CAMERA_INDEX in .env."
            )
        return camera

    @staticmethod
    def to_base64(frame: Any) -> str:
        try:
            import cv2
        except ImportError as exc:
            raise BackendError("OpenCV is not installed; camera preview is unavailable on this platform.") from exc
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        if not ok:
            raise BackendError("Could not encode the camera preview frame.")
        return base64.b64encode(encoded.tobytes()).decode("ascii")

    @staticmethod
    def decode_qr(frame: Any) -> str | None:
        try:
            import cv2
        except ImportError as exc:
            raise BackendError("OpenCV is not installed; QR decoding is unavailable on this platform.") from exc
        detector = cv2.QRCodeDetector()
        data, _points, _straight = detector.detectAndDecode(frame)
        data = (data or "").strip()
        return data or None

    @staticmethod
    def to_rgb_small(frame: Any, scale: float = 0.25):
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if scale != 1:
            rgb = cv2.resize(rgb, (0, 0), fx=scale, fy=scale)
        return rgb
