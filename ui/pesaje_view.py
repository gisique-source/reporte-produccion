"""Pesaje rápido: captura en vivo, todos los campos, guardado y vista previa de etiqueta."""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox

from config import (
    MODO_FARDO_CONTINUAR,
    MODO_FARDO_REINICIAR,
    PORT,
    TARA_CARRETA_KG,
    TARA_FARDO_KG,
    UI_REFRESH_MS,
)
from db import PesajeDatabase, format_fecha_editable
from models import DatosEtiqueta
from serial_reader import SerialWeightReader
from ui.date_picker import DatePicker
from ui.label_preview import LabelPreviewPanel
from ui.print_preview_dialog import PrintPreviewDialog
from ui.searchable_dropdown import SearchableDropdown
from ui.pesaje_data import (
    asegurar_prefijo_lote,
    copiar_ultimo_registro,
    datos_preview_pesaje,
    lote_prefijo,
    normalizar_lote_campo,
    proponer_nro_fardo,
    recoger_datos_pesaje,
)
from ui.time_picker import TimePicker, snap_hora_15
from ui.widgets import ScrollableFrame, Theme, confirm_modal, field_label, text_entry


class PesajeView(tk.Frame):
    """Página principal para registrar fardos con báscula en tiempo real."""

    def __init__(
        self,
        master: tk.Widget,
        reader: SerialWeightReader,
        db: Optional[PesajeDatabase] = None,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.reader = reader
        self.db = db
        self.on_saved = on_saved
        self.fecha = date.today()
        self._guardando = False
        self._last_status = ""
        self._peso_manual: Optional[float] = None
        self._ultimo_guardado: Optional[DatosEtiqueta] = None
        self._esperar_refresco = False

        self.var_fecha = tk.StringVar(value=format_fecha_editable(self.fecha))
        self.var_nro = tk.StringVar()
        self.var_cliente = tk.StringVar()
        self.var_lote = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_dn = tk.StringVar()
        self.var_corte = tk.StringVar()
        self.var_operario = tk.StringVar()
        self.var_hora = tk.StringVar(value=snap_hora_15(""))
        self.var_tara_carreta = tk.StringVar(value=f"{TARA_CARRETA_KG:.2f}")
        self.var_tara_fardo = tk.StringVar(value=f"{TARA_FARDO_KG:.2f}")
        self.var_total = tk.StringVar(value="---.--")
        self.var_bruto = tk.StringVar(value="---.--")
        self.var_neto = tk.StringVar(value="---.--")
        self.var_msg = tk.StringVar(value="")
        self.var_modo_fardo = tk.StringVar(
            value=self.db.get_modo_fardo() if self.db else MODO_FARDO_CONTINUAR
        )

        self._maestro_vars = (
            self.var_nro,
            self.var_cliente,
            self.var_lote,
            self.var_color,
            self.var_dn,
            self.var_corte,
            self.var_operario,
            self.var_hora,
            self.var_fecha,
            self.var_tara_carreta,
            self.var_tara_fardo,
        )

        self._build()
        for var in self._maestro_vars:
            var.trace_add("write", lambda *_: self._actualizar_preview())
        self.var_tara_carreta.trace_add(
            "write", lambda *_: self._actualizar_indicadores()
        )
        self.var_tara_fardo.trace_add(
            "write", lambda *_: self._actualizar_indicadores()
        )
        self.refrescar()
        self.after(UI_REFRESH_MS, self._refresh)

    def _build(self) -> None:
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill=tk.X, padx=14, pady=(10, 4))
        tk.Label(
            head,
            text="PESAJE RÁPIDO",
            font=("Segoe UI", 16, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        tk.Label(
            head,
            text="Registro e impresión desde esta pantalla",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(14, 0))
        tk.Button(
            head,
            text="↻  Refrescar",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
            activeforeground=Theme.ACCENT,
            activebackground=Theme.TREE_HEAD,
            relief=tk.GROOVE,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._preparar_siguiente,
        ).pack(side=tk.RIGHT)

        body = tk.Frame(self, bg=Theme.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2, minsize=520)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=Theme.BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        foot = tk.Frame(left, bg=Theme.BG)
        foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        scroll = ScrollableFrame(left, bg=Theme.BG)
        scroll.pack(fill=tk.BOTH, expand=True)
        inner = scroll.body

        weight_row = tk.Frame(inner, bg=Theme.BG)
        weight_row.pack(pady=(4, 0))

        self.lbl_weight = tk.Label(
            weight_row,
            text="---.-- kg",
            font=("Consolas", 56, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
        )
        self.lbl_weight.pack(side=tk.LEFT)

        manual_fr = tk.Frame(weight_row, bg=Theme.BG)
        manual_fr.pack(side=tk.LEFT, anchor="n", padx=(10, 0), pady=(8, 0))
        self.btn_peso_manual = tk.Button(
            manual_fr,
            text="✎\nManual",
            font=("Segoe UI", 8, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
            activeforeground=Theme.ACCENT,
            activebackground=Theme.TREE_HEAD,
            relief=tk.GROOVE,
            padx=6,
            pady=4,
            cursor="hand2",
            command=self._abrir_peso_manual,
        )
        self.btn_peso_manual.pack()
        self.lbl_manual = tk.Label(
            manual_fr,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg=Theme.US_COLOR,
            bg=Theme.BG,
        )
        self.lbl_manual.pack(pady=(4, 0))

        status_row = tk.Frame(inner, bg=Theme.BG)
        status_row.pack(pady=(2, 6))
        self.lbl_status = tk.Label(
            status_row,
            text="●  --",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.MUTED,
            bg=Theme.BG,
        )
        self.lbl_status.pack(side=tk.LEFT, padx=(0, 12))
        self.lbl_conn = tk.Label(
            status_row,
            text=f"Puerto {PORT} · Desconectado",
            font=("Segoe UI", 10),
            fg=Theme.ERR_COLOR,
            bg=Theme.BG,
        )
        self.lbl_conn.pack(side=tk.LEFT)

        ind = tk.Frame(inner, bg=Theme.BG)
        ind.pack(pady=(0, 10))
        self._make_indicador(
            ind, "P. TOTAL", self.var_total, Theme.FG, Theme.CARD_TOTAL
        ).pack(side=tk.LEFT, padx=8)
        self._make_indicador(
            ind, "P. BRUTO", self.var_bruto, Theme.ERR_COLOR, Theme.CARD_BRUTO
        ).pack(side=tk.LEFT, padx=8)
        self._make_indicador(
            ind, "P. NETO", self.var_neto, Theme.ST_COLOR, Theme.CARD_NETO
        ).pack(side=tk.LEFT, padx=8)

        form = tk.Frame(inner, bg=Theme.PANEL, padx=14, pady=12)
        form.pack(fill=tk.X, padx=2)

        def _cell(row: int, col: int, label: str, widget: tk.Widget) -> None:
            tk.Label(
                form, text=label, fg=Theme.MUTED, bg=Theme.PANEL, font=("Segoe UI", 9)
            ).grid(row=row * 2, column=col, sticky="w", padx=(0, 8), pady=(0, 2))
            widget.grid(row=row * 2 + 1, column=col, sticky="ew", padx=(0, 10), pady=(0, 6))

        self.ent_nro = text_entry(form, self.var_nro, 6)
        _cell(0, 0, "Nº Fardo", self.ent_nro)

        self.cb_cliente = self._dd_maestro(form, self.var_cliente, "cliente", 16)
        _cell(0, 1, "Cliente", self.cb_cliente)

        self.ent_lote = text_entry(form, self.var_lote, 16)
        self.ent_lote.bind("<FocusIn>", self._on_lote_focus_in)
        self.ent_lote.bind("<FocusOut>", self._on_lote_focus_out)
        _cell(0, 2, "Lote", self.ent_lote)

        self.cb_color = self._dd_maestro(form, self.var_color, "color", 12)
        _cell(1, 0, "Color", self.cb_color)

        self.cb_dn = self._dd_maestro(form, self.var_dn, "dn", 6)
        _cell(1, 1, "Dn", self.cb_dn)

        self.cb_corte = self._dd_maestro(form, self.var_corte, "corte", 6)
        _cell(1, 2, "Corte (mm)", self.cb_corte)

        self.cb_operario = self._dd_maestro(form, self.var_operario, "operario", 12)
        _cell(2, 0, "Operario", self.cb_operario)

        hora_fr = tk.Frame(form, bg=Theme.PANEL)
        self.tp_hora = TimePicker(
            hora_fr,
            textvariable=self.var_hora,
            bg=Theme.PANEL,
            width=5,
            on_change=lambda _v: self._actualizar_preview(),
        )
        self.tp_hora.pack(anchor="w")
        _cell(2, 1, "Hora", hora_fr)

        fecha_fr = tk.Frame(form, bg=Theme.PANEL)
        self.dp_fecha = DatePicker(
            fecha_fr,
            textvariable=self.var_fecha,
            bg=Theme.PANEL,
            on_change=self._on_fecha_change,
        )
        self.dp_fecha.pack(anchor="w")
        _cell(2, 2, "Fecha", fecha_fr)

        taras = tk.Frame(form, bg=Theme.PANEL)
        field_label(taras, "Tara Carreta (kg)").pack(anchor="w")
        text_entry(taras, self.var_tara_carreta, 10).pack(anchor="w")
        _cell(3, 0, "", taras)

        taraf = tk.Frame(form, bg=Theme.PANEL)
        field_label(taraf, "Tara Fardo (kg)").pack(anchor="w")
        text_entry(taraf, self.var_tara_fardo, 10).pack(anchor="w")
        _cell(3, 1, "", taraf)

        for c in range(3):
            form.columnconfigure(c, weight=1)

        modo_row = tk.Frame(inner, bg=Theme.BG)
        modo_row.pack(fill=tk.X, pady=(8, 8))
        tk.Label(
            modo_row,
            text="Correlativo:",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        tk.Button(
            modo_row,
            text="Contar de 1",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._set_modo_fardo(MODO_FARDO_REINICIAR),
        ).pack(side=tk.LEFT, padx=(8, 4))
        tk.Button(
            modo_row,
            text="Continuar del día anterior",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._set_modo_fardo(MODO_FARDO_CONTINUAR),
        ).pack(side=tk.LEFT)

        tk.Label(
            foot,
            textvariable=self.var_msg,
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_guardar = tk.Button(
            foot,
            text="GUARDAR",
            font=("Segoe UI", 14, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=28,
            pady=10,
            cursor="hand2",
            command=self.guardar,
        )
        self.btn_guardar.pack(side=tk.RIGHT)

        self.btn_imprimir = tk.Button(
            foot,
            text="IMPRIMIR",
            font=("Segoe UI", 14, "bold"),
            fg="#ffffff",
            bg=Theme.ACCENT,
            activeforeground="#ffffff",
            activebackground="#1e40af",
            relief=tk.FLAT,
            padx=28,
            pady=10,
            cursor="hand2",
            command=self.imprimir,
        )

        right = tk.Frame(body, bg=Theme.BG)
        right.grid(row=0, column=1, sticky="nsew")
        self.preview = LabelPreviewPanel(right)
        self.preview.pack(fill=tk.BOTH, expand=True)

    @staticmethod
    def _make_indicador(
        parent: tk.Widget,
        titulo: str,
        variable: tk.StringVar,
        color: str,
        bg: str,
    ) -> tk.Frame:
        box = tk.Frame(parent, bg=bg, padx=16, pady=10)
        tk.Label(
            box, text=titulo, font=("Segoe UI", 9, "bold"), fg=Theme.MUTED, bg=bg
        ).pack()
        tk.Label(
            box,
            textvariable=variable,
            font=("Consolas", 26, "bold"),
            fg=color,
            bg=bg,
        ).pack()
        tk.Label(box, text="kg", font=("Segoe UI", 9), fg=Theme.MUTED, bg=bg).pack()
        return box

    def _dd_maestro(
        self, parent: tk.Widget, var: tk.StringVar, key: str, width: int
    ) -> SearchableDropdown:
        placeholders = {
            "cliente": "Cliente…",
            "color": "Color…",
            "dn": "Dn…",
            "corte": "Corte…",
            "operario": "Operario…",
        }
        dd = SearchableDropdown(
            parent,
            textvariable=var,
            width=width,
            font=("Segoe UI", 10),
            placeholder=placeholders.get(key, ""),
            on_commit=lambda _v: self._actualizar_preview(),
            compact=True,
        )
        return dd

    def _limpiar_maestros(self) -> None:
        """Deja vacíos los campos de maestros (primer fardo del día)."""
        for var in (
            self.var_cliente,
            self.var_color,
            self.var_dn,
            self.var_corte,
            self.var_operario,
        ):
            var.set("")
        self.var_lote.set("")
        for dd in (
            self.cb_cliente,
            self.cb_color,
            self.cb_dn,
            self.cb_corte,
            self.cb_operario,
        ):
            dd.set("")

    def _registros_activos_dia(self, dia: Optional[date] = None) -> list:
        if not self.db:
            return []
        target = dia or self.fecha
        return [r for r in self.db.por_fecha(target) if r.activo]

    def _lote_prefijo(self) -> str:
        return lote_prefijo(self.fecha.year)

    def _on_fecha_change(self, dia: Optional[date]) -> None:
        if dia is None:
            return
        self.fecha = dia
        activos = self._registros_activos_dia(dia)
        if activos:
            copiar_ultimo_registro(
                activos[-1],
                anio=self.fecha.year,
                var_cliente=self.var_cliente,
                var_lote=self.var_lote,
                var_color=self.var_color,
                var_dn=self.var_dn,
                var_corte=self.var_corte,
                var_operario=self.var_operario,
                var_tara_carreta=self.var_tara_carreta,
                var_tara_fardo=self.var_tara_fardo,
            )
        else:
            self._limpiar_maestros()
        self._proponer_nro()
        self.refrescar_maestros()
        self._actualizar_preview()

    def al_mostrar(self) -> None:
        """Sincroniza maestros; no cambia el Nº si aún no se pulsó Refrescar."""
        self.refrescar_maestros()
        if not self._esperar_refresco:
            self._proponer_nro()

    def _on_lote_focus_in(self, _event=None) -> None:
        asegurar_prefijo_lote(self.var_lote, self.fecha.year)
        try:
            self.ent_lote.icursor(tk.END)
        except tk.TclError:
            pass

    def _on_lote_focus_out(self, _event=None) -> None:
        normalizar_lote_campo(self.var_lote, self.fecha.year)

    def _set_modo_fardo(self, modo: str) -> None:
        if not self.db or modo not in (MODO_FARDO_CONTINUAR, MODO_FARDO_REINICIAR):
            return
        self.var_modo_fardo.set(modo)
        self.db.set_modo_fardo(modo)
        self._proponer_nro()

    def _proponer_nro(self) -> None:
        if not self.db:
            return
        nro = proponer_nro_fardo(
            self.db, self.var_modo_fardo.get(), self.fecha
        )
        self.var_nro.set(str(nro))

    def refrescar_maestros(self) -> None:
        if not self.db:
            return
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
            else:
                dd.set("")

    def refrescar(self) -> None:
        if not self.db:
            return
        self.fecha = date.today()
        self.var_fecha.set(format_fecha_editable(self.fecha))
        self.var_modo_fardo.set(self.db.get_modo_fardo())
        self.tp_hora.set(snap_hora_15(""), notify=False)
        self.var_hora.set(snap_hora_15(""))
        activos = self._registros_activos_dia(self.fecha)
        if activos:
            copiar_ultimo_registro(
                activos[-1],
                anio=self.fecha.year,
                var_cliente=self.var_cliente,
                var_lote=self.var_lote,
                var_color=self.var_color,
                var_dn=self.var_dn,
                var_corte=self.var_corte,
                var_operario=self.var_operario,
                var_tara_carreta=self.var_tara_carreta,
                var_tara_fardo=self.var_tara_fardo,
            )
        else:
            self._limpiar_maestros()
        self._proponer_nro()
        self.refrescar_maestros()
        self.var_msg.set("")
        self._actualizar_preview()

    def _taras(self) -> tuple[float, float]:
        raw_c = self.var_tara_carreta.get().strip().replace(",", ".")
        raw_f = self.var_tara_fardo.get().strip().replace(",", ".")
        try:
            tc = float(raw_c) if raw_c else TARA_CARRETA_KG
        except ValueError:
            tc = TARA_CARRETA_KG
        try:
            tf = float(raw_f) if raw_f else TARA_FARDO_KG
        except ValueError:
            tf = TARA_FARDO_KG
        return tc, tf

    def _calcular_pesos(self, total: float) -> tuple[float, float, float, float]:
        tc, tf = self._taras()
        bruto = max(total - tc, 0.0)
        neto = max(total - tc - tf, 0.0)
        return bruto, neto, tc, tf

    def _peso_bascula(self) -> Optional[float]:
        data = self.reader.snapshot()
        if data["weight"] is None:
            return None
        total = float(data["weight"])
        return total if total > 0 else None

    def _peso_actual(self) -> Optional[float]:
        if self._peso_manual is not None and self._peso_manual > 0:
            return self._peso_manual
        return self._peso_bascula()

    def _limpiar_peso_manual(self) -> None:
        self._peso_manual = None
        self.lbl_manual.config(text="")
        self.btn_peso_manual.config(bg=Theme.PANEL, fg=Theme.FG)
        self._actualizar_display_peso()
        self._actualizar_indicadores()

    def _aplicar_peso_manual(self, valor: float) -> None:
        self._peso_manual = valor
        self.lbl_manual.config(text="MANUAL")
        self.btn_peso_manual.config(bg=Theme.US_COLOR, fg="#ffffff")
        self._actualizar_display_peso()
        self._actualizar_indicadores()
        self.var_msg.set(f"Peso manual: {valor:.2f} kg")

    def _actualizar_display_peso(self) -> None:
        if self._peso_manual is not None and self._peso_manual > 0:
            self.lbl_weight.config(
                text=f"{self._peso_manual:.2f} kg",
                fg=Theme.US_COLOR,
            )
            return
        data = self.reader.snapshot()
        if data["weight"] is not None:
            total = float(data["weight"])
            self.lbl_weight.config(text=f"{total:.2f} {data['unit']}", fg=Theme.FG)
        else:
            self.lbl_weight.config(text="---.-- kg", fg=Theme.FG)

    def _abrir_peso_manual(self) -> None:
        top = self.winfo_toplevel()
        win = tk.Toplevel(top)
        win.title("Peso manual")
        win.configure(bg=Theme.PANEL)
        win.transient(top)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(
            win,
            text="Ingrese el peso total (kg)",
            font=("Segoe UI", 11, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
        ).pack(padx=20, pady=(16, 4), anchor="w")
        tk.Label(
            win,
            text="Use cuando la báscula no esté conectada o no capture el peso.",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            wraplength=280,
            justify=tk.LEFT,
        ).pack(padx=20, pady=(0, 10), anchor="w")

        inicial = ""
        if self._peso_manual is not None and self._peso_manual > 0:
            inicial = f"{self._peso_manual:.2f}"
        else:
            vivo = self._peso_bascula()
            if vivo is not None:
                inicial = f"{vivo:.2f}"
            elif self.var_total.get() not in ("---.--", ""):
                inicial = self.var_total.get().replace(",", ".")

        var = tk.StringVar(value=inicial)
        ent = text_entry(win, var, 14)
        ent.pack(padx=20, pady=(0, 12))
        ent.focus_set()
        ent.select_range(0, tk.END)

        btns = tk.Frame(win, bg=Theme.PANEL)
        btns.pack(fill=tk.X, padx=20, pady=(0, 16))

        def _ok() -> None:
            raw = var.get().strip().replace(",", ".")
            try:
                val = float(raw)
            except ValueError:
                messagebox.showwarning(
                    "Peso manual", "Ingrese un número válido.", parent=win
                )
                return
            if val <= 0:
                messagebox.showwarning(
                    "Peso manual", "El peso debe ser mayor que cero.", parent=win
                )
                return
            self._aplicar_peso_manual(val)
            win.destroy()

        def _bascula() -> None:
            self._limpiar_peso_manual()
            self.var_msg.set("Peso desde báscula")
            win.destroy()

        tk.Button(
            btns,
            text="Usar báscula",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            bg=Theme.TREE_HEAD,
            fg=Theme.FG,
            padx=10,
            pady=5,
            cursor="hand2",
            command=_bascula,
        ).pack(side=tk.LEFT)
        tk.Button(
            btns,
            text="Aplicar",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            bg=Theme.BTN_BG,
            fg="#ffffff",
            padx=14,
            pady=5,
            cursor="hand2",
            command=_ok,
        ).pack(side=tk.RIGHT)
        ent.bind("<Return>", lambda _e: _ok())
        win.bind("<Escape>", lambda _e: win.destroy())

        win.update_idletasks()
        x = top.winfo_rootx() + (top.winfo_width() - win.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + 120
        win.geometry(f"+{max(x, 40)}+{y}")

    def _actualizar_indicadores(self, _event=None) -> None:
        total = self._peso_actual()
        if total is None:
            self.var_total.set("---.--")
            self.var_bruto.set("---.--")
            self.var_neto.set("---.--")
            self._actualizar_preview()
            return
        bruto, neto, _, _ = self._calcular_pesos(total)
        self.var_total.set(f"{total:.2f}")
        self.var_bruto.set(f"{bruto:.2f}")
        self.var_neto.set(f"{neto:.2f}")
        self._actualizar_preview()

    def _refresh(self) -> None:
        data = self.reader.snapshot()
        if data["connected"]:
            self.lbl_conn.config(text=f"Puerto {PORT} · Conectado", fg=Theme.ST_COLOR)
        else:
            err = data["last_error"]
            hint = f" — {err}" if err else ""
            self.lbl_conn.config(
                text=f"Puerto {PORT} · Reconectando…{hint}", fg=Theme.ERR_COLOR
            )

        self._actualizar_display_peso()
        self._actualizar_indicadores()

        if self._peso_manual is not None:
            self.lbl_status.config(text="●  MANUAL", fg=Theme.US_COLOR)
            self._last_status = "MANUAL"
        else:
            st = data["status"]
            self._last_status = st or ""
            if st == "ST":
                self.lbl_status.config(text="●  ST  ESTABLE", fg=Theme.ST_COLOR)
            elif st == "US":
                self.lbl_status.config(text="●  US  INESTABLE", fg=Theme.US_COLOR)
            else:
                self.lbl_status.config(text="●  --", fg=Theme.MUTED)

        self.after(UI_REFRESH_MS, self._refresh)

    def _sync_maestros_desde_combo(self) -> None:
        for dd, var in (
            (self.cb_cliente, self.var_cliente),
            (self.cb_color, self.var_color),
            (self.cb_dn, self.var_dn),
            (self.cb_corte, self.var_corte),
            (self.cb_operario, self.var_operario),
        ):
            var.set(dd.get())

    def _datos_formulario(
        self, *, exigir_peso: bool = False
    ) -> Optional[DatosEtiqueta]:
        self._sync_maestros_desde_combo()
        tc, tf = self._taras()
        datos, err = recoger_datos_pesaje(
            fecha=self.fecha,
            peso_total=self._peso_actual(),
            tara_carreta=tc,
            tara_fardo=tf,
            var_cliente=self.var_cliente,
            var_lote=self.var_lote,
            var_color=self.var_color,
            var_dn=self.var_dn,
            var_corte=self.var_corte,
            var_operario=self.var_operario,
            var_nro=self.var_nro,
            var_hora=self.var_hora,
            exigir_completo=exigir_peso,
        )
        if err:
            self.var_msg.set(err)
        return datos

    def _datos_preview(self) -> DatosEtiqueta:
        self._sync_maestros_desde_combo()
        tc, tf = self._taras()
        return datos_preview_pesaje(
            fecha=self.fecha,
            peso_total=self._peso_actual(),
            tara_carreta=tc,
            tara_fardo=tf,
            var_cliente=self.var_cliente,
            var_lote=self.var_lote,
            var_color=self.var_color,
            var_dn=self.var_dn,
            var_corte=self.var_corte,
            var_operario=self.var_operario,
            var_nro=self.var_nro,
            var_hora=self.var_hora,
        )

    def _actualizar_preview(self) -> None:
        self.preview.schedule(self._datos_preview())

    def guardar(self) -> bool:
        if self._guardando or not self.db:
            return False
        self._guardando = True
        try:
            return self._guardar_impl()
        finally:
            self._guardando = False

    def _guardar_impl(self) -> bool:
        datos = self._datos_formulario(exigir_peso=True)
        if datos is None:
            return False

        if self.db.existe_fardo_en_lote(datos.lote, datos.nro_fardo):
            self.var_msg.set(
                f"El fardo {datos.nro_fardo} ya existe en el lote {datos.lote}"
            )
            messagebox.showwarning("Pesaje", self.var_msg.get(), parent=self)
            return False

        aviso_peso = ""
        if self._peso_manual is not None:
            aviso_peso = "\n\n📋 Peso ingresado manualmente (no báscula)."
        elif self._last_status == "US":
            aviso_peso = "\n\n⚠ Peso INESTABLE (US). Confirme solo si es correcto."
        elif self._last_status != "ST":
            aviso_peso = "\n\n⚠ La báscula no reporta peso estable (ST)."

        msg = (
            f"Fardo #{datos.nro_fardo}\n"
            f"Cliente: {datos.cliente}\n"
            f"Lote: {datos.lote}  ·  Color: {datos.color}\n"
            f"Dn: {datos.dn}  ·  Corte: {datos.corte} mm\n"
            f"Operario: {datos.operario}  ·  {datos.fecha}  ·  {datos.hora}\n"
            f"P.Total {datos.peso_total:.2f}  →  Bruto {datos.peso_bruto:.2f}  "
            f"·  Neto {datos.peso_neto:.2f} kg"
            f"{aviso_peso}\n\n"
            "¿Guardar este registro?"
        )
        if not confirm_modal(
            self,
            "Confirmar registro",
            msg,
            ok_text="Guardar",
            cancel_text="Cancelar",
        ):
            return False

        try:
            pid = self.db.insertar(datos, fecha_hora=datos.fecha_hora_registro or None)
            self.db.auditar_guardado_pesaje(
                pesaje_id=pid, accion="crear", datos=datos
            )
        except ValueError as exc:
            messagebox.showwarning("Pesaje", str(exc), parent=self)
            return False

        self.var_msg.set(
            f"Fardo {datos.nro_fardo} registrado (ID {pid}). "
            "Use Refrescar para el siguiente."
        )
        self._ultimo_guardado = datos
        self._esperar_refresco = True
        self.btn_imprimir.pack(side=tk.RIGHT, padx=(0, 8), before=self.btn_guardar)
        if self.on_saved:
            self.on_saved()
        return True

    def imprimir(self) -> None:
        datos = self._ultimo_guardado
        if datos is None:
            self.var_msg.set("Guarde el fardo antes de imprimir")
            return
        PrintPreviewDialog(
            self,
            datos,
            on_printed=lambda: self.var_msg.set(
                f"Fardo {datos.nro_fardo} enviado a impresora"
            ),
        )

    def _preparar_siguiente(self) -> None:
        """Restablece el formulario: siguiente Nº, hora actual y peso en vivo."""
        self._limpiar_peso_manual()
        self.tp_hora.set(snap_hora_15(""), notify=False)
        self.var_hora.set(snap_hora_15(""))
        self._proponer_nro()
        self._esperar_refresco = False
        self._actualizar_preview()
        self.var_msg.set("Formulario listo para el siguiente fardo")

    def focus_es_entrada(self) -> bool:
        w = self.focus_get()
        if isinstance(w, (tk.Entry, tk.Text)):
            return True
        return isinstance(getattr(w, "master", None), SearchableDropdown)
