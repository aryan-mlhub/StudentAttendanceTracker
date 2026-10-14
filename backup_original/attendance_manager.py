"""
Attendance management business logic and database operations.
Handles date-based marking, batch saving, status updates, historical retrieval, and statistics.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from database import Database


VALID_STATUSES = {"Present", "Absent", "Leave"}


class AttendanceManager:
    """Handles marking, modifying, and retrieving attendance records."""

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
                    # UPSERT (Insert or Update if student_id and attendance_date already exists)
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
        - present_count
        - absent_count
        - leave_count
        - unmarked_count: total_students - marked_count
        - percentage: Present / (Present + Absent) * 100 (Leaves do not count in denominator)
        """
        if not attendance_date:
            date_str = date.today().strftime("%Y-%m-%d")
        else:
            date_str = self.validate_date(attendance_date)

        # Total registered students
        tot_res = self.db.fetch_one("SELECT COUNT(*) as count FROM students;")
        total_students = tot_res["count"] if tot_res else 0

        # Attendance breakdown for the date
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

        # Percentage formula: Present / (Present + Absent) * 100
        denominator = present + absent
        if denominator > 0:
            percentage = round((present / denominator) * 100.0, 1)
        elif marked > 0 and leave > 0:
            percentage = 100.0  # If only leaves were taken, no absences
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
        """
        Fetch summary of recent attendance sessions grouped by date and class.
        """
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
