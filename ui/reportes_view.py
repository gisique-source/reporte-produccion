"""Reportes de producción — exportación Excel y PDF (sin ingreso de datos)."""

from __future__ import annotations

import os
from datetime import date
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from db import (
    PesajeDatabase,
    format_fecha_corta,
    format_fecha_editable,
    nombre_mes,
    parse_fecha_produccion,
)
from models import RegistroPesaje
from reports import exportar_excel, exportar_pdf, nombre_sugerido
from ui.widgets import Theme, secondary_button, text_entry


class ReportesView(tk.Frame):
    def __init__(self, master: tk.Widget, db: PesajeDatabase) -> None:
        super().__init__(master, bg=Theme.BG)
        self.db = db
        today = date.today()
        self.var_modo = tk.StringVar(value="Día")
        self.var_desde = tk.StringVar(value=format_fecha_editable(today))
        self.var_hasta = tk.StringVar(value=format_fecha_editable(today))
        self.var_anio = tk.StringVar(value=str(today.year))
        self.var_mes = tk.StringVar(value=nombre_mes(today.month))
        self.var_info = tk.StringVar(value="")
        self._regs: list[RegistroPesaje] = []
        self._desde: date = today
        self._hasta: date = today
        self._build()
        self._aplicar_periodo()

    def _build(self) -> None:
        tk.Label(
            self,
            text="REPORTES — Excel y PDF",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(10, 2))
        tk.Label(
            self,
            text="Solo consulta y exportación. El ingreso de pesajes se hace en Pesaje / Hoja.",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack()

        filtros = tk.Frame(self, bg=Theme.PANEL, padx=12, pady=10)
        filtros.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(filtros, text="Periodo", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        self.cb_modo = ttk.Combobox(
            filtros,
            textvariable=self.var_modo,
            values=("Día", "Mes", "Rango"),
            state="readonly",
            width=10,
        )
        self.cb_modo.grid(row=1, column=0, sticky="w", pady=(0, 4))
        self.cb_modo.bind("<<ComboboxSelected>>", lambda _e: self._on_modo())

        self.fr_dia = tk.Frame(filtros, bg=Theme.PANEL)
        self.fr_dia.grid(row=1, column=1, sticky="w", padx=(16, 0))
        tk.Label(self.fr_dia, text="Fecha (DD/MM/YYYY)", fg=Theme.MUTED, bg=Theme.PANEL).pack(
            anchor="w"
        )
        text_entry(self.fr_dia, self.var_desde, 12).pack(anchor="w")

        self.fr_mes = tk.Frame(filtros, bg=Theme.PANEL)
        self.fr_mes.grid(row=1, column=1, sticky="w", padx=(16, 0))
        tk.Label(self.fr_mes, text="Año", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Combobox(
            self.fr_mes,
            textvariable=self.var_anio,
            values=[str(y) for y in self.db.listar_anios()],
            width=8,
            state="readonly",
        ).grid(row=1, column=0, sticky="w")
        tk.Label(self.fr_mes, text="Mes", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Combobox(
            self.fr_mes,
            textvariable=self.var_mes,
            values=[nombre_mes(m) for m in range(1, 13)],
            width=12,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=(8, 0))

        self.fr_rango = tk.Frame(filtros, bg=Theme.PANEL)
        self.fr_rango.grid(row=1, column=1, sticky="w", padx=(16, 0))
        tk.Label(self.fr_rango, text="Desde", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        text_entry(self.fr_rango, self.var_desde, 12).grid(row=1, column=0, sticky="w")
        tk.Label(self.fr_rango, text="Hasta", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        text_entry(self.fr_rango, self.var_hasta, 12).grid(
            row=1, column=1, sticky="w", padx=(8, 0)
        )

        btns = tk.Frame(filtros, bg=Theme.PANEL)
        btns.grid(row=1, column=2, sticky="e", padx=(20, 0))
        secondary_button(btns, "Actualizar vista", self._aplicar_periodo).pack(
            side=tk.LEFT, padx=4
        )
        secondary_button(btns, "Excel (.xlsx)", self._export_excel).pack(
            side=tk.LEFT, padx=4
        )
        secondary_button(btns, "PDF", self._export_pdf).pack(side=tk.LEFT, padx=4)

        filtros.columnconfigure(2, weight=1)

        tk.Label(
            self,
            textvariable=self.var_info,
            font=("Segoe UI", 11, "bold"),
            fg=Theme.US_COLOR,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=16)

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        style = ttk.Style()
        style.configure(
            "Rep.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=24,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Rep.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 9, "bold"),
        )

        cols = (
            "fecha",
            "fardo",
            "cliente",
            "lote",
            "color",
            "dn",
            "corte",
            "bruto",
            "neto",
            "operario",
        )
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Rep.Treeview"
        )
        headings = {
            "fecha": ("Fecha/Hora", 140),
            "fardo": ("Fardo", 55),
            "cliente": ("Cliente", 140),
            "lote": ("Lote", 90),
            "color": ("Color", 90),
            "dn": ("Dn", 50),
            "corte": ("Corte", 55),
            "bruto": ("Bruto", 70),
            "neto": ("Neto", 70),
            "operario": ("Operario", 90),
        }
        for key, (title, w) in headings.items():
            self.tree.heading(key, text=title)
            self.tree.column(key, width=w, anchor="center")

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        self._on_modo()

    def _on_modo(self) -> None:
        modo = self.var_modo.get()
        self.fr_dia.grid_remove()
        self.fr_mes.grid_remove()
        self.fr_rango.grid_remove()
        if modo == "Día":
            self.fr_dia.grid()
        elif modo == "Mes":
            self.fr_mes.grid()
        else:
            self.fr_rango.grid()

    def _mes_num(self) -> int:
        nombre = self.var_mes.get()
        for m in range(1, 13):
            if nombre_mes(m) == nombre:
                return m
        return date.today().month

    def _resolver_periodo(self) -> Optional[tuple[date, date, str]]:
        modo = self.var_modo.get()
        if modo == "Día":
            dia = parse_fecha_produccion(self.var_desde.get())
            if dia is None:
                messagebox.showwarning("Reportes", "Fecha inválida. Use DD/MM/YYYY.")
                return None
            return dia, dia, f"Hoja de producción — {format_fecha_corta(dia)}"
        if modo == "Mes":
            try:
                anio = int(self.var_anio.get())
            except ValueError:
                messagebox.showwarning("Reportes", "Año inválido.")
                return None
            mes = self._mes_num()
            import calendar

            ultimo = calendar.monthrange(anio, mes)[1]
            desde = date(anio, mes, 1)
            hasta = date(anio, mes, ultimo)
            return desde, hasta, f"Resumen mensual — {nombre_mes(mes)} {anio}"
        # Rango
        desde = parse_fecha_produccion(self.var_desde.get())
        hasta = parse_fecha_produccion(self.var_hasta.get())
        if desde is None or hasta is None:
            messagebox.showwarning("Reportes", "Desde/Hasta inválidos. Use DD/MM/YYYY.")
            return None
        if hasta < desde:
            desde, hasta = hasta, desde
        return (
            desde,
            hasta,
            f"Producción {format_fecha_editable(desde)} — {format_fecha_editable(hasta)}",
        )

    def _aplicar_periodo(self) -> None:
        resolved = self._resolver_periodo()
        if resolved is None:
            return
        desde, hasta, titulo = resolved
        self._desde, self._hasta = desde, hasta
        self._titulo = titulo
        self._regs = self.db.por_rango(desde, hasta)
        self.tree.delete(*self.tree.get_children())
        for r in self._regs:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    r.fecha_hora,
                    r.nro_fardo,
                    r.cliente,
                    r.lote,
                    r.color,
                    r.denier,
                    r.corte,
                    f"{r.peso_bruto:.2f}",
                    f"{r.peso_neto:.2f}",
                    r.operario,
                ),
            )
        bruto = sum(r.peso_bruto for r in self._regs)
        neto = sum(r.peso_neto for r in self._regs)
        self.var_info.set(
            f"{titulo}  ·  {len(self._regs)} fardos  ·  "
            f"Bruto {bruto:,.1f} kg  ·  Neto {neto:,.1f} kg"
        )

    def refrescar(self) -> None:
        self._aplicar_periodo()

    def _export_excel(self) -> None:
        self._aplicar_periodo()
        path = filedialog.asksaveasfilename(
            title="Guardar Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=nombre_sugerido("produccion", self._desde, self._hasta, "xlsx"),
        )
        if not path:
            return
        try:
            out = exportar_excel(
                self._regs,
                path,
                titulo=getattr(self, "_titulo", "Producción"),
                desde=self._desde,
                hasta=self._hasta,
            )
            messagebox.showinfo("Reportes", f"Excel generado:\n{out}")
            self._abrir_carpeta(out)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Reportes", f"No se pudo generar Excel:\n{exc}")

    def _export_pdf(self) -> None:
        self._aplicar_periodo()
        path = filedialog.asksaveasfilename(
            title="Guardar PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=nombre_sugerido("produccion", self._desde, self._hasta, "pdf"),
        )
        if not path:
            return
        try:
            out = exportar_pdf(
                self._regs,
                path,
                titulo=getattr(self, "_titulo", "Producción"),
                desde=self._desde,
                hasta=self._hasta,
            )
            messagebox.showinfo("Reportes", f"PDF generado:\n{out}")
            self._abrir_carpeta(out)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Reportes", f"No se pudo generar PDF:\n{exc}")

    @staticmethod
    def _abrir_carpeta(path) -> None:
        try:
            folder = os.path.dirname(str(path))
            if folder:
                os.startfile(folder)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
