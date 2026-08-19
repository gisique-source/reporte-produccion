"""Componentes de UI reutilizables (tema industrial claro)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Theme:
    BG = "#f3f5f8"
    PANEL = "#ffffff"
    FG = "#1a2332"
    ACCENT = "#1d4ed8"
    ST_COLOR = "#15803d"
    US_COLOR = "#b45309"
    ERR_COLOR = "#b91c1c"
    MUTED = "#5c6b7a"
    INPUT_BG = "#ffffff"
    BTN_BG = "#15803d"
    BTN_ACTIVE = "#16a34a"
    TREE_BG = "#ffffff"
    TREE_HEAD = "#e8eef6"
    TREE_HEAD_FG = "#1a2332"
    BORDER = "#d0d7de"
    CARD_TOTAL = "#eef1f5"
    CARD_BRUTO = "#fde8e8"
    CARD_NETO = "#e7f6ec"
    ROW_LAST = "#dbeafe"
    ROW_NEXT = "#dcfce7"
    ROW_DIRTY = "#fff3b0"
    ROW_SAVED = "#ffffff"


def field_label(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        font=("Segoe UI", 10, "bold"),
        fg=Theme.MUTED,
        bg=Theme.PANEL,
        anchor="w",
    )


def text_entry(
    parent: tk.Widget,
    textvariable: tk.StringVar,
    width: int = 18,
    *,
    readonly: bool = False,
) -> tk.Entry:
    entry = tk.Entry(
        parent,
        textvariable=textvariable,
        font=("Segoe UI", 13),
        fg=Theme.FG,
        bg=Theme.INPUT_BG,
        insertbackground=Theme.FG,
        relief=tk.SOLID,
        bd=1,
        highlightthickness=0,
        width=width,
    )
    if readonly:
        entry.configure(state="readonly", readonlybackground=Theme.INPUT_BG)
    return entry


def combo_entry(
    parent: tk.Widget,
    textvariable: tk.StringVar,
    values: list[str] | tuple[str, ...] = (),
    width: int = 18,
    *,
    editable: bool = False,
) -> ttk.Combobox:
    style = ttk.Style()
    style.configure(
        "App.TCombobox",
        fieldbackground=Theme.INPUT_BG,
        background=Theme.PANEL,
        foreground=Theme.FG,
        arrowcolor=Theme.FG,
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", Theme.INPUT_BG), ("!readonly", Theme.INPUT_BG)],
        foreground=[("readonly", Theme.FG), ("!readonly", Theme.FG)],
    )
    return ttk.Combobox(
        parent,
        textvariable=textvariable,
        values=list(values),
        font=("Segoe UI", 12),
        width=width,
        # normal = escribir a mano + lista; readonly = solo elegir
        state="normal" if editable else "readonly",
        style="App.TCombobox",
    )


def primary_button(
    parent: tk.Widget,
    text: str,
    command,
    *,
    bg: str | None = None,
    active_bg: str | None = None,
) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        font=("Segoe UI", 18, "bold"),
        fg="#ffffff",
        bg=bg or Theme.BTN_BG,
        activeforeground="#ffffff",
        activebackground=active_bg or Theme.BTN_ACTIVE,
        relief=tk.FLAT,
        padx=28,
        pady=14,
        cursor="hand2",
        command=command,
    )


def secondary_button(parent: tk.Widget, text: str, command) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        font=("Segoe UI", 11, "bold"),
        fg="#ffffff",
        bg=Theme.ACCENT,
        activeforeground="#ffffff",
        activebackground="#3d7cef",
        relief=tk.FLAT,
        padx=14,
        pady=6,
        cursor="hand2",
        command=command,
    )


def confirm_modal(
    parent: tk.Widget,
    title: str,
    message: str,
    *,
    ok_text: str = "Confirmar",
    cancel_text: str = "Cancelar",
) -> bool:
    """Modal de confirmación (soft-delete / ediciones)."""
    top = parent.winfo_toplevel()
    win = tk.Toplevel(top)
    win.title(title)
    win.configure(bg=Theme.PANEL)
    win.transient(top)
    win.resizable(False, False)
    win.grab_set()
    result = {"ok": False}

    tk.Label(
        win,
        text=title,
        font=("Segoe UI", 13, "bold"),
        fg=Theme.FG,
        bg=Theme.PANEL,
        anchor="w",
    ).pack(fill=tk.X, padx=20, pady=(16, 6))
    tk.Label(
        win,
        text=message,
        font=("Segoe UI", 10),
        fg=Theme.MUTED,
        bg=Theme.PANEL,
        justify="left",
        wraplength=420,
        anchor="w",
    ).pack(fill=tk.X, padx=20, pady=(0, 16))

    btns = tk.Frame(win, bg=Theme.PANEL)
    btns.pack(fill=tk.X, padx=20, pady=(0, 16))

    def _ok() -> None:
        result["ok"] = True
        win.destroy()

    def _cancel() -> None:
        result["ok"] = False
        win.destroy()

    tk.Button(
        btns,
        text=cancel_text,
        font=("Segoe UI", 10, "bold"),
        fg=Theme.FG,
        bg=Theme.TREE_HEAD,
        relief=tk.FLAT,
        padx=14,
        pady=8,
        cursor="hand2",
        command=_cancel,
    ).pack(side=tk.RIGHT, padx=(8, 0))
    tk.Button(
        btns,
        text=ok_text,
        font=("Segoe UI", 10, "bold"),
        fg="#ffffff",
        bg=Theme.ERR_COLOR,
        relief=tk.FLAT,
        padx=14,
        pady=8,
        cursor="hand2",
        command=_ok,
    ).pack(side=tk.RIGHT)

    win.bind("<Escape>", lambda _e: _cancel())
    win.bind("<Return>", lambda _e: _ok())
    win.update_idletasks()
    x = top.winfo_rootx() + (top.winfo_width() - win.winfo_reqwidth()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(x, 40)}+{max(y, 40)}")
    top.wait_window(win)
    return bool(result["ok"])


class ScrollableFrame(tk.Frame):
    """
    Contenedor con scroll vertical (rueda del mouse).
    Usar `scroll.body` como padre de los widgets internos.
    """

    _OWN_SCROLL = (ttk.Treeview, tk.Listbox, tk.Text, tk.Canvas)

    def __init__(self, parent: tk.Widget, *, bg: str = Theme.BG, **kwargs) -> None:
        super().__init__(parent, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, bg=bg)

        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Re-bindear rueda en hijos nuevos (Entry, Label, etc.)
        self.body.bind("<Map>", lambda _e: self._bind_tree(self.body))
        self._bind_tree(self.body)

    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._bind_tree(self.body)

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_tree(self, widget: tk.Widget) -> None:
        """La rueda debe funcionar también sobre Entry/Label dentro del body."""
        for seq, handler in (
            ("<MouseWheel>", self._on_mousewheel),
            ("<Button-4>", self._on_mousewheel_linux),
            ("<Button-5>", self._on_mousewheel_linux),
        ):
            widget.bind(seq, handler, add="+")
        for child in widget.winfo_children():
            self._bind_tree(child)

    def _pointer_inside(self) -> bool:
        try:
            w = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            return False
        while w is not None:
            if w == self:
                return True
            w = w.master if hasattr(w, "master") else None
        return False

    def _over_own_scroll_widget(self) -> bool:
        """No robar la rueda a Treeview/Text que ya tienen su scrollbar."""
        try:
            w = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            return False
        while w is not None and w != self:
            if isinstance(w, self._OWN_SCROLL) and w is not self.canvas:
                return True
            w = w.master if hasattr(w, "master") else None
        return False

    def _on_mousewheel(self, event) -> str | None:
        if not self._pointer_inside() or self._over_own_scroll_widget():
            return None
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _on_mousewheel_linux(self, event) -> str | None:
        if not self._pointer_inside() or self._over_own_scroll_widget():
            return None
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        return "break"

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def ensure_visible(self, widget: tk.Widget) -> None:
        """Desplaza el canvas para que `widget` quede a la vista (p. ej. al enfocar)."""
        self.update_idletasks()
        try:
            y = widget.winfo_rooty() - self.body.winfo_rooty()
            h = self.canvas.winfo_height()
            top = self.canvas.canvasy(0)
            bot = top + h
            wh = widget.winfo_height()
            if y < top:
                self.canvas.yview_moveto(max(0, y / max(1, self.body.winfo_height())))
            elif y + wh > bot:
                self.canvas.yview_moveto(
                    max(0, (y + wh - h) / max(1, self.body.winfo_height()))
                )
        except tk.TclError:
            pass
