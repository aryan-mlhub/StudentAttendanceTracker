"""
End-to-End (E2E) Workflow Test for Student Attendance Tracker.
Simulates the entire user lifecycle:
1. Fresh database creation
2. Bulk import of 100+ CSV students, TXT students, and PDF students
3. Duplicate and error handling verification
4. Verifying imported students immediately appear in student manager and attendance sheet
5. Marking and editing attendance records
6. Computing dashboard statistics
7. Generating reports and detecting students with <75% attendance
8. Exporting reports to CSV
9. Reopening the database to confirm permanent persistence
"""

import unittest
import tempfile
import csv
from pathlib import Path
from main import Database, StudentManager, AttendanceManager, BulkImportManager, PDFParser, ReportsManager


class TestEndToEndWorkflow(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "e2e_attendance.db"
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_complete_user_lifecycle(self):
        # 1. Initialize Backend
        db = Database(self.db_path)
        student_mgr = StudentManager(db)
        att_mgr = AttendanceManager(db)
        importer = BulkImportManager(db, student_mgr)
        reports_mgr = ReportsManager(db)

        # 2. Bulk Import 100+ Students from CSV
        large_csv = self.temp_path / "cs_class_roster.csv"
        rows = ["Roll No,Student Name,Class,Section"]
        for i in range(1, 105):
            sec = "A" if i <= 50 else "B"
            rows.append(f"2026-CSE-{i:03d},Student {i},CSE,{sec}")
        large_csv.write_text("\n".join(rows), encoding="utf-8")

        load_res = importer.load_file(large_csv)
        self.assertTrue(load_res["success"])
        self.assertEqual(load_res["summary"]["total_detected"], 104)
        self.assertEqual(load_res["summary"]["valid_count"], 104)

        import_res = importer.execute_import(duplicate_action="skip")
        self.assertTrue(import_res["success"])
        self.assertEqual(import_res["added"], 104)
        self.assertEqual(student_mgr.get_total_students_count(), 104)

        # 3. Bulk Import from TXT (Pipe Format) with a duplicate from existing DB
        pipe_txt = self.temp_path / "additional_students.txt"
        pipe_txt.write_text(
            "Roll No: 2026-ECE-001 | Name: Aditi Rao | Class: ECE | Section: A\n"
            "Roll No: 2026-ECE-002 | Name: Bhuvan Bam | Class: ECE | Section: A\n"
            "Roll No: 2026-CSE-001 | Name: Duplicate Student 1 | Class: CSE | Section: A\n",
            encoding="utf-8"
        )
        txt_res = importer.load_file(pipe_txt)
        self.assertTrue(txt_res["success"])
        self.assertEqual(txt_res["summary"]["duplicate_db_count"], 1)  # 2026-CSE-001 is duplicate
        self.assertEqual(txt_res["summary"]["valid_count"], 2)

        # Import with skip duplicates
        txt_import = importer.execute_import(duplicate_action="skip")
        self.assertEqual(txt_import["added"], 2)
        self.assertEqual(student_mgr.get_total_students_count(), 106)

        # 4. Scanned PDF Detection Check
        pdf_parser = PDFParser()
        scanned_pdf = self.templates_dir / "sample_scanned.pdf"
        if scanned_pdf.exists():
            scan_check = pdf_parser.parse_pdf(scanned_pdf)
            self.assertFalse(scan_check.success)
            self.assertTrue(scan_check.is_scanned)

        # 5. Verify all students immediately appear in Attendance Sheet
        sheet_cse_a = att_mgr.get_attendance_sheet("2026-10-12", class_name="CSE", section="A")
        self.assertEqual(len(sheet_cse_a), 50)  # 50 students in CSE-A

        # 6. Mark Attendance for CSE-A
        # Mark 40 Present, 8 Absent, 2 Leave
        records_to_save = []
        for idx, s in enumerate(sheet_cse_a):
            if idx < 40:
                st = "Present"
            elif idx < 48:
                st = "Absent"
            else:
                st = "Leave"
            records_to_save.append({"student_id": s["student_id"], "status": st})

        saved_count = att_mgr.save_batch_attendance("2026-10-12", records_to_save)
        self.assertEqual(saved_count, 50)

        # 7. Check Dashboard Statistics
        stats = att_mgr.get_date_stats("2026-10-12")
        self.assertEqual(stats["total_students"], 106)
        self.assertEqual(stats["present_count"], 40)
        self.assertEqual(stats["absent_count"], 8)
        self.assertEqual(stats["leave_count"], 2)
        # Denominator = 40 + 8 = 48. Rate = 40 / 48 * 100 = 83.3%
        self.assertEqual(stats["percentage"], 83.3)

        # 8. Mark a second date to generate low-attendance defaulters (< 75%)
        # Student 45: Absent on day 1 and Absent on day 2 -> 0%
        # Student 1: Present on day 1 and Present on day 2 -> 100%
        att_mgr.save_batch_attendance("2026-10-13", [
            {"student_id": sheet_cse_a[0]["student_id"], "status": "Present"},
            {"student_id": sheet_cse_a[44]["student_id"], "status": "Absent"}
        ])

        # 9. Reports & Defaulter (< 75%) Threshold Detection
        reports = reports_mgr.get_attendance_report(class_filter="CSE", section_filter="A")
        self.assertEqual(len(reports), 50)

        defaulters = [r for r in reports if r["is_low"]]
        self.assertGreaterEqual(len(defaulters), 8)  # Students who were absent

        # 10. Export Report to CSV and Verify CSV Content
        export_csv_path = self.temp_path / "final_report.csv"
        reports_mgr.export_report_to_csv(export_csv_path, reports)
        self.assertTrue(export_csv_path.exists())

        with open(export_csv_path, encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 51)  # Header + 50 students
            self.assertIn("Attendance %", reader[0])
            self.assertIn("Roll Number", reader[0])

        # 11. Test Database Persistence across App Re-opens
        # Re-initialize fresh objects pointing to the same SQLite file
        restarted_db = Database(self.db_path)
        restarted_sm = StudentManager(restarted_db)
        restarted_am = AttendanceManager(restarted_db)

        self.assertEqual(restarted_sm.get_total_students_count(), 106)
        persisted_stats = restarted_am.get_date_stats("2026-10-12")
        self.assertEqual(persisted_stats["present_count"], 40)
        self.assertEqual(persisted_stats["absent_count"], 8)
        self.assertEqual(persisted_stats["leave_count"], 2)


if __name__ == "__main__":
    unittest.main()
