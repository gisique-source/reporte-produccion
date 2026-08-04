"""Persistencia del historial de subidas sync → API nube."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from models import RegistroAuditoriaSync

SCHEMA_SYNC_AUDITORIA = """
CREATE TABLE IF NOT EXISTS sync_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enviado_en TEXT NOT NULL,
    pesaje_id INTEGER NOT NULL,
    id_remoto TEXT NOT NULL DEFAULT '',
    http_status INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 0,
    duplicado INTEGER NOT NULL DEFAULT 0,
    planta TEXT NOT NULL DEFAULT '',
    nro_fardo TEXT NOT NULL DEFAULT '',
    lote TEXT NOT NULL DEFAULT '',
    cliente TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    peso_bruto REAL NOT NULL DEFAULT 0,
    peso_neto REAL NOT NULL DEFAULT 0,
    fecha_hora_pesaje TEXT NOT NULL DEFAULT '',
    mensaje TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sync_aud_enviado ON sync_auditoria(enviado_en DESC);
CREATE INDEX IF NOT EXISTS idx_sync_aud_pesaje ON sync_auditoria(pesaje_id);
CREATE INDEX IF NOT EXISTS idx_sync_aud_ok ON sync_auditoria(ok);
"""


class SyncAuditMixin:
    """Métodos de auditoría; requiere _lock y _connect en la clase base."""

    def registrar_auditoria_sync(
        self,
        *,
        pesaje_id: int,
        ok: bool,
        http_status: int = 0,
        id_remoto: str = "",
        duplicado: bool = False,
        planta: str = "",
        nro_fardo: str = "",
        lote: str = "",
        cliente: str = "",
        color: str = "",
        peso_bruto: float = 0.0,
        peso_neto: float = 0.0,
        fecha_hora_pesaje: str = "",
        mensaje: str = "",
        url: str = "",
        enviado_en: Optional[str] = None,
    ) -> int:
        fh = enviado_en or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                cur = conn.execute(
                    """
                    INSERT INTO sync_auditoria (
                        enviado_en, pesaje_id, id_remoto, http_status, ok, duplicado,
                        planta, nro_fardo, lote, cliente, color,
                        peso_bruto, peso_neto, fecha_hora_pesaje, mensaje, url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fh,
                        pesaje_id,
                        id_remoto or "",
                        int(http_status),
                        1 if ok else 0,
                        1 if duplicado else 0,
                        planta or "",
                        nro_fardo or "",
                        lote or "",
                        cliente or "",
                        color or "",
                        float(peso_bruto),
                        float(peso_neto),
                        fecha_hora_pesaje or "",
                        (mensaje or "")[:500],
                        url or "",
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

    def auditoria_sync(
        self,
        *,
        limite: int = 500,
        solo_ok: Optional[bool] = None,
        desde: Optional[str] = None,
        hasta: Optional[str] = None,
        texto: str = "",
    ) -> list[RegistroAuditoriaSync]:
        sql = ["SELECT * FROM sync_auditoria WHERE 1=1"]
        params: list[object] = []
        if solo_ok is True:
            sql.append("AND ok = 1")
        elif solo_ok is False:
            sql.append("AND ok = 0")
        if desde:
            sql.append("AND enviado_en >= ?")
            params.append(desde if " " in desde else f"{desde} 00:00:00")
        if hasta:
            sql.append("AND enviado_en <= ?")
            params.append(hasta if " " in hasta else f"{hasta} 23:59:59")
        q = (texto or "").strip()
        if q:
            like = f"%{q}%"
            sql.append(
                "AND (nro_fardo LIKE ? OR lote LIKE ? OR cliente LIKE ? "
                "OR color LIKE ? OR id_remoto LIKE ? OR CAST(pesaje_id AS TEXT) LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
        sql.append("ORDER BY id DESC LIMIT ?")
        params.append(int(limite))
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                rows = conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_auditoria(r) for r in rows]

    def contar_auditoria_sync(self) -> tuple[int, int]:
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n,
                           COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok_n
                    FROM sync_auditoria
                    """
                ).fetchone()
        return int(row["n"]), int(row["ok_n"])


def _row_to_auditoria(row: sqlite3.Row) -> RegistroAuditoriaSync:
    return RegistroAuditoriaSync(
        id=int(row["id"]),
        enviado_en=str(row["enviado_en"]),
        pesaje_id=int(row["pesaje_id"]),
        id_remoto=str(row["id_remoto"] or ""),
        http_status=int(row["http_status"] or 0),
        ok=int(row["ok"] or 0),
        duplicado=int(row["duplicado"] or 0),
        planta=str(row["planta"] or ""),
        nro_fardo=str(row["nro_fardo"] or ""),
        lote=str(row["lote"] or ""),
        cliente=str(row["cliente"] or ""),
        color=str(row["color"] or ""),
        peso_bruto=float(row["peso_bruto"] or 0),
        peso_neto=float(row["peso_neto"] or 0),
        fecha_hora_pesaje=str(row["fecha_hora_pesaje"] or ""),
        mensaje=str(row["mensaje"] or ""),
        url=str(row["url"] or ""),
    )
