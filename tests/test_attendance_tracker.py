import io
import unittest
from datetime import date, timedelta

from app import create_app
from models import Attendance, Student, db


class AttendanceTrackerTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app for testing with in-memory SQLite isolated testing
        self.app = create_app({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_student_creation_and_duplicate_prevention(self):
        """Verify student creation, validation, and duplicate roll number prevention."""
        with self.app.app_context():
            # Add student 1
            response = self.client.post(
                '/students/add',
                data={
                    'roll_number': 'CS-001',
                    'name': 'Alice Johnson',
                    'course': 'Computer Science',
                    'email': 'alice@example.com',
                },
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'added successfully', response.data)

            # Confirm in DB
            student = Student.query.filter_by(roll_number='CS-001').first()
            self.assertIsNotNone(student)
            self.assertEqual(student.name, 'Alice Johnson')

            # Attempt duplicate roll number (case-insensitive check)
            dup_response = self.client.post(
                '/students/add',
                data={
                    'roll_number': 'cs-001',
                    'name': 'Duplicate Person',
                    'course': 'Computer Science',
                    'email': 'dup@example.com',
                },
                follow_redirects=True,
            )
            self.assertEqual(dup_response.status_code, 200)
            self.assertIn(b'already exists', dup_response.data)

            # Student count should still be 1
            self.assertEqual(Student.query.count(), 1)

    def test_student_edit_and_delete(self):
        """Verify updating student and deleting student with cascade."""
        with self.app.app_context():
            student = Student(
                roll_number='CS-002', name='Bob Smith', course='Math'
            )
            db.session.add(student)
            db.session.commit()
            student_id = student.id

            # Edit student
            edit_response = self.client.post(
                f'/students/{student_id}/edit',
                data={
                    'roll_number': 'CS-002',
                    'name': 'Robert Smith',
                    'course': 'Mathematics',
                    'email': 'robert@example.com',
                },
                follow_redirects=True,
            )
            self.assertEqual(edit_response.status_code, 200)
            self.assertIn(b'updated successfully', edit_response.data)

            updated = db.session.get(Student, student_id)
            self.assertEqual(updated.name, 'Robert Smith')
            self.assertEqual(updated.course, 'Mathematics')

            # Add an attendance record
            att = Attendance(
                student_id=student_id, date=date.today(), status='Present'
            )
            db.session.add(att)
            db.session.commit()
            self.assertEqual(Attendance.query.count(), 1)

            # Delete student
            del_response = self.client.post(
                f'/students/{student_id}/delete', follow_redirects=True
            )
            self.assertEqual(del_response.status_code, 200)
            self.assertIn(b'were deleted', del_response.data)

            # Verify student and cascading attendance are deleted
            self.assertIsNone(db.session.get(Student, student_id))
            self.assertEqual(Attendance.query.count(), 0)

    def test_attendance_percentage_calculation_excluding_leave(self):
        """
        Verify that attendance percentage accurately excludes Leave from denominator.
        Formula: Present / (Present + Absent) * 100
        """
        with self.app.app_context():
            student = Student(
                roll_number='EE-101', name='Charlie Davis', course='EE'
            )
            db.session.add(student)
            db.session.commit()

            # Record: 3 Present, 1 Absent, 2 Leave
            # Total sessions = 6
            # Denominator (Present + Absent) = 4 (Leave excluded!)
            # Expected percentage = (3 / 4) * 100 = 75.0%
            d = date(2024, 10, 1)
            records = [
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=0),
                    status='Present',
                ),
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=1),
                    status='Present',
                ),
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=2),
                    status='Present',
                ),
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=3),
                    status='Absent',
                ),
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=4),
                    status='Leave',
                ),
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=5),
                    status='Leave',
                ),
            ]
            db.session.add_all(records)
            db.session.commit()

            summary = student.attendance_summary()
            self.assertEqual(summary['present'], 3)
            self.assertEqual(summary['absent'], 1)
            self.assertEqual(summary['leave'], 2)
            self.assertEqual(summary['total_sessions'], 6)
            self.assertEqual(summary['total_countable'], 4)
            self.assertEqual(summary['percentage'], 75.0)
            self.assertFalse(summary['is_low'])

            # Add one more Absent session:
            # Present: 3, Absent: 2 -> Countable: 5 -> 3/5 = 60.0% -> Low Attendance (< 75%)
            db.session.add(
                Attendance(
                    student_id=student.id,
                    date=d + timedelta(days=6),
                    status='Absent',
                )
            )
            db.session.commit()

            summary2 = student.attendance_summary()
            self.assertEqual(summary2['percentage'], 60.0)
            self.assertTrue(summary2['is_low'])

    def test_attendance_marking_and_updating_existing_records(self):
        """Verify marking attendance and updating existing records without duplicates."""
        with self.app.app_context():
            s1 = Student(roll_number='IT-01', name='Diana', course='IT')
            s2 = Student(roll_number='IT-02', name='Edward', course='IT')
            db.session.add_all([s1, s2])
            db.session.commit()

            test_date = '2024-10-15'

            # Mark initial attendance
            res1 = self.client.post(
                '/attendance',
                data={
                    'date': test_date,
                    'course': '',
                    f'status_{s1.id}': 'Present',
                    f'status_{s2.id}': 'Absent',
                },
                follow_redirects=True,
            )
            self.assertEqual(res1.status_code, 200)
            self.assertIn(b'saved successfully', res1.data)

            # Check DB records
            r1 = Attendance.query.filter_by(
                student_id=s1.id, date=date(2024, 10, 15)
            ).first()
            r2 = Attendance.query.filter_by(
                student_id=s2.id, date=date(2024, 10, 15)
            ).first()
            self.assertEqual(r1.status, 'Present')
            self.assertEqual(r2.status, 'Absent')
            self.assertEqual(Attendance.query.count(), 2)

            # Now update s2 to 'Leave' and s1 remains 'Present'
            res2 = self.client.post(
                '/attendance',
                data={
                    'date': test_date,
                    'course': '',
                    f'status_{s1.id}': 'Present',
                    f'status_{s2.id}': 'Leave',
                },
                follow_redirects=True,
            )
            self.assertEqual(res2.status_code, 200)

            # Total records should STILL be 2 (no duplicate row created!)
            self.assertEqual(Attendance.query.count(), 2)
            r2_updated = Attendance.query.filter_by(
                student_id=s2.id, date=date(2024, 10, 15)
            ).first()
            self.assertEqual(r2_updated.status, 'Leave')

    def test_csv_export(self):
        """Verify CSV export functionality using Python's csv module."""
        with self.app.app_context():
            student = Student(
                roll_number='CS-500',
                name='Grace Hopper',
                course='CS',
                email='grace@navy.mil',
            )
            db.session.add(student)
            db.session.commit()

            att = Attendance(
                student_id=student.id, date=date(2024, 10, 10), status='Present'
            )
            db.session.add(att)
            db.session.commit()

            response = self.client.get('/reports/export-csv')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, 'text/csv; charset=utf-8')
            self.assertIn(
                b'attachment; filename="attendance_report_',
                response.headers['Content-Disposition'].encode(),
            )

            csv_text = response.data.decode('utf-8')
            self.assertIn('Date,Roll Number,Student Name,Class/Course', csv_text)
            self.assertIn('CS-500,Grace Hopper,CS', csv_text)
            self.assertIn('Present', csv_text)

    def test_csv_import_valid_and_invalid_rows(self):
        """Verify CSV import validation, duplicate detection, and reporting."""
        with self.app.app_context():
            # Seed an existing student in database
            existing = Student(
                roll_number='EXIST-01', name='Existing Student', course='AI'
            )
            db.session.add(existing)
            db.session.commit()

            # CSV with:
            # Row 2: valid student
            # Row 3: duplicate in DB (EXIST-01)
            # Row 4: missing course
            # Row 5: valid student
            # Row 6: duplicate within CSV (same roll as row 2)
            csv_content = """roll_number,name,course,email
NEW-001,John Doe,Physics,john@example.com
EXIST-01,Duplicate In DB,AI,dup@example.com
BAD-001,No Course Student,,nocourse@example.com
NEW-002,Jane Smith,Chemistry,jane@example.com
NEW-001,Duplicate In File,Physics,other@example.com
"""
            data = {
                'file': (
                    io.BytesIO(csv_content.encode('utf-8')),
                    'test_students.csv',
                )
            }
            response = self.client.post(
                '/students/import-csv',
                data=data,
                content_type='multipart/form-data',
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Successfully imported 2 student(s)', response.data)
            self.assertIn(b'Import issues encountered', response.data)

            # Confirm NEW-001 and NEW-002 are in DB, total students = 3 (1 existing + 2 new)
            self.assertEqual(Student.query.count(), 3)
            self.assertIsNotNone(
                Student.query.filter_by(roll_number='NEW-001').first()
            )
            self.assertIsNotNone(
                Student.query.filter_by(roll_number='NEW-002').first()
            )

    def test_sample_csv_download(self):
        """Verify sample CSV template download."""
        response = self.client.get('/students/sample-csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/csv; charset=utf-8')
        self.assertIn('roll_number,name,course,email', response.data.decode('utf-8'))

    def test_health_check(self):
        """Verify health endpoint."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'healthy')


if __name__ == '__main__':
    unittest.main()
