from __future__ import annotations

from typing import Any, Iterable
import flet as ft

from attendx.ui.theme import BORDER, BLUE, CYAN, MUTED, NAVY, NAVY_2, SURFACE, SURFACE_2, WHITE


def heading(title: str, subtitle: str = "") -> ft.Column:
    controls: list[ft.Control] = [ft.Text(title, size=26, weight=ft.FontWeight.BOLD, color=WHITE)]
    if subtitle:
        controls.append(ft.Text(subtitle, size=13, color=MUTED))
    return ft.Column(controls, spacing=4)


def card(content: ft.Control, *, padding: int = 18, expand: bool = False, width: int | None = None) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        width=width,
        expand=expand,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=16,
    )


def field(label: str, *, password: bool = False, value: str = "", hint: str | None = None,
          multiline: bool = False, width: int | None = None, read_only: bool = False) -> ft.TextField:
    return ft.TextField(
        label=label, value=value, password=password, can_reveal_password=password,
        hint_text=hint, multiline=multiline, min_lines=1, max_lines=4 if multiline else 1,
        width=width, read_only=read_only, border_radius=10,
        border_color=BORDER, focused_border_color=CYAN,
        text_size=14, label_style=ft.TextStyle(color=MUTED),
        content_padding=ft.Padding(left=12, top=12, right=12, bottom=12),
    )


def dropdown(label: str, options: Iterable[str], *, value: str | None = None, width: int | None = None) -> ft.Dropdown:
    return ft.Dropdown(
        label=label, value=value, width=width,
        options=[ft.DropdownOption(key=item, text=item) for item in options],
        border_radius=10, border_color=BORDER, focused_border_color=CYAN,
        text_size=14, label_style=ft.TextStyle(color=MUTED),
    )


def icon_data(icon: str | Any | None):
    if not isinstance(icon, str):
        return icon
    return getattr(ft.Icons, icon, ft.Icons.CIRCLE_OUTLINED)


def primary_button(text: str, on_click, *, icon: str | None = None, disabled: bool = False) -> ft.Button:
    return ft.Button(
        content=ft.Text(text, weight=ft.FontWeight.BOLD),
        on_click=on_click, disabled=disabled,
        icon=icon_data(icon),
        style=ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: BLUE, ft.ControlState.HOVERED: CYAN},
            color={ft.ControlState.DEFAULT: WHITE, ft.ControlState.HOVERED: NAVY},
            padding=ft.Padding(left=18, top=12, right=18, bottom=12),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )


def subtle_button(text: str, on_click, *, icon: str | None = None) -> ft.Button:
    return ft.Button(
        content=ft.Text(text), icon=icon_data(icon), on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: SURFACE_2, ft.ControlState.HOVERED: NAVY_2},
            color=WHITE, padding=ft.Padding(left=14, top=10, right=14, bottom=10),
            shape=ft.RoundedRectangleBorder(radius=10),
            side=ft.BorderSide(1, BORDER),
        ),
    )


def stat_card(label: str, value: str | int, icon: str, accent: str = CYAN) -> ft.Container:
    return card(
        ft.Row([
            ft.Container(ft.Icon(icon_data(icon), color=accent, size=24), bgcolor=NAVY_2, padding=12, border_radius=12),
            ft.Column([
                ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=WHITE),
                ft.Text(label, size=12, color=MUTED),
            ], spacing=2, expand=True),
        ], spacing=12), padding=16, expand=True,
    )


def pill(text: str, color: str = CYAN) -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=f"{color}18", border=ft.Border.all(1, f"{color}65"),
        border_radius=20, padding=ft.Padding(left=10, top=5, right=10, bottom=5),
    )


def empty_state(title: str, message: str, icon: str = "INFO_OUTLINE") -> ft.Container:
    return card(ft.Column([
        ft.Icon(icon_data(icon), size=38, color=CYAN),
        ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=WHITE, text_align=ft.TextAlign.CENTER),
        ft.Text(message, size=13, color=MUTED, text_align=ft.TextAlign.CENTER),
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=26)


def simple_table(headers: list[str], rows: list[list[Any]], *, empty_message: str = "No records to display.") -> ft.Control:
    if not rows:
        return ft.Container(ft.Text(empty_message, color=MUTED, size=13), padding=14)
    columns = [ft.DataColumn(ft.Text(header, weight=ft.FontWeight.BOLD, color=CYAN, size=12)) for header in headers]
    data_rows = []
    for row in rows:
        cells = []
        for value in row:
            if isinstance(value, ft.Control):
                control = value
            else:
                control = ft.Text(str(value if value is not None else ""), size=12, color=WHITE, selectable=True)
            cells.append(ft.DataCell(control))
        data_rows.append(ft.DataRow(cells=cells))
    return ft.Row([
        ft.DataTable(columns=columns, rows=data_rows, heading_row_height=42, data_row_min_height=42,
                     column_spacing=22, horizontal_margin=12, border=ft.Border.all(1, BORDER),
                     border_radius=10, heading_row_color=NAVY_2, data_row_color={ft.ControlState.DEFAULT: SURFACE}),
    ], scroll=ft.ScrollMode.AUTO)


def divider() -> ft.Divider:
    return ft.Divider(color=BORDER, height=1, thickness=1)


def schedule_label(schedule: dict[str, Any]) -> str:
    subject = (schedule.get("subject") or {}).get("subject_name", "Subject")
    cls = schedule.get("class") or {}
    return f"{subject} · {cls.get('course', '')} {cls.get('year_level', '')}-{cls.get('section', '')} · {schedule.get('day', '')} {str(schedule.get('start_time', ''))[:5]}–{str(schedule.get('end_time', ''))[:5]}"
