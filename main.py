"""
Student Attendance Tracker - All-in-One Consolidated Application
Single-file self-contained desktop application for student management,
attendance tracking, bulk file importing (CSV, TXT, PDF, Excel),
analytics reporting, and CSV data export.

Consolidated into a single file while preserving 100% of all features,
business logic, database operations, and UI/UX styling.
"""

# =====================================================================
# SECTION 1: IMPORTS AND CONFIGURATION
# =====================================================================

import sys
import os
import csv
import re
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, List, Tuple, Optional, Dict, Set, Callable
from contextlib import contextmanager

# GUI Framework Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Third-party document parsing dependencies
import pypdf

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# Base Paths and Environment
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = PROJECT_ROOT / "attendance_tracker.db"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Business Logic Thresholds and Rules
ATTENDANCE_DEFICIT_THRESHOLD = 75.0
VALID_STATUSES = {"Present", "Absent", "Leave"}

# Canonical Column Identifiers for Import
COL_ROLL = "roll_no"
COL_NAME = "name"
COL_CLASS = "class_name"
COL_SECTION = "section"

# Common Header Synonyms for Intelligent Auto-Mapping
HEADER_ALIASES = {
    COL_ROLL: [
        "roll no", "roll_no", "roll number", "rollno", "roll",
        "student roll no", "student id", "id", "reg no", "reg_no",
        "registration number", "admission no", "enrollment no", "usn"
    ],
    COL_NAME: [
        "student name", "name", "student_name", "full name", "fullname",
        "candidate name", "first name", "student"
    ],
    COL_CLASS: [
        "class", "class_name", "class name", "grade", "standard",
        "course", "branch", "department", "stream", "dept", "program"
    ],
    COL_SECTION: [
        "section", "sec", "division", "div", "batch", "group", "class section"
    ]
}


# =====================================================================
# SECTION 2: DATABASE MANAGEMENT
# =====================================================================

class Database:
    """Manages SQLite database connections, schema creation, and transactions."""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Create a connection with foreign keys enabled and row factory configured."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self):
        """Context manager for atomic transactional operations. Auto-commits or rolls back."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self.transaction() as conn:
            cursor = conn.cursor()

            # Students Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    roll_no TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL,
                    class_name TEXT DEFAULT '',
                    section TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
            """)

            # Attendance Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    attendance_date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Leave')),
                    UNIQUE(student_id, attendance_date),
                    FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
                );
            """)

            # Performance Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_students_roll_no ON students(roll_no);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_students_class_sec ON students(class_name, section);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(attendance_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);")

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return the lastrowid or affected rows."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.lastrowid

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return all rows as dictionaries."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        """Execute a SELECT query and return a single row as a dictionary."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def close(self):
        """Placeholder for interface consistency."""
        pass


# =====================================================================
# SECTION 3: STUDENT MANAGEMENT
# =====================================================================

class DuplicateRollNumberError(Exception):
    """Raised when attempting to add/update a student with a roll number that already exists."""
    pass


class ValidationError(Exception):
    """Raised when required fields are missing or invalid."""
    pass


class StudentManager:
    """Handles all student CRUD operations, searching, filtering, and validation."""

    def __init__(self, db: Database):
        self.db = db

    def validate_student_data(self, roll_no: str, name: str) -> None:
        """Validate required fields."""
        if not roll_no or not str(roll_no).strip():
            raise ValidationError("Roll number is required and cannot be empty.")
        if not name or not str(name).strip():
            raise ValidationError("Student name is required and cannot be empty.")

    def add_student(self, roll_no: str, name: str, class_name: str = "", section: str = "") -> int:
        """Add a single student. Raises DuplicateRollNumberError if roll_no exists."""
        roll_no = str(roll_no).strip()
        name = str(name).strip()
        class_name = str(class_name).strip()
        section = str(section).strip().upper()

        self.validate_student_data(roll_no, name)

        # Check existing
        existing = self.get_student_by_roll_no(roll_no)
        if existing:
            raise DuplicateRollNumberError(f"A student with Roll Number '{roll_no}' already exists.")

        query = """
            INSERT INTO students (roll_no, name, class_name, section)
            VALUES (?, ?, ?, ?);
        """
        return self.db.execute_query(query, (roll_no, name, class_name, section))

    def update_student(self, student_id: int, roll_no: str, name: str, class_name: str = "", section: str = "") -> None:
        """Update existing student details."""
        roll_no = str(roll_no).strip()
        name = str(name).strip()
        class_name = str(class_name).strip()
        section = str(section).strip().upper()

        self.validate_student_data(roll_no, name)

        # Check if roll_no is being changed to another student's roll_no
        existing = self.get_student_by_roll_no(roll_no)
        if existing and existing["id"] != student_id:
            raise DuplicateRollNumberError(f"Roll Number '{roll_no}' is already used by another student ({existing['name']}).")

        query = """
            UPDATE students
            SET roll_no = ?, name = ?, class_name = ?, section = ?
            WHERE id = ?;
        """
        self.db.execute_query(query, (roll_no, name, class_name, section, student_id))

    def delete_student(self, student_id: int) -> bool:
        """Delete a student and their attendance records via cascade."""
        query = "DELETE FROM students WHERE id = ?;"
        self.db.execute_query(query, (student_id,))
        return True

    def get_student_by_id(self, student_id: int) -> Optional[Dict[str, Any]]:
        """Fetch student record by primary key id."""
        query = "SELECT * FROM students WHERE id = ?;"
        return self.db.fetch_one(query, (student_id,))

    def get_student_by_roll_no(self, roll_no: str) -> Optional[Dict[str, Any]]:
        """Fetch student record by roll number (case-insensitive)."""
        query = "SELECT * FROM students WHERE roll_no = ? COLLATE NOCASE;"
        return self.db.fetch_one(query, (str(roll_no).strip(),))

    def get_all_students(
        self,
        search_query: str = "",
        class_filter: str = "",
        section_filter: str = "",
        sort_by: str = "roll_no",
        sort_order: str = "ASC"
    ) -> List[Dict[str, Any]]:
        """
        Retrieve students with search, class/section filtering, and dynamic column sorting.
        """
        valid_sort_columns = {
            "id": "id",
            "roll_no": "roll_no",
            "name": "name",
            "class_name": "class_name",
            "section": "section",
            "created_at": "created_at"
        }
        order_col = valid_sort_columns.get(sort_by, "roll_no")
        order_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

        conditions = []
        params = []

        if search_query:
            q = f"%{search_query.strip()}%"
            conditions.append("(roll_no LIKE ? OR name LIKE ?)")
            params.extend([q, q])

        if class_filter and class_filter != "All":
            conditions.append("class_name = ?")
            params.append(class_filter)

        if section_filter and section_filter != "All":
            conditions.append("section = ?")
            params.append(section_filter)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM students
            {where_clause}
            ORDER BY {order_col} COLLATE NOCASE {order_dir};
        """
        return self.db.fetch_all(query, tuple(params))

    def get_total_students_count(self) -> int:
        """Return total number of registered students."""
        res = self.db.fetch_one("SELECT COUNT(*) as count FROM students;")
        return res["count"] if res else 0

    def get_existing_roll_numbers(self) -> Set[str]:
        """Fetch set of all existing roll numbers (uppercase/clean) for fast bulk validation."""
        rows = self.db.fetch_all("SELECT roll_no FROM students;")
        return {r["roll_no"].strip().upper() for r in rows if r["roll_no"]}

    def get_existing_students_map(self) -> Dict[str, Dict[str, Any]]:
        """Fetch dictionary mapping uppercase roll_no -> student dict."""
        rows = self.db.fetch_all("SELECT * FROM students;")
        return {r["roll_no"].strip().upper(): r for r in rows if r["roll_no"]}

    def get_distinct_classes(self) -> List[str]:
        """Get unique class names sorted."""
        rows = self.db.fetch_all("SELECT DISTINCT class_name FROM students WHERE class_name != '' ORDER BY class_name ASC;")
        return [r["class_name"] for r in rows]

    def get_distinct_sections(self, class_name: Optional[str] = None) -> List[str]:
        """Get unique section names sorted, optionally filtered by class."""
        if class_name and class_name != "All":
            query = "SELECT DISTINCT section FROM students WHERE section != '' AND class_name = ? ORDER BY section ASC;"
            rows = self.db.fetch_all(query, (class_name,))
        else:
            query = "SELECT DISTINCT section FROM students WHERE section != '' ORDER BY section ASC;"
            rows = self.db.fetch_all(query)
        return [r["section"] for r in rows]


# =====================================================================
# SECTION 4: BULK IMPORT AND FILE PARSING
# =====================================================================

class ImportValidationStatus:
    VALID = "Valid"
    DUP_IN_FILE = "Duplicate in File"
    DUP_IN_DB = "Exists in Database"
    MISSING_ROLL = "Missing Roll No"
    MISSING_NAME = "Missing Name"
    INVALID = "Invalid Row"


class PDFParseResult:
    """Encapsulates the result of parsing a PDF file."""

    def __init__(self):
        self.success: bool = True
        self.is_scanned: bool = False
        self.page_count: int = 0
        self.raw_text: str = ""
        self.students: List[Dict[str, str]] = []
        self.unparsed_lines: List[Dict[str, Any]] = []
        self.error_message: Optional[str] = None
        self.ocr_available: bool = False


class PDFParser:
    """Extracts and parses student records from text-based PDF documents."""

    def __init__(self):
        # Check if tesseract binary is in system PATH
        self.has_tesseract = shutil.which("tesseract") is not None

    def parse_pdf(self, file_path: str | Path) -> PDFParseResult:
        """
        Main entry point to parse a PDF file into student records.
        Returns a PDFParseResult with extracted students, raw text, and diagnosis.
        """
        path = Path(file_path)
        result = PDFParseResult()
        result.ocr_available = self.has_tesseract

        if not path.exists():
            result.success = False
            result.error_message = f"File not found: {path}"
            return result

        try:
            reader = pypdf.PdfReader(str(path))
            result.page_count = len(reader.pages)

            if result.page_count == 0:
                result.success = False
                result.error_message = "The selected PDF file contains 0 pages."
                return result

            all_extracted_text: List[str] = []

            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                all_extracted_text.append(page_text)

            combined_text = "\n".join(all_extracted_text)
            result.raw_text = combined_text

            # Check if PDF is image-only / scanned
            cleaned_text = re.sub(r"\s+", "", combined_text)
            if len(cleaned_text) < 15:
                # Virtually no selectable text found
                result.is_scanned = True
                result.success = False
                msg = (
                    "This PDF appears to be a scanned document or contains images rather than selectable text. "
                    "pypdf could not extract any readable text characters.\n\n"
                    "• Cause: Scanned document / image-only PDF.\n"
                    "• Resolution: Please use an exported text-based PDF, CSV, or TXT file."
                )
                if self.has_tesseract:
                    msg += "\n• Note: Tesseract OCR is detected on your system, but automated OCR for image-only scans requires high-contrast scans."
                else:
                    msg += "\n• Note: Tesseract OCR is not installed. To parse scanned images, install Tesseract OCR or convert your document to CSV."
                result.error_message = msg
                return result

            # Parse the extracted text into structured student records
            students, unparsed = self._extract_student_records(combined_text)
            result.students = students
            result.unparsed_lines = unparsed

            if not students and unparsed:
                result.success = False
                result.error_message = (
                    "Readable text was found in the PDF, but no records matching student patterns "
                    "(Roll Number and Name) could be recognized.\n"
                    "Please check the extracted text preview and verify the PDF layout."
                )

            return result

        except Exception as e:
            result.success = False
            result.error_message = f"Error reading PDF file: {str(e)}"
            return result

    def _extract_student_records(self, text: str) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """
        Parses text lines into student dicts.
        Handles key-value format (Roll No: ..., Name: ...) and tabular format (101  Rahul Sharma  CSE  A).
        """
        students: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        lines = text.splitlines()

        # Regexes for noise lines (page numbers, headers, footers, report titles)
        header_patterns = [
            r"^(page\s+\d+|p\.\s*\d+|\d+\s+of\s+\d+)$",
            r"(student\s+attendance|attendance\s+register|student\s+admission|class\s+register)",
            r"(department\s+of|college\s+of|institute\s+of|university|academic\s+year)",
            r"^(roll\s*(no|number)?[\s\t\|,]+(student\s+)?name[\s\t\|,]+(class|branch)?[\s\t\|,]+(sec|section)?)",
            r"^(generated\s+on|date\s*:|faculty\s*:|department\s*:|institution\s*:)",
            r"^-{3,}$|^={3,}$|^_{3,}$",
        ]

        for line_idx, line in enumerate(lines, 1):
            raw_line = line.strip()
            if not raw_line:
                continue

            lower_line = raw_line.lower()

            # Skip header, page number, and separator lines
            if any(re.search(pat, lower_line) for pat in header_patterns):
                continue

            # Try Pattern 1: Key-Value labeled pairs
            # e.g.: Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A
            kv_record = self._try_parse_key_value_line(raw_line)
            if kv_record:
                students.append(kv_record)
                continue

            # Try Pattern 2: Delimited row (pipes, tabs, or semicolons)
            delim_record = self._try_parse_delimited_line(raw_line)
            if delim_record:
                students.append(delim_record)
                continue

            # Try Pattern 3: Tabular whitespace-separated columns
            # e.g.: "101    Rahul Sharma    CSE    A"
            tab_record = self._try_parse_tabular_line(raw_line)
            if tab_record:
                students.append(tab_record)
                continue

            # If line has alphanumeric content, record as unparsed
            if any(c.isalnum() for c in raw_line):
                unparsed.append({
                    "line_num": line_idx,
                    "text": raw_line,
                    "reason": "Could not identify distinct Roll Number and Student Name"
                })

        return students, unparsed

    def _try_parse_key_value_line(self, line: str) -> Optional[Dict[str, str]]:
        """Match lines like: Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A"""
        roll_match = re.search(r"(?:roll\s*(?:no|number)?|id|reg(?:istration)?\s*(?:no)?)\s*[:=\-]\s*([A-Za-z0-9\-_/]+)", line, re.IGNORECASE)
        name_match = re.search(r"(?:student\s*)?name\s*[:=\-]\s*([^\|;,]+)", line, re.IGNORECASE)

        if roll_match and name_match:
            roll_no = roll_match.group(1).strip()
            name = name_match.group(1).strip()

            class_match = re.search(r"(?:class(?:_name)?|branch|dept|course)\s*[:=\-]\s*([^\|;,]+)", line, re.IGNORECASE)
            sec_match = re.search(r"(?:section|sec|div(?:ision)?)\s*[:=\-]\s*([^\|;,\s]+)", line, re.IGNORECASE)

            class_name = class_match.group(1).strip() if class_match else ""
            section = sec_match.group(1).strip().upper() if sec_match else ""

            if roll_no and name:
                return {
                    "roll_no": roll_no,
                    "name": name,
                    "class_name": class_name,
                    "section": section
                }
        return None

    def _try_parse_delimited_line(self, line: str) -> Optional[Dict[str, str]]:
        """Match lines separated by pipe '|', semicolon ';', or tab '\t'."""
        for sep in ["|", "\t", ";"]:
            if sep in line:
                parts = [p.strip() for p in line.split(sep) if p.strip()]
                if len(parts) >= 2:
                    return self._map_columns_to_student(parts)
        return None

    def _try_parse_tabular_line(self, line: str) -> Optional[Dict[str, str]]:
        """
        Match lines where columns are separated by 2 or more spaces.
        e.g. '101    Rahul Sharma    CSE    A' or 'CS101   Aman Patel'
        """
        # Split on 2 or more spaces
        parts = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        if len(parts) >= 2:
            return self._map_columns_to_student(parts)

        # Fallback: line starts with roll number (e.g., '101 Rahul Sharma CSE A')
        match = re.match(r"^([A-Za-z0-9\-_/]{1,15})\s+([A-Za-z\s\.\'\-]+?)(?:\s+([A-Za-z0-9\-]+))?(?:\s+([A-Za-z0-9]))?$", line)
        if match:
            roll = match.group(1).strip()
            name = match.group(2).strip()
            c_name = match.group(3).strip() if match.group(3) else ""
            sec = match.group(4).strip().upper() if match.group(4) else ""
            if roll and name and len(name) > 1 and not name.lower().startswith("page"):
                return self._map_columns_to_student([roll, name, c_name, sec])

        return None

    def _map_columns_to_student(self, parts: List[str]) -> Optional[Dict[str, str]]:
        """Map ordered column parts [roll, name, class, sec] to a student record."""
        first_token = parts[0].strip()
        second_token = parts[1].strip()

        # Reject common header words or descriptive labels
        non_roll_words = {
            "student", "students", "name", "roll", "rollno", "roll_no", "roll number",
            "department", "college", "institute", "university", "academic", "register",
            "attendance", "admission", "semester", "faculty", "signature", "remarks",
            "date", "class", "section", "course", "branch", "sl", "sno", "sr", "total",
            "page", "id", "s.no", "sl no", "#"
        }
        first_lower = first_token.lower()
        if first_lower in non_roll_words:
            return None
        if any(w in first_lower for w in ("attendance", "register", "department", "college", "admission")):
            return None

        # Clean any trailing/leading symbols
        roll_no = first_token
        name = second_token
        class_name = parts[2].strip() if len(parts) > 2 else ""
        section = parts[3].strip() if len(parts) > 3 else ""

        # Validate name is not a number and looks like a name
        if re.match(r"^\d+$", name):
            return None

        if roll_no and name and len(name) > 1:
            return {
                "roll_no": roll_no,
                "name": name,
                "class_name": class_name,
                "section": section.upper()
            }
        return None


class BulkImportManager:
    """Manages the full lifecycle of student bulk imports across multiple file formats."""

    def __init__(self, db: Database, student_manager: StudentManager):
        self.db = db
        self.student_manager = student_manager
        self.pdf_parser = PDFParser()
        self.current_records: List[Dict[str, Any]] = []
        self.file_path: Optional[Path] = None
        self.unparsed_items: List[Dict[str, Any]] = []
        self.raw_text_preview: str = ""

    def load_file(self, file_path: str | Path, column_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Load a file (.csv, .txt, .pdf, .xlsx), parse records, and run validation.
        Returns a dict with preview records, summary counters, and diagnosis.
        """
        path = Path(file_path)
        self.file_path = path
        self.current_records = []
        self.unparsed_items = []
        self.raw_text_preview = ""

        if not path.exists():
            return {
                "success": False,
                "error": f"File does not exist: {path}",
                "records": [],
                "summary": {}
            }

        suffix = path.suffix.lower()
        extracted: List[Dict[str, str]] = []
        parse_error: Optional[str] = None
        is_scanned_pdf = False
        raw_text_preview = ""

        try:
            if suffix == ".csv":
                extracted, self.unparsed_items = self._parse_csv(path, column_mapping)
            elif suffix == ".txt":
                extracted, self.unparsed_items = self._parse_txt(path)
            elif suffix == ".pdf":
                pdf_res = self.pdf_parser.parse_pdf(path)
                if not pdf_res.success:
                    is_scanned_pdf = pdf_res.is_scanned
                    parse_error = pdf_res.error_message
                    raw_text_preview = pdf_res.raw_text
                extracted = pdf_res.students
                self.unparsed_items = pdf_res.unparsed_lines
                raw_text_preview = pdf_res.raw_text
            elif suffix in (".xlsx", ".xls"):
                if not HAS_OPENPYXL:
                    return {
                        "success": False,
                        "error": "openpyxl is not installed. Please install openpyxl to read Excel files.",
                        "records": [],
                        "summary": {}
                    }
                extracted, self.unparsed_items = self._parse_excel(path, column_mapping)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file format '{suffix}'. Supported formats: .csv, .txt, .pdf, .xlsx",
                    "records": [],
                    "summary": {}
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse file: {str(e)}",
                "records": [],
                "summary": {}
            }

        self.raw_text_preview = raw_text_preview

        if parse_error and not extracted:
            return {
                "success": False,
                "error": parse_error,
                "is_scanned_pdf": is_scanned_pdf,
                "raw_text": raw_text_preview,
                "records": [],
                "summary": {}
            }

        # Initialize internal records with tracking ID and selection flag
        self.current_records = []
        for idx, rec in enumerate(extracted, 1):
            self.current_records.append({
                "id": idx,
                "selected": True,  # Default selected if valid (adjusted in validate)
                "roll_no": str(rec.get("roll_no", "")).strip(),
                "name": str(rec.get("name", "")).strip(),
                "class_name": str(rec.get("class_name", "")).strip(),
                "section": str(rec.get("section", "")).strip().upper(),
                "status": ImportValidationStatus.VALID,
                "status_code": "VALID",
                "details": "Ready for import"
            })

        # Run validation
        summary = self.validate_records()

        return {
            "success": True,
            "file_name": path.name,
            "records": self.current_records,
            "unparsed_items": self.unparsed_items,
            "summary": summary,
            "raw_text": raw_text_preview,
            "error": parse_error
        }

    def validate_records(self) -> Dict[str, int]:
        """
        Validates self.current_records against business rules:
        - Missing Roll No
        - Missing Name
        - Duplicate in File
        - Exists in SQLite Database
        - Update selection state & summary counters
        """
        existing_db_rolls = self.student_manager.get_existing_roll_numbers()

        # Count frequencies inside file
        seen_file_rolls: Dict[str, int] = {}
        for rec in self.current_records:
            roll_key = rec["roll_no"].upper()
            if roll_key:
                seen_file_rolls[roll_key] = seen_file_rolls.get(roll_key, 0) + 1

        total_detected = len(self.current_records)
        valid_count = 0
        dup_file_count = 0
        dup_db_count = 0
        invalid_count = 0

        for rec in self.current_records:
            roll = rec["roll_no"]
            name = rec["name"]
            roll_key = roll.upper()

            if not roll:
                rec["status"] = ImportValidationStatus.MISSING_ROLL
                rec["status_code"] = "INVALID"
                rec["details"] = "Roll number cannot be empty"
                rec["selected"] = False
                invalid_count += 1
            elif not name:
                rec["status"] = ImportValidationStatus.MISSING_NAME
                rec["status_code"] = "INVALID"
                rec["details"] = "Student name cannot be empty"
                rec["selected"] = False
                invalid_count += 1
            elif seen_file_rolls.get(roll_key, 0) > 1:
                rec["status"] = ImportValidationStatus.DUP_IN_FILE
                rec["status_code"] = "DUP_FILE"
                rec["details"] = f"Roll number appears {seen_file_rolls[roll_key]} times in this file"
                rec["selected"] = False
                dup_file_count += 1
            elif roll_key in existing_db_rolls:
                rec["status"] = ImportValidationStatus.DUP_IN_DB
                rec["status_code"] = "DUP_DB"
                rec["details"] = "Roll number already exists in database"
                rec["selected"] = False
                dup_db_count += 1
            else:
                rec["status"] = ImportValidationStatus.VALID
                rec["status_code"] = "VALID"
                rec["details"] = "Ready for import"
                rec["selected"] = True
                valid_count += 1

        ready_to_import = sum(1 for r in self.current_records if r["selected"])

        return {
            "total_detected": total_detected,
            "valid_count": valid_count,
            "duplicate_file_count": dup_file_count,
            "duplicate_db_count": dup_db_count,
            "invalid_count": invalid_count,
            "ready_to_import": ready_to_import
        }

    def update_record(self, record_id: int, roll_no: str, name: str, class_name: str, section: str) -> None:
        """Edit a record in preview and re-run validation."""
        for rec in self.current_records:
            if rec["id"] == record_id:
                rec["roll_no"] = roll_no.strip()
                rec["name"] = name.strip()
                rec["class_name"] = class_name.strip()
                rec["section"] = section.strip().upper()
                break
        self.validate_records()

    def remove_record(self, record_id: int) -> None:
        """Remove a record from the preview list."""
        self.current_records = [r for r in self.current_records if r["id"] != record_id]
        self.validate_records()

    def toggle_record_selection(self, record_id: int, is_selected: bool) -> None:
        """Toggle record selection flag."""
        for rec in self.current_records:
            if rec["id"] == record_id:
                rec["selected"] = is_selected
                break

    def select_all_valid(self) -> None:
        """Select all valid and unique records."""
        for rec in self.current_records:
            if rec["status_code"] == "VALID":
                rec["selected"] = True

    def select_all(self, include_duplicates: bool = False) -> None:
        """Select all records, optionally including duplicates."""
        for rec in self.current_records:
            if rec["status_code"] == "VALID":
                rec["selected"] = True
            elif include_duplicates and rec["status_code"] in ("DUP_DB",):
                rec["selected"] = True

    def deselect_all(self) -> None:
        """Deselect all records."""
        for rec in self.current_records:
            rec["selected"] = False

    def execute_import(self, duplicate_action: str = "skip") -> Dict[str, Any]:
        """
        Execute atomic SQLite transaction to insert/update selected records.
        duplicate_action:
          - 'skip': ignore records that exist in DB
          - 'update': update existing student name, class, and section
        Returns summary: added, updated, skipped, failed.
        """
        selected_records = [r for r in self.current_records if r["selected"]]

        if not selected_records:
            return {
                "success": False,
                "error": "No records are selected for import.",
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 0
            }

        existing_students = self.student_manager.get_existing_students_map()
        added_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        errors: List[str] = []

        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()

                for rec in selected_records:
                    roll = rec["roll_no"].strip()
                    name = rec["name"].strip()
                    c_name = rec["class_name"].strip()
                    sec = rec["section"].strip().upper()

                    if not roll or not name:
                        failed_count += 1
                        errors.append(f"Skipped record with missing roll or name: {rec}")
                        continue

                    roll_key = roll.upper()

                    if roll_key in existing_students:
                        if duplicate_action == "update":
                            # Update existing student
                            cursor.execute("""
                                UPDATE students
                                SET name = ?, class_name = ?, section = ?
                                WHERE roll_no = ? COLLATE NOCASE;
                            """, (name, c_name, sec, roll))
                            updated_count += 1
                        else:
                            # Skip duplicate
                            skipped_count += 1
                    else:
                        # Insert new student
                        cursor.execute("""
                            INSERT INTO students (roll_no, name, class_name, section)
                            VALUES (?, ?, ?, ?);
                        """, (roll, name, c_name, sec))
                        added_count += 1
                        existing_students[roll_key] = {"roll_no": roll, "name": name}

            return {
                "success": True,
                "added": added_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total_processed": len(selected_records),
                "errors": errors
            }

        except Exception as e:
            # Transaction automatically rolled back by context manager
            return {
                "success": False,
                "error": f"Database transaction failed and was rolled back: {str(e)}",
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "failed": len(selected_records)
            }

    # --- File Parsing Helpers ---

    def _parse_csv(self, path: Path, custom_mapping: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """Parse CSV with smart header detection and encoding fallback."""
        records: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        text = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return records, unparsed

        reader = list(csv.reader(lines))
        if not reader:
            return records, unparsed

        header_idx, col_map = self._detect_csv_headers(reader, custom_mapping)
        start_row = header_idx + 1 if header_idx is not None else 0

        for row_num, row in enumerate(reader[start_row:], start=start_row + 1):
            if not any(cell.strip() for cell in row):
                continue

            record = {
                "roll_no": "",
                "name": "",
                "class_name": "",
                "section": ""
            }

            if col_map:
                for target_field, col_idx in col_map.items():
                    if col_idx < len(row):
                        record[target_field] = row[col_idx].strip()
            else:
                if len(row) >= 1:
                    record["roll_no"] = row[0].strip()
                if len(row) >= 2:
                    record["name"] = row[1].strip()
                if len(row) >= 3:
                    record["class_name"] = row[2].strip()
                if len(row) >= 4:
                    record["section"] = row[3].strip()

            if record["roll_no"] or record["name"]:
                records.append(record)
            else:
                unparsed.append({"line_num": row_num, "text": ",".join(row), "reason": "Empty row or missing identifiers"})

        return records, unparsed

    def _detect_csv_headers(
        self,
        rows: List[List[str]],
        custom_mapping: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[int], Dict[str, int]]:
        """
        Scan first few rows to locate the header row and map column indices.
        """
        col_map: Dict[str, int] = {}
        header_row_idx: Optional[int] = None

        if custom_mapping:
            first_row = [c.strip().lower() for c in rows[0]]
            for field, col_name in custom_mapping.items():
                if col_name.lower() in first_row:
                    col_map[field] = first_row.index(col_name.lower())
            return (0, col_map)

        for row_idx, row in enumerate(rows[:5]):
            row_normalized = [c.strip().lower() for c in row]
            matched_fields = {}

            for field, aliases in HEADER_ALIASES.items():
                for idx, cell in enumerate(row_normalized):
                    if cell in aliases or any(cell.startswith(a) for a in aliases):
                        matched_fields[field] = idx
                        break

            if COL_ROLL in matched_fields or COL_NAME in matched_fields:
                header_row_idx = row_idx
                col_map = matched_fields
                break

        return (header_row_idx, col_map)

    def _parse_excel(self, path: Path, custom_mapping: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """Read .xlsx files using openpyxl and convert to rows."""
        wb = openpyxl.load_workbook(str(path), data_only=True)
        ws = wb.active

        rows: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
            if any(cleaned_row):
                rows.append(cleaned_row)

        wb.close()

        if not rows:
            return [], []

        header_idx, col_map = self._detect_csv_headers(rows, custom_mapping)
        start_row = header_idx + 1 if header_idx is not None else 0

        records: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        for row_num, row in enumerate(rows[start_row:], start=start_row + 1):
            if not any(row):
                continue

            record = {"roll_no": "", "name": "", "class_name": "", "section": ""}
            if col_map:
                for target_field, col_idx in col_map.items():
                    if col_idx < len(row):
                        record[target_field] = row[col_idx].strip()
            else:
                if len(row) >= 1:
                    record["roll_no"] = row[0].strip()
                if len(row) >= 2:
                    record["name"] = row[1].strip()
                if len(row) >= 3:
                    record["class_name"] = row[2].strip()
                if len(row) >= 4:
                    record["section"] = row[3].strip()

            if record["roll_no"] or record["name"]:
                records.append(record)
            else:
                unparsed.append({"line_num": row_num, "text": " | ".join(row), "reason": "Empty row"})

        return records, unparsed

    def _parse_txt(self, path: Path) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """
        Parse plain-text student lists.
        Handles key-value format (Roll No: 101 | Name: ...) and delimited rows (101, Rahul Sharma, CSE, A).
        """
        records: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        text = ""
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                text = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        lines = text.splitlines()

        for line_num, line in enumerate(lines, 1):
            raw = line.strip()
            if not raw or raw.startswith("#") or raw.startswith("//"):
                continue

            lower_line = raw.lower()
            if "roll" in lower_line and "name" in lower_line and not re.search(r"\d", lower_line):
                continue

            # Pattern 1: Key-Value format (Roll No: 101 | Name: Rahul Sharma ...)
            kv_match = self.pdf_parser._try_parse_key_value_line(raw)
            if kv_match:
                records.append(kv_match)
                continue

            # Pattern 2: Delimited by comma, pipe, tab, or semicolon
            for delim in [",", "|", "\t", ";"]:
                if delim in raw:
                    parts = [p.strip() for p in raw.split(delim) if p.strip()]
                    if len(parts) >= 2:
                        record = {
                            "roll_no": parts[0],
                            "name": parts[1],
                            "class_name": parts[2] if len(parts) > 2 else "",
                            "section": parts[3].upper() if len(parts) > 3 else ""
                        }
                        records.append(record)
                        break
            else:
                unparsed.append({"line_num": line_num, "text": raw, "reason": "Unrecognized line format"})

        return records, unparsed


# =====================================================================
# SECTION 5: ATTENDANCE MANAGEMENT
# =====================================================================

class AttendanceManager:
    """Handles marking, modifying, batch saving, and querying attendance records."""

    def __init__(self, db: Database):
        self.db = db

    def validate_date(self, date_str: str) -> str:
        """Validate and format date string as YYYY-MM-DD."""
        try:
            parsed = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.")

    def has_attendance_for_date(
        self,
        attendance_date: str,
        class_name: Optional[str] = None,
        section: Optional[str] = None
    ) -> Tuple[bool, int]:
        """
        Check if attendance already exists for the given date (and optionally class/section).
        Returns (exists_flag, count_of_records).
        """
        date_str = self.validate_date(attendance_date)
        conditions = ["a.attendance_date = ?"]
        params: List[Any] = [date_str]

        if class_name and class_name != "All":
            conditions.append("s.class_name = ?")
            params.append(class_name)

        if section and section != "All":
            conditions.append("s.section = ?")
            params.append(section)

        query = f"""
            SELECT COUNT(a.id) as count
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE {" AND ".join(conditions)};
        """
        res = self.db.fetch_one(query, tuple(params))
        count = res["count"] if res else 0
        return (count > 0, count)

    def get_attendance_sheet(
        self,
        attendance_date: str,
        class_name: str = "",
        section: str = "",
        search_query: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all students for the given class/section along with their attendance status
        for the specified date. Status will be 'Present', 'Absent', 'Leave', or None if unmarked.
        """
        date_str = self.validate_date(attendance_date)
        conditions = []
        params: List[Any] = [date_str]

        if class_name and class_name != "All":
            conditions.append("s.class_name = ?")
            params.append(class_name)

        if section and section != "All":
            conditions.append("s.section = ?")
            params.append(section)

        if search_query:
            conditions.append("(s.roll_no LIKE ? OR s.name LIKE ?)")
            q = f"%{search_query.strip()}%"
            params.extend([q, q])

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT
                s.id as student_id,
                s.roll_no,
                s.name,
                s.class_name,
                s.section,
                a.status as status,
                a.id as attendance_id
            FROM students s
            LEFT JOIN attendance a ON s.id = a.student_id AND a.attendance_date = ?
            {where_clause}
            ORDER BY s.roll_no COLLATE NOCASE ASC;
        """
        return self.db.fetch_all(query, tuple(params))

    def save_batch_attendance(
        self,
        attendance_date: str,
        records: List[Dict[str, Any]],
        overwrite: bool = True
    ) -> int:
        """
        Save attendance for multiple students for a given date in an atomic transaction.
        Each record should contain 'student_id' and 'status' ('Present', 'Absent', or 'Leave').
        Returns the number of saved records.
        """
        date_str = self.validate_date(attendance_date)

        if not records:
            return 0

        # Validate all records before starting transaction
        for r in records:
            status = r.get("status")
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid attendance status: '{status}'. Must be Present, Absent, or Leave.")

        with self.db.transaction() as conn:
            cursor = conn.cursor()
            saved_count = 0

            for r in records:
                student_id = r["student_id"]
                status = r["status"]

                if overwrite:
                    cursor.execute("""
                        INSERT INTO attendance (student_id, attendance_date, status)
                        VALUES (?, ?, ?)
                        ON CONFLICT(student_id, attendance_date)
                        DO UPDATE SET status = excluded.status;
                    """, (student_id, date_str, status))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO attendance (student_id, attendance_date, status)
                        VALUES (?, ?, ?);
                    """, (student_id, date_str, status))

                saved_count += 1

            return saved_count

    def get_date_stats(self, attendance_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate attendance statistics for a specific date:
        - total_students: registered in system
        - marked_count: total attendance records for this date
        - present_count, absent_count, leave_count
        - unmarked_count: total_students - marked_count
        - percentage: Present / (Present + Absent) * 100
        """
        if not attendance_date:
            date_str = date.today().strftime("%Y-%m-%d")
        else:
            date_str = self.validate_date(attendance_date)

        tot_res = self.db.fetch_one("SELECT COUNT(*) as count FROM students;")
        total_students = tot_res["count"] if tot_res else 0

        query = """
            SELECT
                status,
                COUNT(*) as count
            FROM attendance
            WHERE attendance_date = ?
            GROUP BY status;
        """
        rows = self.db.fetch_all(query, (date_str,))
        status_counts = {r["status"]: r["count"] for r in rows}

        present = status_counts.get("Present", 0)
        absent = status_counts.get("Absent", 0)
        leave = status_counts.get("Leave", 0)
        marked = present + absent + leave
        unmarked = max(0, total_students - marked)

        denominator = present + absent
        if denominator > 0:
            percentage = round((present / denominator) * 100.0, 1)
        elif marked > 0 and leave > 0:
            percentage = 100.0
        else:
            percentage = 0.0

        return {
            "date": date_str,
            "total_students": total_students,
            "marked_count": marked,
            "present_count": present,
            "absent_count": absent,
            "leave_count": leave,
            "unmarked_count": unmarked,
            "percentage": percentage
        }

    def get_recent_activity(self, limit: int = 6) -> List[Dict[str, Any]]:
        """Fetch summary of recent attendance sessions grouped by date and class."""
        query = f"""
            SELECT
                a.attendance_date,
                s.class_name,
                COUNT(a.id) as total_marked,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN a.status = 'Leave' THEN 1 ELSE 0 END) as leave_count
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            GROUP BY a.attendance_date, s.class_name
            ORDER BY a.attendance_date DESC, s.class_name ASC
            LIMIT ?;
        """
        rows = self.db.fetch_all(query, (limit,))
        for r in rows:
            denom = r["present_count"] + r["absent_count"]
            r["percentage"] = round((r["present_count"] / denom * 100.0), 1) if denom > 0 else 0.0
        return rows


# =====================================================================
# SECTION 6: REPORTS AND EXPORTS
# =====================================================================

class ReportsManager:
    """Calculates attendance metrics, identifies low-attendance students, and exports reports."""

    def __init__(self, db: Database):
        self.db = db

    def calculate_attendance_percentage(self, present_days: int, absent_days: int) -> float:
        """
        Attendance Percentage = Present Days / (Present Days + Absent Days) * 100
        Leave days do not count as present or absent days.
        """
        denominator = present_days + absent_days
        if denominator <= 0:
            return 100.0
        return round((present_days / denominator) * 100.0, 1)

    def get_attendance_report(
        self,
        class_filter: str = "",
        section_filter: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search_query: str = "",
        only_defaulters: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Generates class-wise and student-wise attendance reports with filters and percentage calculation.
        """
        conditions = []
        params: List[Any] = []

        if class_filter and class_filter != "All":
            conditions.append("s.class_name = ?")
            params.append(class_filter)

        if section_filter and section_filter != "All":
            conditions.append("s.section = ?")
            params.append(section_filter)

        if search_query:
            conditions.append("(s.roll_no LIKE ? OR s.name LIKE ?)")
            q = f"%{search_query.strip()}%"
            params.extend([q, q])

        # Date range for attendance
        date_conditions = []
        date_params: List[Any] = []

        if start_date:
            date_conditions.append("a.attendance_date >= ?")
            date_params.append(start_date)

        if end_date:
            date_conditions.append("a.attendance_date <= ?")
            date_params.append(end_date)

        date_clause = " AND " + " AND ".join(date_conditions) if date_conditions else ""
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT
                s.id as student_id,
                s.roll_no,
                s.name,
                s.class_name,
                s.section,
                COUNT(a.id) as total_days_recorded,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_days,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_days,
                SUM(CASE WHEN a.status = 'Leave' THEN 1 ELSE 0 END) as leave_days
            FROM students s
            LEFT JOIN attendance a ON s.id = a.student_id {date_clause}
            {where_clause}
            GROUP BY s.id, s.roll_no, s.name, s.class_name, s.section
            ORDER BY s.roll_no COLLATE NOCASE ASC;
        """

        all_params = tuple(date_params + params)
        rows = self.db.fetch_all(query, all_params)

        results = []
        for r in rows:
            present = r["present_days"] or 0
            absent = r["absent_days"] or 0
            leave = r["leave_days"] or 0
            total_recorded = r["total_days_recorded"] or 0

            if (present + absent) > 0:
                pct = round((present / (present + absent)) * 100.0, 1)
                has_history = True
            else:
                pct = 100.0 if total_recorded > 0 else 0.0
                has_history = total_recorded > 0

            is_low = has_history and (pct < ATTENDANCE_DEFICIT_THRESHOLD)

            item = {
                "student_id": r["student_id"],
                "roll_no": r["roll_no"],
                "name": r["name"],
                "class_name": r["class_name"],
                "section": r["section"],
                "total_days": total_recorded,
                "present_days": present,
                "absent_days": absent,
                "leave_days": leave,
                "percentage": pct,
                "has_history": has_history,
                "is_low": is_low,
                "status_label": "CRITICAL (<75%)" if is_low else "Satisfactory"
            }

            if only_defaulters:
                if is_low:
                    results.append(item)
            else:
                results.append(item)

        return results

    def get_student_history(self, student_id: int) -> List[Dict[str, Any]]:
        """Retrieve full chronological attendance history for a single student."""
        query = """
            SELECT
                id,
                attendance_date,
                status
            FROM attendance
            WHERE student_id = ?
            ORDER BY attendance_date DESC;
        """
        rows = self.db.fetch_all(query, (student_id,))
        for r in rows:
            try:
                dt = datetime.strptime(r["attendance_date"], "%Y-%m-%d")
                r["day_name"] = dt.strftime("%A")
            except Exception:
                r["day_name"] = ""
        return rows

    def export_report_to_csv(self, file_path: str | Path, report_data: List[Dict[str, Any]]) -> bool:
        """Export generated report data to a well-formatted CSV file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        headers = [
            "Roll Number",
            "Student Name",
            "Class",
            "Section",
            "Total Days Recorded",
            "Present Days",
            "Absent Days",
            "Leave Days",
            "Attendance %",
            "Attendance Status"
        ]

        with open(path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for row in report_data:
                writer.writerow([
                    row.get("roll_no", ""),
                    row.get("name", ""),
                    row.get("class_name", ""),
                    row.get("section", ""),
                    row.get("total_days", 0),
                    row.get("present_days", 0),
                    row.get("absent_days", 0),
                    row.get("leave_days", 0),
                    f"{row.get('percentage', 0.0)}%",
                    row.get("status_label", "")
                ])

        return True


# =====================================================================
# SECTION 7: GUI COMPONENTS AND STYLES
# =====================================================================

# Design Tokens
COLOR_SIDEBAR_BG = "#0F172A"       # Slate 900
COLOR_SIDEBAR_HOVER = "#1E293B"    # Slate 800
COLOR_SIDEBAR_ACTIVE = "#2563EB"   # Royal Blue
COLOR_SIDEBAR_TEXT = "#F8FAFC"     # Slate 50
COLOR_SIDEBAR_MUTED = "#94A3B8"    # Slate 400

COLOR_CONTENT_BG = "#F8FAFC"       # Light Slate
COLOR_CARD_BG = "#FFFFFF"          # Pure White
COLOR_CARD_BORDER = "#E2E8F0"      # Slate 200

COLOR_PRIMARY = "#2563EB"          # Royal Blue
COLOR_PRIMARY_HOVER = "#1D4ED8"    # Darker Blue
COLOR_PRIMARY_LIGHT = "#EFF6FF"    # Blue 50

COLOR_SUCCESS = "#10B981"          # Emerald Green
COLOR_SUCCESS_LIGHT = "#ECFDF5"    # Emerald 50
COLOR_DANGER = "#EF4444"           # Red
COLOR_DANGER_LIGHT = "#FEF2F2"     # Red 50
COLOR_WARNING = "#F59E0B"          # Amber
COLOR_WARNING_LIGHT = "#FFFBEB"    # Amber 50
COLOR_INFO = "#6366F1"             # Indigo

COLOR_TEXT_PRIMARY = "#0F172A"     # Deep Slate
COLOR_TEXT_SECONDARY = "#64748B"   # Cool Grey
COLOR_TEXT_MUTED = "#94A3B8"       # Light Grey

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 12, "bold")
FONT_HEADING = (FONT_FAMILY, 10, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_BADGE = (FONT_FAMILY, 9, "bold")
FONT_NAV = (FONT_FAMILY, 11, "normal")
FONT_NAV_ACTIVE = (FONT_FAMILY, 11, "bold")
FONT_STAT_NUM = (FONT_FAMILY, 22, "bold")


def configure_app_styles(root: tk.Tk) -> ttk.Style:
    """Configures global ttk widget styles to match modern theme."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(bg=COLOR_CONTENT_BG)

    # Base Frame styles
    style.configure("TFrame", background=COLOR_CONTENT_BG)
    style.configure("Card.TFrame", background=COLOR_CARD_BG, relief="solid", borderwidth=1)
    style.configure("Sidebar.TFrame", background=COLOR_SIDEBAR_BG)

    # Base Label styles
    style.configure("TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_BODY)
    style.configure("Card.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_BODY)
    style.configure("Title.TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_TITLE)
    style.configure("CardTitle.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_SECONDARY, font=FONT_HEADING)
    style.configure("StatNum.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_STAT_NUM)
    style.configure("Muted.TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_SECONDARY, font=FONT_SMALL)

    # Treeview (Modern Tables)
    style.configure(
        "Custom.Treeview",
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        fieldbackground=COLOR_CARD_BG,
        rowheight=32,
        font=FONT_BODY,
        borderwidth=0
    )
    style.configure(
        "Custom.Treeview.Heading",
        background="#F1F5F9",
        foreground=COLOR_TEXT_PRIMARY,
        font=FONT_HEADING,
        relief="flat",
        padding=(6, 6)
    )
    style.map(
        "Custom.Treeview.Heading",
        background=[("active", "#E2E8F0")]
    )
    style.map(
        "Custom.Treeview",
        background=[("selected", COLOR_PRIMARY_LIGHT)],
        foreground=[("selected", COLOR_PRIMARY)]
    )

    # Entry styles
    style.configure(
        "TEntry",
        padding=6,
        relief="flat",
        font=FONT_BODY
    )

    # Combobox styles
    style.configure(
        "TCombobox",
        padding=5,
        font=FONT_BODY
    )

    # Button styles
    style.configure(
        "Primary.TButton",
        background=COLOR_PRIMARY,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_PRIMARY_HOVER), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Success.TButton",
        background=COLOR_SUCCESS,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Success.TButton",
        background=[("active", "#059669"), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Danger.TButton",
        background=COLOR_DANGER,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#DC2626"), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Secondary.TButton",
        background="#E2E8F0",
        foreground=COLOR_TEXT_PRIMARY,
        font=FONT_HEADING,
        padding=(10, 6),
        relief="flat"
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#CBD5E1")]
    )

    return style


# Reusable UI Components

class StatCard(tk.Frame):
    """Modern elevated statistics card with icon, label, primary value, and subtitle."""

    def __init__(self, parent, title: str, value: str = "0", icon: str = "📊", accent_color: str = COLOR_PRIMARY, **kwargs):
        super().__init__(parent, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=16, pady=14, **kwargs)
        self.accent_color = accent_color

        top_frame = tk.Frame(self, bg=COLOR_CARD_BG)
        top_frame.pack(fill="x", anchor="w")

        self.icon_label = tk.Label(top_frame, text=icon, font=("Segoe UI Emoji", 14), bg=COLOR_CARD_BG, fg=accent_color)
        self.icon_label.pack(side="left", padx=(0, 8))

        self.title_label = tk.Label(top_frame, text=title.upper(), font=FONT_SMALL, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.title_label.pack(side="left")

        self.value_label = tk.Label(self, text=value, font=FONT_STAT_NUM, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.value_label.pack(anchor="w", pady=(8, 2))

        self.sub_label = tk.Label(self, text="", font=FONT_SMALL, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.sub_label.pack(anchor="w")

    def update_value(self, value: str, subtext: str = ""):
        self.value_label.config(text=str(value))
        if subtext:
            self.sub_label.config(text=subtext)


class CustomTable(tk.Frame):
    """
    Modern styled Treeview wrapper with scrollbars, sortable columns,
    zebra striping, and empty state message.
    """

    def __init__(
        self,
        parent,
        columns: List[str],
        headings: List[str],
        col_widths: Optional[List[int]] = None,
        col_aligns: Optional[List[str]] = None,
        show_empty_state: bool = True,
        empty_text: str = "No records found.",
        **kwargs
    ):
        super().__init__(parent, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, **kwargs)
        self.columns = columns
        self.headings = headings
        self.empty_text = empty_text
        self.sort_column = None
        self.sort_reverse = False

        self.tree_frame = tk.Frame(self, bg=COLOR_CARD_BG)
        self.tree_frame.pack(fill="both", expand=True)

        self.y_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.x_scroll = ttk.Scrollbar(self.tree_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=columns,
            show="headings",
            style="Custom.Treeview",
            yscrollcommand=self.y_scroll.set,
            xscrollcommand=self.x_scroll.set,
            selectmode="extended"
        )
        self.y_scroll.config(command=self.tree.yview)
        self.x_scroll.config(command=self.tree.xview)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.y_scroll.grid(row=0, column=1, sticky="ns")
        self.x_scroll.grid(row=1, column=0, sticky="ew")

        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

        for idx, col in enumerate(columns):
            heading = headings[idx] if idx < len(headings) else col
            width = col_widths[idx] if col_widths and idx < len(col_widths) else 120
            align = col_aligns[idx] if col_aligns and idx < len(col_aligns) else "w"

            self.tree.heading(col, text=heading, command=lambda c=col: self._on_header_click(c))
            self.tree.column(col, width=width, anchor=align, minwidth=60)

        self.tree.tag_configure("even", background="#FFFFFF")
        self.tree.tag_configure("odd", background="#F8FAFC")
        self.tree.tag_configure("status_valid", background="#ECFDF5", foreground="#065F46")
        self.tree.tag_configure("status_warning", background="#FFFBEB", foreground="#92400E")
        self.tree.tag_configure("status_danger", background="#FEF2F2", foreground="#991B1B")
        self.tree.tag_configure("defaulter", background="#FEF2F2", foreground="#B91C1C")

    def _on_header_click(self, col: str):
        """Header sorting handler."""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        try:
            items.sort(key=lambda t: float(t[0].replace("%", "").strip()), reverse=self.sort_reverse)
        except ValueError:
            items.sort(key=lambda t: str(t[0]).lower(), reverse=self.sort_reverse)

        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)

        for c in self.columns:
            h_text = self.headings[self.columns.index(c)]
            if c == col:
                h_text += " ▲" if not self.sort_reverse else " ▼"
            self.tree.heading(c, text=h_text)

    def clear(self):
        """Remove all rows."""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values: Tuple[Any, ...] | List[Any], tags: Tuple[str, ...] = ()):
        idx = len(self.tree.get_children())
        row_tag = "even" if idx % 2 == 0 else "odd"
        combined_tags = (row_tag,) + tuple(tags)
        return self.tree.insert("", "end", values=values, tags=combined_tags)


class StudentDialog(tk.Toplevel):
    """Modal dialog for creating or updating a single student record."""

    def __init__(self, parent, title: str = "Add Student", student_data: Optional[Dict[str, Any]] = None, on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=COLOR_CONTENT_BG)

        self.student_data = student_data or {}
        self.on_save = on_save
        self.saved = False

        self._create_widgets()
        self.center_window(460, 360)

    def center_window(self, w: int, h: int):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _create_widgets(self):
        main_frame = tk.Frame(self, bg=COLOR_CARD_BG, padx=24, pady=20)
        main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Label(main_frame, text=self.title(), font=FONT_SUBTITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        header.pack(anchor="w", pady=(0, 16))

        tk.Label(main_frame, text="Roll Number *", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.roll_entry = ttk.Entry(main_frame, font=FONT_BODY)
        self.roll_entry.pack(fill="x", pady=(2, 10))
        if self.student_data.get("roll_no"):
            self.roll_entry.insert(0, self.student_data["roll_no"])

        tk.Label(main_frame, text="Full Name *", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.name_entry = ttk.Entry(main_frame, font=FONT_BODY)
        self.name_entry.pack(fill="x", pady=(2, 10))
        if self.student_data.get("name"):
            self.name_entry.insert(0, self.student_data["name"])

        two_col = tk.Frame(main_frame, bg=COLOR_CARD_BG)
        two_col.pack(fill="x", pady=(0, 16))

        c1 = tk.Frame(two_col, bg=COLOR_CARD_BG)
        c1.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(c1, text="Class / Department", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.class_entry = ttk.Entry(c1, font=FONT_BODY)
        self.class_entry.pack(fill="x", pady=(2, 0))
        if self.student_data.get("class_name"):
            self.class_entry.insert(0, self.student_data["class_name"])

        c2 = tk.Frame(two_col, bg=COLOR_CARD_BG)
        c2.pack(side="right", fill="x", expand=True)
        tk.Label(c2, text="Section", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.sec_entry = ttk.Entry(c2, font=FONT_BODY)
        self.sec_entry.pack(fill="x", pady=(2, 0))
        if self.student_data.get("section"):
            self.sec_entry.insert(0, self.student_data["section"])

        btn_frame = tk.Frame(main_frame, bg=COLOR_CARD_BG)
        btn_frame.pack(fill="x", pady=(10, 0))

        cancel_btn = ttk.Button(btn_frame, text="Cancel", style="Secondary.TButton", command=self.destroy)
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ttk.Button(btn_frame, text="Save Student", style="Primary.TButton", command=self._save)
        save_btn.pack(side="right")

    def _save(self):
        roll = self.roll_entry.get().strip()
        name = self.name_entry.get().strip()
        c_name = self.class_entry.get().strip()
        sec = self.sec_entry.get().strip().upper()

        if not roll:
            messagebox.showwarning("Validation Error", "Roll number is required.", parent=self)
            self.roll_entry.focus_set()
            return

        if not name:
            messagebox.showwarning("Validation Error", "Student name is required.", parent=self)
            self.name_entry.focus_set()
            return

        if self.on_save:
            try:
                self.on_save(roll, name, c_name, sec)
                self.saved = True
                self.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)


class RecordEditDialog(tk.Toplevel):
    """Modal dialog for inline editing a single preview row in the Bulk Import wizard."""

    def __init__(self, parent, record: Dict[str, Any], on_save: Callable):
        super().__init__(parent)
        self.title("Edit Record in Import Preview")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=COLOR_CONTENT_BG)

        self.record = record
        self.on_save = on_save

        self._create_widgets()
        self.center_window(440, 320)

    def center_window(self, w: int, h: int):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _create_widgets(self):
        main = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=20)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(main, text="Edit Preview Record", font=FONT_SUBTITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w", pady=(0, 12))

        tk.Label(main, text="Roll Number", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.roll = ttk.Entry(main, font=FONT_BODY)
        self.roll.pack(fill="x", pady=(2, 8))
        self.roll.insert(0, self.record.get("roll_no", ""))

        tk.Label(main, text="Student Name", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.name = ttk.Entry(main, font=FONT_BODY)
        self.name.pack(fill="x", pady=(2, 8))
        self.name.insert(0, self.record.get("name", ""))

        two = tk.Frame(main, bg=COLOR_CARD_BG)
        two.pack(fill="x", pady=(0, 14))

        f1 = tk.Frame(two, bg=COLOR_CARD_BG)
        f1.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(f1, text="Class", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.c_name = ttk.Entry(f1, font=FONT_BODY)
        self.c_name.pack(fill="x", pady=(2, 0))
        self.c_name.insert(0, self.record.get("class_name", ""))

        f2 = tk.Frame(two, bg=COLOR_CARD_BG)
        f2.pack(side="right", fill="x", expand=True)
        tk.Label(f2, text="Section", font=FONT_HEADING, bg=COLOR_CARD_BG).pack(anchor="w")
        self.sec = ttk.Entry(f2, font=FONT_BODY)
        self.sec.pack(fill="x", pady=(2, 0))
        self.sec.insert(0, self.record.get("section", ""))

        bf = tk.Frame(main, bg=COLOR_CARD_BG)
        bf.pack(fill="x")
        ttk.Button(bf, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(bf, text="Update Record", style="Primary.TButton", command=self._do_update).pack(side="right")

    def _do_update(self):
        r = self.roll.get().strip()
        n = self.name.get().strip()
        c = self.c_name.get().strip()
        s = self.sec.get().strip().upper()
        self.on_save(self.record["id"], r, n, c, s)
        self.destroy()


# Application Views

class DashboardView(tk.Frame):
    """Modern dashboard view containing summary metrics and recent activity."""

    def __init__(
        self,
        parent,
        db: Database,
        student_mgr: StudentManager,
        att_mgr: AttendanceManager,
        reports_mgr: ReportsManager,
        navigate_to: Callable[[str], None]
    ):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.att_mgr = att_mgr
        self.reports_mgr = reports_mgr
        self.navigate_to = navigate_to

        self.selected_date = date.today().strftime("%Y-%m-%d")

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Top Header Bar
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 16))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Attendance Dashboard", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(title_box, text="Overview of class attendance, student metrics, and daily trends", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w")

        # Date Switcher on Right
        date_box = tk.Frame(header, bg=COLOR_CARD_BG, padx=10, pady=6, highlightbackground="#E2E8F0", highlightthickness=1)
        date_box.pack(side="right")

        tk.Label(date_box, text="Selected Date:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self.date_var = tk.StringVar(value=self.selected_date)
        self.date_entry = ttk.Entry(date_box, textvariable=self.date_var, width=12, font=FONT_BODY)
        self.date_entry.pack(side="left", padx=(0, 6))

        ttk.Button(date_box, text="Today", style="Secondary.TButton", command=self._set_today).pack(side="left", padx=(0, 4))
        ttk.Button(date_box, text="Yesterday", style="Secondary.TButton", command=self._set_yesterday).pack(side="left", padx=(0, 4))
        ttk.Button(date_box, text="Apply", style="Primary.TButton", command=self._apply_date).pack(side="left")

        # Low attendance banner container
        self.banner_frame = tk.Frame(self, bg=COLOR_CONTENT_BG)
        self.banner_frame.pack(fill="x", padx=24, pady=(0, 14))

        # Metrics Cards Row
        cards_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        cards_container.pack(fill="x", padx=24, pady=(0, 16))
        cards_container.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="stat_cards")

        self.card_total = StatCard(cards_container, title="Total Students", value="0", icon="👥", accent_color=COLOR_PRIMARY)
        self.card_total.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.card_present = StatCard(cards_container, title="Present Today", value="0", icon="✅", accent_color=COLOR_SUCCESS)
        self.card_present.grid(row=0, column=1, sticky="ew", padx=4)

        self.card_absent = StatCard(cards_container, title="Absent Today", value="0", icon="❌", accent_color=COLOR_DANGER)
        self.card_absent.grid(row=0, column=2, sticky="ew", padx=4)

        self.card_leave = StatCard(cards_container, title="On Leave Today", value="0", icon="🌴", accent_color=COLOR_WARNING)
        self.card_leave.grid(row=0, column=3, sticky="ew", padx=4)

        self.card_pct = StatCard(cards_container, title="Attendance Rate", value="0.0%", icon="📈", accent_color=COLOR_PRIMARY)
        self.card_pct.grid(row=0, column=4, sticky="ew", padx=(8, 0))

        # Middle Row: Quick Actions Bar
        actions_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        actions_bar.pack(fill="x", padx=24, pady=(0, 18))

        tk.Label(actions_bar, text="⚡ Quick Actions:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 16))

        ttk.Button(actions_bar, text="📅 Mark Attendance", style="Primary.TButton", command=lambda: self.navigate_to("attendance")).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="📥 Bulk Import Students", style="Success.TButton", command=lambda: self.navigate_to("import")).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="➕ Add Single Student", style="Secondary.TButton", command=self._open_add_student).pack(side="left", padx=(0, 8))
        ttk.Button(actions_bar, text="📊 View Detailed Reports", style="Secondary.TButton", command=lambda: self.navigate_to("reports")).pack(side="left")

        # Bottom Section: Recent Activity Table
        bottom_frame = tk.Frame(self, bg=COLOR_CONTENT_BG)
        bottom_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        recent_label_frame = tk.Frame(bottom_frame, bg=COLOR_CONTENT_BG)
        recent_label_frame.pack(fill="x", pady=(0, 8))
        tk.Label(recent_label_frame, text="Recent Attendance Activity", font=FONT_SUBTITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left")

        columns = ["date", "class_name", "marked", "present", "absent", "leave", "percentage"]
        headings = ["Date", "Class", "Total Marked", "Present", "Absent", "Leave", "Attendance %"]
        widths = [120, 140, 110, 100, 100, 100, 130]
        aligns = ["c", "w", "c", "c", "c", "c", "c"]

        self.recent_table = CustomTable(bottom_frame, columns, headings, widths, aligns)
        self.recent_table.pack(fill="both", expand=True)

    def _set_today(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self._apply_date()

    def _set_yesterday(self):
        yest = date.today() - timedelta(days=1)
        self.date_var.set(yest.strftime("%Y-%m-%d"))
        self._apply_date()

    def _apply_date(self):
        val = self.date_var.get().strip()
        try:
            self.selected_date = self.att_mgr.validate_date(val)
            self.date_var.set(self.selected_date)
            self.refresh()
        except ValueError:
            self.date_var.set(self.selected_date)

    def _open_add_student(self):
        def save_callback(roll, name, c_name, sec):
            self.student_mgr.add_student(roll, name, c_name, sec)
            self.refresh()
        StudentDialog(self, title="Add New Student", on_save=save_callback)

    def refresh(self):
        """Fetch latest database counts and reload UI."""
        stats = self.att_mgr.get_date_stats(self.selected_date)
        total_st = stats["total_students"]

        self.card_total.update_value(str(total_st), "Total registered in system")
        self.card_present.update_value(str(stats["present_count"]), f"{stats['unmarked_count']} unmarked today")
        self.card_absent.update_value(str(stats["absent_count"]), f"For {self.selected_date}")
        self.card_leave.update_value(str(stats["leave_count"]), "Approved absence leaves")
        self.card_pct.update_value(f"{stats['percentage']}%", "Present / (Present + Absent)")

        for widget in self.banner_frame.winfo_children():
            widget.destroy()

        defaulters = self.reports_mgr.get_attendance_report(only_defaulters=True)
        if defaulters:
            b_box = tk.Frame(self.banner_frame, bg="#FEF2F2", highlightbackground="#F87171", highlightthickness=1, padx=14, pady=8)
            b_box.pack(fill="x")

            tk.Label(
                b_box,
                text=f"⚠️ ATTENDANCE WARNING: {len(defaulters)} student(s) currently fall below the required 75% attendance threshold.",
                font=FONT_HEADING,
                bg="#FEF2F2",
                fg="#991B1B"
            ).pack(side="left")

            ttk.Button(
                b_box,
                text="View Defaulters List",
                style="Danger.TButton",
                command=lambda: self.navigate_to("reports")
            ).pack(side="right")

        self.recent_table.clear()
        recent = self.att_mgr.get_recent_activity(limit=10)
        for r in recent:
            c_name = r["class_name"] or "General / All"
            self.recent_table.insert_row((
                r["attendance_date"],
                c_name,
                r["total_marked"],
                r["present_count"],
                r["absent_count"],
                r["leave_count"],
                f"{r['percentage']}%"
            ))


class StudentsView(tk.Frame):
    """Student management screen."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, navigate_to: Callable[[str], None]):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.navigate_to = navigate_to

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Student Directory", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        self.count_label = tk.Label(title_box, text="Total: 0 registered students", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY)
        self.count_label.pack(anchor="w")

        btn_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="➕ Add Student", style="Primary.TButton", command=self._add_student).pack(side="left", padx=(0, 8))
        ttk.Button(btn_box, text="📥 Bulk Import", style="Success.TButton", command=lambda: self.navigate_to("import")).pack(side="left")

        control_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        control_bar.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(control_bar, text="🔍 Search:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        self.search_entry = ttk.Entry(control_bar, textvariable=self.search_var, width=24, font=FONT_BODY)
        self.search_entry.pack(side="left", padx=(0, 18))

        tk.Label(control_bar, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(control_bar, textvariable=self.class_var, state="readonly", width=12)
        self.class_combo.pack(side="left", padx=(0, 14))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        tk.Label(control_bar, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(control_bar, textvariable=self.sec_var, state="readonly", width=8)
        self.sec_combo.pack(side="left", padx=(0, 18))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        ttk.Button(control_bar, text="Reset Filters", style="Secondary.TButton", command=self._reset_filters).pack(side="left")

        action_sub = tk.Frame(control_bar, bg=COLOR_CARD_BG)
        action_sub.pack(side="right")
        ttk.Button(action_sub, text="✏️ Edit Selected", style="Secondary.TButton", command=self._edit_selected).pack(side="left", padx=(0, 6))
        ttk.Button(action_sub, text="🗑️ Delete Selected", style="Danger.TButton", command=self._delete_selected).pack(side="left")

        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        columns = ["id", "roll_no", "name", "class_name", "section", "created_at"]
        headings = ["ID", "Roll Number", "Student Name", "Class / Dept", "Section", "Registered At"]
        widths = [60, 140, 240, 150, 100, 180]
        aligns = ["c", "w", "w", "w", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Double-1>", lambda e: self._edit_selected())

    def _on_class_change(self):
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._apply_filters()

    def _reset_filters(self):
        self.search_var.set("")
        self.class_var.set("All")
        self.sec_var.set("All")
        self.refresh()

    def _apply_filters(self):
        query = self.search_var.get().strip()
        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()

        students = self.student_mgr.get_all_students(
            search_query=query,
            class_filter=c_filter,
            section_filter=s_filter
        )
        self._populate_table(students)

    def _populate_table(self, students):
        self.table.clear()
        for s in students:
            self.table.insert_row((
                s["id"],
                s["roll_no"],
                s["name"],
                s["class_name"] or "—",
                s["section"] or "—",
                s["created_at"]
            ))

    def _get_selected_student_id(self) -> Optional[int]:
        selected = self.table.tree.selection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select a student from the table first.", parent=self)
            return None
        values = self.table.tree.item(selected[0])["values"]
        return int(values[0])

    def _add_student(self):
        def save_callback(roll, name, c_name, sec):
            self.student_mgr.add_student(roll, name, c_name, sec)
            self.refresh()
            messagebox.showinfo("Success", f"Student '{name}' ({roll}) added successfully.", parent=self)
        StudentDialog(self, title="Add New Student", on_save=save_callback)

    def _edit_selected(self):
        student_id = self._get_selected_student_id()
        if not student_id:
            return

        student = self.student_mgr.get_student_by_id(student_id)
        if not student:
            return

        def save_callback(roll, name, c_name, sec):
            self.student_mgr.update_student(student_id, roll, name, c_name, sec)
            self.refresh()
            messagebox.showinfo("Updated", f"Student '{name}' details updated.", parent=self)

        StudentDialog(self, title="Edit Student", student_data=student, on_save=save_callback)

    def _delete_selected(self):
        student_id = self._get_selected_student_id()
        if not student_id:
            return

        student = self.student_mgr.get_student_by_id(student_id)
        if not student:
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete student:\n\n"
            f"Roll No: {student['roll_no']}\n"
            f"Name: {student['name']}\n\n"
            f"Note: This will also remove all historical attendance records for this student.",
            parent=self
        )
        if confirm:
            self.student_mgr.delete_student(student_id)
            self.refresh()
            messagebox.showinfo("Deleted", "Student and attendance records deleted.", parent=self)

    def refresh(self):
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        total = self.student_mgr.get_total_students_count()
        self.count_label.config(text=f"Total: {total} registered students")
        self._apply_filters()


class AttendanceView(tk.Frame):
    """Attendance marking and modification screen."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, att_mgr: AttendanceManager):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.att_mgr = att_mgr

        self.selected_date = date.today().strftime("%Y-%m-%d")
        self.current_statuses: Dict[int, str] = {}
        self.students_list: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Mark & Manage Attendance", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(title_box, text="Select date and class, toggle student statuses, and save class attendance records.", font=FONT_SMALL, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w")

        ctrl_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        ctrl_card.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(ctrl_card, text="📅 Date:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 6))
        self.date_var = tk.StringVar(value=self.selected_date)
        self.date_entry = ttk.Entry(ctrl_card, textvariable=self.date_var, width=12, font=FONT_BODY)
        self.date_entry.pack(side="left", padx=(0, 4))

        ttk.Button(ctrl_card, text="Today", style="Secondary.TButton", command=self._set_today).pack(side="left", padx=(0, 4))
        ttk.Button(ctrl_card, text="Yesterday", style="Secondary.TButton", command=self._set_yesterday).pack(side="left", padx=(0, 16))

        tk.Label(ctrl_card, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(ctrl_card, textvariable=self.class_var, state="readonly", width=12)
        self.class_combo.pack(side="left", padx=(0, 12))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        tk.Label(ctrl_card, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(ctrl_card, textvariable=self.sec_var, state="readonly", width=8)
        self.sec_combo.pack(side="left", padx=(0, 16))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._load_sheet())

        ttk.Button(ctrl_card, text="🔄 Load / Refresh Sheet", style="Primary.TButton", command=self._load_sheet).pack(side="left")

        sub_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=10, highlightbackground="#E2E8F0", highlightthickness=1)
        sub_bar.pack(fill="x", padx=24, pady=(0, 12))

        tk.Label(sub_bar, text="Quick Actions:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        ttk.Button(sub_bar, text="✔ Mark All Present", style="Success.TButton", command=self._mark_all_present).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="✖ Mark All Absent", style="Danger.TButton", command=self._mark_all_absent).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="Clear All", style="Secondary.TButton", command=self._clear_all).pack(side="left", padx=(0, 16))

        tk.Label(sub_bar, text="Selected Student:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        ttk.Button(sub_bar, text="Present (P)", style="Success.TButton", command=lambda: self._set_selected_status("Present")).pack(side="left", padx=(0, 4))
        ttk.Button(sub_bar, text="Absent (A)", style="Danger.TButton", command=lambda: self._set_selected_status("Absent")).pack(side="left", padx=(0, 4))
        ttk.Button(sub_bar, text="Leave (L)", style="Secondary.TButton", command=lambda: self._set_selected_status("Leave")).pack(side="left", padx=(0, 16))

        self.stats_pill = tk.Label(sub_bar, text="Present: 0 | Absent: 0 | Leave: 0", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY)
        self.stats_pill.pack(side="right")

        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 14))

        columns = ["roll_no", "name", "class_name", "section", "status", "action_hint"]
        headings = ["Roll Number", "Student Name", "Class", "Section", "Attendance Status", "Quick Toggle"]
        widths = [140, 240, 140, 90, 160, 200]
        aligns = ["w", "w", "w", "c", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)

        self.table.tree.bind("<Double-1>", self._cycle_status_event)
        self.table.tree.bind("<space>", self._cycle_status_event)

        bottom_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=14, highlightbackground="#CBD5E1", highlightthickness=1)
        bottom_bar.pack(fill="x", padx=24, pady=(0, 18))

        self.save_status_lbl = tk.Label(bottom_bar, text="Changes not saved yet", font=FONT_BODY, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY)
        self.save_status_lbl.pack(side="left")

        self.save_btn = ttk.Button(bottom_bar, text="💾 Save Attendance for Class", style="Primary.TButton", command=self._save_attendance)
        self.save_btn.pack(side="right")

    def _set_today(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self._load_sheet()

    def _set_yesterday(self):
        yest = date.today() - timedelta(days=1)
        self.date_var.set(yest.strftime("%Y-%m-%d"))
        self._load_sheet()

    def _on_class_change(self):
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._load_sheet()

    def _load_sheet(self):
        try:
            self.selected_date = self.att_mgr.validate_date(self.date_var.get().strip())
            self.date_var.set(self.selected_date)
        except ValueError as e:
            messagebox.showerror("Invalid Date", str(e), parent=self)
            return

        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()

        self.students_list = self.att_mgr.get_attendance_sheet(
            attendance_date=self.selected_date,
            class_name=c_filter,
            section=s_filter
        )

        self.current_statuses = {}
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = s.get("status")

        has_existing, count = self.att_mgr.has_attendance_for_date(self.selected_date, c_filter, s_filter)
        if has_existing:
            self.save_status_lbl.config(text=f"Loaded existing attendance records ({count} marked for {self.selected_date})", fg=COLOR_PRIMARY)
        else:
            self.save_status_lbl.config(text=f"No saved attendance records yet for {self.selected_date}. Mark and save below.", fg=COLOR_TEXT_SECONDARY)

        self._render_table()

    def _render_table(self):
        self.table.clear()
        p_count = 0
        a_count = 0
        l_count = 0

        for s in self.students_list:
            sid = s["student_id"]
            st = self.current_statuses.get(sid)

            if st == "Present":
                tag = "status_valid"
                display_st = "✅ Present"
                p_count += 1
            elif st == "Absent":
                tag = "status_danger"
                display_st = "❌ Absent"
                a_count += 1
            elif st == "Leave":
                tag = "status_warning"
                display_st = "🌴 Leave"
                l_count += 1
            else:
                tag = "even"
                display_st = "⚪ Unmarked"

            self.table.insert_row(
                (
                    s["roll_no"],
                    s["name"],
                    s["class_name"] or "—",
                    s["section"] or "—",
                    display_st,
                    "Double-click to toggle"
                ),
                tags=(tag,)
            )

        total_marked = p_count + a_count + l_count
        rate = round((p_count / (p_count + a_count) * 100.0), 1) if (p_count + a_count) > 0 else 0.0
        self.stats_pill.config(
            text=f"Present: {p_count}  |  Absent: {a_count}  |  Leave: {l_count}  |  Total: {len(self.students_list)}  (Rate: {rate}%)"
        )

    def _cycle_status_event(self, event=None):
        sel = self.table.tree.selection()
        if not sel:
            return

        idx = self.table.tree.index(sel[0])
        if idx >= len(self.students_list):
            return

        sid = self.students_list[idx]["student_id"]
        current = self.current_statuses.get(sid)

        cycle_map = {
            None: "Present",
            "Present": "Absent",
            "Absent": "Leave",
            "Leave": "Present"
        }
        self.current_statuses[sid] = cycle_map.get(current, "Present")
        self._render_table()

        items = self.table.tree.get_children()
        if idx < len(items):
            self.table.tree.selection_set(items[idx])

    def _set_selected_status(self, new_status: str):
        sel = self.table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Please select a student row first.", parent=self)
            return

        for item in sel:
            idx = self.table.tree.index(item)
            if idx < len(self.students_list):
                sid = self.students_list[idx]["student_id"]
                self.current_statuses[sid] = new_status

        self._render_table()

    def _mark_all_present(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = "Present"
        self._render_table()

    def _mark_all_absent(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = "Absent"
        self._render_table()

    def _clear_all(self):
        for s in self.students_list:
            self.current_statuses[s["student_id"]] = None
        self._render_table()

    def _save_attendance(self):
        if not self.students_list:
            messagebox.showwarning("No Students", "No students available to mark attendance for.", parent=self)
            return

        records_to_save = []
        unmarked_names = []
        for s in self.students_list:
            st = self.current_statuses.get(s["student_id"])
            if st:
                records_to_save.append({"student_id": s["student_id"], "status": st})
            else:
                unmarked_names.append(s["name"])

        if not records_to_save:
            messagebox.showwarning("No Attendance Marked", "Please mark attendance (Present, Absent, or Leave) for at least one student before saving.", parent=self)
            return

        if unmarked_names:
            cont = messagebox.askyesno(
                "Unmarked Students",
                f"{len(unmarked_names)} student(s) remain unmarked.\n\n"
                f"Do you want to save attendance for the {len(records_to_save)} marked students?",
                parent=self
            )
            if not cont:
                return

        has_existing, count = self.att_mgr.has_attendance_for_date(
            self.selected_date,
            self.class_var.get(),
            self.sec_var.get()
        )
        if has_existing:
            overwrite = messagebox.askyesno(
                "Overwrite Existing Attendance?",
                f"Attendance records already exist for {self.selected_date} ({count} existing records).\n\n"
                f"Saving will update and replace previously recorded attendance for this class.\n"
                f"Do you wish to proceed?",
                parent=self
            )
            if not overwrite:
                return

        try:
            saved_count = self.att_mgr.save_batch_attendance(
                attendance_date=self.selected_date,
                records=records_to_save,
                overwrite=True
            )
            self.save_status_lbl.config(text=f"✅ Saved {saved_count} records for {self.selected_date}", fg=COLOR_SUCCESS)
            messagebox.showinfo("Saved", f"Successfully saved attendance for {saved_count} student(s) on {self.selected_date}.", parent=self)
            self._load_sheet()
        except Exception as e:
            messagebox.showerror("Error Saving Attendance", f"Failed to save attendance: {str(e)}", parent=self)

    def refresh(self):
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        self._load_sheet()


class ReportsView(tk.Frame):
    """Attendance reports, analytics, and CSV exporter."""

    def __init__(self, parent, db: Database, student_mgr: StudentManager, reports_mgr: ReportsManager):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.db = db
        self.student_mgr = student_mgr
        self.reports_mgr = reports_mgr

        self.current_report_data: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = tk.Frame(self, bg=COLOR_CONTENT_BG)
        header.pack(fill="x", padx=24, pady=(20, 14))

        title_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        title_box.pack(side="left")

        tk.Label(title_box, text="Attendance Reports & Analytics", font=FONT_TITLE, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(
            title_box,
            text=f"Formula: Present / (Present + Absent) × 100 | Defaulter threshold: < {ATTENDANCE_DEFICIT_THRESHOLD}%",
            font=FONT_SMALL,
            bg=COLOR_CONTENT_BG,
            fg=COLOR_TEXT_SECONDARY
        ).pack(anchor="w")

        btn_box = tk.Frame(header, bg=COLOR_CONTENT_BG)
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="📥 Export Filtered Report to CSV", style="Success.TButton", command=self._export_csv).pack(side="left")

        cards_box = tk.Frame(self, bg=COLOR_CONTENT_BG)
        cards_box.pack(fill="x", padx=24, pady=(0, 14))
        cards_box.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="rep_cards")

        self.card_total_students = StatCard(cards_box, title="Reported Students", value="0", icon="👥", accent_color=COLOR_PRIMARY)
        self.card_total_students.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.card_avg_pct = StatCard(cards_box, title="Average Attendance", value="0.0%", icon="📈", accent_color=COLOR_SUCCESS)
        self.card_avg_pct.grid(row=0, column=1, sticky="ew", padx=4)

        self.card_defaulters = StatCard(cards_box, title="Students < 75%", value="0", icon="⚠️", accent_color=COLOR_DANGER)
        self.card_defaulters.grid(row=0, column=2, sticky="ew", padx=4)

        self.card_total_days = StatCard(cards_box, title="Total Days Tracked", value="0", icon="📅", accent_color="#6366F1")
        self.card_total_days.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        ctrl_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground="#E2E8F0", highlightthickness=1)
        ctrl_card.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(ctrl_card, text="🔍 Search:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        self.search_entry = ttk.Entry(ctrl_card, textvariable=self.search_var, width=16, font=FONT_BODY)
        self.search_entry.pack(side="left", padx=(0, 14))

        tk.Label(ctrl_card, text="Class:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.class_var = tk.StringVar(value="All")
        self.class_combo = ttk.Combobox(ctrl_card, textvariable=self.class_var, state="readonly", width=10)
        self.class_combo.pack(side="left", padx=(0, 10))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self._on_class_change())

        tk.Label(ctrl_card, text="Section:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.sec_var = tk.StringVar(value="All")
        self.sec_combo = ttk.Combobox(ctrl_card, textvariable=self.sec_var, state="readonly", width=7)
        self.sec_combo.pack(side="left", padx=(0, 14))
        self.sec_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        tk.Label(ctrl_card, text="From:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.start_date_var = tk.StringVar()
        self.start_date_entry = ttk.Entry(ctrl_card, textvariable=self.start_date_var, width=11, font=FONT_BODY)
        self.start_date_entry.pack(side="left", padx=(0, 10))

        tk.Label(ctrl_card, text="To:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.end_date_var = tk.StringVar()
        self.end_date_entry = ttk.Entry(ctrl_card, textvariable=self.end_date_var, width=11, font=FONT_BODY)
        self.end_date_entry.pack(side="left", padx=(0, 14))

        self.defaulters_var = tk.BooleanVar(value=False)
        self.defaulter_check = ttk.Checkbutton(ctrl_card, text="⚠️ Only < 75% Defaulters", variable=self.defaulters_var, command=self._apply_filters)
        self.defaulter_check.pack(side="left", padx=(0, 14))

        ttk.Button(ctrl_card, text="Apply Filter", style="Primary.TButton", command=self._apply_filters).pack(side="left", padx=(0, 6))
        ttk.Button(ctrl_card, text="Reset", style="Secondary.TButton", command=self._reset_filters).pack(side="left")

        table_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        table_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        columns = ["roll_no", "name", "class_name", "section", "total_days", "present_days", "absent_days", "leave_days", "percentage", "status"]
        headings = ["Roll Number", "Student Name", "Class", "Section", "Days Recorded", "Present", "Absent", "Leave", "Attendance %", "Status"]
        widths = [120, 210, 110, 80, 110, 80, 80, 80, 120, 140]
        aligns = ["w", "w", "w", "c", "c", "c", "c", "c", "c", "c"]

        self.table = CustomTable(table_container, columns, headings, widths, aligns)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Double-1>", lambda e: self._view_student_history())

    def _on_class_change(self):
        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections
        self.sec_var.set("All")
        self._apply_filters()

    def _reset_filters(self):
        self.search_var.set("")
        self.class_var.set("All")
        self.sec_var.set("All")
        self.start_date_var.set("")
        self.end_date_var.set("")
        self.defaulters_var.set(False)
        self.refresh()

    def _apply_filters(self):
        query = self.search_var.get().strip()
        c_filter = self.class_var.get()
        s_filter = self.sec_var.get()
        s_date = self.start_date_var.get().strip() or None
        e_date = self.end_date_var.get().strip() or None
        only_def = self.defaulters_var.get()

        self.current_report_data = self.reports_mgr.get_attendance_report(
            class_filter=c_filter,
            section_filter=s_filter,
            start_date=s_date,
            end_date=e_date,
            search_query=query,
            only_defaulters=only_def
        )

        self._render_table()

    def _render_table(self):
        self.table.clear()
        total_students = len(self.current_report_data)
        pct_sum = 0.0
        students_with_history = 0
        defaulter_count = 0
        max_days = 0

        for r in self.current_report_data:
            if r["has_history"]:
                pct_sum += r["percentage"]
                students_with_history += 1
            if r["is_low"]:
                defaulter_count += 1
            if r["total_days"] > max_days:
                max_days = r["total_days"]

            tag = "defaulter" if r["is_low"] else ("even" if not r["has_history"] else "status_valid")

            self.table.insert_row(
                (
                    r["roll_no"],
                    r["name"],
                    r["class_name"] or "—",
                    r["section"] or "—",
                    r["total_days"],
                    r["present_days"],
                    r["absent_days"],
                    r["leave_days"],
                    f"{r['percentage']}%",
                    "⚠️ DEFICIT (<75%)" if r["is_low"] else ("Satisfactory" if r["has_history"] else "No Records")
                ),
                tags=(tag,)
            )

        avg_pct = round(pct_sum / students_with_history, 1) if students_with_history > 0 else 0.0
        self.card_total_students.update_value(str(total_students), f"{students_with_history} with attendance history")
        self.card_avg_pct.update_value(f"{avg_pct}%", "Average of active students")
        self.card_defaulters.update_value(str(defaulter_count), "Attendance below 75%")
        self.card_total_days.update_value(str(max_days), "Max days marked in filter")

    def _view_student_history(self):
        sel = self.table.tree.selection()
        if not sel:
            messagebox.showinfo("Select Student", "Please select a student to view their history log.", parent=self)
            return

        idx = self.table.tree.index(sel[0])
        if idx >= len(self.current_report_data):
            return

        student = self.current_report_data[idx]
        history = self.reports_mgr.get_student_history(student["student_id"])

        top = tk.Toplevel(self)
        top.title(f"Attendance Log — {student['name']} ({student['roll_no']})")
        top.geometry("540x450")
        top.configure(bg=COLOR_CONTENT_BG)

        f = tk.Frame(top, bg=COLOR_CARD_BG, padx=20, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text=f"{student['name']} ({student['roll_no']})", font=FONT_TITLE, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
        tk.Label(f, text=f"Class: {student['class_name']} {student['section']} | Overall Attendance: {student['percentage']}%", font=FONT_BODY, bg=COLOR_CARD_BG, fg=COLOR_TEXT_SECONDARY).pack(anchor="w", pady=(0, 12))

        hist_table = CustomTable(f, columns=["date", "day", "status"], headings=["Date", "Day of Week", "Attendance Status"], col_widths=[120, 140, 140], col_aligns=["c", "w", "c"])
        hist_table.pack(fill="both", expand=True, pady=(0, 10))

        for h in history:
            tag = "status_valid" if h["status"] == "Present" else ("status_danger" if h["status"] == "Absent" else "status_warning")
            hist_table.insert_row((h["attendance_date"], h.get("day_name", ""), h["status"]), tags=(tag,))

        ttk.Button(f, text="Close", style="Secondary.TButton", command=top.destroy).pack(side="right")

    def _export_csv(self):
        if not self.current_report_data:
            messagebox.showwarning("No Data", "There is no report data to export.", parent=self)
            return

        dest = filedialog.asksaveasfilename(
            title="Export Attendance Report to CSV",
            defaultextension=".csv",
            initialfile="attendance_report.csv",
            filetypes=[("CSV Files", "*.csv")]
        )
        if not dest:
            return

        try:
            self.reports_mgr.export_report_to_csv(dest, self.current_report_data)
            messagebox.showinfo("Export Successful", f"Report successfully exported to:\n{dest}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export CSV: {str(e)}", parent=self)

    def refresh(self):
        classes = ["All"] + self.student_mgr.get_distinct_classes()
        self.class_combo["values"] = classes

        selected_class = self.class_var.get()
        sections = ["All"] + self.student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        self.sec_combo["values"] = sections

        self._apply_filters()


class ImportView(tk.Frame):
    """Faculty-friendly guided bulk import wizard."""

    def __init__(self, parent, importer: BulkImportManager, on_import_success: Callable[[], None]):
        super().__init__(parent, bg=COLOR_CONTENT_BG)
        self.importer = importer
        self.on_import_success = on_import_success

        self.selected_file_path: Optional[Path] = None
        self.current_summary: Dict[str, int] = {}
        self.templates_dir = TEMPLATES_DIR

        self._build_ui()

    def _build_ui(self):
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

        tmpl_bar = tk.Frame(self, bg=COLOR_CONTENT_BG)
        tmpl_bar.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(tmpl_bar, text="Sample Templates:", font=FONT_HEADING, bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        ttk.Button(tmpl_bar, text="📥 Download CSV Template", style="Secondary.TButton", command=self._export_csv_template).pack(side="left", padx=(0, 6))
        ttk.Button(tmpl_bar, text="📝 Create TXT Template", style="Secondary.TButton", command=self._export_txt_template).pack(side="left", padx=(0, 6))
        ttk.Button(tmpl_bar, text="📄 View Supported PDF Formats", style="Secondary.TButton", command=self._show_pdf_help).pack(side="left")

        self.upload_card = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=16, highlightbackground="#CBD5E1", highlightthickness=1)
        self.upload_card.pack(fill="x", padx=24, pady=(0, 14))

        upload_inner = tk.Frame(self.upload_card, bg=COLOR_CARD_BG)
        upload_inner.pack(fill="x")

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

        btn_box = tk.Frame(upload_inner, bg=COLOR_CARD_BG)
        btn_box.pack(side="right")

        self.browse_btn = ttk.Button(btn_box, text="Browse & Select File...", style="Primary.TButton", command=self._browse_file)
        self.browse_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ttk.Button(btn_box, text="Clear", style="Secondary.TButton", command=self._clear_all)
        self.clear_btn.pack(side="left")

        self.summary_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=16, pady=10, highlightbackground="#E2E8F0", highlightthickness=1)
        self.summary_bar.pack(fill="x", padx=24, pady=(0, 10))

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

        tbl_actions = tk.Frame(self.summary_bar, bg=COLOR_CARD_BG)
        tbl_actions.pack(side="right")

        ttk.Button(tbl_actions, text="Select All Valid", style="Secondary.TButton", command=self._select_all_valid).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="Deselect All", style="Secondary.TButton", command=self._deselect_all).pack(side="left", padx=(0, 6))
        ttk.Button(tbl_actions, text="✏️ Edit Record", style="Secondary.TButton", command=self._edit_selected_row).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="🗑️ Remove", style="Danger.TButton", command=self._remove_selected_row).pack(side="left", padx=(0, 4))
        ttk.Button(tbl_actions, text="🔍 Raw Text", style="Secondary.TButton", command=self._view_raw_text).pack(side="left")

        preview_container = tk.Frame(self, bg=COLOR_CONTENT_BG)
        preview_container.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        columns = ["selected", "roll_no", "name", "class_name", "section", "status", "details"]
        headings = ["Import?", "Roll Number", "Student Name", "Class", "Section", "Validation Status", "Details / Diagnosis"]
        widths = [70, 120, 200, 100, 70, 150, 240]
        aligns = ["c", "w", "w", "w", "c", "c", "w"]

        self.preview_table = CustomTable(preview_container, columns, headings, widths, aligns)
        self.preview_table.pack(fill="both", expand=True)

        self.preview_table.tree.bind("<ButtonRelease-1>", self._on_table_click)
        self.preview_table.tree.bind("<Double-1>", lambda e: self._edit_selected_row())

        bottom_bar = tk.Frame(self, bg=COLOR_CARD_BG, padx=20, pady=14, highlightbackground="#CBD5E1", highlightthickness=1)
        bottom_bar.pack(fill="x", padx=24, pady=(0, 18))

        dup_frame = tk.Frame(bottom_bar, bg=COLOR_CARD_BG)
        dup_frame.pack(side="left")

        tk.Label(dup_frame, text="Duplicate Handling Option:", font=FONT_HEADING, bg=COLOR_CARD_BG, fg=COLOR_TEXT_PRIMARY).pack(anchor="w")

        self.dup_action_var = tk.StringVar(value="skip")
        r1 = ttk.Radiobutton(dup_frame, text="Skip duplicates (safely add only new students)", variable=self.dup_action_var, value="skip")
        r1.pack(side="left", padx=(0, 16))
        r2 = ttk.Radiobutton(dup_frame, text="Update existing students with details from file", variable=self.dup_action_var, value="update")
        r2.pack(side="left")

        exec_box = tk.Frame(bottom_bar, bg=COLOR_CARD_BG)
        exec_box.pack(side="right")

        self.import_btn = ttk.Button(exec_box, text="✅ Confirm & Import Students", style="Success.TButton", command=self._execute_import)
        self.import_btn.pack(side="right", padx=(8, 0))

        ttk.Button(exec_box, text="Cancel Import", style="Secondary.TButton", command=self._clear_all).pack(side="right")

    def _browse_file(self):
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
        res = self.importer.load_file(path)

        if not res["success"]:
            if res.get("is_scanned_pdf"):
                messagebox.showerror("Scanned PDF Detected", res["error"], parent=self)
            else:
                messagebox.showerror("Import Error", res["error"], parent=self)
            self._clear_all()
            return

        size_kb = path.stat().st_size / 1024
        self.file_status_title.config(text=f"📄 Selected File: {path.name} ({size_kb:.1f} KB)")
        self.file_status_desc.config(text=f"Format: {path.suffix.upper()} | Path: {path}")

        self._render_preview()

    def _render_preview(self):
        self.preview_table.clear()
        records = self.importer.current_records
        summary = self.importer.validate_records()
        self.current_summary = summary

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
        region = self.preview_table.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return

        item = self.preview_table.tree.identify_row(event.y)
        col = self.preview_table.tree.identify_column(event.x)
        if not item:
            return

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


# =====================================================================
# SECTION 8: APPLICATION CONTROLLER AND ENTRY POINT
# =====================================================================

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
        for name, view in self.views.items():
            if hasattr(view, "refresh"):
                view.refresh()
        self.show_view("students")

    def show_view(self, view_name: str):
        """Switch active view and update sidebar styling."""
        if view_name not in self.views:
            return

        self.active_view_name = view_name

        for key, (frame, label) in self.nav_buttons.items():
            if key == view_name:
                frame.configure(bg=COLOR_SIDEBAR_ACTIVE)
                label.configure(bg=COLOR_SIDEBAR_ACTIVE, fg="#FFFFFF", font=FONT_NAV_ACTIVE)
            else:
                frame.configure(bg=COLOR_SIDEBAR_BG)
                label.configure(bg=COLOR_SIDEBAR_BG, fg=COLOR_SIDEBAR_MUTED, font=FONT_NAV)

        for name, view_widget in self.views.items():
            if name == view_name:
                view_widget.pack(fill="both", expand=True)
                if hasattr(view_widget, "refresh"):
                    view_widget.refresh()
            else:
                view_widget.pack_forget()


def main():
    """Main application launcher."""
    root = tk.Tk()
    app = AttendanceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
