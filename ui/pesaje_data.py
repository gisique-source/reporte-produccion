"""Recolección y validación de datos del formulario de pesaje rápido."""

from __future__ import annotations

from datetime import date
from typing import Optional

import tkinter as tk

from db import PesajeDatabase, format_fecha_editable
from models import DatosEtiqueta, RegistroPesaje
from ui.time_picker import combinar_fecha_hora, hora_etiqueta_12h, snap_hora_15
from utils import normalizar_lote, prefijo_lote


def lote_prefijo(anio: int) -> str:
    return prefijo_lote(anio)


def asegurar_prefijo_lote(var_lote: tk.StringVar, anio: int) -> None:
    cur = var_lote.get()
    pref = lote_prefijo(anio)
    if not cur.strip():
        var_lote.set(pref)
        return
    norm = normalizar_lote(cur, anio=anio)
    if norm:
        var_lote.set(norm)
    elif not cur.upper().replace(" ", "").startswith(pref.upper().replace(" ", "")):
        var_lote.set(pref + cur.strip())


def normalizar_lote_campo(var_lote: tk.StringVar, anio: int) -> None:
    cur = var_lote.get().strip()
    pref = lote_prefijo(anio)
    if not cur or cur.upper() == pref.strip().upper():
        var_lote.set(pref)
        return
    norm = normalizar_lote(cur, anio=anio)
    if norm:
        var_lote.set(norm)
    else:
        asegurar_prefijo_lote(var_lote, anio)


def copiar_ultimo_registro(
    last: RegistroPesaje,
    *,
    anio: int,
    var_cliente: tk.StringVar,
    var_lote: tk.StringVar,
    var_color: tk.StringVar,
    var_dn: tk.StringVar,
    var_corte: tk.StringVar,
    var_operario: tk.StringVar,
    var_tara_carreta: tk.StringVar,
    var_tara_fardo: tk.StringVar,
) -> None:
    var_cliente.set(last.cliente)
    lote = normalizar_lote(last.lote, anio=anio)
    var_lote.set(lote if lote else lote_prefijo(anio))
    var_color.set(last.color)
    var_dn.set(last.denier)
    var_corte.set(last.corte)
    var_operario.set(last.operario)
    if last.tara_carreta > 0:
        var_tara_carreta.set(f"{last.tara_carreta:.2f}")
    if last.tara_fardo > 0:
        var_tara_fardo.set(f"{last.tara_fardo:.2f}")


def recoger_datos_pesaje(
    *,
    fecha: date,
    peso_total: Optional[float],
    tara_carreta: float,
    tara_fardo: float,
    var_cliente: tk.StringVar,
    var_lote: tk.StringVar,
    var_color: tk.StringVar,
    var_dn: tk.StringVar,
    var_corte: tk.StringVar,
    var_operario: tk.StringVar,
    var_nro: tk.StringVar,
    var_hora: tk.StringVar,
    exigir_completo: bool = False,
) -> tuple[Optional[DatosEtiqueta], Optional[str]]:
    """Arma DatosEtiqueta. Retorna (datos, mensaje_error)."""
    if peso_total is None or peso_total <= 0:
        if exigir_completo:
            return None, "Sin peso en la báscula."
        return None, None

    bruto = max(peso_total - tara_carreta, 0.0)
    neto = max(peso_total - tara_carreta - tara_fardo, 0.0)

    for nombre, var in (
        ("Cliente", var_cliente),
        ("Color", var_color),
        ("Dn", var_dn),
        ("Corte", var_corte),
        ("Operario", var_operario),
    ):
        if not var.get().strip():
            if exigir_completo:
                return None, f"Complete: {nombre}"
            return None, None

    lote = normalizar_lote(var_lote.get(), anio=fecha.year)
    if not lote:
        if exigir_completo:
            return None, (
                f"Lote incompleto. Use {lote_prefijo(fecha.year).strip()} + número."
            )
        return None, None

    nro_txt = var_nro.get().strip()
    if not nro_txt.isdigit() or int(nro_txt) < 1:
        if exigir_completo:
            return None, "Nº Fardo inválido"
        return None, None

    hhmm = snap_hora_15(var_hora.get())
    fh = combinar_fecha_hora(fecha, hhmm)

    return (
        DatosEtiqueta(
            color=var_color.get().strip(),
            cliente=var_cliente.get().strip(),
            lote=lote,
            dn=var_dn.get().strip(),
            corte=var_corte.get().strip(),
            nro_fardo=str(int(nro_txt)),
            fecha=format_fecha_editable(fecha),
            peso_bruto=bruto,
            peso_neto=neto,
            operario=var_operario.get().strip(),
            peso_total=float(peso_total),
            tara_carreta=tara_carreta,
            tara_fardo=tara_fardo,
            hora=hora_etiqueta_12h(hhmm),
            fecha_hora_registro=fh,
        ),
        None,
    )


def proponer_nro_fardo(db: PesajeDatabase, modo: str, dia: date) -> int:
    return db.siguiente_nro_fardo(modo, dia=dia)
