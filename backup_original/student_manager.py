"""
Student management business logic and database operations.
Provides CRUD operations, searching, filtering, and validation for student records.
"""

import sqlite3
from typing import List, Dict, Any, Optional, Set
from database import Database


class DuplicateRollNumberError(Exception):
    """Raised when attempting to add/update a student with a roll number that already exists."""
    pass


class ValidationError(Exception):
    """Raised when required fields are missing or invalid."""
    pass


class StudentManager:
    """Handles all student-related operations."""

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

        # Use natural sort if sorting by roll_no (numbers vs letters) or standard
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
