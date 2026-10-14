"""
🎓 TrackAttend - Student Attendance Tracker
Streamlit Application Entrypoint

Run locally:
    streamlit run app.py
or:
    python -m streamlit run app.py
or:
    python app.py
"""

import os
import sys
from pathlib import Path

# Add streamlit_app to sys.path so backend imports work seamlessly
STREAMLIT_APP_DIR = Path(__file__).resolve().parent / "streamlit_app"
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

# If user runs directly via `python app.py` (not via `streamlit run`), invoke Streamlit CLI
if __name__ == "__main__" and "streamlit.runtime" not in sys.modules:
    try:
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", str(STREAMLIT_APP_DIR / "app.py")]
        sys.exit(stcli.main())
    except ImportError:
        pass

# When run via `streamlit run app.py`
app_script = STREAMLIT_APP_DIR / "app.py"
with open(app_script, "r", encoding="utf-8") as f:
    code = compile(f.read(), str(app_script), "exec")
    exec(code, globals())
