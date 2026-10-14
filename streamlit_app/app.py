"""
Student Attendance Tracker - Streamlit Web Application
A full-featured, responsive Python web application for student management,
daily attendance marking, bulk multi-format import (CSV, TXT, PDF, Excel),
analytics reports with <75% defaulter detection, and CSV export.

Configured for Streamlit Community Cloud and local execution.
"""

import os
import io
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

# Ensure backend directory is in python path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from backend import (
    Database,
    StudentManager,
    AttendanceManager,
    BulkImportManager,
    ReportsManager,
    PDFParser,
    DuplicateRollNumberError,
    ValidationError,
    ImportValidationStatus,
    DEFAULT_DB_PATH,
    TEMPLATES_DIR,
    ATTENDANCE_DEFICIT_THRESHOLD,
    VALID_STATUSES,
    seed_demo_data
)

# =====================================================================
# 1. STREAMLIT APP CONFIGURATION & THEMING
# =====================================================================

st.set_page_config(
    page_title="TrackAttend — Student Attendance Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    /* Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 16px 20px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetric"]:hover {
        border-color: #3B82F6;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Table headers and rows */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Warning Box */
    .defaulter-alert {
        background-color: #FEF2F2;
        border-left: 5px solid #EF4444;
        padding: 14px 18px;
        border-radius: 6px;
        color: #991B1B;
        margin-bottom: 18px;
        font-weight: 500;
    }

    /* Tag styles */
    .badge-success {
        background-color: #ECFDF5;
        color: #065F46;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85em;
    }
    .badge-danger {
        background-color: #FEF2F2;
        color: #991B1B;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85em;
    }
    .badge-warning {
        background-color: #FFFBEB;
        color: #92400E;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)


# =====================================================================
# 2. STATE AND BACKEND INITIALIZATION
# =====================================================================

@st.cache_resource
def get_backend():
    """Cache database and managers across Streamlit rerun cycles."""
    db = Database(DEFAULT_DB_PATH)
    sm = StudentManager(db)
    am = AttendanceManager(db)
    im = BulkImportManager(db, sm)
    rm = ReportsManager(db)
    return db, sm, am, im, rm

db, student_mgr, att_mgr, importer, reports_mgr = get_backend()

# Seed initial demonstration data if database is brand new
if student_mgr.get_total_students_count() == 0:
    seed_demo_data(db, student_mgr, att_mgr)

# Ensure navigation state
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

if "bulk_import_result" not in st.session_state:
    st.session_state.bulk_import_result = None


# =====================================================================
# 3. SIDEBAR NAVIGATION & SYSTEM INFO
# =====================================================================

with st.sidebar:
    st.markdown("## 🎓 **TrackAttend**")
    st.caption("College Student Attendance Tracker")
    st.markdown("---")

    page_selection = st.radio(
        "Navigation",
        [
            "📊 Dashboard",
            "👥 Students Directory",
            "📅 Mark Attendance",
            "📥 Bulk Import",
            "📈 Reports & Analytics"
        ],
        index=[
            "📊 Dashboard",
            "👥 Students Directory",
            "📅 Mark Attendance",
            "📥 Bulk Import",
            "📈 Reports & Analytics"
        ].index(st.session_state.page if st.session_state.page.startswith(("📊", "👥", "📅", "📥", "📈")) else f"📊 {st.session_state.page}")
        if any(st.session_state.page in p for p in ["Dashboard", "Students", "Attendance", "Import", "Reports"]) else 0
    )

    # Clean selection name
    cleaned_page = page_selection.split(" ", 1)[1]
    st.session_state.page = cleaned_page

    st.markdown("---")
    st.markdown("### ⚙️ **Database Controls**")
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
    with col_r2:
        if st.button("🧪 Reset Demo", use_container_width=True, help="Reload initial sample college dataset"):
            seed_demo_data(db, student_mgr, att_mgr)
            st.success("Sample dataset reloaded!")
            st.rerun()

    # Cloud Hosting Notice (Ephemeral Storage Explanation)
    st.markdown("---")
    st.info(
        "💡 **Cloud Persistence Notice:**\n\n"
        "Streamlit Community Cloud runs in ephemeral Linux containers. "
        "Local SQLite files persist during the active session, but will reset "
        "when the cloud container restarts or redeploys.\n\n"
        "• *For persistent cloud production, connection to a hosted database (e.g. Supabase, PostgreSQL) is recommended.*",
        icon="ℹ️"
    )
    
    st.caption(f"Storage: `SQLite (attendance_tracker.db)`")
    st.caption("Environment: Python + Streamlit")


# =====================================================================
# 4. VIEW: 📊 DASHBOARD
# =====================================================================

if st.session_state.page == "Dashboard":
    st.title("📊 Attendance Dashboard")
    st.caption("Overview of class attendance, student metrics, and daily trends")

    # Date selector bar
    top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
    with top_col1:
        selected_dash_date = st.date_input("Select Date", value=date.today())
    with top_col2:
        st.write("")
        st.write("")
        if st.button("📅 Today", use_container_width=True):
            selected_dash_date = date.today()
    with top_col3:
        st.write("")
        st.write("")
        if st.button("⏮️ Yesterday", use_container_width=True):
            selected_dash_date = date.today() - timedelta(days=1)

    date_str = selected_dash_date.strftime("%Y-%m-%d")
    stats = att_mgr.get_date_stats(date_str)

    # Low attendance alert banner
    defaulters = reports_mgr.get_attendance_report(only_defaulters=True)
    if defaulters:
        st.markdown(
            f"""
            <div class="defaulter-alert">
                ⚠️ <strong>ATTENDANCE DEFICIT ALERT:</strong> {len(defaulters)} student(s) currently fall below 
                the mandatory <strong>75% attendance threshold</strong>. Check the <em>Reports & Analytics</em> tab for the defaulters list.
            </div>
            """,
            unsafe_allow_html=True
        )

    # 5 KPI Metric Cards
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Students", stats["total_students"], help="Total registered students in system")
    with m2:
        st.metric("Present Today", stats["present_count"], delta=f"{stats['unmarked_count']} unmarked", delta_color="off")
    with m3:
        st.metric("Absent Today", stats["absent_count"])
    with m4:
        st.metric("On Leave", stats["leave_count"], help="Approved absence leaves (excluded from rate calculation)")
    with m5:
        st.metric("Attendance Rate", f"{stats['percentage']}%", help="Present / (Present + Absent) * 100")

    st.markdown("---")

    # Quick Action Buttons
    st.markdown("#### ⚡ Quick Actions")
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("📅 Mark Class Attendance", use_container_width=True, type="primary"):
            st.session_state.page = "Mark Attendance"
            st.rerun()
    with qa2:
        if st.button("📥 Bulk Import Students", use_container_width=True):
            st.session_state.page = "Bulk Import"
            st.rerun()
    with qa3:
        if st.button("👥 View Student Directory", use_container_width=True):
            st.session_state.page = "Students Directory"
            st.rerun()
    with qa4:
        if st.button("📈 View Defaulter Reports", use_container_width=True):
            st.session_state.page = "Reports & Analytics"
            st.rerun()

    st.markdown("---")

    # Recent Attendance Activity
    st.markdown("#### 🕒 Recent Attendance Sessions")
    recent = att_mgr.get_recent_activity(limit=10)
    if recent:
        df_recent = pd.DataFrame(recent)
        df_recent["class_name"] = df_recent["class_name"].apply(lambda c: c if c else "All / General")
        df_recent["percentage"] = df_recent["percentage"].apply(lambda p: f"{p}%")
        df_recent.rename(columns={
            "attendance_date": "Date",
            "class_name": "Class / Branch",
            "total_marked": "Total Marked",
            "present_count": "Present",
            "absent_count": "Absent",
            "leave_count": "Leave",
            "percentage": "Attendance %"
        }, inplace=True)
        st.dataframe(df_recent, use_container_width=True, hide_index=True)
    else:
        st.info("No attendance records recorded yet. Use 'Mark Class Attendance' to start logging attendance.")


# =====================================================================
# 5. VIEW: 👥 STUDENTS DIRECTORY
# =====================================================================

elif st.session_state.page == "Students Directory":
    st.title("👥 Student Directory")
    st.caption("Manage student registrations, search records, update details, or remove students.")

    # Top stats and action
    total_st = student_mgr.get_total_students_count()
    top_col, btn_col = st.columns([3, 1])
    with top_col:
        st.write(f"**Total Registered Students:** `{total_st}`")
    with btn_col:
        with st.popover("➕ Add Single Student", use_container_width=True):
            with st.form("add_student_form", clear_on_submit=True):
                st.subheader("Add New Student")
                new_roll = st.text_input("Roll Number *", placeholder="e.g. 2026-CSE-015")
                new_name = st.text_input("Full Name *", placeholder="e.g. Aryan Sharma")
                c1, c2 = st.columns(2)
                with c1:
                    new_class = st.text_input("Class / Dept", placeholder="e.g. CSE")
                with c2:
                    new_sec = st.text_input("Section", placeholder="e.g. A")
                
                submitted = st.form_submit_button("Save Student", type="primary")
                if submitted:
                    try:
                        student_mgr.add_student(new_roll, new_name, new_class, new_sec)
                        st.success(f"Student '{new_name}' ({new_roll}) added successfully!")
                        st.rerun()
                    except (DuplicateRollNumberError, ValidationError) as e:
                        st.error(str(e))

    # Search and Filter Controls
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])
    with f_col1:
        search_query = st.text_input("🔍 Search by Name or Roll No", placeholder="Type to filter...")
    with f_col2:
        class_options = ["All"] + student_mgr.get_distinct_classes()
        selected_class = st.selectbox("Filter Class", class_options)
    with f_col3:
        sec_options = ["All"] + student_mgr.get_distinct_sections(class_name=selected_class if selected_class != "All" else None)
        selected_sec = st.selectbox("Filter Section", sec_options)
    with f_col4:
        st.write("")
        st.write("")
        if st.button("Reset Filters", use_container_width=True):
            st.rerun()

    # Query Students
    students = student_mgr.get_all_students(
        search_query=search_query,
        class_filter=selected_class,
        section_filter=selected_sec
    )

    if students:
        df_students = pd.DataFrame(students)
        df_display = df_students[["id", "roll_no", "name", "class_name", "section", "created_at"]].copy()
        df_display.rename(columns={
            "id": "ID",
            "roll_no": "Roll Number",
            "name": "Student Name",
            "class_name": "Class / Dept",
            "section": "Section",
            "created_at": "Registration Date"
        }, inplace=True)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Edit / Delete Section
        st.markdown("---")
        st.subheader("✏️ Manage Selected Student")
        student_choices = {f"{s['roll_no']} — {s['name']} ({s['class_name']}-{s['section']})": s for s in students}
        chosen_label = st.selectbox("Select a student to edit or delete:", list(student_choices.keys()))
        chosen_student = student_choices[chosen_label]

        edit_col, del_col = st.columns(2)
        with edit_col:
            with st.expander("📝 Edit Student Details"):
                with st.form("edit_form"):
                    e_roll = st.text_input("Roll Number", value=chosen_student["roll_no"])
                    e_name = st.text_input("Full Name", value=chosen_student["name"])
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        e_class = st.text_input("Class", value=chosen_student["class_name"])
                    with ec2:
                        e_sec = st.text_input("Section", value=chosen_student["section"])
                    if st.form_submit_button("Update Student", type="primary"):
                        try:
                            student_mgr.update_student(chosen_student["id"], e_roll, e_name, e_class, e_sec)
                            st.success(f"Student details updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
        with del_col:
            with st.expander("🗑️ Delete Student"):
                st.warning(f"Are you sure you want to delete **{chosen_student['name']} ({chosen_student['roll_no']})**?\n\nThis will permanently delete the student and their attendance history.")
                if st.button("Confirm Deletion", type="primary", key="confirm_del_btn"):
                    student_mgr.delete_student(chosen_student["id"])
                    st.success(f"Student deleted.")
                    st.rerun()

    else:
        st.info("No student records match your search or filter.")


# =====================================================================
# 6. VIEW: 📅 MARK ATTENDANCE
# =====================================================================

elif st.session_state.page == "Mark Attendance":
    st.title("📅 Mark & Manage Attendance")
    st.caption("Select date and class, mark individual student statuses, and save class attendance.")

    # Controls bar
    c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
    with c1:
        att_date = st.date_input("Attendance Date", value=date.today())
        att_date_str = att_date.strftime("%Y-%m-%d")
    with c2:
        class_list = ["All"] + student_mgr.get_distinct_classes()
        att_class = st.selectbox("Class Filter", class_list)
    with c3:
        sec_list = ["All"] + student_mgr.get_distinct_sections(class_name=att_class if att_class != "All" else None)
        att_sec = st.selectbox("Section Filter", sec_list)
    with c4:
        att_search = st.text_input("Filter Student", placeholder="Name or Roll...")

    # Fetch Sheet
    sheet = att_mgr.get_attendance_sheet(
        attendance_date=att_date_str,
        class_name=att_class,
        section=att_sec,
        search_query=att_search
    )

    has_existing, count = att_mgr.has_attendance_for_date(att_date_str, att_class, att_sec)
    if has_existing:
        st.success(f"✅ Loaded existing attendance records: **{count} student(s)** marked for **{att_date_str}**.")
    else:
        st.info(f"ℹ️ No saved attendance records yet for **{att_date_str}**. Mark and save below.")

    if not sheet:
        st.warning("No students found in the selected class/section. Add students or select another class.")
    else:
        # Quick mass actions
        qa_col1, qa_col2, qa_col3, _ = st.columns([1, 1, 1, 2])
        if "mass_action" not in st.session_state:
            st.session_state.mass_action = None

        with qa_col1:
            if st.button("✔ All Present", use_container_width=True):
                st.session_state.mass_action = "Present"
                st.rerun()
        with qa_col2:
            if st.button("✖ All Absent", use_container_width=True):
                st.session_state.mass_action = "Absent"
                st.rerun()
        with qa_col3:
            if st.button("Clear All", use_container_width=True):
                st.session_state.mass_action = "Unmarked"
                st.rerun()

        st.markdown("---")

        # Interactive attendance marking form
        with st.form("attendance_marking_form"):
            st.subheader(f"Attendance Sheet — {att_date_str}")
            
            updated_records = []
            cols_header = st.columns([1.5, 2.5, 1, 1, 2])
            cols_header[0].markdown("**Roll Number**")
            cols_header[1].markdown("**Student Name**")
            cols_header[2].markdown("**Class**")
            cols_header[3].markdown("**Sec**")
            cols_header[4].markdown("**Attendance Status**")

            p_live = 0
            a_live = 0
            l_live = 0

            for s in sheet:
                sid = s["student_id"]
                current_st = s.get("status")

                if st.session_state.mass_action == "Present":
                    default_st = "Present"
                elif st.session_state.mass_action == "Absent":
                    default_st = "Absent"
                elif st.session_state.mass_action == "Unmarked":
                    default_st = "Unmarked"
                else:
                    default_st = current_st if current_st in ("Present", "Absent", "Leave") else "Unmarked"

                options = ["Unmarked", "Present", "Absent", "Leave"]
                default_idx = options.index(default_st)

                row_cols = st.columns([1.5, 2.5, 1, 1, 2])
                row_cols[0].write(s["roll_no"])
                row_cols[1].write(s["name"])
                row_cols[2].write(s["class_name"] or "—")
                row_cols[3].write(s["section"] or "—")

                chosen_val = row_cols[4].selectbox(
                    f"status_{sid}",
                    options,
                    index=default_idx,
                    label_visibility="collapsed",
                    key=f"status_select_{sid}"
                )

                if chosen_val == "Present":
                    p_live += 1
                elif chosen_val == "Absent":
                    a_live += 1
                elif chosen_val == "Leave":
                    l_live += 1

                if chosen_val in ("Present", "Absent", "Leave"):
                    updated_records.append({"student_id": sid, "status": chosen_val})

            # Reset mass action flag
            st.session_state.mass_action = None

            st.markdown("---")
            save_col1, save_col2 = st.columns([2, 1])
            with save_col1:
                denom = p_live + a_live
                rate = round((p_live / denom * 100.0), 1) if denom > 0 else 0.0
                st.markdown(f"**Marked:** Present: `{p_live}` | Absent: `{a_live}` | Leave: `{l_live}` | Attendance Rate: `{rate}%`")
            with save_col2:
                save_btn = st.form_submit_button("💾 Save Class Attendance", type="primary", use_container_width=True)

            if save_btn:
                if not updated_records:
                    st.warning("Please mark at least one student as Present, Absent, or Leave before saving.")
                else:
                    try:
                        saved_count = att_mgr.save_batch_attendance(
                            attendance_date=att_date_str,
                            records=updated_records,
                            overwrite=True
                        )
                        st.success(f"🎉 Successfully saved attendance for {saved_count} students on {att_date_str}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save attendance: {str(e)}")


# =====================================================================
# 7. VIEW: 📥 BULK IMPORT
# =====================================================================

elif st.session_state.page == "Bulk Import":
    st.title("📥 Bulk Student Import")
    st.caption("Upload student rosters from CSV, TXT, PDF, or Excel documents with duplicate checks and validation preview.")

    # Sample Templates Download Bar
    st.markdown("#### 📄 Sample Templates")
    t1, t2, t3 = st.columns(3)
    with t1:
        csv_sample_path = TEMPLATES_DIR / "sample_students.csv"
        if csv_sample_path.exists():
            st.download_button(
                "📥 Download CSV Template",
                data=csv_sample_path.read_bytes(),
                file_name="sample_students.csv",
                mime="text/csv",
                use_container_width=True
            )
    with t2:
        txt_sample_path = TEMPLATES_DIR / "sample_students_pipe.txt"
        if txt_sample_path.exists():
            st.download_button(
                "📝 Download TXT Template",
                data=txt_sample_path.read_bytes(),
                file_name="sample_students_pipe.txt",
                mime="text/plain",
                use_container_width=True
            )
    with t3:
        with st.popover("📄 PDF Format Guide", use_container_width=True):
            st.markdown("""
            **Supported PDF Requirements:**
            - **Selectable text:** Must be an exported text PDF (Word/Excel/Student Portal).
            - **Supported formats:**
              - Labeled: `Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A`
              - Tabular: `101    Rahul Sharma    CSE    A`
            - **Scanned PDFs:** Pure image scans without text layer cannot be parsed directly.
            """)

    st.markdown("---")

    # Step 1: Upload File
    st.markdown("#### 📂 Step 1: Select Student File")
    uploaded_file = st.file_uploader(
        "Choose a CSV, TXT, PDF, or Excel file",
        type=["csv", "txt", "pdf", "xlsx", "xls"],
        help="Upload class roster for bulk insertion"
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_name = uploaded_file.name

        # Parse file on new upload
        if st.session_state.bulk_import_result is None or st.session_state.bulk_import_result.get("file_name") != file_name:
            with st.spinner("Parsing and validating student records..."):
                res = importer.load_file_content(file_name, file_bytes)
                st.session_state.bulk_import_result = res

        res = st.session_state.bulk_import_result

        if not res["success"]:
            if res.get("is_scanned_pdf"):
                st.error(f"❌ **Scanned PDF Detected:** {res['error']}")
            else:
                st.error(f"❌ **Parsing Error:** {res['error']}")
        else:
            summary = res["summary"]
            records = res["records"]

            # Step 2: Validation Metrics
            st.markdown("#### 📊 Step 2: Validation Summary")
            sm1, sm2, sm3, sm4, sm5 = st.columns(5)
            sm1.metric("Total Detected", summary["total_detected"])
            sm2.metric("Valid for Import", summary["valid_count"])
            sm3.metric("Dupes in File", summary["duplicate_file_count"])
            sm4.metric("In Database", summary["duplicate_db_count"])
            sm5.metric("Invalid Records", summary["invalid_count"])

            st.markdown("---")

            # Step 3: Preview Table
            st.markdown("#### 📋 Step 3: Record Preview & Selection")
            
            df_preview = pd.DataFrame(records)
            df_display = df_preview[["selected", "roll_no", "name", "class_name", "section", "status", "details"]].copy()
            df_display.rename(columns={
                "selected": "Import?",
                "roll_no": "Roll Number",
                "name": "Student Name",
                "class_name": "Class",
                "section": "Section",
                "status": "Validation Status",
                "details": "Details / Diagnosis"
            }, inplace=True)

            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # View unparsed / raw text expander
            if res.get("unparsed_items") or res.get("raw_text"):
                with st.expander("🔍 View Extraction Diagnostics & Raw Text"):
                    if res.get("unparsed_items"):
                        st.write("**Unparsed Lines:**")
                        for u in res["unparsed_items"]:
                            st.write(f"- Line {u.get('line_num', '?')}: `{u.get('text', '')}` ({u.get('reason', '')})")
                    if res.get("raw_text"):
                        st.text_area("Raw Extracted Text", res["raw_text"], height=200)

            # Step 4: Import Actions & Duplicate Handling
            st.markdown("---")
            st.markdown("#### ⚙️ Step 4: Confirm Import")

            d_col1, d_col2 = st.columns(2)
            with d_col1:
                dup_action = st.radio(
                    "Duplicate Handling Option:",
                    ["skip", "update"],
                    format_func=lambda v: "Skip duplicates (safely add only new students)" if v == "skip" else "Update existing students with details from file",
                    index=0
                )
            with d_col2:
                st.write("")
                st.write("")
                ready_count = summary["ready_to_import"]
                import_btn = st.button(
                    f"✅ Confirm & Import {ready_count} Students",
                    type="primary",
                    disabled=(ready_count == 0),
                    use_container_width=True
                )

            if import_btn:
                with st.spinner("Executing atomic SQLite transaction..."):
                    import_res = importer.execute_import(duplicate_action=dup_action)
                    if import_res["success"]:
                        st.success(
                            f"🎉 **Bulk Import Successful!**\n\n"
                            f"- Added: **{import_res['added']}**\n"
                            f"- Updated: **{import_res['updated']}**\n"
                            f"- Skipped: **{import_res['skipped']}**\n"
                            f"- Failed: **{import_res['failed']}**"
                        )
                        st.session_state.bulk_import_result = None
                        st.balloons()
                    else:
                        st.error(f"Import failed: {import_res.get('error', 'Unknown error')}")


# =====================================================================
# 8. VIEW: 📈 REPORTS & ANALYTICS
# =====================================================================

elif st.session_state.page == "Reports & Analytics":
    st.title("📈 Attendance Reports & Analytics")
    st.caption("Class reports, attendance percentages, <75% defaulter threshold identification, and CSV export.")

    # Filter Controls
    r_col1, r_col2, r_col3, r_col4 = st.columns([1.5, 1, 1, 1.5])
    with r_col1:
        rep_search = st.text_input("Search Student", placeholder="Roll No or Name...")
    with r_col2:
        rep_class = st.selectbox("Class", ["All"] + student_mgr.get_distinct_classes(), key="rep_class")
    with r_col3:
        rep_sec = st.selectbox("Section", ["All"] + student_mgr.get_distinct_sections(class_name=rep_class if rep_class != "All" else None), key="rep_sec")
    with r_col4:
        only_defaulters = st.checkbox("⚠️ Only < 75% Defaulters", value=False)

    # Date Range Expander
    with st.expander("📅 Date Range Filter (Optional)"):
        dr1, dr2 = st.columns(2)
        with dr1:
            start_d = st.date_input("From Date", value=None)
        with dr2:
            end_d = st.date_input("To Date", value=None)

    start_d_str = start_d.strftime("%Y-%m-%d") if start_d else None
    end_d_str = end_d.strftime("%Y-%m-%d") if end_d else None

    # Fetch report
    report_data = reports_mgr.get_attendance_report(
        class_filter=rep_class,
        section_filter=rep_sec,
        start_date=start_d_str,
        end_date=end_d_str,
        search_query=rep_search,
        only_defaulters=only_defaulters
    )

    # Summary Metrics
    total_rep = len(report_data)
    active_st = sum(1 for r in report_data if r["has_history"])
    avg_pct = round(sum(r["percentage"] for r in report_data if r["has_history"]) / active_st, 1) if active_st > 0 else 0.0
    defaulter_count = sum(1 for r in report_data if r["is_low"])
    max_days = max((r["total_days"] for r in report_data), default=0)

    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("Reported Students", total_rep, f"{active_st} active")
    rm2.metric("Average Attendance", f"{avg_pct}%")
    rm3.metric("Students < 75%", defaulter_count, delta="Defaulters" if defaulter_count > 0 else "None", delta_color="inverse")
    rm4.metric("Max Days Tracked", max_days)

    st.markdown("---")

    # CSV Download Button
    top_t_col, dl_col = st.columns([3, 1])
    with top_t_col:
        st.subheader("Attendance Summary Table")
    with dl_col:
        if report_data:
            csv_str = reports_mgr.generate_csv_string(report_data)
            st.download_button(
                "📥 Export to CSV",
                data=csv_str.encode("utf-8-sig"),
                file_name=f"attendance_report_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True
            )

    if report_data:
        df_rep = pd.DataFrame(report_data)
        df_rep_display = df_rep[["roll_no", "name", "class_name", "section", "total_days", "present_days", "absent_days", "leave_days", "percentage", "status_label"]].copy()
        df_rep_display["percentage"] = df_rep_display["percentage"].apply(lambda p: f"{p}%")
        df_rep_display.rename(columns={
            "roll_no": "Roll Number",
            "name": "Student Name",
            "class_name": "Class",
            "section": "Section",
            "total_days": "Days Recorded",
            "present_days": "Present",
            "absent_days": "Absent",
            "leave_days": "Leave",
            "percentage": "Attendance %",
            "status_label": "Attendance Status"
        }, inplace=True)

        st.dataframe(df_rep_display, use_container_width=True, hide_index=True)

        # Student History Modal
        st.markdown("---")
        st.subheader("📜 Individual Student History Log")
        st_options = {f"{r['roll_no']} — {r['name']} ({r['percentage']})": r["student_id"] for r in report_data}
        chosen_hist_label = st.selectbox("Select a student to view day-by-day attendance history:", list(st_options.keys()))
        chosen_sid = st_options[chosen_hist_label]

        hist = reports_mgr.get_student_history(chosen_sid)
        if hist:
            df_hist = pd.DataFrame(hist)
            df_hist = df_hist[["attendance_date", "day_name", "status"]].copy()
            df_hist.rename(columns={
                "attendance_date": "Date",
                "day_name": "Day of Week",
                "status": "Attendance Status"
            }, inplace=True)
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
        else:
            st.info("No attendance sessions recorded for this student.")

    else:
        st.info("No records matching the current report criteria.")
