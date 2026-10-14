"""
Tests for reports.py:
- Attendance percentage reporting
- Defaulter warning (<75% attendance)
- Date range filtering
- Export reports to CSV
"""

import unittest
import tempfile
import csv
from pathlib import Path
from main import Database, StudentManager, AttendanceManager, ReportsManager


class TestReports(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db = Database(self.temp_path / "test_reports.db")
        self.sm = StudentManager(self.db)
        self.am = AttendanceManager(self.db)
        self.rm = ReportsManager(self.db)

        # Student A (Good Attendance): 4 Present, 0 Absent -> 100%
        self.sa = self.sm.add_student("101", "Student High", "CSE", "A")
        # Student B (Low Attendance): 1 Present, 3 Absent -> 25% (<75%)
        self.sb = self.sm.add_student("102", "Student Low", "CSE", "A")
        # Student C (Borderline Attendance): 3 Present, 1 Absent -> 75%
        self.sc = self.sm.add_student("103", "Student Mid", "CSE", "A")

        dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
        for d in dates:
            self.am.save_batch_attendance(d, [{"student_id": self.sa, "status": "Present"}])

        self.am.save_batch_attendance("2026-10-01", [{"student_id": self.sb, "status": "Present"}])
        self.am.save_batch_attendance("2026-10-02", [{"student_id": self.sb, "status": "Absent"}])
        self.am.save_batch_attendance("2026-10-03", [{"student_id": self.sb, "status": "Absent"}])
        self.am.save_batch_attendance("2026-10-04", [{"student_id": self.sb, "status": "Absent"}])

        self.am.save_batch_attendance("2026-10-01", [{"student_id": self.sc, "status": "Present"}])
        self.am.save_batch_attendance("2026-10-02", [{"student_id": self.sc, "status": "Present"}])
        self.am.save_batch_attendance("2026-10-03", [{"student_id": self.sc, "status": "Present"}])
        self.am.save_batch_attendance("2026-10-04", [{"student_id": self.sc, "status": "Absent"}])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_attendance_report_calculations_and_low_threshold(self):
        """Test calculation of attendance percentages and <75% warning flag."""
        reports = self.rm.get_attendance_report()
        self.assertEqual(len(reports), 3)

        rep_a = next(r for r in reports if r["roll_no"] == "101")
        self.assertEqual(rep_a["percentage"], 100.0)
        self.assertFalse(rep_a["is_low"])

        rep_b = next(r for r in reports if r["roll_no"] == "102")
        self.assertEqual(rep_b["percentage"], 25.0)
        self.assertTrue(rep_b["is_low"], "Student with 25% should be flagged as below 75%")

        rep_c = next(r for r in reports if r["roll_no"] == "103")
        self.assertEqual(rep_c["percentage"], 75.0)
        self.assertFalse(rep_c["is_low"], "Student with exactly 75% is not below 75%")

    def test_filter_only_defaulters(self):
        """Test filtering report to only include students with attendance < 75%."""
        defaulters = self.rm.get_attendance_report(only_defaulters=True)
        self.assertEqual(len(defaulters), 1)
        self.assertEqual(defaulters[0]["roll_no"], "102")

    def test_date_range_filter(self):
        """Test filtering by date range."""
        # Query only first 2 days for Student B: 1 Present, 1 Absent -> 50%
        reports = self.rm.get_attendance_report(start_date="2026-10-01", end_date="2026-10-02")
        rep_b = next(r for r in reports if r["roll_no"] == "102")
        self.assertEqual(rep_b["total_days"], 2)
        self.assertEqual(rep_b["percentage"], 50.0)

    def test_export_report_to_csv(self):
        """Test exporting report data to a valid CSV file."""
        export_path = self.temp_path / "exported_report.csv"
        reports = self.rm.get_attendance_report()
        success = self.rm.export_report_to_csv(export_path, reports)
        self.assertTrue(success)
        self.assertTrue(export_path.exists())

        # Verify CSV content
        with open(export_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 4)  # Header + 3 students
            headers = reader[0]
            self.assertIn("Roll Number", headers)
            self.assertIn("Attendance %", headers)
            self.assertIn("Attendance Status", headers)


if __name__ == "__main__":
    unittest.main()
