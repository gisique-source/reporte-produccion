"""Monitor de báscula: peso en vivo y cálculo de fardo (sin registrar ni imprimir)."""

from __future__ import annotations

import tkinter as tk

from config import PORT, TARA_CARRETA_KG, TARA_FARDO_KG, UI_REFRESH_MS
from serial_reader import SerialWeightReader
from ui.widgets import Theme, field_label, text_entry


class PesajeView(tk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        reader: SerialWeightReader,
        db=None,
        on_saved=None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.reader = reader
        self.db = db
        self.on_saved = on_saved

        self.var_tara_carreta = tk.StringVar(value=f"{TARA_CARRETA_KG:.2f}")
        self.var_tara_fardo = tk.StringVar(value=f"{TARA_FARDO_KG:.2f}")
        self.var_total = tk.StringVar(value="---.--")
        self.var_bruto = tk.StringVar(value="---.--")
        self.var_neto = tk.StringVar(value="---.--")

        self._build()
        self.var_tara_carreta.trace_add("write", lambda *_: self._actualizar_indicadores())
        self.var_tara_fardo.trace_add("write", lambda *_: self._actualizar_indicadores())
        self._actualizar_indicadores()
        self.after(UI_REFRESH_MS, self._refresh)

    def _build(self) -> None:
        tk.Label(
            self,
            text="MONITOR DE BÁSCULA",
            font=("Segoe UI", 16, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(18, 2))
        tk.Label(
            self,
            text="Solo observación · el registro e impresión se hacen en Hoja de cálculo",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(0, 12))

        self.lbl_weight = tk.Label(
            self,
            text="---.-- kg",
            font=("Consolas", 64, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
        )
        self.lbl_weight.pack(pady=(8, 4))

        ind = tk.Frame(self, bg=Theme.BG)
        ind.pack(pady=(8, 8))
        self._make_indicador(ind, "P. TOTAL", self.var_total, Theme.FG, Theme.CARD_TOTAL).pack(
            side=tk.LEFT, padx=10
        )
        self._make_indicador(
            ind, "P. BRUTO", self.var_bruto, Theme.ERR_COLOR, Theme.CARD_BRUTO
        ).pack(side=tk.LEFT, padx=10)
        self._make_indicador(
            ind, "P. NETO", self.var_neto, Theme.ST_COLOR, Theme.CARD_NETO
        ).pack(side=tk.LEFT, padx=10)

        self.lbl_status = tk.Label(
            self, text="●  --", font=("Segoe UI", 16, "bold"), fg=Theme.MUTED, bg=Theme.BG
        )
        self.lbl_status.pack(pady=(6, 0))

        self.lbl_conn = tk.Label(
            self,
            text=f"Puerto {PORT} · Desconectado",
            font=("Segoe UI", 11),
            fg=Theme.ERR_COLOR,
            bg=Theme.BG,
        )
        self.lbl_conn.pack(pady=(4, 16))

        taras = tk.Frame(self, bg=Theme.PANEL, padx=20, pady=14)
        taras.pack(padx=24)

        field_label(taras, "Tara Carreta (kg)").grid(row=0, column=0, sticky="w")
        field_label(taras, "Tara Fardo (kg)").grid(
            row=0, column=1, sticky="w", padx=(16, 0)
        )
        self.ent_tara_carreta = text_entry(taras, self.var_tara_carreta, 12)
        self.ent_tara_carreta.grid(row=1, column=0, sticky="ew")
        self.ent_tara_fardo = text_entry(taras, self.var_tara_fardo, 12)
        self.ent_tara_fardo.grid(row=1, column=1, sticky="ew", padx=(16, 0))
        taras.columnconfigure(0, weight=1)
        taras.columnconfigure(1, weight=1)

        tk.Label(
            self,
            text="P.Bruto = P.Total − Tara Carreta    ·    P.Neto = P.Total − Tara Carreta − Tara Fardo",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(14, 4))
        tk.Label(
            self,
            text="El registro e impresión de etiquetas se hacen en Hoja de cálculo.",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(0, 12))

    @staticmethod
    def _make_indicador(
        parent: tk.Widget,
        titulo: str,
        variable: tk.StringVar,
        color: str,
        bg: str,
    ) -> tk.Frame:
        box = tk.Frame(parent, bg=bg, padx=20, pady=12)
        tk.Label(
            box, text=titulo, font=("Segoe UI", 10, "bold"), fg=Theme.MUTED, bg=bg
        ).pack()
        tk.Label(
            box,
            textvariable=variable,
            font=("Consolas", 32, "bold"),
            fg=color,
            bg=bg,
        ).pack()
        tk.Label(box, text="kg", font=("Segoe UI", 9), fg=Theme.MUTED, bg=bg).pack()
        return box

    def refrescar_maestros(self) -> None:
        return

    def refrescar(self) -> None:
        return

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

    def _calcular_pesos(self, total: float) -> tuple[float, float]:
        tc, tf = self._taras()
        bruto = max(total - tc, 0.0)
        neto = max(total - tc - tf, 0.0)
        return bruto, neto

    def _actualizar_indicadores(self, _event=None) -> None:
        data = self.reader.snapshot()
        if data["weight"] is None:
            self.var_total.set("---.--")
            self.var_bruto.set("---.--")
            self.var_neto.set("---.--")
            return
        total = float(data["weight"])
        bruto, neto = self._calcular_pesos(total)
        self.var_total.set(f"{total:.2f}")
        self.var_bruto.set(f"{bruto:.2f}")
        self.var_neto.set(f"{neto:.2f}")

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

        if data["weight"] is not None:
            total = float(data["weight"])
            self.lbl_weight.config(text=f"{total:.2f} {data['unit']}", fg=Theme.FG)
        else:
            self.lbl_weight.config(text="---.-- kg", fg=Theme.FG)
        self._actualizar_indicadores()

        st = data["status"]
        if st == "ST":
            self.lbl_status.config(text="●  ST  ESTABLE", fg=Theme.ST_COLOR)
        elif st == "US":
            self.lbl_status.config(text="●  US  INESTABLE", fg=Theme.US_COLOR)
        else:
            self.lbl_status.config(text="●  --", fg=Theme.MUTED)

        self.after(UI_REFRESH_MS, self._refresh)

    def focus_es_entrada(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, tk.Text))
