"""Pestaña Exportación — reporte mensual a Excel con gráficos."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import tkinter as tk
from tkinter import ttk

from db import PesajeDatabase, nombre_mes
from export_mensual import exportar_mensual_excel, nombre_archivo_mensual, resumen_exportacion
from ui.widgets import Theme, secondary_button


class ExportacionView(tk.Frame):
    def __init__(self, master: tk.Widget, db: PesajeDatabase) -> None:
        super().__init__(master, bg=Theme.BG)
        self.db = db
        today = date.today()
        self.year = today.year
        self.month = today.month

        self.var_mes = tk.StringVar()
        self.var_kpi_fardos = tk.StringVar(value="—")
        self.var_kpi_bruto = tk.StringVar(value="—")
        self.var_kpi_neto = tk.StringVar(value="—")
        self.var_kpi_dias = tk.StringVar(value="—")
        self.var_archivo = tk.StringVar()
        self.var_msg = tk.StringVar(value="")

        self._build()
        self.refrescar()

    def _build(self) -> None:
        header = tk.Frame(self, bg=Theme.PANEL, padx=16, pady=14)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="EXPORTACIÓN MENSUAL",
            font=("Segoe UI", 16, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Excel con resumen, gráficos y hojas Dia 01–31 (formato planta)",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT, padx=(16, 0))

        nav = tk.Frame(header, bg=Theme.PANEL)
        nav.pack(side=tk.RIGHT)
        tk.Button(
            nav,
            text="◀",
            command=self._mes_ant,
            width=3,
            bg=Theme.TREE_HEAD,
            fg=Theme.FG,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)
        tk.Label(
            nav,
            textvariable=self.var_mes,
            font=("Segoe UI", 13, "bold"),
            fg=Theme.FG,
            bg=Theme.TREE_HEAD,
            width=16,
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT)
        tk.Button(
            nav,
            text="▶",
            command=self._mes_sig,
            width=3,
            bg=Theme.TREE_HEAD,
            fg=Theme.FG,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)

        body = tk.Frame(self, bg=Theme.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        kpis = tk.Frame(body, bg=Theme.BG)
        kpis.pack(fill=tk.X, pady=(0, 12))
        for i in range(4):
            kpis.columnconfigure(i, weight=1)
        self._kpi_card(kpis, 0, "Fardos", self.var_kpi_fardos, Theme.ACCENT)
        self._kpi_card(kpis, 1, "P. Bruto", self.var_kpi_bruto, Theme.US_COLOR)
        self._kpi_card(kpis, 2, "P. Neto", self.var_kpi_neto, Theme.ST_COLOR)
        self._kpi_card(kpis, 3, "Días prod.", self.var_kpi_dias, "#a78bfa")

        panel = tk.Frame(
            body,
            bg=Theme.PANEL,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=16,
            pady=16,
        )
        panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            panel,
            text="Contenido del archivo Excel",
            font=("Segoe UI", 12, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        items = (
            "Hoja «Resumen»: totales del mes, tabla diaria y gráficos de producción.",
            "Hojas «Dia 01» … «Dia 31»: detalle de fardos (columnas como la plantilla Extrusora).",
            "Compatible con el formato de referencia ETIQUETA EXTRUSORA (importación en Hoja).",
        )
        for txt in items:
            tk.Label(
                panel,
                text=f"· {txt}",
                font=("Segoe UI", 10),
                fg=Theme.MUTED,
                bg=Theme.PANEL,
                anchor="w",
                justify=tk.LEFT,
            ).pack(fill=tk.X, pady=2)

        preview = tk.Frame(panel, bg=Theme.BG)
        preview.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        style = ttk.Style()
        style.configure(
            "Exp.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=24,
        )
        style.configure(
            "Exp.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 9, "bold"),
        )

        cols = ("dia", "fecha", "fardos", "bruto", "neto")
        self.tree = ttk.Treeview(
            preview, columns=cols, show="headings", style="Exp.Treeview", height=12
        )
        for cid, txt, w in (
            ("dia", "Día", 50),
            ("fecha", "Fecha", 90),
            ("fardos", "Fardos", 60),
            ("bruto", "Bruto kg", 90),
            ("neto", "Neto kg", 90),
        ):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor="center")
        self.tree.column("bruto", anchor="e")
        self.tree.column("neto", anchor="e")
        self.tree.tag_configure("prod", foreground=Theme.ST_COLOR)
        self.tree.tag_configure("vacio", foreground=Theme.MUTED)

        sy = ttk.Scrollbar(preview, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        actions = tk.Frame(body, bg=Theme.BG)
        actions.pack(fill=tk.X, pady=(12, 0))

        tk.Label(
            actions,
            textvariable=self.var_archivo,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            actions,
            text="EXPORTAR EXCEL",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=24,
            pady=10,
            cursor="hand2",
            command=self._exportar,
        ).pack(side=tk.RIGHT)
        secondary_button(actions, "Elegir carpeta…", self._elegir_ruta).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        tk.Label(
            self,
            textvariable=self.var_msg,
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(0, 10))

        self._destino: Path | None = None

    def _kpi_card(
        self,
        parent: tk.Widget,
        col: int,
        titulo: str,
        valor: tk.StringVar,
        color: str,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=Theme.TREE_HEAD,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=4)
        tk.Label(
            card, text=titulo, font=("Segoe UI", 8, "bold"), fg=Theme.MUTED, bg=Theme.TREE_HEAD
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=valor,
            font=("Segoe UI", 18, "bold"),
            fg=color,
            bg=Theme.TREE_HEAD,
        ).pack(anchor="w", pady=(4, 0))

    def _mes_ant(self) -> None:
        if self.month == 1:
            self.month, self.year = 12, self.year - 1
        else:
            self.month -= 1
        self.refrescar()

    def _mes_sig(self) -> None:
        if self.month == 12:
            self.month, self.year = 1, self.year + 1
        else:
            self.month += 1
        self.refrescar()

    def refrescar(self) -> None:
        self.var_mes.set(f"{nombre_mes(self.month)} {self.year}")
        info = resumen_exportacion(self.db, self.year, self.month)
        self.var_kpi_fardos.set(f"{info['fardos']:,}")
        self.var_kpi_bruto.set(f"{info['bruto']:,.1f} kg")
        self.var_kpi_neto.set(f"{info['neto']:,.1f} kg")
        self.var_kpi_dias.set(str(info["dias_prod"]))

        self.tree.delete(*self.tree.get_children())
        for r in info["filas"]:
            tag = "prod" if r.cantidad > 0 else "vacio"
            self.tree.insert(
                "",
                tk.END,
                values=(
                    f"{r.dia:02d}",
                    r.fecha,
                    r.cantidad,
                    f"{r.peso_bruto:,.1f}",
                    f"{r.peso_neto:,.1f}",
                ),
                tags=(tag,),
            )

        sugerido = nombre_archivo_mensual(self.year, self.month)
        if self._destino is None:
            self.var_archivo.set(f"Archivo sugerido: {sugerido}")
        else:
            self.var_archivo.set(str(self._destino / sugerido))

    def _elegir_ruta(self) -> None:
        carpeta = filedialog.askdirectory(
            title="Carpeta de destino para exportación",
            parent=self.winfo_toplevel(),
        )
        if not carpeta:
            return
        self._destino = Path(carpeta)
        self.refrescar()
        self.var_msg.set(f"Carpeta: {carpeta}")

    def _exportar(self) -> None:
        sugerido = nombre_archivo_mensual(self.year, self.month)
        if self._destino is not None:
            inicial = str(self._destino / sugerido)
        else:
            inicial = sugerido

        path = filedialog.asksaveasfilename(
            title="Exportar reporte mensual",
            parent=self.winfo_toplevel(),
            defaultextension=".xlsx",
            initialfile=Path(inicial).name,
            initialdir=str(Path(inicial).parent) if Path(inicial).parent.exists() else None,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")],
        )
        if not path:
            return

        info = resumen_exportacion(self.db, self.year, self.month)
        if info["fardos"] == 0:
            if not messagebox.askyesno(
                "Exportación",
                f"No hay fardos registrados en {nombre_mes(self.month)} {self.year}.\n\n"
                "¿Exportar igualmente el libro (hojas vacías)?",
                parent=self,
            ):
                return

        try:
            out = exportar_mensual_excel(self.db, self.year, self.month, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Exportación", str(exc), parent=self)
            return

        self.var_msg.set(f"Exportado: {out}")
        messagebox.showinfo(
            "Exportación",
            f"Reporte mensual guardado en:\n{out}\n\n"
            "Incluye hoja Resumen con gráficos y hojas Dia 01–31.",
            parent=self,
        )
