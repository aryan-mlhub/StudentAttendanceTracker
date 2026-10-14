# 🎓 Student Attendance Tracker — Streamlit Web Application

A modern, responsive, Python-powered web application built with **Streamlit** and **SQLite** for managing student records, tracking daily attendance, bulk-importing class rosters (CSV, TXT, PDF, Excel), identifying low-attendance defaulters (< 75%), and exporting reports.

Developed for college Python experiential learning project submission and deployable directly on **Streamlit Community Cloud**.

---

## 🌟 Key Features

1. **📊 Executive Dashboard:**
   - Real-time KPIs: Total Registered Students, Present Today, Absent Today, Leaves, and Attendance Rate (%).
   - Dynamic date switcher (Today, Yesterday, Calendar picker).
   - Prominent **Attendance Deficit Warning Banner** (< 75% attendance threshold).
   - Recent attendance sessions activity table.

2. **👥 Student Directory:**
   - Full CRUD operations (Add, Edit, Delete with cascade protection).
   - Real-time search by name or roll number.
   - Dynamic class and section filters.
   - Prevents duplicate roll numbers with validation error prompts.

3. **📅 Daily Attendance Management:**
   - Date-specific class attendance sheets.
   - Quick mass actions (*Mark All Present*, *Mark All Absent*, *Clear All*).
   - Individual student status cycling (`Present`, `Absent`, `Leave`).
   - Leave days correctly excluded from percentage calculation denominator: $\text{Rate} = \frac{\text{Present}}{\text{Present} + \text{Absent}} \times 100$.
   - Atomic SQLite batch insertion with conflict update handling.

4. **📥 Multi-Format Bulk Import Wizard:**
   - Upload `.csv`, `.txt`, `.pdf`, `.xlsx`, or `.xls` files directly in the browser.
   - Intelligent column alias matching (`Roll No`, `Student Name`, `Branch`, `Section`, etc.).
   - Text PDF extraction using `pypdf`.
   - Scanned / Image-only PDF detection with clear diagnosis and troubleshooting tips.
   - In-memory validation with duplicate detection (both within-file and already in-database).
   - Duplicate conflict strategies: **Skip Duplicates** vs **Update Existing Details**.
   - Downloadable starter templates (CSV & TXT).

5. **📈 Reports & Defaulter Analytics:**
   - Dynamic filtering by search, class, section, date range, or *Only < 75% Defaulters*.
   - Chronological date-by-date student attendance history log.
   - One-click CSV export formatted with UTF-8 BOM encoding (`st.download_button`).

---

## 📁 Project Architecture & Separation

This web application is located in the `streamlit_app/` directory and is completely independent of the desktop Tkinter application:

```
StudentAttendanceTracker/
├── main.py                     # Original standalone Tkinter desktop application
├── requirements.txt            # Repository dependencies
├── backup_original/            # Backup of original source modules
├── templates/                  # Sample import templates
├── tests/                      # Automated unit and integration tests (37 passing)
└── streamlit_app/              # 🌐 Streamlit Web Application (Separate folder)
    ├── app.py                  # Streamlit web UI & interactive controllers
    ├── backend.py              # Pure Python decoupled business logic & SQLite layer
    ├── requirements.txt        # Web app dependencies for Cloud deployment
    ├── README.md               # Streamlit deployment documentation
    ├── attendance_tracker.db   # SQLite database instance
    └── templates/              # Sample CSV, TXT, and PDF templates
```

---

## ⚠️ Important Note on Cloud Storage (Streamlit Community Cloud)

> [!WARNING]
> **Ephemeral Filesystem Behavior in Cloud Containers:**
> Streamlit Community Cloud hosts applications inside ephemeral Linux containers.
> - **During an active session:** SQLite database read and write operations function normally and persist across page navigations and widget interactions.
> - **When the container sleeps or redeploys:** Any modifications written to the local SQLite file (`attendance_tracker.db`) in the container filesystem will be reset back to the state of the GitHub repository commit.
> - **Built-in Demo Seeder:** To ensure your college project evaluator can always test the app immediately even after a container reboot, `seed_demo_data()` automatically populates ~12 sample students across CSE and ECE with 5 days of realistic attendance and a sample defaulter. You can also click the **"🧪 Reset Demo"** button in the sidebar at any time.
> - **Production Recommendation:** For production deployments where permanent multi-user persistence across restarts is strictly required, connect this application to an external hosted database service (such as Supabase, Neon PostgreSQL, or Turso SQLite).

---

## 💻 Running Locally

### 1. Install Dependencies
Make sure you have Python 3.10+ installed:
```powershell
pip install -r streamlit_app/requirements.txt
```

### 2. Launch the Application
Run the Streamlit server:
```powershell
python -m streamlit run streamlit_app/app.py
```
Open your browser at `http://localhost:8501`.

---

## 🚀 Step-by-Step Deployment to Streamlit Community Cloud

### Step 1: Push Code to GitHub
Ensure your latest changes are pushed to your GitHub repository:
```powershell
git add .
git commit -m "Add deployable Streamlit web application"
git push origin main
```

### Step 2: Open Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with your GitHub account.
2. Click the **"New app"** button.

### Step 3: Configure Deployment Settings
Fill in the deployment form:
- **Repository:** `aryan-mlhub/Student_Attendance_Tracker`
- **Branch:** `main`
- **Main file path:** `streamlit_app/app.py`
- **App URL:** (Optional custom subdomain, e.g. `student-attendance-tracker-college`)

### Step 4: Click Deploy
Click **"Deploy!"**. Streamlit will install `streamlit_app/requirements.txt`, launch the container, and provide you with a live public URL (e.g., `https://student-attendance-tracker-xxxx.streamlit.app`).

---

## 🧪 Testing Summary

All features have been tested using automated unit tests and manual execution:

| Feature / Component | Test Status | Notes |
| :--- | :--- | :--- |
| **SQLite Schema & Indexes** | ✅ Tested | Auto-initialization, transactions, and foreign key cascades verified |
| **Student CRUD Operations** | ✅ Tested | Add, update, delete, search, class/section filtering tested |
| **Duplicate Roll Prevention** | ✅ Tested | Unique constraint and custom exception handling verified |
| **Attendance Sheet Marking** | ✅ Tested | Present/Absent/Leave batch saving and UPSERT verified |
| **Attendance Rate Formula** | ✅ Tested | Leaves correctly excluded from denominator |
| **< 75% Defaulter Detection** | ✅ Tested | Flagged correctly in reports, KPIs, and dashboard alerts |
| **CSV & TXT File Import** | ✅ Tested | Positional and alias header matching verified |
| **Text PDF Import** | ✅ Tested | `pypdf` extraction tested with `sample_students.pdf` |
| **Scanned PDF Diagnosis** | ✅ Tested | Detected low text density with OCR guidance message |
| **CSV Report Export** | ✅ Tested | File generation with UTF-8 BOM encoding verified |
| **Demo Data Seeding** | ✅ Tested | 12 students with 5-day attendance history verified |
| **Tesseract System OCR** | ℹ️ *Not Tested / Platform Dependent* | Native `tesseract` binary is not bundled in Streamlit Cloud Linux by default; scanned PDFs will prompt users to upload text-based PDFs or CSVs. |
