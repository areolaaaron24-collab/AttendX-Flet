from __future__ import annotations
import flet as ft
from attendx.ui.components import card, icon_data, primary_button, pill
from attendx.ui.theme import BLUE, CYAN, GOLD, MUTED, NAVY, NAVY_2, SURFACE, WHITE


def build_portal_page(app) -> ft.Control:
    settings = app.settings
    configured = settings.is_configured
    status_text = "Supabase keys configured · server connection is verified after sign-in" if configured else "Setup required · add your Supabase project keys to .env"
    status_color = CYAN if configured else GOLD

    def portal_card(role: str, title: str, description: str, icon: str, accent: str) -> ft.Control:
        def choose(_e):
            app.show_auth(role, "login")
        return card(ft.Column([
            ft.Container(ft.Icon(icon_data(icon), size=36, color=accent), bgcolor=NAVY_2, padding=17, border_radius=16),
            ft.Text(title, size=21, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text(description, size=13, color=MUTED, text_align=ft.TextAlign.CENTER),
            primary_button(f"Continue to {role.title()} Portal", choose, icon="ARROW_FORWARD_ROUNDED"),
            ft.Text("Create an account or sign in", size=11, color=MUTED),
        ], spacing=13, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=25, expand=True)

    return ft.Container(
        expand=True,
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                   colors=[NAVY, NAVY_2, "#0A3355"]),
        content=ft.Column([
            ft.Row([
                ft.Image(src="csu_logo.png", width=68, height=68, fit=ft.BoxFit.CONTAIN),
                ft.Column([
                    ft.Text("CAGAYAN STATE UNIVERSITY", size=13, weight=ft.FontWeight.BOLD, color=GOLD),
                    ft.Text("ATTENDX", size=34, weight=ft.FontWeight.BOLD, color=WHITE),
                    ft.Text("SMART ATTENDANCE SYSTEM", size=12, color=CYAN, weight=ft.FontWeight.BOLD),
                ], spacing=1),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=16),
            ft.Container(height=1, bgcolor="#3F6283", width=240),
            ft.Text("Select Your Portal", size=27, weight=ft.FontWeight.BOLD, color=WHITE),
            ft.Text("Choose the workspace that matches your school account.", size=14, color=MUTED, text_align=ft.TextAlign.CENTER),
            ft.Container(
                content=ft.ResponsiveRow([
                    ft.Container(content=portal_card("teacher", "Teacher Portal", "Manage subjects, schedules, student attendance, and reports.", "SCHOOL_ROUNDED", GOLD), col={"xs": 12, "sm": 6}),
                    ft.Container(content=portal_card("student", "Student Portal", "View your classes, attendance history, schedules, and QR pass.", "PERSON_ROUNDED", CYAN), col={"xs": 12, "sm": 6}),
                ], spacing=18, run_spacing=18),
                width=760,
            ),
            ft.Row([pill(status_text, status_color)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("CSU-inspired identity · Dark navy · Blue & cyan · Gold accent", size=11, color=MUTED, text_align=ft.TextAlign.CENTER),
        ], spacing=16, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           alignment=ft.MainAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding(left=18, top=24, right=18, bottom=24),
    )
