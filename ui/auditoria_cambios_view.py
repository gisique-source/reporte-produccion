"""Historial de altas y ediciones hechas en Hoja de cálculo."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from db import PesajeDatabase
from ui.widgets import Theme, secondary_button, text_entry


class AuditoriaCambiosView(tk.Frame):
    COLS = (
        ("cuando", "Fecha/hora", 140),
        ("accion", "Acción", 70),
        ("fardo", "Fardo", 55),
        ("id_local", "ID", 50),
        ("campo", "Campo", 90),
        ("antes", "Antes", 120),
        ("despues", "Después", 120),
        ("operario", "Operario", 90),
        ("detalle", "Detalle", 280),
    )

    def __init__(self, master: tk.Widget, db: PesajeDatabase) -> None:
        super().__init__(master, bg=Theme.BG)
        self.db = db
        self.var_buscar = tk.StringVar()
        self.var_resumen = tk.StringVar(value="")
        self._build()
        self.refrescar()

    def _build(self) -> None:
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            head,
            text="AUDITORÍA — CAMBIOS EN HOJA DE CÁLCULO",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        secondary_button(head, "Actualizar", self.refrescar).pack(side=tk.RIGHT)

        bar = tk.Frame(self, bg=Theme.PANEL, padx=12, pady=8)
        bar.pack(fill=tk.X, padx=12, pady=8)
        tk.Label(bar, text="Buscar", fg=Theme.MUTED, bg=Theme.PANEL).pack(side=tk.LEFT)
        ent = text_entry(bar, self.var_buscar, 24)
        ent.pack(side=tk.LEFT, padx=8)
        ent.bind("<Return>", lambda _e: self.refrescar())
        secondary_button(bar, "Filtrar", self.refrescar).pack(side=tk.LEFT)

        tk.Label(
            self,
            textvariable=self.var_resumen,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 4))

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        cols = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Aud.Treeview"
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            self.tree.column(
                key, width=width, anchor="w" if key == "detalle" else "center", stretch=True
            )
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("crear", background="#e7f6ec")
        self.tree.tag_configure("editar", background="#fff8e6")

    def refrescar(self) -> None:
        rows = self.db.auditoria_pesaje(limite=800, texto=self.var_buscar.get())
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert(
                "",
                tk.END,
                iid=str(r.id),
                values=(
                    r.creado_en,
                    r.accion,
                    r.nro_fardo,
                    r.pesaje_id,
                    r.campo or "—",
                    r.valor_anterior or "—",
                    r.valor_nuevo or "—",
                    r.operario,
                    r.detalle,
                ),
                tags=(r.accion,),
            )
        self.var_resumen.set(f"{len(rows)} evento(s) de alta / edición")
