"""
Database layer for Student Attendance Tracker.
Handles SQLite connection, schema initialization, constraints, indexes, and transactions.
"""

import sqlite3
import os
from pathlib import Path
from typing import Any, List, Tuple, Optional, Dict
from contextlib import contextmanager

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "attendance_tracker.db"


class Database:
    """Manages SQLite database connections and transactions."""

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
        """Placeholder for consistency."""
        pass
