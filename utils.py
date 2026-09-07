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


def prefijo_lote(anio: int | None = None, sufijo: str = "LOC") -> str:
    """Prefijo de lote: ``26LOC`` (año corto + sufijo, sin espacio antes del número)."""
    y = anio if anio is not None else date.today().year
    return f"{y % 100:02d}{sufijo.upper()}"


def normalizar_lote(
    texto: str, *, anio: int | None = None, sufijo: str = "LOC"
) -> str:
    """
    Normaliza a ``YYLOCN`` (ej. ``26LOC3606``), sin espacio entre sufijo y número.

    Acepta solo el número, ``26LOC3606``, ``26LOC 3606``, otro sufijo (``26ABC15``), etc.
    Retorna ``""`` si no hay número de lote.
    """
    y = anio if anio is not None else date.today().year
    suf = sufijo.upper()
    pref = prefijo_lote(y, sufijo=suf)
    raw = (texto or "").replace("\u00a0", " ").strip()
    if not raw:
        return ""

    compact = re.sub(r"\s+", "", raw)

    # YY + letras + dígitos (ej. 26LOC3606, 26ABC15)
    m = re.match(r"^(\d{2})([A-Za-z]+)(\d+)$", compact, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1)}{m.group(2).upper()}{m.group(3)}"

    # Con espacios: 26 LOC 3606 / 26LOC 3606
    m = re.match(r"^(\d{2})\s*([A-Za-z]+)\s*(.+)$", raw, flags=re.IGNORECASE)
    if m:
        num = re.sub(r"\s+", "", m.group(3))
        if num.isdigit():
            return f"{m.group(1)}{m.group(2).upper()}{num}"

    # Sufijo por defecto + número: LOC3606 / LOC 3606
    m = re.match(rf"^{suf}\s*(.+)$", raw, flags=re.IGNORECASE)
    if m:
        num = re.sub(r"\s+", "", m.group(1))
        if num.isdigit():
            return f"{pref}{num}"

    # Solo número → prefijo del año en curso
    if compact.isdigit():
        return f"{pref}{compact}"

    return ""
