"""Desplegable con búsqueda (filtrar lista al escribir)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import tkinter as tk

from catalog import normalizar_maestro
from ui.widgets import Theme


class SearchableDropdown(tk.Frame):
    """Entry + lista filtrable. Sirve para llenar un campo o filtrar registros."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        textvariable: Optional[tk.StringVar] = None,
        values: Sequence[str] = (),
        width: int = 14,
        placeholder: str = "",
        font: tuple = ("Segoe UI", 10),
        on_change: Optional[Callable[[str], None]] = None,
        on_commit: Optional[Callable[[str], None]] = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent, bg=Theme.INPUT_BG, highlightthickness=1, highlightbackground=Theme.BORDER)
        self._all: list[str] = list(values)
        self._placeholder = placeholder
        self._on_change = on_change
        self._on_commit = on_commit
        self._pop: Optional[tk.Toplevel] = None
        self._list: Optional[tk.Listbox] = None
        self._ignore_trace = False
        self.var = textvariable or tk.StringVar()

        self._entry = tk.Entry(
            self,
            textvariable=self.var,
            font=font,
            fg=Theme.FG,
            bg=Theme.INPUT_BG,
            insertbackground=Theme.FG,
            relief=tk.FLAT,
            width=width,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=1 if compact else 2)
        self._btn = tk.Button(
            self,
            text="▾",
            font=("Segoe UI", 8 if compact else 9),
            fg=Theme.MUTED,
            bg=Theme.INPUT_BG,
            relief=tk.FLAT,
            width=2,
            cursor="hand2",
            command=self.toggle,
        )
        self._btn.pack(side=tk.RIGHT, fill=tk.Y)

        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<Down>", self._move_sel)
        self._entry.bind("<Up>", self._move_sel)
        self._entry.bind("<Return>", self._accept)
        self._entry.bind("<Escape>", lambda _e: self.close())
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.var.trace_add("write", self._on_var)

    def set_values(self, values: Sequence[str]) -> None:
        actual = self.get()
        self._all = list(values)
        if actual and actual not in self._all:
            self._all = [actual] + self._all
        if self._pop is not None:
            self._fill_list(self._entry.get())

    def get(self) -> str:
        texto = self.var.get().strip()
        if self._placeholder and texto == self._placeholder:
            return ""
        return texto

    def resolved_value(self) -> str:
        texto = self.get()
        return self._unico_match(texto) or texto

    def set(self, texto: str) -> None:
        self._ignore_trace = True
        try:
            self.var.set(texto)
        finally:
            self._ignore_trace = False
        self._refresh_placeholder()

    def focus_set(self) -> None:  # type: ignore[override]
        self._entry.focus_set()

    def bind(self, sequence: str, func, add: str | None = None):  # type: ignore[override]
        return self._entry.bind(sequence, func, add)

    def owns_widget(self, widget) -> bool:
        if widget is None:
            return False
        try:
            w = str(widget)
        except tk.TclError:
            return False
        if w.startswith(str(self)):
            return True
        if self._pop is not None and w.startswith(str(self._pop)):
            return True
        return False

    def toggle(self) -> None:
        if self._pop is None:
            self.open()
        else:
            self.close()

    def open(self) -> None:
        if self._pop is not None:
            self._fill_list(self._entry.get())
            return
        pop = tk.Toplevel(self)
        pop.overrideredirect(True)
        try:
            pop.attributes("-topmost", True)
        except tk.TclError:
            pass
        pop.configure(bg=Theme.BORDER)
        lst = tk.Listbox(
            pop,
            font=("Segoe UI", 10),
            fg=Theme.FG,
            bg=Theme.PANEL,
            selectbackground=Theme.ACCENT,
            selectforeground="#ffffff",
            relief=tk.FLAT,
            activestyle="none",
            exportselection=False,
        )
        lst.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        lst.bind("<ButtonRelease-1>", lambda _e: self._pick_list())
        lst.bind("<Return>", lambda _e: self._pick_list())
        lst.bind("<Escape>", lambda _e: self.close())
        self._pop = pop
        self._list = lst
        self._place_pop()
        self._fill_list(self._entry.get())
        pop.bind("<FocusOut>", self._on_pop_focus_out)

    def close(self) -> None:
        if self._pop is None:
            return
        try:
            self._pop.destroy()
        except tk.TclError:
            pass
        self._pop = None
        self._list = None

    def destroy(self) -> None:  # type: ignore[override]
        self.close()
        super().destroy()

    def _on_var(self, *_args) -> None:
        if self._ignore_trace:
            return
        if self._on_change:
            self._on_change(self.get())

    def _on_focus_in(self, _event=None) -> None:
        if self._placeholder and self.var.get() == self._placeholder:
            self._ignore_trace = True
            try:
                self.var.set("")
            finally:
                self._ignore_trace = False
            self._entry.configure(fg=Theme.FG)

    def _on_entry_focus_out(self, _event=None) -> None:
        self.after(150, self._maybe_placeholder)

    def _maybe_placeholder(self) -> None:
        if self.owns_widget(self.focus_get()):
            return
        if self._placeholder and not self.get():
            self._refresh_placeholder()

    def _refresh_placeholder(self) -> None:
        if self._placeholder and not self.var.get().strip():
            self._ignore_trace = True
            try:
                self.var.set(self._placeholder)
            finally:
                self._ignore_trace = False
            self._entry.configure(fg=Theme.MUTED)
        else:
            self._entry.configure(fg=Theme.FG)

    def _on_key(self, event) -> None:
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.open()
        self._fill_list(self._entry.get())

    def _move_sel(self, event) -> str:
        self.open()
        lst = self._list
        if lst is None or lst.size() == 0:
            return "break"
        cur = lst.curselection()
        idx = int(cur[0]) if cur else 0
        if event.keysym == "Down":
            idx = min(idx + 1, lst.size() - 1) if cur else 0
        else:
            idx = max(idx - 1, 0)
        lst.selection_clear(0, tk.END)
        lst.selection_set(idx)
        lst.see(idx)
        return "break"

    def _accept(self, _event=None) -> str:
        if self._pop is not None and self._list is not None and self._list.curselection():
            self._pick_list()
            return "break"
        texto = self._entry.get().strip()
        match = self._unico_match(texto)
        if match:
            self._apply(match, commit=True)
        elif self._on_commit:
            self._on_commit(self.get())
        self.close()
        return "break"

    def _pick_list(self) -> None:
        lst = self._list
        if lst is None:
            return
        sel = lst.curselection()
        if not sel:
            return
        valor = lst.get(sel[0])
        self._apply(valor, commit=True)

    def _apply(self, valor: str, *, commit: bool) -> None:
        self.set(valor)
        self.close()
        if self._on_change:
            self._on_change(valor)
        if commit and self._on_commit:
            self._on_commit(valor)

    def _unico_match(self, texto: str) -> str:
        q = normalizar_maestro(texto)
        if not q:
            return ""
        hits = [v for v in self._all if q in normalizar_maestro(v)]
        if len(hits) == 1:
            return hits[0]
        exactos = [v for v in self._all if normalizar_maestro(v) == q]
        return exactos[0] if exactos else ""

    def _filtrados(self, texto: str) -> list[str]:
        q = normalizar_maestro(texto)
        if self._placeholder and texto.strip() == self._placeholder:
            q = ""
        if not q:
            return list(self._all)
        return [v for v in self._all if q in normalizar_maestro(v)]

    def _fill_list(self, texto: str) -> None:
        lst = self._list
        if lst is None:
            return
        items = self._filtrados(texto)
        lst.delete(0, tk.END)
        for v in items:
            lst.insert(tk.END, v)
        if items:
            lst.selection_set(0)
        n = min(max(len(items), 1), 8)
        lst.configure(height=n)
        self._place_pop()

    def _place_pop(self) -> None:
        if self._pop is None:
            return
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 140)
        n = self._list.size() if self._list is not None else 1
        h = min(max(n, 1), 8) * 22 + 8
        self._pop.geometry(f"{w}x{h}+{x}+{y}")

    def _on_pop_focus_out(self, _event=None) -> None:
        self.after(120, self._close_if_left)

    def _close_if_left(self) -> None:
        fg = self.focus_get()
        if self.owns_widget(fg):
            return
        self.close()
