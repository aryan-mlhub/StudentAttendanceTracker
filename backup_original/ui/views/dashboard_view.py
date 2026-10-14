"""
Dashboard View: Executive summary with modern stat cards, date selector,
recent attendance activity table, quick actions, and low attendance alert banner.
"""

import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta
from typing import Callable, Optional
from database import Database
from student_manager import StudentManager
from attendance_manager import AttendanceManager
from reports import ReportsManager
from ui.styles import (
    COLOR_CONTENT_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADING, FONT_BODY, FONT_SMALL
)
from ui.components import StatCard, CustomTable, StudentDialog


class DashboardView(tk.Frame):
    """Modern dashboard view containing summary metrics and recent activity."""

    def __init__(
        self,
        parent,
        db: Database,
        student_mgr: StudentManager,
        att_mgr: AttendanceManager,
        reports_mgr: ReportsManager,
        navigate_to: Callable[[str], None]
    ):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.att_mgr = att_mgr
        self.reports_mgr = reports_mgr
        self.navigate_to = navigate_to

        self.selected_date = date.today().strftime("%Y-%m-%d")

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Top Header Bar
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 16))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Attendance Dashboard", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(title_box, text="Overview of class attendance, student metrics, and daily trends", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w")

        # Date Switcher on Right
        date_box = tk.Frame(header, bg=COLOR_CARD_BG, padx=10, pady=6, highlightbackground="#E2E8F0", highlightthickness=1)
        date_box.pack(side="right")

        tk.Label(date_box, text="Selected Date:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self.date_var = tk.StringVar(value=self.selected_date)
        self.date_entry = ttk.Entry(date_box, textvariable=self.date_var, width=12, font=FONT_BODY)
        self.date_entry.pack(side="left", padx=(0, 6))

        ttk.Button(date_box, text="Today", style="Secondary.TButton", command=self._set_today).pack(side="left", padx=(0, 4))
        ttk.Button(date_box, text="Yesterday", style="Secondary.TButton", command=self._set_yesterday).pack(side="left", padx=(0, 4))
        ttk.Button(date_box, text="Apply", style="Primary.TButton", command=self._apply_date).pack(side="left")

        # Low attendance banner container
        self.banner_frame = tk.Frame(self, bg=COLOR_CONTENT_BG)
        self.banner_frame.pack(fill="x", padx=24, pady=(0, 14))

        # Metrics Cards Row
        cards_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        cards_container.pack(fill="x", padx=24, pady=(0, 16))
        cards_container.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="stat_cards")

        self.card_total = StatCard(cards_container, title="Total Students", value="0", icon="👥", accent_color=COLOR_PRIMARY)
        self.card_total.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.card_present = StatCard(cards_container, title="Present Today", value="0", icon="✅", accent_color=COLOR_SUCCESS)
        self.card_present.grid(row=0, column=1, sticky="ew", padx=4)

        self.card_absent = StatCard(cards_container, title="Absent Today", value="0", icon="❌", accent_color=COLOR_DANGER)
        self.card_absent.grid(row=0, column=2, sticky="ew", padx=4)

        self.card_leave = StatCard(cards_container, title="On Leave Today", value="0", icon="🌴", accent_color=COLOR_WARNING)
        self.card_leave.grid(row=0, column=3, sticky="ew", padx=4)

        self.card_pct = StatCard(cards_container, title="Attendance Rate", value="0.0%", icon="📈", accent_color=COLOR_PRIMARY)
        self.card_pct.grid(row=0, column=4, sticky="ew", padx=(8, 0))

        # Middle Row: Quick Actions Bar
        actions_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        actions_bar.pack(fill="x", padx=24, pady=(0, 18))

        tk.Label(actions_bar, text="⚡ Quick Actions:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 16))

        ttk.Button(actions_bar, text="📅 Mark Attendance", style="Primary.TButton", command=lambda: self.navigate_to("attendance")).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="📥 Bulk Import Students", style="Success.TButton", command=lambda: self.navigate_to("import")).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="➕ Add Single Student", style="Secondary.TButton", command=self._open_add_student).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="📊 View Detailed Reports", style="Secondary.TButton", command=lambda: self.navigate_to("reports")).pack(side="left")

        # Bottom Section: Recent Activity Table
        bottom_frame = tk.Frame(self, bg=COLOR_CONTENT_BG)
        bottom_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        recent_label_frame = tk.Frame(bottom_frame, bg=COLOR_CONTENT_BG)
        recent_label_frame.pack(fill="x", pady=(0, 8))
        tk.Label(recent_label_frame, text="Recent Attendance Activity", font=FONT_SUBTITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left")

        columns = ["date", "class_name", "marked", "present", "absent", "leave", "percentage"]
        headings = ["Date", "Class", "Total Marked", "Present", "Absent", "Leave", "Attendance %"]
        widths = [120, 140, 110, 100, 100, 100, 130]
        aligns = ["c", "w", "c", "c", "c", "c", "c"]

        self.recent_table = CustomTable(bottom_frame, columns, headings, widths, aligns)
        self.recent_table.pack(fill="both", expand=True)

    def _set_today(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self._apply_date()

    def _set_yesterday(self):
        yest = date.today() - timedelta(days=1)
        self.date_var.set(yest.strftime("%Y-%m-%d"))
        self._apply_date()

    def _apply_date(self):
        val = self.date_var.get().strip()
        try:
            self.selected_date = self.att_mgr.validate_date(val)
            self.date_var.set(self.selected_date)
            self.refresh()
        except ValueError:
            self.date_var.set(self.selected_date)

    def _open_add_student(self):
        def save_callback(roll, name, c_name, sec):
            self.student_mgr.add_student(roll, name, c_name, sec)
            self.refresh()
        StudentDialog(self, title="Add New Student", on_save=save_callback)

    def refresh(self):
        """Fetch latest database counts and reload UI."""
        # 1. Update stats for selected date
        stats = self.att_mgr.get_date_stats(self.selected_date)
        total_st = stats["total_students"]

        self.card_total.update_value(str(total_st), "Total registered in system")
        self.card_present.update_value(str(stats["present_count"]), f"{stats['unmarked_count']} unmarked today")
        self.card_absent.update_value(str(stats["absent_count"]), f"For {self.selected_date}")
        self.card_leave.update_value(str(stats["leave_count"]), "Approved absence leaves")
        self.card_pct.update_value(f"{stats['percentage']}%", "Present / (Present + Absent)")

        # 2. Check for defaulters (<75%) and render alert banner if any
        for widget in self.banner_frame.winfo_children():
            widget.destroy()

        defaulters = self.reports_mgr.get_attendance_report(only_defaulters=True)
        if defaulters:
            b_box = tk.Frame(self.banner_frame, bg="#FEF2F2", highlightbackground="#F87171", highlightthickness=1, padx=14, pady=8)
            b_box.pack(fill="x")

            tk.Label(
                b_box,
                text=f"⚠️ ATTENDANCE WARNING: {len(defaulters)} student(s) currently fall below the required 75% attendance threshold.",
                font=FONT_HEADING,
                bg="#FEF2F2",
                fg="#991B1B"
            ).pack(side="left")

            ttk.Button(
                b_box,
                text="View Defaulters List",
                style="Danger.TButton",
                command=lambda: self.navigate_to("reports")
            ).pack(side="right")

        # 3. Populate Recent Activity
        self.recent_table.clear()
        recent = self.att_mgr.get_recent_activity(limit=10)
        for r in recent:
            c_name = r["class_name"] or "General / All"
            self.recent_table.insert_row((
                r["attendance_date"],
                c_name,
                r["total_marked"],
                r["present_count"],
                r["absent_count"],
                r["leave_count"],
                f"{r['percentage']}%"
            ))
