from __future__ import annotations
import flet as ft
from attendx.ui.components import card, field, dropdown, heading, primary_button
from attendx.ui.theme import CYAN, ERROR, GOLD, MUTED, SUCCESS, WHITE


def build_profile_page(app) -> ft.Control:
    profile = app.profile or {}
    first = field("First Name", value=profile.get("first_name", ""))
    last = field("Last Name", value=profile.get("last_name", ""))
    middle = field("Middle Name (optional)", value=profile.get("middle_name", ""))
    suffix = field("Suffix / Extension (optional)", value=profile.get("suffix", ""))
    sex = dropdown("Sex", ["Male", "Female"], value=profile.get("sex", "Male"))
    status = ft.Text("Changes save to your authenticated Supabase profile.", size=12, color=MUTED)
    controls: list[ft.Control] = [
        heading("My Profile", "Edit supported personal details. Account ID, role, and password are not editable here."),
        card(ft.Column([
            ft.Row([first, last], wrap=True, spacing=12),
            ft.Row([middle, suffix], wrap=True, spacing=12),
            sex,
        ], spacing=12)),
    ]
    if app.role == "STUDENT":
        course = field("Course / Program", value=profile.get("course", ""))
        year = dropdown("Year", ["1", "2", "3", "4", "5", "6"], value=str(profile.get("year_level", "")))
        section = field("Section", value=profile.get("section", ""))
        controls.append(card(ft.Column([ft.Text("Student Information", size=16, color=CYAN, weight=ft.FontWeight.BOLD),
                                        course, ft.Row([year, section], wrap=True, spacing=12)], spacing=12)))
    else:
        department = field("Department", value=profile.get("department") or "")
        office = field("Office", value=profile.get("office") or "")
        controls.append(card(ft.Column([ft.Text("Teacher Information", size=16, color=CYAN, weight=ft.FontWeight.BOLD),
                                        department, office], spacing=12)))
    controls.append(card(ft.Column([
        ft.Text("Account Security", size=16, weight=ft.FontWeight.BOLD, color=WHITE),
        ft.Text(f"Account ID: {profile.get('account_id', '')}", size=13, color=MUTED),
        ft.Text(f"Role: {app.role.title()}", size=13, color=MUTED),
        ft.Text(f"Recovery Email: {profile.get('recovery_email') or 'Not configured — password recovery may require school support'}", size=12, color=GOLD if not profile.get("recovery_email") else MUTED),
        ft.Text("To change your password, use Forgot Password from the portal sign-in screen. A recovery email is recommended.", size=11, color=MUTED),
    ], spacing=8)))

    def save(_e):
        try:
            changes = {
                "first_name": first.value, "last_name": last.value,
                "middle_name": middle.value, "suffix": suffix.value, "sex": sex.value,
            }
            if app.role == "STUDENT":
                changes.update({"course": course.value, "year_level": year.value, "section": section.value})
            else:
                changes.update({"department": department.value, "office": office.value})
            updated = app.profile_service.update_own(app.user_id, app.role, changes)
            app.profile = {**app.profile, **updated}
            app.audit_service.record("profile_updated", "profiles", app.user_id, {"fields": sorted(changes.keys())})
            status.value = "Profile updated successfully."
            status.color = SUCCESS
            app.page.update()
        except Exception as exc:
            status.value = str(exc)
            status.color = ERROR
            app.page.update()

    controls.append(card(ft.Column([primary_button("Save Profile", save, icon="SAVE_ROUNDED"), status], spacing=10)))
    return ft.Column(controls, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
