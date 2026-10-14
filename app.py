import csv
import io
import os
import re
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, text
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from models import Attendance, Student, db, utc_now

# Load environment variables
load_dotenv()

csrf = CSRFProtect()


def normalize_db_url(raw_url: str) -> str:
    """Normalizes connection schemes for modern SQLAlchemy compatibility."""
    if not raw_url:
        return ''
    raw_url = raw_url.strip()
    # Normalize postgres:// to postgresql://
    if raw_url.startswith('postgres://'):
        return raw_url.replace('postgres://', 'postgresql://', 1)
    return raw_url


def create_app(config_overrides=None):
    app = Flask(__name__, static_folder='static', template_folder='templates')

    # Default Secret Key
    app.config['SECRET_KEY'] = os.environ.get(
        'SECRET_KEY', 'student-tracker-dev-secret-key-change-in-production'
    )

    # Database Configuration
    raw_db_url = normalize_db_url(os.environ.get('DATABASE_URL', ''))
    if raw_db_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
    else:
        # Placeholder that avoids silently falling back to SQLite or fake data in production
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            'postgresql://unconfigured:unconfigured@localhost:5432/unconfigured'
        )

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    if config_overrides:
        app.config.update(config_overrides)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)

    def get_db_status():
        """
        Checks if a real database is configured and reachable.
        Returns (is_connected: bool, message: str).
        """
        # If in testing mode with test URI
        if app.config.get('TESTING'):
            try:
                db.session.execute(text('SELECT 1'))
                return True, 'Test database active.'
            except Exception as e:
                return False, f'Test database error: {e}'

        if not os.environ.get('DATABASE_URL'):
            return (
                False,
                'DATABASE_URL environment variable is not set. A hosted PostgreSQL database (such as Neon) is required for production persistence.',
            )

        try:
            db.session.execute(text('SELECT 1'))
            return True, 'Connected to PostgreSQL successfully.'
        except (OperationalError, DatabaseError) as e:
            return False, f'Database connection error: {str(e).splitlines()[0]}'
        except Exception as e:
            return False, f'Unexpected database error: {str(e)}'

    @app.context_processor
    def inject_global_data():
        """Injects current date and DB status into all templates."""
        is_connected, db_msg = get_db_status()
        return {
            'today_date': date.today().isoformat(),
            'db_connected': is_connected,
            'db_message': db_msg,
            'now_year': datetime.now().year,
        }

    @app.cli.command('init-db')
    def init_db_command():
        """CLI command to initialize the PostgreSQL database schema."""
        is_connected, msg = get_db_status()
        if not is_connected:
            print(f'Cannot initialize database: {msg}')
            return

        try:
            db.create_all()
            print('PostgreSQL database schema initialized successfully.')
        except Exception as e:
            print(f'Failed to initialize database schema: {e}')

    @app.route('/init-db', methods=['POST'])
    def web_init_db():
        """Web route to manually trigger schema initialization."""
        is_connected, msg = get_db_status()
        if not is_connected:
            flash(f'Cannot initialize database: {msg}', 'error')
            return redirect(url_for('dashboard'))

        try:
            db.create_all()
            flash(
                'PostgreSQL database schema initialized successfully! Ready for students and attendance.',
                'success',
            )
        except Exception as e:
            flash(f'Failed to initialize database schema: {e}', 'error')

        return redirect(url_for('dashboard'))

    # -----------------------------------------------------------------------------
    # DASHBOARD
    # -----------------------------------------------------------------------------
    @app.route('/')
    def dashboard():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            return render_template(
                'dashboard.html',
                is_connected=False,
                db_message=db_msg,
                total_students=0,
                selected_date=date.today().isoformat(),
                present_count=0,
                absent_count=0,
                leave_count=0,
                unmarked_count=0,
                date_percentage=None,
                overall_percentage=None,
                low_attendance_students=[],
                courses=[],
            )

        try:
            db.create_all()
        except Exception:
            pass

        selected_date_str = request.args.get('date', date.today().isoformat())
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
            selected_date_str = selected_date.isoformat()

        try:
            total_students = Student.query.count()
            courses = [
                c[0]
                for c in db.session.query(Student.course).distinct().all()
                if c[0]
            ]

            day_attendances = Attendance.query.filter_by(date=selected_date).all()
            present_count = sum(
                1 for a in day_attendances if a.status == 'Present'
            )
            absent_count = sum(1 for a in day_attendances if a.status == 'Absent')
            leave_count = sum(1 for a in day_attendances if a.status == 'Leave')
            marked_count = len(day_attendances)
            unmarked_count = max(0, total_students - marked_count)

            # Accurate percentage calculation excluding Leave from denominator
            day_countable = present_count + absent_count
            if day_countable > 0:
                date_percentage = round(
                    (present_count / day_countable) * 100.0, 1
                )
            else:
                date_percentage = None

            all_records = Attendance.query.all()
            all_present = sum(1 for a in all_records if a.status == 'Present')
            all_absent = sum(1 for a in all_records if a.status == 'Absent')
            all_countable = all_present + all_absent
            if all_countable > 0:
                overall_percentage = round(
                    (all_present / all_countable) * 100.0, 1
                )
            else:
                overall_percentage = None

            all_students = Student.query.order_by(Student.roll_number.asc()).all()
            low_attendance_students = []
            for s in all_students:
                summary = s.attendance_summary()
                if summary['is_low']:
                    low_attendance_students.append({
                        'student': s,
                        'summary': summary,
                    })

            return render_template(
                'dashboard.html',
                is_connected=True,
                db_message=db_msg,
                total_students=total_students,
                selected_date=selected_date_str,
                present_count=present_count,
                absent_count=absent_count,
                leave_count=leave_count,
                unmarked_count=unmarked_count,
                date_percentage=date_percentage,
                overall_percentage=overall_percentage,
                low_attendance_students=low_attendance_students,
                courses=courses,
            )
        except (OperationalError, DatabaseError) as e:
            flash(f'Database error: {str(e).splitlines()[0]}', 'error')
            return render_template(
                'dashboard.html',
                is_connected=False,
                db_message=str(e),
                total_students=0,
                selected_date=selected_date_str,
                present_count=0,
                absent_count=0,
                leave_count=0,
                unmarked_count=0,
                date_percentage=None,
                overall_percentage=None,
                low_attendance_students=[],
                courses=[],
            )

    # -----------------------------------------------------------------------------
    # STUDENT MANAGEMENT
    # -----------------------------------------------------------------------------
    @app.route('/students')
    def students():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'PostgreSQL database not connected: {db_msg}', 'warning')
            return render_template(
                'students.html',
                students=[],
                courses=[],
                search_query='',
                selected_course='',
            )

        try:
            db.create_all()
        except Exception:
            pass

        search_query = request.args.get('q', '').strip()
        selected_course = request.args.get('course', '').strip()

        try:
            query = Student.query
            if search_query:
                search_pattern = f'%{search_query}%'
                query = query.filter(
                    (Student.roll_number.ilike(search_pattern))
                    | (Student.name.ilike(search_pattern))
                    | (Student.email.ilike(search_pattern))
                )

            if selected_course:
                query = query.filter(Student.course == selected_course)

            student_list = query.order_by(Student.roll_number.asc()).all()

            student_data = []
            for s in student_list:
                student_data.append({
                    'student': s,
                    'summary': s.attendance_summary(),
                })

            courses = [
                c[0]
                for c in db.session.query(Student.course).distinct().all()
                if c[0]
            ]

            return render_template(
                'students.html',
                students=student_data,
                courses=courses,
                search_query=search_query,
                selected_course=selected_course,
            )
        except (OperationalError, DatabaseError) as e:
            flash(f'Database query error: {str(e).splitlines()[0]}', 'error')
            return render_template(
                'students.html',
                students=[],
                courses=[],
                search_query=search_query,
                selected_course=selected_course,
            )

    @app.route('/students/add', methods=['GET', 'POST'])
    def add_student():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Cannot add student. Database not connected: {db_msg}', 'error')
            return redirect(url_for('students'))

        if request.method == 'GET':
            return render_template(
                'student_form.html',
                action='Add',
                student=None,
                form_data={},
            )

        roll_number = request.form.get('roll_number', '').strip()
        name = request.form.get('name', '').strip()
        course = request.form.get('course', '').strip()
        email = request.form.get('email', '').strip()

        form_data = {
            'roll_number': roll_number,
            'name': name,
            'course': course,
            'email': email,
        }

        errors = []
        if not roll_number:
            errors.append('Roll Number is required.')
        elif len(roll_number) > 50:
            errors.append('Roll Number must be 50 characters or less.')

        if not name:
            errors.append('Full Name is required.')
        elif len(name) > 100:
            errors.append('Full Name must be 100 characters or less.')

        if not course:
            errors.append('Class / Course is required.')
        elif len(course) > 100:
            errors.append('Class / Course must be 100 characters or less.')

        if email:
            if len(email) > 120:
                errors.append('Email must be 120 characters or less.')
            elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                errors.append('Please provide a valid email address.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template(
                'student_form.html',
                action='Add',
                student=None,
                form_data=form_data,
            )

        existing_student = Student.query.filter(
            func.lower(Student.roll_number) == roll_number.lower()
        ).first()
        if existing_student:
            flash(
                f"A student with Roll Number '{roll_number}' already exists ({existing_student.name}).",
                'error',
            )
            return render_template(
                'student_form.html',
                action='Add',
                student=None,
                form_data=form_data,
            )

        try:
            new_student = Student(
                roll_number=roll_number,
                name=name,
                course=course,
                email=email or None,
            )
            db.session.add(new_student)
            db.session.commit()
            flash(
                f"Student '{name}' ({roll_number}) added successfully!", 'success'
            )
            return redirect(url_for('students'))
        except IntegrityError:
            db.session.rollback()
            flash(
                f"Duplicate record error: Roll Number '{roll_number}' already exists.",
                'error',
            )
            return render_template(
                'student_form.html',
                action='Add',
                student=None,
                form_data=form_data,
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to add student: {str(e)}', 'error')
            return render_template(
                'student_form.html',
                action='Add',
                student=None,
                form_data=form_data,
            )

    @app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
    def edit_student(student_id):
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Cannot edit student. Database not connected: {db_msg}', 'error')
            return redirect(url_for('students'))

        student = db.get_or_404(Student, student_id)

        if request.method == 'GET':
            form_data = {
                'roll_number': student.roll_number,
                'name': student.name,
                'course': student.course,
                'email': student.email or '',
            }
            return render_template(
                'student_form.html',
                action='Edit',
                student=student,
                form_data=form_data,
            )

        roll_number = request.form.get('roll_number', '').strip()
        name = request.form.get('name', '').strip()
        course = request.form.get('course', '').strip()
        email = request.form.get('email', '').strip()

        form_data = {
            'roll_number': roll_number,
            'name': name,
            'course': course,
            'email': email,
        }

        errors = []
        if not roll_number:
            errors.append('Roll Number is required.')
        if not name:
            errors.append('Full Name is required.')
        if not course:
            errors.append('Class / Course is required.')
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Please provide a valid email address.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template(
                'student_form.html',
                action='Edit',
                student=student,
                form_data=form_data,
            )

        existing = (
            Student.query.filter(
                func.lower(Student.roll_number) == roll_number.lower(),
                Student.id != student.id,
            ).first()
        )
        if existing:
            flash(
                f"Another student with Roll Number '{roll_number}' already exists ({existing.name}).",
                'error',
            )
            return render_template(
                'student_form.html',
                action='Edit',
                student=student,
                form_data=form_data,
            )

        try:
            student.roll_number = roll_number
            student.name = name
            student.course = course
            student.email = email or None
            db.session.commit()
            flash(f"Student '{name}' updated successfully!", 'success')
            return redirect(url_for('students'))
        except IntegrityError:
            db.session.rollback()
            flash(f"Duplicate Roll Number '{roll_number}'.", 'error')
            return render_template(
                'student_form.html',
                action='Edit',
                student=student,
                form_data=form_data,
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update student: {str(e)}', 'error')
            return render_template(
                'student_form.html',
                action='Edit',
                student=student,
                form_data=form_data,
            )

    @app.route('/students/<int:student_id>/delete', methods=['POST'])
    def delete_student(student_id):
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Cannot delete student. Database not connected: {db_msg}', 'error')
            return redirect(url_for('students'))

        student = db.get_or_404(Student, student_id)
        student_name = student.name
        student_roll = student.roll_number

        try:
            db.session.delete(student)
            db.session.commit()
            flash(
                f"Student '{student_name}' ({student_roll}) and all associated attendance records were deleted.",
                'success',
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to delete student: {str(e)}', 'error')

        return redirect(url_for('students'))

    @app.route('/students/<int:student_id>/history')
    def student_history(student_id):
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Database not connected: {db_msg}', 'error')
            return redirect(url_for('students'))

        student = db.get_or_404(Student, student_id)
        records = student.attendances.order_by(Attendance.date.desc()).all()
        summary = student.attendance_summary()

        return render_template(
            'student_history.html',
            student=student,
            records=records,
            summary=summary,
        )

    # -----------------------------------------------------------------------------
    # ATTENDANCE MANAGEMENT
    # -----------------------------------------------------------------------------
    @app.route('/attendance', methods=['GET', 'POST'])
    def attendance():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(
                f'Cannot mark attendance. Database not connected: {db_msg}',
                'warning',
            )
            return render_template(
                'attendance.html',
                students=[],
                courses=[],
                selected_date=date.today().isoformat(),
                selected_course='',
                status_map={},
            )

        try:
            db.create_all()
        except Exception:
            pass

        if request.method == 'GET':
            selected_date_str = request.args.get('date', date.today().isoformat())
            selected_course = request.args.get('course', '').strip()

            try:
                selected_date = datetime.strptime(
                    selected_date_str, '%Y-%m-%d'
                ).date()
            except ValueError:
                selected_date = date.today()
                selected_date_str = selected_date.isoformat()

            try:
                student_query = Student.query
                if selected_course:
                    student_query = student_query.filter(
                        Student.course == selected_course
                    )
                student_list = student_query.order_by(
                    Student.roll_number.asc()
                ).all()

                existing_records = Attendance.query.filter_by(
                    date=selected_date
                ).all()
                status_map = {r.student_id: r.status for r in existing_records}

                courses = [
                    c[0]
                    for c in db.session.query(Student.course).distinct().all()
                    if c[0]
                ]

                return render_template(
                    'attendance.html',
                    students=student_list,
                    courses=courses,
                    selected_date=selected_date_str,
                    selected_course=selected_course,
                    status_map=status_map,
                )
            except (OperationalError, DatabaseError) as e:
                flash(f'Database error: {str(e).splitlines()[0]}', 'error')
                return render_template(
                    'attendance.html',
                    students=[],
                    courses=[],
                    selected_date=selected_date_str,
                    selected_course=selected_course,
                    status_map={},
                )

        # POST: Save attendance
        date_str = request.form.get('date', '').strip()
        selected_course = request.form.get('course', '').strip()

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date provided.', 'error')
            return redirect(url_for('attendance'))

        student_query = Student.query
        if selected_course:
            student_query = student_query.filter(Student.course == selected_course)
        students_to_mark = student_query.all()

        if not students_to_mark:
            flash('No students available to mark attendance for.', 'warning')
            return redirect(
                url_for('attendance', date=date_str, course=selected_course)
            )

        updated_count = 0
        created_count = 0

        try:
            for s in students_to_mark:
                status = request.form.get(f'status_{s.id}')
                if status in ['Present', 'Absent', 'Leave']:
                    existing_record = Attendance.query.filter_by(
                        student_id=s.id, date=target_date
                    ).first()

                    if existing_record:
                        if existing_record.status != status:
                            existing_record.status = status
                            existing_record.updated_at = utc_now()
                            updated_count += 1
                    else:
                        new_rec = Attendance(
                            student_id=s.id,
                            date=target_date,
                            status=status,
                        )
                        db.session.add(new_rec)
                        created_count += 1

            db.session.commit()
            flash(
                f'Attendance for {target_date.strftime("%b %d, %Y")} saved successfully! ({created_count} marked, {updated_count} updated)',
                'success',
            )
        except IntegrityError:
            db.session.rollback()
            flash('Duplicate attendance record detected. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to save attendance: {str(e)}', 'error')

        return redirect(
            url_for('attendance', date=date_str, course=selected_course)
        )

    # -----------------------------------------------------------------------------
    # REPORTS & ANALYTICS
    # -----------------------------------------------------------------------------
    @app.route('/reports')
    def reports():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Database not connected: {db_msg}', 'warning')
            return render_template(
                'reports.html',
                records=[],
                summary={
                    'total': 0,
                    'present': 0,
                    'absent': 0,
                    'leave': 0,
                    'percentage': None,
                },
                courses=[],
                students=[],
                start_date='',
                end_date='',
                selected_student_id='',
                selected_course='',
                selected_status='',
            )

        try:
            db.create_all()
        except Exception:
            pass

        selected_student_id = request.args.get('student_id', '').strip()
        selected_course = request.args.get('course', '').strip()
        selected_status = request.args.get('status', '').strip()
        start_date_str = request.args.get('start_date', '').strip()
        end_date_str = request.args.get('end_date', '').strip()

        if not start_date_str and not end_date_str:
            end_date = date.today()
            start_date = end_date - timedelta(days=30)
            start_date_str = start_date.isoformat()
            end_date_str = end_date.isoformat()
        else:
            try:
                start_date = (
                    datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    if start_date_str
                    else None
                )
            except ValueError:
                start_date = None
            try:
                end_date = (
                    datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    if end_date_str
                    else None
                )
            except ValueError:
                end_date = None

        try:
            query = Attendance.query.join(Student)

            if selected_student_id and selected_student_id.isdigit():
                query = query.filter(Attendance.student_id == int(selected_student_id))

            if selected_course:
                query = query.filter(Student.course == selected_course)

            if selected_status in ['Present', 'Absent', 'Leave']:
                query = query.filter(Attendance.status == selected_status)

            if start_date:
                query = query.filter(Attendance.date >= start_date)

            if end_date:
                query = query.filter(Attendance.date <= end_date)

            records = query.order_by(
                Attendance.date.desc(), Student.roll_number.asc()
            ).all()

            present = sum(1 for r in records if r.status == 'Present')
            absent = sum(1 for r in records if r.status == 'Absent')
            leave = sum(1 for r in records if r.status == 'Leave')
            total = len(records)
            countable = present + absent

            if countable > 0:
                percentage = round((present / countable) * 100.0, 1)
            else:
                percentage = None

            summary = {
                'total': total,
                'present': present,
                'absent': absent,
                'leave': leave,
                'percentage': percentage,
            }

            courses = [
                c[0]
                for c in db.session.query(Student.course).distinct().all()
                if c[0]
            ]
            students = Student.query.order_by(Student.roll_number.asc()).all()

            return render_template(
                'reports.html',
                records=records,
                summary=summary,
                courses=courses,
                students=students,
                start_date=start_date_str,
                end_date=end_date_str,
                selected_student_id=selected_student_id,
                selected_course=selected_course,
                selected_status=selected_status,
            )
        except (OperationalError, DatabaseError) as e:
            flash(f'Database error: {str(e).splitlines()[0]}', 'error')
            return render_template(
                'reports.html',
                records=[],
                summary={
                    'total': 0,
                    'present': 0,
                    'absent': 0,
                    'leave': 0,
                    'percentage': None,
                },
                courses=[],
                students=[],
                start_date=start_date_str,
                end_date=end_date_str,
                selected_student_id=selected_student_id,
                selected_course=selected_course,
                selected_status=selected_status,
            )

    @app.route('/reports/export-csv')
    def export_reports_csv():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Cannot export CSV: Database not connected ({db_msg})', 'error')
            return redirect(url_for('reports'))

        selected_student_id = request.args.get('student_id', '').strip()
        selected_course = request.args.get('course', '').strip()
        selected_status = request.args.get('status', '').strip()
        start_date_str = request.args.get('start_date', '').strip()
        end_date_str = request.args.get('end_date', '').strip()

        try:
            start_date = (
                datetime.strptime(start_date_str, '%Y-%m-%d').date()
                if start_date_str
                else None
            )
        except ValueError:
            start_date = None
        try:
            end_date = (
                datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if end_date_str
                else None
            )
        except ValueError:
            end_date = None

        query = Attendance.query.join(Student)
        if selected_student_id and selected_student_id.isdigit():
            query = query.filter(Attendance.student_id == int(selected_student_id))
        if selected_course:
            query = query.filter(Student.course == selected_course)
        if selected_status in ['Present', 'Absent', 'Leave']:
            query = query.filter(Attendance.status == selected_status)
        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)

        records = query.order_by(
            Attendance.date.desc(), Student.roll_number.asc()
        ).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Date',
            'Roll Number',
            'Student Name',
            'Class/Course',
            'Email',
            'Attendance Status',
        ])

        for r in records:
            writer.writerow([
                r.date.isoformat(),
                r.student.roll_number,
                r.student.name,
                r.student.course,
                r.student.email or '',
                r.status,
            ])

        csv_data = output.getvalue()
        filename = f"attendance_report_{date.today().strftime('%Y%m%d')}.csv"

        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    # -----------------------------------------------------------------------------
    # CSV STUDENT IMPORT & SAMPLE TEMPLATE
    # -----------------------------------------------------------------------------
    @app.route('/students/sample-csv')
    def sample_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['roll_number', 'name', 'course', 'email'])
        writer.writerow([
            'CS-2024-001',
            'Alice Johnson',
            'Computer Science',
            'alice.johnson@example.edu',
        ])
        writer.writerow([
            'CS-2024-002',
            'Bob Smith',
            'Computer Science',
            'bob.smith@example.edu',
        ])
        writer.writerow([
            'EE-2024-001',
            'Charlie Davis',
            'Electrical Engineering',
            'charlie.davis@example.edu',
        ])

        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename="student_import_template.csv"'
            },
        )

    @app.route('/students/import-csv', methods=['POST'])
    def import_students_csv():
        is_connected, db_msg = get_db_status()
        if not is_connected:
            flash(f'Cannot import students: Database not connected ({db_msg})', 'error')
            return redirect(url_for('students'))

        if 'file' not in request.files:
            flash('No file part in upload request.', 'error')
            return redirect(url_for('students'))

        file = request.files['file']
        if not file or file.filename == '':
            flash('No file selected. Please choose a CSV file to upload.', 'error')
            return redirect(url_for('students'))

        if not file.filename.lower().endswith('.csv'):
            flash('Invalid file format. Please upload a .csv file.', 'error')
            return redirect(url_for('students'))

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'), newline=None)
            reader = csv.reader(stream)
            rows = list(reader)
        except Exception as e:
            flash(f'Failed to parse CSV file: {str(e)}', 'error')
            return redirect(url_for('students'))

        if not rows:
            flash('The uploaded CSV file is empty.', 'error')
            return redirect(url_for('students'))

        raw_headers = [h.strip().lower().replace(' ', '_').replace('/', '_') for h in rows[0]]
        header_indices = {}
        for idx, h in enumerate(raw_headers):
            if h in ['roll_number', 'roll_no', 'rollno', 'roll']:
                header_indices['roll_number'] = idx
            elif h in ['name', 'full_name', 'student_name']:
                header_indices['name'] = idx
            elif h in ['course', 'class', 'branch', 'department']:
                header_indices['course'] = idx
            elif h in ['email', 'email_address']:
                header_indices['email'] = idx

        missing_headers = []
        for req in ['roll_number', 'name', 'course']:
            if req not in header_indices:
                missing_headers.append(req)

        if missing_headers:
            flash(
                f"Missing required columns in CSV: {', '.join(missing_headers)}. Required headers: roll_number, name, course (optional: email).",
                'error',
            )
            return redirect(url_for('students'))

        success_count = 0
        errors = []
        seen_rolls = set()

        existing_db_rolls = {
            r[0].lower() for r in db.session.query(Student.roll_number).all()
        }

        students_to_add = []

        for row_num, row in enumerate(rows[1:], start=2):
            if not row or not any(cell.strip() for cell in row):
                continue

            try:
                roll = (
                    row[header_indices['roll_number']].strip()
                    if len(row) > header_indices['roll_number']
                    else ''
                )
                name = (
                    row[header_indices['name']].strip()
                    if len(row) > header_indices['name']
                    else ''
                )
                course = (
                    row[header_indices['course']].strip()
                    if len(row) > header_indices['course']
                    else ''
                )
                email = ''
                if 'email' in header_indices and len(row) > header_indices['email']:
                    email = row[header_indices['email']].strip()

                if not roll:
                    errors.append(f'Row {row_num}: Missing Roll Number.')
                    continue
                if not name:
                    errors.append(f"Row {row_num}: Missing Name for roll '{roll}'.")
                    continue
                if not course:
                    errors.append(f"Row {row_num}: Missing Course for student '{name}'.")
                    continue

                roll_lower = roll.lower()
                if roll_lower in seen_rolls:
                    errors.append(
                        f"Row {row_num}: Duplicate Roll Number '{roll}' found within the CSV file."
                    )
                    continue

                if roll_lower in existing_db_rolls:
                    errors.append(
                        f"Row {row_num}: Roll Number '{roll}' already exists in the database."
                    )
                    continue

                if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                    errors.append(
                        f"Row {row_num}: Invalid email '{email}' for student '{name}'."
                    )
                    continue

                seen_rolls.add(roll_lower)
                new_student = Student(
                    roll_number=roll,
                    name=name,
                    course=course,
                    email=email or None,
                )
                students_to_add.append(new_student)
                success_count += 1

            except Exception as row_err:
                errors.append(f'Row {row_num}: Error processing row: {str(row_err)}')

        if students_to_add:
            try:
                db.session.add_all(students_to_add)
                db.session.commit()
                flash(
                    f'Successfully imported {success_count} student(s) into the database!',
                    'success',
                )
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to commit imported students to database: {str(e)}', 'error')
                return redirect(url_for('students'))

        if errors:
            max_displayed = 5
            sample_errors = errors[:max_displayed]
            remaining = len(errors) - max_displayed
            err_msg = 'Import issues encountered: ' + ' | '.join(sample_errors)
            if remaining > 0:
                err_msg += f' ...and {remaining} more row(s) skipped.'
            flash(err_msg, 'warning')

        return redirect(url_for('students'))

    # -----------------------------------------------------------------------------
    # HEALTH ENDPOINT
    # -----------------------------------------------------------------------------
    @app.route('/health')
    @csrf.exempt
    def health():
        is_connected, msg = get_db_status()
        return {
            'status': 'healthy',
            'database_connected': is_connected,
            'database_message': msg,
            'timestamp': utc_now().isoformat(),
        }

    return app


# Default application instance for WSGI / Vercel
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
