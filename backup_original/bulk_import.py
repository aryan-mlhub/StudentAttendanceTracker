"""
Bulk Import Engine for Student Attendance Tracker.
Orchestrates file reading (CSV, TXT, PDF, XLSX), smart column mapping,
in-memory validation, duplicate conflict resolution, preview editing, and atomic SQLite insertion.
"""

import csv
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from database import Database
from student_manager import StudentManager
from pdf_parser import PDFParser, PDFParseResult

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# Canonical column keys
COL_ROLL = "roll_no"
COL_NAME = "name"
COL_CLASS = "class_name"
COL_SECTION = "section"

# Common header synonyms
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


class ImportValidationStatus:
    VALID = "Valid"
    DUP_IN_FILE = "Duplicate in File"
    DUP_IN_DB = "Exists in Database"
    MISSING_ROLL = "Missing Roll No"
    MISSING_NAME = "Missing Name"
    INVALID = "Invalid Row"


class BulkImportManager:
    """Manages the full lifecycle of student bulk imports."""

    def __init__(self, db: Database, student_manager: StudentManager):
        self.db = db
        self.student_manager = student_manager
        self.pdf_parser = PDFParser()
        self.current_records: List[Dict[str, Any]] = []
        self.file_path: Optional[Path] = None
        self.unparsed_items: List[Dict[str, Any]] = []

    def load_file(self, file_path: str | Path, column_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Load a file (.csv, .txt, .pdf, .xlsx), parse records, and run validation.
        Returns a dict with preview records, summary counters, and diagnosis.
        """
        path = Path(file_path)
        self.file_path = path
        self.current_records = []
        self.unparsed_items = []

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
                # Keep first or deselect by default for safety
                rec["selected"] = False
                dup_file_count += 1
            elif roll_key in existing_db_rolls:
                rec["status"] = ImportValidationStatus.DUP_IN_DB
                rec["status_code"] = "DUP_DB"
                rec["details"] = "Roll number already exists in database"
                rec["selected"] = False  # Deselected by default unless user allows update
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
                        # Update local cache in case file had internal dupes selected
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

        # Try UTF-8 then fallback to Latin-1
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

        # Use csv.reader to inspect lines
        reader = list(csv.reader(lines))
        if not reader:
            return records, unparsed

        # Detect header row index and column mapping
        header_idx, col_map = self._detect_csv_headers(reader, custom_mapping)

        # Parse rows
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
                # Fallback to positional mapping: [roll, name, class, section]
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
            # User provided explicit header string mapping
            first_row = [c.strip().lower() for c in rows[0]]
            for field, col_name in custom_mapping.items():
                if col_name.lower() in first_row:
                    col_map[field] = first_row.index(col_name.lower())
            return (0, col_map)

        # Search the first 5 rows for header row
        for row_idx, row in enumerate(rows[:5]):
            row_normalized = [c.strip().lower() for c in row]
            matched_fields = {}

            for field, aliases in HEADER_ALIASES.items():
                for idx, cell in enumerate(row_normalized):
                    if cell in aliases or any(cell.startswith(a) for a in aliases):
                        matched_fields[field] = idx
                        break

            # If at least roll_no or name was identified as a header
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

            # Check if line is a header row (e.g. Roll No, Name, Class, Section)
            lower_line = raw.lower()
            if "roll" in lower_line and "name" in lower_line and not re.search(r"\d", lower_line):
                # Header row, skip
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
                        # Map positional columns
                        record = {
                            "roll_no": parts[0],
                            "name": parts[1],
                            "class_name": parts[2] if len(parts) > 2 else "",
                            "section": parts[3].upper() if len(parts) > 3 else ""
                        }
                        records.append(record)
                        break
            else:
                # Could not parse line
                unparsed.append({"line_num": line_num, "text": raw, "reason": "Unrecognized line format"})

        return records, unparsed
