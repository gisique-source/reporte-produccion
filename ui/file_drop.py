"""Arrastrar y soltar archivos (tkinterdnd2). Opcional: si no está, no rompe la app."""

from __future__ import annotations

import os
import re
from typing import Callable, Optional

import tkinter as tk

_EXCEL_EXT = {".xlsx", ".xlsm", ".xls"}

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except ImportError:  # pragma: no cover
    DND_FILES = "DND_Files"  # type: ignore[misc, assignment]
    TkinterDnD = None  # type: ignore[misc, assignment]
    DND_AVAILABLE = False


def parse_drop_paths_with(widget: tk.Misc, data: str) -> list[str]:
    """Interpreta event.data de <<Drop>> (Windows/Linux)."""
    if not data or not str(data).strip():
        return []
    raw = str(data).strip()
    try:
        parts = list(widget.tk.splitlist(raw))
    except Exception:  # noqa: BLE001
        parts = []
    if not parts:
        for m in re.finditer(r"\{([^}]+)\}|(\S+)", raw):
            p = m.group(1) or m.group(2)
            if p:
                parts.append(p)
    out: list[str] = []
    for p in parts:
        p = str(p).strip().strip('"').strip("'")
        if p.startswith("file://"):
            p = p[7:]
            if re.match(r"^/[A-Za-z]:/", p):
                p = p[1:]
        if p:
            out.append(os.path.normpath(p))
    return out


def first_excel_path(paths: list[str]) -> Optional[str]:
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in _EXCEL_EXT and os.path.isfile(p):
            return p
    return None


def enable_file_drop(
    widget: tk.Misc,
    on_paths: Callable[[list[str]], None],
    *,
    on_enter: Optional[Callable[[], None]] = None,
    on_leave: Optional[Callable[[], None]] = None,
) -> bool:
    """Registra el widget como destino de archivos. False si DnD no está."""
    if not DND_AVAILABLE:
        return False
    try:
        widget.drop_target_register(DND_FILES)  # type: ignore[attr-defined]

        def _drop(event) -> None:  # noqa: ANN001
            paths = parse_drop_paths_with(widget, getattr(event, "data", "") or "")
            on_paths(paths)

        def _enter(_event=None) -> None:
            if on_enter:
                on_enter()

        def _leave(_event=None) -> None:
            if on_leave:
                on_leave()

        widget.dnd_bind("<<Drop>>", _drop)  # type: ignore[attr-defined]
        widget.dnd_bind("<<DragEnter>>", _enter)  # type: ignore[attr-defined]
        widget.dnd_bind("<<DragLeave>>", _leave)  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False
