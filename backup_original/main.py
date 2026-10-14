"""
Main Application Entry Point for Student Attendance Tracker.
Initializes SQLite database, registers navigation, sets up modern theme, and runs GUI main loop.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Database, DEFAULT_DB_PATH
from student_manager import StudentManager
from attendance_manager import AttendanceManager
from bulk_import import BulkImportManager
from reports import ReportsManager

from ui.styles import (
    configure_app_styles, COLOR_SIDEBAR_BG, COLOR_SIDEBAR_HOVER,
    COLOR_SIDEBAR_ACTIVE, COLOR_SIDEBAR_TEXT, COLOR_SIDEBAR_MUTED,
    COLOR_CONTENT_BG, FONT_NAV, FONT_NAV_ACTIVE, FONT_TITLE, FONT_SMALL
)
from ui.views.dashboard_view import DashboardView
from ui.views.students_view import StudentsView
from ui.views.import_view import ImportView
from ui.views.attendance_view import AttendanceView
from ui.views.reports_view import ReportsView


class AttendanceApp:
    """Root Application Controller."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Student Attendance Tracker — College Experiential Learning")
        self.root.geometry("1240x780")
        self.root.minsize(980, 620)
        self.root.configure(bg=COLOR_CONTENT_BG)

        # Initialize Backend Layers
        self.db = Database(DEFAULT_DB_PATH)
        self.student_mgr = StudentManager(self.db)
        self.att_mgr = AttendanceManager(self.db)
        self.importer = BulkImportManager(self.db, self.student_mgr)
        self.reports_mgr = ReportsManager(self.db)

        # Apply Global Styling
        self.style = configure_app_styles(self.root)

        # Current Active View Name
        self.active_view_name = "dashboard"
        self.nav_buttons = {}

        # Build Main Scaffold
        self._build_scaffold()

        # Keyboard shortcuts
        self.root.bind("<Control-Key-1>", lambda e: self.show_view("dashboard"))
        self.root.bind("<Control-Key-2>", lambda e: self.show_view("students"))
        self.root.bind("<Control-Key-3>", lambda e: self.show_view("import"))
        self.root.bind("<Control-Key-4>", lambda e: self.show_view("attendance"))
        self.root.bind("<Control-Key-5>", lambda e: self.show_view("reports"))

    def _build_scaffold(self):
        # Master Horizontal Container
        self.master_container = tk.Frame(self.root, bg=COLOR_CONTENT_BG)
        self.master_container.pack(fill="both", expand=True)

        # Left Sidebar (Fixed 240px)
        self.sidebar = tk.Frame(self.master_container, bg=COLOR_SIDEBAR_BG, width=240)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Right Content Viewport
        self.content_area = tk.Frame(self.master_container, bg=COLOR_CONTENT_BG)
        self.content_area.pack(side="right", fill="both", expand=True)

        self._build_sidebar()
        self._build_views()

        # Show initial view
        self.show_view("dashboard")

    def _build_sidebar(self):
        # App Branding Logo & Header
        brand_frame = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR_BG, padx=20, pady=24)
        brand_frame.pack(fill="x")

        logo_row = tk.Frame(brand_frame, bg=COLOR_SIDEBAR_BG)
        logo_row.pack(fill="x")

        tk.Label(logo_row, text="🎓", font=("Segoe UI Emoji", 20), bg=COLOR_SIDEBAR_BG, fg="#38BDF8").pack(side="left", padx=(0, 10))
        title_box = tk.Frame(logo_row, bg=COLOR_SIDEBAR_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="TrackAttend", font=("Segoe UI", 14, "bold"), bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_TEXT).pack(anchor="w")
        tk.Label(title_box, text="Student Attendance Tracker", font=FONT_SMALL, bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_MUTED).pack(anchor="w")

        # Separator line
        sep = tk.Frame(self.sidebar, bg="#1E293B", height=1)
        sep.pack(fill="x", padx=16, pady=(0, 16))

        # Nav Section Title
        tk.Label(self.sidebar, text="MAIN NAVIGATION", font=("Segoe UI", 8, "bold"), bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_MUTED, padx=24).pack(anchor="w", pady=(0, 8))

        # Nav Items
        nav_items = [
            ("dashboard", "📊  Dashboard", "Overview & daily metrics"),
            ("students", "👥  Students", "Directory & records"),
            ("import", "📥  Bulk Import", "CSV, TXT, PDF upload"),
            ("attendance", "📅  Attendance", "Mark & edit class records"),
            ("reports", "📈  Reports", "Analytics & CSV export")
        ]

        self.nav_buttons = {}
        for key, label, subtitle in nav_items:
            btn_frame = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR_BG, cursor="hand2")
            btn_frame.pack(fill="x", padx=12, pady=3)

            lbl = tk.Label(
                btn_frame,
                text=label,
                font=FONT_NAV,
                bg=COLOR_SIDEBAR_BG,
                fg=COLOR_SIDEBAR_MUTED,
                anchor="w",
                padx=16,
                pady=10
            )
            lbl.pack(fill="x")

            # Bindings for hover and click
            btn_frame.bind("<Button-1>", lambda e, k=key: self.show_view(k))
            lbl.bind("<Button-1>", lambda e, k=key: self.show_view(k))

            btn_frame.bind("<Enter>", lambda e, f=btn_frame, l=lbl, k=key: self._on_nav_hover(f, l, k))
            btn_frame.bind("<Leave>", lambda e, f=btn_frame, l=lbl, k=key: self._on_nav_leave(f, l, k))
            lbl.bind("<Enter>", lambda e, f=btn_frame, l=lbl, k=key: self._on_nav_hover(f, l, k))
            lbl.bind("<Leave>", lambda e, f=btn_frame, l=lbl, k=key: self._on_nav_leave(f, l, k))

            self.nav_buttons[key] = (btn_frame, lbl)

        # Bottom System Info Footer
        footer = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR_BG, padx=20, pady=16)
        footer.pack(side="bottom", fill="x")

        status_pill = tk.Frame(footer, bg="#1E293B", padx=12, pady=8)
        status_pill.pack(fill="x")

        tk.Label(status_pill, text="● SQLite Database Active", font=FONT_SMALL, bg="#1E293B", fg="#10B981").pack(anchor="w")
        tk.Label(status_pill, text="Offline Desktop Application", font=FONT_SMALL, bg="#1E293B", fg=COLOR_SIDEBAR_MUTED).pack(anchor="w")

    def _on_nav_hover(self, frame: tk.Frame, label: tk.Label, key: str):
        if key != self.active_view_name:
            frame.configure(bg=COLOR_SIDEBAR_HOVER)
            label.configure(bg=COLOR_SIDEBAR_HOVER, fg=COLOR_SIDEBAR_TEXT)

    def _on_nav_leave(self, frame: tk.Frame, label: tk.Label, key: str):
        if key != self.active_view_name:
            frame.configure(bg=COLOR_SIDEBAR_BG)
            label.configure(bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_MUTED)

    def _build_views(self):
        """Construct the view frames inside content area."""
        self.views = {}

        # 1. Dashboard
        self.views["dashboard"] = DashboardView(
            self.content_area,
            db=self.db,
            student_mgr=self.student_mgr,
            att_mgr=self.att_mgr,
            reports_mgr=self.reports_mgr,
            navigate_to=self.show_view
        )

        # 2. Students Directory
        self.views["students"] = StudentsView(
            self.content_area,
            db=self.db,
            student_mgr=self.student_mgr,
            navigate_to=self.show_view
        )

        # 3. Bulk Import
        self.views["import"] = ImportView(
            self.content_area,
            importer=self.importer,
            on_import_success=self._on_import_success
        )

        # 4. Attendance
        self.views["attendance"] = AttendanceView(
            self.content_area,
            db=self.db,
            student_mgr=self.student_mgr,
            att_mgr=self.att_mgr
        )

        # 5. Reports
        self.views["reports"] = ReportsView(
            self.content_area,
            db=self.db,
            student_mgr=self.student_mgr,
            reports_mgr=self.reports_mgr
        )

    def _on_import_success(self):
        """Triggered after students are successfully imported."""
        # Refresh all views so new students appear everywhere
        for name, view in self.views.items():
            if hasattr(view, "refresh"):
                view.refresh()
        # Switch to students view to review imported students
        self.show_view("students")

    def show_view(self, view_name: str):
        """Switch active view and update sidebar styling."""
        if view_name not in self.views:
            return

        self.active_view_name = view_name

        # Update sidebar visual styles
        for key, (frame, label) in self.nav_buttons.items():
            if key == view_name:
                frame.configure(bg=COLOR_SIDEBAR_ACTIVE)
                label.configure(bg=COLOR_SIDEBAR_ACTIVE, fg="#FFFFFF", font=FONT_NAV_ACTIVE)
            else:
                frame.configure(bg=COLOR_SIDEBAR_BG)
                label.configure(bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_MUTED, font=FONT_NAV)

        # Hide all views and show target view
        for name, view_widget in self.views.items():
            if name == view_name:
                view_widget.pack(fill="both", expand=True)
                if hasattr(view_widget, "refresh"):
                    view_widget.refresh()
            else:
                view_widget.pack_forget()


def main():
    """Main launcher."""
    root = tk.Tk()
    app = AttendanceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
