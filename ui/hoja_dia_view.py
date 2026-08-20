"""Hoja de producción del día — detalle de cada fardo + pesaje compacto."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from config import (
    MODO_FARDO_CONTINUAR,
    MODO_FARDO_REINICIAR,
    PORT,
    TARA_CARRETA_KG,
    TARA_FARDO_KG,
    UI_REFRESH_MS,
)
from db import (
    PesajeDatabase,
    format_fecha_corta,
    format_fecha_editable,
    parse_fecha_produccion,
)
from catalog import normalizar_maestro
from models import DatosEtiqueta, RegistroPesaje
from serial_reader import SerialWeightReader
from ui.bulk_paste_dialog import BulkPasteDialog
from ui.bulk_file_dialog import BulkFileDialog
from ui.drop_zone import ExcelPickDialog
from ui.print_preview_dialog import PrintPreviewDialog
from ui.row_actions import TreeRowActions
from ui.searchable_dropdown import SearchableDropdown
from ui.tree_excel import TreeExcelEditor
from ui.widgets import Theme, confirm_modal, secondary_button, text_entry
from utils import normalizar_lote, prefijo_lote


class HojaDiaView(tk.Frame):
    COLS = (
        ("n", "N°", 40),
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
        ("accion", "Acción", 255),
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
        self.var_modo = tk.StringVar(value="Nuevo fardo")

        self.var_nro = tk.StringVar()
        self.var_cliente = tk.StringVar()
        self.var_lote = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_dn = tk.StringVar()
        self.var_corte = tk.StringVar()
        self.var_operario = tk.StringVar()
        self.var_ir_fecha = tk.StringVar(value=format_fecha_editable(date.today()))
        self.var_mostrar_ocultos = tk.BooleanVar(value=False)
        self.var_modo_fardo = tk.StringVar(value=self.db.get_modo_fardo())

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
        self._guardando = False
        self._espera_bascula_cero = False
        self._iids_orden: list[str] = []
        self._editando_id: Optional[int] = None

        self._build()
        self.refrescar_maestros()
        self.refrescar()
        self.after(UI_REFRESH_MS, self._refresh_peso)

    def _build(self) -> None:
        top = tk.Frame(self, bg=Theme.BG)
        top.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(
            top,
            text="HOJA DE CÁLCULO — PRODUCCIÓN EXTRUSORA",
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
        secondary_button(nav, "Archivo Excel…", self.abrir_carga_archivo).pack(
            side=tk.LEFT, padx=(6, 0)
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
        self.wrap_tree = wrap

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

        tk.Label(
            tools,
            text="Amarillo = sin guardar  ·  Blanco = guardado  ·  acciones a la derecha de cada fila",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(16, 0))

        self._build_filtros_maestros(wrap)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Hoja.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=28,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Hoja.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 9, "bold"),
        )

        cols = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Hoja.Treeview"
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="center", stretch=True)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("bruto", foreground=Theme.ERR_COLOR)
        self.tree.tag_configure("ultimo", background=Theme.ROW_LAST)
        self.tree.tag_configure("oculto", foreground=Theme.MUTED)
        self.tree.tag_configure(
            "siguiente", foreground=Theme.FG, background=Theme.ROW_DIRTY
        )
        self.excel = TreeExcelEditor(
            self.tree,
            tuple(c[0] for c in self.COLS),
            {
                "fardo",
                "cliente",
                "lote",
                "color",
                "dn",
                "corte",
                "total",
                "tara_c",
                "tara_f",
                "operario",
            },
            combo_cols={"cliente", "color", "dn", "corte", "operario"},
            on_change=self._on_excel_change,
            normalize=self._excel_normalize,
            can_edit=self._excel_puede_editar,
        )
        self.row_actions = TreeRowActions(self.tree, "accion", self._spec_accion)
        self.row_actions.attach_scroll(sy)
        self.tree.bind("<ButtonRelease-1>", lambda _e: self.row_actions.sync(), add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", self._on_delete_fila)
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
        self.ent_nro = text_entry(col, self.var_nro, 5)
        self.ent_nro.configure(font=("Segoe UI", 10))
        self.ent_nro.pack(anchor="w")
        self.ent_nro.bind("<KeyRelease>", self._on_nro_manual)
        self.ent_nro.bind("<FocusOut>", self._on_nro_manual)

        col = _lab_col(mid, "Cliente")
        self.cb_cliente = self._dd_maestro(col, self.var_cliente, "cliente", 12)

        col = _lab_col(mid, "Lote")
        self.ent_lote = text_entry(col, self.var_lote, 12)
        self.ent_lote.configure(font=("Segoe UI", 10))
        self.ent_lote.pack()
        self.ent_lote.bind("<FocusIn>", self._on_lote_focus_in)
        self.ent_lote.bind("<FocusOut>", self._on_lote_focus_out)

        col = _lab_col(mid, "Color")
        self.cb_color = self._dd_maestro(col, self.var_color, "color", 8)

        col = _lab_col(mid, "Dn")
        self.cb_dn = self._dd_maestro(col, self.var_dn, "dn", 5)

        col = _lab_col(mid, "Corte")
        self.cb_corte = self._dd_maestro(col, self.var_corte, "corte", 5)

        col = _lab_col(mid, "Op.")
        self.cb_operario = self._dd_maestro(col, self.var_operario, "operario", 8)

        row_modo = tk.Frame(bar, bg=Theme.PANEL)
        row_modo.pack(fill=tk.X, pady=(6, 0))
        tk.Label(
            row_modo,
            text="Nº fardo:",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.btn_fardo_nuevo = tk.Button(
            row_modo,
            text="Contar de 1",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._set_modo_fardo(MODO_FARDO_REINICIAR),
        )
        self.btn_fardo_nuevo.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_fardo_seguir = tk.Button(
            row_modo,
            text="Continuar del día anterior",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._set_modo_fardo(MODO_FARDO_CONTINUAR),
        )
        self.btn_fardo_seguir.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(
            row_modo,
            text="o escriba el número; el próximo registro será ese + 1",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT)
        self._actualizar_lbl_modo_fardo()

        tk.Label(
            bar,
            text=(
                "El peso de la báscula se refleja en la fila nueva. "
                "Con datos completos y peso estable se registra solo. "
                "IMPRIMIR abre la vista previa en fardos ya guardados."
            ),
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            anchor="w",
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(8, 0))

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

    def _dd_maestro(
        self, parent: tk.Widget, var: tk.StringVar, key: str, width: int
    ) -> SearchableDropdown:
        dd = SearchableDropdown(
            parent,
            textvariable=var,
            width=width,
            font=("Segoe UI", 10),
            on_commit=lambda valor, k=key: self._on_maestro_barra(k, valor),
            compact=True,
        )
        dd.pack(fill=tk.X)
        return dd

    def _build_filtros_maestros(self, parent: tk.Widget) -> None:
        row = tk.Frame(parent, bg=Theme.BG)
        row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            row,
            text="Buscar / filtrar",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(0, 8))

        def _filtro(key: str, placeholder: str, width: int) -> SearchableDropdown:
            dd = SearchableDropdown(
                row,
                width=width,
                placeholder=placeholder,
                font=("Segoe UI", 9),
                on_change=lambda _v: self._aplicar_filtros_maestros(),
                compact=True,
            )
            dd.pack(side=tk.LEFT, padx=(0, 6), ipady=1)
            dd._refresh_placeholder()
            return dd

        self.dd_filtro_cliente = _filtro("cliente", "Cliente", 14)
        self.dd_filtro_color = _filtro("color", "Color", 10)
        self.dd_filtro_dn = _filtro("dn", "Dn", 6)
        self.dd_filtro_corte = _filtro("corte", "Corte", 6)
        self.dd_filtro_operario = _filtro("operario", "Operario", 10)
        secondary_button(row, "Limpiar filtros", self._limpiar_filtros_maestros).pack(
            side=tk.LEFT, padx=(4, 0)
        )

    def _on_maestro_barra(self, key: str, valor: str) -> None:
        if not valor or not hasattr(self, "tree"):
            return
        iid = ""
        if self._modo_nuevo and self.tree.exists("__nuevo__"):
            iid = "__nuevo__"
        elif self._selected_id is not None and self.tree.exists(str(self._selected_id)):
            iid = str(self._selected_id)
        if iid:
            self.tree.set(iid, key, valor)
            self.excel.mark_dirty(iid)

    def _filtros_activos(self) -> dict[str, str]:
        if not hasattr(self, "dd_filtro_cliente"):
            return {}
        return {
            "cliente": self.dd_filtro_cliente.get(),
            "color": self.dd_filtro_color.get(),
            "dn": self.dd_filtro_dn.get(),
            "corte": self.dd_filtro_corte.get(),
            "operario": self.dd_filtro_operario.get(),
        }

    def _aplicar_filtros_maestros(self, *_args) -> None:
        if not hasattr(self, "tree"):
            return
        filtros = self._filtros_activos()
        keys = [c[0] for c in self.COLS]
        for iid in self._iids_orden:
            if not self.tree.exists(iid):
                continue
            vals = dict(zip(keys, self.tree.item(iid, "values")))
            visible = True
            for col, q in filtros.items():
                if q and normalizar_maestro(q) not in normalizar_maestro(
                    str(vals.get(col, ""))
                ):
                    visible = False
                    break
            if visible:
                self.tree.reattach(iid, "", "end")
            else:
                self.tree.detach(iid)
        if self.tree.exists("__nuevo__"):
            self.tree.move("__nuevo__", "", "end")
        if hasattr(self, "row_actions"):
            self.row_actions.sync()

    def _limpiar_filtros_maestros(self) -> None:
        for dd in (
            self.dd_filtro_cliente,
            self.dd_filtro_color,
            self.dd_filtro_dn,
            self.dd_filtro_corte,
            self.dd_filtro_operario,
        ):
            dd.set("")
            dd._refresh_placeholder()
        self._aplicar_filtros_maestros()

    def refrescar_maestros(self) -> None:
        cat = self.db.catalogo
        valores = {
            "cliente": list(cat.valores_activos("cliente")),
            "color": list(cat.valores_activos("color")),
            "dn": list(cat.valores_activos("denier")),
            "corte": list(cat.valores_activos("corte")),
            "operario": list(cat.valores_activos("operario")),
        }
        pairs = (
            (self.cb_cliente, self.var_cliente, "cliente"),
            (self.cb_color, self.var_color, "color"),
            (self.cb_dn, self.var_dn, "dn"),
            (self.cb_corte, self.var_corte, "corte"),
            (self.cb_operario, self.var_operario, "operario"),
        )
        for dd, var, key in pairs:
            lista = list(valores[key])
            actual = var.get().strip()
            if actual and actual not in lista:
                lista = [actual] + lista
            dd.set_values(lista)
            if actual:
                dd.set(actual)
            elif lista:
                var.set(lista[0])
                dd.set(lista[0])
            else:
                dd.set("")
        filtros = (
            (getattr(self, "dd_filtro_cliente", None), "cliente"),
            (getattr(self, "dd_filtro_color", None), "color"),
            (getattr(self, "dd_filtro_dn", None), "dn"),
            (getattr(self, "dd_filtro_corte", None), "corte"),
            (getattr(self, "dd_filtro_operario", None), "operario"),
        )
        for dd, key in filtros:
            if dd is not None:
                dd.set_values(valores[key])
        if hasattr(self, "excel"):
            self.excel.set_combo_values(valores)

    def _actualizar_lbl_modo_fardo(self) -> None:
        modo = self.var_modo_fardo.get()
        if modo not in (MODO_FARDO_CONTINUAR, MODO_FARDO_REINICIAR):
            modo = MODO_FARDO_CONTINUAR
            self.var_modo_fardo.set(modo)
        activo = dict(
            bg=Theme.ST_COLOR, fg="#fff", activebackground=Theme.BTN_ACTIVE
        )
        inactivo = dict(
            bg=Theme.BORDER, fg=Theme.MUTED, activebackground="#c5d0dc"
        )
        if modo == MODO_FARDO_CONTINUAR:
            self.btn_fardo_seguir.configure(**activo)
            self.btn_fardo_nuevo.configure(**inactivo)
        else:
            self.btn_fardo_nuevo.configure(
                bg=Theme.US_COLOR, fg="#fff", activebackground="#d97706"
            )
            self.btn_fardo_seguir.configure(**inactivo)

    def _nro_propuesto(self) -> int:
        """Último fardo guardado del día + 1, o 1 / continuación del día anterior."""
        activos = [r for r in (self._regs or []) if r.activo]
        if activos:
            try:
                return int(str(activos[-1].nro_fardo).strip()) + 1
            except ValueError:
                pass
        if self.var_modo_fardo.get() == MODO_FARDO_REINICIAR:
            return 1
        return self.db.ultimo_nro_fardo_antes(self.fecha) + 1

    def _on_nro_manual(self, _event=None) -> None:
        if not self._modo_nuevo:
            return
        nro = self.var_nro.get().strip()
        if self.tree.exists("__nuevo__"):
            self.tree.set("__nuevo__", "fardo", nro or "…")

    def _set_modo_fardo(self, modo: str) -> None:
        if modo not in (MODO_FARDO_CONTINUAR, MODO_FARDO_REINICIAR):
            return
        self.var_modo_fardo.set(modo)
        self.db.set_modo_fardo(modo)
        self._actualizar_lbl_modo_fardo()
        if not self._modo_nuevo:
            return
        if modo == MODO_FARDO_REINICIAR:
            nro = 1
        else:
            nro = self.db.ultimo_nro_fardo_antes(self.fecha) + 1
        self.var_nro.set(str(nro))
        self.var_modo.set(f"Nuevo fardo #{nro}")
        origen = (
            "Contar de 1"
            if modo == MODO_FARDO_REINICIAR
            else "Continuar del día anterior"
        )
        self.var_msg.set(f"{origen} → #{nro}. El próximo será {nro + 1} al guardar.")
        if self.tree.exists("__nuevo__"):
            self.tree.set("__nuevo__", "fardo", str(nro))
        self._show_detail(None)

    def _lote_prefijo(self) -> str:
        return prefijo_lote(self.fecha.year)

    def _asegurar_prefijo_lote(self) -> None:
        """Deja ``26LOC `` listo para que el operario solo complete el número."""
        cur = self.var_lote.get()
        pref = self._lote_prefijo()
        if not cur.strip():
            self.var_lote.set(pref)
            return
        norm = normalizar_lote(cur, anio=self.fecha.year)
        if norm:
            self.var_lote.set(norm)
        elif not cur.upper().replace(" ", "").startswith(
            pref.upper().replace(" ", "")
        ):
            self.var_lote.set(pref + cur.strip())

    def _on_lote_focus_in(self, _event=None) -> None:
        self._asegurar_prefijo_lote()
        # Cursor al final para escribir el número tras «26LOC »
        try:
            self.ent_lote.icursor(tk.END)
        except tk.TclError:
            pass

    def _on_lote_focus_out(self, _event=None) -> None:
        cur = self.var_lote.get().strip()
        pref = self._lote_prefijo()
        if not cur or cur.upper() == pref.strip().upper():
            self.var_lote.set(pref)
            return
        norm = normalizar_lote(cur, anio=self.fecha.year)
        if norm:
            self.var_lote.set(norm)
        else:
            self._asegurar_prefijo_lote()

    def refrescar(self) -> None:
        if hasattr(self, "excel"):
            self.excel.commit()
            self.excel.clear()
        self.var_modo_fardo.set(self.db.get_modo_fardo())
        if hasattr(self, "btn_fardo_seguir"):
            self._actualizar_lbl_modo_fardo()
        self.var_fecha.set(format_fecha_corta(self.fecha))
        self.var_ir_fecha.set(format_fecha_editable(self.fecha))
        self._regs = self.db.por_fecha(
            self.fecha, incluir_ocultos=self.var_mostrar_ocultos.get()
        )
        self.tree.delete(*self.tree.get_children())
        self._iids_orden = []

        activos = [r for r in self._regs if r.activo]
        bruto_t = 0.0
        neto_t = 0.0
        for idx, r in enumerate(self._regs, start=1):
            if r.activo:
                bruto_t += r.peso_bruto
                neto_t += r.peso_neto
            hora = self._hora(r.fecha_hora)
            tags: tuple[str, ...]
            if not r.activo:
                tags = ("oculto",)
            elif activos and r.id == activos[-1].id:
                tags = ("saved", "ultimo")
            else:
                tags = ("saved",)
            estado = "oculto" if not r.activo else ("✓" if r.estado_sincronizado else "…")
            self.tree.insert(
                "",
                tk.END,
                iid=str(r.id),
                values=(
                    idx,
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
                    "",
                ),
                tags=tags,
            )
            self._iids_orden.append(str(r.id))

        self.var_totales.set(
            f"Total del día · {len(activos)} fardos · "
            f"Bruto {bruto_t:,.1f} Kgrs · Neto {neto_t:,.1f} Kgrs"
        )
        self._regs_activos = activos

        nro_keep: Optional[int] = None
        if self._modo_nuevo and not self._force_siguiente:
            try:
                raw = self.var_nro.get().strip()
                if raw:
                    nro_keep = int(raw)
            except ValueError:
                nro_keep = None
        nro_sig = nro_keep if nro_keep is not None else self._nro_propuesto()
        last = activos[-1] if activos else None
        self.tree.insert(
            "",
            tk.END,
            iid="__nuevo__",
            values=(
                len(self._regs) + 1,
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
                "nuevo",
                "",
            ),
            tags=("siguiente", "dirty"),
        )
        self._aplicar_filtros_maestros()

        keep = self._selected_id
        reg_keep = next((r for r in self._regs if r.id == keep), None) if keep else None
        visibles = set(self.tree.get_children())
        if self._force_siguiente or self._modo_nuevo or reg_keep is None:
            usar = None if self._force_siguiente else nro_keep
            self._force_siguiente = False
            self.preparar_siguiente(nro=usar)
        elif str(reg_keep.id) not in visibles:
            self._force_siguiente = False
            self.preparar_siguiente()
        else:
            self._select_tree_iid(str(reg_keep.id))
            self._cargar_registro_en_barra(reg_keep)
            self._show_detail(reg_keep)
        if hasattr(self, "row_actions"):
            self.after_idle(self.row_actions.sync)

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

    def preparar_siguiente(self, nro: Optional[int] = None) -> None:
        """Prepara la fila nueva: copia datos del último y propone el Nº de fardo."""
        self._modo_nuevo = True
        self._editando_id = None
        self._target_id = None
        self._selected_id = None
        self._peso_edit = None
        self.reanudar_medicion()

        activos = [r for r in self._regs if r.activo] if self._regs else []
        last = activos[-1] if activos else None
        if nro is None:
            nro = self._nro_propuesto()

        if last:
            self.var_cliente.set(last.cliente)
            lote = normalizar_lote(last.lote, anio=self.fecha.year)
            self.var_lote.set(lote if lote else self._lote_prefijo())
            self.var_color.set(last.color)
            self.var_dn.set(last.denier)
            self.var_corte.set(last.corte)
            self.var_operario.set(last.operario)
            tc = last.tara_carreta if last.tara_carreta > 0 else TARA_CARRETA_KG
            tf = last.tara_fardo if last.tara_fardo > 0 else TARA_FARDO_KG
            self._tara_prep = (tc, tf)
        else:
            self.var_lote.set(self._lote_prefijo())
            self._tara_prep = (TARA_CARRETA_KG, TARA_FARDO_KG)

        self.var_nro.set(str(nro))
        self.var_modo.set(f"Nuevo fardo #{nro}")
        self.lbl_modo.config(fg=Theme.ST_COLOR)
        self.var_hint.set(
            f"Nº {nro} · complete maestros · el peso se actualiza solo · "
            f"con peso estable se registra y el próximo será + 1"
        )
        self.var_msg.set("")
        self.refrescar_maestros()
        self._asegurar_prefijo_lote()
        if self.tree.exists("__nuevo__"):
            self.tree.set("__nuevo__", "fardo", str(nro))

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
        lote = normalizar_lote(reg.lote, anio=self.fecha.year)
        self.var_lote.set(lote if lote else reg.lote)
        self.var_color.set(reg.color)
        self.var_dn.set(reg.denier)
        self.var_corte.set(reg.corte)
        self.var_operario.set(reg.operario)
        self.var_bruto.set(f"{reg.peso_bruto:.2f}")
        self.var_neto.set(f"{reg.peso_neto:.2f}")
        if reg.peso_total > 0:
            self.var_peso.set(f"{reg.peso_total:.2f} kg")
        estado = "oculto — restaure para editar" if not reg.activo else "edición"
        self.var_modo.set(f"Editando fardo #{reg.nro_fardo}")
        self.lbl_modo.config(fg=Theme.US_COLOR)
        self.var_hint.set(
            f"Editando fardo {reg.nro_fardo} · {estado} · cada cambio se guarda al salir de la celda"
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
            self._editando_id = None
            if hasattr(self, "row_actions"):
                self.row_actions.sync()
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
                    f"Nuevo fardo #{nro} — elija maestros; el peso de la báscula llena P.Total/Bruto/Neto.\n"
                    f"Lote: {self._lote_prefijo().strip()} + número (ej. {self._lote_prefijo()}15).\n"
                    f"Con todos los datos y peso estable (ST) se registra solo.\n"
                    f"IMPRIMIR aparece en filas guardadas y completas (abre vista previa)."
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

    def _on_delete_fila(self, _event=None):
        if self.focus_es_entrada():
            return
        self.ocultar_seleccionado()

    def ocultar_seleccionado(self) -> None:
        """Soft-delete del fardo (no borra; no libera el Nº)."""
        sel = self.tree.selection()
        if sel and sel[0] == "__nuevo__":
            messagebox.showinfo(
                "Hoja",
                "Esa fila aún no está guardada. Complete los datos y el peso se registrará solo.",
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
        if not confirm_modal(
            self,
            "Ocultar fardo",
            f"¿Ocultar fardo {reg.nro_fardo} (ID {reg.id})?\n\n"
            "No se elimina de la base (soft-delete). El Nº de fardo no se reutiliza.\n"
            "Puede restaurarlo con «Mostrar ocultos» y el botón Restaurar de la fila.",
            ok_text="Ocultar",
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

    def _excel_puede_editar(self, iid: str, _key: str) -> bool:
        if iid == "__nuevo__":
            return True
        return self._editando_id is not None and iid == str(self._editando_id)

    def _spec_accion(self, iid: str):
        if iid == "__nuevo__":
            return None
        try:
            rid = int(iid)
        except ValueError:
            return None
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None:
            return None
        if not reg.activo:
            return [
                ("Restaurar", Theme.ST_COLOR, lambda i=iid: self._restaurar_fila(i))
            ]
        acciones = [
            ("Editar", Theme.ACCENT, lambda i=iid: self._iniciar_edicion(i)),
            ("Ocultar", Theme.ERR_COLOR, lambda i=iid: self._ocultar_fila(i)),
        ]
        if self._registro_completo(reg):
            acciones.insert(
                1,
                ("Imprimir", Theme.BTN_BG, lambda i=iid: self._abrir_preview(i)),
            )
        return acciones

    def _ocultar_fila(self, iid: str) -> None:
        try:
            rid = int(iid)
        except ValueError:
            return
        self._selected_id = rid
        self.ocultar_seleccionado()

    def _restaurar_fila(self, iid: str) -> None:
        try:
            rid = int(iid)
        except ValueError:
            return
        self._selected_id = rid
        self.restaurar_seleccionado()

    def _iniciar_edicion(self, iid: str) -> None:
        try:
            rid = int(iid)
        except ValueError:
            return
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None or not reg.activo:
            messagebox.showinfo("Hoja", "Ese fardo no se puede editar.")
            return
        self._editando_id = rid
        self._modo_nuevo = False
        self._select_tree_iid(iid)
        self._cargar_registro_en_barra(reg)
        self._show_detail(reg)
        self.row_actions.sync()
        self.var_msg.set("Edición activa · cada cambio se guarda al confirmar la celda")

    def _taras_desde_ultimo(self) -> tuple[float, float]:
        if self._modo_nuevo and hasattr(self, "tree") and self.tree.exists("__nuevo__"):
            try:
                tc = float(str(self.tree.set("__nuevo__", "tara_c")).replace(",", "."))
                tf = float(str(self.tree.set("__nuevo__", "tara_f")).replace(",", "."))
                if tc > 0:
                    return tc, tf if tf >= 0 else TARA_FARDO_KG
            except ValueError:
                pass
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
        self._sync_peso_fila_nueva(total, bruto, neto)

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

        self._sync_peso_fila_nueva()
        self._auto_guardar_si_listo()
        self.after(UI_REFRESH_MS, self._refresh_peso)

    def _sync_peso_fila_nueva(
        self,
        total: Optional[float] = None,
        bruto: Optional[float] = None,
        neto: Optional[float] = None,
    ) -> None:
        if not self._modo_nuevo or not hasattr(self, "tree"):
            return
        if not self.tree.exists("__nuevo__"):
            return
        if total is None:
            if self._frozen and self._foto is not None:
                total = float(self._foto["weight"])
            else:
                data = self.reader.snapshot()
                if data["weight"] is None:
                    return
                total = float(data["weight"])
            bruto, neto, _, _ = self._calcular_pesos(total)
        assert bruto is not None and neto is not None
        self.tree.set("__nuevo__", "total", f"{total:.2f}")
        self.tree.set("__nuevo__", "bruto", f"{bruto:.2f}")
        self.tree.set("__nuevo__", "neto", f"{neto:.2f}")

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

    def _excel_normalize(self, key: str, texto: str) -> str:
        if key == "lote":
            return normalizar_lote(texto, anio=self.fecha.year) or texto
        return texto

    def _on_excel_change(self, iid: str, key: str, texto: str) -> None:
        if iid == "__nuevo__":
            self._modo_nuevo = True
            self._target_id = None
        else:
            try:
                rid = int(iid)
                self._selected_id = rid
                self._target_id = rid
                self._modo_nuevo = False
            except ValueError:
                pass
        mapping = {
            "fardo": self.var_nro,
            "cliente": self.var_cliente,
            "lote": self.var_lote,
            "color": self.var_color,
            "dn": self.var_dn,
            "corte": self.var_corte,
            "operario": self.var_operario,
        }
        var = mapping.get(key)
        if var is not None:
            var.set(texto)
        if key in ("total", "tara_c", "tara_f"):
            self._recalc_fila_excel(iid)
        if iid == "__nuevo__":
            self.var_msg.set("Complete los maestros · el peso se actualiza solo")
            self.after(300, self._auto_guardar_si_listo)
        elif self._editando_id is not None:
            self._persistir_edicion()

    def _recalc_fila_excel(self, iid: str) -> None:
        def _f(col: str) -> float:
            raw = str(self.tree.set(iid, col)).replace(",", ".").replace("…", "").strip()
            try:
                return float(raw) if raw else 0.0
            except ValueError:
                return 0.0

        total = _f("total")
        tc = _f("tara_c") or TARA_CARRETA_KG
        tf = _f("tara_f") or TARA_FARDO_KG
        if total <= 0:
            return
        bruto = max(total - tc, 0.0)
        neto = max(total - tc - tf, 0.0)
        self.tree.set(iid, "bruto", f"{bruto:.2f}")
        self.tree.set(iid, "neto", f"{neto:.2f}")
        self.var_bruto.set(f"{bruto:.2f}")
        self.var_neto.set(f"{neto:.2f}")
        self.var_peso.set(f"{total:.2f} kg")
        self._peso_edit = (total, bruto, neto, tc, tf)
        self._tara_prep = (tc, tf)

    def focus_es_entrada(self) -> bool:
        if getattr(self, "excel", None) is not None and self.excel._edit is not None:
            return True
        w = self.focus_get()
        if isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text, tk.Listbox)):
            return True
        return isinstance(getattr(w, "master", None), SearchableDropdown)

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
                "P.Total, Tara Carr., Tara Fardo, P.Bruto, P.Neto, Hora, Operario.\n\n"
                "También puede usar «Archivo Excel…» para importar el .xlsm mensual completo.",
            )
            return
        BulkPasteDialog(
            self,
            self.db,
            self.fecha,
            texto,
            on_done=self._despues_carga_masiva,
        )

    def abrir_carga_archivo(self) -> None:
        ExcelPickDialog(self, on_file=self.abrir_archivo_excel)

    def abrir_archivo_excel(self, path: str) -> None:
        if not path:
            return
        BulkFileDialog(
            self,
            self.db,
            path,
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

        if permitir_peso_guardado and self._peso_edit is not None:
            total, bruto, neto, tc, tf = self._peso_edit
        else:
            total = self._peso_desde_fila_o_vivo()
            if total is None:
                self.var_msg.set("Sin peso en la fila ni en la báscula.")
                return None
            bruto, neto, tc, tf = self._calcular_pesos(float(total))

        for nombre, var in (
            ("Cliente", self.var_cliente),
            ("Color", self.var_color),
            ("Dn", self.var_dn),
            ("Corte", self.var_corte),
            ("Operario", self.var_operario),
        ):
            if not var.get().strip():
                self.var_msg.set(f"Complete: {nombre}")
                return None

        lote = normalizar_lote(self.var_lote.get(), anio=self.fecha.year)
        if not lote:
            self.var_msg.set(
                f"Lote incompleto. Use {self._lote_prefijo().strip()} + número "
                f"(ej. {self._lote_prefijo()}15)"
            )
            self.var_lote.set(self._lote_prefijo())
            try:
                self.ent_lote.focus_set()
                self.ent_lote.icursor(tk.END)
            except tk.TclError:
                pass
            return None
        self.var_lote.set(lote)

        nro_txt = self.var_nro.get().strip()
        if not nro_txt.isdigit() or int(nro_txt) < 1:
            self.var_msg.set("Nº Fardo inválido")
            return None
        if self.db.existe_fardo_en_lote(
            lote, nro_txt, excluir_id=self._target_id
        ):
            self.var_msg.set(
                f"El fardo {nro_txt} ya existe en el lote {lote}"
            )
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
            lote=lote,
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

    def _peso_desde_fila_o_vivo(self) -> Optional[float]:
        if hasattr(self, "tree") and self.tree.exists("__nuevo__"):
            raw = (
                str(self.tree.set("__nuevo__", "total"))
                .replace(",", ".")
                .replace("…", "")
                .strip()
            )
            try:
                val = float(raw)
                if val > 0:
                    return val
            except ValueError:
                pass
        return self._peso_actual()

    def _nuevo_listo(self) -> bool:
        for var in (
            self.var_cliente,
            self.var_color,
            self.var_dn,
            self.var_corte,
            self.var_operario,
        ):
            if not var.get().strip() or var.get().strip() in ("—", "…"):
                return False
        nro = self.var_nro.get().strip()
        if not nro.isdigit() or int(nro) < 1:
            return False
        if not normalizar_lote(self.var_lote.get(), anio=self.fecha.year):
            return False
        total = self._peso_desde_fila_o_vivo()
        return total is not None and total >= 0.3

    def _registro_completo(self, reg: RegistroPesaje) -> bool:
        campos = (
            reg.cliente,
            reg.lote,
            reg.color,
            reg.denier,
            reg.corte,
            reg.operario,
            str(reg.nro_fardo),
        )
        if any(not str(c).strip() or str(c).strip() in ("—", "…") for c in campos):
            return False
        return float(reg.peso_total or 0) > 0 and float(reg.peso_neto or 0) >= 0

    def _datos_desde_registro(self, reg: RegistroPesaje) -> DatosEtiqueta:
        return DatosEtiqueta(
            color=reg.color,
            cliente=reg.cliente,
            lote=reg.lote,
            dn=reg.denier,
            corte=reg.corte,
            nro_fardo=str(reg.nro_fardo),
            fecha=format_fecha_editable(self.fecha),
            peso_bruto=float(reg.peso_bruto),
            peso_neto=float(reg.peso_neto),
            operario=reg.operario,
            peso_total=float(reg.peso_total),
            tara_carreta=float(reg.tara_carreta),
            tara_fardo=float(reg.tara_fardo),
            hora=self._hora(reg.fecha_hora),
            fecha_hora_registro=reg.fecha_hora,
        )

    def _auto_guardar_si_listo(self) -> None:
        if self._guardando or not self._modo_nuevo:
            return
        if getattr(self, "excel", None) is not None and self.excel._edit is not None:
            return
        data = self.reader.snapshot()
        if self._espera_bascula_cero:
            w = data["weight"]
            if w is not None and float(w) >= 0.3:
                return
            self._espera_bascula_cero = False
        if not self._nuevo_listo():
            return
        lote = normalizar_lote(self.var_lote.get(), anio=self.fecha.year)
        nro = self.var_nro.get().strip()
        if lote and self.db.existe_fardo_en_lote(lote, nro):
            self.var_msg.set(f"El fardo {nro} ya existe en el lote {lote}")
            return
        if data.get("connected") and data.get("status") != "ST":
            return
        self.guardar()

    def _persistir_edicion(self) -> None:
        if self._editando_id is None:
            return
        datos = self._recoger(permitir_peso_guardado=True)
        if datos is None:
            return
        anterior = self.db.obtener(self._editando_id)
        try:
            self.db.actualizar(self._editando_id, datos)
            self.db.auditar_guardado_pesaje(
                pesaje_id=self._editando_id,
                accion="editar",
                datos=datos,
                anterior=anterior,
            )
        except ValueError as exc:
            self.var_msg.set(str(exc))
            return
        self.var_msg.set(f"Fardo {datos.nro_fardo} actualizado")
        actualizado = self.db.obtener(self._editando_id)
        if actualizado is not None:
            self._regs = [
                actualizado if r.id == self._editando_id else r for r in self._regs
            ]
        iid = str(self._editando_id)
        if self.tree.exists(iid):
            self.excel.mark_saved(iid)
        if hasattr(self, "row_actions"):
            self.row_actions.sync()

    def guardar(self) -> bool:
        """Registra la fila nueva (peso en vivo) o confirma edición."""
        if self._guardando:
            return False
        self._guardando = True
        try:
            return self._guardar_impl()
        finally:
            self._guardando = False

    def _guardar_impl(self) -> bool:
        if hasattr(self, "excel"):
            self.excel.commit()
        if self._target_id is None and self._selected_id is not None:
            reg = next((r for r in self._regs if r.id == self._selected_id), None)
            if reg and not reg.activo:
                return False

        creando = self._modo_nuevo or self._target_id is None
        datos = self._recoger(permitir_peso_guardado=not creando)
        if datos is None:
            return False

        target_id = self._target_id
        anterior = self.db.obtener(target_id) if target_id is not None else None
        try:
            if target_id is not None:
                self.db.actualizar(target_id, datos)
                self.db.auditar_guardado_pesaje(
                    pesaje_id=target_id,
                    accion="editar",
                    datos=datos,
                    anterior=anterior,
                )
                self.var_msg.set(f"Fardo {datos.nro_fardo} guardado (ID {target_id})")
                self._editando_id = None
            else:
                pid = self.db.insertar(
                    datos, fecha_hora=datos.fecha_hora_registro or None
                )
                self.db.auditar_guardado_pesaje(
                    pesaje_id=pid, accion="crear", datos=datos
                )
                self.var_msg.set(f"Fardo {datos.nro_fardo} registrado")
                self._force_siguiente = True
                self._espera_bascula_cero = True
        except ValueError as exc:
            messagebox.showwarning("Hoja", str(exc))
            return False

        self.reanudar_medicion()
        self.refrescar()
        if self.on_saved:
            self.on_saved()
        return True

    def _abrir_preview(self, iid: str) -> None:
        try:
            rid = int(iid)
        except ValueError:
            return
        reg = next((r for r in self._regs if r.id == rid), None)
        if reg is None or not reg.activo:
            messagebox.showinfo("Imprimir", "Seleccione un fardo guardado.")
            return
        if not self._registro_completo(reg):
            messagebox.showinfo(
                "Imprimir",
                "Faltan datos en este fardo. Complete Cliente, Lote, Color, "
                "Dn, Corte, Operario y pesos antes de imprimir.",
            )
            return
        datos = self._datos_desde_registro(reg)
        PrintPreviewDialog(
            self,
            datos,
            on_printed=lambda: self.var_msg.set(
                f"Fardo {datos.nro_fardo} enviado a impresora"
            ),
        )

    def imprimir(self) -> None:
        """Atajo: vista previa del fardo seleccionado (si está completo)."""
        sel = self.tree.selection()
        if not sel or sel[0] == "__nuevo__":
            return
        self._abrir_preview(sel[0])
