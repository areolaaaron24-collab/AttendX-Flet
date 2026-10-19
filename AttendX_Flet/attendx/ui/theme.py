from __future__ import annotations

import flet as ft

NAVY = "#081B34"
NAVY_2 = "#0E2B50"
BLUE = "#176AA6"
CYAN = "#39B9D7"
GOLD = "#F4C84A"
WHITE = "#F7FAFF"
MUTED = "#AAB9CC"
SURFACE = "#102742"
SURFACE_2 = "#153250"
BORDER = "#294867"
SUCCESS = "#32B58B"
WARNING = "#E8A33A"
ERROR = "#E66D70"


def configure_page(page: ft.Page) -> None:
    page.title = "AttendX | Smart Attendance System"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = NAVY
    page.padding = 0
    page.spacing = 0
    page.theme = ft.Theme(color_scheme_seed=BLUE, use_material3=True)
    page.window.min_width = 360
    page.window.min_height = 600
