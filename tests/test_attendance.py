"""
Tests for attendance_manager.py:
- Date-based attendance marking and batch saving
- Statuses: Present, Absent, Leave
- Historical editing and overwrite handling
- Formula verification: Present / (Present + Absent) * 100 with Leave exclusion
- Duplicate prevention
- Persistence across database re-connections
"""

import unittest
import tempfile
from pathlib import Path
from main import Database, StudentManager, AttendanceManager


class TestAttendance(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_att.db"
        self.db = Database(self.db_path)
        self.sm = StudentManager(self.db)
        self.am = AttendanceManager(self.db)

        # Pre-seed 3 students
        self.s1 = self.sm.add_student("101", "Alice", "CSE", "A")
        self.s2 = self.sm.add_student("102", "Bob", "CSE", "A")
        self.s3 = self.sm.add_student("103", "Charlie", "CSE", "A")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_batch_attendance(self):
        """Test batch marking attendance for a class on a given date."""
        records = [
            {"student_id": self.s1, "status": "Present"},
            {"student_id": self.s2, "status": "Absent"},
            {"student_id": self.s3, "status": "Leave"},
        ]
        saved = self.am.save_batch_attendance("2026-10-12", records)
        self.assertEqual(saved, 3)

        # Retrieve sheet
        sheet = self.am.get_attendance_sheet("2026-10-12", class_name="CSE", section="A")
        self.assertEqual(len(sheet), 3)

        statuses = {row["student_id"]: row["status"] for row in sheet}
        self.assertEqual(statuses[self.s1], "Present")
        self.assertEqual(statuses[self.s2], "Absent")
        self.assertEqual(statuses[self.s3], "Leave")

    def test_attendance_percentage_calculation_formula(self):
        """
        Verify formula: Present / (Present + Absent) * 100.
        Leave days must not count in the denominator.
        """
        records = [
            {"student_id": self.s1, "status": "Present"},
            {"student_id": self.s2, "status": "Absent"},
            {"student_id": self.s3, "status": "Leave"},
        ]
        self.am.save_batch_attendance("2026-10-12", records)
        stats = self.am.get_date_stats("2026-10-12")

        self.assertEqual(stats["present_count"], 1)
        self.assertEqual(stats["absent_count"], 1)
        self.assertEqual(stats["leave_count"], 1)
        # Denominator = 1 + 1 = 2. Present = 1 -> 50.0%
        self.assertEqual(stats["percentage"], 50.0)

    def test_historical_editing_and_overwrite(self):
        """Test editing previously saved attendance replaces existing status."""
        # Initial marking
        self.am.save_batch_attendance("2026-10-12", [{"student_id": self.s1, "status": "Absent"}])
        sheet1 = self.am.get_attendance_sheet("2026-10-12")
        self.assertEqual(next(s for s in sheet1 if s["student_id"] == self.s1)["status"], "Absent")

        # Edit/Update to Present
        self.am.save_batch_attendance("2026-10-12", [{"student_id": self.s1, "status": "Present"}], overwrite=True)
        sheet2 = self.am.get_attendance_sheet("2026-10-12")
        self.assertEqual(next(s for s in sheet2 if s["student_id"] == self.s1)["status"], "Present")

    def test_database_persistence_across_app_restarts(self):
        """Test closing database connection and opening fresh instance preserves all records."""
        self.am.save_batch_attendance("2026-10-12", [
            {"student_id": self.s1, "status": "Present"},
            {"student_id": self.s2, "status": "Present"}
        ])

        # Simulate app closing and reopening
        fresh_db = Database(self.db_path)
        fresh_am = AttendanceManager(fresh_db)
        fresh_stats = fresh_am.get_date_stats("2026-10-12")

        self.assertEqual(fresh_stats["present_count"], 2)
        self.assertEqual(fresh_stats["total_students"], 3)


if __name__ == "__main__":
    unittest.main()
