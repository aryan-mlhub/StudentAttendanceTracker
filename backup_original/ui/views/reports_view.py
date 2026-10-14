"""
Reports View: Attendance analytics, date-range filtering, <75% defaulter warnings,
detailed student history log viewer, and CSV report export.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Any, Optional
from database import Database
from student_manager import StudentManager
from reports import ReportsManager, ATTENDANCE_DEFICIT_THRESHOLD
from ui.styles import (
    COLOR_CONTENT_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADING, FONT_BODY, FONT_SMALL
)
from ui.components import CustomTable, StatCard


class ReportsView(tk.Frame):
    """Attendance reports, analytics, and CSV exporter."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, reports_mgr: ReportsManager):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.reports_mgr = reports_mgr

        self.current_report_data: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Attendance Reports & Analytics", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(
            title_box,
            text=f"Formula: Present / (Present + Absent) × 100 | Defaulter threshold: < {ATTENDANCE_DEFICIT_THRESHOLD}%",
            font=FONT_SMALL,
            bg=COLOR_CONTENT_BG,
            fg=COLOR_TEXT_SECONDARY
        ).pack(anchor="w")

        # Top Action Button
        btn_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="📥 Export Filtered Report to CSV", style="Success.TButton", command=self._export_csv).pack(side="left")

        # Stat Summary Cards Row
        cards_box = tk.Frame(self, bg=COLOR_CONTENT_BG)
        cards_box.pack(fill="x", padx=24, pady=(0, 14))
        cards_box.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="rep_cards")

        self.card_total_students = StatCard(cards_box, title="Reported Students", value="0", icon="👥", accent_color=COLOR_PRIMARY)
        self.card_total_students.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.card_avg_pct = StatCard(cards_box, title="Average Attendance", value="0.0%", icon="📈", accent_color=COLOR_SUCCESS)
        self.card_avg_pct.grid(row=0, column=1, sticky="ew", padx=4)

        self.card_defaulters = StatCard(cards_box, title="Students < 75%", value="0", icon="⚠️", accent_color=COLOR_DANGER)
        self.card_defaulters.grid(row=0, column=2, sticky="ew", padx=4)

        self.card_total_days = StatCard(cards_box, title="Total Days Tracked", value="0", icon="📅", accent_color="#6366F1")
        self.card_total_days.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # Filter Controls Bar
        ctrl_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        ctrl_card.pack(fill="x", padx=24, pady=(0, 14))

        # Search
        tk.Label(ctrl_card, text="🔍 Search:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        self.search_entry = ttk.Entry(ctrl_card, textvariable=self.search_var, width=16, font=FONT_BODY)
        self.search_entry.pack(side="left", padx=(0, 14))

        # Class
        tk.Label(ctrl_card, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(ctrl_card, textvariable=self.class_var, state="readonly", width=10)
        self.class_combo.pack(side="left", padx=(0, 10))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        # Section
        tk.Label(ctrl_card, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(ctrl_card, textvariable=self.sec_var, state="readonly", width=7)
        self.sec_combo.pack(side="left", padx=(0, 14))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        # Date Range: Start Date & End Date
        tk.Label(ctrl_card, text="From:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.start_date_var = tk.StringVar()
        self.start_date_entry = ttk.Entry(ctrl_card, textvariable=self.start_date_var, width=11, font=FONT_BODY)
        self.start_date_entry.pack(side="left", padx=(0, 10))

        tk.Label(ctrl_card, text="To:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.end_date_var = tk.StringVar()
        self.end_date_entry = ttk.Entry(ctrl_card, textvariable=self.end_date_var, width=11, font=FONT_BODY)
        self.end_date_entry.pack(side="left", padx=(0, 14))

        # Only Defaulters Checkbox
        self.defaulters_var = tk.BooleanVar(value=False)
        self.defaulter_check = ttk.Checkbutton(ctrl_card, text="⚠️ Only < 75% Defaulters", variable=self.defaulters_var, command=self._apply_filters)
        self.defaulter_check.pack(side="left", padx=(0, 14))

        # Filter Actions
        ttk.Button(ctrl_card, text="Apply Filter", style="Primary.TButton", command=self._apply_filters).pack(side="left", padx=(0, 6))
        ttk.Button(ctrl_card, text="Reset", style="Secondary.TButton", command=self._reset_filters).pack(side="left")

        # Table
        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        columns = ["roll_no", "name", "class_name", "section", "total_days", "present_days", "absent_days", "leave_days", "percentage", "status"]
        headings = ["Roll Number", "Student Name", "Class", "Section", "Days Recorded", "Present", "Absent", "Leave", "Attendance %", "Status"]
        widths = [120, 210, 110, 80, 110, 80, 80, 80, 120, 140]
        aligns = ["w", "w", "w", "c", "c", "c", "c", "c", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)

        # Double-click to view student's individual attendance history
        self.table.tree.bind("<Double-1>", lambda e: self._view_student_history())

    def _on_class_change(self):
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._apply_filters()

    def _reset_filters(self):
        self.search_var.set("")
        self.class_var.set("All")
        self.sec_var.set("All")
        self.start_date_var.set("")
        self.end_date_var.set("")
        self.defaulters_var.set(False)
        self.refresh()

    def _apply_filters(self):
        query = self.search_var.get().strip()
        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()
        s_date = self.start_date_var.get().strip() or None
        e_date = self.end_date_var.get().strip() or None
        only_def = self.defaulters_var.get()

        self.current_report_data = self.reports_mgr.get_attendance_report(
            class_filter=c_filter,
            section_filter=s_filter,
            start_date=s_date,
            end_date=e_date,
            search_query=query,
            only_defaulters=only_def
        )

        self._render_table()

    def _render_table(self):
        self.table.clear()
        total_students = len(self.current_report_data)
        pct_sum = 0.0
        students_with_history = 0
        defaulter_count = 0
        max_days = 0

        for r in self.current_report_data:
            if r["has_history"]:
                pct_sum += r["percentage"]
                students_with_history += 1
            if r["is_low"]:
                defaulter_count += 1
            if r["total_days"] > max_days:
                max_days = r["total_days"]

            tag = "defaulter" if r["is_low"] else ("even" if not r["has_history"] else "status_valid")

            self.table.insert_row(
                (
                    r["roll_no"],
                    r["name"],
                    r["class_name"] or "—",
                    r["section"] or "—",
                    r["total_days"],
                    r["present_days"],
                    r["absent_days"],
                    r["leave_days"],
                    f"{r['percentage']}%",
                    "⚠️ DEFICIT (<75%)" if r["is_low"] else ("Satisfactory" if r["has_history"] else "No Records")
                ),
                tags=(tag,)
            )

        # Update stat cards
        avg_pct = round(pct_sum / students_with_history, 1) if students_with_history > 0 else 0.0
        self.card_total_students.update_value(str(total_students), f"{students_with_history} with attendance history")
        self.card_avg_pct.update_value(f"{avg_pct}%", "Average of active students")
        self.card_defaulters.update_value(str(defaulter_count), "Attendance below 75%")
        self.card_total_days.update_value(str(max_days), "Max days marked in filter")

    def _view_student_history(self):
        """Open detailed date-by-date attendance log for the selected student."""
        sel = self.table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Please select a student to view their history log.", parent=self)
            return

        idx = self.table.tree.index(sel[0])
        if idx >= len(self.current_report_data):
            return

        student = self.current_report_data[idx]
        history = self.reports_mgr.get_student_history(student["student_id"])

        # History modal
        top = tk.Toplevel(self)
        top.title(f"Attendance Log — {student['name']} ({student['roll_no']})")
        top.geometry("540x450")
        top.configure(bg=COLOR_CONTENT_BG)

        f = tk.Frame(top, bg=COLOR_CARD_BG, padx=20, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text=f"{student['name']} ({student['roll_no']})", font=FONT_TITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(f, text=f"Class: {student['class_name']} {student['section']} | Overall Attendance: {student['percentage']}%", font=FONT_BODY, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w", pady=(0, 12))

        hist_table = CustomTable(f, columns=["date", "day", "status"], headings=["Date", "Day of Week", "Attendance Status"], col_widths=[120, 140, 140], col_aligns=["c", "w", "c"])
        hist_table.pack(fill="both", expand=True, pady=(0, 10))

        for h in history:
            tag = "status_valid" if h["status"] == "Present" else ("status_danger" if h["status"] == "Absent" else "status_warning")
            hist_table.insert_row((h["attendance_date"], h.get("day_name", ""), h["status"]), tags=(tag,))

        ttk.Button(f, text="Close", style="Secondary.TButton", command=top.destroy).pack(side="right")

    def _export_csv(self):
        """Export current filtered report to CSV."""
        if not self.current_report_data:
            messagebox.showwarning("No Data", "There is no report data to export.", parent=self)
            return

        dest = filedialog.asksaveasfilename(
            title="Export Attendance Report to CSV",
            defaultextension=".csv",
            initialfile="attendance_report.csv",
            filetypes=[("CSV Files", "*.csv")]
        )
        if not dest:
            return

        try:
            self.reports_mgr.export_report_to_csv(dest, self.current_report_data)
            messagebox.showinfo("Export Successful", f"Report successfully exported to:\n{dest}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export CSV: {str(e)}", parent=self)

    def refresh(self):
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        self._apply_filters()
