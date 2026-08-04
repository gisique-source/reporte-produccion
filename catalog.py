"""
Catálogo maestro: cliente, color, denier, corte mm.

Prohibido DELETE físico. Baja solo por soft-delete (activo = 0).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import Literal

from config import DB_PATH
from models import MaestroItem

MaestroTipo = Literal["cliente", "color", "denier", "corte"]

# tabla → columna de valor visible
_MAESTROS: dict[MaestroTipo, tuple[str, str]] = {
    "cliente": ("clientes", "nombre"),
    "color": ("colores", "nombre"),
    "denier": ("deniers", "valor"),
    "corte": ("cortes", "valor_mm"),
}

_SCHEMA_MAESTROS = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    codigo TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_nombre
    ON clientes(nombre) WHERE activo = 1;

CREATE TABLE IF NOT EXISTS colores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    codigo TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_colores_nombre
    ON colores(nombre) WHERE activo = 1;

CREATE TABLE IF NOT EXISTS deniers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor TEXT NOT NULL,
    codigo TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_deniers_valor
    ON deniers(valor) WHERE activo = 1;

CREATE TABLE IF NOT EXISTS cortes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor_mm TEXT NOT NULL,
    codigo TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cortes_valor
    ON cortes(valor_mm) WHERE activo = 1;
"""

_SEEDS: dict[MaestroTipo, list[str]] = {
    "cliente": ["Catalina Peru SAC"],
    "color": ["Marron 580"],
    "denier": ["4.0"],
    "corte": ["65"],
}

ETIQUETAS: dict[MaestroTipo, str] = {
    "cliente": "Cliente",
    "color": "Color",
    "denier": "Denier (Dn)",
    "corte": "Corte (mm)",
}


class CatalogoError(Exception):
    pass


class CatalogoMaestros:
    """CRUD de maestros con soft-delete. Nunca ejecuta DELETE."""

    def __init__(self, path: str = DB_PATH, lock: threading.Lock | None = None) -> None:
        self.path = path
        self._lock = lock or threading.Lock()
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA_MAESTROS)
                self._seed_if_empty(conn)

    def _seed_if_empty(self, conn: sqlite3.Connection) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tipo, valores in _SEEDS.items():
            tabla, col = _MAESTROS[tipo]
            n = conn.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]
            if int(n) > 0:
                continue
            for v in valores:
                conn.execute(
                    f"""
                    INSERT INTO {tabla} ({col}, codigo, activo, creado_en, actualizado_en)
                    VALUES (?, '', 1, ?, ?)
                    """,
                    (v, now, now),
                )
        conn.commit()

    def listar(self, tipo: MaestroTipo, *, solo_activos: bool = True) -> list[MaestroItem]:
        tabla, col = _MAESTROS[tipo]
        where = "WHERE activo = 1" if solo_activos else ""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT id, {col} AS valor, codigo, activo
                    FROM {tabla}
                    {where}
                    ORDER BY {col} COLLATE NOCASE ASC
                    """
                ).fetchall()
        return [
            MaestroItem(
                id=int(r["id"]),
                valor=str(r["valor"]),
                activo=int(r["activo"]),
                codigo=str(r["codigo"] or ""),
            )
            for r in rows
        ]

    def valores_activos(self, tipo: MaestroTipo) -> list[str]:
        return [m.valor for m in self.listar(tipo, solo_activos=True)]

    def crear(self, tipo: MaestroTipo, valor: str, codigo: str = "") -> int:
        valor = valor.strip()
        if not valor:
            raise CatalogoError("El valor no puede estar vacío.")
        tabla, col = _MAESTROS[tipo]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                # Si existe inactivo con mismo nombre → reactivar
                row = conn.execute(
                    f"SELECT id, activo FROM {tabla} WHERE {col} = ? COLLATE NOCASE",
                    (valor,),
                ).fetchone()
                if row:
                    if int(row["activo"]) == 1:
                        raise CatalogoError(f"Ya existe: {valor}")
                    conn.execute(
                        f"""
                        UPDATE {tabla}
                        SET activo = 1, codigo = ?, actualizado_en = ?
                        WHERE id = ?
                        """,
                        (codigo.strip(), now, int(row["id"])),
                    )
                    conn.commit()
                    return int(row["id"])
                cur = conn.execute(
                    f"""
                    INSERT INTO {tabla} ({col}, codigo, activo, creado_en, actualizado_en)
                    VALUES (?, ?, 1, ?, ?)
                    """,
                    (valor, codigo.strip(), now, now),
                )
                conn.commit()
                return int(cur.lastrowid)

    def actualizar(self, tipo: MaestroTipo, item_id: int, valor: str, codigo: str = "") -> None:
        valor = valor.strip()
        if not valor:
            raise CatalogoError("El valor no puede estar vacío.")
        tabla, col = _MAESTROS[tipo]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                dup = conn.execute(
                    f"""
                    SELECT id FROM {tabla}
                    WHERE {col} = ? COLLATE NOCASE AND id != ? AND activo = 1
                    """,
                    (valor, item_id),
                ).fetchone()
                if dup:
                    raise CatalogoError(f"Ya existe: {valor}")
                cur = conn.execute(
                    f"""
                    UPDATE {tabla}
                    SET {col} = ?, codigo = ?, actualizado_en = ?
                    WHERE id = ?
                    """,
                    (valor, codigo.strip(), now, item_id),
                )
                if cur.rowcount == 0:
                    raise CatalogoError("Registro no encontrado.")
                conn.commit()

    def desactivar(self, tipo: MaestroTipo, item_id: int) -> None:
        """Soft-delete: activo = 0. Prohibido borrar filas."""
        tabla, _ = _MAESTROS[tipo]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    f"""
                    UPDATE {tabla}
                    SET activo = 0, actualizado_en = ?
                    WHERE id = ? AND activo = 1
                    """,
                    (now, item_id),
                )
                if cur.rowcount == 0:
                    raise CatalogoError("Registro no encontrado o ya inactivo.")
                conn.commit()

    def reactivar(self, tipo: MaestroTipo, item_id: int) -> None:
        tabla, _ = _MAESTROS[tipo]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    f"""
                    UPDATE {tabla}
                    SET activo = 1, actualizado_en = ?
                    WHERE id = ? AND activo = 0
                    """,
                    (now, item_id),
                )
                if cur.rowcount == 0:
                    raise CatalogoError("Registro no encontrado o ya activo.")
                conn.commit()

    def eliminar(self, *_args, **_kwargs) -> None:
        """Bloqueado a propósito: maestros no se eliminan."""
        raise CatalogoError(
            "Prohibido eliminar maestros. Use desactivar (soft-delete)."
        )
