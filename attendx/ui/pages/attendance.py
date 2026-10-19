from __future__ import annotations

import asyncio
import time
from typing import Any
import flet as ft

from attendx.services.supabase_client import BackendError
from attendx.ui.components import card, dropdown, heading, primary_button, schedule_label, simple_table, subtle_button, pill
from attendx.ui.theme import CYAN, ERROR, GOLD, MUTED, SUCCESS, WHITE


def build_teacher_attendance_center(app) -> ft.Control:
    schedules = app.teacher_service.my_schedules()
    preferred = next((s for s in schedules if str(s.get("id")) == str(getattr(app, "preferred_schedule_id", ""))), None)
    initial_schedule = preferred or (schedules[0] if schedules else None)
    choice = dropdown("Select Schedule", [schedule_label(s) for s in schedules], value=schedule_label(initial_schedule) if initial_schedule else None)
    id_by_label = {schedule_label(s): str(s["id"]) for s in schedules}
    selected_text = ft.Text("Select one of your class schedules before scanning attendance.", color=MUTED, size=12)
    camera_preview = ft.Image(width=540, height=330, fit=ft.BoxFit.CONTAIN, src="")
    camera_status = ft.Text("Camera is stopped.", color=MUTED, size=12)
    scan_results = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=240)
    app.scan_running = False
    manual_student = dropdown("Student to enroll fingerprint", [], value=None)
    manual_student_ids: dict[str, str] = {}

    def load_manual_roster(schedule_id: str) -> None:
        nonlocal manual_student_ids
        try:
            enrollments = app.teacher_service.class_enrollments(schedule_id)
            options = []
            mapping: dict[str, str] = {}
            for enrollment in enrollments:
                profile = enrollment.get("student", {})
                name = " ".join(filter(None, [profile.get("first_name"), profile.get("middle_name"), profile.get("last_name"), profile.get("suffix")]))
                label = f"{name or 'Student'} · {profile.get('account_id', enrollment.get('student_id', ''))}"
                options.append(label)
                mapping[label] = str(enrollment["student_id"])
            manual_student.options = [ft.DropdownOption(key=item, text=item) for item in options]
            manual_student.value = options[0] if options else None
            manual_student_ids = mapping
        except Exception as exc:
            manual_student.options = []
            manual_student.value = None
            manual_student_ids = {}
            app.notify(f"Could not load the student roster: {exc}", error=True)

    def selected_schedule_id() -> str:
        if not choice.value or choice.value not in id_by_label:
            raise BackendError("Create or select a schedule before starting attendance.")
        return id_by_label[choice.value]

    def update_live_records(schedule_id: str):
        try:
            records = app.attendance_service.teacher_records(schedule_id=schedule_id, limit=100)
            records = [r for r in records if r.get("attendance_date") == app.today_manila()]
            rows = []
            for record in records:
                p = record.get("student", {})
                name = " ".join(filter(None, [p.get("first_name"), p.get("middle_name"), p.get("last_name"), p.get("suffix")]))
                rows.append([name or p.get("account_id", "Student"), record.get("attendance_time", ""), record.get("status", ""), record.get("method", "")])
            scan_results.controls = [simple_table(["Student", "Time", "Status", "Method"], rows, empty_message="No attendance scans recorded for this schedule today.")]
        except Exception as exc:
            scan_results.controls = [ft.Text(str(exc), color=GOLD, size=12)]

    async def scan_qr(_e):
        try:
            schedule_id = selected_schedule_id()
            if app.scan_running:
                return
            camera = await asyncio.to_thread(app.camera_service.open)
            app.scan_running = True
            camera_status.value = "Scanning student QR passes · press EXIT to release the camera."
            camera_status.color = SUCCESS
            app.page.update()
            import cv2
            detector = cv2.QRCodeDetector()
            last_seen: dict[str, float] = {}
            try:
                while app.scan_running:
                    ok, frame = await asyncio.to_thread(camera.read)
                    if not ok:
                        camera_status.value = "Camera frame unavailable. The camera may have been disconnected."
                        camera_status.color = ERROR
                        break
                    frame = cv2.flip(frame, 1)
                    data, points, _straight = detector.detectAndDecode(frame)
                    if points is not None:
                        pts = points.astype(int).reshape(-1, 2)
                        for idx, point in enumerate(pts):
                            next_point = pts[(idx + 1) % len(pts)]
                            cv2.line(frame, tuple(point), tuple(next_point), (48, 200, 130), 2)
                    camera_preview.src = "data:image/jpeg;base64," + app.camera_service.to_base64(frame)
                    camera_preview.update()
                    if data:
                        now = time.monotonic()
                        if now - last_seen.get(data, 0) >= 2.5:
                            last_seen[data] = now
                            try:
                                outcome = await asyncio.to_thread(app.attendance_service.record_qr, data.strip(), schedule_id)
                                scan_results.controls.insert(0, ft.Row([
                                    pill(outcome.get("status", "RECORDED"), SUCCESS),
                                    ft.Text(outcome.get("message", "Attendance recorded."), color=WHITE, size=12),
                                ], spacing=8))
                                update_live_records(schedule_id)
                                app.page.update()
                            except Exception as exc:
                                scan_results.controls.insert(0, ft.Row([
                                    pill("NOT RECORDED", ERROR), ft.Text(str(exc), color=GOLD, size=12, selectable=True)
                                ], spacing=8))
                                app.page.update()
                    await asyncio.sleep(0.025)
            finally:
                app.scan_running = False
                camera.release()
                camera_preview.src = ""
                camera_status.value = "Camera stopped and released. Saved attendance records were not changed."
                camera_status.color = MUTED
                app.page.update()
        except Exception as exc:
            app.scan_running = False
            app.notify(str(exc), error=True)

    async def scan_face(_e):
        try:
            schedule_id = selected_schedule_id()
            if app.scan_running:
                return
            if not app.face_service.is_available():
                raise BackendError("Face recognition is not installed. Install face-recognition/dlib for this desktop OS and retry.")
            templates = await asyncio.to_thread(app.face_service.templates_for_current_classes, schedule_id)
            enrolled = {e["student_id"] for e in app.teacher_service.class_enrollments(schedule_id)}
            templates = [t for t in templates if t.get("student_id") in enrolled]
            if not templates:
                raise BackendError("No authorized enrolled students have registered face descriptors for this schedule.")
            camera = await asyncio.to_thread(app.camera_service.open)
            app.scan_running = True
            camera_status.value = "Face attendance is running · keep one face clearly visible · press EXIT to stop."
            camera_status.color = SUCCESS
            app.page.update()
            import cv2
            import face_recognition
            from attendx.services.biometric_service import FaceBiometricService
            known = {t["student_id"]: t["embedding"] for t in templates}
            cooldown: dict[str, float] = {}
            used_in_frame: set[str] = set()
            frame_count = 0
            try:
                while app.scan_running:
                    ok, frame = await asyncio.to_thread(camera.read)
                    if not ok:
                        camera_status.value = "Camera frame unavailable."
                        break
                    frame = cv2.flip(frame, 1)
                    frame_count += 1
                    if frame_count % 4 == 0:
                        small_rgb = app.camera_service.to_rgb_small(frame, 0.25)
                        locations = await asyncio.to_thread(face_recognition.face_locations, small_rgb, model="hog")
                        encodings = await asyncio.to_thread(face_recognition.face_encodings, small_rgb, locations)
                        used_in_frame = set()
                        for encoding in encodings:
                            match = FaceBiometricService.best_match(encoding.tolist(), templates, tolerance=0.43)
                            if not match:
                                continue
                            student_id, distance = match
                            now = time.monotonic()
                            if student_id in used_in_frame or now - cooldown.get(student_id, 0) < 5:
                                continue
                            used_in_frame.add(student_id)
                            cooldown[student_id] = now
                            try:
                                outcome = await asyncio.to_thread(app.attendance_service.record_biometric, student_id, schedule_id, "FACE")
                                scan_results.controls.insert(0, ft.Row([
                                    pill(outcome.get("status", "RECORDED"), SUCCESS),
                                    ft.Text(f"Face matched (distance {distance:.3f}). {outcome.get('message', '')}", color=WHITE, size=12),
                                ], spacing=8))
                                update_live_records(schedule_id)
                            except Exception as exc:
                                scan_results.controls.insert(0, ft.Row([pill("NOT RECORDED", ERROR), ft.Text(str(exc), color=GOLD, size=12)], spacing=8))
                    camera_preview.src = "data:image/jpeg;base64," + app.camera_service.to_base64(frame)
                    camera_preview.update()
                    if frame_count % 4 == 0:
                        app.page.update()
                    await asyncio.sleep(0.015)
            finally:
                app.scan_running = False
                camera.release()
                camera_preview.src = ""
                camera_status.value = "Camera stopped and released."
                camera_status.color = MUTED
                app.page.update()
        except Exception as exc:
            app.scan_running = False
            app.notify(str(exc), error=True)

    async def scan_fingerprint(_e):
        try:
            schedule_id = selected_schedule_id()
            if app.scan_running:
                return
            if not app.fingerprint_service.hardware.is_installed():
                raise BackendError("Fingerprint support is not installed. Install the optional reader dependencies with: pip install -r requirements-fingerprint.txt")
            enrolled = {str(row["student_id"]) for row in await asyncio.to_thread(app.teacher_service.class_enrollments, schedule_id)}
            if not enrolled:
                raise BackendError("No students are enrolled in this class schedule.")
            device = await asyncio.to_thread(app.fingerprint_service.hardware.check_device)
            if not device.get("available"):
                raise BackendError(str(device.get("message") or f"Fingerprint reader is not available on {device.get('port', 'the configured port')}."))
            app.scan_running = True
            camera_status.value = f"Fingerprint reader connected on {device.get('port')} · scan one finger at a time · press EXIT to stop."
            camera_status.color = SUCCESS
            app.page.update()
            last_position = None
            last_seen_at = 0.0
            try:
                while app.scan_running:
                    match = await asyncio.to_thread(app.fingerprint_service.hardware.identify, 3)
                    if match:
                        position, score = match
                        now = time.monotonic()
                        if now - last_seen_at > 2.5 or position != last_position:
                            last_seen_at, last_position = now, position
                            try:
                                verified = await asyncio.to_thread(
                                    app.fingerprint_service.verify_sensor_position, schedule_id, position
                                )
                                student = verified.get("student", {})
                                student_id = str(student.get("id", ""))
                                if not student_id or student_id not in enrolled:
                                    raise BackendError("The fingerprint is not assigned to an enrolled student in this class.")
                                outcome = await asyncio.to_thread(
                                    app.attendance_service.record_biometric, student_id, schedule_id, "FINGERPRINT"
                                )
                                name = student.get("name") or "Student"
                                scan_results.controls.insert(0, ft.Row([
                                    pill(outcome.get("status", "RECORDED"), SUCCESS),
                                    ft.Text(f"{name} · Fingerprint verified (score {score}). {outcome.get('message', '')}", color=WHITE, size=12),
                                ], spacing=8))
                                update_live_records(schedule_id)
                            except Exception as exc:
                                scan_results.controls.insert(0, ft.Row([
                                    pill("NOT RECORDED", ERROR), ft.Text(str(exc), color=GOLD, size=12, selectable=True)
                                ], spacing=8))
                            app.page.update()
                    await asyncio.sleep(0.05)
            finally:
                app.scan_running = False
                camera_status.value = "Fingerprint scanning stopped. Saved attendance records were not changed."
                camera_status.color = MUTED
                app.page.update()
        except Exception as exc:
            app.scan_running = False
            camera_status.value = str(exc)
            camera_status.color = ERROR
            app.page.update()

    async def finalize_session(_e):
        try:
            schedule_id = selected_schedule_id()
            result = await asyncio.to_thread(app.attendance_service.finalize_schedule, schedule_id)
            selected_text.value = result.get("message", "Attendance finalized.")
            update_live_records(schedule_id)
            app.page.update()
            app.notify(selected_text.value)
        except Exception as exc:
            app.notify(str(exc), error=True)

    async def enroll_fingerprint(_e):
        try:
            schedule_id = selected_schedule_id()
            label = manual_student.value
            student_id = manual_student_ids.get(label or "")
            if not student_id:
                raise BackendError("Select an enrolled student from the roster first.")
            camera_status.value = "Follow the fingerprint reader prompts and scan the same finger twice."
            camera_status.color = CYAN
            app.page.update()
            template_position = await asyncio.to_thread(
                app.fingerprint_service.register_student_fingerprint, student_id, schedule_id
            )
            app.audit_service.record(
                "fingerprint_registered", "fingerprint_templates", student_id,
                {"schedule_id": schedule_id, "sensor_template_id": template_position}
            )
            app.notify(f"Fingerprint mapping saved for the selected student (reader template #{template_position}).")
            camera_status.value = f"Fingerprint enrolled · sensor template #{template_position}."
            camera_status.color = SUCCESS
            app.page.update()
        except Exception as exc:
            camera_status.value = str(exc)
            camera_status.color = ERROR
            app.page.update()
            app.notify(str(exc), error=True)

    def stop_scan(_e):
        app.scan_running = False
        camera_status.value = "Stopping active scanner/reader…"
        app.page.update()

    if schedules and initial_schedule:
        update_live_records(str(initial_schedule["id"]))
        load_manual_roster(str(initial_schedule["id"]))
    def refresh_records():
        if choice.value in id_by_label:
            schedule_id = selected_schedule_id()
            update_live_records(schedule_id)
            app.page.update()

    def on_schedule_change(_e):
        if choice.value in id_by_label:
            schedule_id = selected_schedule_id()
            update_live_records(schedule_id)
            load_manual_roster(schedule_id)
    choice.on_select = on_schedule_change

    return ft.Column([
        heading("Attendance Center", "Select one of your class schedules, then verify enrolled students using QR, face recognition, or a supported fingerprint reader."),
        card(ft.Column([
            ft.Text("Class & attendance controls", size=17, weight=ft.FontWeight.BOLD, color=WHITE),
            choice,
            selected_text,
            ft.Text("QR workflow: open the student's QR Pass page and generate the pass for this exact class. Then choose Scan Student QR below. This uses the existing AttendX-Web QR verification service.", size=12, color=MUTED),
            ft.Row([
                subtle_button("Refresh Attendance List", lambda _e: refresh_records(), icon="REFRESH_ROUNDED"),
                subtle_button("Finalize & Mark Missing Absent", finalize_session, icon="FACT_CHECK_ROUNDED"),
            ], wrap=True, spacing=10),
        ], spacing=12)),
        card(ft.Column([
            ft.Text("Attendance Verification", size=18, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("Choose one method. The scanner remains active for multiple students until you press EXIT. Only server-confirmed attendance appears in the saved list.", size=12, color=MUTED),
            ft.Row([
                primary_button("Scan Student QR", scan_qr, icon="QR_CODE_SCANNER_ROUNDED"),
                subtle_button("Start Face Recognition", scan_face, icon="FACE_RETOUCHING_NATURAL_ROUNDED"),
                subtle_button("Start Fingerprint Reader", scan_fingerprint, icon="FINGERPRINT_ROUNDED"),
                subtle_button("EXIT / Stop Scanner", stop_scan, icon="CLOSE_ROUNDED"),
            ], wrap=True, spacing=10),
            camera_status,
            ft.Container(content=camera_preview, bgcolor="#06162A", border_radius=12, padding=6, alignment=ft.Alignment.CENTER),
            ft.Text("Hardware notes: Face attendance requires the optional desktop face-recognition package and a registered compatible Flet face template. Fingerprint attendance requires a supported AS608/R307 serial reader connected to this computer; a phone/laptop built-in fingerprint sensor is not supported.", size=11, color=MUTED),
        ], spacing=12)),
        card(ft.Column([
            ft.Text("Fingerprint Enrollment", size=18, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("Select an enrolled student from the roster, connect the configured reader, and scan the same finger twice. Use the same reader/COM port when taking attendance.", size=12, color=MUTED),
            manual_student,
            subtle_button("Enroll Selected Student Fingerprint", enroll_fingerprint, icon="FINGERPRINT_ROUNDED"),
        ], spacing=10)),
        card(ft.Column([
            ft.Text("Live Attendance List", size=18, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("Latest records are loaded from Supabase for the selected schedule and today's Manila date.", size=12, color=MUTED),
            scan_results,
        ], spacing=10)),
    ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)


def build_student_session_scanner(app) -> ft.Control:
    preview = ft.Image(width=520, height=320, src="", fit=ft.BoxFit.CONTAIN)
    status = ft.Text("Start the scanner and point it at your teacher's active Session QR.", color=MUTED, size=12)
    app.student_scan_running = False

    async def scan(_e):
        if app.student_scan_running:
            return
        try:
            camera = await asyncio.to_thread(app.camera_service.open)
            app.student_scan_running = True
            status.value = "Scanning active class QR. Press EXIT to stop."
            app.page.update()
            import cv2
            detector = cv2.QRCodeDetector()
            last_token, last_time = "", 0.0
            try:
                while app.student_scan_running:
                    ok, frame = await asyncio.to_thread(camera.read)
                    if not ok:
                        status.value = "Camera frame unavailable."
                        break
                    frame = cv2.flip(frame, 1)
                    data, _points, _straight = detector.detectAndDecode(frame)
                    preview.src = "data:image/jpeg;base64," + app.camera_service.to_base64(frame)
                    preview.update()
                    if data and (data != last_token or time.monotonic() - last_time > 3):
                        last_token, last_time = data, time.monotonic()
                        try:
                            outcome = await asyncio.to_thread(app.attendance_service.record_session_qr, data.strip())
                            status.value = outcome.get("message", "Attendance submitted.")
                            status.color = SUCCESS
                            app.notify(status.value)
                        except Exception as exc:
                            status.value = str(exc)
                            status.color = GOLD
                            app.page.update()
                    await asyncio.sleep(0.025)
            finally:
                app.student_scan_running = False
                camera.release()
                preview.src = ""
                app.page.update()
        except Exception as exc:
            app.student_scan_running = False
            status.value = str(exc)
            status.color = ERROR
            app.page.update()

    def stop(_e):
        app.student_scan_running = False
        status.value = "Stopping camera…"
        app.page.update()

    return ft.Column([
        heading("Scan Class Session QR", "This scans the teacher's active attendance session—not a personal QR pass."),
        card(ft.Column([
            ft.Row([primary_button("Start Camera", scan, icon="QR_CODE_SCANNER_ROUNDED"), subtle_button("EXIT", stop, icon="CLOSE_ROUNDED")], wrap=True),
            status,
            ft.Container(content=preview, bgcolor="#06162A", border_radius=12, padding=6, alignment=ft.Alignment.CENTER),
        ], spacing=12)),
    ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)


async def register_face_capture(app, preview: ft.Image, status: ft.Text, stop_button: ft.Button) -> None:
    try:
        if not app.face_service.is_available():
            raise BackendError("Face recognition is not installed. Install the optional face-recognition dependency and native dlib support.")
        camera = await asyncio.to_thread(app.camera_service.open)
        app.face_capture_running = True
        status.value = "Look at the camera in good lighting. Keep exactly one face in frame."
        status.color = CYAN
        app.page.update()
        import cv2
        import face_recognition
        frame_count = 0
        last_error = ""
        try:
            while app.face_capture_running:
                ok, frame = await asyncio.to_thread(camera.read)
                if not ok:
                    raise BackendError("Camera frame unavailable.")
                frame = cv2.flip(frame, 1)
                preview.src = "data:image/jpeg;base64," + app.camera_service.to_base64(frame)
                preview.update()
                frame_count += 1
                if frame_count % 5 == 0:
                    rgb = app.camera_service.to_rgb_small(frame, 0.5)
                    locations = await asyncio.to_thread(face_recognition.face_locations, rgb, model="hog")
                    if len(locations) == 1:
                        encodings = await asyncio.to_thread(face_recognition.face_encodings, rgb, locations)
                        if encodings:
                            embedding = [float(x) for x in encodings[0].tolist()]
                            await asyncio.to_thread(app.face_service.register_own_face, embedding)
                            app.audit_service.record("face_template_registered", "face_templates", app.user_id, {"algorithm": "face_recognition-128d"})
                            status.value = "Face descriptor saved. The camera frame was not uploaded."
                            status.color = SUCCESS
                            app.notify(status.value)
                            break
                    last_error = "Keep exactly one face visible, centered, and well lit."
                    status.value = last_error
                    status.color = GOLD
                await asyncio.sleep(0.025)
        finally:
            app.face_capture_running = False
            camera.release()
            preview.src = ""
            app.page.update()
    except Exception as exc:
        app.face_capture_running = False
        status.value = str(exc)
        status.color = ERROR
        app.page.update()
