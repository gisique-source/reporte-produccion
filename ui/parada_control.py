"""Botón de parada: abrir el tiempo y cerrarlo al segundo toque."""

from __future__ import annotations

import threading
from datetime import datetime

import tkinter as tk
from tkinter import messagebox

from paradas_api import push_evento
from ui.parada_dialog import ParadaDialog
from ui.widgets import Theme, confirm_modal


class ParadaControl:
    def __init__(self, app, parent: tk.Widget, store) -> None:
        self.app = app
        self.store = store
        self.var = tk.StringVar(value="PARADA")
        self.btn = tk.Button(
            parent,
            textvariable=self.var,
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg=Theme.US_COLOR,
            activeforeground="#ffffff",
            activebackground="#92400e",
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.on_click,
        )
        self.btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.pintar()

    def on_click(self) -> None:
        abierta = self.store.abierta()
        if abierta is not None:
            self._reanudar(abierta)
            return
        self._dialogo()

    def pintar(self) -> None:
        abierta = self.store.abierta()
        if abierta is None:
            self.var.set("PARADA")
            self.btn.configure(bg=Theme.US_COLOR, activebackground="#92400e")
            return
        self.var.set("REANUDAR")
        self.btn.configure(bg=Theme.ERR_COLOR, activebackground="#991b1b")

    def _operario(self) -> str:
        pesaje = getattr(self.app, "view_pesaje", None)
        if pesaje is not None:
            texto = pesaje.var_operario.get().strip()
            if texto:
                return texto
        return ""

    def _dialogo(self) -> None:
        dlg = ParadaDialog(self.app, operario=self._operario())
        self.app.wait_window(dlg)
        if not dlg.result:
            self.pintar()
            return
        if self.store.abierta() is not None:
            messagebox.showinfo(
                "Parada",
                "Ya hay una parada abierta en esta planta. Reanude antes de iniciar otra.",
                parent=self.app,
            )
            self.pintar()
            return
        parada_id = self.store.insertar(dlg.result)
        self.pintar()
        self._empujar(parada_id)

    def _reanudar(self, parada) -> None:
        clasif = _texto_clasificacion(parada)
        if not confirm_modal(
            self.app,
            "Reanudar producción",
            f"¿Cerrar la parada y reanudar?\n\n"
            f"Inicio: {parada.inicio}\n"
            f"Clasificación: {clasif}",
            ok_text="Reanudar",
            cancel_text="Seguir parada",
        ):
            return
        fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.store.cerrar(parada.id, fin)
        self.pintar()
        self._empujar(parada.id)

    def _empujar(self, parada_id: int) -> None:
        def work() -> None:
            parada = self.store.obtener(parada_id)
            if parada is None:
                return
            ok, msg = push_evento(self.store, parada)
            self.app.after(0, lambda: self._fin_push(parada_id, ok, msg))

        threading.Thread(target=work, name="ParadaPush", daemon=True).start()

    def _fin_push(self, parada_id: int, ok: bool, msg: str) -> None:
        if not ok and "PARADA_ABIERTA" in msg:
            parada = self.store.obtener(parada_id)
            if parada is not None and parada.abierta:
                self.store.descartar(parada_id)
                messagebox.showwarning(
                    "Parada",
                    "Esta planta ya tiene una parada abierta en la nube. "
                    "Ciérrela antes de iniciar otra.",
                    parent=self.app,
                )
        elif not ok and msg:
            self.app.lbl_sync.config(text=f"Parada: {msg[:48]}", fg=Theme.ERR_COLOR)
        self.pintar()
        for nombre in ("view_paradas", "view_historial_paradas"):
            vista = getattr(self.app, nombre, None)
            if vista is None:
                continue
            try:
                vista.refrescar()
            except tk.TclError:
                pass


def _texto_clasificacion(parada) -> str:
    if not parada.clasificada:
        return "sin clasificar (lo hace la nube)"
    tipo = parada.tipo_nombre or parada.tipo_codigo or "tipo"
    maquina = parada.maquinaria_nombre or parada.maquinaria_codigo
    if maquina:
        return f"{tipo} · {maquina}"
    return tipo
