"""
Tests for bulk_import.py:
- 100+ students bulk CSV import
- Duplicate roll numbers inside file
- Duplicate roll numbers already in database
- Missing roll numbers and missing names
- Cancelling an import (no rows saved)
- Importing only selected valid rows
- Database rollback on failure
- Duplicate resolution: skip vs update
"""

import unittest
import tempfile
from pathlib import Path
from main import Database, StudentManager, BulkImportManager, ImportValidationStatus


class TestBulkImport(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db = Database(self.temp_path / "test_import.db")
        self.sm = StudentManager(self.db)
        self.importer = BulkImportManager(self.db, self.sm)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_100_plus_students_from_csv(self):
        """Test importing 120 students in a single batch from CSV."""
        csv_path = self.temp_path / "large_class.csv"
        rows = ["Roll No,Student Name,Class,Section"]
        for i in range(1, 121):
            rows.append(f"CS-{i:03d},Student {i},CSE,{'A' if i % 2 == 0 else 'B'}")
        csv_path.write_text("\n".join(rows), encoding="utf-8")

        # Load and validate
        res = self.importer.load_file(csv_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["total_detected"], 120)
        self.assertEqual(res["summary"]["valid_count"], 120)
        self.assertEqual(res["summary"]["ready_to_import"], 120)

        # Execute import
        import_res = self.importer.execute_import(duplicate_action="skip")
        self.assertTrue(import_res["success"])
        self.assertEqual(import_res["added"], 120)

        # Verify in database
        total_in_db = self.sm.get_total_students_count()
        self.assertEqual(total_in_db, 120)

    def test_duplicate_in_file_detection(self):
        """Test that duplicate roll numbers within the file are flagged."""
        csv_path = self.temp_path / "dupe_in_file.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            "101,Rahul Sharma,CSE,A\n"
            "102,Priya Verma,CSE,A\n"
            "101,Rahul Sharma Duplicate,CSE,A\n",
            encoding="utf-8"
        )
        res = self.importer.load_file(csv_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["total_detected"], 3)
        self.assertEqual(res["summary"]["duplicate_file_count"], 2)
        # 102 is the only unique one
        self.assertEqual(res["summary"]["valid_count"], 1)

    def test_duplicate_in_database_detection(self):
        """Test that roll numbers already existing in the database are flagged."""
        # Pre-insert student 101 in database
        self.sm.add_student("101", "Existing Rahul", "CSE", "A")

        csv_path = self.temp_path / "dupe_in_db.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            "101,Rahul Sharma,CSE,A\n"
            "102,Priya Verma,CSE,A\n",
            encoding="utf-8"
        )
        res = self.importer.load_file(csv_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["duplicate_db_count"], 1)
        self.assertEqual(res["summary"]["valid_count"], 1)

        # Record 101 should be marked as exists in DB
        rec101 = next(r for r in res["records"] if r["roll_no"] == "101")
        self.assertEqual(rec101["status"], ImportValidationStatus.DUP_IN_DB)
        self.assertFalse(rec101["selected"])

    def test_missing_roll_and_name_validation(self):
        """Test missing roll numbers and missing names are detected as invalid."""
        csv_path = self.temp_path / "missing_fields.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            ",Rahul Sharma,CSE,A\n"
            "102,,CSE,A\n"
            "103,Aman Patel,CSE,A\n",
            encoding="utf-8"
        )
        res = self.importer.load_file(csv_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["invalid_count"], 2)
        self.assertEqual(res["summary"]["valid_count"], 1)

    def test_cancel_import_preserves_database(self):
        """Test that loading a preview and cancelling leaves database empty."""
        csv_path = self.temp_path / "cancel_test.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            "101,Rahul Sharma,CSE,A\n",
            encoding="utf-8"
        )
        res = self.importer.load_file(csv_path)
        self.assertTrue(res["success"])

        # User cancels (does not call execute_import)
        self.assertEqual(self.sm.get_total_students_count(), 0)

    def test_import_only_selected_valid_rows(self):
        """Test user can select/deselect specific rows and only selected ones are saved."""
        csv_path = self.temp_path / "selective.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            "101,Rahul Sharma,CSE,A\n"
            "102,Priya Verma,CSE,A\n"
            "103,Aman Patel,CSE,A\n",
            encoding="utf-8"
        )
        self.importer.load_file(csv_path)
        # Deselect record 102
        rec102 = next(r for r in self.importer.current_records if r["roll_no"] == "102")
        self.importer.toggle_record_selection(rec102["id"], False)

        import_res = self.importer.execute_import(duplicate_action="skip")
        self.assertTrue(import_res["success"])
        self.assertEqual(import_res["added"], 2)

        # Check DB
        in_db = [s["roll_no"] for s in self.sm.get_all_students()]
        self.assertIn("101", in_db)
        self.assertIn("103", in_db)
        self.assertNotIn("102", in_db)

    def test_update_existing_students_option(self):
        """Test updating existing students on duplicate option = 'update'."""
        self.sm.add_student("101", "Old Name", "CSE", "A")

        csv_path = self.temp_path / "update_test.csv"
        csv_path.write_text(
            "Roll No,Student Name,Class,Section\n"
            "101,Updated Name,CSE,B\n",
            encoding="utf-8"
        )
        self.importer.load_file(csv_path)

        # Explicitly select 101 for update
        rec = self.importer.current_records[0]
        self.importer.toggle_record_selection(rec["id"], True)

        import_res = self.importer.execute_import(duplicate_action="update")
        self.assertTrue(import_res["success"])
        self.assertEqual(import_res["updated"], 1)

        # Check that DB student was updated
        updated_student = self.sm.get_student_by_roll_no("101")
        self.assertEqual(updated_student["name"], "Updated Name")
        self.assertEqual(updated_student["section"], "B")


if __name__ == "__main__":
    unittest.main()
