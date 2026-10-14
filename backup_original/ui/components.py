"""
Reusable UI components: StatCard, CustomTable with sorting and empty state, and modal dialogs.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Optional, Callable
from ui.styles import (
    COLOR_CARD_BG, COLOR_CARD_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_PRIMARY, COLOR_PRIMARY_LIGHT, COLOR_CONTENT_BG, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, FONT_HEADING, FONT_BODY, FONT_STAT_NUM,
    FONT_SMALL, FONT_SUBTITLE, FONT_BADGE
)


class StatCard(tk.Frame):
    """Modern elevated statistics card with icon, label, primary value, and subtitle."""

    def __init__(self, parent, title: str, value: str = "0", icon: str = "📊", accent_color: str = COLOR_PRIMARY, **kwargs):
        super().__init__(parent, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=16, pady=14, **kwargs)
        self.accent_color = accent_color

        # Top row: icon + title
        top_frame = tk.Frame(self, bg=COLOR_CARD_BG)
        top_frame.pack(fill="x", anchor="w")

        self.icon_label = tk.Label(top_frame, text=icon, font=("Segoe UI Emoji", 14), bg=COLOR_CARD_BG, fg=accent_color)
        self.icon_label.pack(side="left", padx=(0, 8))

        self.title_label = tk.Label(top_frame, text=title.upper(), font=FONT_SMALL, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.title_label.pack(side="left")

        # Big Value
        self.value_label = tk.Label(self, text=value, font=FONT_STAT_NUM, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.value_label.pack(anchor="w", pady=(8, 2))

        # Bottom subtitle / hint
        self.sub_label = tk.Label(self, text="", font=FONT_SMALL, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.sub_label.pack(anchor="w")

    def update_value(self, value: str, subtext: str = ""):
        self.value_label.config(text=str(value))
        if subtext:
            self.sub_label.config(text=subtext)


class CustomTable(tk.Frame):
    """
    Modern styled Treeview wrapper with scrollbars, sortable columns,
    zebra striping, and empty state message.
    """

    def __init__(
        self,
        parent,
        columns: List[str],
        headings: List[str],
        col_widths: Optional[List[int]] = None,
        col_aligns: Optional[List[str]] = None,
        show_empty_state: bool = True,
        empty_text: str = "No records found.",
        **kwargs
    ):
        super().__init__(parent, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, **kwargs)
        self.columns = columns
        self.headings = headings
        self.empty_text = empty_text
        self.sort_column = None
        self.sort_reverse = False

        # Container
        self.tree_frame = tk.Frame(self, bg=COLOR_CARD_BG)
        self.tree_frame.pack(fill="both", expand=True)

        # Scrollbars
        self.y_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.x_scroll = ttk.Scrollbar(self.tree_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=columns,
            show="headings",
            style="Custom.Treeview",
            yscrollcommand=self.y_scroll.set,
            xscrollcommand=self.x_scroll.set,
            selectmode="extended"
        )
        self.y_scroll.config(command=self.tree.yview)
        self.x_scroll.config(command=self.tree.xview)

        # Layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.y_scroll.grid(row=0, column=1, sticky="ns")
        self.x_scroll.grid(row=1, column=0, sticky="ew")

        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

        # Configure columns
        for idx, col in enumerate(columns):
            heading = headings[idx] if idx < len(headings) else col
            width = col_widths[idx] if col_widths and idx < len(col_widths) else 120
            align = col_aligns[idx] if col_aligns and idx < len(col_aligns) else "w"

            self.tree.heading(col, text=heading, command=lambda c=col: self._on_header_click(c))
            self.tree.column(col, width=width, anchor=align, minwidth=60)

        # Tag styles for row status and alternating backgrounds
        self.tree.tag_configure("even", background="#FFFFFF")
        self.tree.tag_configure("odd", background="#F8FAFC")
        self.tree.tag_configure("status_valid", background="#ECFDF5", foreground="#065F46")
        self.tree.tag_configure("status_warning", background="#FFFBEB", foreground="#92400E")
        self.tree.tag_configure("status_danger", background="#FEF2F2", foreground="#991B1B")
        self.tree.tag_configure("defaulter", background="#FEF2F2", foreground="#B91C1C")

    def _on_header_click(self, col: str):
        """Header sorting handler."""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        # Sort items in tree
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        # Try numeric sort first
        try:
            items.sort(key=lambda t: float(t[0].replace("%", "").strip()), reverse=self.sort_reverse)
        except ValueError:
            items.sort(key=lambda t: str(t[0]).lower(), reverse=self.sort_reverse)

        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)

        # Update headings with sort indicator
        for c in self.columns:
            h_text = self.headings[self.columns.index(c)]
            if c == col:
                h_text += " ▲" if not self.sort_reverse else " ▼"
            self.tree.heading(c, text=h_text)

    def clear(self):
        """Remove all rows."""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values: Tuple[Any, ...] | List[Any], tags: Tuple[str, ...] = ()):
        idx = len(self.tree.get_children())
        row_tag = "even" if idx % 2 == 0 else "odd"
        combined_tags = (row_tag,) + tuple(tags)
        return self.tree.insert("", "end", values=values, tags=combined_tags)


class StudentDialog(tk.Toplevel):
    """Modal dialog for creating or updating a single student record."""

    def __init__(self, parent, title: str = "Add Student", student_data: Optional[Dict[str, Any]] = None, on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=COLOR_CONTENT_BG)

        self.student_data = student_data or {}
        self.on_save = on_save
        self.saved = False

        self._create_widgets()
        self.center_window(460, 360)

    def center_window(self, w: int, h: int):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _create_widgets(self):
        main_frame = tk.Frame(self, bg=COLOR_CARD_BG, padx=24, pady=20)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Header
        header = tk.Label(main_frame, text=self.title(), font=FONT_SUBTITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        header.pack(anchor="w", pady=(0, 16))

        # Roll Number
        tk.Label(main_frame, text="Roll Number *", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.roll_entry = ttk.Entry(main_frame, font=FONT_BODY)
        self.roll_entry.pack(fill="x", pady=(2, 10))
        if self.student_data.get("roll_no"):
            self.roll_entry.insert(0, self.student_data["roll_no"])

        # Name
        tk.Label(main_frame, text="Full Name *", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.name_entry = ttk.Entry(main_frame, font=FONT_BODY)
        self.name_entry.pack(fill="x", pady=(2, 10))
        if self.student_data.get("name"):
            self.name_entry.insert(0, self.student_data["name"])

        # Class and Section (two columns)
        two_col = tk.Frame(main_frame, bg=COLOR_CARD_BG)
        two_col.pack(fill="x", pady=(0, 16))

        c1 = tk.Frame(two_col, bg=COLOR_CARD_BG)
        c1.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(c1, text="Class / Department", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.class_entry = ttk.Entry(c1, font=FONT_BODY)
        self.class_entry.pack(fill="x", pady=(2, 0))
        if self.student_data.get("class_name"):
            self.class_entry.insert(0, self.student_data["class_name"])

        c2 = tk.Frame(two_col, bg=COLOR_CARD_BG)
        c2.pack(side="right", fill="x", expand=True)
        tk.Label(c2, text="Section", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.sec_entry = ttk.Entry(c2, font=FONT_BODY)
        self.sec_entry.pack(fill="x", pady=(2, 0))
        if self.student_data.get("section"):
            self.sec_entry.insert(0, self.student_data["section"])

        # Buttons
        btn_frame = tk.Frame(main_frame, bg=COLOR_CARD_BG)
        btn_frame.pack(fill="x", pady=(10, 0))

        cancel_btn = ttk.Button(btn_frame, text="Cancel", style="Secondary.TButton", command=self.destroy)
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ttk.Button(btn_frame, text="Save Student", style="Primary.TButton", command=self._save)
        save_btn.pack(side="right")

    def _save(self):
        roll = self.roll_entry.get().strip()
        name = self.name_entry.get().strip()
        c_name = self.class_entry.get().strip()
        sec = self.sec_entry.get().strip().upper()

        if not roll:
            messagebox.showwarning("Validation Error", "Roll number is required.", parent=self)
            self.roll_entry.focus_set()
            return

        if not name:
            messagebox.showwarning("Validation Error", "Student name is required.", parent=self)
            self.name_entry.focus_set()
            return

        if self.on_save:
            try:
                self.on_save(roll, name, c_name, sec)
                self.saved = True
                self.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)


class RecordEditDialog(tk.Toplevel):
    """Modal dialog for inline editing a single preview row in the Bulk Import wizard."""

    def __init__(self, parent, record: Dict[str, Any], on_save: Callable):
        super().__init__(parent)
        self.title("Edit Record in Import Preview")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=COLOR_CONTENT_BG)

        self.record = record
        self.on_save = on_save

        self._create_widgets()
        self.center_window(440, 320)

    def center_window(self, w: int, h: int):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _create_widgets(self):
        main = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=20)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(main, text="Edit Preview Record", font=FONT_SUBTITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w", pady=(0, 12))

        tk.Label(main, text="Roll Number", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.roll = ttk.Entry(main, font=FONT_BODY)
        self.roll.pack(fill="x", pady=(2, 8))
        self.roll.insert(0, self.record.get("roll_no", ""))

        tk.Label(main, text="Student Name", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.name = ttk.Entry(main, font=FONT_BODY)
        self.name.pack(fill="x", pady=(2, 8))
        self.name.insert(0, self.record.get("name", ""))

        two = tk.Frame(main, bg=COLOR_CARD_BG)
        two.pack(fill="x", pady=(0, 14))

        f1 = tk.Frame(two, bg=COLOR_CARD_BG)
        f1.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(f1, text="Class", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.c_name = ttk.Entry(f1, font=FONT_BODY)
        self.c_name.pack(fill="x", pady=(2, 0))
        self.c_name.insert(0, self.record.get("class_name", ""))

        f2 = tk.Frame(two, bg=COLOR_CARD_BG)
        f2.pack(side="right", fill="x", expand=True)
        tk.Label(f2, text="Section", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.sec = ttk.Entry(f2, font=FONT_BODY)
        self.sec.pack(fill="x", pady=(2, 0))
        self.sec.insert(0, self.record.get("section", ""))

        bf = tk.Frame(main, bg=COLOR_CARD_BG)
        bf.pack(fill="x")
        ttk.Button(bf, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(bf, text="Update Record", style="Primary.TButton", command=self._do_update).pack(side="right")

    def _do_update(self):
        r = self.roll.get().strip()
        n = self.name.get().strip()
        c = self.c_name.get().strip()
        s = self.sec.get().strip().upper()
        self.on_save(self.record["id"], r, n, c, s)
        self.destroy()
