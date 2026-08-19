"""Botones de acción superpuestos en la última columna de un Treeview."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import tkinter as tk
from tkinter import ttk

AccionSpec = tuple[str, str, Callable[[], None]]


class TreeRowActions:
    def __init__(
        self,
        tree: ttk.Treeview,
        col: str,
        spec: Callable[[str], Optional[Sequence[AccionSpec]]],
    ) -> None:
        self.tree = tree
        self.col = col
        self.spec = spec
        self._frames: dict[str, tk.Frame] = {}
        tree.bind("<Configure>", lambda _e: self.sync(), add="+")
        tree.bind("<MouseWheel>", lambda _e: self._later(), add="+")
        tree.bind("<Button-4>", lambda _e: self._later(), add="+")
        tree.bind("<Button-5>", lambda _e: self._later(), add="+")

    def attach_scroll(self, scrollbar: ttk.Scrollbar) -> None:
        def _yset(*args) -> None:
            scrollbar.set(*args)
            self.sync()

        def _yview(*args) -> None:
            self.tree.yview(*args)
            self.sync()

        self.tree.configure(yscrollcommand=_yset)
        scrollbar.configure(command=_yview)

    def _later(self) -> None:
        self.tree.after_idle(self.sync)

    def sync(self) -> None:
        if not self.tree.winfo_ismapped():
            return
        seen: set[str] = set()
        for iid in self.tree.get_children():
            acciones = self.spec(iid)
            bbox = self.tree.bbox(iid, self.col)
            if not acciones or not bbox:
                self._drop(iid)
                continue
            seen.add(iid)
            fr = self._frames.get(iid)
            if fr is None or not fr.winfo_exists():
                fr = tk.Frame(self.tree, bg=self.tree.winfo_toplevel().cget("bg"))
                self._frames[iid] = fr
            self._fill(fr, list(acciones))
            x, y, w, h = bbox
            fr.place(x=x + 1, y=y + 1, width=max(w - 2, 80), height=max(h - 2, 20))
        for iid in list(self._frames):
            if iid not in seen:
                self._drop(iid)

    def _fill(self, fr: tk.Frame, acciones: list[AccionSpec]) -> None:
        for child in fr.winfo_children():
            child.destroy()
        for texto, bg, cmd in acciones:
            tk.Button(
                fr,
                text=texto,
            font=("Segoe UI", 7, "bold"),
                fg="#ffffff",
                bg=bg,
                activebackground=bg,
                activeforeground="#ffffff",
                relief=tk.FLAT,
                cursor="hand2",
                command=cmd,
                padx=4,
                pady=0,
            ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1)

    def _drop(self, iid: str) -> None:
        fr = self._frames.pop(iid, None)
        if fr is not None:
            try:
                fr.destroy()
            except tk.TclError:
                pass
