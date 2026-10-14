"""
Bulk Import View: Dedicated, faculty-friendly 5-step guided bulk student import wizard.
Supports CSV, TXT, PDF, and XLSX with validation preview, inline record editing,
duplicate conflict handling (skip vs update), templates export, and transactional commit.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import shutil
from typing import Callable, Optional, Dict, Any, List
from bulk_import import BulkImportManager, ImportValidationStatus
from ui.styles import (
    COLOR_CONTENT_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADING, FONT_BODY, FONT_SMALL, FONT_BADGE
)
from ui.components import CustomTable, RecordEditDialog


class ImportView(tk.Frame):
    """Faculty-friendly guided bulk import wizard."""

    def __init__(self, parent, importer: BulkImportManager, on_import_success: Callable[[], None]):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.importer = importer
        self.on_import_success = on_import_success

        self.selected_file_path: Optional[Path] = None
        self.current_summary: Dict[str, int] = {}
        self.templates_dir = Path(__file__).resolve().parent.parent.parent / "templates"

        self._build_ui()

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 12))

        tk.Label(header, text="Bulk Student Import", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(
            header,
            text="Easily import entire class rosters at once using CSV, TXT, or text-based PDF files with automatic validation.",
            font=FONT_SMALL,
            bg=COLOR_CONTENT_BG,
            fg=COLOR_TEXT_SECONDARY
        ).pack(anchor="w")

        # Top Action & Template Buttons Bar
        tmpl_bar = tk.Frame(self, bg=COLOR_CONTENT_BG)
        tmpl_bar.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(tmpl_bar, text="Sample Templates:", font=FONT_HEADING, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        ttk.Button(tmpl_bar, text="📥 Download CSV Template", style="Secondary.TButton", command=self._export_csv_template).pack(side="left", padx=(0, 6))
        ttk.Button(tmpl_bar, text="📝 Create TXT Template", style="Secondary.TButton", command=self._export_txt_template).pack(side="left", padx=(0, 6))
        ttk.Button(tmpl_bar, text="📄 View Supported PDF Formats", style="Secondary.TButton", command=self._show_pdf_help).pack(side="left")

        # Step 1: Upload Drop Area
        self.upload_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=16, highlightbackground="#CBD5E1", highlightthickness=1)
        self.upload_card.pack(fill="x", padx=24, pady=(0, 14))

        upload_inner = tk.Frame(self.upload_card, bg=COLOR_CARD_BG)
        upload_inner.pack(fill="x")

        # Left side icon & prompt
        prompt_box = tk.Frame(upload_inner, bg=COLOR_CARD_BG)
        prompt_box.pack(side="left", fill="x", expand=True)

        self.file_status_title = tk.Label(prompt_box, text="📂 Step 1: Select Student List File (.csv, .txt, .pdf, .xlsx)", font=FONT_SUBTITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.file_status_title.pack(anchor="w")

        self.file_status_desc = tk.Label(
            prompt_box,
            text="No file selected yet. Choose a class file from your computer to preview records.",
            font=FONT_BODY,
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_SECONDARY
        )
        self.file_status_desc.pack(anchor="w", pady=(3, 0))

        # Right side button
        btn_box = tk.Frame(upload_inner, bg=COLOR_CARD_BG)
        btn_box.pack(side="right")

        self.browse_btn = ttk.Button(btn_box, text="Browse & Select File...", style="Primary.TButton", command=self._browse_file)
        self.browse_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ttk.Button(btn_box, text="Clear", style="Secondary.TButton", command=self._clear_all)
        self.clear_btn.pack(side="left")

        # Step 2 & 3: Validation Summary & Action Toolbar
        self.summary_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=10, highlightbackground="#E2E8F0", highlightthickness=1)
        self.summary_bar.pack(fill="x", padx=24, pady=(0, 10))

        # Stat pills
        self.lbl_total = tk.Label(self.summary_bar, text="Detected: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.lbl_total.pack(side="left", padx=(0, 14))

        self.lbl_valid = tk.Label(self.summary_bar, text="Valid: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_SUCCESS)
        self.lbl_valid.pack(side="left", padx=(0, 14))

        self.lbl_dup_file = tk.Label(self.summary_bar, text="Dupes in File: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_WARNING)
        self.lbl_dup_file.pack(side="left", padx=(0, 14))

        self.lbl_dup_db = tk.Label(self.summary_bar, text="In Database: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg="#6366F1")
        self.lbl_dup_db.pack(side="left", padx=(0, 14))

        self.lbl_invalid = tk.Label(self.summary_bar, text="Invalid: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_DANGER)
        self.lbl_invalid.pack(side="left", padx=(0, 18))

        # Table Row Actions on Right
        tbl_actions = tk.Frame(self.summary_bar, bg=COLOR_CARD_BG)
        tbl_actions.pack(side="right")

        ttk.Button(tbl_actions, text="Select All Valid", style="Secondary.TButton", command=self._select_all_valid).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="Deselect All", style="Secondary.TButton", command=self._deselect_all).pack(side="left", padx=(0, 6))
        ttk.Button(tbl_actions, text="✏️ Edit Record", style="Secondary.TButton", command=self._edit_selected_row).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="🗑️ Remove", style="Danger.TButton", command=self._remove_selected_row).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="🔍 Raw Text", style="Secondary.TButton", command=self._view_raw_text).pack(side="left")

        # Preview Table
        preview_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        preview_container.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        columns = ["selected", "roll_no", "name", "class_name", "section", "status", "details"]
        headings = ["Import?", "Roll Number", "Student Name", "Class", "Section", "Validation Status", "Details / Diagnosis"]
        widths = [70, 120, 200, 100, 70, 150, 240]
        aligns = ["c", "w", "w", "w", "c", "c", "w"]

        self.preview_table = CustomTable(preview_container, columns, headings, widths, aligns)
        self.preview_table.pack(fill="both", expand=True)

        # Click or space toggles checkbox
        self.preview_table.tree.bind("<ButtonRelease-1>", self._on_table_click)
        self.preview_table.tree.bind("<Double-1>", lambda e: self._edit_selected_row())

        # Step 4 & 5: Bottom Confirmation & Import Action Bar
        bottom_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=14, highlightbackground="#CBD5E1", highlightthickness=1)
        bottom_bar.pack(fill="x", padx=24, pady=(0, 18))

        # Duplicate Handling Options
        dup_frame = tk.Frame(bottom_bar, bg=COLOR_CARD_BG)
        dup_frame.pack(side="left")

        tk.Label(dup_frame, text="Duplicate Handling Option:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")

        self.dup_action_var = tk.StringVar(value="skip")
        r1 = ttk.Radiobutton(dup_frame, text="Skip duplicates (safely add only new students)", variable=self.dup_action_var, value="skip")
        r1.pack(side="left", padx=(0, 16))
        r2 = ttk.Radiobutton(dup_frame, text="Update existing students with details from file", variable=self.dup_action_var, value="update")
        r2.pack(side="left")

        # Action Buttons on Right
        exec_box = tk.Frame(bottom_bar, bg=COLOR_CARD_BG)
        exec_box.pack(side="right")

        self.import_btn = ttk.Button(exec_box, text="✅ Confirm & Import Students", style="Success.TButton", command=self._execute_import)
        self.import_btn.pack(side="right", padx=(8, 0))

        ttk.Button(exec_box, text="Cancel Import", style="Secondary.TButton", command=self._clear_all).pack(side="right")

    def _browse_file(self):
        """Open file dialog for TXT, CSV, PDF, XLSX."""
        file_path = filedialog.askopenfilename(
            title="Select Student Class List",
            filetypes=[
                ("All Supported Files", "*.csv;*.txt;*.pdf;*.xlsx;*.xls"),
                ("CSV Files", "*.csv"),
                ("Text Files", "*.txt"),
                ("PDF Documents", "*.pdf"),
                ("Excel Files", "*.xlsx;*.xls")
            ]
        )
        if not file_path:
            return

        self.selected_file_path = Path(file_path)
        self._load_and_preview_file(self.selected_file_path)

    def _load_and_preview_file(self, path: Path):
        """Load records and render preview."""
        res = self.importer.load_file(path)

        if not res["success"]:
            # Check if scanned PDF diagnosis
            if res.get("is_scanned_pdf"):
                messagebox.showerror("Scanned PDF Detected", res["error"], parent=self)
            else:
                messagebox.showerror("Import Error", res["error"], parent=self)
            self._clear_all()
            return

        # Update file banner
        size_kb = path.stat().st_size / 1024
        self.file_status_title.config(text=f"📄 Selected File: {path.name} ({size_kb:.1f} KB)")
        self.file_status_desc.config(text=f"Format: {path.suffix.upper()} | Path: {path}")

        # Render preview
        self._render_preview()

    def _render_preview(self):
        """Populate the preview table from importer records."""
        self.preview_table.clear()
        records = self.importer.current_records
        summary = self.importer.validate_records()
        self.current_summary = summary

        # Update summary counters
        self.lbl_total.config(text=f"Total Detected: {summary['total_detected']}")
        self.lbl_valid.config(text=f"Valid: {summary['valid_count']}")
        self.lbl_dup_file.config(text=f"Dupes in File: {summary['duplicate_file_count']}")
        self.lbl_dup_db.config(text=f"In Database: {summary['duplicate_db_count']}")
        self.lbl_invalid.config(text=f"Invalid: {summary['invalid_count']}")

        self.import_btn.config(text=f"✅ Confirm & Import {summary['ready_to_import']} Students")

        for r in records:
            check_mark = "☑ YES" if r["selected"] else "☐ NO"
            tag = "status_valid" if r["status"] == ImportValidationStatus.VALID else (
                "status_warning" if "Duplicate" in r["status"] or "Database" in r["status"] else "status_danger"
            )

            self.preview_table.insert_row(
                (
                    check_mark,
                    r["roll_no"] or "(empty)",
                    r["name"] or "(empty)",
                    r["class_name"] or "—",
                    r["section"] or "—",
                    r["status"],
                    r["details"]
                ),
                tags=(tag,)
            )

    def _on_table_click(self, event):
        """Toggle record selection when clicking the first column or anywhere on the row."""
        region = self.preview_table.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return

        item = self.preview_table.tree.identify_row(event.y)
        col = self.preview_table.tree.identify_column(event.x)
        if not item:
            return

        # If clicked on the 'Import?' column (#1) or double clicked
        if col == "#1":
            idx = self.preview_table.tree.index(item)
            if idx < len(self.importer.current_records):
                rec = self.importer.current_records[idx]
                new_state = not rec["selected"]
                self.importer.toggle_record_selection(rec["id"], new_state)
                self._render_preview()

    def _select_all_valid(self):
        self.importer.select_all_valid()
        self._render_preview()

    def _deselect_all(self):
        self.importer.deselect_all()
        self._render_preview()

    def _edit_selected_row(self):
        sel = self.preview_table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Record", "Please select a row from the preview table to edit.", parent=self)
            return

        idx = self.preview_table.tree.index(sel[0])
        if idx >= len(self.importer.current_records):
            return

        record = self.importer.current_records[idx]

        def save_callback(rec_id, r, n, c, s):
            self.importer.update_record(rec_id, r, n, c, s)
            self._render_preview()

        RecordEditDialog(self, record=record, on_save=save_callback)

    def _remove_selected_row(self):
        sel = self.preview_table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Record", "Please select a row from the preview table to remove.", parent=self)
            return

        idx = self.preview_table.tree.index(sel[0])
        if idx >= len(self.importer.current_records):
            return

        record = self.importer.current_records[idx]
        self.importer.remove_record(record["id"])
        self._render_preview()

    def _view_raw_text(self):
        """Open modal with raw extracted text or unparsed items."""
        raw_text = getattr(self.importer, "raw_text_preview", "")
        unparsed = self.importer.unparsed_items

        top = tk.Toplevel(self)
        top.title("Extracted Content & Unparsed Lines")
        top.geometry("640x480")
        top.configure(bg=COLOR_CONTENT_BG)

        frame = tk.Frame(top, bg=COLOR_CARD_BG, padx=16, pady=16)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(frame, text="Extraction Diagnostics & Unparsed Items", font=FONT_SUBTITLE, bg=COLOR_CARD_BG).pack(anchor="w", pady=(0, 8))

        txt_widget = tk.Text(frame, font=("Consolas", 10), wrap="none")
        s = ttk.Scrollbar(frame, command=txt_widget.yview)
        txt_widget.config(yscrollcommand=s.set)
        s.pack(side="right", fill="y")
        txt_widget.pack(fill="both", expand=True)

        content = []
        if unparsed:
            content.append(f"=== UNPARSED / SKIPPED LINES ({len(unparsed)}) ===")
            for u in unparsed:
                content.append(f"Line {u.get('line_num', '?')}: {u.get('text', '')} -> {u.get('reason', '')}")
            content.append("\n" + "="*50 + "\n")

        if raw_text:
            content.append("=== RAW EXTRACTED TEXT ===")
            content.append(raw_text)

        if not content:
            content.append("No unparsed items or raw text recorded.")

        txt_widget.insert("1.0", "\n".join(content))
        txt_widget.config(state="disabled")

    def _execute_import(self):
        """Execute transactional insertion."""
        summary = self.importer.validate_records()
        ready = summary["ready_to_import"]

        if ready == 0:
            messagebox.showwarning("No Records Selected", "There are no valid records selected for import.", parent=self)
            return

        action = self.dup_action_var.get()
        confirm_msg = (
            f"You are about to import {ready} student record(s) into the database.\n\n"
            f"• Duplicate policy: {'Skip existing students' if action == 'skip' else 'Update existing students'}\n"
            f"• Database action: Atomic SQLite transaction\n\n"
            f"Proceed with import?"
        )
        if not messagebox.askyesno("Confirm Bulk Import", confirm_msg, parent=self):
            return

        # Perform atomic import
        res = self.importer.execute_import(duplicate_action=action)

        if res["success"]:
            msg = (
                f"🎉 Bulk Student Import Completed Successfully!\n\n"
                f"• New Students Added: {res['added']}\n"
                f"• Students Updated: {res['updated']}\n"
                f"• Duplicates Skipped: {res['skipped']}\n"
                f"• Failed Records: {res['failed']}"
            )
            messagebox.showinfo("Import Complete", msg, parent=self)
            self._clear_all()
            if self.on_import_success:
                self.on_import_success()
        else:
            messagebox.showerror("Import Failed", res.get("error", "An unknown error occurred during import."), parent=self)

    def _clear_all(self):
        """Reset state."""
        self.selected_file_path = None
        self.importer.current_records = []
        self.importer.unparsed_items = []
        self.preview_table.clear()
        self.file_status_title.config(text="📂 Step 1: Select Student List File (.csv, .txt, .pdf, .xlsx)")
        self.file_status_desc.config(text="No file selected yet. Choose a class file from your computer to preview records.")
        self.lbl_total.config(text="Detected: 0")
        self.lbl_valid.config(text="Valid: 0")
        self.lbl_dup_file.config(text="Dupes in File: 0")
        self.lbl_dup_db.config(text="In Database: 0")
        self.lbl_invalid.config(text="Invalid: 0")
        self.import_btn.config(text="✅ Confirm & Import Students")

    def _export_csv_template(self):
        src = self.templates_dir / "sample_students.csv"
        dest = filedialog.asksaveasfilename(
            title="Save CSV Template",
            defaultextension=".csv",
            initialfile="student_import_template.csv",
            filetypes=[("CSV Files", "*.csv")]
        )
        if dest:
            shutil.copyfile(src, dest)
            messagebox.showinfo("Template Saved", f"CSV template saved to:\n{dest}", parent=self)

    def _export_txt_template(self):
        src = self.templates_dir / "sample_students_pipe.txt"
        dest = filedialog.asksaveasfilename(
            title="Save TXT Template",
            defaultextension=".txt",
            initialfile="student_import_template.txt",
            filetypes=[("Text Files", "*.txt")]
        )
        if dest:
            shutil.copyfile(src, dest)
            messagebox.showinfo("Template Saved", f"TXT template saved to:\n{dest}", parent=self)

    def _show_pdf_help(self):
        msg = (
            "📄 Supported PDF Format Guidelines:\n\n"
            "1. Text-based PDFs: Must have selectable text (exported from Word, Excel, or Student Portal).\n"
            "2. Common Layouts Supported:\n"
            "   • Labeled: 'Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A'\n"
            "   • Tabular: '101    Rahul Sharma    CSE    A'\n\n"
            "3. Scanned PDFs: Image-only scans require OCR. For maximum accuracy, export directly as CSV from your institution's portal."
        )
        messagebox.showinfo("PDF Guidelines", msg, parent=self)
