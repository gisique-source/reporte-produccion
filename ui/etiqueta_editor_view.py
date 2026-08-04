"""
Editor visual de etiqueta: previsualización, arrastre/redimensionado de
valores, tipografía (fuente, tamaño, negrita) y color de impresión.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Optional

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from db import format_fecha_editable
from label_layout import (
    FIELD_IDS,
    FIELD_LABELS,
    FieldLayout,
    LabelLayout,
    default_layout,
    load_layout,
    save_layout,
    set_active_layout,
)
from models import DatosEtiqueta
from print_engine import render_etiqueta_region
from ui.widgets import Theme, secondary_button, text_entry

try:
    from PIL import ImageTk
except ImportError:  # pragma: no cover
    ImageTk = None  # type: ignore

# Escala de la etiqueta en pantalla (px por mm)
_SCALE = 3.2
_HANDLE = 8


def _sample_datos() -> DatosEtiqueta:
    return DatosEtiqueta(
        color="Marron 580",
        cliente="Catalina Peru SAC",
        lote="L-DEMO-01",
        dn="4.0",
        corte="65",
        nro_fardo="12",
        fecha=format_fecha_editable(date.today()),
        peso_bruto=228.6,
        peso_neto=226.2,
        operario="DEMO",
        peso_total=349.6,
        tara_carreta=121.0,
        tara_fardo=2.4,
        hora="2:30 pm",
    )


class EtiquetaEditorView(tk.Frame):
    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, bg=Theme.BG)
        self.layout: LabelLayout = deepcopy(load_layout())
        self._selected: Optional[str] = None
        self._drag_mode: Optional[str] = None  # move | resize
        self._drag_start: tuple[float, float] = (0.0, 0.0)
        self._field_start: Optional[FieldLayout] = None
        self._photo = None
        self._dirty = False

        self.var_field = tk.StringVar()
        self.var_font = tk.StringVar(value="Arial")
        self.var_size = tk.StringVar(value="28")
        self.var_bold = tk.BooleanVar(value=True)
        self.var_color = tk.StringVar(value="#000000")
        self.var_align = tk.StringVar(value="left")
        self.var_visible = tk.BooleanVar(value=True)
        self.var_x = tk.StringVar()
        self.var_y = tk.StringVar()
        self.var_w = tk.StringVar()
        self.var_h = tk.StringVar()
        self.var_ox = tk.StringVar(value=f"{self.layout.origin_x_mm:.1f}")
        self.var_oy = tk.StringVar(value=f"{self.layout.origin_y_mm:.1f}")
        self.var_msg = tk.StringVar(
            value="Arrastre los recuadros · esquinas para redimensionar · solo se imprimen valores"
        )

        self._build()
        set_active_layout(self.layout)
        self._refresh_canvas()

    def _build(self) -> None:
        header = tk.Frame(self, bg=Theme.PANEL, padx=12, pady=10)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="EDITOR DE ETIQUETA",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.ACCENT,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Solo valores · la etiqueta física ya trae marcos, títulos y dirección",
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(side=tk.LEFT, padx=16)

        body = tk.Frame(self, bg=Theme.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Canvas preview
        left = tk.Frame(body, bg=Theme.PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(
            left,
            text="Vista previa (guías solo en pantalla)",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.FG,
            bg=Theme.PANEL,
        ).pack(anchor="w", padx=10, pady=(8, 0))

        self.canvas = tk.Canvas(left, bg="#e8e8e8", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)
        self.canvas.bind("<Configure>", lambda _e: self._refresh_canvas())

        # Props panel
        right = tk.Frame(body, bg=Theme.PANEL, padx=12, pady=10)
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            right, text="Campo", font=("Segoe UI", 9, "bold"), fg=Theme.MUTED, bg=Theme.PANEL
        ).pack(anchor="w")
        self.cb_field = ttk.Combobox(
            right,
            textvariable=self.var_field,
            values=[FIELD_LABELS[i] for i in FIELD_IDS],
            state="readonly",
            width=22,
        )
        self.cb_field.pack(fill=tk.X, pady=(0, 8))
        self.cb_field.bind("<<ComboboxSelected>>", self._on_pick_field)

        tk.Checkbutton(
            right,
            text="Visible al imprimir",
            variable=self.var_visible,
            command=self._apply_props,
            fg=Theme.FG,
            bg=Theme.PANEL,
            selectcolor=Theme.INPUT_BG,
            activebackground=Theme.PANEL,
        ).pack(anchor="w")

        self._prop_row(right, "Fuente", self.var_font)
        fonts = ("Arial", "Calibri", "Tahoma", "Verdana", "Segoe UI", "Consolas")
        self.cb_font = ttk.Combobox(
            right, textvariable=self.var_font, values=fonts, width=20
        )
        self.cb_font.pack(fill=tk.X, pady=(0, 6))
        self.cb_font.bind("<<ComboboxSelected>>", lambda _e: self._apply_props())

        row = tk.Frame(right, bg=Theme.PANEL)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text="Tamaño", fg=Theme.MUTED, bg=Theme.PANEL).pack(side=tk.LEFT)
        text_entry(row, self.var_size, 6).pack(side=tk.LEFT, padx=6)
        tk.Checkbutton(
            row,
            text="Negrita",
            variable=self.var_bold,
            command=self._apply_props,
            fg=Theme.FG,
            bg=Theme.PANEL,
            selectcolor=Theme.INPUT_BG,
            activebackground=Theme.PANEL,
        ).pack(side=tk.LEFT, padx=8)

        crow = tk.Frame(right, bg=Theme.PANEL)
        crow.pack(fill=tk.X, pady=4)
        tk.Label(crow, text="Color", fg=Theme.MUTED, bg=Theme.PANEL).pack(side=tk.LEFT)
        text_entry(crow, self.var_color, 10).pack(side=tk.LEFT, padx=6)
        secondary_button(crow, "Elegir…", self._pick_color).pack(side=tk.LEFT)

        tk.Label(
            right, text="Alineación", font=("Segoe UI", 9), fg=Theme.MUTED, bg=Theme.PANEL
        ).pack(anchor="w", pady=(8, 0))
        self.cb_align = ttk.Combobox(
            right,
            textvariable=self.var_align,
            values=("left", "center", "right"),
            state="readonly",
            width=12,
        )
        self.cb_align.pack(anchor="w", pady=(0, 6))
        self.cb_align.bind("<<ComboboxSelected>>", lambda _e: self._apply_props())

        grid = tk.Frame(right, bg=Theme.PANEL)
        grid.pack(fill=tk.X, pady=6)
        for i, (lab, var) in enumerate(
            (("X mm", self.var_x), ("Y mm", self.var_y), ("Ancho", self.var_w), ("Alto", self.var_h))
        ):
            tk.Label(grid, text=lab, fg=Theme.MUTED, bg=Theme.PANEL).grid(
                row=0, column=i, sticky="w", padx=2
            )
            text_entry(grid, var, 7).grid(row=1, column=i, padx=2)

        secondary_button(right, "Aplicar tipografía / tamaño", self._apply_props).pack(
            fill=tk.X, pady=(10, 4)
        )

        tk.Label(
            right,
            text="Origen en hoja A4 (mm)",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.MUTED,
            bg=Theme.PANEL,
        ).pack(anchor="w", pady=(12, 0))
        org = tk.Frame(right, bg=Theme.PANEL)
        org.pack(fill=tk.X, pady=4)
        tk.Label(org, text="Izq.", fg=Theme.MUTED, bg=Theme.PANEL).pack(side=tk.LEFT)
        text_entry(org, self.var_ox, 6).pack(side=tk.LEFT, padx=4)
        tk.Label(org, text="Arr.", fg=Theme.MUTED, bg=Theme.PANEL).pack(side=tk.LEFT)
        text_entry(org, self.var_oy, 6).pack(side=tk.LEFT, padx=4)

        secondary_button(right, "Guardar layout", self._guardar).pack(fill=tk.X, pady=(16, 4))
        secondary_button(right, "Restaurar defaults", self._reset).pack(fill=tk.X, pady=4)
        secondary_button(right, "Actualizar vista", self._refresh_canvas).pack(
            fill=tk.X, pady=4
        )

        tk.Label(
            self,
            textvariable=self.var_msg,
            font=("Segoe UI", 9),
            fg=Theme.MUTED,
            bg=Theme.BG,
        ).pack(pady=(0, 8))

        # Seleccionar primer campo
        self.var_field.set(FIELD_LABELS["color"])
        self._select_field("color")

    def _prop_row(self, parent, title: str, _var) -> None:
        tk.Label(
            parent, text=title, font=("Segoe UI", 9), fg=Theme.MUTED, bg=Theme.PANEL
        ).pack(anchor="w", pady=(8, 0))

    def _id_from_label(self, label: str) -> Optional[str]:
        for k, v in FIELD_LABELS.items():
            if v == label:
                return k
        return None

    def _on_pick_field(self, _event=None) -> None:
        fid = self._id_from_label(self.var_field.get())
        if fid:
            self._select_field(fid)
            self._refresh_canvas()

    def _select_field(self, field_id: str) -> None:
        self._selected = field_id
        fld = self.layout.field(field_id)
        if fld is None:
            return
        self.var_field.set(FIELD_LABELS.get(field_id, field_id))
        self.var_font.set(fld.font_name)
        self.var_size.set(str(fld.font_size))
        self.var_bold.set(fld.bold)
        self.var_color.set(fld.color)
        self.var_align.set(fld.align)
        self.var_visible.set(fld.visible)
        self.var_x.set(f"{fld.x_mm:.1f}")
        self.var_y.set(f"{fld.y_mm:.1f}")
        self.var_w.set(f"{fld.w_mm:.1f}")
        self.var_h.set(f"{fld.h_mm:.1f}")

    def _apply_props(self) -> None:
        if not self._selected:
            return
        fld = self.layout.field(self._selected)
        if fld is None:
            return
        try:
            fld.font_size = int(float(self.var_size.get().replace(",", ".")))
        except ValueError:
            messagebox.showwarning("Etiqueta", "Tamaño de fuente inválido.")
            return
        try:
            fld.x_mm = float(self.var_x.get().replace(",", "."))
            fld.y_mm = float(self.var_y.get().replace(",", "."))
            fld.w_mm = float(self.var_w.get().replace(",", "."))
            fld.h_mm = float(self.var_h.get().replace(",", "."))
            self.layout.origin_x_mm = float(self.var_ox.get().replace(",", "."))
            self.layout.origin_y_mm = float(self.var_oy.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Etiqueta", "Coordenadas inválidas.")
            return
        fld.font_name = self.var_font.get().strip() or "Arial"
        fld.bold = bool(self.var_bold.get())
        fld.color = self.var_color.get().strip() or "#000000"
        fld.align = self.var_align.get() or "left"
        fld.visible = bool(self.var_visible.get())
        fld.clamp(self.layout.label_width_mm, self.layout.label_height_mm)
        set_active_layout(self.layout)
        self._dirty = True
        self._select_field(fld.id)
        self._refresh_canvas()
        self.var_msg.set(f"Actualizado: {FIELD_LABELS.get(fld.id, fld.id)}")

    def _pick_color(self) -> None:
        rgb, hx = colorchooser.askcolor(
            color=self.var_color.get() or "#000000", title="Color de impresión"
        )
        if hx:
            self.var_color.set(hx)
            self._apply_props()

    def _mm_to_canvas(self, mm: float) -> float:
        return mm * _SCALE

    def _canvas_to_mm(self, px: float) -> float:
        return px / _SCALE

    def _label_offset(self) -> tuple[float, float]:
        cw = self.canvas.winfo_width() or 400
        ch = self.canvas.winfo_height() or 300
        lw = self._mm_to_canvas(self.layout.label_width_mm)
        lh = self._mm_to_canvas(self.layout.label_height_mm)
        return max((cw - lw) / 2, 10), max((ch - lh) / 2, 10)

    def _refresh_canvas(self) -> None:
        if ImageTk is None:
            return
        self.canvas.delete("all")
        ox, oy = self._label_offset()
        lw = self._mm_to_canvas(self.layout.label_width_mm)
        lh = self._mm_to_canvas(self.layout.label_height_mm)

        # Sombra / papel
        self.canvas.create_rectangle(
            ox + 4, oy + 4, ox + lw + 4, oy + lh + 4, fill="#c0c0c0", outline=""
        )
        self.canvas.create_rectangle(
            ox, oy, ox + lw, oy + lh, fill="white", outline="#666", width=1
        )

        # Preview render
        try:
            img = render_etiqueta_region(
                _sample_datos(),
                self.layout,
                dpi=int(25.4 * _SCALE),
                bg="white",
                show_guides=False,
            )
            img = img.resize((int(lw), int(lh)))
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(ox, oy, image=self._photo, anchor="nw")
        except Exception:  # noqa: BLE001
            pass

        # Interactive boxes
        for fld in self.layout.fields:
            if not fld.visible and fld.id != self._selected:
                continue
            x1 = ox + self._mm_to_canvas(fld.x_mm)
            y1 = oy + self._mm_to_canvas(fld.y_mm)
            x2 = x1 + self._mm_to_canvas(fld.w_mm)
            y2 = y1 + self._mm_to_canvas(fld.h_mm)
            selected = fld.id == self._selected
            color = Theme.ACCENT if selected else "#888888"
            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline=color,
                width=2 if selected else 1,
                dash=(4, 3),
                tags=("field", fld.id),
            )
            self.canvas.create_text(
                x1 + 4,
                y1 + 2,
                text=FIELD_LABELS.get(fld.id, fld.id),
                anchor="nw",
                fill=color,
                font=("Segoe UI", 7),
                tags=("field", fld.id),
            )
            if selected:
                # Handle esquina inferior derecha
                self.canvas.create_rectangle(
                    x2 - _HANDLE,
                    y2 - _HANDLE,
                    x2,
                    y2,
                    fill=Theme.ACCENT,
                    outline="white",
                    tags=("handle", fld.id),
                )

    def _hit_field(self, cx: float, cy: float) -> tuple[Optional[str], Optional[str]]:
        """Retorna (field_id, mode) mode=resize|move."""
        ox, oy = self._label_offset()
        # Preferir seleccionado para resize
        if self._selected:
            fld = self.layout.field(self._selected)
            if fld:
                x2 = ox + self._mm_to_canvas(fld.x_mm + fld.w_mm)
                y2 = oy + self._mm_to_canvas(fld.y_mm + fld.h_mm)
                if x2 - _HANDLE <= cx <= x2 + 2 and y2 - _HANDLE <= cy <= y2 + 2:
                    return fld.id, "resize"
        # De atrás hacia adelante (último = encima)
        for fld in reversed(self.layout.fields):
            if not fld.visible and fld.id != self._selected:
                continue
            x1 = ox + self._mm_to_canvas(fld.x_mm)
            y1 = oy + self._mm_to_canvas(fld.y_mm)
            x2 = x1 + self._mm_to_canvas(fld.w_mm)
            y2 = y1 + self._mm_to_canvas(fld.h_mm)
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                if x2 - _HANDLE <= cx and y2 - _HANDLE <= cy:
                    return fld.id, "resize"
                return fld.id, "move"
        return None, None

    def _on_down(self, event) -> None:
        fid, mode = self._hit_field(event.x, event.y)
        if not fid:
            return
        self._select_field(fid)
        self._drag_mode = mode
        self._drag_start = (event.x, event.y)
        self._field_start = deepcopy(self.layout.field(fid))
        self._refresh_canvas()

    def _on_drag(self, event) -> None:
        if not self._selected or not self._drag_mode or self._field_start is None:
            return
        fld = self.layout.field(self._selected)
        if fld is None:
            return
        dx = self._canvas_to_mm(event.x - self._drag_start[0])
        dy = self._canvas_to_mm(event.y - self._drag_start[1])
        if self._drag_mode == "move":
            fld.x_mm = self._field_start.x_mm + dx
            fld.y_mm = self._field_start.y_mm + dy
        else:
            fld.w_mm = self._field_start.w_mm + dx
            fld.h_mm = self._field_start.h_mm + dy
        fld.clamp(self.layout.label_width_mm, self.layout.label_height_mm)
        set_active_layout(self.layout)
        self._dirty = True
        self._select_field(fld.id)
        self._refresh_canvas()

    def _on_up(self, _event=None) -> None:
        self._drag_mode = None
        self._field_start = None
        if self._dirty:
            set_active_layout(self.layout)

    def _guardar(self) -> None:
        self._apply_props()
        save_layout(self.layout)
        self._dirty = False
        self.var_msg.set("Layout guardado · se usará en la próxima impresión")
        messagebox.showinfo("Etiqueta", "Diseño de etiqueta guardado.")

    def _reset(self) -> None:
        if not messagebox.askyesno(
            "Etiqueta", "¿Restaurar posiciones y tipografías por defecto?"
        ):
            return
        self.layout = default_layout()
        self.var_ox.set(f"{self.layout.origin_x_mm:.1f}")
        self.var_oy.set(f"{self.layout.origin_y_mm:.1f}")
        set_active_layout(self.layout)
        self._select_field(self._selected or "color")
        self._dirty = True
        self._refresh_canvas()
