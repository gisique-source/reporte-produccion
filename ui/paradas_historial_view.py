"""Página de consulta: historial de paradas por periodo."""

from __future__ import annotations

import threading
from datetime import date, datetime

import tkinter as tk
from tkinter import ttk

from db import format_fecha_editable, parse_fecha_produccion
from ui.date_picker import DatePicker
from ui.widgets import Theme, secondary_button


def _cuando(texto: str) -> str:
    try:
        dt = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return texto[:16] if texto else "—"


def _minutos(inicio: str, fin: str | None) -> int | None:
    if not fin:
        return None
    try:
        a = datetime.strptime(inicio, "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(fin, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(0, int((b - a).total_seconds() // 60))


def _duracion(minutos: int | None, *, abierta: bool) -> str:
    if abierta or minutos is None:
        return "en curso"
    horas, mins = divmod(minutos, 60)
    if horas:
        return f"{horas} h {mins} min"
    return f"{mins} min"


class ParadasHistorialView(tk.Frame):
    COLS = (
        ("inicio", "Inicio", 140),
        ("fin", "Fin", 140),
        ("duracion", "Duración", 90),
        ("estado", "Estado", 90),
        ("clasif", "Clasificación", 130),
        ("maquina", "Máquina", 140),
        ("tipo", "Tipo", 160),
        ("turno", "Turno", 70),
        ("operario", "Operario", 120),
        ("nota", "Nota", 220),
    )

    def __init__(self, master: tk.Widget, store) -> None:
        super().__init__(master, bg=Theme.BG)
        self.store = store
        hoy = date.today()
        self.var_desde = tk.StringVar(value=format_fecha_editable(hoy))
        self.var_hasta = tk.StringVar(value=format_fecha_editable(hoy))
        self.var_resumen = tk.StringVar(value="")
        self._build()
        self.refrescar()

    def _build(self) -> None:
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            head,
            text="HISTORIAL DE PARADAS",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        secondary_button(head, "Actualizar", self.actualizar).pack(side=tk.RIGHT)

        filtros = tk.Frame(self, bg=Theme.PANEL, padx=12, pady=8)
        filtros.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(filtros, text="Desde", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        DatePicker(
            filtros,
            textvariable=self.var_desde,
            bg=Theme.PANEL,
            on_change=lambda _d: self.refrescar(),
        ).grid(row=1, column=0, sticky="w")
        tk.Label(filtros, text="Hasta", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=1, sticky="w", padx=(16, 0)
        )
        DatePicker(
            filtros,
            textvariable=self.var_hasta,
            bg=Theme.PANEL,
            on_change=lambda _d: self.refrescar(),
        ).grid(row=1, column=1, sticky="w", padx=(16, 0))
        secondary_button(filtros, "Hoy", self._hoy).grid(
            row=1, column=2, sticky="sw", padx=(16, 0)
        )
        secondary_button(filtros, "Este mes", self._mes).grid(
            row=1, column=3, sticky="sw", padx=(8, 0)
        )

        tk.Label(
            self,
            textvariable=self.var_resumen,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        self.tree = ttk.Treeview(
            wrap,
            columns=[c[0] for c in self.COLS],
            show="headings",
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            anchor = "w" if key in {"maquina", "tipo", "nota", "operario"} else "center"
            self.tree.column(key, width=width, anchor=anchor)
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        sx = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.tag_configure("abierta", foreground=Theme.ERR_COLOR)
        self.tree.tag_configure("cerrada", foreground=Theme.FG)
        self.tree.tag_configure("anulada", foreground=Theme.MUTED)

    def _hoy(self) -> None:
        hoy = format_fecha_editable(date.today())
        self.var_desde.set(hoy)
        self.var_hasta.set(hoy)
        self.refrescar()

    def _mes(self) -> None:
        hoy = date.today()
        self.var_desde.set(format_fecha_editable(hoy.replace(day=1)))
        self.var_hasta.set(format_fecha_editable(hoy))
        self.refrescar()

    def _rango(self) -> tuple[date, date]:
        desde = parse_fecha_produccion(self.var_desde.get()) or date.today()
        hasta = parse_fecha_produccion(self.var_hasta.get()) or desde
        if hasta < desde:
            desde, hasta = hasta, desde
        return desde, hasta

    def actualizar(self) -> None:
        def work() -> None:
            from paradas_api import bajar_clasificacion

            try:
                bajar_clasificacion(self.store)
            except Exception:  # noqa: BLE001
                pass
            try:
                self.after(0, self.refrescar)
            except tk.TclError:
                pass

        threading.Thread(target=work, name="ParadasHistorial", daemon=True).start()

    def refrescar(self) -> None:
        desde, hasta = self._rango()
        filas = self.store.listar_periodo(desde, hasta)
        self.tree.delete(*self.tree.get_children())
        total_min = 0
        abiertas = 0
        sin_clasificar = 0
        for p in filas:
            mins = _minutos(p.inicio, p.fin)
            if p.abierta:
                abiertas += 1
                estado = "Abierta"
                tag = "abierta"
            elif not p.activo:
                estado = "Anulada"
                tag = "anulada"
            else:
                estado = "Cerrada"
                tag = "cerrada"
                if mins is not None:
                    total_min += mins
            if not p.clasificada and p.activo:
                sin_clasificar += 1
            clasif = p.categoria if p.clasificada and p.categoria else "Sin clasificar"
            self.tree.insert(
                "",
                tk.END,
                values=(
                    _cuando(p.inicio),
                    _cuando(p.fin or "") if p.fin else "—",
                    _duracion(mins, abierta=p.abierta),
                    estado,
                    clasif,
                    p.maquinaria_nombre or p.maquinaria_codigo or "—",
                    p.tipo_nombre or p.tipo_codigo or "—",
                    p.turno or "—",
                    p.operario or "—",
                    p.observaciones or p.detalle_otro or "—",
                ),
                tags=(tag,),
            )
        if not filas:
            self.var_resumen.set(
                f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}   ·   "
                "Sin paradas en este periodo."
            )
            return
        self.var_resumen.set(
            f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}   ·   "
            f"{len(filas)} parada(s)   ·   "
            f"Tiempo cerrado: {_duracion(total_min, abierta=False)}   ·   "
            f"Abiertas: {abiertas}   ·   Sin clasificar: {sin_clasificar}"
        )
