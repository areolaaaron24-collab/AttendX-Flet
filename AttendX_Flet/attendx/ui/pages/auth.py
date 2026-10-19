from __future__ import annotations
import asyncio
import flet as ft
from attendx.core.validators import RegistrationData, normalize_account_id, validate_password, ValidationError
from attendx.ui.components import card, field, dropdown, heading, primary_button, subtle_button
from attendx.ui.theme import CYAN, GOLD, MUTED, NAVY_2, WHITE


def build_auth_page(app, role: str, mode: str = "login") -> ft.Control:
    role = role.upper()
    mode = mode.lower()
    role_label = role.title()
    account_id = field("Account ID", hint="Enter your school account ID")
    password = field("Password", password=True)
    confirm = field("Confirm Password", password=True)
    first = field("First Name")
    last = field("Last Name")
    middle = field("Middle Name (optional)")
    suffix = field("Suffix / Extension (optional)")
    sex = dropdown("Sex", ["Male", "Female"])
    recovery_email = field("Recovery Email (optional but recommended)", hint="name@example.com")
    teacher_invite_code = field("Teacher Invitation Code", hint="Code from the AttendX administrator")
    course = field("Course / Program")
    year_level = dropdown("Year", ["1ST", "2ND", "3RD", "4TH"])
    section = field("Section")
    department = field("Department (optional)")
    office = field("Office (optional)")
    reset_id = field("Account ID")
    message = ft.Text("", color=GOLD, size=12)

    def go_back(_e=None):
        app.show_portal()

    def go_login(_e=None):
        app.show_auth(role.lower(), "login")

    def go_register(_e=None):
        app.show_auth(role.lower(), "register")

    def go_reset(_e=None):
        app.show_auth(role.lower(), "reset")

    async def login_action(_e):
        try:
            aid = normalize_account_id(account_id.value)
            if not (password.value or ""):
                raise ValidationError("Password is required.")
            app._ensure_client()
            profile = await asyncio.to_thread(app.auth_service.login, aid, password.value, role)
            app._enter_workspace(profile)
        except Exception as exc:
            message.value = str(exc)
            message.color = GOLD
            app.page.update()

    async def register_action(_e):
        try:
            data = RegistrationData.build(
                account_id=account_id.value,
                role=role,
                password=password.value or "",
                confirm_password=confirm.value or "",
                first_name=first.value,
                last_name=last.value,
                middle_name=middle.value,
                suffix=suffix.value,
                sex=sex.value,
                recovery_email=recovery_email.value,
                course=course.value,
                year_level=year_level.value,
                section=section.value,
                department=department.value,
                office=office.value,
            )
            invite_code = (teacher_invite_code.value or "").strip()
            if role == "TEACHER" and not invite_code:
                raise ValidationError("Enter the invitation code provided by the AttendX administrator.")
            app._ensure_client()
            profile = await asyncio.to_thread(app.auth_service.register, data, invite_code)
            app._enter_workspace(profile)
        except Exception as exc:
            message.value = str(exc)
            message.color = GOLD
            app.page.update()

    async def reset_action(_e):
        try:
            aid = normalize_account_id(reset_id.value)
            app._ensure_client()
            await asyncio.to_thread(app.auth_service.request_password_reset, aid, role)
            message.value = "If this account has a recovery email, reset instructions will be sent. Accounts without a recovery email require school support."
            message.color = CYAN
            app.page.update()
        except Exception as exc:
            message.value = str(exc)
            message.color = GOLD
            app.page.update()

    if mode == "register":
        controls: list[ft.Control] = [
            heading(f"Create {role_label} Account", "Account IDs are globally unique across Teacher and Student portals."),
            account_id,
            ft.Row([first, last], spacing=12, wrap=True),
            ft.Row([middle, suffix], spacing=12, wrap=True),
            sex,
            recovery_email,
        ]
        if role == "TEACHER":
            controls.insert(2, teacher_invite_code)
        if role == "STUDENT":
            controls.append(ft.Row([course, year_level, section], spacing=12, wrap=True))
        else:
            controls.append(ft.Row([department, office], spacing=12, wrap=True))
        controls += [password, confirm, message,
                     primary_button("Create Account", register_action, icon="PERSON_ADD_ROUNDED"),
                     ft.Row([ft.Text("Already registered?", color=MUTED), subtle_button("Sign In", go_login)], wrap=True),
                     subtle_button("Back to Portal Selection", go_back)]
    elif mode == "reset":
        controls = [
            heading("Password Recovery", "Instructions can only be sent when a real recovery email was provided at registration."),
            reset_id,
            message,
            primary_button("Request Reset Instructions", reset_action, icon="MARK_EMAIL_READ_ROUNDED"),
            subtle_button("Back to Sign In", go_login),
        ]
    else:
        controls = [
            heading(f"{role_label} Sign In", "Sign in with your school Account ID and password."),
            account_id, password, message,
            primary_button("Sign In", login_action, icon="LOGIN_ROUNDED"),
            ft.Row([ft.Text("Need an account?", color=MUTED), subtle_button("Register", go_register)], wrap=True),
            subtle_button("Forgot Password?", go_reset, icon="LOCK_RESET_ROUNDED"),
            subtle_button("Back to Portal Selection", go_back),
        ]

    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                   colors=["#07172E", "#0C3153"]),
        content=ft.Column([
            ft.Row([ft.Image(src="csu_logo.png", width=58, height=58),
                    ft.Column([ft.Text("ATTENDX", size=26, weight=ft.FontWeight.BOLD, color=WHITE),
                               ft.Text(f"{role_label.upper()} PORTAL", size=11, color=GOLD, weight=ft.FontWeight.BOLD)], spacing=0)],
                   alignment=ft.MainAxisAlignment.CENTER, spacing=12),
            ft.Container(
                width=570,
                content=card(ft.Column(controls, spacing=14, scroll=ft.ScrollMode.AUTO), padding=26),
            ),
            ft.Text("Protect your password. Use only your own school account.", size=11, color=MUTED),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER,
           spacing=18, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding(left=16, top=18, right=16, bottom=18),
    )
