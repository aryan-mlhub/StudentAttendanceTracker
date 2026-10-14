from datetime import date, datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, UniqueConstraint

db = SQLAlchemy()


def utc_now():
    """Returns current UTC timestamp."""
    return datetime.now(timezone.utc)


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationship with cascade delete of attendance records
    attendances = db.relationship(
        'Attendance',
        backref='student',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    def attendance_summary(self, start_date=None, end_date=None):
        """
        Calculates student attendance statistics.
        NOTE: According to system requirements, Leave is excluded from the denominator.
        Formula: (Present / (Present + Absent)) * 100
        """
        query = self.attendances
        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)

        records = query.all()
        present = sum(1 for r in records if r.status == 'Present')
        absent = sum(1 for r in records if r.status == 'Absent')
        leave = sum(1 for r in records if r.status == 'Leave')
        total_countable = present + absent
        total_sessions = len(records)

        if total_countable > 0:
            percentage = round((present / total_countable) * 100.0, 1)
        else:
            percentage = 100.0 if total_sessions == 0 or leave > 0 else 0.0

        is_low = total_countable > 0 and percentage < 75.0

        return {
            'present': present,
            'absent': absent,
            'leave': leave,
            'total_countable': total_countable,
            'total_sessions': total_sessions,
            'percentage': percentage,
            'is_low': is_low
        }

    def __repr__(self):
        return f'<Student {self.roll_number} - {self.name}>'


class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)  # 'Present', 'Absent', 'Leave'
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint('student_id', 'date', name='uq_student_date'),
        Index('ix_attendance_student_date', 'student_id', 'date'),
    )

    def __repr__(self):
        return f'<Attendance student_id={self.student_id} date={self.date} status={self.status}>'
