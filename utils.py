"""Utilidades de rutas compatibles con PyInstaller."""

from __future__ import annotations

import os
import sys


def resource_path(relative: str) -> str:
    """Ruta dinámica: desarrollo normal o bundle congelado (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
