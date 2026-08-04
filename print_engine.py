"""
Motor de impresión: render Pillow (A4 300 DPI) + Device Context Windows.

Evita win32ui.CreateSolidBrush / pens: la etiqueta se dibuja en imagen
y se transfiere al DC con CreateBitmap + BitBlt / ImageWin.Dib.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont, ImageWin

from config import (
    DIRECCION,
    EMAIL,
    EMPRESA,
    LABEL_HEIGHT_MM,
    LABEL_LINE_RGB,
    LABEL_ORIGIN_X_MM,
    LABEL_ORIGIN_Y_MM,
    LABEL_TEXT_RGB,
    LABEL_WIDTH_MM,
    MARGIN_LEFT_MM,
    MARGIN_TOP_MM,
    PAGE_HEIGHT_MM,
    PAGE_WIDTH_MM,
    PRODUCTO,
    TELEFONO,
    WEB,
)

if TYPE_CHECKING:
    from models import DatosEtiqueta

try:
    import win32con
    import win32print
    import win32ui
except ImportError:  # pragma: no cover
    win32con = None  # type: ignore
    win32print = None  # type: ignore
    win32ui = None  # type: ignore

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
except ImportError:  # pragma: no cover
    Code128 = None  # type: ignore
    ImageWriter = None  # type: ignore

# A4 @ 300 DPI
PRINT_DPI = 300
PAGE_W_PX = 2480  # round(210 / 25.4 * 300)
PAGE_H_PX = 3508  # round(297 / 25.4 * 300)


def _mm_to_px(mm: float, dpi: int = PRINT_DPI) -> int:
    return int(round(mm * dpi / 25.4))


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf", "arialbd.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_barcode(payload: str, max_width: int, height: int) -> Image.Image:
    """Code128 con python-barcode → imagen Pillow."""
    text = payload or "-"
    if Code128 is None or ImageWriter is None:
        # Fallback mínimo: rectángulo con texto
        img = Image.new("RGB", (max_width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, max_width - 1, height - 1), outline="black")
        draw.text((8, height // 3), text, fill="black", font=_font(18))
        return img

    buf = io.BytesIO()
    options = {
        "module_width": 0.35,
        "module_height": max(height * 25.4 / PRINT_DPI * 0.7, 8.0),
        "quiet_zone": 1.5,
        "font_size": 10,
        "text_distance": 3,
        "write_text": True,
        "dpi": PRINT_DPI,
    }
    Code128(text, writer=ImageWriter()).write(buf, options=options)
    buf.seek(0)
    bc = Image.open(buf).convert("RGB")
    if bc.width > max_width or bc.height > height:
        bc = bc.resize(
            (
                min(bc.width, max_width),
                min(bc.height, height),
            ),
            Image.Resampling.LANCZOS,
        )
    canvas = Image.new("RGB", (max_width, height), "white")
    x = (max_width - bc.width) // 2
    y = (height - bc.height) // 2
    canvas.paste(bc, (x, y))
    return canvas


def render_etiqueta_a4(datos: "DatosEtiqueta") -> Image.Image:
    """
    Renderiza página A4 2480×3508 (300 DPI).
    Etiqueta en esquina superior izquierda: margen 15 mm / 11 mm (P52:Y72).
    """
    assert abs(PAGE_W_PX - _mm_to_px(PAGE_WIDTH_MM)) <= 2
    assert abs(PAGE_H_PX - _mm_to_px(PAGE_HEIGHT_MM)) <= 2

    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "white")
    draw = ImageDraw.Draw(img)

    ox = _mm_to_px(LABEL_ORIGIN_X_MM)  # 11 mm
    oy = _mm_to_px(LABEL_ORIGIN_Y_MM)  # 15 mm
    w = _mm_to_px(LABEL_WIDTH_MM)
    h = _mm_to_px(LABEL_HEIGHT_MM)
    line = LABEL_LINE_RGB
    text_c = LABEL_TEXT_RGB

    def x_frac(f: float) -> int:
        return ox + int(w * f)

    def y_frac(f: float) -> int:
        return oy + int(h * f)

    def line_h(y: int, width: int = 3) -> None:
        draw.line((ox, y, ox + w, y), fill=line, width=width)

    def line_v(x: int, y1: int, y2: int, width: int = 3) -> None:
        draw.line((x, y1, x, y2), fill=line, width=width)

    def text(
        value: str,
        x: int,
        y: int,
        *,
        size: int = 28,
        bold: bool = False,
        fill=text_c,
    ) -> None:
        draw.text((x, y), value, font=_font(size, bold=bold), fill=fill)

    def cell(
        label: str,
        value: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        unit: str = "",
        value_size: int = 36,
    ) -> None:
        pad = 10
        text(label, x1 + pad, y1 + pad, size=22, bold=True)
        mid_y = y1 + (y2 - y1) // 2 - 4
        text(value, x1 + pad, mid_y, size=value_size, bold=True)
        if unit:
            tw = draw.textlength(unit, font=_font(20))
            text(unit, x2 - int(tw) - pad, y2 - 34, size=20)

    # Marco
    draw.rectangle((ox, oy, ox + w, oy + h), outline=line, width=4)

    # Encabezado
    y_header = y_frac(0.22)
    line_h(y_header)
    text(EMPRESA, ox + 14, oy + 12, size=48, bold=True)
    text(PRODUCTO, ox + 14, oy + 70, size=24)
    right = x_frac(0.50)
    text(DIRECCION, right, oy + 14, size=16)
    text(f"Tel: {TELEFONO}", right, oy + 42, size=16)
    text(EMAIL, right, oy + 68, size=16)
    text(WEB, right, oy + 94, size=16)

    # Color | Cliente
    y2 = y_frac(0.42)
    mid = x_frac(0.45)
    line_h(y2)
    line_v(mid, y_header, y2)
    cell("Color:", datos.color, ox, y_header, mid, y2)
    cell("Cliente:", datos.cliente, mid, y_header, ox + w, y2)

    # Lote | Dn | Corte
    y3 = y_frac(0.62)
    c1, c2 = x_frac(0.33), x_frac(0.60)
    line_h(y3)
    line_v(c1, y2, y3)
    line_v(c2, y2, y3)
    cell("Lote:", datos.lote, ox, y2, c1, y3)
    cell("Dn:", datos.dn, c1, y2, c2, y3)
    cell("Corte:", datos.corte, c2, y2, ox + w, y3, unit="mm")

    # Nº Fardo | Fecha | P.Bruto | P.Neto
    y4 = y_frac(0.82)
    d1, d2, d3 = x_frac(0.25), x_frac(0.48), x_frac(0.72)
    line_h(y4)
    line_v(d1, y3, y4)
    line_v(d2, y3, y4)
    line_v(d3, y3, y4)
    cell("Nº Fardo", datos.nro_fardo, ox, y3, d1, y4, value_size=30)
    cell("Fecha", datos.fecha, d1, y3, d2, y4, value_size=26)
    cell("P.Bruto", f"{datos.peso_bruto:.1f}", d2, y3, d3, y4, unit="kg", value_size=30)
    cell("P.Neto", f"{datos.peso_neto:.1f}", d3, y3, ox + w, y4, unit="kg", value_size=30)

    # Código de barras
    bc_pad = 24
    bc_h = max(oy + h - (y4 + 16) - 12, 80)
    barcode = _render_barcode(
        datos.codigo_barras,
        max_width=w - 2 * bc_pad,
        height=bc_h,
    )
    img.paste(barcode, (ox + bc_pad, y4 + 16))

    # Metadatos de página (márgenes documentados)
    _ = (MARGIN_TOP_MM, MARGIN_LEFT_MM)
    return img


def _blit_image_to_dc(hdc, image: Image.Image) -> None:
    """
    Transfiere la imagen Pillow al DC de impresora con CreateBitmap
    (sin CreateSolidBrush / pens nativos).
    """
    horz = hdc.GetDeviceCaps(win32con.HORZRES)
    vert = hdc.GetDeviceCaps(win32con.VERTRES)
    if horz <= 0 or vert <= 0:
        horz, vert = PAGE_W_PX, PAGE_H_PX

    rgb = image.convert("RGB")
    if rgb.size != (horz, vert):
        rgb = rgb.resize((horz, vert), Image.Resampling.LANCZOS)

    # Bitmap compatible + Dib → BitBlt al DC de impresora
    mem_dc = hdc.CreateCompatibleDC()
    try:
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, horz, vert)
        old = mem_dc.SelectObject(bmp)
        try:
            dib = ImageWin.Dib(rgb)
            dib.draw(mem_dc.GetHandleOutput(), (0, 0, horz, vert))
            hdc.BitBlt((0, 0), (horz, vert), mem_dc, (0, 0), win32con.SRCCOPY)
        finally:
            mem_dc.SelectObject(old)
            try:
                bmp.DeleteObject()
            except Exception:  # noqa: BLE001
                pass
    finally:
        mem_dc.DeleteDC()


def imprimir_etiqueta(datos: "DatosEtiqueta") -> None:
    """Renderiza A4 en Pillow e imprime en la impresora predeterminada."""
    if win32print is None or win32ui is None or win32con is None:
        raise RuntimeError(
            "pywin32 no está disponible. Instale con: pip install pywin32"
        )

    page = render_etiqueta_a4(datos)
    printer_name = win32print.GetDefaultPrinter()
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    try:
        hdc.StartDoc("Etiqueta Gexim")
        hdc.StartPage()
        try:
            _blit_image_to_dc(hdc, page)
        finally:
            hdc.EndPage()
            hdc.EndDoc()
    finally:
        hdc.DeleteDC()
