"""Ventana principal: pesaje, hoja, resumen, reportes, etiqueta y maestros."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from config import PORT, SYNC_INTERVAL_S, SYNC_TOKEN, UI_REFRESH_MS
from db import PesajeDatabase
from serial_reader import SerialWeightReader
from sync import SyncWorker
from ui.auditoria_cambios_view import AuditoriaCambiosView
from ui.auditoria_view import AuditoriaSyncView
from ui.etiqueta_editor_view import EtiquetaEditorView
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
        self.after(200, self._refresh_device_light)
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

        # Derecha: sync + luz de conexión Precix (clic = detalle)
        right = tk.Frame(header, bg=Theme.BG)
        right.pack(side=tk.RIGHT)

        self.var_device = tk.StringVar(value=f"●  {PORT} OFF")
        self.btn_device = tk.Button(
            right,
            textvariable=self.var_device,
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#9ca3af",
            activeforeground="#ffffff",
            activebackground="#6b7280",
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._show_device_info,
        )
        self.btn_device.pack(side=tk.RIGHT)

        self.lbl_sync = tk.Label(
            right,
            text="",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        )
        self.lbl_sync.pack(side=tk.RIGHT, padx=(0, 12))

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
        self.tab_auditoria = ttk.Notebook(self.nb)
        self.view_auditoria = AuditoriaSyncView(
            self.tab_auditoria, self.db, sync=self.sync
        )
        self.view_aud_cambios = AuditoriaCambiosView(self.tab_auditoria, self.db)
        self.tab_auditoria.add(self.view_auditoria, text="  Sync nube  ")
        self.tab_auditoria.add(self.view_aud_cambios, text="  Cambios de hoja  ")
        self.view_etiqueta = EtiquetaEditorView(self.nb)
        self.view_maestros = MaestrosView(
            self.nb,
            self.db.catalogo,
            on_change=self._on_maestros_change,
        )

        self.nb.add(self.view_pesaje, text="  Pesaje  ")
        self.nb.add(self.view_hoja, text="  Hoja de cálculo  ")
        self.nb.add(self.view_mes, text="  Resumen mensual  ")
        self.nb.add(self.view_reportes, text="  Reportes  ")
        self.nb.add(self.tab_auditoria, text="  Auditoría  ")
        self.nb.add(self.view_etiqueta, text="  Etiqueta  ")
        self.nb.add(self.view_maestros, text="  Maestros  ")
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _event=None) -> None:
        try:
            if self.nb.select() == str(self.tab_auditoria):
                self.view_auditoria.refrescar()
                self.view_aud_cambios.refrescar()
        except tk.TclError:
            pass

    def _on_maestros_change(self) -> None:
        self.view_pesaje.refrescar_maestros()
        self.view_hoja.refrescar_maestros()

    def _on_registro_guardado(self) -> None:
        self.view_hoja.refrescar()
        self.view_mes.refrescar()
        self.view_reportes.refrescar()
        self.view_aud_cambios.refrescar()
        self._refresh_sync_badge()

    def _abrir_dia(self, dia: date) -> None:
        self.view_hoja.set_fecha(dia)
        self.nb.select(self.view_hoja)

    def _refresh_device_light(self) -> None:
        """Luz superior derecha: verde si el indicador Precix está conectado."""
        data = self.reader.snapshot()
        if data["connected"]:
            peso = (
                f"{data['weight']:.1f} {data['unit']}"
                if data["weight"] is not None
                else "OK"
            )
            self.var_device.set(f"●  Precix ON · {peso}")
            self.btn_device.configure(
                bg=Theme.ST_COLOR,
                activebackground="#27ae60",
                fg="#ffffff",
            )
        else:
            self.var_device.set(f"●  Precix OFF · {PORT}")
            self.btn_device.configure(
                bg=Theme.ERR_COLOR,
                activebackground="#c0392b",
                fg="#ffffff",
            )
        self.after(UI_REFRESH_MS, self._refresh_device_light)

    def _show_device_info(self) -> None:
        """Popup con datos del dispositivo físico Precix-Weight."""
        data = self.reader.snapshot()
        win = tk.Toplevel(self)
        win.title("Dispositivo Precix-Weight")
        win.configure(bg=Theme.PANEL)
        win.transient(self)
        win.resizable(False, False)

        ok = bool(data["connected"])
        color = Theme.ST_COLOR if ok else Theme.ERR_COLOR
        lbl_estado = tk.Label(
            win,
            text="●  CONECTADO" if ok else "●  DESCONECTADO",
            font=("Segoe UI", 14, "bold"),
            fg=color,
            bg=Theme.PANEL,
        )
        lbl_estado.pack(anchor="w", padx=16, pady=(14, 4))

        tk.Label(
            win,
            text="Indicador industrial Precix-Weight (báscula RS-232)",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        info = tk.Text(
            win,
            width=56,
            height=14,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            font=("Consolas", 10),
            relief=tk.FLAT,
            wrap=tk.WORD,
            padx=10,
            pady=10,
        )
        info.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        info.insert("1.0", self.reader.device_info_text())
        info.configure(state=tk.DISABLED)

        btns = tk.Frame(win, bg=Theme.PANEL)
        btns.pack(fill=tk.X, padx=16, pady=(0, 14))

        def _refresh_popup() -> None:
            info.configure(state=tk.NORMAL)
            info.delete("1.0", tk.END)
            info.insert("1.0", self.reader.device_info_text())
            info.configure(state=tk.DISABLED)
            d = self.reader.snapshot()
            connected = bool(d["connected"])
            lbl_estado.config(
                text="●  CONECTADO" if connected else "●  DESCONECTADO",
                fg=Theme.ST_COLOR if connected else Theme.ERR_COLOR,
            )

        tk.Button(
            btns,
            text="Actualizar",
            font=("Segoe UI", 10, "bold"),
            fg="#fff",
            bg=Theme.ACCENT,
            relief=tk.FLAT,
            padx=12,
            pady=6,
            cursor="hand2",
            command=_refresh_popup,
        ).pack(side=tk.LEFT)

        tk.Button(
            btns,
            text="Cerrar",
            font=("Segoe UI", 10, "bold"),
            fg="#fff",
            bg=Theme.MUTED,
            relief=tk.FLAT,
            padx=12,
            pady=6,
            cursor="hand2",
            command=win.destroy,
        ).pack(side=tk.RIGHT)

        win.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - win.winfo_reqwidth() - 24
        y = self.winfo_rooty() + 48
        win.geometry(f"+{max(x, 40)}+{y}")

    def _refresh_sync_badge(self) -> None:
        pend = self.db.contar_pendientes()
        cada = (
            f"cada {max(1, SYNC_INTERVAL_S // 60)} min"
            if SYNC_INTERVAL_S >= 60
            else f"cada {SYNC_INTERVAL_S}s"
        )
        if not SYNC_TOKEN:
            self.lbl_sync.config(
                text=f"Cron {cada} · falta TOKEN · {pend} pend.",
                fg=Theme.US_COLOR,
            )
        elif self.sync.last_error:
            self.lbl_sync.config(
                text=f"Cron {cada} · {pend} pend. · {self.sync.last_error}",
                fg=Theme.US_COLOR,
            )
        else:
            ok = f" · OK {self.sync.last_ok_at}" if self.sync.last_ok_at else ""
            self.lbl_sync.config(
                text=f"Cron {cada} · {pend} pend.{ok}",
                fg=Theme.ST_COLOR if pend == 0 else Theme.MUTED,
            )
        self.after(5000, self._refresh_sync_badge)

    def _on_print_key(self, _event=None):
        if self._en_hoja():
            self.view_hoja.imprimir()
            return "break"
        return None

    def _on_space_key(self, _event=None):
        if self._en_hoja() and self.view_hoja.focus_es_entrada():
            return None
        return None

    def _on_escape_key(self, _event=None):
        if self._en_hoja():
            self.view_hoja.reanudar_medicion()
            return "break"
        return None

    def _en_hoja(self) -> bool:
        try:
            return self.nb.select() == str(self.view_hoja)
        except tk.TclError:
            return False

    def _on_close(self) -> None:
        self.sync.stop()
        self.reader.stop()
        self.destroy()
