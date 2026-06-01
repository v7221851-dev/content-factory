"""Точка входа для Streamlit Cloud. Main file path: streamlit_app.py"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_secrets() -> None:
    """Secrets должны попасть в env до импорта settings."""
    try:
        import streamlit as st

        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)):
                os.environ[str(key)] = str(value)
    except Exception:
        pass


_bootstrap_secrets()

from admin.app import main

main()
