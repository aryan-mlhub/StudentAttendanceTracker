"""
Reports and analytics engine for Student Attendance Tracker.
Generates individual student summaries, class-wise reports, date-range filters,
low-attendance threshold warnings (< 75%), and CSV exports.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from database import Database


ATTENDANCE_DEFICIT_THRESHOLD = 75.0


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
            return 100.0  # If no present/absent days recorded (e.g. only leaves or fresh)
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

        # Query joins students with filtered attendance
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

        # Combine params in order: date_params then where_params
        all_params = tuple(date_params + params)
        rows = self.db.fetch_all(query, all_params)

        results = []
        for r in rows:
            present = r["present_days"] or 0
            absent = r["absent_days"] or 0
            leave = r["leave_days"] or 0
            total_recorded = r["total_days_recorded"] or 0

            # Only calculate percentage if attendance has been marked at least once
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
