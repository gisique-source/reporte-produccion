"""Auditoría de altas y ediciones de pesajes en Hoja de cálculo."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional

from models import DatosEtiqueta, RegistroAuditoriaPesaje, RegistroPesaje

SCHEMA_PESAJE_AUDITORIA = """
CREATE TABLE IF NOT EXISTS pesaje_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado_en TEXT NOT NULL,
    pesaje_id INTEGER NOT NULL,
    accion TEXT NOT NULL,
    campo TEXT NOT NULL DEFAULT '',
    valor_anterior TEXT NOT NULL DEFAULT '',
    valor_nuevo TEXT NOT NULL DEFAULT '',
    nro_fardo TEXT NOT NULL DEFAULT '',
    operario TEXT NOT NULL DEFAULT '',
    detalle TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pesaje_aud_creado ON pesaje_auditoria(creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_pesaje_aud_pesaje ON pesaje_auditoria(pesaje_id);
"""

_CAMPOS = (
    ("nro_fardo", "Fardo"),
    ("cliente", "Cliente"),
    ("lote", "Lote"),
    ("color", "Color"),
    ("denier", "Dn"),
    ("corte", "Corte"),
    ("operario", "Operario"),
    ("peso_total", "P.Total"),
    ("tara_carreta", "Tara Carr."),
    ("tara_fardo", "Tara Fardo"),
    ("peso_bruto", "P.Bruto"),
    ("peso_neto", "P.Neto"),
)


def _campo(obj: Any, key: str) -> str:
    if key == "denier":
        val = getattr(obj, "denier", None)
        if val is None:
            val = getattr(obj, "dn", "")
    else:
        val = getattr(obj, key, "")
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val or "")


def snapshot(obj: DatosEtiqueta | RegistroPesaje) -> dict[str, str]:
    return {key: _campo(obj, key) for key, _label in _CAMPOS}


def diff_cambios(
    antes: Optional[dict[str, str]], despues: dict[str, str]
) -> list[tuple[str, str, str, str]]:
    """Lista (campo, etiqueta, anterior, nuevo) de valores distintos."""
    out: list[tuple[str, str, str, str]] = []
    base = antes or {}
    for key, label in _CAMPOS:
        a = base.get(key, "")
        b = despues.get(key, "")
        if a != b:
            out.append((key, label, a, b))
    return out


class PesajeAuditMixin:
    """Métodos de auditoría de hoja; requiere _lock y _connect."""

    def registrar_auditoria_pesaje(
        self,
        *,
        pesaje_id: int,
        accion: str,
        campo: str = "",
        valor_anterior: str = "",
        valor_nuevo: str = "",
        nro_fardo: str = "",
        operario: str = "",
        detalle: str = "",
        creado_en: Optional[str] = None,
    ) -> int:
        fh = creado_en or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                cur = conn.execute(
                    """
                    INSERT INTO pesaje_auditoria (
                        creado_en, pesaje_id, accion, campo,
                        valor_anterior, valor_nuevo, nro_fardo, operario, detalle
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fh,
                        pesaje_id,
                        accion,
                        campo or "",
                        valor_anterior or "",
                        valor_nuevo or "",
                        nro_fardo or "",
                        operario or "",
                        (detalle or "")[:800],
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

    def auditar_guardado_pesaje(
        self,
        *,
        pesaje_id: int,
        accion: str,
        datos: DatosEtiqueta,
        anterior: Optional[RegistroPesaje] = None,
    ) -> None:
        despues = snapshot(datos)
        cambios = diff_cambios(snapshot(anterior) if anterior else None, despues)
        if accion == "crear":
            detalle = " · ".join(
                f"{label} {despues[key]}" for key, label in _CAMPOS if despues.get(key)
            )
            self.registrar_auditoria_pesaje(
                pesaje_id=pesaje_id,
                accion="crear",
                nro_fardo=datos.nro_fardo,
                operario=datos.operario,
                detalle=detalle or "Alta de fardo",
            )
            return
        if not cambios:
            self.registrar_auditoria_pesaje(
                pesaje_id=pesaje_id,
                accion="editar",
                nro_fardo=datos.nro_fardo,
                operario=datos.operario,
                detalle="Guardar sin cambios de campos",
            )
            return
        resumen = "; ".join(f"{lab}: {a} → {b}" for _k, lab, a, b in cambios)
        self.registrar_auditoria_pesaje(
            pesaje_id=pesaje_id,
            accion="editar",
            nro_fardo=datos.nro_fardo,
            operario=datos.operario,
            detalle=resumen,
        )
        for key, label, ant, nuevo in cambios:
            self.registrar_auditoria_pesaje(
                pesaje_id=pesaje_id,
                accion="editar",
                campo=label,
                valor_anterior=ant,
                valor_nuevo=nuevo,
                nro_fardo=datos.nro_fardo,
                operario=datos.operario,
                detalle=f"{label}: {ant} → {nuevo}",
            )

    def auditoria_pesaje(
        self, *, limite: int = 500, texto: str = ""
    ) -> list[RegistroAuditoriaPesaje]:
        sql = ["SELECT * FROM pesaje_auditoria WHERE 1=1"]
        params: list[object] = []
        q = (texto or "").strip()
        if q:
            like = f"%{q}%"
            sql.append(
                "AND (nro_fardo LIKE ? OR operario LIKE ? OR campo LIKE ? "
                "OR detalle LIKE ? OR CAST(pesaje_id AS TEXT) LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        sql.append("ORDER BY id DESC LIMIT ?")
        params.append(int(limite))
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                rows = conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_aud_pesaje(r) for r in rows]


def _row_to_aud_pesaje(row: sqlite3.Row) -> RegistroAuditoriaPesaje:
    return RegistroAuditoriaPesaje(
        id=int(row["id"]),
        creado_en=str(row["creado_en"]),
        pesaje_id=int(row["pesaje_id"]),
        accion=str(row["accion"]),
        campo=str(row["campo"] or ""),
        valor_anterior=str(row["valor_anterior"] or ""),
        valor_nuevo=str(row["valor_nuevo"] or ""),
        nro_fardo=str(row["nro_fardo"] or ""),
        operario=str(row["operario"] or ""),
        detalle=str(row["detalle"] or ""),
    )
