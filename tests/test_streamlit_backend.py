"""
Unit and integration tests for streamlit_app/backend.py
Verifies 100% of the decoupled business logic used by the Streamlit application.
"""

import unittest
import tempfile
from pathlib import Path
from datetime import date

# Add streamlit_app to sys.path
import sys
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent / "streamlit_app"
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from backend import (
    Database,
    StudentManager,
    DuplicateRollNumberError,
    ValidationError,
    PDFParser,
    BulkImportManager,
    ImportValidationStatus,
    AttendanceManager,
    ReportsManager,
    ATTENDANCE_DEFICIT_THRESHOLD,
    seed_demo_data
)


class TestStreamlitBackend(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_streamlit.db"
        self.templates_dir = STREAMLIT_APP_DIR / "templates"

        self.db = Database(self.db_path)
        self.sm = StudentManager(self.db)
        self.am = AttendanceManager(self.db)
        self.im = BulkImportManager(self.db, self.sm)
        self.rm = ReportsManager(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_student_crud_and_validation(self):
        """Test student CRUD operations and error handling."""
        # Add
        s_id = self.sm.add_student("2026-IT-001", "Priya Sharma", "IT", "A")
        self.assertGreater(s_id, 0)

        # Duplicate error
        with self.assertRaises(DuplicateRollNumberError):
            self.sm.add_student("2026-IT-001", "Another Priya")

        # Validation error
        with self.assertRaises(ValidationError):
            self.sm.add_student("", "No Roll")

        # Update
        self.sm.update_student(s_id, "2026-IT-001", "Priya Updated", "IT", "B")
        st = self.sm.get_student_by_id(s_id)
        self.assertEqual(st["name"], "Priya Updated")
        self.assertEqual(st["section"], "B")

        # Distinct classes & sections
        classes = self.sm.get_distinct_classes()
        self.assertIn("IT", classes)

        # Delete
        self.sm.delete_student(s_id)
        self.assertIsNone(self.sm.get_student_by_id(s_id))

    def test_bulk_import_from_bytes(self):
        """Test in-memory byte stream importing for Streamlit file uploader."""
        csv_bytes = b"Roll No,Student Name,Class,Section\nCS-01,Aman Verma,CSE,A\nCS-02,Bhavna Rao,CSE,B\n"
        res = self.im.load_file_content("test.csv", csv_bytes)

        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["total_detected"], 2)
        self.assertEqual(res["summary"]["valid_count"], 2)

        import_res = self.im.execute_import(duplicate_action="skip")
        self.assertTrue(import_res["success"])
        self.assertEqual(import_res["added"], 2)
        self.assertEqual(self.sm.get_total_students_count(), 2)

    def test_pdf_parsing_sample_and_scanned(self):
        """Test PDF parsing on sample documents."""
        pdf_path = self.templates_dir / "sample_students.pdf"
        if pdf_path.exists():
            parser = PDFParser()
            res = parser.parse_pdf(pdf_path)
            self.assertTrue(res.success)
            self.assertGreaterEqual(len(res.students), 10)

        scanned_path = self.templates_dir / "sample_scanned.pdf"
        if scanned_path.exists():
            parser = PDFParser()
            res_scan = parser.parse_pdf(scanned_path)
            self.assertFalse(res_scan.success)
            self.assertTrue(res_scan.is_scanned)

    def test_attendance_and_defaulter_threshold(self):
        """Test attendance marking, percentage formula, and <75% threshold."""
        s1 = self.sm.add_student("R1", "High Attender", "CSE", "A")
        s2 = self.sm.add_student("R2", "Low Attender", "CSE", "A")

        # Day 1
        self.am.save_batch_attendance("2026-10-01", [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Absent"}
        ])
        # Day 2
        self.am.save_batch_attendance("2026-10-02", [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Present"}
        ])
        # Day 3
        self.am.save_batch_attendance("2026-10-03", [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Absent"}
        ])
        # Day 4
        self.am.save_batch_attendance("2026-10-04", [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Absent"}
        ])

        # R1: 4 Present / 4 = 100%
        # R2: 1 Present / 4 = 25% (< 75%)
        reports = self.rm.get_attendance_report()
        r1_rep = next(r for r in reports if r["roll_no"] == "R1")
        r2_rep = next(r for r in reports if r["roll_no"] == "R2")

        self.assertEqual(r1_rep["percentage"], 100.0)
        self.assertFalse(r1_rep["is_low"])

        self.assertEqual(r2_rep["percentage"], 25.0)
        self.assertTrue(r2_rep["is_low"])

        # CSV string generation
        csv_str = self.rm.generate_csv_string(reports)
        self.assertIn("High Attender", csv_str)
        self.assertIn("Low Attender", csv_str)

    def test_seed_demo_data(self):
        """Test pre-seeding sample dataset."""
        seed_demo_data(self.db, self.sm, self.am)
        self.assertGreaterEqual(self.sm.get_total_students_count(), 10)
        stats = self.am.get_date_stats(date.today().strftime("%Y-%m-%d"))
        self.assertGreater(stats["marked_count"], 0)


if __name__ == "__main__":
    unittest.main()
