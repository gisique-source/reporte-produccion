"""SQLite local de paradas de máquina (cola hacia Nexus Ops)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parada_local (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_remoto TEXT,
    maquinaria_codigo TEXT NOT NULL,
    maquinaria_nombre TEXT NOT NULL DEFAULT '',
    parte_codigo TEXT NOT NULL DEFAULT '',
    parte_nombre TEXT NOT NULL DEFAULT '',
    tipo_codigo TEXT NOT NULL,
    tipo_nombre TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT '',
    detalle_otro TEXT NOT NULL DEFAULT '',
    inicio TEXT NOT NULL,
    fin TEXT,
    turno TEXT NOT NULL DEFAULT '',
    operario TEXT NOT NULL DEFAULT '',
    observaciones TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    sync_estado TEXT NOT NULL DEFAULT 'pendiente',
    sync_error TEXT NOT NULL DEFAULT '',
    sync_http INTEGER NOT NULL DEFAULT 0,
    clasificada INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parada_maquina (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT '',
    planta TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS parada_parte (
    maquinaria_codigo TEXT NOT NULL,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    parent_codigo TEXT NOT NULL DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (maquinaria_codigo, codigo)
);
CREATE TABLE IF NOT EXISTS parada_tipo (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class ParadaLocal:
    id: int
    maquinaria_codigo: str
    maquinaria_nombre: str
    parte_codigo: str
    parte_nombre: str
    tipo_codigo: str
    tipo_nombre: str
    categoria: str
    detalle_otro: str
    inicio: str
    fin: Optional[str]
    turno: str
    operario: str
    observaciones: str
    activo: int
    sync_estado: str
    sync_error: str
    sync_http: int
    clasificada: int = 0
    id_remoto: str = ""

    @property
    def abierta(self) -> bool:
        return self.activo == 1 and not (self.fin or "").strip()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_parada(row: sqlite3.Row) -> ParadaLocal:
    return ParadaLocal(
        id=int(row["id"]),
        id_remoto=str(row["id_remoto"] or ""),
        maquinaria_codigo=str(row["maquinaria_codigo"] or ""),
        maquinaria_nombre=str(row["maquinaria_nombre"] or ""),
        parte_codigo=str(row["parte_codigo"] or ""),
        parte_nombre=str(row["parte_nombre"] or ""),
        tipo_codigo=str(row["tipo_codigo"] or ""),
        tipo_nombre=str(row["tipo_nombre"] or ""),
        categoria=str(row["categoria"] or ""),
        detalle_otro=str(row["detalle_otro"] or ""),
        inicio=str(row["inicio"] or ""),
        fin=str(row["fin"]) if row["fin"] else None,
        turno=str(row["turno"] or ""),
        operario=str(row["operario"] or ""),
        observaciones=str(row["observaciones"] or ""),
        activo=int(row["activo"] or 0),
        sync_estado=str(row["sync_estado"] or ""),
        sync_error=str(row["sync_error"] or ""),
        sync_http=int(row["sync_http"] or 0),
        clasificada=int(row["clasificada"] or 0) if "clasificada" in row.keys() else 0,
    )


class ParadasStore:
    def __init__(self, db: Any) -> None:
        self.db = db
        self._ensure()

    def _ensure(self) -> None:
        with self.db._lock:
            with self.db._connect() as conn:
                conn.executescript(_SCHEMA)
                cols = {
                    str(r[1])
                    for r in conn.execute("PRAGMA table_info(parada_local)")
                }
                if "clasificada" not in cols:
                    conn.execute(
                        "ALTER TABLE parada_local "
                        "ADD COLUMN clasificada INTEGER NOT NULL DEFAULT 0"
                    )
                conn.commit()

    def reemplazar_catalogo(
        self,
        maquinaria: list[dict],
        tipos: list[dict],
    ) -> None:
        with self.db._lock:
            with self.db._connect() as conn:
                conn.execute("DELETE FROM parada_parte")
                conn.execute("DELETE FROM parada_maquina")
                conn.execute("DELETE FROM parada_tipo")
                for m in maquinaria:
                    codigo = str(m.get("codigo") or "").strip()
                    if not codigo:
                        continue
                    conn.execute(
                        """
                        INSERT INTO parada_maquina
                        (codigo, nombre, descripcion, area, estado, planta)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            codigo,
                            str(m.get("nombre") or codigo),
                            str(m.get("descripcion") or ""),
                            str(m.get("area") or ""),
                            str(m.get("estado") or ""),
                            str(m.get("planta") or ""),
                        ),
                    )
                    self._insert_partes(conn, codigo, m.get("partes") or [], "")
                for t in tipos:
                    codigo = str(t.get("codigo") or "").strip()
                    if not codigo:
                        continue
                    conn.execute(
                        """
                        INSERT INTO parada_tipo
                        (codigo, nombre, categoria, descripcion, orden)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            codigo,
                            str(t.get("nombre") or codigo),
                            str(t.get("categoria") or ""),
                            str(t.get("descripcion") or ""),
                            int(t.get("orden") or 0),
                        ),
                    )
                conn.commit()

    @staticmethod
    def _insert_partes(
        conn: sqlite3.Connection,
        maquina: str,
        nodos: list,
        parent: str,
    ) -> None:
        for nodo in nodos:
            if not isinstance(nodo, dict):
                continue
            codigo = str(nodo.get("codigo") or "").strip()
            if not codigo:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO parada_parte
                (maquinaria_codigo, codigo, nombre, parent_codigo, orden)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    maquina,
                    codigo,
                    str(nodo.get("nombre") or codigo),
                    parent,
                    int(nodo.get("orden") or 0),
                ),
            )
            hijos = nodo.get("hijos") or []
            if isinstance(hijos, list):
                ParadasStore._insert_partes(conn, maquina, hijos, codigo)

    def maquinas(self) -> list[dict]:
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM parada_maquina ORDER BY nombre"
                ).fetchall()
        return [dict(r) for r in rows]

    def partes(self, maquinaria_codigo: str) -> list[dict]:
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM parada_parte
                    WHERE maquinaria_codigo = ?
                    ORDER BY orden, nombre
                    """,
                    (maquinaria_codigo,),
                ).fetchall()
        return [dict(r) for r in rows]

    def tipos(self) -> list[dict]:
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM parada_tipo ORDER BY orden, nombre"
                ).fetchall()
        return [dict(r) for r in rows]

    def abierta(self) -> Optional[ParadaLocal]:
        with self.db._lock:
            with self.db._connect() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM parada_local
                    WHERE activo = 1 AND (fin IS NULL OR fin = '')
                    ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
        return _row_parada(row) if row else None

    def obtener(self, parada_id: int) -> Optional[ParadaLocal]:
        with self.db._lock:
            with self.db._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM parada_local WHERE id = ?", (parada_id,)
                ).fetchone()
        return _row_parada(row) if row else None

    def listar_periodo(self, desde: date, hasta: date) -> list[ParadaLocal]:
        ini = desde.isoformat()
        fin = hasta.isoformat()
        if fin < ini:
            ini, fin = fin, ini
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM parada_local
                    WHERE substr(inicio, 1, 10) >= ?
                      AND substr(inicio, 1, 10) <= ?
                    ORDER BY inicio DESC, id DESC
                    """,
                    (ini, fin),
                ).fetchall()
        return [_row_parada(r) for r in rows]

    def listar(self, limite: int = 200) -> list[ParadaLocal]:
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM parada_local ORDER BY id DESC LIMIT ?",
                    (limite,),
                ).fetchall()
        return [_row_parada(r) for r in rows]

    def pendientes(self) -> list[ParadaLocal]:
        with self.db._lock:
            with self.db._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM parada_local
                    WHERE sync_estado = 'pendiente'
                    ORDER BY id ASC
                    """
                ).fetchall()
        return [_row_parada(r) for r in rows]

    def insertar(self, datos: dict) -> int:
        ahora = _now()
        with self.db._lock:
            with self.db._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO parada_local (
                        maquinaria_codigo, maquinaria_nombre, parte_codigo, parte_nombre,
                        tipo_codigo, tipo_nombre, categoria, detalle_otro, inicio, fin,
                        turno, operario, observaciones, activo, sync_estado, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 1, 'pendiente', ?)
                    """,
                    (
                        datos.get("maquinaria_codigo") or "",
                        datos.get("maquinaria_nombre") or "",
                        datos.get("parte_codigo") or "",
                        datos.get("parte_nombre") or "",
                        datos.get("tipo_codigo") or "",
                        datos.get("tipo_nombre") or "",
                        datos.get("categoria") or "",
                        datos.get("detalle_otro") or "",
                        datos["inicio"],
                        datos.get("turno") or "",
                        datos.get("operario") or "",
                        datos.get("observaciones") or "",
                        ahora,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

    def cerrar(self, parada_id: int, fin: str) -> None:
        with self.db._lock:
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE parada_local
                    SET fin = ?, sync_estado = 'pendiente', sync_error = '', updated_at = ?
                    WHERE id = ?
                    """,
                    (fin, _now(), parada_id),
                )
                conn.commit()

    def aplicar_clasificacion(self, item: dict) -> None:
        """Copia máquina/tipo que el especialista puso en la nube. No toca la cola."""
        raw_id = item.get("id_local")
        if raw_id in (None, ""):
            return
        try:
            parada_id = int(raw_id)
        except (TypeError, ValueError):
            return

        def texto(clave: str) -> str:
            valor = item.get(clave)
            return "" if valor is None else str(valor).strip()

        clasificada = 1 if item.get("clasificada") else 0
        fin_nube = texto("fin")
        with self.db._lock:
            with self.db._connect() as conn:
                row = conn.execute(
                    "SELECT fin, sync_estado FROM parada_local WHERE id = ?",
                    (parada_id,),
                ).fetchone()
                if row is None:
                    return
                fin_local = str(row["fin"] or "")
                adoptar_fin = (
                    str(row["sync_estado"] or "") == "ok"
                    and fin_nube
                    and not fin_local
                )
                conn.execute(
                    """
                    UPDATE parada_local
                    SET maquinaria_codigo = ?, maquinaria_nombre = ?,
                        parte_codigo = ?, parte_nombre = ?,
                        tipo_codigo = ?, tipo_nombre = ?,
                        categoria = ?, detalle_otro = ?,
                        clasificada = ?,
                        id_remoto = CASE WHEN ? != '' THEN ? ELSE id_remoto END,
                        fin = CASE WHEN ? = 1 THEN ? ELSE fin END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        texto("maquinaria_codigo"),
                        texto("maquinaria_nombre"),
                        texto("parte_codigo"),
                        texto("parte_nombre"),
                        texto("tipo_codigo"),
                        texto("tipo_nombre"),
                        texto("categoria") or "SIN_CLASIFICAR",
                        texto("detalle_otro"),
                        clasificada,
                        texto("id_remoto"),
                        texto("id_remoto"),
                        1 if adoptar_fin else 0,
                        fin_nube,
                        _now(),
                        parada_id,
                    ),
                )
                conn.commit()

    def descartar(self, parada_id: int) -> None:
        """Quita un alta local que la nube rechazó (p. ej. ya había otra abierta)."""
        with self.db._lock:
            with self.db._connect() as conn:
                conn.execute("DELETE FROM parada_local WHERE id = ?", (parada_id,))
                conn.commit()

    def marcar_sync(
        self,
        parada_id: int,
        *,
        ok: bool,
        http: int,
        id_remoto: str = "",
        error: str = "",
    ) -> None:
        with self.db._lock:
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE parada_local
                    SET sync_estado = ?, sync_http = ?, sync_error = ?,
                        id_remoto = CASE WHEN ? != '' THEN ? ELSE id_remoto END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "ok" if ok else "pendiente",
                        http,
                        "" if ok else error[:400],
                        id_remoto,
                        id_remoto,
                        _now(),
                        parada_id,
                    ),
                )
                conn.commit()
