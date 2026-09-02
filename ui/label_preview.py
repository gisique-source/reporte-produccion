"""Vista previa de etiqueta (solo lectura) para Pesaje y modales."""

from __future__ import annotations

from typing import Optional

import tkinter as tk

from label_layout import get_layout
from models import DatosEtiqueta
from print_engine import render_etiqueta_region
from ui.widgets import Theme

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

# Misma escala que el editor de etiqueta: px por mm en pantalla.
PREVIEW_SCALE = 3.2


class LabelPreviewPanel(tk.Frame):
    """Renderiza la etiqueta tal como se imprimiría (sin controles de edición)."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        scale: float = PREVIEW_SCALE,
        title: str = "Vista previa de etiqueta",
    ) -> None:
        super().__init__(master, bg=Theme.PANEL, padx=10, pady=10)
        self._scale = scale
        self._photo = None
        self._job: Optional[str] = None
        self._last_datos: Optional[DatosEtiqueta] = None
        self._resize_job: Optional[str] = None

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
            text="Se actualiza al escribir · los campos vacíos muestran —",
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
        self._frame.bind("<Configure>", self._on_frame_configure)

    def _label_pixel_size(self) -> tuple[int, int]:
        layout = get_layout()
        return (
            max(1, int(layout.label_width_mm * self._scale)),
            max(1, int(layout.label_height_mm * self._scale)),
        )

    def schedule(self, datos: Optional[DatosEtiqueta], *, delay_ms: int = 180) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self._job = self.after(delay_ms, lambda: self._render(datos))

    def _on_frame_configure(self, event: tk.Event) -> None:
        if event.width < 40 or event.height < 40:
            return
        if self._last_datos is None:
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.after(120, lambda: self._render(self._last_datos))

    def _render(self, datos: Optional[DatosEtiqueta]) -> None:
        self._job = None
        self._resize_job = None
        self._last_datos = datos
        if datos is None or Image is None or ImageTk is None:
            self._photo = None
            self._lbl.configure(
                image="",
                text="Vista previa no disponible",
                fg=Theme.MUTED,
                bg="#ffffff",
                padx=24,
                pady=48,
            )
            return
        try:
            tw, th = self._label_pixel_size()
            img = render_etiqueta_region(
                datos,
                dpi=int(25.4 * self._scale),
                bg="white",
                show_guides=False,
            )
            img = img.resize((tw, th), Image.Resampling.LANCZOS)

            fw = self._frame.winfo_width()
            fh = self._frame.winfo_height()
            if fw > 40 and fh > 40:
                img = self._fit(img, fw - 2, fh - 2)

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
        if scale >= 0.999:
            return img
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        return img.resize((nw, nh), Image.Resampling.LANCZOS)
