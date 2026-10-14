# 🎓 Student Attendance Tracker (Desktop Tkinter & Web Streamlit)

A complete college attendance tracking and management system designed for college faculty and educational institutions. Features student management, daily attendance logging, multi-format bulk import (CSV, TXT, PDF, Excel), attendance percentage calculations, < 75% deficit alerts, and CSV exports.

Available in two versions:
1. **🌐 Web Application (`streamlit_app/`):** Streamlit-based web interface deployable directly to **Streamlit Community Cloud**.
2. **🖥️ Desktop Application (`main.py`):** Standalone Tkinter/ttk desktop interface operating 100% offline.

---

## ⚡ Quick Launch

### 🌐 Run Streamlit Web Application
```powershell
pip install -r streamlit_app/requirements.txt
python -m streamlit run streamlit_app/app.py
```

### 🖥️ Run Tkinter Desktop Application
```powershell
python main.py
```

---

## 🌟 Key Highlights & Features

### 1. 📥 Bulk Student Import (Most Important Feature)
Faculty members can add an entire class roster in seconds instead of keying in students one by one:
- **Supported Formats**:
  - **`.csv`**: Automatically detects headers (`Roll No`, `Student Name`, `Class`, `Section`) with support for variations like `roll_no`, `Roll Number`, `Name`, `Branch`, `Division`.
  - **`.txt`**: Handles structured key-value lines (`Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A`) as well as comma/pipe/tab delimited records (`101, Rahul Sharma, CSE, A`).
  - **`.pdf`**: Extracts student records from text-based PDFs using `pypdf`, intelligently identifying roll numbers and names while filtering out headers, footers, and page numbers.
  - **`.xlsx`**: Native Excel spreadsheet import via `openpyxl`.
- **Scanned PDF Detection**: If an uploaded PDF is image-only with no extractable text characters, the application detects this condition and explains OCR requirements clearly.
- **5-Step Guided Faculty Workflow**:
  1. **Select File**: Choose CSV, TXT, PDF, or XLSX and view file size and metadata.
  2. **Preview Data**: Review extracted rows in a clear table with validation status badges.
  3. **Review & Edit**: Toggle selection, edit individual records directly in the preview, remove invalid rows, or select all valid rows.
  4. **Duplicate Handling Choice**: Choose between **Skip duplicates** (safely add only new students) or **Update existing student details**.
  5. **Transactional Database Import**: Atomic SQLite transactions guarantee that data is either imported completely or rolled back safely upon any system failure.
- **Built-in Sample Templates**: One-click download buttons for `sample_students.csv`, `sample_students.txt`, and PDF formatting guidelines.

### 2. 👥 Student Directory Management
- View all registered students with sorting by clicking any column header.
- Instant live search by student name or roll number.
- Filter by Class and Section with dynamic dropdowns.
- Add single students manually with field validation.
- Edit student records with a double-click or edit button.
- Delete student with confirmation dialog (cascading removal of attendance records).

### 3. 📅 Attendance Marking & Historical Editing
- Class-wise attendance marking for any selected date (`YYYY-MM-DD`).
- Statuses supported: **Present (P)**, **Absent (A)**, and **Leave (L)**.
- Interactive status toggling: Double-click any row to cycle through `Present -> Absent -> Leave -> Present`.
- Quick batch actions: **Mark All Present**, **Mark All Absent**, or **Clear All**.
- Overwrite protection: Displays a warning if attendance has already been recorded for that class and date before overwriting.
- Automatic persistence: All records saved permanently in SQLite.

### 4. 📊 Real-Time Dashboard
- Summary metric cards: Total Registered Students, Present Today, Absent Today, On Leave Today, and Daily Attendance Rate %.
- Date switcher to inspect attendance for Today, Yesterday, or any custom date.
- Defaulter alert banner: Instantly warns faculty when students drop below the 75% attendance threshold.
- Recent attendance activity feed showing the latest marked classes and percentages.
- One-click shortcuts for Quick Actions.

### 5. 📈 Attendance Reports & Defaulter Tracking
- Class-wise and individual attendance analytics.
- Date-range filter (Start Date to End Date).
- **Attendance Percentage Formula**:
  $$\text{Attendance Percentage} = \frac{\text{Present Days}}{\text{Present Days} + \text{Absent Days}} \times 100$$
  *(Approved Leave days do not penalize students and are excluded from the denominator)*.
- **75% Threshold Alert**: Highlights students below 75% in high-contrast red warning status.
- Single-student detailed chronological log: Double-click any student in reports to view their complete date-by-date attendance history.
- **One-Click CSV Export**: Save filtered attendance reports as a formatted CSV file.

---

## 🛠️ Technology Stack

| Layer | Technology | Details |
| :--- | :--- | :--- |
| **Language** | Python 3 | Core language (3.10+) |
| **GUI Framework** | Tkinter & `ttk` | Modern desktop UI with custom styles |
| **Database** | SQLite3 | Local embedded database with foreign-key cascade |
| **PDF Extraction** | `pypdf` | Extract text-based student registers |
| **Excel Support** | `openpyxl` | Read `.xlsx` class rosters |
| **File Formats** | Standard Library (`csv`, `pathlib`, `re`, `datetime`) | Fast, native, and robust file parsing |

---

## 📂 Project Structure

```text
StudentAttendanceTracker/
├── main.py                     # Main application entry point & navigation controller
├── database.py                 # SQLite database layer, schema & atomic transactions
├── student_manager.py          # Student CRUD, live filtering, and duplicate validation
├── attendance_manager.py       # Attendance recording, stats, and historical queries
├── bulk_import.py              # 5-step bulk import engine, validation & transactional commit
├── pdf_parser.py               # PDF text extraction, layout parsing & scanned PDF detector
├── reports.py                  # Analytics engine, 75% defaulter detection & CSV export
├── requirements.txt            # Python dependencies (pypdf, openpyxl)
├── README.md                   # Complete documentation and user manual
├── .gitignore                  # Git exclusions for database and temporary files
│
├── templates/                  # Sample templates and generators
│   ├── sample_students.csv     # Sample CSV class list
│   ├── sample_students_pipe.txt# Sample TXT with pipe-separated records
│   ├── sample_students_comma.txt# Sample TXT with comma-delimited records
│   ├── sample_students.pdf     # Valid text-based sample PDF register
│   ├── sample_scanned.pdf      # Textless sample PDF to test scanned document detection
│   └── generate_sample_pdf.py  # Utility script to generate sample test PDFs
│
├── ui/                         # Modular User Interface
│   ├── styles.py               # Modern Navy & Slate design system, tokens & ttk styles
│   ├── components.py           # StatCard, CustomTable with sorting, and modal dialogs
│   └── views/
│       ├── dashboard_view.py   # Overview metrics, date switcher, and recent activity
│       ├── students_view.py    # Student directory, search, and CRUD
│       ├── import_view.py      # Guided bulk import wizard with preview table
│       ├── attendance_view.py  # Class attendance sheet with quick toggles
│       └── reports_view.py     # Attendance summaries, defaulter alert & CSV export
│
└── tests/                      # Automated test suite (25 tests)
    ├── test_database.py        # Database transactions, foreign keys & rollbacks
    ├── test_parsers.py         # CSV, TXT (pipe & comma), text PDF & scanned PDF tests
    ├── test_bulk_import.py     # 100+ CSV import, duplicates, selectivity & update modes
    ├── test_attendance.py      # Attendance saving, percentage formula & persistence
    ├── test_reports.py         # Defaulter detection (< 75%) and CSV export verification
    └── test_e2e_workflow.py    # End-to-end full user journey integration test
```

---

## 🚀 Installation & Running

### 1. Prerequisites
Ensure **Python 3.10 or higher** is installed on your Windows machine:
```powershell
python --version
```

### 2. Install Dependencies
Open a PowerShell or Command Prompt terminal in the project directory:
```powershell
pip install -r requirements.txt
```

### 3. Launch the Application
Run the main Python script:
```powershell
python main.py
```

---

## 🧪 Running Automated Tests

A comprehensive suite of 25 unit, integration, and end-to-end tests is included:

```powershell
python -m unittest discover tests
```

To run individual test modules:
```powershell
python -m unittest tests/test_database.py
python -m unittest tests/test_parsers.py
python -m unittest tests/test_bulk_import.py
python -m unittest tests/test_attendance.py
python -m unittest tests/test_reports.py
python -m unittest tests/test_e2e_workflow.py
```

---

## 📋 Faculty User Guide

### How to Bulk Import Students
1. Launch the application and click **📥 Bulk Import** on the sidebar.
2. Click **Download CSV Template** or **Create TXT Template** if you need reference formats.
3. Click **Browse & Select File...** and choose your `.csv`, `.txt`, `.pdf`, or `.xlsx` file.
4. The system automatically scans the file:
   - Roll numbers already in your database are highlighted as **Exists in Database**.
   - Duplicates within the same file are highlighted as **Duplicate in File**.
   - Incomplete rows missing a roll number or name are highlighted as **Missing Field**.
5. Faculty can:
   - Double-click any row to fix a typo or update the details before importing.
   - Click **Select All Valid** or manually check/uncheck rows.
   - Choose whether existing roll numbers should be skipped or updated.
6. Click **✅ Confirm & Import Students**. The records are committed to the SQLite database and will immediately appear in the **Students Directory**, **Attendance Sheet**, and **Reports**.

### Marking Attendance
1. Click **📅 Attendance** on the sidebar.
2. Select the class (e.g., `CSE`) and section (e.g., `A`).
3. Set the date (defaults to today's date).
4. Click **✔ Mark All Present** to quickly mark everyone present, then click individual absent students to toggle their status to **Absent** or **Leave**.
5. Click **💾 Save Attendance for Class**.

### Viewing Reports & Exporting
1. Click **📈 Reports** on the sidebar.
2. Select your class and date range.
3. Check **⚠️ Only < 75% Defaulters** to view only students whose attendance is below the mandatory requirement.
4. Double-click any student to view their date-by-date attendance history.
5. Click **📥 Export Filtered Report to CSV** to save the report to your computer.

---

## 🔒 Data Safety & Offline Guarantee
- **Permanent SQLite Storage**: Data is saved to `attendance_tracker.db` in the application directory.
- **Transactions with Rollback**: If an import or batch save encounters an unexpected error, SQLite rolls back the transaction completely, preventing data corruption.
- **Offline Operation**: Works entirely on the local machine with no cloud logins, third-party trackers, or internet connection needed.
