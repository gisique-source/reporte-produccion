"""Modal de vista previa de etiqueta antes de imprimir."""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

from label_layout import get_layout
from models import DatosEtiqueta
from print_engine import imprimir_etiqueta, render_etiqueta_region
from ui.label_preview import PREVIEW_SCALE
from ui.widgets import Theme, secondary_button


class PrintPreviewDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Widget,
        datos: DatosEtiqueta,
        *,
        on_printed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.datos = datos
        self.on_printed = on_printed
        self._photo: Optional[ImageTk.PhotoImage] = None
        self.title(f"Vista previa · Fardo {datos.nro_fardo}")
        self.configure(bg=Theme.BG)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self._build()
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(10, self._center)

    def _build(self) -> None:
        tk.Label(
            self,
            text="Vista previa de etiqueta",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        ).pack(pady=(14, 4))
        tk.Label(
            self,
            text=(
                f"Fardo {self.datos.nro_fardo}  ·  {self.datos.cliente}  ·  "
                f"{self.datos.lote}  ·  Bruto {self.datos.peso_bruto:.2f}  ·  "
                f"Neto {self.datos.peso_neto:.2f} kg"
            ),
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(0, 8))

        frame = tk.Frame(self, bg=Theme.BORDER, padx=1, pady=1)
        frame.pack(padx=16, pady=4)
        try:
            layout = get_layout()
            tw = max(1, int(layout.label_width_mm * PREVIEW_SCALE))
            th = max(1, int(layout.label_height_mm * PREVIEW_SCALE))
            img = render_etiqueta_region(
                self.datos,
                dpi=int(25.4 * PREVIEW_SCALE),
                bg="white",
                show_guides=True,
            )
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            tk.Label(frame, image=self._photo, bg="#ffffff").pack()
        except Exception as exc:  # noqa: BLE001
            tk.Label(
                frame,
                text=f"No se pudo renderizar la vista previa.\n{exc}",
                fg=Theme.ERR_COLOR,
                bg=Theme.PANEL,
                padx=24,
                pady=24,
            ).pack()

        btns = tk.Frame(self, bg=Theme.BG)
        btns.pack(fill=tk.X, padx=16, pady=14)
        secondary_button(btns, "Cancelar", self.destroy).pack(side=tk.RIGHT)
        tk.Button(
            btns,
            text="IMPRIMIR",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=Theme.BTN_BG,
            activeforeground="#ffffff",
            activebackground=Theme.BTN_ACTIVE,
            relief=tk.FLAT,
            padx=22,
            pady=8,
            cursor="hand2",
            command=self._imprimir,
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _center(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _imprimir(self) -> None:
        try:
            imprimir_etiqueta(self.datos)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Imprimir", str(exc), parent=self)
            return
        if self.on_printed:
            self.on_printed()
        self.destroy()
