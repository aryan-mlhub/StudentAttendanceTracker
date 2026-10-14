"""
PDF parsing engine for Student Attendance Tracker.
Extracts student records from text-based PDFs using pypdf, with smart pattern matching,
table-layout interpretation, page break normalization, and scanned/image PDF detection.
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import pypdf


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
