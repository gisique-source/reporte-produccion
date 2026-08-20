"""Valida filas de importación contra SQLite (nuevos / modificar / ya subidos)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from bulk_import import FilaImport, normalizar_texto
from models import RegistroPesaje

_PESO_TOL = 0.05  # kg — tolerancia por redondeo Excel


class EstadoImport(str, Enum):
    NUEVO = "nuevo"
    MODIFICAR = "modificar"
    YA_SUBIDO = "ya_subido"
    FALTANTE = "faltante"
    ERROR = "error"


@dataclass
class FilaValidada:
    dia: date
    fila: FilaImport
    estado: EstadoImport
    registro_id: Optional[int] = None
    campos_diff: list[str] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        if self.estado == EstadoImport.NUEVO:
            return "Nuevo"
        if self.estado == EstadoImport.MODIFICAR:
            extra = f" ({', '.join(self.campos_diff[:3])})" if self.campos_diff else ""
            return f"Modificar{extra}"
        if self.estado == EstadoImport.YA_SUBIDO:
            return "Ya subido"
        if self.estado == EstadoImport.FALTANTE:
            return "Nuevo maestro"
        return "Error"

    @property
    def es_pendiente(self) -> bool:
        """Filas que aún hay que insertar o actualizar."""
        return self.estado in (
            EstadoImport.NUEVO,
            EstadoImport.MODIFICAR,
            EstadoImport.FALTANTE,
            EstadoImport.ERROR,
        )

    @property
    def se_puede_aplicar(self) -> bool:
        return self.estado in (EstadoImport.NUEVO, EstadoImport.MODIFICAR)


def _nro_clave(nro: str) -> str:
    n = str(nro or "").strip()
    if n.isdigit():
        return str(int(n))
    return n


def _txt_eq(a: str, b: str) -> bool:
    return normalizar_texto(a) == normalizar_texto(b)


def _num_eq(a: float, b: float, tol: float = _PESO_TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def comparar_fila_con_registro(
    fila: FilaImport, reg: RegistroPesaje, *, dia: Optional[date] = None
) -> list[str]:
    """
    Campos que no coinciden (fila completa de producción).
    Vacío = fila ya subida idéntica.
    """
    diffs: list[str] = []
    cli = fila.cliente_ok or fila.cliente
    col = fila.color_ok or fila.color
    dn = fila.dn_ok or fila.dn
    corte = fila.corte_ok or fila.corte
    op = fila.operario_ok or fila.operario

    if not _txt_eq(cli, reg.cliente):
        diffs.append("cliente")
    if not _txt_eq(fila.lote, reg.lote):
        diffs.append("lote")
    if not _txt_eq(col, reg.color):
        diffs.append("color")
    if not _txt_eq(dn, reg.denier):
        diffs.append("dn")
    if not _txt_eq(corte, reg.corte):
        diffs.append("corte")
    if _nro_clave(fila.nro_fardo) != _nro_clave(reg.nro_fardo):
        diffs.append("fardo")
    if not _num_eq(fila.peso_total, reg.peso_total):
        diffs.append("p.total")
    if not _num_eq(fila.tara_carreta, reg.tara_carreta):
        diffs.append("tara carr.")
    if not _num_eq(fila.tara_fardo, reg.tara_fardo):
        diffs.append("tara fardo")
    if not _num_eq(fila.peso_bruto, reg.peso_bruto):
        diffs.append("p.bruto")
    if not _num_eq(fila.peso_neto, reg.peso_neto):
        diffs.append("p.neto")
    if op and reg.operario and not _txt_eq(op, reg.operario):
        diffs.append("operario")
    elif op and not (reg.operario or "").strip():
        diffs.append("operario")
    elif (reg.operario or "").strip() and not (op or "").strip():
        diffs.append("operario")

    if dia is not None and (reg.fecha_hora or "")[:10]:
        try:
            reg_dia = date.fromisoformat(reg.fecha_hora[:10])
            if reg_dia != dia:
                diffs.append("fecha")
        except ValueError:
            pass

    return diffs


def validar_filas_importacion(
    pares: list[tuple[date, FilaImport]],
    buscar_registro,  # Callable[[str, str], Optional[RegistroPesaje]]
) -> list[FilaValidada]:
    """
    Clasifica cada fila Excel contra la DB local.
    ``buscar_registro(lote, nro_fardo)`` → RegistroPesaje | None
    """
    out: list[FilaValidada] = []
    for dia, fila in pares:
        if fila.errores:
            out.append(
                FilaValidada(dia=dia, fila=fila, estado=EstadoImport.ERROR)
            )
            continue
        if fila.tiene_faltantes:
            out.append(
                FilaValidada(dia=dia, fila=fila, estado=EstadoImport.FALTANTE)
            )
            continue

        reg = buscar_registro(fila.lote, fila.nro_fardo)
        if reg is None:
            out.append(
                FilaValidada(dia=dia, fila=fila, estado=EstadoImport.NUEVO)
            )
            continue

        diffs = comparar_fila_con_registro(fila, reg, dia=dia)
        if not diffs:
            out.append(
                FilaValidada(
                    dia=dia,
                    fila=fila,
                    estado=EstadoImport.YA_SUBIDO,
                    registro_id=reg.id,
                )
            )
        else:
            out.append(
                FilaValidada(
                    dia=dia,
                    fila=fila,
                    estado=EstadoImport.MODIFICAR,
                    registro_id=reg.id,
                    campos_diff=diffs,
                )
            )
    return out


def resumir_validacion(items: list[FilaValidada]) -> dict[str, int]:
    return {
        "nuevo": sum(1 for i in items if i.estado == EstadoImport.NUEVO),
        "modificar": sum(1 for i in items if i.estado == EstadoImport.MODIFICAR),
        "ya_subido": sum(1 for i in items if i.estado == EstadoImport.YA_SUBIDO),
        "faltante": sum(1 for i in items if i.estado == EstadoImport.FALTANTE),
        "error": sum(1 for i in items if i.estado == EstadoImport.ERROR),
    }
