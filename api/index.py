import os
import sys
from pathlib import Path

# Add project root directory to sys.path so modules (models, app) are resolved correctly on Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app

# Vercel looks for the WSGI application callable named `app`
