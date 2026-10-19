from __future__ import annotations

import asyncio
import flet as ft

from attendx.services.supabase_client import BackendError
from attendx.ui.components import card, dropdown, empty_state, field, heading, primary_button, schedule_label, simple_table, stat_card, subtle_button, pill
from attendx.ui.pages.attendance import build_student_session_scanner, register_face_capture
from attendx.ui.pages.profile import build_profile_page
from attendx.ui.theme import CYAN, ERROR, GOLD, MUTED, SUCCESS, WHITE


def build_student_page(app, page_key: str) -> ft.Control:
    if page_key == "dashboard": return _dashboard(app)
    if page_key == "subjects": return _available_subjects(app)
    if page_key == "schedule": return _schedule(app)
    if page_key == "attendance": return _attendance_history(app)
    if page_key == "qr_pass": return _qr_pass(app)
    if page_key == "scan_session": return build_student_session_scanner(app)
    if page_key == "face": return _face_registration(app)
    if page_key == "fingerprint": return _fingerprint_registration(app)
    if page_key == "profile": return build_profile_page(app)
    if page_key == "settings": return _settings(app)
    return empty_state("Page not found", "Choose a page from the navigation panel.")


def _dashboard(app) -> ft.Control:
    schedules = app.student_service.my_schedules()
    summary = app.student_service.attendance_summary()
    schedule_cards = []
    for schedule in schedules[:6]:
        schedule_cards.append(card(ft.Row([
            ft.Container(ft.Icon(ft.Icons.EVENT_AVAILABLE_ROUNDED, color=CYAN, size=22), padding=10, bgcolor="#15395B", border_radius=11),
            ft.Column([
                ft.Text((schedule.get("subject") or {}).get("subject_name", "Subject"), size=14, weight=ft.FontWeight.BOLD, color=WHITE),
                ft.Text(schedule_label(schedule), size=12, color=MUTED),
            ], spacing=3, expand=True),
        ], spacing=10), padding=12))
    return ft.Column([
        heading(f"Welcome, {app.full_name()}", f"Student workspace · {app.today_manila()}"),
        ft.ResponsiveRow([
            ft.Container(content=stat_card("Attendance Rate", f"{summary['percentage']}%", ft.Icons.PERCENT_ROUNDED, CYAN), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Present", summary["present"], ft.Icons.CHECK_CIRCLE_ROUNDED, SUCCESS), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Late", summary["late"], ft.Icons.SCHEDULE_ROUNDED, GOLD), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Absent / Late Absent", summary["absent"] + summary["late_absent"], ft.Icons.ERROR_OUTLINE_ROUNDED, ERROR), col={"xs": 12, "sm": 6, "md": 3}),
        ], spacing=12, run_spacing=12),
        card(ft.Column([
            ft.Row([ft.Text("My Subjects & Schedule", size=18, weight=ft.FontWeight.BOLD, color=WHITE), ft.Container(expand=True), subtle_button("Add Subject", lambda _e: app.navigate("subjects"), icon="ADD_ROUNDED")]),
            *(schedule_cards or [empty_state("No enrolled subjects", "Use Add Subject to join a subject/class schedule.", "MENU_BOOK_ROUNDED")]),
        ], spacing=10)),
    ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)


def _available_subjects(app) -> ft.Control:
    schedules = app.student_service.available_schedules()
    search = field("Search by subject, course, year, section, or teacher")
    list_box = ft.Column(spacing=10)

    def render(query: str = ""):
        needle = (query or "").strip().lower()
        cards = []
        for schedule in schedules:
            label = schedule_label(schedule)
            teacher = schedule.get("teacher") or {}
            text = f"{label} {teacher.get('first_name', '')} {teacher.get('last_name', '')}".lower()
            if needle and needle not in text:
                continue
            cards.append(card(ft.Column([
                ft.Text((schedule.get("subject") or {}).get("subject_name", "Subject"), size=15, weight=ft.FontWeight.BOLD, color=WHITE),
                ft.Text(label, size=12, color=MUTED),
                primary_button("Enroll in This Subject", lambda _e, sid=str(schedule["id"]): _enroll(sid), icon="PERSON_ADD_ROUNDED"),
            ], spacing=8), padding=14))
        list_box.controls = cards or [empty_state("No available schedules", "All visible schedules are already enrolled, or the teacher has not published a schedule yet.", "SEARCH_OFF_ROUNDED")]
        app.page.update()

    def _enroll(schedule_id: str):
        try:
            app.student_service.enroll(schedule_id)
            app.audit_service.record("student_enrolled", "class_enrollments", schedule_id, {})
            app.notify("Enrollment saved. The class is now in My Schedule.")
            app.refresh_current_page()
        except Exception as exc:
            app.notify(str(exc), error=True)

    search.on_change = lambda e: render(e.control.value)
    render()
    return ft.Column([
        heading("Add Subject", "Browse real active schedules and enroll in one subject/class at a time."),
        search,
        list_box,
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _schedule(app) -> ft.Control:
    schedules = app.student_service.my_schedules()
    cards = []
    for schedule in schedules:
        teacher = schedule.get("teacher") or {}
        teacher_name = " ".join(filter(None, [teacher.get("first_name"), teacher.get("middle_name"), teacher.get("last_name")])) or "Teacher"
        cards.append(card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.EVENT_NOTE_ROUNDED, color=CYAN, size=24), ft.Text((schedule.get("subject") or {}).get("subject_name", "Subject"), size=15, weight=ft.FontWeight.BOLD, color=WHITE, expand=True)]),
            ft.Text(schedule_label(schedule), color=MUTED, size=12),
            ft.Text(f"Teacher: {teacher_name}", color=MUTED, size=12),
            subtle_button("Remove Subject", lambda _e, sid=str(schedule["id"]): _unenroll(app, sid), icon="REMOVE_CIRCLE_OUTLINE_ROUNDED"),
        ], spacing=8), padding=14))
    return ft.Column([
        heading("My Schedule", "Your enrolled class schedules and subject information."),
        *(cards or [empty_state("No schedules", "Enroll in a subject first from Add Subject.", "EVENT_NOTE_ROUNDED")]),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _unenroll(app, schedule_id: str):
    try:
        app.student_service.unenroll(schedule_id)
        app.audit_service.record("student_unenrolled", "class_enrollments", schedule_id, {})
        app.notify("You have been removed from this subject schedule.")
        app.refresh_current_page()
    except Exception as exc:
        app.notify(str(exc), error=True)


def _attendance_history(app) -> ft.Control:
    records = app.student_service.attendance_records()
    rows = []
    for record in records:
        schedule = record.get("schedule") or {}
        subject = (schedule.get("subject") or {}).get("subject_name", "Subject")
        rows.append([subject, record.get("attendance_date", ""), record.get("attendance_time", ""), record.get("status", ""), record.get("method", "")])
    summary = app.student_service.attendance_summary()
    return ft.Column([
        heading("My Attendance", "Personal attendance history and status summary."),
        ft.ResponsiveRow([
            ft.Container(content=stat_card("Total Records", summary["total"], ft.Icons.FACT_CHECK_ROUNDED), col={"xs": 6, "md": 3}),
            ft.Container(content=stat_card("Present", summary["present"], ft.Icons.CHECK_CIRCLE_ROUNDED, SUCCESS), col={"xs": 6, "md": 3}),
            ft.Container(content=stat_card("Late", summary["late"], ft.Icons.SCHEDULE_ROUNDED, GOLD), col={"xs": 6, "md": 3}),
            ft.Container(content=stat_card("Absent", summary["absent"] + summary["late_absent"], ft.Icons.ERROR_OUTLINE_ROUNDED, ERROR), col={"xs": 6, "md": 3}),
        ], spacing=12, run_spacing=12),
        card(simple_table(["Subject", "Date", "Time", "Status", "Method"], rows, empty_message="No attendance records are available yet."), padding=10),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _qr_pass(app) -> ft.Control:
    schedules = app.student_service.my_schedules()
    labels = [schedule_label(s) for s in schedules]
    schedule_ids = {schedule_label(s): str(s["id"]) for s in schedules}
    choice = dropdown("Class / Subject", labels, value=labels[0] if labels else None)
    preview = ft.Image(src="", width=250, height=250, fit=ft.BoxFit.CONTAIN)
    status = ft.Text("Generate a QR pass for one enrolled class. The pass is valid only for that class.", color=MUTED, size=12)

    async def generate(_e):
        try:
            if not choice.value or choice.value not in schedule_ids:
                raise BackendError("Enroll in a subject before generating a QR pass.")
            _token, data_uri = await asyncio.to_thread(app.qr_service.issue_student_pass, schedule_ids[choice.value])
            preview.src = data_uri
            status.value = "QR pass generated. Show this code to the teacher's scanner for the selected class."
            status.color = SUCCESS
            app.audit_service.record("student_qr_pass_issued", "qr_tokens", schedule_ids[choice.value], {})
            app.page.update()
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
            app.page.update()

    return ft.Column([
        heading("My QR Pass", "QR passes are specific to an enrolled schedule; only token hashes are stored in Supabase."),
        card(ft.Column([
            choice,
            primary_button("Generate / Refresh QR Pass", generate, icon="QR_CODE_2_ROUNDED"),
            status,
            ft.Container(content=preview, alignment=ft.Alignment.CENTER, bgcolor="#FFFFFF", border_radius=14, padding=12),
            ft.Text("If you refresh or leave this page, generate a new pass if the raw token is no longer available.", color=MUTED, size=11),
        ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _face_registration(app) -> ft.Control:
    preview = ft.Image(src="", width=540, height=330, fit=ft.BoxFit.CONTAIN)
    status = ft.Text("The system stores a face descriptor, not the camera image. Keep exactly one face visible.", color=MUTED, size=12)
    app.face_capture_running = False

    async def start(_e):
        if app.face_capture_running:
            return
        await register_face_capture(app, preview, status, None)

    def stop(_e):
        app.face_capture_running = False
        status.value = "Stopping camera…"
        app.page.update()

    async def check_registration(_e):
        try:
            has_face = await asyncio.to_thread(app.face_service.has_own_face)
            status.value = "A face template is currently registered for this account." if has_face else "No face template is registered for this account."
            status.color = CYAN
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()

    async def delete_registration(_e):
        try:
            await asyncio.to_thread(app.face_service.delete_own_face)
            app.audit_service.record("face_template_deleted", "face_templates", app.user_id, {})
            status.value = "Face template deleted. Re-register before face attendance can recognize you."
            status.color = SUCCESS
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()

    return ft.Column([
        heading("Face Recognition Setup", "Desktop camera and native face-recognition dependencies are required."),
        card(ft.Column([
            ft.Row([
                primary_button("Start Camera & Register", start, icon="FACE_RETOUCHING_NATURAL_ROUNDED"),
                subtle_button("EXIT / Stop Camera", stop, icon="CLOSE_ROUNDED"),
            ], wrap=True, spacing=10),
            ft.Row([subtle_button("Check Registration", check_registration), subtle_button("Delete My Face Template", delete_registration, icon="DELETE_OUTLINE_ROUNDED")], wrap=True, spacing=10),
            status,
            ft.Container(content=preview, bgcolor="#06162A", border_radius=12, padding=6, alignment=ft.Alignment.CENTER),
            ft.Text("Privacy: raw video stays in memory on this device. Only a 128-number face descriptor is stored centrally, under RLS; teachers can access descriptors only for students in their schedules.", color=MUTED, size=11),
        ], spacing=12)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _fingerprint_registration(app) -> ft.Control:
    finger = dropdown("Finger Label", ["Right Index", "Left Index", "Right Thumb", "Left Thumb", "Right Middle", "Left Middle", "Right Ring", "Left Ring", "Right Little", "Left Little"])
    status = ft.Text("This requires a compatible external AS608/R307 USB-to-serial reader. A phone's built-in sensor is not available to the app.", color=MUTED, size=12)
    async def device_check(_e):
        result = await asyncio.to_thread(app.fingerprint_service.hardware.check_device)
        if result.get("available"):
            status.value = f"Reader connected on {result['port']} · templates {result['templates']} / {result['capacity']}"
            status.color = SUCCESS
        else:
            status.value = result.get("message", "Reader unavailable.")
            status.color = ERROR
        app.page.update()
    async def register(_e):
        try:
            if not finger.value:
                raise BackendError("Select a finger label first.")
            status.value = "Follow the sensor prompt: place and lift the same finger as instructed."
            status.color = CYAN
            app.page.update()
            template_id = await asyncio.to_thread(app.fingerprint_service.register_own_fingerprint, finger.value)
            app.audit_service.record("fingerprint_registered", "fingerprint_credentials", app.user_id, {"finger_name": finger.value, "template_id": template_id})
            status.value = f"Fingerprint mapping saved for sensor template #{template_id}."
            status.color = SUCCESS
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()
    return ft.Column([
        heading("Fingerprint Setup", "Use a physical reader connected to the computer through a compatible USB-to-serial adapter."),
        card(ft.Column([
            finger,
            ft.Row([subtle_button("Check Reader", device_check, icon="USB_ROUNDED"), primary_button("Enroll Fingerprint", register, icon="FINGERPRINT_ROUNDED")], wrap=True, spacing=10),
            status,
            ft.Text("No fingerprint is read from the mobile phone's internal sensor. The sensor stores its own template; AttendX stores only the sensor's template ID and finger label.", color=MUTED, size=11),
        ], spacing=12)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _settings(app) -> ft.Control:
    health = ft.Text("Connection not checked yet.", color=MUTED, size=12)
    async def check(_e):
        try:
            value = await asyncio.to_thread(app.audit_service.health)
            health.value = f"Supabase connected · role {value.get('role')} · timezone {value.get('timezone')} · schema {value.get('schema_version')}"
            health.color = SUCCESS
        except Exception as exc:
            health.value = str(exc)
            health.color = ERROR
        app.page.update()
    return ft.Column([
        heading("Settings", "Review the live backend and privacy settings."),
        card(ft.Column([health, primary_button("Test Supabase Connection", check, icon="CLOUD_SYNC_ROUNDED")], spacing=12)),
        card(ft.Column([
            ft.Text("Attendance Rules", size=16, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("Pre-start scans are rejected. Present: exactly at the scheduled start. Late: after start through start+14:59. Late Absent: at start+15:00 or later. Absent: inserted at/after session end during finalization if no valid record exists.", color=MUTED, size=12),
            ft.Text("Timezone: Asia/Manila. Duplicate attendance is blocked at the database level for each student, schedule, and date.", color=MUTED, size=12),
        ], spacing=8)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
