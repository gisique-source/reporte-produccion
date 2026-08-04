"""Diálogo de carga masiva por pegado Excel (Ctrl+V)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from bulk_import import (
    FilaImport,
    crear_maestros_faltantes,
    fila_a_datos,
    maestros_faltantes,
    parsear_pegado,
)
from catalog import ETIQUETAS
from db import PesajeDatabase, format_fecha_editable
from ui.widgets import Theme, secondary_button


class BulkPasteDialog(tk.Toplevel):
    """
    Vista previa del pegado:
    - Filas OK en color normal
    - Maestros no encontrados en naranja
    - Errores en rojo
    """

    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        dia: date,
        texto: str,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.db = db
        self.dia = dia
        self.on_done = on_done
        self.title(f"Carga masiva — {format_fecha_editable(dia)}")
        self.configure(bg=Theme.BG)
        self.geometry("980x560")
        self.minsize(800, 420)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.var_info = tk.StringVar()
        self.var_falt = tk.StringVar()
        self._resultado = parsear_pegado(texto, db.catalogo)
        self._filas: list[FilaImport] = list(self._resultado.filas)

        self._build()
        self._rellenar()
        self.bind("<Control-v>", self._repegar)
        self.bind("<Control-V>", self._repegar)

    def _build(self) -> None:
        tk.Label(
            self,
            text="Pegado desde Excel → vista previa",
            font=("Segoe UI", 13, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(10, 2))
        tk.Label(
            self,
            textvariable=self.var_info,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack()
        tk.Label(
            self,
            textvariable=self.var_falt,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.US_COLOR,
            bg=Theme.BG,
            wraplength=900,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=12, pady=4)

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        style = ttk.Style(self)
        style.configure(
            "Bulk.Treeview",
            background="#2a2a2a",
            foreground=Theme.FG,
            fieldbackground="#2a2a2a",
            rowheight=24,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Bulk.Treeview.Heading",
            background="#111",
            foreground="#fff",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Bulk.Treeview", background=[("selected", Theme.ACCENT)])

        cols = (
            "ok",
            "fardo",
            "cliente",
            "lote",
            "color",
            "dn",
            "corte",
            "total",
            "bruto",
            "neto",
            "operario",
        )
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Bulk.Treeview"
        )
        heads = {
            "ok": ("Estado", 90),
            "fardo": ("Fardo", 55),
            "cliente": ("Cliente", 140),
            "lote": ("Lote", 90),
            "color": ("Color", 100),
            "dn": ("Dn", 50),
            "corte": ("Corte", 55),
            "total": ("Total", 70),
            "bruto": ("Bruto", 70),
            "neto": ("Neto", 70),
            "operario": ("Op.", 80),
        }
        for k, (t, w) in heads.items():
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor="center")

        self.tree.tag_configure("ok", foreground=Theme.ST_COLOR)
        self.tree.tag_configure("faltante", foreground="#ff9f43")
        self.tree.tag_configure("error", foreground=Theme.ERR_COLOR)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        btns = tk.Frame(self, bg=Theme.BG)
        btns.pack(fill=tk.X, padx=12, pady=10)
        secondary_button(btns, "Pegar de nuevo (Ctrl+V)", self._repegar).pack(
            side=tk.LEFT, padx=4
        )
        secondary_button(
            btns, "Crear maestros faltantes", self._crear_faltantes
        ).pack(side=tk.LEFT, padx=4)
        secondary_button(btns, "Importar listos", self._importar).pack(
            side=tk.LEFT, padx=4
        )
        secondary_button(btns, "Cancelar", self.destroy).pack(side=tk.RIGHT, padx=4)

        tk.Label(
            self,
            text=(
                "Naranja = valor no está en Maestros (espacios/acentos se ignoran al buscar). "
                "Cree maestros o corrija en Excel y vuelva a pegar."
            ),
            font=("Segoe UI", 8),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(0, 8))

    def _rellenar(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.var_info.set(self._resultado.aviso)

        falt = maestros_faltantes(self._filas)
        partes = []
        for tipo, vals in falt.items():
            if vals:
                partes.append(f"{ETIQUETAS[tipo]}: {', '.join(vals[:8])}"
                              + ("…" if len(vals) > 8 else ""))
        n_ok = sum(1 for f in self._filas if f.lista_para_importar)
        n_falt = sum(1 for f in self._filas if f.tiene_faltantes)
        n_err = sum(1 for f in self._filas if f.errores)
        resumen = f"Listos: {n_ok}  ·  Con maestros nuevos: {n_falt}  ·  Errores: {n_err}"
        if partes:
            self.var_falt.set(resumen + "\nFaltan → " + " | ".join(partes))
        else:
            self.var_falt.set(resumen + "  ·  Todos los maestros coinciden")

        for i, f in enumerate(self._filas):
            if f.errores:
                estado, tag = "Error", "error"
            elif f.tiene_faltantes:
                estado, tag = "Nuevo maestro", "faltante"
            else:
                estado, tag = "OK", "ok"

            def mark(ok: Optional[str], raw: str) -> str:
                if not raw:
                    return ""
                return raw if ok else f"⚠ {raw}"

            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    estado,
                    f.nro_fardo,
                    mark(f.cliente_ok, f.cliente),
                    f.lote,
                    mark(f.color_ok, f.color),
                    mark(f.dn_ok, f.dn),
                    mark(f.corte_ok, f.corte),
                    f"{f.peso_total:.2f}",
                    f"{f.peso_bruto:.2f}",
                    f"{f.peso_neto:.2f}",
                    f.operario,
                ),
                tags=(tag,),
            )

    def _repegar(self, _event=None) -> None:
        try:
            texto = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Carga masiva", "Portapapeles vacío.")
            return
        self._resultado = parsear_pegado(texto, self.db.catalogo)
        self._filas = list(self._resultado.filas)
        self._rellenar()

    def _crear_faltantes(self) -> None:
        falt = maestros_faltantes(self._filas)
        total = sum(len(v) for v in falt.values())
        if total == 0:
            messagebox.showinfo("Carga masiva", "No hay maestros faltantes.")
            return
        detalle = "\n".join(
            f"· {ETIQUETAS[t]}: {', '.join(vs)}" for t, vs in falt.items() if vs
        )
        if not messagebox.askyesno(
            "Crear maestros",
            f"Se crearán {total} valor(es) en Maestros:\n\n{detalle}\n\n¿Continuar?",
        ):
            return
        n = crear_maestros_faltantes(self.db.catalogo, self._filas)
        self._rellenar()
        messagebox.showinfo("Carga masiva", f"Creados / reactivados: {n}")

    def _importar(self) -> None:
        listos = [f for f in self._filas if f.lista_para_importar]
        bloqueados = [f for f in self._filas if not f.lista_para_importar]
        if not listos:
            messagebox.showwarning(
                "Carga masiva",
                "No hay filas listas. Cree los maestros faltantes o corrija errores.",
            )
            return
        msg = f"Importar {len(listos)} registro(s) al día {format_fecha_editable(self.dia)}?"
        if bloqueados:
            msg += f"\n({len(bloqueados)} fila(s) se omitirán por faltantes/errores)"
        if not messagebox.askyesno("Importar", msg):
            return

        ok = 0
        errores = 0
        for f in listos:
            try:
                datos = fila_a_datos(f, self.dia)
                self.db.insertar(datos, fecha_hora=datos.fecha_hora_registro or None)
                ok += 1
            except Exception:  # noqa: BLE001
                errores += 1

        messagebox.showinfo(
            "Carga masiva",
            f"Importados: {ok}" + (f"  ·  Fallidos: {errores}" if errores else ""),
        )
        if self.on_done:
            self.on_done()
        self.destroy()
