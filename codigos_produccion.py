"""Códigos de producción / etiqueta (formato planta Extrusora)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Union

from catalog import CatalogoMaestros, normalizar_maestro

NumberLike = Union[str, int, float]


def _entero(valor: NumberLike) -> int:
    s = str(valor or "").strip().replace(",", ".")
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        digits = re.sub(r"\D", "", s)
        return int(digits) if digits else 0


def _pad3(valor: NumberLike) -> str:
    """Tres dígitos con ceros a la izquierda (Dn, Corte)."""
    return f"{_entero(valor):03d}"


def _fardo_3(valor: NumberLike) -> str:
    """Últimos 3 dígitos del Nº fardo (0093 → 093)."""
    n = _entero(valor)
    return f"{n:03d}"[-3:]


def codigo_color_desde_nombre(color: str) -> str:
    """Extrae código numérico del maestro Color (ej. Marrón 580 → 580)."""
    nums = re.findall(r"\d+", color or "")
    if not nums:
        return "000"
    return nums[-1].zfill(3)[-3:]


def resolver_codigo_color(
    color: str,
    catalogo: Optional[CatalogoMaestros] = None,
) -> str:
    """Prefiere código del catálogo maestro; si no, el número en el nombre."""
    nombre = (color or "").strip()
    if catalogo and nombre:
        clave = normalizar_maestro(nombre)
        for m in catalogo.listar("color", solo_activos=False):
            if normalizar_maestro(m.valor) == clave:
                cod = (m.codigo or "").strip()
                if cod.isdigit():
                    return cod.zfill(3)[-3:]
                if cod:
                    nums = re.findall(r"\d+", cod)
                    if nums:
                        return nums[-1].zfill(3)[-3:]
    return codigo_color_desde_nombre(nombre)


def codigo_bloque_producto(
    *,
    beteado: NumberLike = 1,
    color: str,
    corte: NumberLike,
    dn: NumberLike,
    catalogo: Optional[CatalogoMaestros] = None,
) -> str:
    """
    Primer bloque del código largo: 1 + código color + corte + Td.
    Ej.: 1 + 580 + 064 + 005 = 1580064005
    """
    pref = str(int(_entero(beteado) or 1))
    cc = resolver_codigo_color(color, catalogo)
    return f"{pref}{cc}{_pad3(corte)}{_pad3(dn)}"


def codigo_principal(
    anio: int,
    mes: int,
    nro_fardo: NumberLike,
) -> str:
    """
    Código principal AAMMFff: año (2) + mes (2) + fardo (3).
    Ej.: 2026-01 fardo 93 → 2601093
    """
    yy = anio % 100
    mm = f"{mes:02d}"
    fff = _fardo_3(nro_fardo)
    return f"{yy:02d}{mm}{fff}"


def codigo_neto_texto(peso_neto: NumberLike) -> str:
    """Peso neto con 2 decimales (332.20)."""
    return f"{float(peso_neto):.2f}"


def codigo_largo(
    *,
    anio: int,
    mes: int,
    nro_fardo: NumberLike,
    color: str,
    corte: NumberLike,
    dn: NumberLike,
    peso_neto: NumberLike,
    beteado: NumberLike = 1,
    catalogo: Optional[CatalogoMaestros] = None,
) -> str:
    """Cadena completa: bloque producto + principal + neto."""
    z = codigo_bloque_producto(
        beteado=beteado,
        color=color,
        corte=corte,
        dn=dn,
        catalogo=catalogo,
    )
    aa = codigo_principal(anio, mes, nro_fardo)
    ab = codigo_neto_texto(peso_neto)
    return f"{z} {aa} {ab}"


def periodo_desde_fecha_hora(fecha_hora: str) -> tuple[int, int]:
    try:
        dt = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M:%S")
        return dt.year, dt.month
    except ValueError:
        if len(fecha_hora) >= 7:
            try:
                return int(fecha_hora[:4]), int(fecha_hora[5:7])
            except ValueError:
                pass
    hoy = date.today()
    return hoy.year, hoy.month


def codigos_desde_registro(
    reg,
    *,
    catalogo: Optional[CatalogoMaestros] = None,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
) -> dict[str, str]:
    """Calcula principal, largo y bloques para un RegistroPesaje / DatosEtiqueta."""
    if anio is None or mes is None:
        fh = getattr(reg, "fecha_hora_registro", None) or getattr(reg, "fecha_hora", "")
        anio, mes = periodo_desde_fecha_hora(fh or "")

    principal = codigo_principal(anio, mes, reg.nro_fardo)
    bloque_z = codigo_bloque_producto(
        beteado=getattr(reg, "beteado", 1),
        color=reg.color,
        corte=reg.corte,
        dn=getattr(reg, "denier", None) or getattr(reg, "dn", ""),
        catalogo=catalogo,
    )
    neto_txt = codigo_neto_texto(reg.peso_neto)
    largo = f"{bloque_z} {principal} {neto_txt}"

    return {
        "principal": principal,
        "largo": largo,
        "bloque_z": bloque_z,
        "color_codigo": resolver_codigo_color(reg.color, catalogo),
        "fardo_3": _fardo_3(reg.nro_fardo),
        "dn_3": _pad3(getattr(reg, "denier", None) or getattr(reg, "dn", "")),
        "corte_3": _pad3(reg.corte),
        "neto": neto_txt,
    }
