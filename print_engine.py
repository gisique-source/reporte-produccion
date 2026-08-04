"""
Motor de impresión: render Pillow (A4 300 DPI) + Device Context Windows.

Solo imprime valores variables según etiqueta_layout.json (sin marcos,
sin rótulos de atributos ni datos de empresa — van en la etiqueta preimpresa).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageDraw, ImageFont, ImageWin

from config import PAGE_HEIGHT_MM, PAGE_WIDTH_MM
from label_layout import LabelLayout, get_layout

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

PRINT_DPI = 300
PAGE_W_PX = 2480
PAGE_H_PX = 3508

# font_size del layout está en puntos tipográficos (como en Word/el editor).
# Pillow pide píxeles: px = pt * dpi / 72.
_FONT_FILES: dict[str, tuple[str, str]] = {
    # clave normalizada → (regular, bold)
    "arial": ("arial.ttf", "arialbd.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf"),
    "segoeui": ("segoeui.ttf", "segoeuib.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf"),
}


def _mm_to_px(mm: float, dpi: int = PRINT_DPI) -> int:
    return int(round(mm * dpi / 25.4))


def _pt_to_px(points: float, dpi: int = PRINT_DPI) -> int:
    """Convierte puntos tipográficos a píxeles según el DPI del render."""
    return max(8, int(round(float(points) * dpi / 72.0)))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = (color or "#000000").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 0, 0, 0


def _fonts_dirs() -> list[Path]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    dirs = [Path(windir) / "Fonts"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return dirs


def _font(
    size_pt: int,
    *,
    bold: bool = False,
    font_name: str = "Arial",
    dpi: int = PRINT_DPI,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carga TTF desde Windows\\Fonts. size_pt = puntos del editor/layout."""
    size_px = _pt_to_px(size_pt, dpi)
    key = (font_name or "Arial").replace(" ", "").lower()
    regular, bold_file = _FONT_FILES.get(key, (f"{key}.ttf", f"{key}bd.ttf"))
    names = [bold_file, regular] if bold else [regular, bold_file]
    # Fallbacks seguros
    names.extend(["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf", "arialbd.ttf"])

    candidates: list[str] = []
    for name in names:
        candidates.append(name)
        for folder in _fonts_dirs():
            candidates.append(str(folder / name))

    seen: set[str] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            continue
    # Último recurso: bitmap minúsculo (solo si no hay ninguna TTF)
    return ImageFont.load_default()


def _render_barcode(payload: str, max_width: int, height: int) -> Image.Image:
    text = payload or "-"
    if Code128 is None or ImageWriter is None:
        img = Image.new("RGB", (max_width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.text(
            (8, max(0, height // 3)),
            text,
            fill="black",
            font=_font(14, dpi=PRINT_DPI),
        )
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
            (min(bc.width, max_width), min(bc.height, height)),
            Image.Resampling.LANCZOS,
        )
    canvas = Image.new("RGB", (max_width, height), "white")
    x = (max_width - bc.width) // 2
    y = (height - bc.height) // 2
    canvas.paste(bc, (x, y))
    return canvas


def _valor_campo(datos: "DatosEtiqueta", field_id: str) -> str:
    if field_id == "color":
        return datos.color
    if field_id == "cliente":
        return datos.cliente
    if field_id == "lote":
        return datos.lote
    if field_id == "dn":
        return datos.dn
    if field_id == "corte":
        return datos.corte
    if field_id == "nro_fardo":
        return str(datos.nro_fardo)
    if field_id == "fecha":
        return datos.fecha
    if field_id == "peso_bruto":
        return f"{datos.peso_bruto:.1f}"
    if field_id == "peso_neto":
        return f"{datos.peso_neto:.1f}"
    if field_id == "operario":
        return datos.operario
    if field_id == "hora":
        return datos.hora
    if field_id == "peso_total":
        return f"{datos.peso_total:.1f}" if datos.peso_total else ""
    if field_id == "barcode":
        return datos.codigo_barras
    return ""


def render_etiqueta_region(
    datos: "DatosEtiqueta",
    layout: Optional[LabelLayout] = None,
    *,
    dpi: int = PRINT_DPI,
    bg: str = "white",
    show_guides: bool = False,
) -> Image.Image:
    """
    Renderiza solo el área de la etiqueta (valores según layout).
    show_guides=True dibuja recuadros punteados (solo preview del editor).
    """
    layout = layout or get_layout()
    w = _mm_to_px(layout.label_width_mm, dpi)
    h = _mm_to_px(layout.label_height_mm, dpi)
    img = Image.new("RGB", (max(w, 1), max(h, 1)), bg)
    draw = ImageDraw.Draw(img)

    if show_guides:
        draw.rectangle((0, 0, w - 1, h - 1), outline=(180, 180, 180), width=1)

    for fld in layout.fields:
        if not fld.visible:
            continue
        fld.clamp(layout.label_width_mm, layout.label_height_mm)
        x = _mm_to_px(fld.x_mm, dpi)
        y = _mm_to_px(fld.y_mm, dpi)
        bw = max(_mm_to_px(fld.w_mm, dpi), 1)
        bh = max(_mm_to_px(fld.h_mm, dpi), 1)
        fill = _hex_to_rgb(fld.color)

        if show_guides:
            draw.rectangle((x, y, x + bw, y + bh), outline=(200, 200, 220), width=1)

        if fld.id == "barcode":
            bc = _render_barcode(_valor_campo(datos, "barcode"), bw, bh)
            img.paste(bc, (x, y))
            continue

        value = _valor_campo(datos, fld.id)
        if not value:
            continue
        font = _font(
            fld.font_size,
            bold=fld.bold,
            font_name=fld.font_name,
            dpi=dpi,
        )
        # Ajuste vertical centrado aproximado
        bbox = draw.textbbox((0, 0), value, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if fld.align == "center":
            tx = x + max((bw - tw) // 2, 0)
        elif fld.align == "right":
            tx = x + max(bw - tw - 2, 0)
        else:
            tx = x + 2
        ty = y + max((bh - th) // 2, 0)
        # fill= color RGB del layout (hex del editor)
        draw.text((tx, ty), value, font=font, fill=fill)

    return img


def render_etiqueta_a4(
    datos: "DatosEtiqueta",
    layout: Optional[LabelLayout] = None,
) -> Image.Image:
    """Página A4 2480×3508 (300 DPI) con la etiqueta en el origen configurado."""
    layout = layout or get_layout()
    page = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "white")
    label = render_etiqueta_region(datos, layout, dpi=PRINT_DPI, bg="white", show_guides=False)
    ox = _mm_to_px(layout.origin_x_mm)
    oy = _mm_to_px(layout.origin_y_mm)
    page.paste(label, (ox, oy))
    _ = (PAGE_WIDTH_MM, PAGE_HEIGHT_MM)
    return page


def _blit_image_to_dc(hdc, image: Image.Image) -> None:
    horz = hdc.GetDeviceCaps(win32con.HORZRES)
    vert = hdc.GetDeviceCaps(win32con.VERTRES)
    if horz <= 0 or vert <= 0:
        horz, vert = PAGE_W_PX, PAGE_H_PX

    rgb = image.convert("RGB")
    if rgb.size != (horz, vert):
        rgb = rgb.resize((horz, vert), Image.Resampling.LANCZOS)

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
    """Renderiza A4 según layout e imprime en la impresora predeterminada."""
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
