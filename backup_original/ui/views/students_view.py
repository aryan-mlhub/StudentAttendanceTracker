"""
Students View: Complete student directory with live search, class/section filtering,
column sorting, single student creation, editing, deletion with confirmation, and counters.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
from database import Database
from student_manager import StudentManager
from ui.styles import (
    COLOR_CONTENT_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_DANGER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, FONT_TITLE, FONT_SUBTITLE,
    FONT_HEADING, FONT_BODY, FONT_SMALL
)
from ui.components import CustomTable, StudentDialog


class StudentsView(tk.Frame):
    """Student management screen."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, navigate_to: Callable[[str], None]):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.navigate_to = navigate_to

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header Area
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Student Directory", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.count_label = tk.Label(title_box, text="Total: 0 registered students", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY)
        self.count_label.pack(anchor="w")

        # Top Action Buttons
        btn_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="➕ Add Student", style="Primary.TButton", command=self._add_student).pack(side="left", padx=(0, 8))
        ttk.Button(btn_box, text="📥 Bulk Import", style="Success.TButton", command=lambda: self.navigate_to("import")).pack(side="left")

        # Controls & Filter Bar (Search, Class filter, Section filter)
        control_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        control_bar.pack(fill="x", padx=24, pady=(0, 14))

        # Search Box
        tk.Label(control_bar, text="🔍 Search:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        self.search_entry = ttk.Entry(control_bar, textvariable=self.search_var, width=24, font=FONT_BODY)
        self.search_entry.pack(side="left", padx=(0, 18))

        # Class Filter
        tk.Label(control_bar, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(control_bar, textvariable=self.class_var, state="readonly", width=12)
        self.class_combo.pack(side="left", padx=(0, 14))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        # Section Filter
        tk.Label(control_bar, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(control_bar, textvariable=self.sec_var, state="readonly", width=8)
        self.sec_combo.pack(side="left", padx=(0, 18))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        # Clear Filters
        ttk.Button(control_bar, text="Reset Filters", style="Secondary.TButton", command=self._reset_filters).pack(side="left")

        # Action Buttons on Right: Edit, Delete
        action_sub = tk.Frame(control_bar, bg=COLOR_CARD_BG)
        action_sub.pack(side="right")
        ttk.Button(action_sub, text="✏️ Edit Selected", style="Secondary.TButton", command=self._edit_selected).pack(side="left", padx=(0, 6))
        ttk.Button(action_sub, text="🗑️ Delete Selected", style="Danger.TButton", command=self._delete_selected).pack(side="left")

        # Table
        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        columns = ["id", "roll_no", "name", "class_name", "section", "created_at"]
        headings = ["ID", "Roll Number", "Student Name", "Class / Dept", "Section", "Registered At"]
        widths = [60, 140, 240, 150, 100, 180]
        aligns = ["c", "w", "w", "w", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)

        # Double click to edit
        self.table.tree.bind("<Double-1>", lambda e: self._edit_selected())

    def _on_class_change(self):
        # Update section dropdown options based on selected class
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._apply_filters()

    def _reset_filters(self):
        self.search_var.set("")
        self.class_var.set("All")
        self.sec_var.set("All")
        self.refresh()

    def _apply_filters(self):
        query = self.search_var.get().strip()
        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()

        students = self.student_mgr.get_all_students(
            search_query=query,
            class_filter=c_filter,
            section_filter=s_filter
        )
        self._populate_table(students)

    def _populate_table(self, students):
        self.table.clear()
        for s in students:
            self.table.insert_row((
                s["id"],
                s["roll_no"],
                s["name"],
                s["class_name"] or "—",
                s["section"] or "—",
                s["created_at"]
            ))

    def _get_selected_student_id(self) -> Optional[int]:
        selected = self.table.tree.selection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select a student from the table first.", parent=self)
            return None
        values = self.table.tree.item(selected[0])["values"]
        return int(values[0])

    def _add_student(self):
        def save_callback(roll, name, c_name, sec):
            self.student_mgr.add_student(roll, name, c_name, sec)
            self.refresh()
            messagebox.showinfo("Success", f"Student '{name}' ({roll}) added successfully.", parent=self)
        StudentDialog(self, title="Add New Student", on_save=save_callback)

    def _edit_selected(self):
        student_id = self._get_selected_student_id()
        if not student_id:
            return

        student = self.student_mgr.get_student_by_id(student_id)
        if not student:
            return

        def save_callback(roll, name, c_name, sec):
            self.student_mgr.update_student(student_id, roll, name, c_name, sec)
            self.refresh()
            messagebox.showinfo("Updated", f"Student '{name}' details updated.", parent=self)

        StudentDialog(self, title="Edit Student", student_data=student, on_save=save_callback)

    def _delete_selected(self):
        student_id = self._get_selected_student_id()
        if not student_id:
            return

        student = self.student_mgr.get_student_by_id(student_id)
        if not student:
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete student:\n\n"
            f"Roll No: {student['roll_no']}\n"
            f"Name: {student['name']}\n\n"
            f"Note: This will also remove all historical attendance records for this student.",
            parent=self
        )
        if confirm:
            self.student_mgr.delete_student(student_id)
            self.refresh()
            messagebox.showinfo("Deleted", "Student and attendance records deleted.", parent=self)

    def refresh(self):
        """Reload class filters, counts, and student table."""
        # Update dropdowns
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        total = self.student_mgr.get_total_students_count()
        self.count_label.config(text=f"Total: {total} registered students")

        self._apply_filters()
