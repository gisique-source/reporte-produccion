"""Resumen de producción mensual — totales por día."""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from db import PesajeDatabase, nombre_mes
from models import ResumenDia
from ui.widgets import Theme


class ResumenMesView(tk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        on_open_day: Optional[Callable[[date], None]] = None,
    ) -> None:
        super().__init__(master, bg="#3a2030")
        self.db = db
        self.on_open_day = on_open_day
        today = date.today()
        self.year = today.year
        self.month = today.month
        self.var_mes = tk.StringVar()
        self.var_total = tk.StringVar()
        self._rows: list[ResumenDia] = []
        self._build()
        self.refrescar()

    def _build(self) -> None:
        top = tk.Frame(self, bg="#3a2030")
        top.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(
            top,
            text="Gexim SAC",
            font=("Segoe UI", 12, "bold"),
            fg="#f5c6d0",
            bg="#3a2030",
        ).pack(side=tk.LEFT)

        tk.Label(
            top,
            text="Resumen de Producción Mensual Sección Extrusora",
            font=("Segoe UI", 13, "bold"),
            fg="#fff",
            bg="#3a2030",
        ).pack(side=tk.LEFT, padx=16)

        nav = tk.Frame(top, bg="#3a2030")
        nav.pack(side=tk.RIGHT)
        tk.Label(nav, text="Mes:", fg="#fff", bg="#3a2030").pack(side=tk.LEFT)
        tk.Button(nav, text="◀", command=self._mes_ant, width=3).pack(side=tk.LEFT, padx=2)
        tk.Label(
            nav, textvariable=self.var_mes, font=("Segoe UI", 12, "bold"),
            fg="#111", bg="#fff", width=12
        ).pack(side=tk.LEFT)
        tk.Button(nav, text="▶", command=self._mes_sig, width=3).pack(side=tk.LEFT, padx=2)

        body = tk.Frame(self, bg="#3a2030")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self.left = self._make_table(body)
        self.right = self._make_table(body)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        body.rowconfigure(0, weight=1)

        foot = tk.Frame(self, bg="#f1c40f")
        foot.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 4))
        tk.Label(
            foot, textvariable=self.var_total, font=("Segoe UI", 12, "bold"),
            fg="#1a3a6e", bg="#f1c40f", anchor="e"
        ).pack(fill=tk.X, padx=8, pady=6)

        tk.Label(
            self,
            text="Doble clic en un día (Hojas) para abrir el detalle de fardos",
            font=("Segoe UI", 9),
            fg="#f5c6d0",
            bg="#3a2030",
        ).pack(side=tk.BOTTOM, pady=(0, 8))

        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    def _make_table(self, parent: tk.Widget) -> ttk.Treeview:
        style = ttk.Style()
        style.configure(
            "Mes.Treeview",
            background="#f8d7e0",
            foreground="#111",
            fieldbackground="#f8d7e0",
            rowheight=24,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Mes.Treeview.Heading",
            background="#111",
            foreground="#fff",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Mes.Treeview", background=[("selected", "#c0392b")])

        cols = ("hojas", "fecha", "bruto", "neto")
        tree = ttk.Treeview(
            parent, columns=cols, show="headings", style="Mes.Treeview", height=16
        )
        tree.heading("hojas", text="Hojas")
        tree.heading("fecha", text="Fecha")
        tree.heading("bruto", text="Peso Bruto")
        tree.heading("neto", text="Peso Neto")
        tree.column("hojas", width=70, anchor="center")
        tree.column("fecha", width=90, anchor="center")
        tree.column("bruto", width=110, anchor="e")
        tree.column("neto", width=110, anchor="e")
        tree.tag_configure("link", foreground="#c0392b")
        tree.bind("<Double-1>", self._on_double)
        return tree

    def _mes_ant(self) -> None:
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.refrescar()

    def _mes_sig(self) -> None:
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.refrescar()

    def refrescar(self) -> None:
        self.var_mes.set(nombre_mes(self.month))
        self._rows = self.db.resumen_mes(self.year, self.month)
        self._fill(self.left, self._rows[:15])
        self._fill(self.right, self._rows[15:])

        tb = sum(r.peso_bruto for r in self._rows)
        tn = sum(r.peso_neto for r in self._rows)
        self.var_total.set(
            f"Total del Mes    Bruto {tb:,.1f} Kgrs    Neto {tn:,.1f} Kgrs"
        )

    def _fill(self, tree: ttk.Treeview, rows: list[ResumenDia]) -> None:
        tree.delete(*tree.get_children())
        for r in rows:
            tree.insert(
                "",
                tk.END,
                iid=f"{self.year}-{self.month:02d}-{r.dia:02d}",
                values=(
                    f"Dia {r.dia:02d}",
                    r.fecha,
                    f"{r.peso_bruto:,.1f} Kgrs",
                    f"{r.peso_neto:,.1f} Kgrs",
                ),
                tags=("link",),
            )

    def _on_double(self, event) -> None:
        tree = event.widget
        item = tree.identify_row(event.y)
        if not item or not self.on_open_day:
            return
        y, m, d = (int(x) for x in item.split("-"))
        self.on_open_day(date(y, m, d))
