from __future__ import annotations

import asyncio
from typing import Any
import flet as ft

from attendx.services.supabase_client import BackendError, query_data
from attendx.ui.components import card, dropdown, empty_state, field, heading, primary_button, schedule_label, simple_table, stat_card, subtle_button, pill, divider
from attendx.ui.pages.attendance import build_teacher_attendance_center
from attendx.ui.pages.profile import build_profile_page
from attendx.ui.theme import CYAN, ERROR, GOLD, MUTED, SUCCESS, WHITE


def build_teacher_page(app, page_key: str) -> ft.Control:
    if page_key == "dashboard":
        return _dashboard(app)
    if page_key == "students":
        return _students(app)
    if page_key == "subjects":
        return _subjects(app)
    if page_key == "schedules":
        return _schedules(app)
    if page_key == "attendance":
        return build_teacher_attendance_center(app)
    if page_key == "records":
        return _records(app)
    if page_key == "reports":
        return _reports(app)
    if page_key == "profile":
        return build_profile_page(app)
    if page_key == "settings":
        return _settings(app)
    if page_key == "database":
        return _database_tools(app)
    return empty_state("Page not found", "Choose a page from the navigation panel.")


def _dashboard(app) -> ft.Control:
    schedules = app.teacher_service.my_schedules()
    students = app.teacher_service.students()
    summary = app.attendance_service.today_summary()
    today = app.today_manila()
    schedule_cards: list[ft.Control] = []
    for schedule in schedules[:8]:
        schedule_cards.append(card(ft.Row([
            ft.Container(ft.Icon(getattr(ft.Icons, "EVENT_AVAILABLE_ROUNDED", ft.Icons.CIRCLE_OUTLINED), color=CYAN, size=24), padding=12, bgcolor="#15395B", border_radius=12),
            ft.Column([
                ft.Text((schedule.get("subject") or {}).get("subject_name", "Subject"), size=15, weight=ft.FontWeight.BOLD, color=WHITE),
                ft.Text(schedule_label(schedule), size=12, color=MUTED),
            ], spacing=3, expand=True),
            subtle_button("Open", lambda _e, key=str(schedule["id"]): app.navigate("attendance", selected_schedule=key)),
        ], spacing=12), padding=14))
    if not schedule_cards:
        schedule_cards.append(empty_state("No schedules yet", "Add a subject, then create your first class schedule.", "EVENT_NOTE_ROUNDED"))
    return ft.Column([
        heading(f"Welcome, {app.full_name()}", f"Teacher workspace · {today} · attendance data from Supabase"),
        ft.ResponsiveRow([
            ft.Container(content=stat_card("My Schedules", len(schedules), "EVENT_NOTE_ROUNDED", CYAN), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Enrolled Students", len(students), "GROUP_ROUNDED", GOLD), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Today Records", summary["today"], "FACT_CHECK_ROUNDED", SUCCESS), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("This Week", summary["week"], "DATE_RANGE_ROUNDED", CYAN), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("This Month", summary["month"], "CALENDAR_MONTH_ROUNDED", GOLD), col={"xs": 12, "sm": 6, "md": 3}),
            ft.Container(content=stat_card("Late / Late Absent", f"{summary['late']} / {summary['late_absent']}", "SCHEDULE_ROUNDED", GOLD), col={"xs": 12, "sm": 6, "md": 3}),
        ], spacing=12, run_spacing=12),
        card(ft.Column([
            ft.Row([ft.Text("My Schedule", size=18, weight=ft.FontWeight.BOLD, color=WHITE), ft.Container(expand=True), subtle_button("Add Schedule", lambda _e: app.navigate("schedules"), icon="ADD_ROUNDED")]),
            *schedule_cards,
        ], spacing=10)),
        card(ft.Column([
            ft.Text("Attendance Summary", size=18, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.ResponsiveRow([
                ft.Container(ft.Row([pill("PRESENT", SUCCESS), ft.Text(str(summary["present"]), size=20, weight=ft.FontWeight.BOLD, color=WHITE)]), col={"xs": 6, "md": 3}),
                ft.Container(ft.Row([pill("LATE", GOLD), ft.Text(str(summary["late"]), size=20, weight=ft.FontWeight.BOLD, color=WHITE)]), col={"xs": 6, "md": 3}),
                ft.Container(ft.Row([pill("LATE ABSENT", ERROR), ft.Text(str(summary["late_absent"]), size=20, weight=ft.FontWeight.BOLD, color=WHITE)]), col={"xs": 6, "md": 3}),
                ft.Container(ft.Row([pill("ABSENT", ERROR), ft.Text(str(summary["absent"]), size=20, weight=ft.FontWeight.BOLD, color=WHITE)]), col={"xs": 6, "md": 3}),
            ], spacing=12, run_spacing=12),
            ft.Text("Absent records are generated only after a session reaches its scheduled end and is finalized.", size=11, color=MUTED),
        ], spacing=12)),
    ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)


def _students(app) -> ft.Control:
    students = app.teacher_service.students()
    search = field("Search by student name or Account ID")
    list_box = ft.Column(spacing=10)

    def render(query: str = ""):
        needle = (query or "").strip().lower()
        rows = []
        for student in students:
            full = app.profile_name(student).lower()
            if needle and needle not in full and needle not in student.get("account_id", "").lower():
                continue
            enrollment_controls = []
            for enrollment in student.get("enrollments", []):
                schedule = enrollment.get("schedule") or {}
                label = schedule_label(schedule) if schedule else f"Schedule #{enrollment.get('schedule_id')}"
                schedule_id = str(enrollment.get("schedule_id"))
                enrollment_controls.append(ft.Row([
                    ft.Text(label, size=12, color=MUTED, expand=True),
                    subtle_button("Remove Student", lambda _e, sid=student["id"], scid=schedule_id: _remove(sid, scid), icon="PERSON_REMOVE_ROUNDED"),
                ], wrap=True, spacing=8))
            rows.append(card(ft.Column([
                ft.Row([
                    ft.Container(ft.Icon(getattr(ft.Icons, "PERSON_ROUNDED", ft.Icons.CIRCLE_OUTLINED), color=CYAN, size=24), padding=10, bgcolor="#15395B", border_radius=12),
                    ft.Column([
                        ft.Text(app.profile_name(student), size=15, weight=ft.FontWeight.BOLD, color=WHITE),
                        ft.Text(f"Account ID: {student.get('account_id', '')} · {student.get('course', '')} {student.get('year_level', '')}-{student.get('section', '')}", size=12, color=MUTED),
                    ], spacing=3, expand=True),
                    pill(student.get("student_status", "ACTIVE"), SUCCESS if student.get("student_status") == "ACTIVE" else ERROR),
                ], spacing=12),
                divider(),
                ft.Text("Enrolled Schedules", weight=ft.FontWeight.BOLD, color=CYAN, size=12),
                *(enrollment_controls or [ft.Text("No schedule enrollment details.", color=MUTED, size=12)]),
            ], spacing=8), padding=15))
        list_box.controls = rows or [empty_state("No students found", "Students appear after they enroll in your schedule. Try another search term.", "GROUP_OFF_ROUNDED")]
        app.page.update()

    def _remove(student_id: str, schedule_id: str):
        try:
            app.teacher_service.remove_student_from_schedule(student_id, schedule_id)
            app.audit_service.record("student_removed_from_schedule", "class_enrollments", student_id, {"schedule_id": schedule_id})
            app.notify("Student removed from this schedule.")
            app.refresh_current_page()
        except Exception as exc:
            app.notify(str(exc), error=True)

    search.on_change = lambda e: render(e.control.value)
    render()
    return ft.Column([
        heading("My Students", "Students enrolled in schedules assigned to your teacher account."),
        search,
        ft.Text(f"{len(students)} unique student account(s) across your schedules", color=MUTED, size=12),
        list_box,
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _subjects(app) -> ft.Control:
    name = field("Subject Name", hint="e.g. Database Management")
    subjects_box = ft.Column(spacing=8)
    status = ft.Text("", color=GOLD, size=12)

    def refresh():
        try:
            subjects = app.teacher_service.subjects()
            subjects_box.controls = [card(ft.Row([
                ft.Icon(getattr(ft.Icons, "MENU_BOOK_ROUNDED", ft.Icons.CIRCLE_OUTLINED), color=CYAN),
                ft.Text(item.get("subject_name", ""), size=14, color=WHITE, weight=ft.FontWeight.BOLD, expand=True),
                pill("IN CATALOG", CYAN),
            ], spacing=10), padding=12) for item in subjects] or [empty_state("Subject catalog is empty", "Add your first subject using the form above.", "MENU_BOOK_ROUNDED")]
        except Exception as exc:
            subjects_box.controls = [ft.Text(str(exc), color=ERROR)]
        app.page.update()

    def add_subject(_e):
        try:
            item = app.teacher_service.add_subject(name.value or "")
            app.audit_service.record("subject_added", "subjects", str(item.get("id")), {"subject_name": item.get("subject_name")})
            name.value = ""
            status.value = "Subject added to the shared catalog."
            status.color = SUCCESS
            refresh()
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
            app.page.update()

    refresh()
    return ft.Column([
        heading("Subject Management", "Manage the shared subject catalog used by teacher schedules and student enrollment."),
        card(ft.Column([name, primary_button("Add Subject to Catalog", add_subject, icon="ADD_CIRCLE_ROUNDED"), status], spacing=10)),
        ft.Text("Available Subjects", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
        subjects_box,
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _schedules(app) -> ft.Control:
    subjects = app.teacher_service.subjects()
    subject_field = dropdown("Subject", [str(s["subject_name"]) for s in subjects], value=str(subjects[0]["subject_name"]) if subjects else None)
    subject_ids = {str(s["subject_name"]): str(s["id"]) for s in subjects}
    course = field("Course / Program")
    year = dropdown("Year", ["1", "2", "3", "4", "5", "6"])
    section = field("Section")
    day = dropdown("Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    start = field("Start Time (24-hour)", hint="08:00")
    end = field("End Time (24-hour)", hint="09:30")
    status = ft.Text("", color=GOLD, size=12)
    schedules_box = ft.Column(spacing=8)

    def refresh():
        try:
            schedules = app.teacher_service.my_schedules()
            cards = []
            for item in schedules:
                cards.append(card(ft.Row([
                    ft.Icon(getattr(ft.Icons, "EVENT_NOTE_ROUNDED", ft.Icons.CIRCLE_OUTLINED), color=CYAN, size=24),
                    ft.Column([
                        ft.Text((item.get("subject") or {}).get("subject_name", "Subject"), size=14, weight=ft.FontWeight.BOLD, color=WHITE),
                        ft.Text(schedule_label(item), size=12, color=MUTED),
                    ], spacing=3, expand=True),
                    subtle_button("Attendance", lambda _e, sid=str(item["id"]): app.navigate("attendance", selected_schedule=sid), icon="FACT_CHECK_ROUNDED"),
                    subtle_button("Archive", lambda _e, sid=str(item["id"]): _delete(sid), icon="ARCHIVE_OUTLINED"),
                ], wrap=True, spacing=8), padding=13))
            schedules_box.controls = cards or [empty_state("No schedules yet", "Complete the form above. Add a subject first if the list is empty.", "EVENT_NOTE_ROUNDED")]
        except Exception as exc:
            schedules_box.controls = [ft.Text(str(exc), color=ERROR)]
        app.page.update()

    def add_schedule(_e):
        try:
            if not subject_field.value or subject_field.value not in subject_ids:
                raise BackendError("Add a subject to the catalog before creating a schedule.")
            item = app.teacher_service.add_schedule(
                course=course.value or "", year_level=year.value or "", section=section.value or "",
                subject_id=subject_ids[subject_field.value], day=day.value or "",
                start_time=start.value or "", end_time=end.value or "",
            )
            app.audit_service.record("schedule_created", "schedules", str(item.get("id")), {"subject_id": item.get("subject_id")})
            status.value = "Schedule saved to Supabase."
            status.color = SUCCESS
            refresh()
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
            app.page.update()

    def _delete(schedule_id: str):
        try:
            app.teacher_service.delete_schedule(schedule_id)
            app.audit_service.record("schedule_archived", "schedules", schedule_id)
            app.notify("Schedule archived. Existing attendance records were preserved.")
            refresh()
        except Exception as exc:
            app.notify(str(exc), error=True)

    refresh()
    return ft.Column([
        heading("Class Schedules", "Add Subject and Add Schedule are kept as separate workflows. Archive schedules to preserve their attendance history."),
        card(ft.Column([
            ft.Text("Add Schedule", size=18, weight=ft.FontWeight.BOLD, color=WHITE),
            subject_field,
            ft.Row([course, year, section], spacing=10, wrap=True),
            ft.Row([day, start, end], spacing=10, wrap=True),
            primary_button("Save Schedule", add_schedule, icon="EVENT_AVAILABLE_ROUNDED"),
            status,
        ], spacing=12)),
        ft.Text("My Schedules", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
        schedules_box,
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _records(app) -> ft.Control:
    schedules = app.teacher_service.my_schedules()
    labels = ["All my schedules"] + [schedule_label(s) for s in schedules]
    schedule_ids = {schedule_label(s): str(s["id"]) for s in schedules}
    schedule_choice = dropdown("Schedule Filter", labels, value=labels[0])
    date_choice = field("Attendance Date (YYYY-MM-DD)", value=app.today_manila(), width=230)
    content = ft.Column(spacing=10)
    status = ft.Text("", color=GOLD, size=12)

    def load(_e=None):
        try:
            date_value = (date_choice.value or "").strip()
            if date_value:
                from datetime import date as date_type
                date_type.fromisoformat(date_value)
            schedule_id = schedule_ids.get(schedule_choice.value or "")
            rows = app.attendance_service.teacher_records(schedule_id=schedule_id, attendance_date=date_value or None, limit=1000)
            table_rows = []
            for record in rows:
                p = record.get("student", {})
                name = app.profile_name(p) if p else "Student"
                table_rows.append([name, record.get("attendance_date", ""), record.get("attendance_time", ""), record.get("status", ""), record.get("method", "")])
            content.controls = [simple_table(["Student", "Date", "Time", "Status", "Method"], table_rows, empty_message="No saved attendance records match these filters.")]
            status.value = f"Loaded {len(rows)} saved record(s)."
            status.color = CYAN
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()

    load()
    return ft.Column([
        heading("Attendance History & Verification", "View real attendance records returned by Supabase. Missing students are absent only after session finalization."),
        card(ft.Column([ft.Row([schedule_choice, date_choice], wrap=True, spacing=10), primary_button("Apply Filters", load, icon="FILTER_ALT_ROUNDED"), status], spacing=10)),
        content,
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _reports(app) -> ft.Control:
    schedules = app.teacher_service.my_schedules()
    report_date = field("Report Date (YYYY-MM-DD)", value=app.today_manila(), width=230)
    status = ft.Text("Exports are generated from real records and saved on this device in the exports folder.", color=MUTED, size=12)
    items = []

    def run_export(schedule_id: str, kind: str):
        try:
            from datetime import date
            date.fromisoformat((report_date.value or app.today_manila()).strip())
            target_date = (report_date.value or app.today_manila()).strip()
            if kind == "Excel": path = app.report_service.export_excel(schedule_id, target_date)
            elif kind == "CSV": path = app.report_service.export_csv(schedule_id, target_date)
            else: path = app.report_service.export_pdf(schedule_id, target_date)
            app.audit_service.record("report_exported", "schedules", schedule_id, {"format": kind})
            status.value = f"{kind} generated successfully: {path}"
            status.color = SUCCESS
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()

    for schedule in schedules:
        sid = str(schedule["id"])
        items.append(card(ft.Column([
            ft.Text((schedule.get("subject") or {}).get("subject_name", "Subject"), size=15, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text(schedule_label(schedule), size=12, color=MUTED),
            ft.Row([
                primary_button("Generate Excel", lambda _e, key=sid: run_export(key, "Excel"), icon="TABLE_VIEW_ROUNDED"),
                subtle_button("Export CSV", lambda _e, key=sid: run_export(key, "CSV"), icon="DOWNLOAD_ROUNDED"),
                subtle_button("Export PDF", lambda _e, key=sid: run_export(key, "PDF"), icon="PICTURE_AS_PDF_ROUNDED"),
            ], wrap=True, spacing=8),
        ], spacing=9), padding=14))
    return ft.Column([
        heading("Reports & Exports", "Generate a separate report for each schedule/subject from live attendance data."),
        card(ft.Column([report_date, status], spacing=8)),
        *(items or [empty_state("No subjects to export", "Create a schedule first. Reports appear for each schedule you own.", "DESCRIPTION_ROUNDED")]),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _settings(app) -> ft.Control:
    status = ft.Text("Run a server-side health check to validate the session, database role, and timezone.", color=MUTED, size=12)
    details = ft.Column(spacing=6)

    async def check(_e):
        try:
            result = await asyncio.to_thread(app.audit_service.health)
            status.value = "Supabase health check passed."
            status.color = SUCCESS
            details.controls = [ft.Text(f"{key}: {value}", color=WHITE, size=12) for key, value in result.items()]
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
        app.page.update()

    return ft.Column([
        heading("Settings & Connection", "Connection status is checked against Supabase; missing credentials never produce a fake connected state."),
        card(ft.Column([
            ft.Text("Backend Health", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
            status, primary_button("Test Supabase Connection", check, icon="CLOUD_SYNC_ROUNDED"), details,
        ], spacing=12)),
        card(ft.Column([
            ft.Text("Application Security", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("• Client uses a publishable/anon key only.\n• Role and row permissions are enforced by database RLS and secured RPCs.\n• Biometric descriptors are stored instead of raw face photos.\n• Camera and serial resources are released using EXIT.\n• Do not commit .env or real student exports.", color=MUTED, size=12),
        ], spacing=8)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _database_tools(app) -> ft.Control:
    health = ft.Text("Database check not yet run.", color=MUTED, size=12)
    table_info = ft.Column(spacing=8)
    async def verify(_e):
        try:
            result = await asyncio.to_thread(app.audit_service.health)
            counts = {
                "Your schedules": len(await asyncio.to_thread(app.teacher_service.my_schedules)),
                "Students in your schedules": len(await asyncio.to_thread(app.teacher_service.students)),
                "Recent attendance records": len(await asyncio.to_thread(app.attendance_service.teacher_records, None, app.today_manila(), 1000)),
            }
            health.value = f"Database reachable · schema {result.get('schema_version', 'unknown')} · role {result.get('role', app.role)}"
            health.color = SUCCESS
            table_info.controls = [ft.Row([ft.Icon(getattr(ft.Icons, "CHECK_CIRCLE_ROUNDED", ft.Icons.CIRCLE_OUTLINED), color=SUCCESS), ft.Text(f"{key}: {value}", color=WHITE, size=13)]) for key, value in counts.items()]
            table_info.controls.append(ft.Text("For student-record privacy, this utility verifies permitted data only; it does not expose unrestricted database rows or credentials.", color=MUTED, size=11))
        except Exception as exc:
            health.value = str(exc)
            health.color = ERROR
        app.page.update()
    return ft.Column([
        heading("Database Management / Verification", "Safe backend verification replacing the old local SQLite table viewer."),
        card(ft.Column([health, primary_button("Verify Database Access", verify, icon="FACT_CHECK_ROUNDED"), table_info], spacing=12)),
        card(ft.Column([
            ft.Text("Migration safety", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("The supplied SQLite files are not uploaded automatically. Use scripts/export_sqlite_migration.py to create a sanitized local migration pack. Password hashes, QR tokens, face descriptors, and fingerprint identifiers are excluded.", size=12, color=MUTED),
        ], spacing=8)),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
