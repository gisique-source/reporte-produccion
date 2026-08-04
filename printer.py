"""
Fachada de impresión. La lógica vive en print_engine (Pillow + CreateBitmap).
"""

from __future__ import annotations

from print_engine import imprimir_etiqueta, render_etiqueta_a4

__all__ = ["imprimir_etiqueta", "render_etiqueta_a4"]
