"""Selector reutilizable de fecha: Día / Mes / Año (combobox)."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from db import format_fecha_editable, nombre_mes, parse_fecha_produccion
from ui.widgets import Theme

_VACIO = "—"
_MESES = [nombre_mes(m) for m in range(1, 13)]


class DatePicker(tk.Frame):
    """
    Tres listas: día, mes, año.
    Sincroniza un StringVar en formato DD/MM/YYYY (compatible con parse_fecha_produccion).
    """

    def __init__(
        self,
        master: tk.Widget,
        *,
        textvariable: Optional[tk.StringVar] = None,
        value: Optional[date] = None,
        allow_empty: bool = False,
        year_from: int = 2020,
        year_to: Optional[int] = None,
        bg: str = Theme.PANEL,
        on_change: Optional[Callable[[Optional[date]], None]] = None,
    ) -> None:
        super().__init__(master, bg=bg)
        self.allow_empty = allow_empty
        self.on_change = on_change
        self._bg = bg
        self._syncing = False
        self.var = textvariable or tk.StringVar()
        hoy = date.today()
        y_to = year_to or max(hoy.year + 1, 2030)
        self._years = [str(y) for y in range(y_to, year_from - 1, -1)]

        self.var_dia = tk.StringVar()
        self.var_mes = tk.StringVar()
        self.var_anio = tk.StringVar()

        style = ttk.Style()
        style.configure(
            "Date.TCombobox",
            fieldbackground=Theme.INPUT_BG,
            background=Theme.PANEL,
            foreground=Theme.FG,
            arrowcolor=Theme.FG,
        )

        self.cb_dia = ttk.Combobox(
            self,
            textvariable=self.var_dia,
            width=3,
            state="readonly",
            style="Date.TCombobox",
            font=("Segoe UI", 11),
        )
        self.cb_mes = ttk.Combobox(
            self,
            textvariable=self.var_mes,
            width=10,
            state="readonly",
            style="Date.TCombobox",
            font=("Segoe UI", 11),
            values=([_VACIO] + _MESES) if allow_empty else _MESES,
        )
        self.cb_anio = ttk.Combobox(
            self,
            textvariable=self.var_anio,
            width=5,
            state="readonly",
            style="Date.TCombobox",
            font=("Segoe UI", 11),
            values=([_VACIO] + self._years) if allow_empty else self._years,
        )

        self.cb_dia.pack(side=tk.LEFT)
        tk.Label(self, text="/", fg=Theme.MUTED, bg=bg, font=("Segoe UI", 11)).pack(
            side=tk.LEFT, padx=2
        )
        self.cb_mes.pack(side=tk.LEFT)
        tk.Label(self, text="/", fg=Theme.MUTED, bg=bg, font=("Segoe UI", 11)).pack(
            side=tk.LEFT, padx=2
        )
        self.cb_anio.pack(side=tk.LEFT)

        self.cb_dia.bind("<<ComboboxSelected>>", self._on_combo)
        self.cb_mes.bind("<<ComboboxSelected>>", self._on_combo)
        self.cb_anio.bind("<<ComboboxSelected>>", self._on_combo)

        # Carga inicial
        inicial = value
        if inicial is None and self.var.get().strip():
            inicial = parse_fecha_produccion(self.var.get())
        if inicial is None and not allow_empty:
            inicial = hoy
        self.set_date(inicial, notify=False)

        self.var.trace_add("write", self._on_var_write)

    def get_date(self) -> Optional[date]:
        if self.allow_empty and (
            self.var_dia.get() in ("", _VACIO)
            or self.var_mes.get() in ("", _VACIO)
            or self.var_anio.get() in ("", _VACIO)
        ):
            return None
        try:
            dia = int(self.var_dia.get())
            mes = _MESES.index(self.var_mes.get()) + 1
            anio = int(self.var_anio.get())
            max_d = calendar.monthrange(anio, mes)[1]
            dia = min(max(1, dia), max_d)
            return date(anio, mes, dia)
        except (ValueError, IndexError):
            return None

    def set_date(
        self, value: Optional[date], *, notify: bool = True
    ) -> None:
        self._syncing = True
        try:
            if value is None:
                if self.allow_empty:
                    self.var_anio.set(_VACIO)
                    self.var_mes.set(_VACIO)
                    self._refresh_dias()
                    self.var_dia.set(_VACIO)
                    if self.var.get() != "":
                        self.var.set("")
                else:
                    value = date.today()
            if value is not None:
                self.var_anio.set(str(value.year))
                self.var_mes.set(nombre_mes(value.month))
                self._refresh_dias()
                self.var_dia.set(f"{value.day:02d}")
                texto = format_fecha_editable(value)
                if self.var.get() != texto:
                    self.var.set(texto)
        finally:
            self._syncing = False
        if notify and self.on_change:
            self.on_change(self.get_date())

    def clear(self, *, notify: bool = True) -> None:
        if not self.allow_empty:
            self.set_date(date.today(), notify=notify)
            return
        self.set_date(None, notify=notify)

    def _dias_disponibles(self) -> list[str]:
        if self.allow_empty and (
            self.var_mes.get() in ("", _VACIO)
            or self.var_anio.get() in ("", _VACIO)
        ):
            base = [f"{d:02d}" for d in range(1, 32)]
            return [_VACIO] + base
        try:
            mes = _MESES.index(self.var_mes.get()) + 1
            anio = int(self.var_anio.get())
            max_d = calendar.monthrange(anio, mes)[1]
        except (ValueError, IndexError):
            max_d = 31
        dias = [f"{d:02d}" for d in range(1, max_d + 1)]
        return ([_VACIO] + dias) if self.allow_empty else dias

    def _refresh_dias(self) -> None:
        dias = self._dias_disponibles()
        self.cb_dia.configure(values=dias)
        actual = self.var_dia.get()
        if actual not in dias:
            if self.allow_empty and actual in ("", _VACIO):
                self.var_dia.set(_VACIO)
            else:
                # Clamp al último día válido del mes
                nums = [d for d in dias if d != _VACIO]
                self.var_dia.set(nums[-1] if nums else _VACIO)

    def _on_combo(self, _event=None) -> None:
        if self._syncing:
            return
        # Si eligió mes/año vacío → limpiar
        if self.allow_empty and (
            self.var_mes.get() == _VACIO or self.var_anio.get() == _VACIO
        ):
            self._syncing = True
            try:
                self.var_mes.set(_VACIO)
                self.var_anio.set(_VACIO)
                self._refresh_dias()
                self.var_dia.set(_VACIO)
                if self.var.get() != "":
                    self.var.set("")
            finally:
                self._syncing = False
            if self.on_change:
                self.on_change(None)
            return

        self._refresh_dias()
        d = self.get_date()
        self._syncing = True
        try:
            if d is None:
                if self.var.get() != "":
                    self.var.set("")
            else:
                texto = format_fecha_editable(d)
                if self.var.get() != texto:
                    self.var.set(texto)
        finally:
            self._syncing = False
        if self.on_change:
            self.on_change(d)

    def _on_var_write(self, *_args) -> None:
        if self._syncing:
            return
        raw = (self.var.get() or "").strip()
        if not raw:
            if self.allow_empty:
                self.set_date(None, notify=False)
            return
        d = parse_fecha_produccion(raw)
        if d is not None:
            actual = self.get_date()
            if actual != d:
                self.set_date(d, notify=False)
