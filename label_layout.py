"""
Layout editable de la etiqueta (posiciones, tipografía, color).

La etiqueta física preimpresa ya trae marcos, rótulos y datos de empresa;
aquí solo se definen los valores variables a sobreimprimir.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from config import (
    LABEL_HEIGHT_MM,
    LABEL_ORIGIN_X_MM,
    LABEL_ORIGIN_Y_MM,
    LABEL_WIDTH_MM,
    _APP_DIR,
)

LAYOUT_PATH = os.path.join(_APP_DIR, "etiqueta_layout.json")

# Campos variables que se pueden colocar en la etiqueta
FIELD_IDS: tuple[str, ...] = (
    "color",
    "cliente",
    "lote",
    "dn",
    "corte",
    "nro_fardo",
    "fecha",
    "peso_bruto",
    "peso_neto",
    "operario",
    "hora",
    "peso_total",
    "barcode",
)

FIELD_LABELS: dict[str, str] = {
    "color": "Color",
    "cliente": "Cliente",
    "lote": "Lote",
    "dn": "Dn",
    "corte": "Corte",
    "nro_fardo": "Nº Fardo",
    "fecha": "Fecha",
    "peso_bruto": "P.Bruto",
    "peso_neto": "P.Neto",
    "operario": "Operario",
    "hora": "Hora",
    "peso_total": "P.Total",
    "barcode": "Código de barras",
}


@dataclass
class FieldLayout:
    id: str
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    font_name: str = "Arial"
    font_size: int = 28
    bold: bool = True
    color: str = "#000000"
    align: str = "left"  # left | center | right
    visible: bool = True

    def clamp(self, label_w: float, label_h: float) -> None:
        self.w_mm = max(8.0, min(self.w_mm, label_w))
        self.h_mm = max(4.0, min(self.h_mm, label_h))
        self.x_mm = max(0.0, min(self.x_mm, label_w - self.w_mm))
        self.y_mm = max(0.0, min(self.y_mm, label_h - self.h_mm))
        self.font_size = max(8, min(int(self.font_size), 120))


@dataclass
class LabelLayout:
    label_width_mm: float = LABEL_WIDTH_MM
    label_height_mm: float = LABEL_HEIGHT_MM
    origin_x_mm: float = LABEL_ORIGIN_X_MM
    origin_y_mm: float = LABEL_ORIGIN_Y_MM
    fields: list[FieldLayout] = field(default_factory=list)

    def field(self, field_id: str) -> Optional[FieldLayout]:
        for f in self.fields:
            if f.id == field_id:
                return f
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_width_mm": self.label_width_mm,
            "label_height_mm": self.label_height_mm,
            "origin_x_mm": self.origin_x_mm,
            "origin_y_mm": self.origin_y_mm,
            "fields": [asdict(f) for f in self.fields],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabelLayout":
        fields = []
        for raw in data.get("fields", []):
            fid = str(raw.get("id", ""))
            if fid not in FIELD_IDS:
                continue
            fields.append(
                FieldLayout(
                    id=fid,
                    x_mm=float(raw.get("x_mm", 0)),
                    y_mm=float(raw.get("y_mm", 0)),
                    w_mm=float(raw.get("w_mm", 30)),
                    h_mm=float(raw.get("h_mm", 12)),
                    font_name=str(raw.get("font_name", "Arial")),
                    font_size=int(raw.get("font_size", 28)),
                    bold=bool(raw.get("bold", True)),
                    color=str(raw.get("color", "#000000")),
                    align=str(raw.get("align", "left")),
                    visible=bool(raw.get("visible", True)),
                )
            )
        layout = cls(
            label_width_mm=float(data.get("label_width_mm", LABEL_WIDTH_MM)),
            label_height_mm=float(data.get("label_height_mm", LABEL_HEIGHT_MM)),
            origin_x_mm=float(data.get("origin_x_mm", LABEL_ORIGIN_X_MM)),
            origin_y_mm=float(data.get("origin_y_mm", LABEL_ORIGIN_Y_MM)),
            fields=fields,
        )
        for f in layout.fields:
            f.clamp(layout.label_width_mm, layout.label_height_mm)
        return layout


def default_layout() -> LabelLayout:
    """
    Posiciones iniciales aproximadas sobre la etiqueta preimpresa
    (solo valores; sin marcos ni títulos).
    """
    w, h = LABEL_WIDTH_MM, LABEL_HEIGHT_MM
    fields = [
        FieldLayout("color", 4, 26, w * 0.42, 18, font_size=32, bold=True),
        FieldLayout("cliente", w * 0.46, 26, w * 0.50, 18, font_size=30, bold=True),
        FieldLayout("lote", 4, 48, w * 0.30, 16, font_size=28, bold=True),
        FieldLayout("dn", w * 0.34, 48, w * 0.24, 16, font_size=28, bold=True),
        FieldLayout("corte", w * 0.62, 48, w * 0.34, 16, font_size=28, bold=True),
        FieldLayout("nro_fardo", 4, 68, w * 0.22, 16, font_size=28, bold=True),
        FieldLayout("fecha", w * 0.26, 68, w * 0.22, 16, font_size=24, bold=True),
        FieldLayout("peso_bruto", w * 0.50, 68, w * 0.22, 16, font_size=28, bold=True),
        FieldLayout("peso_neto", w * 0.74, 68, w * 0.24, 16, font_size=28, bold=True),
        FieldLayout("operario", 4, 88, w * 0.40, 10, font_size=18, bold=False),
        FieldLayout("hora", w * 0.46, 88, w * 0.24, 10, font_size=16, bold=False, visible=False),
        FieldLayout("peso_total", w * 0.72, 88, w * 0.24, 10, font_size=16, bold=False, visible=False),
        FieldLayout("barcode", 8, 96, w - 16, h - 100, font_size=12, bold=False),
    ]
    return LabelLayout(fields=fields)


_cached: Optional[LabelLayout] = None


def load_layout(path: str = LAYOUT_PATH) -> LabelLayout:
    global _cached
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            _cached = LabelLayout.from_dict(data)
            # Asegurar campos nuevos del default
            base = default_layout()
            have = {f.id for f in _cached.fields}
            for f in base.fields:
                if f.id not in have:
                    _cached.fields.append(deepcopy(f))
            return _cached
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    _cached = default_layout()
    return _cached


def save_layout(layout: LabelLayout, path: str = LAYOUT_PATH) -> None:
    global _cached
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(layout.to_dict(), fh, indent=2, ensure_ascii=False)
    _cached = layout


def get_layout() -> LabelLayout:
    return load_layout() if _cached is None else _cached


def invalidate_layout_cache() -> None:
    global _cached
    _cached = None
