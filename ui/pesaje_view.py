"""Vista de pesaje e impresión de etiqueta."""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from config import (
    PORT,
    TARA_CARRETA_KG,
    TARA_FARDO_KG,
    UI_REFRESH_MS,
    MODO_FARDO_CONTINUAR,
    MODO_FARDO_REINICIAR,
)
from db import (
    PesajeDatabase,
    format_fecha_corta,
    format_fecha_editable,
    parse_fecha_produccion,
)
from models import DatosEtiqueta
from printer import imprimir_etiqueta
from serial_reader import SerialWeightReader
from ui.widgets import (
    Theme,
    ScrollableFrame,
    combo_entry,
    field_label,
    primary_button,
    text_entry,
)


class PesajeView(tk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        reader: SerialWeightReader,
        db: PesajeDatabase,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.reader = reader
        self.db = db
        self.on_saved = on_saved
        self._printing = False
        self._frozen = False
        self._foto: Optional[dict] = None  # peso congelado
        self._toast_job: Optional[str] = None

        self.var_color = tk.StringVar()
        self.var_cliente = tk.StringVar()
        self.var_lote = tk.StringVar()
        self.var_dn = tk.StringVar()
        self.var_corte = tk.StringVar()
        self.var_operario = tk.StringVar()
        self.var_nro_fardo = tk.StringVar(value="1")
        self.var_modo_fardo = tk.StringVar(value=MODO_FARDO_CONTINUAR)
        self.var_fecha = tk.StringVar(value=format_fecha_editable(date.today()))
        self.var_ultimo_hint = tk.StringVar(value="")
        self._fecha_manual = False  # True si el operario editó la fecha
        self.var_tara_carreta = tk.StringVar(value=f"{TARA_CARRETA_KG:.2f}")
        self.var_tara_fardo = tk.StringVar(value=f"{TARA_FARDO_KG:.2f}")
        self.var_total = tk.StringVar(value="---.--")
        self.var_bruto = tk.StringVar(value="---.--")
        self.var_neto = tk.StringVar(value="---.--")
        self.var_verif = tk.StringVar(value="Ingrese datos antes de imprimir")

        self._build()
        self.var_tara_carreta.trace_add("write", lambda *_: self._on_tara_change())
        self.var_tara_fardo.trace_add("write", lambda *_: self._on_tara_change())
        self.refrescar_maestros()
        self.var_modo_fardo.set(self.db.get_modo_fardo())
        self._actualizar_nro_fardo(aplicar_modo=True)
        self._actualizar_indicadores_peso()
        self.after(UI_REFRESH_MS, self._refresh)

    def _build(self) -> None:
        # Barra de acciones FIJA abajo (siempre visible)
        pie = tk.Frame(self, bg=Theme.BG)
        pie.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 10))

        self.lbl_msg = tk.Label(
            pie, text="", font=("Segoe UI", 10), fg=Theme.MUTED, bg=Theme.BG
        )
        self.lbl_msg.pack()

        tk.Label(
            pie,
            text=(
                "ESPACIO = capturar foto  ·  ESC = reanudar  ·  ENTER = imprimir  ·  "
                "Bruto = Total−Tara Carreta  ·  Neto = Total−Tara Carreta−Tara Fardo"
            ),
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack()

        acciones = tk.Frame(pie, bg=Theme.BG)
        acciones.pack(pady=(6, 2))

        self.btn_foto = primary_button(
            acciones,
            "CAPTURAR",
            self.tomar_foto,
            bg=Theme.ACCENT,
            active_bg="#3d7cef",
        )
        self.btn_foto.pack(side=tk.LEFT, padx=(0, 16))

        self.btn_print = primary_button(
            acciones,
            "IMPRIMIR ETIQUETA",
            self.imprimir,
        )
        self.btn_print.pack(side=tk.LEFT)

        # Zona scrolleable (campos accesibles en pantallas chicas)
        scroll = ScrollableFrame(self, bg=Theme.BG)
        scroll.pack(fill=tk.BOTH, expand=True)
        root = scroll.body
        self._scroll = scroll

        tk.Label(
            root,
            text="HOJA DE PRODUCCIÓN — SECCIÓN EXTRUSORA",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(8, 2))

        meta = tk.Frame(root, bg=Theme.BG)
        meta.pack(fill=tk.X, padx=20)

        tk.Label(
            meta,
            text="Nº Fardo:",
            font=("Segoe UI", 11),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        self.ent_nro_fardo = tk.Entry(
            meta,
            textvariable=self.var_nro_fardo,
            font=("Segoe UI", 16, "bold"),
            fg="#fff",
            bg="#222",
            insertbackground="#fff",
            relief=tk.FLAT,
            width=6,
            justify="center",
        )
        self.ent_nro_fardo.pack(side=tk.LEFT, padx=8)

        tk.Label(
            meta,
            text="Fecha producción:",
            font=("Segoe UI", 11),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(16, 0))

        self.ent_fecha = tk.Entry(
            meta,
            textvariable=self.var_fecha,
            font=("Segoe UI", 14, "bold"),
            fg=Theme.FG,
            bg=Theme.INPUT_BG,
            insertbackground=Theme.FG,
            relief=tk.FLAT,
            width=12,
            justify="center",
        )
        self.ent_fecha.pack(side=tk.LEFT, padx=8)
        self.ent_fecha.bind("<KeyRelease>", self._on_fecha_editada)
        self.ent_fecha.bind("<FocusOut>", self._on_fecha_editada)

        tk.Button(
            meta,
            text="Hoy",
            font=("Segoe UI", 10, "bold"),
            fg="#fff",
            bg=Theme.ACCENT,
            relief=tk.FLAT,
            padx=10,
            pady=2,
            cursor="hand2",
            command=self._fecha_hoy,
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Label(
            meta,
            text="(DD/MM/YYYY — editable para registros anteriores)",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        # Modo correlativo
        modo_fr = tk.Frame(root, bg=Theme.BG)
        modo_fr.pack(fill=tk.X, padx=20, pady=(4, 0))

        tk.Label(
            modo_fr,
            text="Correlativo:",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        tk.Radiobutton(
            modo_fr,
            text="Continuar del último (día anterior)",
            variable=self.var_modo_fardo,
            value=MODO_FARDO_CONTINUAR,
            command=self._on_modo_fardo,
            font=("Segoe UI", 10),
            fg=Theme.FG,
            bg=Theme.BG,
            selectcolor=Theme.PANEL,
            activebackground=Theme.BG,
            activeforeground=Theme.FG,
        ).pack(side=tk.LEFT, padx=(8, 4))

        tk.Radiobutton(
            modo_fr,
            text="Reiniciar en 1",
            variable=self.var_modo_fardo,
            value=MODO_FARDO_REINICIAR,
            command=self._on_modo_fardo,
            font=("Segoe UI", 10),
            fg=Theme.FG,
            bg=Theme.BG,
            selectcolor=Theme.PANEL,
            activebackground=Theme.BG,
            activeforeground=Theme.FG,
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(
            modo_fr,
            textvariable=self.var_ultimo_hint,
            font=("Segoe UI", 9),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.lbl_weight = tk.Label(
            root, text="---.-- kg", font=("Consolas", 42, "bold"), fg=Theme.FG, bg=Theme.BG
        )
        self.lbl_weight.pack(pady=(8, 0))

        # Indicadores automáticos: Total / Bruto / Neto
        ind = tk.Frame(root, bg=Theme.BG)
        ind.pack(pady=(4, 2))

        self.lbl_ind_total = self._make_indicador(
            ind, "P. TOTAL", self.var_total, Theme.FG, "#333333"
        )
        self.lbl_ind_bruto = self._make_indicador(
            ind, "P. BRUTO", self.var_bruto, Theme.ERR_COLOR, "#3a1a1a"
        )
        self.lbl_ind_neto = self._make_indicador(
            ind, "P. NETO", self.var_neto, Theme.ST_COLOR, "#1a3a22"
        )
        self.lbl_ind_total.pack(side=tk.LEFT, padx=8)
        self.lbl_ind_bruto.pack(side=tk.LEFT, padx=8)
        self.lbl_ind_neto.pack(side=tk.LEFT, padx=8)

        self.lbl_status = tk.Label(
            root, text="●  --", font=("Segoe UI", 14, "bold"), fg=Theme.MUTED, bg=Theme.BG
        )
        self.lbl_status.pack()

        self.lbl_foto = tk.Label(
            root,
            text="",
            font=("Segoe UI", 12, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        )
        self.lbl_foto.pack()

        self.lbl_conn = tk.Label(
            root, text=f"Puerto {PORT} · Desconectado",
            font=("Segoe UI", 10), fg=Theme.ERR_COLOR, bg=Theme.BG
        )
        self.lbl_conn.pack(pady=(0, 6))

        # Toast efímero (advertencias) — sobre la vista completa
        self.lbl_toast = tk.Label(
            self,
            text="",
            font=("Segoe UI", 12, "bold"),
            fg="#111",
            bg=Theme.US_COLOR,
            padx=16,
            pady=8,
        )

        form = tk.Frame(root, bg=Theme.PANEL, padx=14, pady=12)
        form.pack(fill=tk.X, padx=20, pady=4)

        field_label(form, "Cliente").grid(row=0, column=0, sticky="w")
        field_label(form, "Lote").grid(row=0, column=1, sticky="w", padx=(10, 0))
        field_label(form, "Color").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.cb_cliente = combo_entry(form, self.var_cliente, width=22)
        self.cb_cliente.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        text_entry(form, self.var_lote, 14).grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 8)
        )
        self.cb_color = combo_entry(form, self.var_color, width=14)
        self.cb_color.grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(0, 8))

        field_label(form, "Dn").grid(row=2, column=0, sticky="w")
        field_label(form, "Corte (mm)").grid(row=2, column=1, sticky="w", padx=(10, 0))
        field_label(form, "Operario").grid(row=2, column=2, sticky="w", padx=(10, 0))
        self.cb_dn = combo_entry(form, self.var_dn, width=10)
        self.cb_dn.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.cb_corte = combo_entry(form, self.var_corte, width=10)
        self.cb_corte.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(0, 8))
        text_entry(form, self.var_operario, 14).grid(
            row=3, column=2, sticky="ew", padx=(10, 0), pady=(0, 8)
        )

        field_label(form, "Tara Carreta (kg)").grid(row=4, column=0, sticky="w")
        field_label(form, "Tara Fardo (kg)").grid(row=4, column=1, sticky="w", padx=(10, 0))
        field_label(form, "Bruto / Neto (auto)").grid(row=4, column=2, sticky="w", padx=(10, 0))

        self.ent_tara_carreta = text_entry(form, self.var_tara_carreta, 10)
        self.ent_tara_carreta.grid(row=5, column=0, sticky="ew")
        self.ent_tara_fardo = text_entry(form, self.var_tara_fardo, 10)
        self.ent_tara_fardo.grid(row=5, column=1, sticky="ew", padx=(10, 0))

        # Campos solo lectura: se llenan solos
        auto_fr = tk.Frame(form, bg=Theme.PANEL)
        auto_fr.grid(row=5, column=2, sticky="ew", padx=(10, 0))
        for titulo, var, color in (
            ("Bruto", self.var_bruto, Theme.ERR_COLOR),
            ("Neto", self.var_neto, Theme.ST_COLOR),
        ):
            col = tk.Frame(auto_fr, bg=Theme.INPUT_BG, padx=6, pady=2)
            col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            tk.Label(
                col, text=titulo, font=("Segoe UI", 8, "bold"),
                fg=Theme.MUTED, bg=Theme.INPUT_BG,
            ).pack(anchor="w")
            tk.Label(
                col, textvariable=var, font=("Consolas", 14, "bold"),
                fg=color, bg=Theme.INPUT_BG,
            ).pack(anchor="w")

        self.ent_tara_carreta.bind("<KeyRelease>", self._on_tara_change)
        self.ent_tara_fardo.bind("<KeyRelease>", self._on_tara_change)
        self.ent_tara_carreta.bind("<FocusOut>", self._on_tara_change)
        self.ent_tara_fardo.bind("<FocusOut>", self._on_tara_change)

        for c in range(3):
            form.columnconfigure(c, weight=1)

        self.lbl_verif = tk.Label(
            root, textvariable=self.var_verif, font=("Segoe UI", 11, "bold"),
            fg=Theme.US_COLOR, bg=Theme.BG
        )
        self.lbl_verif.pack(pady=(6, 12))

        # Al enfocar un campo, scrollear para que no quede fuera de vista
        def _scroll_into_view(event) -> None:
            self._scroll.ensure_visible(event.widget)

        for w in (
            self.ent_nro_fardo,
            self.ent_fecha,
            self.cb_cliente,
            self.cb_color,
            self.cb_dn,
            self.cb_corte,
            self.ent_tara_carreta,
            self.ent_tara_fardo,
        ):
            w.bind("<FocusIn>", _scroll_into_view, add="+")
        for child in form.winfo_children():
            if isinstance(child, tk.Entry):
                child.bind("<FocusIn>", _scroll_into_view, add="+")

    @staticmethod
    def _make_indicador(
        parent: tk.Widget,
        titulo: str,
        variable: tk.StringVar,
        color: str,
        bg: str,
    ) -> tk.Frame:
        box = tk.Frame(parent, bg=bg, padx=16, pady=8)
        tk.Label(
            box,
            text=titulo,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.MUTED,
            bg=bg,
        ).pack()
        tk.Label(
            box,
            textvariable=variable,
            font=("Consolas", 28, "bold"),
            fg=color,
            bg=bg,
        ).pack()
        tk.Label(
            box,
            text="kg",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=bg,
        ).pack()
        return box

    def _on_tara_change(self, _event=None) -> None:
        """Recalcula Bruto/Neto al instante al editar taras."""
        self._actualizar_indicadores_peso()

    def _peso_actual_total(self) -> Optional[float]:
        if self._frozen and self._foto is not None:
            return float(self._foto["weight"])
        data = self.reader.snapshot()
        if data["weight"] is None:
            return None
        return float(data["weight"])

    def _actualizar_indicadores_peso(self) -> None:
        """Llena automáticamente P.Total, P.Bruto y P.Neto."""
        total = self._peso_actual_total()
        if total is None:
            self.var_total.set("---.--")
            self.var_bruto.set("---.--")
            self.var_neto.set("---.--")
            return
        bruto, neto, _tc, _tf = self._calcular_pesos(total)
        self.var_total.set(f"{total:.2f}")
        self.var_bruto.set(f"{bruto:.2f}")
        self.var_neto.set(f"{neto:.2f}")

    def refrescar_maestros(self) -> None:
        """Recarga combos desde tablas maestro (solo activos)."""
        cat = self.db.catalogo
        pairs = (
            (self.cb_cliente, self.var_cliente, "cliente"),
            (self.cb_color, self.var_color, "color"),
            (self.cb_dn, self.var_dn, "denier"),
            (self.cb_corte, self.var_corte, "corte"),
        )
        for cb, var, tipo in pairs:
            valores = cat.valores_activos(tipo)  # type: ignore[arg-type]
            actual = var.get()
            cb["values"] = valores
            if actual in valores:
                var.set(actual)
            elif valores:
                var.set(valores[0])
            else:
                var.set("")

    def _fecha_produccion(self) -> Optional[date]:
        return parse_fecha_produccion(self.var_fecha.get())

    def _on_fecha_editada(self, _event=None) -> None:
        self._fecha_manual = True
        dia = self._fecha_produccion()
        if dia is None:
            self.ent_fecha.config(fg=Theme.ERR_COLOR)
            return
        self.ent_fecha.config(fg=Theme.FG)
        self._actualizar_hint()
        # Si está en reiniciar, sugerir correlativo del día elegido
        if self.var_modo_fardo.get() == MODO_FARDO_REINICIAR:
            self._actualizar_nro_fardo(aplicar_modo=True)

    def _fecha_hoy(self) -> None:
        self._fecha_manual = False
        self.var_fecha.set(format_fecha_editable(date.today()))
        self.ent_fecha.config(fg=Theme.FG)
        self._actualizar_hint()
        if self.var_modo_fardo.get() == MODO_FARDO_REINICIAR:
            self._actualizar_nro_fardo(aplicar_modo=True)
        self.lbl_msg.config(text="Fecha = hoy", fg=Theme.MUTED)

    def set_fecha_produccion(self, dia: date) -> None:
        """Fija fecha de producción (p. ej. desde Resumen → Hoja) para registrar ese día."""
        self._fecha_manual = True
        self.var_fecha.set(format_fecha_editable(dia))
        self.ent_fecha.config(fg=Theme.FG)
        self._actualizar_hint()
        self._actualizar_nro_fardo(aplicar_modo=True)
        self.lbl_msg.config(
            text=f"Fecha de producción: {format_fecha_editable(dia)} — listo para registrar",
            fg=Theme.ACCENT,
        )

    def _on_modo_fardo(self) -> None:
        modo = self.var_modo_fardo.get()
        self.db.set_modo_fardo(modo)
        if modo == MODO_FARDO_REINICIAR:
            self.var_nro_fardo.set("1")
            self._actualizar_hint()
            self.lbl_msg.config(
                text="Serie reiniciada: próximo fardo = 1 (editable)",
                fg=Theme.US_COLOR,
            )
        else:
            self._actualizar_nro_fardo(aplicar_modo=True)
            self.lbl_msg.config(
                text="Correlativo continuo desde el último registrado",
                fg=Theme.ST_COLOR,
            )

    def _actualizar_hint(self) -> None:
        dia = self._fecha_produccion() or date.today()
        ultimo = self.db.ultimo_nro_fardo(solo_hoy=False)
        ultimo_dia = self.db.ultimo_nro_fardo(solo_hoy=True, dia=dia)
        etiqueta = "Hoy" if dia == date.today() else format_fecha_corta(dia)
        self.var_ultimo_hint.set(
            f"Último global: {ultimo}  ·  {etiqueta}: {ultimo_dia or '—'}"
        )

    def _actualizar_nro_fardo(self, *, aplicar_modo: bool = False) -> None:
        """
        Actualiza el Nº sugerido.
        aplicar_modo=True: recalcula según radio (continuar / reiniciar).
        Tras imprimir se usa el correlativo del valor impreso + 1.
        """
        self._actualizar_hint()
        if not aplicar_modo:
            return
        dia = self._fecha_produccion() or date.today()
        modo = self.var_modo_fardo.get()
        if modo == MODO_FARDO_REINICIAR:
            n = self.db.ultimo_nro_fardo(solo_hoy=True, dia=dia)
            self.var_nro_fardo.set(str(n + 1 if n > 0 else 1))
        else:
            self.var_nro_fardo.set(
                str(self.db.siguiente_nro_fardo(MODO_FARDO_CONTINUAR, dia=dia))
            )

    def _taras(self) -> tuple[float, float]:
        """Lee taras de UI; si vacías/inválidas usa los valores por defecto de config."""
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
        """
        P.Bruto = P.Total − Tara Carreta
        P.Neto  = P.Total − Tara Carreta − Tara Fardo
        """
        tc, tf = self._taras()
        bruto = max(total - tc, 0.0)
        neto = max(total - tc - tf, 0.0)
        return bruto, neto, tc, tf

    def _mostrar_toast(self, mensaje: str, *, ms: int = 3500) -> None:
        if self._toast_job is not None:
            try:
                self.after_cancel(self._toast_job)
            except Exception:  # noqa: BLE001
                pass
            self._toast_job = None
        self.lbl_toast.config(text=mensaje)
        self.lbl_toast.place(relx=0.5, rely=0.12, anchor="n")
        self.lbl_toast.lift()
        self._toast_job = self.after(ms, self._ocultar_toast)

    def _ocultar_toast(self) -> None:
        self.lbl_toast.place_forget()
        self._toast_job = None

    def tomar_foto(self) -> bool:
        """Congela el peso actual (ST o US). Retorna False si no hay peso."""
        if self._frozen:
            return True

        data = self.reader.snapshot()
        if data["weight"] is None:
            self._mostrar_toast("Sin peso para fotografiar")
            self.lbl_msg.config(text="Sin peso válido para foto.", fg=Theme.ERR_COLOR)
            return False

        total = float(data["weight"])
        status = data["status"] or "--"

        self._foto = {
            "weight": total,
            "unit": data["unit"],
            "status": status,
        }
        self._frozen = True

        self.lbl_weight.config(text=f"{total:.2f} {data['unit']}", fg=Theme.ACCENT)
        self._actualizar_indicadores_peso()
        self.lbl_foto.config(
            text=f"FOTO CONGELADA ({status}) — ESC para reanudar",
            fg=Theme.ACCENT,
        )

        if status == "US":
            self._mostrar_toast("Advertencia: foto tomada en US inestable")
            self.lbl_msg.config(
                text="Advertencia: foto tomada en US inestable",
                fg=Theme.US_COLOR,
            )
        else:
            self.lbl_msg.config(
                text=f"Foto tomada · {total:.2f} kg ({status})",
                fg=Theme.ST_COLOR,
            )
        return True

    def reanudar_medicion(self) -> None:
        """Sale del estado foto y vuelve a medición en vivo."""
        if not self._frozen:
            return
        self._frozen = False
        self._foto = None
        self.lbl_weight.config(fg=Theme.FG)
        self.lbl_foto.config(text="")
        self.lbl_msg.config(text="Medición reanudada", fg=Theme.MUTED)
        self._ocultar_toast()

    def _refresh(self) -> None:
        data = self.reader.snapshot()
        # Solo sincronizar fecha con el calendario si el operario no la editó
        if not self._fecha_manual:
            self.var_fecha.set(format_fecha_editable(date.today()))

        # Conexión siempre en vivo
        if data["connected"]:
            self.lbl_conn.config(text=f"Puerto {PORT} · Conectado", fg=Theme.ST_COLOR)
        else:
            err = data["last_error"]
            hint = f" — {err}" if err else ""
            self.lbl_conn.config(
                text=f"Puerto {PORT} · Reconectando…{hint}", fg=Theme.ERR_COLOR
            )

        if self._frozen and self._foto is not None:
            total = float(self._foto["weight"])
            self.lbl_weight.config(
                text=f"{total:.2f} {self._foto['unit']}", fg=Theme.ACCENT
            )
            self._actualizar_indicadores_peso()

            st = self._foto["status"]
            if st == "ST":
                self.lbl_status.config(text="●  ST  ESTABLE (foto)", fg=Theme.ST_COLOR)
            elif st == "US":
                self.lbl_status.config(text="●  US  INESTABLE (foto)", fg=Theme.US_COLOR)
            else:
                self.lbl_status.config(text="●  --  (foto)", fg=Theme.MUTED)
        else:
            if data["weight"] is not None:
                total = float(data["weight"])
                self.lbl_weight.config(text=f"{total:.2f} {data['unit']}", fg=Theme.FG)
            else:
                self.lbl_weight.config(text="---.-- kg", fg=Theme.FG)
            self._actualizar_indicadores_peso()

            st = data["status"]
            if st == "ST":
                self.lbl_status.config(text="●  ST  ESTABLE", fg=Theme.ST_COLOR)
            elif st == "US":
                self.lbl_status.config(text="●  US  INESTABLE", fg=Theme.US_COLOR)
            else:
                self.lbl_status.config(text="●  --", fg=Theme.MUTED)

        self._actualizar_verificacion()
        self.after(UI_REFRESH_MS, self._refresh)

    def _peso_para_imprimir(self) -> Optional[tuple[float, float, float, float, float]]:
        """(total, bruto, neto, tara_c, tara_f)."""
        if self._frozen and self._foto is not None:
            total = float(self._foto["weight"])
        else:
            data = self.reader.snapshot()
            if data["weight"] is None:
                return None
            total = float(data["weight"])

        bruto, neto, tc, tf = self._calcular_pesos(total)
        return total, bruto, neto, tc, tf

    def _actualizar_verificacion(self) -> None:
        faltan = []
        for nombre, var in (
            ("Cliente", self.var_cliente),
            ("Lote", self.var_lote),
            ("Color", self.var_color),
            ("Dn", self.var_dn),
            ("Corte", self.var_corte),
            ("Operario", self.var_operario),
        ):
            if not var.get().strip():
                faltan.append(nombre)
        if faltan:
            self.var_verif.set(
                "Ingrese Operario antes de Imprimir"
                if faltan == ["Operario"]
                else f"Falta: {', '.join(faltan)}"
            )
            self.lbl_verif.config(fg=Theme.ERR_COLOR)
        else:
            self.var_verif.set("ok Listo para imprimir")
            self.lbl_verif.config(fg=Theme.ST_COLOR)

    def focus_es_entrada(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox))

    def _recoger(self) -> Optional[DatosEtiqueta]:
        pesos = self._peso_para_imprimir()
        if pesos is None:
            self.lbl_msg.config(text="Sin peso válido. Tome una foto (ESPACIO).", fg=Theme.ERR_COLOR)
            return None

        for nombre, var in (
            ("Cliente", self.var_cliente),
            ("Lote", self.var_lote),
            ("Color", self.var_color),
            ("Dn", self.var_dn),
            ("Corte", self.var_corte),
            ("Operario", self.var_operario),
        ):
            if not var.get().strip():
                self.lbl_msg.config(text=f"Complete: {nombre}", fg=Theme.ERR_COLOR)
                return None

        total, bruto, neto, tc, tf = pesos
        now = datetime.now()

        dia = self._fecha_produccion()
        if dia is None:
            self.lbl_msg.config(
                text="Fecha inválida. Use DD/MM/YYYY (ej. 03/08/2026).",
                fg=Theme.ERR_COLOR,
            )
            self.ent_fecha.config(fg=Theme.ERR_COLOR)
            return None

        nro_txt = self.var_nro_fardo.get().strip()
        if not nro_txt.isdigit() or int(nro_txt) < 1:
            self.lbl_msg.config(
                text="Nº Fardo inválido. Indique un entero ≥ 1.",
                fg=Theme.ERR_COLOR,
            )
            return None
        nro = str(int(nro_txt))
        self.var_nro_fardo.set(nro)

        # Conservar hora actual; la fecha de producción puede ser anterior
        fecha_hora = datetime.combine(dia, now.time()).strftime("%Y-%m-%d %H:%M:%S")

        datos = DatosEtiqueta(
            color=self.var_color.get().strip(),
            cliente=self.var_cliente.get().strip(),
            lote=self.var_lote.get().strip(),
            dn=self.var_dn.get().strip(),
            corte=self.var_corte.get().strip(),
            nro_fardo=nro,
            fecha=format_fecha_editable(dia),
            peso_bruto=bruto,
            peso_neto=neto,
            operario=self.var_operario.get().strip(),
            peso_total=total,
            tara_carreta=tc,
            tara_fardo=tf,
            hora=now.strftime("%I:%M %p").lstrip("0").lower(),
            fecha_hora_registro=fecha_hora,
        )
        return datos

    def imprimir(self) -> None:
        if self._printing:
            return
        datos = self._recoger()
        if datos is None:
            return

        self._printing = True
        self.btn_print.config(state=tk.DISABLED)

        def _worker() -> None:
            try:
                imprimir_etiqueta(datos)
                fh = datos.fecha_hora_registro or None
                self.db.insertar(datos, fecha_hora=fh)
                self.after(0, self._on_print_ok, datos)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda: messagebox.showerror("Error", msg))
                self.after(
                    0,
                    lambda: self.lbl_msg.config(text="Error al imprimir.", fg=Theme.ERR_COLOR),
                )
            finally:
                self.after(0, self._print_done)

        threading.Thread(target=_worker, name="PrintWorker", daemon=True).start()

    def _on_print_ok(self, datos: DatosEtiqueta) -> None:
        self.lbl_msg.config(
            text=(
                f"Registrado · {datos.fecha} · Fardo {datos.nro_fardo} · "
                f"Bruto {datos.peso_bruto:.2f} / Neto {datos.peso_neto:.2f} kg"
            ),
            fg=Theme.ST_COLOR,
        )
        self._actualizar_nro_fardo()
        # Tras imprimir: correlativo = impreso + 1
        try:
            self.var_nro_fardo.set(str(int(datos.nro_fardo) + 1))
        except ValueError:
            self._actualizar_nro_fardo(aplicar_modo=True)
        self.reanudar_medicion()
        if self.on_saved:
            self.on_saved()

    def _print_done(self) -> None:
        self._printing = False
        self.btn_print.config(state=tk.NORMAL)
