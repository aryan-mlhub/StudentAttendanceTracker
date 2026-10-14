# Student Attendance Tracker

A production-ready, full-stack **Student Attendance Tracker** application built with Python, Flask, SQLAlchemy, hosted PostgreSQL (e.g. Neon), Tailwind CSS, and designed for deployment on Vercel.

---

## 1. Technology Stack

- **Frontend**: Semantic HTML5 with modern UI layout
- **Styling**: Tailwind CSS (Tailwind CDN) with custom utility styles
- **Backend**: Python 3 + Flask (Application Factory pattern)
- **Database**: Hosted PostgreSQL (Neon Serverless PostgreSQL recommended)
- **ORM**: SQLAlchemy (via Flask-SQLAlchemy)
- **CSV Processing**: Python standard library `csv` and `io` modules
- **CSRF Protection**: Flask-WTF
- **Deployment Platform**: Vercel (Serverless Python Runtime `@vercel/python`)

---

## 2. Key Features

### Academic Dashboard
- **Total Registered Students**: Live count from the PostgreSQL database.
- **Daily Attendance Breakdown**: Counts for **Present**, **Absent**, and **Leave** for any selected date (defaults to today).
- **Accurate Percentage Metrics**:
  - Daily Attendance Rate.
  - Overall Cumulative College Attendance Rate.
  - **Important Rule**: *Leave is strictly excluded from the percentage denominator*:
    $$\text{Attendance \%} = \frac{\text{Present}}{\text{Present} + \text{Absent}} \times 100$$
- **Low-Attendance Alerts**: Instant alert cards and flags for students falling below the 75% attendance threshold.
- **Resilient Database Notice**: If `DATABASE_URL` is unconfigured, the dashboard clearly displays a setup guide rather than crashing or writing temporary mock files.

### Student Management
- **Add, Edit, View, and Delete**: Full student lifecycle management.
- **Fields**: Roll Number (unique), Full Name, Class / Course, and optional Email.
- **Duplicate Prevention**: Case-insensitive roll number collision checks enforced both in application logic and at the database level (`UNIQUE` constraint).
- **Cascade Deletion**: Safely removes all associated attendance records when a student is deleted.
- **Search & Filter**: Real-time filtering by course and keyword searching across roll number, name, and email.

### Attendance Management
- **Date Selector**: Select any date to record or update attendance.
- **Roll Call Table**: Clean listing of registered students grouped by course.
- **Quick-Mark Helpers**: One-click buttons to mark **All Present**, **All Absent**, **All Leave**, or **Clear**.
- **Idempotent Updates**: Existing records for the selected student and date are updated in place without duplicate entries.
- **Student History**: Chronological audit trail of all sessions for each individual student.

### Reports & CSV Operations
- **Filtered Attendance Log**: Filter by specific student, course, status (Present, Absent, Leave), and date range (Start / End date).
- **Summary Metrics**: Instant dynamic totals and attendance percentage for the filtered query.
- **CSV Export**: Download filtered attendance logs using Python's built-in `csv` module.
- **CSV Batch Import**:
  - Bulk import students from a `.csv` file with headers: `roll_number, name, course, email`.
  - Validates missing columns and empty fields.
  - Detects duplicate roll numbers within the CSV and against existing database records.
  - Provides detailed feedback reporting successfully added students and specific skipped rows.
- **Template Download**: In-app link to download a sample CSV import file.

---

## 3. Project Directory Structure

```
StudentAttendance_Tracker/
├── api/
│   └── index.py            # Vercel serverless WSGI entrypoint
├── templates/
│   ├── base.html           # Main layout with responsive sidebar and alert banners
│   ├── dashboard.html      # Academic dashboard with metrics & low-attendance alerts
│   ├── students.html       # Student directory, search, filter & CSV import modal
│   ├── student_form.html   # Add/Edit student form with server validation
│   ├── student_history.html# Individual student attendance history & percentages
│   ├── attendance.html     # Attendance roll call table & status radio controls
│   └── reports.html        # Comprehensive reports, date range filters & CSV export
├── static/
│   └── css/
│       └── styles.css      # Custom styling, fonts, and segmented controls
├── tests/
│   ├── test_attendance_tracker.py  # Unit and integration test suite
│   └── test_unconfigured_mode.py   # Test verifying behavior when DB is unconfigured
├── app.py                  # Flask application factory, routes, and error handling
├── models.py               # SQLAlchemy models (Student, Attendance) and constraints
├── requirements.txt        # Production Python dependencies
├── vercel.json             # Vercel deployment routing configuration
├── .env.example            # Sample environment variables template
├── .gitignore              # Git ignore rules (protects credentials and virtualenv)
└── README.md               # Complete documentation and setup guide
```

---

## 4. Local Development Setup

### Step 1: Clone or Open Directory
```bash
cd StudentAttendance_Tracker
```

### Step 2: Create and Activate a Python Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
On macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` and set:
```ini
SECRET_KEY="your-random-secret-key"
DATABASE_URL="postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz.region.aws.neon.tech/neondb?sslmode=require"
```
*(If you do not have a PostgreSQL database yet, see Section 5 below.)*

### Step 5: Run Database Schema Initialization
To create the database tables in your PostgreSQL database:
```bash
flask --app app init-db
```
*(You can also click the "Test Database Connection & Initialize Tables" button directly on the dashboard once the app is running.)*

### Step 6: Start the Local Development Server
```bash
python app.py
```
Open your browser at [http://localhost:5000](http://localhost:5000).

### Step 7: Run the Test Suite
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 5. Hosted PostgreSQL Database Setup (Neon)

To persist data in production without relying on local files or temporary in-memory storage, use Neon Serverless PostgreSQL:

### Step 1: Create a Free Neon Account
1. Visit [https://neon.tech](https://neon.tech) and sign up (using GitHub, Google, or Email).
2. Click **Create Project**.
3. Name your project (e.g. `student-attendance-db`).
4. Select your preferred AWS region (choose the region closest to you or your Vercel deployment region).
5. Click **Create Project**.

### Step 2: Obtain your Connection String
1. In the Neon Dashboard, locate the **Connection Details** widget on your project dashboard.
2. Select **Connection String** with **Pooled connection** enabled (recommended for serverless) or Direct connection.
3. Choose **psycopg2** or **SQLAlchemy** from the dropdown, or copy the URI format:
   ```
   postgresql://neondb_owner:YOUR_PASSWORD@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
   *(Keep your password safe. Never commit this URL to GitHub or share it publicly!)*

---

## 6. Vercel Deployment Instructions

### Step 1: Push Code to GitHub
1. Initialize Git in the project root:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Student Attendance Tracker"
   ```
2. Create a new repository on GitHub (private or public).
3. Push your repository:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/student-attendance-tracker.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Import into Vercel
1. Log in to your [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** &rarr; **Project**.
3. Select your GitHub repository (`student-attendance-tracker`) and click **Import**.

### Step 3: Configure Environment Variables in Vercel
Before clicking Deploy, expand the **Environment Variables** section:

1. **`DATABASE_URL`**:
   - Value: Paste your complete Neon PostgreSQL connection string:
     `postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz.region.aws.neon.tech/neondb?sslmode=require`
2. **`SECRET_KEY`**:
   - Value: A secure, random 32+ character string (e.g. `d8f2a6e9c4b710538a1f2e6d9c8b74a1`).

### Step 4: Deploy
1. Click **Deploy**.
2. Vercel will install the dependencies from `requirements.txt` and package the application using `@vercel/python`.
3. Once deployed, open your live Vercel URL.
4. On the live site, navigate to the Dashboard:
   - If tables are not yet initialized, click **Test Database Connection & Initialize Tables** or visit the page; the schema will initialize automatically on your hosted PostgreSQL instance.
   - The indicator in the sidebar footer will display a green badge: `PostgreSQL Connected`.
5. Test creating a student and marking attendance, then refresh the browser to confirm your data is permanently persisted.

---

## 7. Security Best Practices Implemented

- **CSRF Protection**: All POST forms include CSRF verification via `Flask-WTF`.
- **SQL Injection Prevention**: All queries use SQLAlchemy ORM parameterized statements.
- **Environment Separation**: Secrets and database credentials are kept out of version control via `.gitignore`.
- **Serverless Resilience**: Engine configured with `pool_pre_ping=True` and connection recycling to handle serverless cold starts and auto-suspending databases gracefully.
