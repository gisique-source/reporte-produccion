"""Administración de tablas maestro (cliente, color, denier, corte)."""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from catalog import ETIQUETAS, CatalogoError, CatalogoMaestros, MaestroTipo
from models import MaestroItem
from ui.widgets import Theme, secondary_button, text_entry


class MaestrosView(tk.Frame):
    """Alta / edición / desactivación. Sin borrado físico."""

    TIPOS: tuple[MaestroTipo, ...] = ("cliente", "color", "denier", "corte")

    def __init__(
        self,
        master: tk.Widget,
        catalogo: CatalogoMaestros,
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.catalogo = catalogo
        self.on_change = on_change
        self.tipo: MaestroTipo = "cliente"
        self.var_valor = tk.StringVar()
        self.var_codigo = tk.StringVar()
        self.var_filtro = tk.BooleanVar(value=False)
        self.var_titulo = tk.StringVar(value=ETIQUETAS["cliente"])
        self._items: list[MaestroItem] = []
        self._selected_id: Optional[int] = None
        self._nav_btns: dict[MaestroTipo, tk.Button] = {}
        self._build()
        self._seleccionar_nav("cliente")
        self.refrescar()

    def _build(self) -> None:
        tk.Label(
            self,
            text="TABLAS MAESTRO — Referencias",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(10, 2))
        tk.Label(
            self,
            text="Prohibido eliminar. Use Desactivar (soft-delete) / Reactivar.",
            font=("Segoe UI", 10),
            fg=Theme.US_COLOR,
            bg=Theme.BG,
        ).pack()

        body = tk.Frame(self, bg=Theme.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # --- Navegación lateral ---
        side = tk.Frame(body, bg=Theme.PANEL, width=200)
        side.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        side.grid_propagate(False)

        tk.Label(
            side,
            text="CATÁLOGOS",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(14, 8))

        for tipo in self.TIPOS:
            btn = tk.Button(
                side,
                text=ETIQUETAS[tipo],
                font=("Segoe UI", 12, "bold"),
                fg=Theme.FG,
                bg=Theme.PANEL,
                activeforeground="#ffffff",
                activebackground=Theme.ACCENT,
                relief=tk.FLAT,
                anchor="w",
                padx=16,
                pady=12,
                cursor="hand2",
                command=lambda t=tipo: self._seleccionar_nav(t),
            )
            btn.pack(fill=tk.X, padx=6, pady=2)
            self._nav_btns[tipo] = btn

        tk.Frame(side, bg=Theme.PANEL, height=8).pack()
        tk.Label(
            side,
            text="Seleccione un catálogo\npara administrar valores.",
            font=("Segoe UI", 8),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=14, pady=8)

        # --- Contenido derecho ---
        right = tk.Frame(body, bg=Theme.BG)
        right.grid(row=0, column=1, sticky="nsew")

        head = tk.Frame(right, bg=Theme.BG)
        head.pack(fill=tk.X)
        tk.Label(
            head,
            textvariable=self.var_titulo,
            font=("Segoe UI", 16, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            head,
            text="Mostrar inactivos",
            variable=self.var_filtro,
            command=self.refrescar,
            fg=Theme.FG,
            bg=Theme.BG,
            selectcolor=Theme.PANEL,
            activebackground=Theme.BG,
            activeforeground=Theme.FG,
        ).pack(side=tk.RIGHT)

        form = tk.Frame(right, bg=Theme.PANEL, padx=12, pady=10)
        form.pack(fill=tk.X, pady=(10, 4))
        tk.Label(form, text="Valor", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(form, text="Código (opc.)", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        text_entry(form, self.var_valor, 28).grid(row=1, column=0, sticky="ew")
        text_entry(form, self.var_codigo, 14).grid(
            row=1, column=1, sticky="ew", padx=(10, 0)
        )
        form.columnconfigure(0, weight=2)
        form.columnconfigure(1, weight=1)

        btns = tk.Frame(right, bg=Theme.BG)
        btns.pack(fill=tk.X, pady=8)
        secondary_button(btns, "Nuevo / Guardar", self._guardar).pack(side=tk.LEFT, padx=4)
        secondary_button(btns, "Desactivar", self._desactivar).pack(side=tk.LEFT, padx=4)
        secondary_button(btns, "Reactivar", self._reactivar).pack(side=tk.LEFT, padx=4)
        secondary_button(btns, "Limpiar", self._limpiar).pack(side=tk.LEFT, padx=4)

        wrap = tk.Frame(right, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=4)

        style = ttk.Style()
        style.configure(
            "Mae.Treeview",
            background="#2a2a2a",
            foreground=Theme.FG,
            fieldbackground="#2a2a2a",
            rowheight=26,
        )
        style.configure(
            "Mae.Treeview.Heading",
            background="#111",
            foreground="#fff",
            font=("Segoe UI", 10, "bold"),
        )

        self.tree = ttk.Treeview(
            wrap,
            columns=("id", "valor", "codigo", "estado"),
            show="headings",
            style="Mae.Treeview",
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("valor", text="Valor")
        self.tree.heading("codigo", text="Código")
        self.tree.heading("estado", text="Estado")
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("valor", width=280, anchor="w")
        self.tree.column("codigo", width=100, anchor="center")
        self.tree.column("estado", width=90, anchor="center")
        self.tree.tag_configure("inactivo", foreground="#888")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        self.lbl_msg = tk.Label(
            right, text="", font=("Segoe UI", 10), fg=Theme.MUTED, bg=Theme.BG
        )
        self.lbl_msg.pack(pady=6)

    def _seleccionar_nav(self, tipo: MaestroTipo) -> None:
        self.tipo = tipo
        self.var_titulo.set(ETIQUETAS[tipo])
        for t, btn in self._nav_btns.items():
            if t == tipo:
                btn.configure(bg=Theme.ACCENT, fg="#ffffff")
            else:
                btn.configure(bg=Theme.PANEL, fg=Theme.FG)
        self._limpiar()
        self.refrescar()

    def refrescar(self) -> None:
        solo_activos = not self.var_filtro.get()
        self._items = self.catalogo.listar(self.tipo, solo_activos=solo_activos)
        self.tree.delete(*self.tree.get_children())
        for m in self._items:
            estado = "Activo" if m.activo else "Inactivo"
            tags = () if m.activo else ("inactivo",)
            self.tree.insert(
                "",
                tk.END,
                iid=str(m.id),
                values=(m.id, m.valor, m.codigo, estado),
                tags=tags,
            )

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        mid = int(sel[0])
        item = next((m for m in self._items if m.id == mid), None)
        if not item:
            return
        self._selected_id = item.id
        self.var_valor.set(item.valor)
        self.var_codigo.set(item.codigo)

    def _limpiar(self) -> None:
        self._selected_id = None
        self.var_valor.set("")
        self.var_codigo.set("")
        self.tree.selection_remove(self.tree.selection())

    def _guardar(self) -> None:
        valor = self.var_valor.get().strip()
        codigo = self.var_codigo.get().strip()
        try:
            if self._selected_id is None:
                self.catalogo.crear(self.tipo, valor, codigo)
                self.lbl_msg.config(text=f"Creado: {valor}", fg=Theme.ST_COLOR)
            else:
                self.catalogo.actualizar(self.tipo, self._selected_id, valor, codigo)
                self.lbl_msg.config(text=f"Actualizado: {valor}", fg=Theme.ST_COLOR)
        except CatalogoError as exc:
            messagebox.showwarning("Maestros", str(exc))
            return
        self._limpiar()
        self.refrescar()
        if self.on_change:
            self.on_change()

    def _desactivar(self) -> None:
        if self._selected_id is None:
            messagebox.showinfo("Maestros", "Seleccione un registro activo.")
            return
        if not messagebox.askyesno(
            "Desactivar",
            "¿Desactivar este registro?\nNo se elimina; dejará de aparecer en los combos.",
        ):
            return
        try:
            self.catalogo.desactivar(self.tipo, self._selected_id)
            self.lbl_msg.config(text="Desactivado (soft-delete).", fg=Theme.US_COLOR)
        except CatalogoError as exc:
            messagebox.showwarning("Maestros", str(exc))
            return
        self._limpiar()
        self.refrescar()
        if self.on_change:
            self.on_change()

    def _reactivar(self) -> None:
        if self._selected_id is None:
            messagebox.showinfo("Maestros", "Seleccione un registro inactivo.")
            return
        try:
            self.catalogo.reactivar(self.tipo, self._selected_id)
            self.lbl_msg.config(text="Reactivado.", fg=Theme.ST_COLOR)
        except CatalogoError as exc:
            messagebox.showwarning("Maestros", str(exc))
            return
        self._limpiar()
        self.refrescar()
        if self.on_change:
            self.on_change()
