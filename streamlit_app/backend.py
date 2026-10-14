"""
Backend business logic for Streamlit Student Attendance Tracker.
Contains 100% of the decoupled core logic:
- SQLite Database & Transactions
- Student Management (CRUD, duplicate validation)
- Document Parsing (PDF, CSV, TXT, Excel, Scanned PDF detection)
- Attendance Engine (Marking, UPSERT, percentage formula excluding leaves)
- Reports Engine (Defaulter threshold <75%, history logs, CSV exporter)
- Demo data seeder for Cloud evaluation
"""

import csv
import re
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, List, Tuple, Optional, Dict, Set
from contextlib import contextmanager

# Third-party document parsing dependencies
import pypdf

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BACKEND_DIR / "attendance_tracker.db"
TEMPLATES_DIR = BACKEND_DIR / "templates"

# Business Logic Rules
ATTENDANCE_DEFICIT_THRESHOLD = 75.0
VALID_STATUSES = {"Present", "Absent", "Leave"}

# Column Identifiers for Import
COL_ROLL = "roll_no"
COL_NAME = "name"
COL_CLASS = "class_name"
COL_SECTION = "section"

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


class Database:
    """Manages SQLite database connections and transactions."""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Create a connection with foreign keys enabled and row factory configured."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self):
        """Context manager for atomic operations with automatic commit/rollback."""
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
        """Execute an INSERT/UPDATE/DELETE query and return lastrowid."""
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


class DuplicateRollNumberError(Exception):
    """Raised when attempting to add/update a student with an existing roll number."""
    pass


class ValidationError(Exception):
    """Raised when required fields are missing or invalid."""
    pass


class StudentManager:
    """Handles student CRUD operations, searching, filtering, and validation."""

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
        """Delete a student and cascade delete their attendance records."""
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
        """Retrieve students with search, class/section filtering, and dynamic column sorting."""
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
        """Fetch set of all existing roll numbers (uppercase) for fast bulk validation."""
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
        self.has_tesseract = shutil.which("tesseract") is not None

    def parse_pdf(self, file_path_or_bytes: str | Path | Any) -> PDFParseResult:
        """
        Main entry point to parse a PDF file into student records.
        Supports file paths and in-memory binary streams (e.g. Streamlit UploadedFile).
        """
        result = PDFParseResult()
        result.ocr_available = self.has_tesseract

        try:
            reader = pypdf.PdfReader(file_path_or_bytes)
            result.page_count = len(reader.pages)

            if result.page_count == 0:
                result.success = False
                result.error_message = "The selected PDF file contains 0 pages."
                return result

            all_extracted_text: List[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                all_extracted_text.append(page_text)

            combined_text = "\n".join(all_extracted_text)
            result.raw_text = combined_text

            cleaned_text = re.sub(r"\s+", "", combined_text)
            if len(cleaned_text) < 15:
                result.is_scanned = True
                result.success = False
                msg = (
                    "This PDF appears to be a scanned document or contains images rather than selectable text. "
                    "pypdf could not extract readable characters.\n\n"
                    "• Cause: Scanned document / image-only PDF.\n"
                    "• Resolution: Please use an exported text-based PDF, CSV, or TXT file."
                )
                if self.has_tesseract:
                    msg += "\n• Note: Tesseract OCR is detected, but automated OCR for image-only scans requires high-contrast scans."
                else:
                    msg += "\n• Note: Tesseract OCR is not installed. To parse scanned images, install Tesseract OCR or convert your document to CSV."
                result.error_message = msg
                return result

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
        students: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        lines = text.splitlines()

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
            if any(re.search(pat, lower_line) for pat in header_patterns):
                continue

            kv_record = self._try_parse_key_value_line(raw_line)
            if kv_record:
                students.append(kv_record)
                continue

            delim_record = self._try_parse_delimited_line(raw_line)
            if delim_record:
                students.append(delim_record)
                continue

            tab_record = self._try_parse_tabular_line(raw_line)
            if tab_record:
                students.append(tab_record)
                continue

            if any(c.isalnum() for c in raw_line):
                unparsed.append({
                    "line_num": line_idx,
                    "text": raw_line,
                    "reason": "Could not identify distinct Roll Number and Student Name"
                })

        return students, unparsed

    def _try_parse_key_value_line(self, line: str) -> Optional[Dict[str, str]]:
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
        for sep in ["|", "\t", ";"]:
            if sep in line:
                parts = [p.strip() for p in line.split(sep) if p.strip()]
                if len(parts) >= 2:
                    return self._map_columns_to_student(parts)
        return None

    def _try_parse_tabular_line(self, line: str) -> Optional[Dict[str, str]]:
        parts = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        if len(parts) >= 2:
            return self._map_columns_to_student(parts)

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
        first_token = parts[0].strip()
        second_token = parts[1].strip()

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

        roll_no = first_token
        name = second_token
        class_name = parts[2].strip() if len(parts) > 2 else ""
        section = parts[3].strip() if len(parts) > 3 else ""

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


class ImportValidationStatus:
    VALID = "Valid"
    DUP_IN_FILE = "Duplicate in File"
    DUP_IN_DB = "Exists in Database"
    MISSING_ROLL = "Missing Roll No"
    MISSING_NAME = "Missing Name"
    INVALID = "Invalid Row"


class BulkImportManager:
    """Manages bulk student imports across CSV, TXT, PDF, and XLSX formats."""

    def __init__(self, db: Database, student_manager: StudentManager):
        self.db = db
        self.student_manager = student_manager
        self.pdf_parser = PDFParser()
        self.current_records: List[Dict[str, Any]] = []
        self.unparsed_items: List[Dict[str, Any]] = []
        self.raw_text_preview: str = ""

    def load_file_content(self, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        """Load and parse file bytes directly from an upload widget."""
        self.current_records = []
        self.unparsed_items = []
        self.raw_text_preview = ""

        ext = Path(file_name).suffix.lower()
        extracted: List[Dict[str, str]] = []
        parse_error: Optional[str] = None
        is_scanned_pdf = False
        raw_text_preview = ""

        try:
            if ext == ".csv":
                extracted, self.unparsed_items = self._parse_csv_bytes(file_bytes)
            elif ext == ".txt":
                extracted, self.unparsed_items = self._parse_txt_bytes(file_bytes)
            elif ext == ".pdf":
                import io
                pdf_res = self.pdf_parser.parse_pdf(io.BytesIO(file_bytes))
                if not pdf_res.success:
                    is_scanned_pdf = pdf_res.is_scanned
                    parse_error = pdf_res.error_message
                extracted = pdf_res.students
                self.unparsed_items = pdf_res.unparsed_lines
                raw_text_preview = pdf_res.raw_text
            elif ext in (".xlsx", ".xls"):
                if not HAS_OPENPYXL:
                    return {"success": False, "error": "openpyxl is not installed.", "records": [], "summary": {}}
                extracted, self.unparsed_items = self._parse_excel_bytes(file_bytes)
            else:
                return {"success": False, "error": f"Unsupported format '{ext}'.", "records": [], "summary": {}}

        except Exception as e:
            return {"success": False, "error": f"Failed to parse file: {str(e)}", "records": [], "summary": {}}

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

        self.current_records = []
        for idx, rec in enumerate(extracted, 1):
            self.current_records.append({
                "id": idx,
                "selected": True,
                "roll_no": str(rec.get("roll_no", "")).strip(),
                "name": str(rec.get("name", "")).strip(),
                "class_name": str(rec.get("class_name", "")).strip(),
                "section": str(rec.get("section", "")).strip().upper(),
                "status": ImportValidationStatus.VALID,
                "status_code": "VALID",
                "details": "Ready for import"
            })

        summary = self.validate_records()

        return {
            "success": True,
            "file_name": file_name,
            "records": self.current_records,
            "unparsed_items": self.unparsed_items,
            "summary": summary,
            "raw_text": raw_text_preview,
            "error": parse_error
        }

    def validate_records(self) -> Dict[str, int]:
        existing_db_rolls = self.student_manager.get_existing_roll_numbers()

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

    def execute_import(self, duplicate_action: str = "skip") -> Dict[str, Any]:
        selected_records = [r for r in self.current_records if r["selected"]]

        if not selected_records:
            return {
                "success": False,
                "error": "No records are selected for import.",
                "added": 0, "updated": 0, "skipped": 0, "failed": 0
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
                        errors.append(f"Skipped record missing roll or name: {rec}")
                        continue

                    roll_key = roll.upper()

                    if roll_key in existing_students:
                        if duplicate_action == "update":
                            cursor.execute("""
                                UPDATE students
                                SET name = ?, class_name = ?, section = ?
                                WHERE roll_no = ? COLLATE NOCASE;
                            """, (name, c_name, sec, roll))
                            updated_count += 1
                        else:
                            skipped_count += 1
                    else:
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
            return {
                "success": False,
                "error": f"Database transaction failed: {str(e)}",
                "added": 0, "updated": 0, "skipped": 0, "failed": len(selected_records)
            }

    def _parse_csv_bytes(self, data: bytes) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        records: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        text = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return records, unparsed

        reader = list(csv.reader(lines))
        if not reader:
            return records, unparsed

        header_idx, col_map = self._detect_csv_headers(reader)
        start_row = header_idx + 1 if header_idx is not None else 0

        for row_num, row in enumerate(reader[start_row:], start=start_row + 1):
            if not any(cell.strip() for cell in row):
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
                unparsed.append({"line_num": row_num, "text": ",".join(row), "reason": "Empty row or missing identifiers"})

        return records, unparsed

    def _parse_txt_bytes(self, data: bytes) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        records: List[Dict[str, str]] = []
        unparsed: List[Dict[str, Any]] = []

        text = ""
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                text = data.decode(encoding)
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

            kv_match = self.pdf_parser._try_parse_key_value_line(raw)
            if kv_match:
                records.append(kv_match)
                continue

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

    def _parse_excel_bytes(self, data: bytes) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        import io
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active

        rows: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
            if any(cleaned_row):
                rows.append(cleaned_row)
        wb.close()

        if not rows:
            return [], []

        header_idx, col_map = self._detect_csv_headers(rows)
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

    def _detect_csv_headers(self, rows: List[List[str]]) -> Tuple[Optional[int], Dict[str, int]]:
        col_map: Dict[str, int] = {}
        header_row_idx: Optional[int] = None

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


class AttendanceManager:
    """Attendance marking, modification, date stats, and historical tracking."""

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
        date_str = self.validate_date(attendance_date)

        if not records:
            return 0

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


class ReportsManager:
    """Calculates attendance metrics, identifies defaulters (<75%), and exports CSV reports."""

    def __init__(self, db: Database):
        self.db = db

    def calculate_attendance_percentage(self, present_days: int, absent_days: int) -> float:
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

    def generate_csv_string(self, report_data: List[Dict[str, Any]]) -> str:
        """Returns CSV formatted string for direct Streamlit download button."""
        import io
        output = io.StringIO()
        writer = csv.writer(output)

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

        return output.getvalue()


def seed_demo_data(db: Database, sm: StudentManager, am: AttendanceManager) -> None:
    """Pre-seeds sample students and attendance for quick college project evaluation."""
    sample_students = [
        ("2026-CSE-001", "Aarav Sharma", "CSE", "A"),
        ("2026-CSE-002", "Ananya Verma", "CSE", "A"),
        ("2026-CSE-003", "Rohan Gupta", "CSE", "A"),
        ("2026-CSE-004", "Pooja Patel", "CSE", "A"),
        ("2026-CSE-005", "Vikram Singh", "CSE", "A"),
        ("2026-CSE-006", "Sneha Joshi", "CSE", "B"),
        ("2026-CSE-007", "Karan Malhotra", "CSE", "B"),
        ("2026-CSE-008", "Diya Nair", "CSE", "B"),
        ("2026-ECE-101", "Aditya Iyer", "ECE", "A"),
        ("2026-ECE-102", "Ishita Reddy", "ECE", "A"),
        ("2026-ECE-103", "Kabir Sen", "ECE", "A"),
        ("2026-ECE-104", "Meera Kulkarni", "ECE", "A"),
    ]

    for roll, name, c_name, sec in sample_students:
        try:
            sm.add_student(roll, name, c_name, sec)
        except DuplicateRollNumberError:
            pass

    # Fetch IDs
    st_map = sm.get_existing_students_map()
    s1 = st_map.get("2026-CSE-001", {}).get("id")
    s2 = st_map.get("2026-CSE-002", {}).get("id")
    s3 = st_map.get("2026-CSE-003", {}).get("id")  # Low attendance demo
    s4 = st_map.get("2026-CSE-004", {}).get("id")
    s5 = st_map.get("2026-CSE-005", {}).get("id")

    today = date.today()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4, -1, -1)]

    # Mark attendance over the last 5 days
    if s1 and s2 and s3 and s4 and s5:
        # Day 1
        am.save_batch_attendance(dates[0], [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Present"},
            {"student_id": s3, "status": "Absent"},
            {"student_id": s4, "status": "Present"},
            {"student_id": s5, "status": "Leave"},
        ])
        # Day 2
        am.save_batch_attendance(dates[1], [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Present"},
            {"student_id": s3, "status": "Absent"},
            {"student_id": s4, "status": "Leave"},
            {"student_id": s5, "status": "Present"},
        ])
        # Day 3
        am.save_batch_attendance(dates[2], [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Absent"},
            {"student_id": s3, "status": "Absent"},
            {"student_id": s4, "status": "Present"},
            {"student_id": s5, "status": "Present"},
        ])
        # Day 4
        am.save_batch_attendance(dates[3], [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Present"},
            {"student_id": s3, "status": "Present"},
            {"student_id": s4, "status": "Present"},
            {"student_id": s5, "status": "Present"},
        ])
        # Day 5 (Today)
        am.save_batch_attendance(dates[4], [
            {"student_id": s1, "status": "Present"},
            {"student_id": s2, "status": "Present"},
            {"student_id": s3, "status": "Absent"},  # Total s3: 1 Present, 4 Absent -> 20% defaulter
            {"student_id": s4, "status": "Present"},
            {"student_id": s5, "status": "Present"},
        ])
