"""Historial condensado del día en la pantalla de pesaje."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Sequence

from models import RegistroPesaje
from ui.widgets import Theme

_COLS = (
    ("n", "N°", 36),
    ("fardo", "Fardo", 52),
    ("cliente", "Cliente", 130),
    ("lote", "Lote", 110),
    ("color", "Color", 90),
    ("dn", "Dn", 46),
    ("corte", "Corte", 52),
    ("total", "P.Total", 64),
    ("tara_c", "Tara Carr.", 72),
    ("tara_f", "Tara Fardo", 72),
    ("bruto", "P.Bruto", 64),
    ("neto", "P.Neto", 64),
    ("hora", "Hora", 58),
    ("operario", "Operario", 90),
)


class PesajeHistorial(tk.Frame):
    """Tabla de solo lectura, mismas columnas que la hoja, en pocas filas."""

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, bg=Theme.BG)
        tk.Label(
            self,
            text="Registros del día",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))

        style = ttk.Style()
        style.configure(
            "PesajeHist.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=22,
            font=("Segoe UI", 8),
        )
        style.configure(
            "PesajeHist.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 8, "bold"),
        )

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(
            wrap,
            columns=[c[0] for c in _COLS],
            show="headings",
            style="PesajeHist.Treeview",
            height=4,
        )
        for key, title, width in _COLS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="center", stretch=True, minwidth=40)
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("ultimo", background=Theme.ROW_LAST)

    def cargar(self, registros: Sequence[RegistroPesaje]) -> None:
        self.tree.delete(*self.tree.get_children())
        ultimo = registros[-1].id if registros else None
        for idx, reg in enumerate(registros, start=1):
            tags = ("ultimo",) if reg.id == ultimo else ()
            self.tree.insert(
                "",
                tk.END,
                iid=str(reg.id),
                values=(
                    idx,
                    reg.nro_fardo,
                    reg.cliente,
                    reg.lote,
                    reg.color,
                    reg.denier,
                    reg.corte,
                    f"{reg.peso_total:.2f}",
                    f"{reg.tara_carreta:.2f}",
                    f"{reg.tara_fardo:.2f}",
                    f"{reg.peso_bruto:.2f}",
                    f"{reg.peso_neto:.2f}",
                    _hora(reg.fecha_hora),
                    reg.operario,
                ),
                tags=tags,
            )
        if registros:
            self.tree.see(str(registros[-1].id))


def _hora(fecha_hora: str) -> str:
    if len(fecha_hora) >= 16:
        return fecha_hora[11:16]
    return ""
