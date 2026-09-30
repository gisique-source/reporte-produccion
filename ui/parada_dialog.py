"""Diálogo para abrir una parada: solo tiempo, operario y nota."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import tkinter as tk
from tkinter import ttk

from paradas_api import turno_actual
from ui.widgets import Theme, text_entry


class ParadaDialog(tk.Toplevel):
    def __init__(self, master: tk.Widget, *, operario: str = "") -> None:
        super().__init__(master)
        self.result: Optional[dict] = None
        self.title("Iniciar parada")
        self.configure(bg=Theme.PANEL)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.grab_set()

        self.var_operario = tk.StringVar(value=operario)
        self.var_turno = tk.StringVar(value=turno_actual())
        self.var_obs = tk.StringVar()

        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())
        self.after(10, self._center)

    def _build(self) -> None:
        tk.Label(
            self,
            text="Iniciar parada",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.PANEL,
        ).pack(anchor="w", padx=18, pady=(14, 4))
        tk.Label(
            self,
            text=(
                "Se registra la hora de inicio. La máquina y el motivo "
                "los clasifica después el especialista en la nube.\n"
                "Para reanudar, vuelva a pulsar el botón."
            ),
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=18, pady=(0, 10))

        form = tk.Frame(self, bg=Theme.PANEL)
        form.pack(fill=tk.X, padx=18)

        row = tk.Frame(form, bg=Theme.PANEL)
        row.pack(fill=tk.X)
        col_a = tk.Frame(row, bg=Theme.PANEL)
        col_a.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        col_b = tk.Frame(row, bg=Theme.PANEL)
        col_b.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._label(col_a, "Operario")
        text_entry(col_a, self.var_operario, 22).pack(fill=tk.X, pady=(0, 8))
        self._label(col_b, "Turno")
        ttk.Combobox(
            col_b,
            textvariable=self.var_turno,
            values=["Mañana", "Tarde", "Noche"],
            state="readonly",
            width=16,
        ).pack(fill=tk.X, pady=(0, 8))

        self._label(form, "Qué ocurrió (opcional)")
        text_entry(form, self.var_obs, 46).pack(fill=tk.X, pady=(0, 12))

        btns = tk.Frame(self, bg=Theme.PANEL)
        btns.pack(fill=tk.X, padx=18, pady=(0, 16))
        tk.Button(
            btns,
            text="Cancelar",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            bg=Theme.TREE_HEAD,
            fg=Theme.FG,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.destroy,
        ).pack(side=tk.LEFT)
        tk.Button(
            btns,
            text="Iniciar parada",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            bg=Theme.ERR_COLOR,
            fg="#ffffff",
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._ok,
        ).pack(side=tk.RIGHT)

    def _label(self, parent, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 9, "bold"),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            anchor="w",
        ).pack(fill=tk.X)

    def _ok(self) -> None:
        self.result = {
            "inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "turno": self.var_turno.get().strip(),
            "operario": self.var_operario.get().strip(),
            "observaciones": self.var_obs.get().strip()[:1000],
        }
        self.destroy()

    def _center(self) -> None:
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + 80
        y = top.winfo_rooty() + 60
        self.geometry(f"+{x}+{y}")
