"""Hoja de producción del día — detalle de cada fardo + pesaje compacto."""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from config import PORT, TARA_CARRETA_KG, TARA_FARDO_KG, UI_REFRESH_MS
from db import (
    PesajeDatabase,
    format_fecha_corta,
    format_fecha_editable,
    parse_fecha_produccion,
)
from models import DatosEtiqueta, RegistroPesaje
from print_engine import imprimir_etiqueta
from serial_reader import SerialWeightReader
from ui.bulk_paste_dialog import BulkPasteDialog
from ui.widgets import Theme, combo_entry, secondary_button, text_entry


class HojaDiaView(tk.Frame):
    COLS = (
        ("fardo", "Fardo", 55),
        ("cliente", "Cliente", 140),
        ("lote", "Lote", 100),
        ("color", "Color", 100),
        ("dn", "Dn", 50),
        ("corte", "Corte", 55),
        ("total", "P.Total", 70),
        ("tara_c", "Tara Carr.", 75),
        ("tara_f", "Tara Fardo", 75),
        ("bruto", "P.Bruto", 70),
        ("neto", "P.Neto", 70),
        ("hora", "Hora", 80),
        ("operario", "Operario", 90),
        ("sync", "Sync", 45),
    )

    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        reader: SerialWeightReader,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.db = db
        self.reader = reader
        self.on_saved = on_saved
        self.fecha: date = date.today()

        self.var_fecha = tk.StringVar()
        self.var_totales = tk.StringVar()
        self.var_peso = tk.StringVar(value="---.-- kg")
        self.var_status = tk.StringVar(value="●  --")
        self.var_bruto = tk.StringVar(value="---.--")
        self.var_neto = tk.StringVar(value="---.--")
        self.var_hint = tk.StringVar(value="")
        self.var_msg = tk.StringVar(value="")
        self.var_modo = tk.StringVar(value="SIGUIENTE FARDO")

        self.var_nro = tk.StringVar()
        self.var_cliente = tk.StringVar()
        self.var_lote = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_dn = tk.StringVar()
        self.var_corte = tk.StringVar()
        self.var_operario = tk.StringVar()
        self.var_ir_fecha = tk.StringVar(value=format_fecha_editable(date.today()))
        self.var_mostrar_ocultos = tk.BooleanVar(value=False)

        self._regs: list[RegistroPesaje] = []
        self._regs_activos: list[RegistroPesaje] = []
        self._selected_id: Optional[int] = None
        self._target_id: Optional[int] = None
        self._peso_edit: Optional[tuple[float, float, float, float, float]] = None
        # (total, bruto, neto, tara_c, tara_f) del registro en edición
        self._tara_prep: tuple[float, float] = (TARA_CARRETA_KG, TARA_FARDO_KG)
        self._modo_nuevo = True  # hueco «siguiente fardo» listo
        self._force_siguiente = False
        self._ignore_tree_select = False
        self._frozen = False
        self._foto: Optional[dict] = None
        self._printing = False

        self._build()
        self.refrescar_maestros()
        self.refrescar()
        self.after(UI_REFRESH_MS, self._refresh_peso)

    def _build(self) -> None:
        top = tk.Frame(self, bg=Theme.BG)
        top.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(
            top,
            text="HOJA — PRODUCCIÓN EXTRUSORA",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        nav = tk.Frame(top, bg=Theme.BG)
        nav.pack(side=tk.RIGHT)
        tk.Label(nav, text="Ir a", fg=Theme.MUTED, bg=Theme.BG).pack(side=tk.LEFT)
        text_entry(nav, self.var_ir_fecha, 11).pack(side=tk.LEFT, padx=(4, 2))
        tk.Button(nav, text="Ir", command=self._ir_a_fecha, width=3).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        tk.Button(nav, text="◀", command=self._dia_ant, width=3).pack(side=tk.LEFT, padx=2)
        tk.Label(
            nav, textvariable=self.var_fecha, font=("Segoe UI", 13, "bold"),
            fg=Theme.FG, bg=Theme.BG, width=12
        ).pack(side=tk.LEFT)
        tk.Button(nav, text="▶", command=self._dia_sig, width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(nav, text="Hoy", command=self._hoy).pack(side=tk.LEFT, padx=6)
        secondary_button(nav, "Pegar Excel", self.abrir_carga_masiva).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Pie fijo: pesaje compacto + detalle + totales
        foot = tk.Frame(self, bg=Theme.BG)
        foot.pack(side=tk.BOTTOM, fill=tk.X)
        self._build_barra_compacta(foot)

        self.detail = tk.Text(
            foot, height=4, bg=Theme.PANEL, fg=Theme.FG, font=("Consolas", 10),
            relief=tk.FLAT, wrap=tk.WORD
        )
        self.detail.pack(fill=tk.X, padx=12, pady=(4, 2))
        self.detail.configure(state=tk.DISABLED)

        tk.Label(
            foot, textvariable=self.var_totales, font=("Segoe UI", 11, "bold"),
            fg=Theme.US_COLOR, bg=Theme.BG, anchor="e"
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        tools = tk.Frame(wrap, bg=Theme.BG)
        tools.pack(fill=tk.X, pady=(0, 4))
        tk.Checkbutton(
            tools,
            text="Mostrar ocultos",
            variable=self.var_mostrar_ocultos,
            command=self.refrescar,
            fg=Theme.FG,
            bg=Theme.BG,
            selectcolor=Theme.PANEL,
            activebackground=Theme.BG,
            activeforeground=Theme.FG,
        ).pack(side=tk.LEFT)

        # Acciones del fardo seleccionado (siempre visibles arriba de la tabla)
        secondary_button(
            tools, "＋ Siguiente fardo", self.preparar_siguiente
        ).pack(side=tk.LEFT, padx=(12, 0))
        secondary_button(
            tools, "Imprimir seleccionado", self.imprimir
        ).pack(side=tk.RIGHT, padx=(6, 0))
        secondary_button(
            tools, "Guardar seleccionado", self.guardar
        ).pack(side=tk.RIGHT, padx=(6, 0))
        secondary_button(tools, "Ocultar", self.ocultar_seleccionado).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        secondary_button(tools, "Restaurar", self.restaurar_seleccionado).pack(
            side=tk.RIGHT
        )

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Hoja.Treeview",
            background="#2a2a2a",
            foreground=Theme.FG,
            fieldbackground="#2a2a2a",
            rowheight=26,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Hoja.Treeview.Heading",
            background="#111",
            foreground="#fff",
            font=("Segoe UI", 9, "bold"),
        )

        cols = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Hoja.Treeview"
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="center", stretch=True)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("bruto", foreground="#e74c3c")
        self.tree.tag_configure("ultimo", background="#1e3a5f")
        self.tree.tag_configure("oculto", foreground="#888888")
        self.tree.tag_configure(
            "siguiente", foreground="#2ecc71", background="#14301f"
        )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", lambda _e: self.ocultar_seleccionado())
        # Ctrl+V en la hoja (fuera de Entry) abre carga masiva
        self.bind_all("<Control-v>", self._on_ctrl_v, add="+")
        self.bind_all("<Control-V>", self._on_ctrl_v, add="+")

    def _build_barra_compacta(self, parent: tk.Widget) -> None:
        bar = tk.Frame(parent, bg=Theme.PANEL, padx=10, pady=8)
        bar.pack(fill=tk.X, padx=12, pady=(0, 2))

        # Título de modo (edición vs siguiente)
        modo_fr = tk.Frame(bar, bg=Theme.PANEL)
        modo_fr.pack(fill=tk.X, pady=(0, 6))
        self.lbl_modo = tk.Label(
            modo_fr,
            textvariable=self.var_modo,
            font=("Segoe UI", 12, "bold"),
            fg=Theme.ST_COLOR,
            bg=Theme.PANEL,
            anchor="w",
        )
        self.lbl_modo.pack(side=tk.LEFT)
        secondary_button(
            modo_fr, "＋ Preparar siguiente", self.preparar_siguiente
        ).pack(side=tk.RIGHT)

        # Fila 1: peso + campos
        row1 = tk.Frame(bar, bg=Theme.PANEL)
        row1.pack(fill=tk.X)

        left = tk.Frame(row1, bg=Theme.PANEL)
        left.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_peso = tk.Label(
            left,
            textvariable=self.var_peso,
            font=("Consolas", 22, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
            width=12,
            anchor="w",
        )
        self.lbl_peso.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(
            left,
            textvariable=self.var_status,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            width=18,
            anchor="w",
        )
        self.lbl_status.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(
            left, text="Bruto", font=("Segoe UI", 8), fg=Theme.MUTED, bg=Theme.PANEL
        ).pack(side=tk.LEFT, padx=(8, 2))
        tk.Label(
            left,
            textvariable=self.var_bruto,
            font=("Consolas", 12, "bold"),
            fg=Theme.ERR_COLOR,
            bg=Theme.PANEL,
            width=7,
        ).pack(side=tk.LEFT)
        tk.Label(
            left, text="Neto", font=("Segoe UI", 8), fg=Theme.MUTED, bg=Theme.PANEL
        ).pack(side=tk.LEFT, padx=(6, 2))
        tk.Label(
            left,
            textvariable=self.var_neto,
            font=("Consolas", 12, "bold"),
            fg=Theme.ST_COLOR,
            bg=Theme.PANEL,
            width=7,
        ).pack(side=tk.LEFT)

        mid = tk.Frame(row1, bg=Theme.PANEL)
        mid.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        def _lab_col(parent, lab: str):
            col = tk.Frame(parent, bg=Theme.PANEL)
            col.pack(side=tk.LEFT, padx=2)
            tk.Label(
                col, text=lab, font=("Segoe UI", 7), fg=Theme.MUTED, bg=Theme.PANEL
            ).pack(anchor="w")
            return col

        col = _lab_col(mid, "Fardo")
        ent = text_entry(col, self.var_nro, 5)
        ent.configure(font=("Segoe UI", 10))
        ent.pack()

        col = _lab_col(mid, "Cliente")
        self.cb_cliente = combo_entry(col, self.var_cliente, width=12)
        self.cb_cliente.pack()

        col = _lab_col(mid, "Lote")
        ent = text_entry(col, self.var_lote, 8)
        ent.configure(font=("Segoe UI", 10))
        ent.pack()

        col = _lab_col(mid, "Color")
        self.cb_color = combo_entry(col, self.var_color, width=8)
        self.cb_color.pack()

        col = _lab_col(mid, "Dn")
        self.cb_dn = combo_entry(col, self.var_dn, width=5)
        self.cb_dn.pack()

        col = _lab_col(mid, "Corte")
        self.cb_corte = combo_entry(col, self.var_corte, width=5)
        self.cb_corte.pack()

        col = _lab_col(mid, "Op.")
        self.cb_operario = combo_entry(col, self.var_operario, width=8)
        self.cb_operario.pack()

        # Fila 2: botones siempre visibles a todo el ancho
        row2 = tk.Frame(bar, bg=Theme.PANEL)
        row2.pack(fill=tk.X, pady=(10, 0))

        self.btn_foto = tk.Button(
            row2,
            text="CAPTURAR",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=Theme.ACCENT,
            activeforeground="#ffffff",
            activebackground="#3d7cef",
            relief=tk.FLAT,
            padx=22,
            pady=12,
            cursor="hand2",
            command=self.tomar_foto,
        )
        self.btn_foto.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_guardar = tk.Button(
            row2,
            text="GUARDAR",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg="#6c5ce7",
            activeforeground="#ffffff",
            activebackground="#7d6ff0",
            relief=tk.FLAT,
            padx=22,
            pady=12,
            cursor="hand2",
            command=self.guardar,
        )
        self.btn_guardar.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_print = tk.Button(
            row2,
            text="IMPRIMIR / SUBIR",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=22,
            pady=12,
            cursor="hand2",
            command=self.imprimir,
        )
        self.btn_print.pack(side=tk.LEFT)

        tk.Label(
            row2,
            text="En «Siguiente»: peso en vivo → Bruto/Neto auto → CAPTURAR → IMPRIMIR",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT, padx=(16, 0))

        hint_fr = tk.Frame(parent, bg=Theme.BG)
        hint_fr.pack(fill=tk.X, padx=12, pady=(0, 2))
        tk.Label(
            hint_fr,
            textvariable=self.var_hint,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(side=tk.LEFT)
        tk.Label(
            hint_fr,
            textvariable=self.var_msg,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="e",
        ).pack(side=tk.RIGHT)

    def set_fecha(self, dia: date) -> None:
        self.fecha = dia
        self.var_ir_fecha.set(format_fecha_editable(dia))
        self.reanudar_medicion()
        self.refrescar()

    def _ir_a_fecha(self) -> None:
        dia = parse_fecha_produccion(self.var_ir_fecha.get())
        if dia is None:
            messagebox.showwarning("Hoja", "Fecha inválida. Use DD/MM/YYYY.")
            return
        self.set_fecha(dia)

    def _hoy(self) -> None:
        self.set_fecha(date.today())

    def _dia_ant(self) -> None:
        from datetime import timedelta

        self.set_fecha(self.fecha - timedelta(days=1))

    def _dia_sig(self) -> None:
        from datetime import timedelta

        self.set_fecha(self.fecha + timedelta(days=1))

    def refrescar_maestros(self) -> None:
        cat = self.db.catalogo
        pairs = (
            (self.cb_cliente, self.var_cliente, "cliente"),
            (self.cb_color, self.var_color, "color"),
            (self.cb_dn, self.var_dn, "denier"),
            (self.cb_corte, self.var_corte, "corte"),
            (self.cb_operario, self.var_operario, "operario"),
        )
        for cb, var, tipo in pairs:
            valores = list(cat.valores_activos(tipo))  # type: ignore[arg-type]
            actual = var.get().strip()
            if actual and actual not in valores:
                valores = [actual] + valores
            cb["values"] = valores
            if actual in valores:
                var.set(actual)
            elif valores:
                var.set(valores[0])
            else:
                var.set("")

    def refrescar(self) -> None:
        self.var_fecha.set(format_fecha_corta(self.fecha))
        self.var_ir_fecha.set(format_fecha_editable(self.fecha))
        self._regs = self.db.por_fecha(
            self.fecha, incluir_ocultos=self.var_mostrar_ocultos.get()
        )
        self.tree.delete(*self.tree.get_children())

        activos = [r for r in self._regs if r.activo]
        bruto_t = 0.0
        neto_t = 0.0
        for r in self._regs:
            if r.activo:
                bruto_t += r.peso_bruto
                neto_t += r.peso_neto
            hora = self._hora(r.fecha_hora)
            tags: tuple[str, ...]
            if not r.activo:
                tags = ("oculto",)
            elif activos and r.id == activos[-1].id:
                tags = ("ultimo",)
            else:
                tags = ()
            estado = "oculto" if not r.activo else ("✓" if r.estado_sincronizado else "…")
            self.tree.insert(
                "",
                tk.END,
                iid=str(r.id),
                values=(
                    r.nro_fardo,
                    r.cliente,
                    r.lote,
                    r.color,
                    r.denier,
                    r.corte,
                    f"{r.peso_total:.2f}",
                    f"{r.tara_carreta:.2f}",
                    f"{r.tara_fardo:.2f}",
                    f"{r.peso_bruto:.2f}",
                    f"{r.peso_neto:.2f}",
                    hora,
                    r.operario,
                    estado,
                ),
                tags=tags,
            )

        self.var_totales.set(
            f"Total del día · {len(activos)} fardos · "
            f"Bruto {bruto_t:,.1f} Kgrs · Neto {neto_t:,.1f} Kgrs"
        )
        self._regs_activos = activos

        # Fila fantasma: siguiente fardo (hueco listo para pesar)
        nro_sig = self.db.siguiente_nro_fardo(dia=self.fecha)
        last = activos[-1] if activos else None
        self.tree.insert(
            "",
            tk.END,
            iid="__nuevo__",
            values=(
                nro_sig,
                last.cliente if last else "—",
                last.lote if last else "—",
                last.color if last else "—",
                last.denier if last else "—",
                last.corte if last else "—",
                "…",
                f"{(last.tara_carreta if last and last.tara_carreta > 0 else TARA_CARRETA_KG):.2f}",
                f"{(last.tara_fardo if last and last.tara_fardo > 0 else TARA_FARDO_KG):.2f}",
                "…",
                "…",
                "—",
                last.operario if last else "—",
                "▶ SIG.",
            ),
            tags=("siguiente",),
        )

        keep = self._selected_id
        reg_keep = next((r for r in self._regs if r.id == keep), None) if keep else None
        if self._force_siguiente or self._modo_nuevo or reg_keep is None:
            self._force_siguiente = False
            self.preparar_siguiente()
        else:
            self._select_tree_iid(str(reg_keep.id))
            self._cargar_registro_en_barra(reg_keep)
            self._show_detail(reg_keep)

    def _select_tree_iid(self, iid: str) -> None:
        """Selecciona sin reentrar en _on_select (evita bucles al arrancar)."""
        if not self.tree.exists(iid):
            return
        self._ignore_tree_select = True
        try:
            self.tree.selection_set(iid)
            self.tree.see(iid)
        finally:
            self._ignore_tree_select = False

    def preparar_siguiente(self) -> None:
        """
        Hueco del próximo fardo (p. ej. el 11.º si ya hay 10):
        copia datos del último, correlativo nuevo, peso en vivo → Bruto/Neto.
        """
        self._modo_nuevo = True
        self._target_id = None
        self._selected_id = None
        self._peso_edit = None
        self.reanudar_medicion()

        activos = [r for r in self._regs if r.activo] if self._regs else []
        last = activos[-1] if activos else None
        nro = self.db.siguiente_nro_fardo(dia=self.fecha)

        if last:
            self.var_cliente.set(last.cliente)
            self.var_lote.set(last.lote)
            self.var_color.set(last.color)
            self.var_dn.set(last.denier)
            self.var_corte.set(last.corte)
            self.var_operario.set(last.operario)
            tc = last.tara_carreta if last.tara_carreta > 0 else TARA_CARRETA_KG
            tf = last.tara_fardo if last.tara_fardo > 0 else TARA_FARDO_KG
            self._tara_prep = (tc, tf)
        else:
            self.var_lote.set("")
            self._tara_prep = (TARA_CARRETA_KG, TARA_FARDO_KG)

        self.var_nro.set(str(nro))
        self.var_modo.set(f"▶  SIGUIENTE FARDO  #{nro}  ·  listo para pesar")
        self.lbl_modo.config(fg=Theme.ST_COLOR)
        self.var_hint.set(
            f"Hueco #{nro} · peso en vivo actualiza Bruto/Neto · "
            f"CAPTURAR → IMPRIMIR / SUBIR (crea el registro)"
        )
        self.var_msg.set("")
        self.refrescar_maestros()

        self._select_tree_iid("__nuevo__")
        self._show_detail(None)
        self._actualizar_indicadores_vivos()

    def _cargar_registro_en_barra(self, reg: Optional[RegistroPesaje]) -> None:
        """Carga un registro existente en modo edición."""
        self._modo_nuevo = False
        self.reanudar_medicion()
        if reg is None:
            self.preparar_siguiente()
            return

        self._selected_id = reg.id
        self._target_id = reg.id if reg.activo else None
        self._peso_edit = (
            float(reg.peso_total),
            float(reg.peso_bruto),
            float(reg.peso_neto),
            float(reg.tara_carreta) if reg.tara_carreta > 0 else TARA_CARRETA_KG,
            float(reg.tara_fardo) if reg.tara_fardo > 0 else TARA_FARDO_KG,
        )
        self._tara_prep = (self._peso_edit[3], self._peso_edit[4])
        self.var_nro.set(str(reg.nro_fardo))
        self.var_cliente.set(reg.cliente)
        self.var_lote.set(reg.lote)
        self.var_color.set(reg.color)
        self.var_dn.set(reg.denier)
        self.var_corte.set(reg.corte)
        self.var_operario.set(reg.operario)
        self.var_bruto.set(f"{reg.peso_bruto:.2f}")
        self.var_neto.set(f"{reg.peso_neto:.2f}")
        if reg.peso_total > 0:
            self.var_peso.set(f"{reg.peso_total:.2f} kg")
        estado = "oculto — restaure para editar" if not reg.activo else "edición"
        self.var_modo.set(f"✎  EDITANDO FARDO  #{reg.nro_fardo}  (ID {reg.id})")
        self.lbl_modo.config(fg=Theme.US_COLOR)
        self.var_hint.set(
            f"Editando fardo {reg.nro_fardo} · {estado} · "
            f"GUARDAR cambios  |  CAPTURAR peso nuevo → IMPRIMIR  |  "
            f"«＋ Siguiente fardo» para el hueco nuevo"
        )
        self.refrescar_maestros()

    def _hora(self, fecha_hora: str) -> str:
        try:
            dt = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%I:%M %p").lstrip("0").lower()
        except ValueError:
            return fecha_hora[11:16] if len(fecha_hora) >= 16 else ""

    def _on_select(self, _event=None) -> None:
        if self._ignore_tree_select:
            return
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__nuevo__":
            # Ya estamos en el hueco: no reentrar (selection_set dispara este evento).
            if self._modo_nuevo:
                self._show_detail(None)
                return
            self.preparar_siguiente()
            return
        rid = int(iid)
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None:
            return
        self._cargar_registro_en_barra(reg)
        self._show_detail(reg)

    def _show_detail(self, reg: Optional[RegistroPesaje]) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        if self._modo_nuevo or reg is None:
            nro = self.var_nro.get() or "?"
            self.detail.insert(
                tk.END,
                (
                    f"SIGUIENTE FARDO #{nro} — hueco listo para la próxima subida\n"
                    f"Cliente/Lote/Color/Dn/Corte/Op. se copian del último registro.\n"
                    f"El peso en vivo calcula P.Bruto y P.Neto al instante.\n"
                    f"CAPTURAR congela el peso → IMPRIMIR / SUBIR crea el fardo #{nro}."
                ),
            )
        else:
            sync = "Sincronizado" if reg.estado_sincronizado else "Pendiente de sync"
            estado = "OCULTO (soft-delete)" if not reg.activo else sync
            self.detail.insert(
                tk.END,
                (
                    f"ID {reg.id}  |  Fardo {reg.nro_fardo}  |  {reg.fecha_hora}  |  {estado}\n"
                    f"Cliente: {reg.cliente}   Lote: {reg.lote}   Color: {reg.color}\n"
                    f"Dn: {reg.denier}   Corte: {reg.corte} mm   Operario: {reg.operario}\n"
                    f"P.Total {reg.peso_total:.2f}  −  Tara Carreta {reg.tara_carreta:.2f}  "
                    f"= P.Bruto {reg.peso_bruto:.2f}  ·  P.Neto {reg.peso_neto:.2f}"
                ),
            )
        self.detail.configure(state=tk.DISABLED)

    def ocultar_seleccionado(self) -> None:
        """Soft-delete del fardo seleccionado (no borra; no libera el Nº)."""
        if self.focus_es_entrada():
            return
        sel = self.tree.selection()
        if sel and sel[0] == "__nuevo__":
            messagebox.showinfo(
                "Hoja",
                "Esa fila es el hueco del siguiente fardo (aún no existe).",
            )
            return
        rid = self._selected_id
        if rid is None:
            if not sel:
                messagebox.showinfo("Hoja", "Seleccione un fardo en la tabla.")
                return
            if sel[0] == "__nuevo__":
                return
            rid = int(sel[0])
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None:
            messagebox.showinfo("Hoja", "Seleccione un fardo en la tabla.")
            return
        if not reg.activo:
            messagebox.showinfo("Hoja", "Ese fardo ya está oculto.")
            return
        if not messagebox.askyesno(
            "Ocultar fardo",
            f"¿Ocultar fardo {reg.nro_fardo} (ID {reg.id})?\n\n"
            "No se elimina de la base. El Nº de fardo no se reutiliza.\n"
            "Puede restaurarlo con «Mostrar ocultos» → Restaurar.",
        ):
            return
        try:
            self.db.ocultar(rid)
        except ValueError as exc:
            messagebox.showwarning("Hoja", str(exc))
            return
        self.var_msg.set(f"Fardo {reg.nro_fardo} oculto (soft-delete)")
        self.refrescar()
        if self.on_saved:
            self.on_saved()

    def restaurar_seleccionado(self) -> None:
        sel = self.tree.selection()
        if sel and sel[0] == "__nuevo__":
            return
        rid = self._selected_id
        if rid is None:
            if not sel:
                messagebox.showinfo("Hoja", "Seleccione un fardo oculto.")
                return
            if sel[0] == "__nuevo__":
                return
            rid = int(sel[0])
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None:
            messagebox.showinfo("Hoja", "Seleccione un fardo oculto.")
            return
        if reg.activo:
            messagebox.showinfo(
                "Hoja", "Ese fardo está activo. Active «Mostrar ocultos» para ver ocultos."
            )
            return
        try:
            self.db.restaurar(rid)
        except ValueError as exc:
            messagebox.showwarning("Hoja", str(exc))
            return
        self.var_msg.set(f"Fardo {reg.nro_fardo} restaurado")
        self.refrescar()
        if self.on_saved:
            self.on_saved()

    # --- Pesaje compacto -------------------------------------------------

    def _taras_desde_ultimo(self) -> tuple[float, float]:
        if self._modo_nuevo:
            return self._tara_prep
        if self._peso_edit is not None:
            return self._peso_edit[3], self._peso_edit[4]
        activos = getattr(self, "_regs_activos", None) or [
            r for r in self._regs if r.activo
        ]
        if activos:
            u = activos[-1]
            tc = u.tara_carreta if u.tara_carreta > 0 else TARA_CARRETA_KG
            tf = u.tara_fardo if u.tara_fardo > 0 else TARA_FARDO_KG
            return tc, tf
        return TARA_CARRETA_KG, TARA_FARDO_KG

    def _actualizar_indicadores_vivos(self) -> None:
        """Bruto/Neto desde peso en vivo o foto (modo siguiente / captura)."""
        if self._frozen and self._foto is not None:
            total = float(self._foto["weight"])
        else:
            data = self.reader.snapshot()
            if data["weight"] is None:
                if self._modo_nuevo:
                    self.var_bruto.set("---.--")
                    self.var_neto.set("---.--")
                return
            total = float(data["weight"])
        bruto, neto, _, _ = self._calcular_pesos(total)
        self.var_bruto.set(f"{bruto:.2f}")
        self.var_neto.set(f"{neto:.2f}")

    def _calcular_pesos(self, total: float) -> tuple[float, float, float, float]:
        tc, tf = self._taras_desde_ultimo()
        bruto = max(total - tc, 0.0)
        neto = max(total - tc - tf, 0.0)
        return bruto, neto, tc, tf

    def _peso_actual(self) -> Optional[float]:
        if self._frozen and self._foto is not None:
            return float(self._foto["weight"])
        data = self.reader.snapshot()
        if data["weight"] is None:
            return None
        return float(data["weight"])

    def _refresh_peso(self) -> None:
        data = self.reader.snapshot()
        if self._frozen and self._foto is not None:
            total = float(self._foto["weight"])
            unit = self._foto["unit"]
            st = self._foto["status"]
            self.var_peso.set(f"{total:.2f} {unit}")
            self.lbl_peso.config(fg=Theme.ACCENT)
            if st == "ST":
                self.var_status.set("●  ST  FOTO")
                self.lbl_status.config(fg=Theme.ST_COLOR)
            elif st == "US":
                self.var_status.set("●  US  FOTO")
                self.lbl_status.config(fg=Theme.US_COLOR)
            else:
                self.var_status.set("●  --  FOTO")
                self.lbl_status.config(fg=Theme.MUTED)
            bruto, neto, _, _ = self._calcular_pesos(total)
            self.var_bruto.set(f"{bruto:.2f}")
            self.var_neto.set(f"{neto:.2f}")
        else:
            self.lbl_peso.config(fg=Theme.FG)
            if data["weight"] is not None:
                total = float(data["weight"])
                self.var_peso.set(f"{total:.2f} {data['unit']}")
                bruto, neto, _, _ = self._calcular_pesos(total)
                self.var_bruto.set(f"{bruto:.2f}")
                self.var_neto.set(f"{neto:.2f}")
            else:
                self.var_peso.set("---.-- kg")
                self.var_bruto.set("---.--")
                self.var_neto.set("---.--")
            st = data["status"]
            if st == "ST":
                self.var_status.set("●  ST  ESTABLE")
                self.lbl_status.config(fg=Theme.ST_COLOR)
            elif st == "US":
                self.var_status.set("●  US  INESTABLE")
                self.lbl_status.config(fg=Theme.US_COLOR)
            else:
                self.var_status.set("●  --")
                self.lbl_status.config(fg=Theme.MUTED)
            if not data["connected"]:
                self.var_status.set(f"●  {PORT} OFF")
                self.lbl_status.config(fg=Theme.ERR_COLOR)

        self.after(UI_REFRESH_MS, self._refresh_peso)

    def tomar_foto(self) -> bool:
        if self._frozen:
            return True
        data = self.reader.snapshot()
        if data["weight"] is None:
            self.var_msg.set("Sin peso válido para capturar")
            return False
        total = float(data["weight"])
        status = data["status"] or "--"
        self._foto = {"weight": total, "unit": data["unit"], "status": status}
        self._frozen = True
        if status == "US":
            self.var_msg.set(f"Foto US inestable · {total:.2f} kg — ESC reanuda")
        else:
            self.var_msg.set(f"Foto {total:.2f} kg ({status}) — listo para imprimir")
        return True

    def reanudar_medicion(self) -> None:
        if not self._frozen:
            return
        self._frozen = False
        self._foto = None
        self.lbl_peso.config(fg=Theme.FG)
        self.var_msg.set("Medición reanudada")

    def focus_es_entrada(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text))

    def _on_ctrl_v(self, _event=None):
        """Ctrl+V en pestaña Hoja (fuera de Entry) → carga masiva del día actual."""
        try:
            top = self.winfo_toplevel()
            nb = getattr(top, "nb", None)
            if nb is not None and str(nb.select()) != str(self):
                return None
        except tk.TclError:
            return None
        if self.focus_es_entrada():
            return None
        self.abrir_carga_masiva()
        return "break"

    def abrir_carga_masiva(self) -> None:
        try:
            texto = self.clipboard_get()
        except tk.TclError:
            texto = ""
        if not texto.strip():
            messagebox.showinfo(
                "Carga masiva",
                "Copie filas desde Excel (Ctrl+C) y luego pulse Pegar Excel o Ctrl+V aquí.\n\n"
                "Columnas sugeridas: Fardo, Cliente, Lote, Color, Dn, Corte, "
                "P.Total, Tara Carr., Tara Fardo, P.Bruto, P.Neto, Hora, Operario.",
            )
            return
        BulkPasteDialog(
            self,
            self.db,
            self.fecha,
            texto,
            on_done=self._despues_carga_masiva,
        )

    def _despues_carga_masiva(self) -> None:
        self.refrescar_maestros()
        self._force_siguiente = True
        self.refrescar()
        top = self.winfo_toplevel()
        if hasattr(top, "_on_maestros_change"):
            top._on_maestros_change()
        if self.on_saved:
            self.on_saved()

    def _recoger(self, *, permitir_peso_guardado: bool = False) -> Optional[DatosEtiqueta]:
        total: Optional[float] = None
        bruto = neto = tc = tf = 0.0

        if self._frozen and self._foto is not None:
            total = float(self._foto["weight"])
            bruto, neto, tc, tf = self._calcular_pesos(total)
        elif permitir_peso_guardado and self._peso_edit is not None:
            total, bruto, neto, tc, tf = self._peso_edit
        else:
            live = self._peso_actual()
            if live is None:
                if permitir_peso_guardado:
                    self.var_msg.set("Sin peso guardado ni captura. CAPTURAR o elija un fardo.")
                else:
                    self.var_msg.set("Sin peso. Pulse CAPTURAR primero.")
                return None
            if not self._frozen:
                if not self.tomar_foto():
                    return None
            total = self._peso_actual()
            if total is None:
                return None
            bruto, neto, tc, tf = self._calcular_pesos(float(total))

        for nombre, var in (
            ("Cliente", self.var_cliente),
            ("Lote", self.var_lote),
            ("Color", self.var_color),
            ("Dn", self.var_dn),
            ("Corte", self.var_corte),
            ("Operario", self.var_operario),
        ):
            if not var.get().strip():
                self.var_msg.set(f"Complete: {nombre}")
                return None

        nro_txt = self.var_nro.get().strip()
        if not nro_txt.isdigit() or int(nro_txt) < 1:
            self.var_msg.set("Nº Fardo inválido")
            return None

        now = datetime.now()
        # Conservar hora del registro si editamos sin nueva captura
        reg = next((r for r in self._regs if r.id == self._target_id), None)
        if reg and permitir_peso_guardado and not self._frozen:
            fh = reg.fecha_hora
            hora = self._hora(reg.fecha_hora)
        else:
            fh = datetime.combine(self.fecha, now.time()).strftime("%Y-%m-%d %H:%M:%S")
            hora = now.strftime("%I:%M %p").lstrip("0").lower()

        return DatosEtiqueta(
            color=self.var_color.get().strip(),
            cliente=self.var_cliente.get().strip(),
            lote=self.var_lote.get().strip(),
            dn=self.var_dn.get().strip(),
            corte=self.var_corte.get().strip(),
            nro_fardo=str(int(nro_txt)),
            fecha=format_fecha_editable(self.fecha),
            peso_bruto=bruto,
            peso_neto=neto,
            operario=self.var_operario.get().strip(),
            peso_total=float(total),
            tara_carreta=tc,
            tara_fardo=tf,
            hora=hora,
            fecha_hora_registro=fh,
        )

    def guardar(self) -> None:
        """Guarda cambios del fardo seleccionado (sin obligar a reimprimir)."""
        if self._target_id is None and self._selected_id is not None:
            reg = next((r for r in self._regs if r.id == self._selected_id), None)
            if reg and not reg.activo:
                messagebox.showinfo(
                    "Hoja",
                    "El fardo está oculto. Restáurelo antes de editarlo.",
                )
                return

        # Nuevo fardo: exige captura / peso en vivo. Edición: puede reusar pesos.
        creando = self._modo_nuevo or self._target_id is None
        datos = self._recoger(permitir_peso_guardado=not creando)
        if datos is None:
            return

        target_id = self._target_id
        try:
            if target_id is not None:
                self.db.actualizar(target_id, datos)
                self.var_msg.set(f"Fardo {datos.nro_fardo} guardado (ID {target_id})")
            else:
                self.db.insertar(datos, fecha_hora=datos.fecha_hora_registro or None)
                self.var_msg.set(f"Fardo {datos.nro_fardo} creado · listo el siguiente")
                self._force_siguiente = True
        except ValueError as exc:
            messagebox.showwarning("Hoja", str(exc))
            return

        self.reanudar_medicion()
        self.refrescar()
        if self.on_saved:
            self.on_saved()

    def imprimir(self) -> None:
        if self._printing:
            return
        if self._target_id is None and self._selected_id is not None:
            reg = next((r for r in self._regs if r.id == self._selected_id), None)
            if reg and not reg.activo:
                messagebox.showinfo(
                    "Hoja",
                    "El fardo está oculto. Restáurelo antes de imprimir.",
                )
                return

        creando = self._modo_nuevo or self._target_id is None
        # Nuevo: captura/vivo. Edición sin foto: reimprimir con pesos guardados.
        datos = self._recoger(permitir_peso_guardado=not creando)
        if datos is None:
            return

        target_id = self._target_id
        self._printing = True
        self.btn_print.config(state=tk.DISABLED)

        def _worker() -> None:
            try:
                imprimir_etiqueta(datos)
                if target_id is not None:
                    self.db.actualizar(target_id, datos)
                    accion = "actualizado"
                else:
                    self.db.insertar(datos, fecha_hora=datos.fecha_hora_registro or None)
                    accion = "creado"
                self.after(0, self._on_print_ok, datos, accion)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda: messagebox.showerror("Error", msg))
                self.after(0, lambda: self.var_msg.set("Error al imprimir"))
            finally:
                self.after(0, self._print_done)

        threading.Thread(target=_worker, name="HojaPrintWorker", daemon=True).start()

    def _on_print_ok(self, datos: DatosEtiqueta, accion: str) -> None:
        self.var_msg.set(
            f"Fardo {datos.nro_fardo} {accion} · "
            f"Bruto {datos.peso_bruto:.2f} / Neto {datos.peso_neto:.2f} kg"
        )
        if accion == "creado":
            self._force_siguiente = True
        self.reanudar_medicion()
        self.refrescar()
        if self.on_saved:
            self.on_saved()

    def _print_done(self) -> None:
        self._printing = False
        self.btn_print.config(state=tk.NORMAL)
