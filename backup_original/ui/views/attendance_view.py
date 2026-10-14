"""
Attendance View: Class-wise attendance marking, bulk status actions,
interactive status toggling, historical loading, overwrite warnings, and transactional saving.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from database import Database
from student_manager import StudentManager
from attendance_manager import AttendanceManager
from ui.styles import (
    COLOR_CONTENT_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADING, FONT_BODY, FONT_SMALL
)
from ui.components import CustomTable


class AttendanceView(tk.Frame):
    """Attendance marking and modification screen."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, att_mgr: AttendanceManager):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.att_mgr = att_mgr

        self.selected_date = date.today().strftime("%Y-%m-%d")
        # In-memory working copy of attendance statuses: {student_id: "Present" | "Absent" | "Leave"}
        self.current_statuses: Dict[int, str] = {}
        self.students_list: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Mark & Manage Attendance", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(title_box, text="Select date and class, toggle student statuses, and save class attendance records.", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w")

        # Top Control Bar (Date selection, Class/Section filter, Load)
        ctrl_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        ctrl_card.pack(fill="x", padx=24, pady=(0, 14))

        # Date Picker
        tk.Label(ctrl_card, text="📅 Date:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 6))
        self.date_var = tk.StringVar(value=self.selected_date)
        self.date_entry = ttk.Entry(ctrl_card, textvariable=self.date_var, width=12, font=FONT_BODY)
        self.date_entry.pack(side="left", padx=(0, 4))

        ttk.Button(ctrl_card, text="Today", style="Secondary.TButton", command=self._set_today).pack(side="left", padx=(0, 4))
        ttk.Button(ctrl_card, text="Yesterday", style="Secondary.TButton", command=self._set_yesterday).pack(side="left", padx=(0, 16))

        # Class Filter
        tk.Label(ctrl_card, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(ctrl_card, textvariable=self.class_var, state="readonly", width=12)
        self.class_combo.pack(side="left", padx=(0, 12))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        # Section Filter
        tk.Label(ctrl_card, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(ctrl_card, textvariable=self.sec_var, state="readonly", width=8)
        self.sec_combo.pack(side="left", padx=(0, 16))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._load_sheet())

        ttk.Button(ctrl_card, text="🔄 Load / Refresh Sheet", style="Primary.TButton", command=self._load_sheet).pack(side="left")

        # Action & Summary Sub-bar
        sub_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=10, highlightbackground="#E2E8F0", highlightthickness=1)
        sub_bar.pack(fill="x", padx=24, pady=(0, 12))

        # Quick Mass-Status Actions
        tk.Label(sub_bar, text="Quick Actions:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        ttk.Button(sub_bar, text="✔ Mark All Present", style="Success.TButton", command=self._mark_all_present).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="✖ Mark All Absent", style="Danger.TButton", command=self._mark_all_absent).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="Clear All", style="Secondary.TButton", command=self._clear_all).pack(side="left", padx=(0, 16))

        # Selected Row Status Buttons
        tk.Label(sub_bar, text="Selected Student:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="Present (P)", style="Success.TButton", command=lambda: self._set_selected_status("Present")).pack(side="left", padx=(0, 4))
        ttk.Button(sub_bar, text="Absent (A)", style="Danger.TButton", command=lambda: self._set_selected_status("Absent")).pack(side="left", padx=(0, 4))
        ttk.Button(sub_bar, text="Leave (L)", style="Secondary.TButton", command=lambda: self._set_selected_status("Leave")).pack(side="left", padx=(0, 16))

        # Live Counts
        self.stats_pill = tk.Label(sub_bar, text="Present: 0 | Absent: 0 | Leave: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.stats_pill.pack(side="right")

        # Table
        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 14))

        columns = ["roll_no", "name", "class_name", "section", "status", "action_hint"]
        headings = ["Roll Number", "Student Name", "Class", "Section", "Attendance Status", "Quick Toggle"]
        widths = [140, 240, 140, 90, 160, 200]
        aligns = ["w", "w", "w", "c", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)

        # Space or double-click cycles status: Present -> Absent -> Leave -> Present
        self.table.tree.bind("<Double-1>", self._cycle_status_event)
        self.table.tree.bind("<space>", self._cycle_status_event)

        # Bottom Save Bar
        bottom_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=14, highlightbackground="#CBD5E1", highlightthickness=1)
        bottom_bar.pack(fill="x", padx=24, pady=(0, 18))

        self.save_status_lbl = tk.Label(bottom_bar, text="Changes not saved yet", font=FONT_BODY, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.save_status_lbl.pack(side="left")

        self.save_btn = ttk.Button(bottom_bar, text="💾 Save Attendance for Class", style="Primary.TButton", command=self._save_attendance)
        self.save_btn.pack(side="right")

    def _set_today(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self._load_sheet()

    def _set_yesterday(self):
        yest = date.today() - timedelta(days=1)
        self.date_var.set(yest.strftime("%Y-%m-%d"))
        self._load_sheet()

    def _on_class_change(self):
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._load_sheet()

    def _load_sheet(self):
        """Fetch students and their attendance status for the selected date."""
        try:
            self.selected_date = self.att_mgr.validate_date(self.date_var.get().strip())
            self.date_var.set(self.selected_date)
        except ValueError as e:
            messagebox.showerror("Invalid Date", str(e), parent=self)
            return

        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()

        self.students_list = self.att_mgr.get_attendance_sheet(
            attendance_date=self.selected_date,
            class_name=c_filter,
            section=s_filter
        )

        # Sync in-memory working copy
        self.current_statuses = {}
        for s in self.students_list:
            # If status exists in DB for this date, use it; otherwise default to None (unmarked)
            self.current_statuses[s["student_id"]] = s.get("status")

        has_existing, count = self.att_mgr.has_attendance_for_date(self.selected_date, c_filter, s_filter)
        if has_existing:
            self.save_status_lbl.config(text=f"Loaded existing attendance records ({count} marked for {self.selected_date})", fg=COLOR_PRIMARY)
        else:
            self.save_status_lbl.config(text=f"No saved attendance records yet for {self.selected_date}. Mark and save below.", fg=COLOR_TEXT_SECONDARY)

        self._render_table()

    def _render_table(self):
        self.table.clear()
        p_count = 0
        a_count = 0
        l_count = 0

        for s in self.students_list:
            sid = s["student_id"]
            st = self.current_statuses.get(sid)

            if st == "Present":
                tag = "status_valid"
                display_st = "✅ Present"
                p_count += 1
            elif st == "Absent":
                tag = "status_danger"
                display_st = "❌ Absent"
                a_count += 1
            elif st == "Leave":
                tag = "status_warning"
                display_st = "🌴 Leave"
                l_count += 1
            else:
                tag = "even"
                display_st = "⚪ Unmarked"

            self.table.insert_row(
                (
                    s["roll_no"],
                    s["name"],
                    s["class_name"] or "—",
                    s["section"] or "—",
                    display_st,
                    "Double-click to toggle"
                ),
                tags=(tag,)
            )

        total_marked = p_count + a_count + l_count
        rate = round((p_count / (p_count + a_count) * 100.0), 1) if (p_count + a_count) > 0 else 0.0
        self.stats_pill.config(
            text=f"Present: {p_count}  |  Absent: {a_count}  |  Leave: {l_count}  |  Total: {len(self.students_list)}  (Rate: {rate}%)"
        )

    def _cycle_status_event(self, event=None):
        """Cycle status of selected row: Unmarked/Present -> Absent -> Leave -> Present."""
        sel = self.table.tree.selection()
        if not sel:
            return

        idx = self.table.tree.index(sel[0])
        if idx >= len(self.students_list):
            return

        sid = self.students_list[idx]["student_id"]
        current = self.current_statuses.get(sid)

        cycle_map = {
            None: "Present",
            "Present": "Absent",
            "Absent": "Leave",
            "Leave": "Present"
        }
        self.current_statuses[sid] = cycle_map.get(current, "Present")
        self._render_table()

        # Re-select the row
        items = self.table.tree.get_children()
        if idx < len(items):
            self.table.tree.selection_set(items[idx])

    def _set_selected_status(self, new_status: str):
        sel = self.table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Please select a student row first.", parent=self)
            return

        for item in sel:
            idx = self.table.tree.index(item)
            if idx < len(self.students_list):
                sid = self.students_list[idx]["student_id"]
                self.current_statuses[sid] = new_status

        self._render_table()

    def _mark_all_present(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = "Present"
        self._render_table()

    def _mark_all_absent(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = "Absent"
        self._render_table()

    def _clear_all(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = None
        self._render_table()

    def _save_attendance(self):
        """Batch save attendance to SQLite with transaction and overwrite check."""
        if not self.students_list:
            messagebox.showwarning("No Students", "No students available to mark attendance for.", parent=self)
            return

        # Prepare records
        records_to_save = []
        unmarked_names = []
        for s in self.students_list:
            st = self.current_statuses.get(s["student_id"])
            if st:
                records_to_save.append({"student_id": s["student_id"], "status": st})
            else:
                unmarked_names.append(s["name"])

        if not records_to_save:
            messagebox.showwarning("No Attendance Marked", "Please mark attendance (Present, Absent, or Leave) for at least one student before saving.", parent=self)
            return

        # Warn if some students remain unmarked
        if unmarked_names:
            cont = messagebox.askyesno(
                "Unmarked Students",
                f"{len(unmarked_names)} student(s) remain unmarked.\n\n"
                f"Do you want to save attendance for the {len(records_to_save)} marked students?",
                parent=self
            )
            if not cont:
                return

        # Check if records already existed for this date/class
        has_existing, count = self.att_mgr.has_attendance_for_date(
            self.selected_date,
            self.class_var.get(),
            self.sec_var.get()
        )
        if has_existing:
            overwrite = messagebox.askyesno(
                "Overwrite Existing Attendance?",
                f"Attendance records already exist for {self.selected_date} ({count} existing records).\n\n"
                f"Saving will update and replace previously recorded attendance for this class.\n"
                f"Do you wish to proceed?",
                parent=self
            )
            if not overwrite:
                return

        try:
            saved_count = self.att_mgr.save_batch_attendance(
                attendance_date=self.selected_date,
                records=records_to_save,
                overwrite=True
            )
            self.save_status_lbl.config(text=f"✅ Saved {saved_count} records for {self.selected_date}", fg=COLOR_SUCCESS)
            messagebox.showinfo("Saved", f"Successfully saved attendance for {saved_count} student(s) on {self.selected_date}.", parent=self)
            self._load_sheet()
        except Exception as e:
            messagebox.showerror("Error Saving Attendance", f"Failed to save attendance: {str(e)}", parent=self)

    def refresh(self):
        """Reload classes and sheet."""
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        self._load_sheet()
