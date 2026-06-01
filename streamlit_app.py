"""Точка входа для Streamlit Cloud. Main file path: streamlit_app.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin.app import main

main()
