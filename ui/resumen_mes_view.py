"""Dashboard ejecutivo — resumen mensual de producción (KPIs + gráficos)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from db import PesajeDatabase, nombre_mes
from models import ResumenDia
from ui.widgets import Theme

# Paleta corporativa del dashboard (alineada al tema oscuro de la app)
_BG = Theme.BG
_PANEL = "#1e2430"
_CARD = "#252d3d"
_BORDER = "#323c50"
_ACCENT = "#3b82f6"
_ACCENT2 = "#22c55e"
_WARN = "#f59e0b"
_MUTED = "#94a3b8"
_FG = "#f1f5f9"
_GRID = "#334155"


class ResumenMesView(tk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        on_open_day: Optional[Callable[[date], None]] = None,
    ) -> None:
        super().__init__(master, bg=_BG)
        self.db = db
        self.on_open_day = on_open_day
        today = date.today()
        self.year = today.year
        self.month = today.month

        self.var_mes = tk.StringVar()
        self.var_kpi_bruto = tk.StringVar(value="—")
        self.var_kpi_neto = tk.StringVar(value="—")
        self.var_kpi_fardos = tk.StringVar(value="—")
        self.var_kpi_dias = tk.StringVar(value="—")
        self.var_delta_bruto = tk.StringVar(value="")
        self.var_delta_neto = tk.StringVar(value="")
        self.var_delta_fardos = tk.StringVar(value="")
        self.var_delta_dias = tk.StringVar(value="")
        self.var_hint = tk.StringVar(
            value="Doble clic en un día de la tabla para abrir la Hoja de ese día"
        )

        self._rows: list[ResumenDia] = []
        self._fig_canvas = None
        self._build()
        self.refrescar()

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=_PANEL, padx=16, pady=12)
        header.pack(fill=tk.X)

        left_h = tk.Frame(header, bg=_PANEL)
        left_h.pack(side=tk.LEFT)
        tk.Label(
            left_h,
            text="GEXIM S.A.C.",
            font=("Segoe UI", 10, "bold"),
            fg=_ACCENT,
            bg=_PANEL,
        ).pack(anchor="w")
        tk.Label(
            left_h,
            text="Dashboard ejecutivo · Extrusora",
            font=("Segoe UI", 16, "bold"),
            fg=_FG,
            bg=_PANEL,
        ).pack(anchor="w")

        nav = tk.Frame(header, bg=_PANEL)
        nav.pack(side=tk.RIGHT)
        tk.Label(nav, text="Periodo", font=("Segoe UI", 9), fg=_MUTED, bg=_PANEL).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        tk.Button(
            nav, text="◀", command=self._mes_ant, width=3,
            bg=_CARD, fg=_FG, relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)
        tk.Label(
            nav,
            textvariable=self.var_mes,
            font=("Segoe UI", 13, "bold"),
            fg=_FG,
            bg=_CARD,
            width=16,
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT)
        tk.Button(
            nav, text="▶", command=self._mes_sig, width=3,
            bg=_CARD, fg=_FG, relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)

        # KPI cards
        kpis = tk.Frame(self, bg=_BG)
        kpis.pack(fill=tk.X, padx=12, pady=(12, 6))
        for i in range(4):
            kpis.columnconfigure(i, weight=1)

        self._card(
            kpis, 0, "PESO BRUTO", self.var_kpi_bruto, self.var_delta_bruto, _WARN
        )
        self._card(
            kpis, 1, "PESO NETO", self.var_kpi_neto, self.var_delta_neto, _ACCENT2
        )
        self._card(
            kpis, 2, "FARDOS", self.var_kpi_fardos, self.var_delta_fardos, _ACCENT
        )
        self._card(
            kpis, 3, "DÍAS CON PRODUCCIÓN", self.var_kpi_dias, self.var_delta_dias, "#a78bfa"
        )

        # Body: chart + table
        body = tk.Frame(self, bg=_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Chart panel
        chart_panel = tk.Frame(body, bg=_PANEL, highlightbackground=_BORDER, highlightthickness=1)
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(
            chart_panel,
            text="Producción diaria (kg neto)",
            font=("Segoe UI", 11, "bold"),
            fg=_FG,
            bg=_PANEL,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 0))
        tk.Label(
            chart_panel,
            text="Barras = neto · línea = bruto",
            font=("Segoe UI", 8),
            fg=_MUTED,
            bg=_PANEL,
            anchor="w",
        ).pack(fill=tk.X, padx=12)

        self.chart_host = tk.Frame(chart_panel, bg=_PANEL)
        self.chart_host.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Table panel
        table_panel = tk.Frame(body, bg=_PANEL, highlightbackground=_BORDER, highlightthickness=1)
        table_panel.grid(row=0, column=1, sticky="nsew")
        tk.Label(
            table_panel,
            text="Detalle por día",
            font=("Segoe UI", 11, "bold"),
            fg=_FG,
            bg=_PANEL,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 4))

        wrap = tk.Frame(table_panel, bg=_PANEL)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dash.Treeview",
            background=_CARD,
            foreground=_FG,
            fieldbackground=_CARD,
            rowheight=26,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.configure(
            "Dash.Treeview.Heading",
            background=_PANEL,
            foreground=_MUTED,
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
        )
        style.map(
            "Dash.Treeview",
            background=[("selected", _ACCENT)],
            foreground=[("selected", "#fff")],
        )

        cols = ("dia", "fecha", "fardos", "bruto", "neto")
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Dash.Treeview"
        )
        self.tree.heading("dia", text="Día")
        self.tree.heading("fecha", text="Fecha")
        self.tree.heading("fardos", text="Fardos")
        self.tree.heading("bruto", text="Bruto")
        self.tree.heading("neto", text="Neto")
        self.tree.column("dia", width=45, anchor="center")
        self.tree.column("fecha", width=80, anchor="center")
        self.tree.column("fardos", width=55, anchor="center")
        self.tree.column("bruto", width=85, anchor="e")
        self.tree.column("neto", width=85, anchor="e")
        self.tree.tag_configure("prod", foreground=_ACCENT2)
        self.tree.tag_configure("vacio", foreground=_MUTED)
        self.tree.bind("<Double-1>", self._on_double)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        # Footer
        foot = tk.Frame(self, bg=_PANEL)
        foot.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(
            foot,
            textvariable=self.var_hint,
            font=("Segoe UI", 9),
            fg=_MUTED,
            bg=_PANEL,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=8)

    def _card(
        self,
        parent: tk.Widget,
        col: int,
        titulo: str,
        valor: tk.StringVar,
        delta: tk.StringVar,
        accent: str,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=_CARD,
            highlightbackground=_BORDER,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=4)
        tk.Label(
            card, text=titulo, font=("Segoe UI", 8, "bold"), fg=_MUTED, bg=_CARD
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=valor,
            font=("Segoe UI", 20, "bold"),
            fg=accent,
            bg=_CARD,
        ).pack(anchor="w", pady=(4, 0))
        lbl = tk.Label(
            card, textvariable=delta, font=("Segoe UI", 9), fg=_MUTED, bg=_CARD
        )
        lbl.pack(anchor="w")
        # guardar ref para colorear delta
        if not hasattr(self, "_delta_labels"):
            self._delta_labels = {}
        self._delta_labels[id(delta)] = lbl

    def _mes_ant(self) -> None:
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.refrescar()

    def _mes_sig(self) -> None:
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.refrescar()

    def _prev_month(self) -> tuple[int, int]:
        if self.month == 1:
            return self.year - 1, 12
        return self.year, self.month - 1

    @staticmethod
    def _delta_txt(actual: float, anterior: float) -> tuple[str, str]:
        if anterior <= 0 and actual <= 0:
            return "vs mes ant. · sin data", _MUTED
        if anterior <= 0:
            return "vs mes ant. · nuevo", _ACCENT2
        pct = ((actual - anterior) / anterior) * 100.0
        signo = "+" if pct >= 0 else ""
        color = _ACCENT2 if pct >= 0 else Theme.ERR_COLOR
        return f"vs mes ant. · {signo}{pct:.1f}%", color

    def refrescar(self) -> None:
        self.var_mes.set(f"{nombre_mes(self.month)} {self.year}")
        self._rows = self.db.resumen_mes(self.year, self.month)

        py, pm = self._prev_month()
        prev = self.db.resumen_mes(py, pm)

        tb = sum(r.peso_bruto for r in self._rows)
        tn = sum(r.peso_neto for r in self._rows)
        tf = sum(r.cantidad for r in self._rows)
        td = sum(1 for r in self._rows if r.cantidad > 0)

        pb = sum(r.peso_bruto for r in prev)
        pn = sum(r.peso_neto for r in prev)
        pf = sum(r.cantidad for r in prev)
        pd = sum(1 for r in prev if r.cantidad > 0)

        self.var_kpi_bruto.set(f"{tb:,.1f} kg")
        self.var_kpi_neto.set(f"{tn:,.1f} kg")
        self.var_kpi_fardos.set(f"{tf:,}")
        self.var_kpi_dias.set(f"{td}")

        for var, act, ant in (
            (self.var_delta_bruto, tb, pb),
            (self.var_delta_neto, tn, pn),
            (self.var_delta_fardos, float(tf), float(pf)),
            (self.var_delta_dias, float(td), float(pd)),
        ):
            txt, color = self._delta_txt(act, ant)
            var.set(txt)
            lbl = self._delta_labels.get(id(var))
            if lbl is not None:
                lbl.config(fg=color)

        self._fill_table()
        self._draw_chart()

    def _fill_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for r in self._rows:
            tag = "prod" if r.cantidad > 0 else "vacio"
            self.tree.insert(
                "",
                tk.END,
                iid=f"{self.year}-{self.month:02d}-{r.dia:02d}",
                values=(
                    f"{r.dia:02d}",
                    r.fecha,
                    r.cantidad,
                    f"{r.peso_bruto:,.1f}",
                    f"{r.peso_neto:,.1f}",
                ),
                tags=(tag,),
            )

    def _draw_chart(self) -> None:
        for w in self.chart_host.winfo_children():
            w.destroy()
        self._fig_canvas = None

        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            import matplotlib

            matplotlib.use("Agg")
        except ImportError:
            tk.Label(
                self.chart_host,
                text="Instale matplotlib para ver gráficos\n(pip install matplotlib)",
                fg=_MUTED,
                bg=_PANEL,
                font=("Segoe UI", 11),
            ).pack(expand=True)
            return

        dias = [r.dia for r in self._rows]
        netos = [r.peso_neto for r in self._rows]
        brutos = [r.peso_bruto for r in self._rows]

        fig = Figure(figsize=(7.2, 3.6), dpi=100)
        fig.patch.set_facecolor(_PANEL)
        ax = fig.add_subplot(111)
        ax.set_facecolor(_CARD)

        ax.bar(dias, netos, color=_ACCENT2, alpha=0.85, width=0.7, label="Neto")
        ax.plot(
            dias,
            brutos,
            color=_WARN,
            linewidth=2.0,
            marker="o",
            markersize=3.5,
            label="Bruto",
        )

        ax.set_xlabel("Día del mes", color=_MUTED, fontsize=8)
        ax.set_ylabel("kg", color=_MUTED, fontsize=8)
        ax.tick_params(colors=_MUTED, labelsize=7)
        ax.set_xlim(0.5, max(dias) + 0.5 if dias else 31.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(_GRID)
        ax.spines["left"].set_color(_GRID)
        ax.grid(axis="y", color=_GRID, linestyle="--", linewidth=0.6, alpha=0.7)
        ax.legend(
            facecolor=_CARD,
            edgecolor=_BORDER,
            labelcolor=_FG,
            fontsize=8,
            loc="upper right",
        )
        fig.tight_layout(pad=1.2)

        canvas = FigureCanvasTkAgg(fig, master=self.chart_host)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._fig_canvas = canvas

    def _on_double(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel or not self.on_open_day:
            return
        item = sel[0]
        y, m, d = (int(x) for x in item.split("-"))
        self.on_open_day(date(y, m, d))
