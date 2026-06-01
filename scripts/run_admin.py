#!/usr/bin/env python3
"""Запуск Streamlit-панели управления."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "admin" / "app.py"),
            "--server.port",
            "8501",
        ],
        cwd=str(ROOT),
        env=env,
        check=True,
    )
