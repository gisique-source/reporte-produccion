"""Historial local de paradas y si la nube las recibió."""

from __future__ import annotations

import threading

import tkinter as tk
from tkinter import ttk

from ui.widgets import Theme, secondary_button


class ParadasAuditView(tk.Frame):
    COLS = (
        ("inicio", "Inicio", 130),
        ("fin", "Fin", 130),
        ("sync", "Nube", 90),
        ("clasif", "Clasificación", 150),
        ("maquina", "Máquina", 140),
        ("tipo", "Tipo", 160),
        ("turno", "Turno", 70),
        ("operario", "Operario", 110),
        ("id_local", "ID local", 70),
        ("id_remoto", "ID remoto", 180),
        ("detalle", "Nota / error", 220),
    )

    def __init__(self, master: tk.Widget, store) -> None:
        super().__init__(master, bg=Theme.BG)
        self.store = store
        self.var_resumen = tk.StringVar(value="")
        self._build()
        self.refrescar()

    def _build(self) -> None:
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            head,
            text="AUDITORÍA — PARADAS",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        secondary_button(head, "Actualizar", self.actualizar).pack(side=tk.RIGHT)
        tk.Label(
            self,
            textvariable=self.var_resumen,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        self.tree = ttk.Treeview(
            wrap,
            columns=[c[0] for c in self.COLS],
            show="headings",
            height=16,
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("ok", foreground=Theme.ST_COLOR)
        self.tree.tag_configure("pend", foreground=Theme.US_COLOR)
        self.tree.tag_configure("abierta", foreground=Theme.ERR_COLOR)

    def actualizar(self) -> None:
        """Vuelve a pedir a la nube si ya clasificaron la parada."""

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

        threading.Thread(target=work, name="ParadasPull", daemon=True).start()

    def refrescar(self) -> None:
        filas = self.store.listar()
        self.tree.delete(*self.tree.get_children())
        ok = sum(1 for p in filas if p.sync_estado == "ok")
        pend = sum(1 for p in filas if p.sync_estado != "ok")
        abiertas = sum(1 for p in filas if p.abierta)
        self.var_resumen.set(
            f"Recibidas en nube: {ok}   ·   Pendientes o con error: {pend}   ·   "
            f"Abiertas ahora: {abiertas}"
        )
        for p in filas:
            if p.abierta:
                tag = "abierta"
                nube = "ABIERTA"
            elif p.sync_estado == "ok":
                tag = "ok"
                nube = "RECIBIDA"
            else:
                tag = "pend"
                nube = "PENDIENTE"
            if p.clasificada:
                clasif = p.categoria or "Clasificada"
            else:
                clasif = "Sin clasificar"
            detalle = p.sync_error or p.observaciones or p.detalle_otro
            self.tree.insert(
                "",
                tk.END,
                values=(
                    p.inicio,
                    p.fin or "—",
                    nube,
                    clasif,
                    p.maquinaria_nombre or p.maquinaria_codigo or "—",
                    p.tipo_nombre or p.tipo_codigo or "—",
                    p.turno,
                    p.operario,
                    p.id,
                    p.id_remoto,
                    detalle,
                ),
                tags=(tag,),
            )
