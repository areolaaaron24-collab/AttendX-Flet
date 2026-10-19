from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import flet as ft

from attendx.core.config import ConfigurationError, Settings
from attendx.core.logging_config import configure_logging
from attendx.core.validators import RegistrationData
from attendx.services.attendance_service import AttendanceService
from attendx.services.audit_service import AuditService
from attendx.services.auth_service import AuthService
from attendx.services.biometric_service import FaceBiometricService
from attendx.services.camera_service import CameraService
from attendx.services.fingerprint_service import FingerprintService
from attendx.services.profile_service import ProfileService
from attendx.services.qr_service import QRService
from attendx.services.report_service import ReportService
from attendx.services.student_service import StudentService
from attendx.services.supabase_client import BackendError, get_client, safe_message
from attendx.services.teacher_service import TeacherService
from attendx.ui.pages.auth import build_auth_page
from attendx.ui.pages.portal import build_portal_page
from attendx.ui.pages.student import build_student_page
from attendx.ui.pages.teacher import build_teacher_page
from attendx.ui.theme import BORDER, CYAN, GOLD, MUTED, NAVY, NAVY_2, SURFACE, SURFACE_2, WHITE, configure_page

log = logging.getLogger(__name__)

TEACHER_NAV = [
    ("dashboard", "Dashboard", "SPACE_DASHBOARD_ROUNDED"),
    ("students", "My Students", "GROUP_ROUNDED"),
    ("subjects", "Subjects", "MENU_BOOK_ROUNDED"),
    ("schedules", "Schedules", "EVENT_NOTE_ROUNDED"),
    ("attendance", "Attendance Center", "FACT_CHECK_ROUNDED"),
    ("records", "Attendance History", "HISTORY_ROUNDED"),
    ("reports", "Reports & Exports", "ASSESSMENT_ROUNDED"),
    ("profile", "My Profile", "ACCOUNT_CIRCLE_ROUNDED"),
    ("settings", "Settings", "SETTINGS_ROUNDED"),
    ("database", "Database Verification", "STORAGE_ROUNDED"),
]
STUDENT_NAV = [
    ("dashboard", "Dashboard", "SPACE_DASHBOARD_ROUNDED"),
    ("subjects", "Add Subject", "ADD_CIRCLE_ROUNDED"),
    ("schedule", "My Schedule", "EVENT_NOTE_ROUNDED"),
    ("attendance", "My Attendance", "FACT_CHECK_ROUNDED"),
    ("qr_pass", "My QR Pass", "QR_CODE_2_ROUNDED"),
    ("scan_session", "Scan Class QR", "QR_CODE_SCANNER_ROUNDED"),
    ("face", "Face Setup", "FACE_RETOUCHING_NATURAL_ROUNDED"),
    ("fingerprint", "Fingerprint Setup", "FINGERPRINT_ROUNDED"),
    ("profile", "My Profile", "ACCOUNT_CIRCLE_ROUNDED"),
    ("settings", "Settings", "SETTINGS_ROUNDED"),
]


class AppController:
    def __init__(self, page: ft.Page):
        self.page = page
        self.settings = Settings.from_env()
        configure_logging(self.settings.log_level)
        configure_page(page)
        self.client = None
        self.auth_service = None
        self.profile_service = None
        self.audit_service = None
        self.teacher_service = None
        self.student_service = None
        self.attendance_service = None
        self.qr_service = None
        self.face_service = None
        self.fingerprint_service = None
        self.camera_service = CameraService(self.settings)
        self.report_service = None
        self.profile: dict[str, Any] | None = None
        self.user_id: str | None = None
        self.role: str | None = None
        self.current_page = "dashboard"
        self.preferred_schedule_id: str | None = None
        self.active_session_id: str | None = None
        self.scan_running = False
        self.student_scan_running = False
        self.face_capture_running = False
        self.show_portal()

    def _ensure_client(self):
        if self.client is None:
            self.client = get_client(self.settings)
            self.auth_service = AuthService(self.client, self.settings)
        return self.client

    def show_portal(self):
        self._stop_hardware()
        self.profile = None
        self.user_id = None
        self.role = None
        self.current_page = "dashboard"
        self.page.controls.clear()
        self.page.add(build_portal_page(self))
        self.page.update()

    def show_auth(self, role: str, mode: str = "login"):
        if role.lower() not in {"teacher", "student"}:
            self.notify("Only the Teacher and Student portals are available.", error=True)
            return
        self._stop_hardware()
        self.page.controls.clear()
        self.page.add(build_auth_page(self, role, mode))
        self.page.update()

    def login(self, account_id: str, password: str, role: str):
        try:
            self._ensure_client()
            profile = self.auth_service.login(account_id, password, role)
            self._enter_workspace(profile)
        except Exception as exc:
            log.warning("Login failed: %s", exc)
            raise BackendError(str(exc)) from exc

    def register(self, data: RegistrationData):
        try:
            self._ensure_client()
            profile = self.auth_service.register(data)
            self._enter_workspace(profile)
        except Exception as exc:
            log.warning("Registration failed: %s", exc)
            raise BackendError(str(exc)) from exc

    def request_password_reset(self, account_id: str, role: str):
        self._ensure_client()
        self.auth_service.request_password_reset(account_id, role)

    def _enter_workspace(self, profile: dict[str, Any]):
        self.profile = profile
        self.user_id = str(profile["id"])
        self.role = str(profile["role"]).upper()
        self.profile_service = ProfileService(self.client)
        self.audit_service = AuditService(self.client)
        self.attendance_service = AttendanceService(self.client, self.user_id, self.role)
        self.qr_service = QRService(self.client, self.user_id, self.role, self.settings)
        self.face_service = FaceBiometricService(self.client, self.user_id, self.role)
        self.fingerprint_service = FingerprintService(self.client, self.user_id, self.role, self.settings)
        if self.role == "TEACHER":
            self.teacher_service = TeacherService(self.client, self.user_id)
            self.student_service = None
            self.report_service = ReportService(self.settings, self.teacher_service, self.attendance_service)
        elif self.role == "STUDENT":
            self.student_service = StudentService(self.client, self.user_id, self.profile)
            self.teacher_service = None
            self.report_service = None
        else:
            self.show_portal()
            raise BackendError("This application only supports Teacher and Student roles.")
        try:
            from attendx.services.supabase_client import rpc
            rpc(self.client, "record_login_event", {})
        except Exception:
            log.exception("Login history event could not be recorded")
        self.current_page = "dashboard"
        self.preferred_schedule_id = None
        self.render_workspace()

    def navigate(self, page_key: str, *, selected_schedule: str | None = None):
        if not self.profile or self.role not in {"TEACHER", "STUDENT"}:
            self.show_portal()
            return
        allowed = {key for key, _, _ in (TEACHER_NAV if self.role == "TEACHER" else STUDENT_NAV)}
        if page_key not in allowed:
            self.notify("This page is not available for this account role.", error=True)
            return
        self._stop_hardware()
        self.current_page = page_key
        if selected_schedule:
            self.preferred_schedule_id = str(selected_schedule)
        else:
            self.preferred_schedule_id = None
        self.render_workspace()

    def render_workspace(self):
        try:
            nav = TEACHER_NAV if self.role == "TEACHER" else STUDENT_NAV
            width = float(getattr(self.page, "width", 1280) or 1280)
            nav_controls = []
            for key, label, icon_name in nav:
                is_selected = self.current_page == key
                icon_data = self._icon_data(icon_name)
                nav_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(icon_data, size=19, color=GOLD if is_selected else MUTED),
                            ft.Text(label, size=12, weight=ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL,
                                    color=WHITE if is_selected else MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ], spacing=11),
                        padding=ft.Padding(left=12, top=11, right=10, bottom=11),
                        border_radius=10,
                        bgcolor="#1A4267" if is_selected else None,
                        on_click=lambda _e, target=key: self.navigate(target),
                        ink=True,
                    )
                )
            sidebar = ft.Container(
                width=238,
                bgcolor=NAVY,
                padding=ft.Padding(left=14, top=18, right=14, bottom=14),
                content=ft.Column([
                    ft.Row([ft.Image(src="csu_logo.png", width=42, height=42), ft.Column([
                        ft.Text("ATTENDX", size=19, weight=ft.FontWeight.BOLD, color=WHITE),
                        ft.Text(f"{self.role.title()} Portal", size=11, color=GOLD),
                    ], spacing=0)], spacing=9),
                    ft.Container(height=1, bgcolor=BORDER),
                    ft.Column(nav_controls, spacing=3, scroll=ft.ScrollMode.AUTO, expand=True),
                    ft.Container(height=1, bgcolor=BORDER),
                    ft.Row([ft.Icon(self._icon_data("ACCOUNT_CIRCLE_ROUNDED"), color=CYAN), ft.Column([
                        ft.Text(self.full_name(), size=12, weight=ft.FontWeight.BOLD, color=WHITE, max_lines=1),
                        ft.Text(str(self.profile.get("account_id", "")), size=10, color=MUTED, max_lines=1),
                    ], spacing=2, expand=True)], spacing=8),
                    ft.Container(
                        content=ft.Row([ft.Icon(self._icon_data("LOGOUT_ROUNDED"), color=GOLD), ft.Text("Log Out", color=WHITE, weight=ft.FontWeight.BOLD)], spacing=10),
                        bgcolor=SURFACE_2, border_radius=10, padding=12, on_click=lambda _e: self.logout(), ink=True,
                    ),
                ], spacing=12, expand=True),
            )
            header = ft.Container(
                padding=ft.Padding(left=24, top=16, right=24, bottom=12),
                content=ft.Row([
                    ft.Column([
                        ft.Text(self._page_title(), size=22, weight=ft.FontWeight.BOLD, color=WHITE),
                        ft.Text(f"Cagayan State University · {datetime.now(ZoneInfo('Asia/Manila')).strftime('%A, %d %B %Y · %I:%M:%S %p')}", size=11, color=MUTED),
                    ], spacing=2, expand=True),
                    ft.Container(content=ft.Row([ft.Icon(self._icon_data("CLOUD_DONE_ROUNDED"), color=CYAN, size=17), ft.Text("Supabase session", size=11, color=CYAN)], spacing=7), border=ft.Border.all(1, BORDER), border_radius=20, padding=10),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            )
            page_content = build_teacher_page(self, self.current_page) if self.role == "TEACHER" else build_student_page(self, self.current_page)
            main_area = ft.Container(
                expand=True,
                bgcolor="#0A203A",
                content=ft.Column([
                    header,
                    ft.Container(content=page_content, padding=ft.Padding(left=22, top=4, right=22, bottom=22), expand=True),
                ], spacing=0, expand=True),
            )
            if width < 840:
                horizontal_nav = ft.Container(
                    bgcolor=NAVY,
                    padding=ft.Padding(left=8, top=8, right=8, bottom=8),
                    content=ft.Row([
                        ft.Container(content=ft.Column([ft.Icon(self._icon_data(icon_name), size=18, color=GOLD if self.current_page == key else MUTED),
                                                        ft.Text(label, size=9, color=WHITE if self.current_page == key else MUTED)], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                     padding=8, border_radius=8, bgcolor="#1A4267" if self.current_page == key else None,
                                     on_click=lambda _e, target=key: self.navigate(target), ink=True)
                        for key, label, icon_name in nav
                    ], scroll=ft.ScrollMode.AUTO, spacing=6),
                )
                root = ft.Column([horizontal_nav, main_area], expand=True, spacing=0)
            else:
                root = ft.Row([sidebar, ft.Container(content=main_area, expand=True)], spacing=0, expand=True)
            self.page.controls.clear()
            self.page.add(ft.Container(content=root, expand=True, bgcolor="#0A203A"))
            self.page.update()
        except Exception as exc:
            log.exception("Could not render %s page", self.current_page)
            self.page.controls.clear()
            self.page.add(ft.Container(expand=True, padding=24, content=ft.Column([
                ft.Icon(self._icon_data("ERROR_OUTLINE_ROUNDED"), size=42, color=GOLD),
                ft.Text("Page could not be loaded", size=22, weight=ft.FontWeight.BOLD, color=WHITE),
                ft.Text(safe_message(exc), color=MUTED, selectable=True),
                ft.Button("Retry", on_click=lambda _e: self.render_workspace()),
                ft.Button("Return to Portal", on_click=lambda _e: self.show_portal()),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12)))
            self.page.update()

    def refresh_current_page(self):
        self.render_workspace()

    def logout(self):
        self._stop_hardware()
        try:
            if self.auth_service:
                self.auth_service.sign_out()
        finally:
            self.client = None
            self.auth_service = None
            self.audit_service = None
            self.profile_service = None
            self.teacher_service = None
            self.student_service = None
            self.attendance_service = None
            self.qr_service = None
            self.face_service = None
            self.fingerprint_service = None
            self.report_service = None
            self.show_portal()

    def notify(self, message: str, *, error: bool = False):
        try:
            snack = ft.SnackBar(content=ft.Text(str(message), color=WHITE, selectable=True), bgcolor="#6B2933" if error else SURFACE_2)
            self.page.open(snack)
        except Exception:
            log.warning("UI notification: %s", message)

    def _stop_hardware(self):
        self.scan_running = False
        self.student_scan_running = False
        self.face_capture_running = False

    def today_manila(self) -> str:
        return datetime.now(ZoneInfo("Asia/Manila")).date().isoformat()

    def full_name(self) -> str:
        return self.profile_name(self.profile or {})

    @staticmethod
    def profile_name(profile: dict[str, Any]) -> str:
        return " ".join(filter(None, [profile.get("first_name"), profile.get("middle_name"), profile.get("last_name"), profile.get("suffix")])) or "AttendX User"

    def _page_title(self) -> str:
        nav = TEACHER_NAV if self.role == "TEACHER" else STUDENT_NAV
        return next((label for key, label, _ in nav if key == self.current_page), "AttendX")

    @staticmethod
    def _icon_data(name: str):
        return getattr(ft.Icons, name, ft.Icons.CIRCLE_OUTLINED)
