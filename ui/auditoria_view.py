"""Auditoría de sincronización — historial de subidas a la API nube."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from config import SYNC_API_URL, SYNC_INTERVAL_S, SYNC_PLANTA, SYNC_TOKEN
from db import PesajeDatabase, format_fecha_editable, parse_fecha_produccion
from models import RegistroAuditoriaSync
from ui.widgets import Theme, secondary_button, text_entry

if TYPE_CHECKING:
    from sync import SyncWorker


class AuditoriaSyncView(tk.Frame):
    COLS = (
        ("enviado", "Enviado", 140),
        ("estado", "Estado", 70),
        ("http", "HTTP", 50),
        ("fardo", "Fardo", 55),
        ("id_local", "ID local", 65),
        ("id_remoto", "ID remoto", 220),
        ("lote", "Lote", 100),
        ("cliente", "Cliente", 140),
        ("color", "Color", 100),
        ("bruto", "Bruto", 70),
        ("neto", "Neto", 70),
        ("planta", "Planta", 120),
        ("dup", "Dup.", 45),
        ("msg", "Detalle", 160),
    )

    def __init__(
        self,
        master: tk.Widget,
        db: PesajeDatabase,
        sync: Optional["SyncWorker"] = None,
    ) -> None:
        super().__init__(master, bg=Theme.BG)
        self.db = db
        self.sync = sync
        self._subiendo = False
        today = date.today()
        self.var_desde = tk.StringVar(value=format_fecha_editable(today - timedelta(days=7)))
        self.var_hasta = tk.StringVar(value=format_fecha_editable(today))
        self.var_filtro = tk.StringVar(value="Todas")
        self.var_buscar = tk.StringVar()
        self.var_resumen = tk.StringVar(value="")
        self.var_cfg = tk.StringVar(value="")
        self._rows: list[RegistroAuditoriaSync] = []
        self._build()
        self.refrescar()

    def _build(self) -> None:
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            head,
            text="AUDITORÍA — SUBIDAS A LA NUBE",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)
        self.btn_subir = tk.Button(
            head,
            text="⬆  Subir datos faltantes",
            font=("Segoe UI", 11, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.subir_faltantes,
        )
        self.btn_subir.pack(side=tk.RIGHT, padx=(8, 0))
        secondary_button(head, "Actualizar", self.refrescar).pack(side=tk.RIGHT)

        tk.Label(
            self,
            textvariable=self.var_cfg,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=12)

        filtros = tk.Frame(self, bg=Theme.PANEL, padx=12, pady=8)
        filtros.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(filtros, text="Desde", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=0, sticky="w"
        )
        text_entry(filtros, self.var_desde, 12).grid(row=1, column=0, sticky="w")

        tk.Label(filtros, text="Hasta", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        text_entry(filtros, self.var_hasta, 12).grid(
            row=1, column=1, sticky="w", padx=(12, 0)
        )

        tk.Label(filtros, text="Estado", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=2, sticky="w", padx=(12, 0)
        )
        self.cb_filtro = ttk.Combobox(
            filtros,
            textvariable=self.var_filtro,
            values=("Todas", "OK", "Error"),
            state="readonly",
            width=10,
        )
        self.cb_filtro.grid(row=1, column=2, sticky="w", padx=(12, 0))
        self.cb_filtro.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())

        tk.Label(filtros, text="Buscar", fg=Theme.MUTED, bg=Theme.PANEL).grid(
            row=0, column=3, sticky="w", padx=(12, 0)
        )
        ent = text_entry(filtros, self.var_buscar, 18)
        ent.grid(row=1, column=3, sticky="w", padx=(12, 0))
        ent.bind("<Return>", lambda _e: self.refrescar())

        secondary_button(filtros, "Filtrar", self.refrescar).grid(
            row=1, column=4, padx=(12, 0)
        )
        secondary_button(
            filtros, "Hoy", lambda: self._rango_rapido(0)
        ).grid(row=1, column=5, padx=(6, 0))
        secondary_button(
            filtros, "7 días", lambda: self._rango_rapido(7)
        ).grid(row=1, column=6, padx=(6, 0))

        tk.Label(
            self,
            textvariable=self.var_resumen,
            font=("Segoe UI", 10, "bold"),
            fg=Theme.FG,
            bg=Theme.BG,
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 4))

        wrap = tk.Frame(self, bg=Theme.BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        style = ttk.Style()
        style.configure(
            "Aud.Treeview",
            background=Theme.TREE_BG,
            foreground=Theme.FG,
            fieldbackground=Theme.TREE_BG,
            rowheight=26,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Aud.Treeview.Heading",
            background=Theme.TREE_HEAD,
            foreground=Theme.TREE_HEAD_FG,
            font=("Segoe UI", 9, "bold"),
        )

        cols = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", style="Aud.Treeview"
        )
        for key, title, width in self.COLS:
            self.tree.heading(key, text=title)
            anchor = "w" if key in ("id_remoto", "cliente", "msg", "lote") else "center"
            self.tree.column(key, width=width, anchor=anchor, stretch=True)

        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        sx = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.tag_configure("ok", foreground=Theme.ST_COLOR)
        self.tree.tag_configure("err", foreground=Theme.ERR_COLOR)
        self.tree.tag_configure("dup", foreground=Theme.US_COLOR)

    def _rango_rapido(self, dias: int) -> None:
        hoy = date.today()
        desde = hoy if dias <= 0 else hoy - timedelta(days=dias)
        self.var_desde.set(format_fecha_editable(desde))
        self.var_hasta.set(format_fecha_editable(hoy))
        self.refrescar()

    def _parse_rango(self) -> tuple[Optional[str], Optional[str]]:
        d = parse_fecha_produccion(self.var_desde.get())
        h = parse_fecha_produccion(self.var_hasta.get())
        desde = d.strftime("%Y-%m-%d") if d else None
        hasta = h.strftime("%Y-%m-%d") if h else None
        return desde, hasta

    def subir_faltantes(self) -> None:
        if self.sync is None:
            messagebox.showwarning("Auditoría", "Sync no está disponible.")
            return
        if self._subiendo or self.sync.busy:
            messagebox.showinfo("Auditoría", "Ya hay una subida en curso.")
            return
        if not SYNC_TOKEN:
            messagebox.showwarning(
                "Auditoría",
                "Falta PRECIX_SYNC_TOKEN. Configure el token en las variables de entorno.",
            )
            return
        pend = self.db.contar_pendientes()
        if pend == 0:
            messagebox.showinfo("Auditoría", "No hay registros pendientes de subir.")
            self.refrescar()
            return
        if not messagebox.askyesno(
            "Subir a la nube",
            f"Hay {pend} fardo(s) pendiente(s).\n\n"
            "¿Enviarlos ahora al sistema integrado?",
        ):
            return
        self._subiendo = True
        self.btn_subir.config(state=tk.DISABLED, text="Subiendo…")
        self.var_cfg.set(f"Subiendo {pend} pendiente(s)…")

        def _work() -> None:
            try:
                result = self.sync.sync_now(continuar_si_falla=True)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": 0, "error": 1, "restantes": pend, "_exc": str(exc)}
            self.after(0, lambda: self._fin_subida(result))

        threading.Thread(target=_work, name="AuditManualSync", daemon=True).start()

    def _fin_subida(self, result: dict) -> None:
        self._subiendo = False
        self.btn_subir.config(state=tk.NORMAL, text="⬆  Subir datos faltantes")
        self.refrescar()
        if result.get("_exc"):
            messagebox.showerror("Auditoría", f"Error al subir:\n{result['_exc']}")
            return
        ok = int(result.get("ok") or 0)
        err = int(result.get("error") or 0)
        rest = int(result.get("restantes") or 0)
        messagebox.showinfo(
            "Subida a la nube",
            f"Enviados OK: {ok}\nErrores: {err}\nPendientes restantes: {rest}",
        )

    def refrescar(self) -> None:
        tok = "token OK" if SYNC_TOKEN else "sin token"
        cada = (
            f"cada {max(1, SYNC_INTERVAL_S // 60)} min"
            if SYNC_INTERVAL_S >= 60
            else f"cada {SYNC_INTERVAL_S}s"
        )
        pend = self.db.contar_pendientes()
        self.var_cfg.set(
            f"Cron {cada} mientras la app está abierta · {tok} · "
            f"planta {SYNC_PLANTA} · {pend} pendiente(s) · {SYNC_API_URL}"
        )

        filtro = self.var_filtro.get()
        solo_ok: Optional[bool]
        if filtro == "OK":
            solo_ok = True
        elif filtro == "Error":
            solo_ok = False
        else:
            solo_ok = None

        desde, hasta = self._parse_rango()
        self._rows = self.db.auditoria_sync(
            limite=800,
            solo_ok=solo_ok,
            desde=desde,
            hasta=hasta,
            texto=self.var_buscar.get(),
        )
        self.tree.delete(*self.tree.get_children())
        ok_n = 0
        err_n = 0
        for r in self._rows:
            if r.ok:
                ok_n += 1
                tag = "dup" if r.duplicado else "ok"
                estado = "DUP" if r.duplicado else "OK"
            else:
                err_n += 1
                tag = "err"
                estado = "ERROR"
            self.tree.insert(
                "",
                tk.END,
                iid=str(r.id),
                values=(
                    r.enviado_en,
                    estado,
                    r.http_status or "—",
                    r.nro_fardo,
                    r.pesaje_id,
                    r.id_remoto or "—",
                    r.lote,
                    r.cliente,
                    r.color,
                    f"{r.peso_bruto:.2f}",
                    f"{r.peso_neto:.2f}",
                    r.planta,
                    "sí" if r.duplicado else "",
                    r.mensaje,
                ),
                tags=(tag,),
            )

        total_db, ok_db = self.db.contar_auditoria_sync()
        self.var_resumen.set(
            f"{pend} pendiente(s) de subir  ·  "
            f"Mostrando {len(self._rows)} · vista OK {ok_n} / Error {err_n}  ·  "
            f"Histórico {total_db} (exitosos {ok_db})"
        )
