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

        self.var_nro = tk.StringVar()
        self.var_cliente = tk.StringVar()
        self.var_lote = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_dn = tk.StringVar()
        self.var_corte = tk.StringVar()
        self.var_operario = tk.StringVar()
        self.var_ir_fecha = tk.StringVar(value=format_fecha_editable(date.today()))

        self._regs: list[RegistroPesaje] = []
        self._frozen = False
        self._foto: Optional[dict] = None
        self._printing = False
        self._target_id: Optional[int] = None  # último registro a actualizar

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
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        # Ctrl+V en la hoja (fuera de Entry) abre carga masiva
        self.bind_all("<Control-v>", self._on_ctrl_v, add="+")
        self.bind_all("<Control-V>", self._on_ctrl_v, add="+")

    def _build_barra_compacta(self, parent: tk.Widget) -> None:
        bar = tk.Frame(parent, bg=Theme.PANEL, padx=10, pady=8)
        bar.pack(fill=tk.X, padx=12, pady=(0, 2))

        # Peso + estado
        left = tk.Frame(bar, bg=Theme.PANEL)
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

        # Campos compactos: maestros (combo) + lote/op/fardo
        mid = tk.Frame(bar, bg=Theme.PANEL)
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
        ent = text_entry(col, self.var_operario, 8)
        ent.configure(font=("Segoe UI", 10))
        ent.pack()

        # Botones a la derecha
        right = tk.Frame(bar, bg=Theme.PANEL)
        right.pack(side=tk.RIGHT, padx=(8, 0))

        self.btn_foto = tk.Button(
            right,
            text="CAPTURAR",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=Theme.ACCENT,
            activeforeground="#ffffff",
            activebackground="#3d7cef",
            relief=tk.FLAT,
            padx=16,
            pady=10,
            cursor="hand2",
            command=self.tomar_foto,
        )
        self.btn_foto.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_print = tk.Button(
            right,
            text="IMPRIMIR",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=16,
            pady=10,
            cursor="hand2",
            command=self.imprimir,
        )
        self.btn_print.pack(side=tk.LEFT)

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
        self._regs = self.db.por_fecha(self.fecha)
        self.tree.delete(*self.tree.get_children())

        bruto_t = 0.0
        neto_t = 0.0
        for r in self._regs:
            bruto_t += r.peso_bruto
            neto_t += r.peso_neto
            hora = self._hora(r.fecha_hora)
            tags = ("ultimo",) if r is self._regs[-1] else ()
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
                    "✓" if r.estado_sincronizado else "…",
                ),
                tags=tags,
            )

        self.var_totales.set(
            f"Total del día · {len(self._regs)} fardos · "
            f"Bruto {bruto_t:,.1f} Kgrs · Neto {neto_t:,.1f} Kgrs"
        )
        self._cargar_ultimo_en_barra()
        self._show_detail(self._regs[-1] if self._regs else None)
        if self._regs:
            self.tree.selection_set(str(self._regs[-1].id))
            self.tree.see(str(self._regs[-1].id))

    def _cargar_ultimo_en_barra(self) -> None:
        """Precarga la barra con el último registro del día (o vacío)."""
        if not self._regs:
            self._target_id = None
            self.var_nro.set(str(self.db.siguiente_nro_fardo(dia=self.fecha)))
            self.var_hint.set(
                "Sin registros este día · complete campos y CAPTURAR → IMPRIMIR (crea el primero)"
            )
            self.refrescar_maestros()
            return

        ultimo = self._regs[-1]
        self._target_id = ultimo.id
        self.var_nro.set(str(ultimo.nro_fardo))
        self.var_cliente.set(ultimo.cliente)
        self.var_lote.set(ultimo.lote)
        self.var_color.set(ultimo.color)
        self.var_dn.set(ultimo.denier)
        self.var_corte.set(ultimo.corte)
        self.var_operario.set(ultimo.operario)
        self.var_hint.set(
            f"Actualiza fardo {ultimo.nro_fardo} (último del día) · "
            f"CAPTURAR peso → IMPRIMIR etiqueta y guardar"
        )
        self.refrescar_maestros()

    def _hora(self, fecha_hora: str) -> str:
        try:
            dt = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%I:%M %p").lstrip("0").lower()
        except ValueError:
            return fecha_hora[11:16] if len(fecha_hora) >= 16 else ""

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        rid = int(sel[0])
        reg = next((r for r in self._regs if r.id == rid), None)
        self._show_detail(reg)

    def _show_detail(self, reg: Optional[RegistroPesaje]) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        if reg is None:
            self.detail.insert(tk.END, "Sin fardos este día. Use la barra de abajo para el primero.")
        else:
            sync = "Sincronizado" if reg.estado_sincronizado else "Pendiente de sync"
            self.detail.insert(
                tk.END,
                (
                    f"ID {reg.id}  |  Fardo {reg.nro_fardo}  |  {reg.fecha_hora}  |  {sync}\n"
                    f"Cliente: {reg.cliente}   Lote: {reg.lote}   Color: {reg.color}\n"
                    f"Dn: {reg.denier}   Corte: {reg.corte} mm   Operario: {reg.operario}\n"
                    f"P.Total {reg.peso_total:.2f}  −  Tara Carreta {reg.tara_carreta:.2f}  "
                    f"= P.Bruto {reg.peso_bruto:.2f}  ·  P.Neto {reg.peso_neto:.2f}"
                ),
            )
        self.detail.configure(state=tk.DISABLED)

    # --- Pesaje compacto -------------------------------------------------

    def _taras_desde_ultimo(self) -> tuple[float, float]:
        if self._regs:
            u = self._regs[-1]
            tc = u.tara_carreta if u.tara_carreta > 0 else TARA_CARRETA_KG
            tf = u.tara_fardo if u.tara_fardo > 0 else TARA_FARDO_KG
            return tc, tf
        return TARA_CARRETA_KG, TARA_FARDO_KG

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
        self.refrescar()
        top = self.winfo_toplevel()
        if hasattr(top, "_on_maestros_change"):
            top._on_maestros_change()
        if self.on_saved:
            self.on_saved()

    def _recoger(self) -> Optional[DatosEtiqueta]:
        total = self._peso_actual()
        if total is None:
            self.var_msg.set("Sin peso. Pulse CAPTURAR primero.")
            return None
        if not self._frozen:
            # Auto-captura al imprimir si aún no hay foto
            if not self.tomar_foto():
                return None
            total = self._peso_actual()
            if total is None:
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
                self.var_msg.set(f"Complete: {nombre}")
                return None

        nro_txt = self.var_nro.get().strip()
        if not nro_txt.isdigit() or int(nro_txt) < 1:
            self.var_msg.set("Nº Fardo inválido")
            return None

        bruto, neto, tc, tf = self._calcular_pesos(float(total))
        now = datetime.now()
        fecha_hora = datetime.combine(self.fecha, now.time()).strftime("%Y-%m-%d %H:%M:%S")

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
            hora=now.strftime("%I:%M %p").lstrip("0").lower(),
            fecha_hora_registro=fecha_hora,
        )

    def imprimir(self) -> None:
        if self._printing:
            return
        datos = self._recoger()
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
        self.reanudar_medicion()
        self.refrescar()
        if self.on_saved:
            self.on_saved()

    def _print_done(self) -> None:
        self._printing = False
        self.btn_print.config(state=tk.NORMAL)
