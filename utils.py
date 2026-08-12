"""Utilidades de rutas y formato de lote (compatibles con PyInstaller)."""

from __future__ import annotations

import os
import re
import sys
from datetime import date


def resource_path(relative: str) -> str:
    """Ruta dinámica: desarrollo normal o bundle congelado (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def prefijo_lote(anio: int | None = None) -> str:
    """Prefijo de lote de planta: ``26LOC `` (año corto + LOC + espacio)."""
    y = anio if anio is not None else date.today().year
    return f"{y % 100:02d}LOC "


def normalizar_lote(texto: str, *, anio: int | None = None) -> str:
    """
    Normaliza a ``YYLOC N`` (ej. ``26LOC 15``).
    Acepta solo el número, ``26LOC15``, ``26LOC 15``, etc.
    Retorna ``""`` si no hay número de lote.
    """
    pref = prefijo_lote(anio)
    raw = (texto or "").replace("\u00a0", " ").strip()
    if not raw:
        return ""
    m = re.match(r"^\d{2}\s*LOC\s*(.*)$", raw, flags=re.IGNORECASE)
    if m:
        num = m.group(1).strip()
    elif raw.upper().startswith("LOC"):
        num = raw[3:].strip()
    else:
        num = raw
    num = re.sub(r"\s+", "", num)
    if not num:
        return ""
    return f"{pref}{num}"
