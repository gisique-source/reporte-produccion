"""Vista previa de etiqueta (solo lectura) para Pesaje y modales."""

from __future__ import annotations

from typing import Optional

import tkinter as tk

from models import DatosEtiqueta
from print_engine import render_etiqueta_region
from ui.widgets import Theme

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageTk = None  # type: ignore


class LabelPreviewPanel(tk.Frame):
    """Renderiza la etiqueta tal como se imprimiría (sin controles de edición)."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        dpi: int = 130,
        max_w: int = 400,
        max_h: int = 340,
        title: str = "Vista previa de etiqueta",
    ) -> None:
        super().__init__(master, bg=Theme.PANEL, padx=10, pady=10)
        self._dpi = dpi
        self._max_w = max_w
        self._max_h = max_h
        self._photo = None
        self._job: Optional[str] = None

        tk.Label(
            self,
            text=title,
            font=("Segoe UI", 11, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            self,
            text="Así se verá al imprimir (solo valores)",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        self._frame = tk.Frame(self, bg=Theme.BORDER, padx=1, pady=1)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._lbl = tk.Label(
            self._frame,
            text="Complete los datos para ver la etiqueta",
            font=("Segoe UI", 10),
            fg=Theme.MUTED,
            bg="#ffffff",
            padx=24,
            pady=48,
            justify=tk.CENTER,
        )
        self._lbl.pack(fill=tk.BOTH, expand=True)

    def schedule(self, datos: Optional[DatosEtiqueta], *, delay_ms: int = 180) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self._job = self.after(delay_ms, lambda: self._render(datos))

    def _render(self, datos: Optional[DatosEtiqueta]) -> None:
        self._job = None
        if datos is None or Image is None or ImageTk is None:
            self._photo = None
            self._lbl.configure(
                image="",
                text="Complete los datos para ver la etiqueta",
                fg=Theme.MUTED,
                bg="#ffffff",
                padx=24,
                pady=48,
            )
            return
        try:
            img = render_etiqueta_region(
                datos, dpi=self._dpi, bg="white", show_guides=False
            )
            img = self._fit(img, self._max_w, self._max_h)
            self._photo = ImageTk.PhotoImage(img)
            self._lbl.configure(
                image=self._photo,
                text="",
                bg="#ffffff",
                padx=0,
                pady=0,
            )
        except Exception as exc:  # noqa: BLE001
            self._photo = None
            self._lbl.configure(
                image="",
                text=f"No se pudo generar la vista previa.\n{exc}",
                fg=Theme.ERR_COLOR,
                bg=Theme.PANEL,
                padx=16,
                pady=16,
            )

    @staticmethod
    def _fit(img: "Image.Image", max_w: int, max_h: int) -> "Image.Image":
        w, h = img.size
        if w <= 0 or h <= 0:
            return img
        scale = min(max_w / w, max_h / h, 1.0)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        if (nw, nh) == (w, h):
            return img
        return img.resize((nw, nh), Image.Resampling.LANCZOS)
