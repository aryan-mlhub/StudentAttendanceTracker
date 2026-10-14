"""
Automated Verification Test Suite for consolidated main.py.
Imports 100% of classes, managers, parsers, algorithms, and UI scaffolding
directly from main.py to verify self-contained correctness.
"""

import unittest
import tempfile
import csv
from pathlib import Path
import tkinter as tk

# Import directly from the consolidated main.py
from main import (
    Database,
    StudentManager,
    DuplicateRollNumberError,
    ValidationError,
    PDFParser,
    PDFParseResult,
    BulkImportManager,
    ImportValidationStatus,
    AttendanceManager,
    ReportsManager,
    ATTENDANCE_DEFICIT_THRESHOLD,
    AttendanceApp,
    StatCard,
    CustomTable,
    StudentDialog,
    RecordEditDialog,
    DashboardView,
    StudentsView,
    AttendanceView,
    ReportsView,
    ImportView,
    configure_app_styles
)


class TestConsolidatedMain(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_consolidated.db"
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"

        self.db = Database(self.db_path)
        self.student_mgr = StudentManager(self.db)
        self.att_mgr = AttendanceManager(self.db)
        self.importer = BulkImportManager(self.db, self.student_mgr)
        self.reports_mgr = ReportsManager(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_and_student_crud(self):
        """Test database initialization, constraints, transactions, and student operations."""
        # 1. Add students
        s1 = self.student_mgr.add_student("CS101", "Alice Wonder", "CSE", "A")
        s2 = self.student_mgr.add_student("CS102", "Bob Smith", "CSE", "A")
        self.assertGreater(s1, 0)
        self.assertGreater(s2, 0)

        # 2. Duplicate roll number prevention
        with self.assertRaises(DuplicateRollNumberError):
            self.student_mgr.add_student("cs101", "Another Alice", "CSE", "A")

        # 3. Validation error on empty name or roll
        with self.assertRaises(ValidationError):
            self.student_mgr.add_student("", "No Roll")
        with self.assertRaises(ValidationError):
            self.student_mgr.add_student("CS103", "")

        # 4. Update student
        self.student_mgr.update_student(s1, "CS101", "Alice Updated", "CSE", "B")
        st = self.student_mgr.get_student_by_id(s1)
        self.assertEqual(st["name"], "Alice Updated")
        self.assertEqual(st["section"], "B")

        # 5. Roll number change conflict
        with self.assertRaises(DuplicateRollNumberError):
            self.student_mgr.update_student(s1, "CS102", "Alice Conflict", "CSE", "B")

        # 6. Sorting and filtering
        all_students = self.student_mgr.get_all_students(search_query="Updated")
        self.assertEqual(len(all_students), 1)
        self.assertEqual(all_students[0]["roll_no"], "CS101")

        # 7. Delete student and cascade check
        self.att_mgr.save_batch_attendance("2026-10-12", [{"student_id": s2, "status": "Present"}])
        self.student_mgr.delete_student(s2)
        self.assertIsNone(self.student_mgr.get_student_by_id(s2))
        att_row = self.db.fetch_one("SELECT * FROM attendance WHERE student_id = ?;", (s2,))
        self.assertIsNone(att_row, "Attendance should be deleted on cascade")

    def test_bulk_import_csv_txt_and_duplicate_handling(self):
        """Test bulk importing from CSV and TXT with skip/update duplicate handling."""
        # Pre-seed CS-001
        self.student_mgr.add_student("CS-001", "Pre-existing Student", "CSE", "A")

        # CSV with 110 students + 1 duplicate of existing + 1 internal duplicate
        csv_file = self.temp_path / "students_import.csv"
        rows = ["Roll No,Student Name,Class,Section"]
        rows.append("CS-001,Updated Name,CSE,A")  # DB dupe
        rows.append("CS-002,John Doe,CSE,A")
        rows.append("CS-002,John Doe Dup,CSE,A")  # File dupe
        for i in range(3, 115):
            rows.append(f"CS-{i:03d},Student {i},CSE,B")
        csv_file.write_text("\n".join(rows), encoding="utf-8")

        load_res = self.importer.load_file(csv_file)
        self.assertTrue(load_res["success"])
        self.assertEqual(load_res["summary"]["duplicate_db_count"], 1)
        self.assertEqual(load_res["summary"]["duplicate_file_count"], 2)

        # Import with skip duplicates
        res_skip = self.importer.execute_import(duplicate_action="skip")
        self.assertTrue(res_skip["success"])
        self.assertEqual(res_skip["added"], 112)  # CS-003 to CS-114

        # Test TXT parsing (pipe format)
        txt_file = self.temp_path / "students.txt"
        txt_file.write_text(
            "Roll No: ME-001 | Name: Rohit Rao | Class: MECH | Section: A\n"
            "Roll No: ME-002 | Name: Sunita Sen | Class: MECH | Section: B\n",
            encoding="utf-8"
        )
        txt_res = self.importer.load_file(txt_file)
        self.assertTrue(txt_res["success"])
        self.assertEqual(len(txt_res["records"]), 2)
        import_txt_res = self.importer.execute_import(duplicate_action="skip")
        self.assertEqual(import_txt_res["added"], 2)

    def test_pdf_parsing_and_scanned_detection(self):
        """Test text PDF extraction and scanned PDF diagnosis."""
        pdf_file = self.templates_dir / "sample_students.pdf"
        if pdf_file.exists():
            parser = PDFParser()
            res = parser.parse_pdf(pdf_file)
            self.assertTrue(res.success)
            self.assertGreaterEqual(len(res.students), 10)
            self.assertEqual(res.students[0]["roll_no"], "101")

        scanned_file = self.templates_dir / "sample_scanned.pdf"
        if scanned_file.exists():
            parser = PDFParser()
            scan_res = parser.parse_pdf(scanned_file)
            self.assertFalse(scan_res.success)
            self.assertTrue(scan_res.is_scanned)
            self.assertIn("scanned document", scan_res.error_message.lower())

    def test_attendance_marking_and_formula(self):
        """Test attendance marking, historical update, stats, and percentage formula."""
        s1 = self.student_mgr.add_student("R1", "Student One", "IT", "A")
        s2 = self.student_mgr.add_student("R2", "Student Two", "IT", "A")
        s3 = self.student_mgr.add_student("R3", "Student Three", "IT", "A")

        # Save batch: 1 Present, 1 Absent, 1 Leave
        records = [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Absent"},
            {"student_id": s3, "status": "Leave"},
        ]
        saved = self.att_mgr.save_batch_attendance("2026-10-12", records)
        self.assertEqual(saved, 3)

        # Check stats and percentage formula
        stats = self.att_mgr.get_date_stats("2026-10-12")
        self.assertEqual(stats["present_count"], 1)
        self.assertEqual(stats["absent_count"], 1)
        self.assertEqual(stats["leave_count"], 1)
        # Denominator = 1 + 1 = 2 -> 50.0%
        self.assertEqual(stats["percentage"], 50.0)

        # Overwrite historical attendance
        self.att_mgr.save_batch_attendance("2026-10-12", [{"student_id": s2, "status": "Present"}], overwrite=True)
        sheet = self.att_mgr.get_attendance_sheet("2026-10-12", class_name="IT", section="A")
        s2_row = next(r for r in sheet if r["student_id"] == s2)
        self.assertEqual(s2_row["status"], "Present")

    def test_reports_defaulter_warnings_and_csv_export(self):
        """Test report calculations, <75% warning flag, and CSV export."""
        s1 = self.student_mgr.add_student("HIGH", "High Attender", "CE", "A")
        s2 = self.student_mgr.add_student("LOW", "Low Attender", "CE", "A")

        # High Attender: 4 Present, 0 Absent -> 100%
        # Low Attender: 1 Present, 3 Absent -> 25% (<75%)
        for d in ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]:
            self.att_mgr.save_batch_attendance(d, [{"student_id": s1, "status": "Present"}])

        self.att_mgr.save_batch_attendance("2026-10-01", [{"student_id": s2, "status": "Present"}])
        self.att_mgr.save_batch_attendance("2026-10-02", [{"student_id": s2, "status": "Absent"}])
        self.att_mgr.save_batch_attendance("2026-10-03", [{"student_id": s2, "status": "Absent"}])
        self.att_mgr.save_batch_attendance("2026-10-04", [{"student_id": s2, "status": "Absent"}])

        rep = self.reports_mgr.get_attendance_report()
        high_r = next(r for r in rep if r["roll_no"] == "HIGH")
        low_r = next(r for r in rep if r["roll_no"] == "LOW")

        self.assertEqual(high_r["percentage"], 100.0)
        self.assertFalse(high_r["is_low"])

        self.assertEqual(low_r["percentage"], 25.0)
        self.assertTrue(low_r["is_low"])

        # Defaulters only filter
        defaulters = self.reports_mgr.get_attendance_report(only_defaulters=True)
        self.assertEqual(len(defaulters), 1)
        self.assertEqual(defaulters[0]["roll_no"], "LOW")

        # CSV Export
        csv_out = self.temp_path / "exported.csv"
        exported = self.reports_mgr.export_report_to_csv(csv_out, rep)
        self.assertTrue(exported)
        self.assertTrue(csv_out.exists())

        with open(csv_out, encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 3)  # Header + 2 students

    def test_database_persistence_across_reconnect(self):
        """Test closing and reconnecting preserves all student and attendance data."""
        s = self.student_mgr.add_student("PERSIST", "Persist Student", "CSE", "A")
        self.att_mgr.save_batch_attendance("2026-10-12", [{"student_id": s, "status": "Present"}])

        # Fresh instance pointing to same file
        reconnected_db = Database(self.db_path)
        reconnected_sm = StudentManager(reconnected_db)
        reconnected_am = AttendanceManager(reconnected_db)

        student = reconnected_sm.get_student_by_roll_no("PERSIST")
        self.assertIsNotNone(student)
        self.assertEqual(student["name"], "Persist Student")

        stats = reconnected_am.get_date_stats("2026-10-12")
        self.assertEqual(stats["present_count"], 1)

    def test_ui_scaffold_initialization(self):
        """Test Tkinter GUI scaffold and views initialization without hanging mainloop."""
        root = tk.Tk()
        root.withdraw()  # Headless mode
        try:
            app = AttendanceApp(root)
            self.assertIsNotNone(app)
            self.assertIn("dashboard", app.views)
            self.assertIn("students", app.views)
            self.assertIn("import", app.views)
            self.assertIn("attendance", app.views)
            self.assertIn("reports", app.views)

            # Test view navigation
            app.show_view("students")
            self.assertEqual(app.active_view_name, "students")

            app.show_view("attendance")
            self.assertEqual(app.active_view_name, "attendance")

            app.show_view("reports")
            self.assertEqual(app.active_view_name, "reports")

            app.show_view("import")
            self.assertEqual(app.active_view_name, "import")

            app.show_view("dashboard")
            self.assertEqual(app.active_view_name, "dashboard")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
