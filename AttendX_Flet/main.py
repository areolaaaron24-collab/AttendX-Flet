"""AttendX Smart Attendance System — Flet entry point."""
from __future__ import annotations
import logging
import flet as ft
from attendx.ui.app_controller import AppController


def main(page: ft.Page) -> None:
    AppController(page)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
