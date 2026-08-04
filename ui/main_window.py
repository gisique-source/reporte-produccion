"""Ventana principal: pesaje, hoja, resumen, reportes y maestros."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from config import PORT, SYNC_ENABLED
from db import PesajeDatabase
from serial_reader import SerialWeightReader
from sync import SyncWorker
from ui.hoja_dia_view import HojaDiaView
from ui.maestros_view import MaestrosView
from ui.pesaje_view import PesajeView
from ui.reportes_view import ReportesView
from ui.resumen_mes_view import ResumenMesView
from ui.widgets import Theme


class PrecixApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Precix-Weight — Gexim Extrusora")
        self.configure(bg=Theme.BG)
        self.geometry("1180x820")
        self.minsize(1000, 720)

        self.db = PesajeDatabase()
        self.reader = SerialWeightReader(PORT)
        self.sync = SyncWorker(self.db)

        self._build()
        self.bind_all("<Return>", self._on_print_key)
        self.bind_all("<space>", self._on_space_key)
        self.bind_all("<Key-space>", self._on_space_key)
        self.bind_all("<Escape>", self._on_escape_key)
        self.bind_all("<KeyPress-Escape>", self._on_escape_key)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.reader.start()
        self.sync.start()
        self.after(5000, self._refresh_sync_badge)

    def _build(self) -> None:
        header = tk.Frame(self, bg=Theme.BG)
        header.pack(fill=tk.X, padx=12, pady=(10, 0))

        tk.Label(
            header,
            text="GEXIM S.A.C.  ·  PRECIX-WEIGHT",
            font=("Segoe UI", 16, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        self.lbl_sync = tk.Label(
            header,
            text="",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        )
        self.lbl_sync.pack(side=tk.RIGHT)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=Theme.BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=Theme.PANEL,
            foreground=Theme.FG,
            padding=[12, 8],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", Theme.ACCENT)],
            foreground=[("selected", "#fff")],
        )

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.view_pesaje = PesajeView(
            self.nb, self.reader, self.db, on_saved=self._on_registro_guardado
        )
        self.view_hoja = HojaDiaView(
            self.nb,
            self.db,
            self.reader,
            on_saved=self._on_registro_guardado,
        )
        self.view_mes = ResumenMesView(
            self.nb, self.db, on_open_day=self._abrir_dia
        )
        self.view_reportes = ReportesView(self.nb, self.db)
        self.view_maestros = MaestrosView(
            self.nb,
            self.db.catalogo,
            on_change=self._on_maestros_change,
        )

        self.nb.add(self.view_pesaje, text="  Pesaje / Imprimir  ")
        self.nb.add(self.view_hoja, text="  Hoja  ")
        self.nb.add(self.view_mes, text="  Resumen mensual  ")
        self.nb.add(self.view_reportes, text="  Reportes  ")
        self.nb.add(self.view_maestros, text="  Maestros  ")

    def _on_maestros_change(self) -> None:
        self.view_pesaje.refrescar_maestros()
        self.view_hoja.refrescar_maestros()

    def _on_registro_guardado(self) -> None:
        self.view_hoja.refrescar()
        self.view_mes.refrescar()
        self.view_reportes.refrescar()
        self._refresh_sync_badge()

    def _abrir_dia(self, dia: date) -> None:
        self.view_hoja.set_fecha(dia)
        self.nb.select(self.view_hoja)

    def _refresh_sync_badge(self) -> None:
        pend = self.db.contar_pendientes()
        if not SYNC_ENABLED:
            self.lbl_sync.config(
                text=f"Sync OFF · {pend} pendientes locales",
                fg=Theme.MUTED,
            )
        elif self.sync.last_error:
            self.lbl_sync.config(
                text=f"Sync: {pend} pend. · {self.sync.last_error}",
                fg=Theme.US_COLOR,
            )
        else:
            self.lbl_sync.config(
                text=f"Sync OK · {pend} pendientes",
                fg=Theme.ST_COLOR if pend == 0 else Theme.MUTED,
            )
        self.after(5000, self._refresh_sync_badge)

    def _on_print_key(self, _event=None):
        if self._en_pesaje():
            self.view_pesaje.imprimir()
            return "break"
        if self._en_hoja():
            self.view_hoja.imprimir()
            return "break"
        return None

    def _on_space_key(self, _event=None):
        if self._en_pesaje():
            if self.view_pesaje.focus_es_entrada():
                return None
            self.view_pesaje.tomar_foto()
            return "break"
        if self._en_hoja():
            if self.view_hoja.focus_es_entrada():
                return None
            self.view_hoja.tomar_foto()
            return "break"
        return None

    def _on_escape_key(self, _event=None):
        if self._en_pesaje():
            self.view_pesaje.reanudar_medicion()
            return "break"
        if self._en_hoja():
            self.view_hoja.reanudar_medicion()
            return "break"
        return None

    def _en_pesaje(self) -> bool:
        try:
            return self.nb.select() == str(self.view_pesaje)
        except tk.TclError:
            return False

    def _en_hoja(self) -> bool:
        try:
            return self.nb.select() == str(self.view_hoja)
        except tk.TclError:
            return False

    def _on_close(self) -> None:
        self.sync.stop()
        self.reader.stop()
        self.destroy()
