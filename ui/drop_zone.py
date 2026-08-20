"""Zona visual y modal para elegir archivo Excel (arrastrar o buscar)."""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk
from tkinter import filedialog

from ui.file_drop import DND_AVAILABLE, enable_file_drop, first_excel_path
from ui.widgets import Theme, secondary_button


class ExcelDropZone(tk.Frame):
    """
    Área grande y clara para soltar .xlsx / .xlsm.
    Cambia de color al poner el archivo encima.
    """

    IDLE_BG = "#eef2f7"
    IDLE_BORDER = "#94a3b8"
    IDLE_FG = "#334155"
    IDLE_HINT = "#64748b"

    HOVER_BG = "#dcfce7"
    HOVER_BORDER = "#16a34a"
    HOVER_FG = "#14532d"
    HOVER_HINT = "#166534"

    DISABLED_BG = "#f1f5f9"
    DISABLED_BORDER = "#cbd5e1"
    DISABLED_FG = "#94a3b8"

    def __init__(
        self,
        master: tk.Widget,
        *,
        on_file: Callable[[str], None],
        on_browse: Optional[Callable[[], None]] = None,
        height: int = 120,
        title_idle: str = "Suelte aquí el archivo Excel",
        hint_idle: str = "Arrastre un .xlsm / .xlsx sobre esta zona",
    ) -> None:
        super().__init__(
            master,
            bg=self.IDLE_BG,
            highlightbackground=self.IDLE_BORDER,
            highlightcolor=self.IDLE_BORDER,
            highlightthickness=2,
            bd=0,
        )
        self.on_file = on_file
        self.on_browse = on_browse
        self._title_idle = title_idle
        self._hint_idle = hint_idle
        self._hover = False
        self._enter_depth = 0

        self.var_title = tk.StringVar()
        self.var_hint = tk.StringVar()

        inner = tk.Frame(self, bg=self.IDLE_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        self._inner = inner

        self.lbl_icon = tk.Label(
            inner,
            text="⬇",
            font=("Segoe UI", 28, "bold"),
            fg=self.IDLE_FG,
            bg=self.IDLE_BG,
        )
        self.lbl_icon.pack(side=tk.LEFT, padx=(4, 16))

        texts = tk.Frame(inner, bg=self.IDLE_BG)
        texts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._texts = texts

        self.lbl_title = tk.Label(
            texts,
            textvariable=self.var_title,
            font=("Segoe UI", 13, "bold"),
            fg=self.IDLE_FG,
            bg=self.IDLE_BG,
            anchor="w",
        )
        self.lbl_title.pack(fill=tk.X)
        self.lbl_hint = tk.Label(
            texts,
            textvariable=self.var_hint,
            font=("Segoe UI", 10),
            fg=self.IDLE_HINT,
            bg=self.IDLE_BG,
            anchor="w",
        )
        self.lbl_hint.pack(fill=tk.X)

        self._painted = (
            self,
            inner,
            texts,
            self.lbl_icon,
            self.lbl_title,
            self.lbl_hint,
        )

        self.configure(height=height)
        self.pack_propagate(False)

        if DND_AVAILABLE:
            self.var_title.set(self._title_idle)
            self.var_hint.set(self._hint_idle)
            enable_file_drop(
                self,
                self._on_paths,
                on_enter=self._on_drag_enter,
                on_leave=self._on_drag_leave,
            )
            for w in (inner, texts, self.lbl_icon, self.lbl_title, self.lbl_hint):
                enable_file_drop(
                    w,
                    self._on_paths,
                    on_enter=self._on_drag_enter,
                    on_leave=self._on_drag_leave,
                )
        else:
            self.var_title.set("Arrastre no disponible en este equipo")
            self.var_hint.set("Use el botón «Buscar en el equipo…»")
            self._apply_colors(
                self.DISABLED_BG,
                self.DISABLED_BORDER,
                self.DISABLED_FG,
                self.DISABLED_FG,
            )

        if on_browse:
            for w in self._painted:
                w.bind("<Button-1>", self._on_click)
                w.configure(cursor="hand2")

    def _on_click(self, _event=None) -> None:
        if self.on_browse:
            self.on_browse()

    def _on_paths(self, paths: list[str]) -> None:
        self._enter_depth = 0
        self._set_hover(False)
        excel = first_excel_path(paths)
        if not excel:
            self._flash_error()
            return
        self.on_file(excel)

    def _on_drag_enter(self) -> None:
        self._enter_depth += 1
        self._set_hover(True)

    def _on_drag_leave(self) -> None:
        self._enter_depth = max(0, self._enter_depth - 1)
        if self._enter_depth == 0:
            self._set_hover(False)

    def _set_hover(self, active: bool) -> None:
        if self._hover == active:
            return
        self._hover = active
        if not DND_AVAILABLE:
            return
        if active:
            self.var_title.set("¡Suelte ahora para importar!")
            self.var_hint.set("El archivo se abrirá en la vista previa por días")
            self.lbl_icon.config(text="📥")
            self._apply_colors(
                self.HOVER_BG,
                self.HOVER_BORDER,
                self.HOVER_FG,
                self.HOVER_HINT,
            )
            self.configure(highlightthickness=3)
        else:
            self.var_title.set(self._title_idle)
            self.var_hint.set(self._hint_idle)
            self.lbl_icon.config(text="⬇")
            self._apply_colors(
                self.IDLE_BG,
                self.IDLE_BORDER,
                self.IDLE_FG,
                self.IDLE_HINT,
            )
            self.configure(highlightthickness=2)

    def _apply_colors(
        self, bg: str, border: str, fg: str, hint: str
    ) -> None:
        self.configure(
            bg=bg,
            highlightbackground=border,
            highlightcolor=border,
        )
        self._inner.configure(bg=bg)
        self._texts.configure(bg=bg)
        self.lbl_icon.configure(bg=bg, fg=fg)
        self.lbl_title.configure(bg=bg, fg=fg)
        self.lbl_hint.configure(bg=bg, fg=hint)

    def _flash_error(self) -> None:
        self._enter_depth = 0
        self._hover = False
        self.var_title.set("Archivo no válido")
        self.var_hint.set("Use un .xlsx o .xlsm de hoja de producción")
        self.lbl_icon.config(text="⚠")
        self.configure(highlightthickness=3)
        self._apply_colors("#fee2e2", Theme.ERR_COLOR, Theme.ERR_COLOR, "#991b1b")

        def _restore() -> None:
            self.lbl_icon.config(text="⬇")
            self.configure(highlightthickness=2)
            if DND_AVAILABLE:
                self.var_title.set(self._title_idle)
                self.var_hint.set(self._hint_idle)
                self._apply_colors(
                    self.IDLE_BG,
                    self.IDLE_BORDER,
                    self.IDLE_FG,
                    self.IDLE_HINT,
                )
            else:
                self.var_title.set("Arrastre no disponible en este equipo")
                self.var_hint.set("Use el botón «Buscar en el equipo…»")
                self._apply_colors(
                    self.DISABLED_BG,
                    self.DISABLED_BORDER,
                    self.DISABLED_FG,
                    self.DISABLED_FG,
                )

        self.after(1600, _restore)


class ExcelPickDialog(tk.Toplevel):
    """
    Modal al pulsar «Archivo Excel…»:
    arrastrar archivo o buscarlo en el equipo.
    """

    def __init__(
        self,
        master: tk.Widget,
        *,
        on_file: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self.on_file = on_file
        self.title("Importar Excel de producción")
        self.configure(bg=Theme.BG)
        self.geometry("520x280")
        self.minsize(440, 240)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)

        tk.Label(
            self,
            text="Cargar hoja mensual Excel",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(16, 4))
        tk.Label(
            self,
            text="Elija una forma de seleccionar el archivo .xlsm / .xlsx",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(0, 10))

        self.zone = ExcelDropZone(
            self,
            on_file=self._elegido,
            on_browse=None,
            height=120,
            title_idle="Suelte aquí el archivo Excel",
            hint_idle="Arrastre el archivo sobre esta zona (cambia a verde)",
        )
        self.zone.pack(fill=tk.X, padx=20, pady=(0, 12))

        btns = tk.Frame(self, bg=Theme.BG)
        btns.pack(fill=tk.X, padx=20, pady=(0, 16))

        tk.Button(
            btns,
            text="Buscar en el equipo…",
            font=("Segoe UI", 11, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._buscar,
        ).pack(side=tk.LEFT)

        secondary_button(btns, "Cancelar", self.destroy).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(50, self._centrar)

    def _centrar(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master.winfo_toplevel()
            px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(0, px)}+{max(0, py)}")
        except tk.TclError:
            pass

    def _buscar(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar hoja de producción Excel",
            filetypes=[
                ("Excel extrusora", "*.xlsm *.xlsx"),
                ("Macro Excel", "*.xlsm"),
                ("Excel", "*.xlsx"),
                ("Todos", "*.*"),
            ],
        )
        if path:
            self._elegido(path)

    def _elegido(self, path: str) -> None:
        self.destroy()
        if path:
            self.on_file(path)
