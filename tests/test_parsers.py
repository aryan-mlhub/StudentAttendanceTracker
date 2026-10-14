"""
Tests for parsers: CSV, TXT, text-based PDF, and scanned PDF detection.
"""

import unittest
import tempfile
from pathlib import Path
from main import PDFParser, BulkImportManager, Database, StudentManager


class TestParsers(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db = Database(self.temp_path / "test.db")
        self.sm = StudentManager(self.db)
        self.importer = BulkImportManager(self.db, self.sm)
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_txt_pipe_format(self):
        """Test parsing TXT with key-value pipes: Roll No: 101 | Name: ..."""
        txt_file = self.templates_dir / "sample_students_pipe.txt"
        self.assertTrue(txt_file.exists(), f"File {txt_file} should exist")
        res = self.importer.load_file(txt_file)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["records"]), 10)
        self.assertEqual(res["records"][0]["roll_no"], "101")
        self.assertEqual(res["records"][0]["name"], "Rahul Sharma")
        self.assertEqual(res["records"][0]["class_name"], "CSE")
        self.assertEqual(res["records"][0]["section"], "A")

    def test_parse_txt_delimited_format(self):
        """Test parsing TXT with comma delimiters: 101, Rahul Sharma, CSE, A"""
        txt_file = self.templates_dir / "sample_students_comma.txt"
        self.assertTrue(txt_file.exists(), f"File {txt_file} should exist")
        res = self.importer.load_file(txt_file)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["records"]), 10)
        self.assertEqual(res["records"][0]["roll_no"], "101")
        self.assertEqual(res["records"][0]["name"], "Rahul Sharma")

    def test_parse_csv_with_header_aliases(self):
        """Test CSV parsing with custom variations of headers."""
        custom_csv = self.temp_path / "custom_students.csv"
        custom_csv.write_text(
            "Registration Number,Candidate Name,Branch,Division\n"
            "CS201,Ankit Saxena,CSE,B\n"
            "CS202,Bhavna Rao,ECE,A\n",
            encoding="utf-8"
        )
        res = self.importer.load_file(custom_csv)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["records"]), 2)
        self.assertEqual(res["records"][0]["roll_no"], "CS201")
        self.assertEqual(res["records"][0]["name"], "Ankit Saxena")
        self.assertEqual(res["records"][0]["class_name"], "CSE")
        self.assertEqual(res["records"][0]["section"], "B")

    def test_parse_text_pdf(self):
        """Test parsing structured records from a text-based PDF."""
        pdf_file = self.templates_dir / "sample_students.pdf"
        self.assertTrue(pdf_file.exists(), f"File {pdf_file} should exist")
        res = self.importer.load_file(pdf_file)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(len(res["records"]), 10)
        first = res["records"][0]
        self.assertEqual(first["roll_no"], "101")
        self.assertEqual(first["name"], "Rahul Sharma")
        self.assertEqual(first["class_name"], "CSE")
        self.assertEqual(first["section"], "A")

    def test_detect_scanned_pdf_and_ocr_explanation(self):
        """Test that textless/scanned PDFs are detected and an informative OCR message is given."""
        scanned_file = self.templates_dir / "sample_scanned.pdf"
        self.assertTrue(scanned_file.exists(), f"File {scanned_file} should exist")
        parser = PDFParser()
        result = parser.parse_pdf(scanned_file)
        self.assertFalse(result.success)
        self.assertTrue(result.is_scanned)
        self.assertIn("scanned document", result.error_message.lower())
        self.assertIn("ocr", result.error_message.lower())


if __name__ == "__main__":
    unittest.main()
