"""Aviso cuando el Nº de fardo ya está usado en el lote."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import tkinter as tk

from ui.widgets import Theme


def _cuando(fecha_hora: str) -> str:
    try:
        dt = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return fecha_hora[:16] if fecha_hora else "sin fecha"


def mostrar_fardo_duplicado(
    parent: tk.Widget,
    db,
    lote: str,
    nro: str,
    *,
    excluir_id: Optional[int] = None,
) -> bool:
    """
    Muestra día y estado de los fardos repetidos.
    Retorna True si el usuario los eliminó.
    """
    regs = db.listar_fardos_en_lote(lote, nro, excluir_id=excluir_id)
    if not regs:
        return False

    lineas = []
    for reg in regs:
        estado = "activo" if reg.activo else "oculto"
        lineas.append(
            f"· {_cuando(reg.fecha_hora)}  ·  {estado}  ·  "
            f"{reg.cliente or 'sin cliente'}  ·  ID {reg.id}"
        )
    texto = (
        f"El fardo {nro} ya existe en el lote {lote}.\n\n"
        + "\n".join(lineas)
        + "\n\nNo puede repetirse en el mismo lote."
    )

    top = parent.winfo_toplevel()
    win = tk.Toplevel(top)
    win.title("Fardo ya existe")
    win.configure(bg=Theme.PANEL)
    win.transient(top)
    win.resizable(False, False)
    win.grab_set()
    eliminados = {"ok": False}

    tk.Label(
        win,
        text="Fardo ya existe",
        font=("Segoe UI", 13, "bold"),
        fg=Theme.FG,
        bg=Theme.PANEL,
        anchor="w",
    ).pack(fill=tk.X, padx=20, pady=(16, 6))
    tk.Label(
        win,
        text=texto,
        font=("Segoe UI", 10),
        fg=Theme.MUTED,
        bg=Theme.PANEL,
        justify="left",
        anchor="w",
    ).pack(fill=tk.X, padx=20, pady=(0, 16))

    btns = tk.Frame(win, bg=Theme.PANEL)
    btns.pack(fill=tk.X, padx=20, pady=(0, 16))

    def _eliminar() -> None:
        for reg in regs:
            try:
                if reg.activo:
                    db.ocultar(reg.id)
                db.eliminar_definitivo(reg.id)
            except Exception:  # noqa: BLE001
                pass
        eliminados["ok"] = True
        win.destroy()

    tk.Button(
        btns,
        text="Cerrar",
        font=("Segoe UI", 10),
        fg=Theme.FG,
        bg=Theme.TREE_HEAD,
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
        command=win.destroy,
    ).pack(side=tk.LEFT)
    tk.Button(
        btns,
        text="Eliminar existentes",
        font=("Segoe UI", 10, "bold"),
        fg="#ffffff",
        bg=Theme.ERR_COLOR,
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
        command=_eliminar,
    ).pack(side=tk.RIGHT)

    win.bind("<Escape>", lambda _e: win.destroy())
    win.update_idletasks()
    x = top.winfo_rootx() + 80
    y = top.winfo_rooty() + 80
    win.geometry(f"+{max(x, 20)}+{max(y, 20)}")
    win.wait_window()
    return eliminados["ok"]
