"""
Tests for database.py: schema initialization, foreign keys, transactions, and rollback.
"""

import unittest
import tempfile
import os
from pathlib import Path
from main import Database


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_creation(self):
        """Test tables are created upon initialization."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("students", tables)
        self.assertIn("attendance", tables)

    def test_transaction_rollback_on_error(self):
        """Test that a transaction rollback occurs when an exception is raised."""
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO students (roll_no, name) VALUES ('R1', 'Student One');")
                # Intentionally trigger an error
                raise RuntimeError("Forced simulation error")
        except RuntimeError:
            pass

        # Verify record was NOT saved
        student = self.db.fetch_one("SELECT * FROM students WHERE roll_no = 'R1';")
        self.assertIsNone(student, "Record should have been rolled back upon exception.")

    def test_unique_roll_number_constraint(self):
        """Test that duplicate roll numbers violate SQLite unique constraint."""
        self.db.execute_query("INSERT INTO students (roll_no, name) VALUES ('R101', 'Alice');")
        with self.assertRaises(Exception):
            self.db.execute_query("INSERT INTO students (roll_no, name) VALUES ('R101', 'Bob');")

    def test_foreign_key_cascade(self):
        """Test that deleting a student cascades and deletes their attendance records."""
        student_id = self.db.execute_query("INSERT INTO students (roll_no, name) VALUES ('R200', 'Charlie');")
        self.db.execute_query(
            "INSERT INTO attendance (student_id, attendance_date, status) VALUES (?, '2026-10-12', 'Present');",
            (student_id,)
        )

        att = self.db.fetch_one("SELECT * FROM attendance WHERE student_id = ?;", (student_id,))
        self.assertIsNotNone(att)

        # Delete student
        self.db.execute_query("DELETE FROM students WHERE id = ?;", (student_id,))

        att_after = self.db.fetch_one("SELECT * FROM attendance WHERE student_id = ?;", (student_id,))
        self.assertIsNone(att_after, "Attendance record should have been cascade deleted.")


if __name__ == "__main__":
    unittest.main()
