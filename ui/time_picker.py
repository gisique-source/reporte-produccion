"""Selector de hora en intervalos de 15 minutos (00:00 … 23:45)."""

from __future__ import annotations

import re
from datetime import datetime, time
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from ui.widgets import Theme

HORAS_15MIN: list[str] = [
    f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)
]


def snap_hora_15(texto: str, *, default: Optional[str] = None) -> str:
    """Normaliza a HH:MM en la cuadrícula de 15 minutos más cercana."""
    t = parse_hora(texto)
    if t is None:
        if default:
            return default
        now = datetime.now().time()
        t = now
    total = t.hour * 60 + t.minute
    snapped = int(round(total / 15.0) * 15) % (24 * 60)
    return f"{snapped // 60:02d}:{snapped % 60:02d}"


def parse_hora(texto: str) -> Optional[time]:
    """Acepta HH:MM, H:MM, 12h con a.m./p.m."""
    s = (texto or "").strip()
    if not s:
        return None
    m = re.match(
        r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)?$",
        s,
        re.I,
    )
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    ampm = (m.group(4) or "").lower().replace(".", "").replace(" ", "")
    if ampm.startswith("p") and hh < 12:
        hh += 12
    if ampm.startswith("a") and hh == 12:
        hh = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return time(hh, mm)


def combinar_fecha_hora(dia, hora_txt: str) -> str:
    """YYYY-MM-DD HH:MM:SS a partir de date + 'HH:MM'."""
    hhmm = snap_hora_15(hora_txt)
    h, m = map(int, hhmm.split(":"))
    return datetime(dia.year, dia.month, dia.day, h, m, 0).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def hora_etiqueta_12h(hhmm: str) -> str:
    """Formato de impresión: 2:30 pm."""
    t = parse_hora(hhmm)
    if t is None:
        return hhmm
    return t.strftime("%I:%M %p").lstrip("0").lower()


class TimePicker(tk.Frame):
    """Combobox readonly con las 96 franjas de 15 minutos."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        textvariable: Optional[tk.StringVar] = None,
        value: Optional[str] = None,
        bg: str = Theme.PANEL,
        width: int = 6,
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master, bg=bg)
        self.on_change = on_change
        self.var = textvariable or tk.StringVar()
        self._syncing = False

        style = ttk.Style()
        style.configure(
            "Time.TCombobox",
            fieldbackground=Theme.INPUT_BG,
            background=Theme.PANEL,
            foreground=Theme.FG,
            arrowcolor=Theme.FG,
        )
        self.cb = ttk.Combobox(
            self,
            textvariable=self.var,
            values=HORAS_15MIN,
            width=width,
            state="readonly",
            style="Time.TCombobox",
            font=("Segoe UI", 11),
        )
        self.cb.pack(side=tk.LEFT)
        self.cb.bind("<<ComboboxSelected>>", self._on_select)

        inicial = value or self.var.get() or snap_hora_15("")
        self.set(inicial, notify=False)

    def get(self) -> str:
        return snap_hora_15(self.var.get())

    def set(self, value: str, *, notify: bool = True) -> None:
        hhmm = snap_hora_15(value)
        self._syncing = True
        try:
            if hhmm not in HORAS_15MIN:
                # Incluir valor atípico en la lista temporalmente
                self.cb.configure(values=[hhmm] + HORAS_15MIN)
            else:
                self.cb.configure(values=HORAS_15MIN)
            if self.var.get() != hhmm:
                self.var.set(hhmm)
        finally:
            self._syncing = False
        if notify and self.on_change:
            self.on_change(hhmm)

    def _on_select(self, _event=None) -> None:
        if self._syncing:
            return
        hhmm = snap_hora_15(self.var.get())
        if self.var.get() != hhmm:
            self.var.set(hhmm)
        if self.on_change:
            self.on_change(hhmm)
