"""
Catálogo maestro: cliente, color, denier, corte mm, operario.

Prohibido DELETE físico. Baja solo por soft-delete (activo = 0).
Permite fusionar duplicados (p. ej. Asencios / asencios) en un solo valor canónico.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from typing import Literal

from config import DB_PATH
from models import MaestroItem

MaestroTipo = Literal["cliente", "color", "denier", "corte", "operario"]

# tabla → columna de valor visible
_MAESTROS: dict[MaestroTipo, tuple[str, str]] = {
    "cliente": ("clientes", "nombre"),
    "color": ("colores", "nombre"),
    "denier": ("deniers", "valor"),
    "corte": ("cortes", "valor_mm"),
    "operario": ("operarios", "nombre"),
}

# Columna en pesajes que usa el valor del maestro (para fusionar historial)
_PESAJES_COL: dict[MaestroTipo, str] = {
    "cliente": "cliente",
    "color": "color",
    "denier": "denier",
    "corte": "corte",
    "operario": "operario",
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

CREATE TABLE IF NOT EXISTS operarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    codigo TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_operarios_nombre
    ON operarios(nombre) WHERE activo = 1;
"""

_SEEDS: dict[MaestroTipo, list[str]] = {
    "cliente": ["Catalina Peru SAC"],
    "color": ["Marron 580"],
    "denier": ["4.0"],
    "corte": ["65"],
    "operario": [],
}

ETIQUETAS: dict[MaestroTipo, str] = {
    "cliente": "Cliente",
    "color": "Color",
    "denier": "Denier (Dn)",
    "corte": "Corte (mm)",
    "operario": "Operario",
}


def normalizar_maestro(texto: str) -> str:
    """Comparación robusta: sin acentos, minúsculas, espacios colapsados."""
    s = (texto or "").replace("\u00a0", " ").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = re.sub(r"\s+", " ", s).strip()
    return s


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
                self._seed_operarios_desde_pesajes(conn)

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

    def _seed_operarios_desde_pesajes(self, conn: sqlite3.Connection) -> None:
        """Importa nombres distintos ya usados en pesajes hacia maestros operarios."""
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT TRIM(operario) AS n
                FROM pesajes
                WHERE TRIM(operario) != ''
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            nombre = str(r["n"] or "").strip()
            if not nombre:
                continue
            exists = conn.execute(
                "SELECT id FROM operarios WHERE nombre = ? COLLATE NOCASE",
                (nombre,),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO operarios (nombre, codigo, activo, creado_en, actualizado_en)
                VALUES (?, '', 1, ?, ?)
                """,
                (nombre, now, now),
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

    def grupos_duplicados(
        self, tipo: MaestroTipo, *, solo_activos: bool = True
    ) -> list[list[MaestroItem]]:
        """Agrupa ítems con el mismo nombre normalizado (Aa / espacios / acentos)."""
        items = self.listar(tipo, solo_activos=solo_activos)
        buckets: dict[str, list[MaestroItem]] = {}
        for m in items:
            key = normalizar_maestro(m.valor)
            if not key:
                continue
            buckets.setdefault(key, []).append(m)
        return [g for g in buckets.values() if len(g) > 1]

    def fusionar(
        self,
        tipo: MaestroTipo,
        id_canonico: int,
        ids_duplicados: list[int],
    ) -> tuple[str, int]:
        """
        Colapsa duplicados en el valor canónico:
        - actualiza historial en pesajes
        - desactiva los maestros duplicados
        Retorna (valor_canonico, cantidad_fusionados).
        """
        ids_duplicados = [i for i in ids_duplicados if i != id_canonico]
        if not ids_duplicados:
            raise CatalogoError("Seleccione al menos un duplicado distinto del canónico.")

        tabla, col = _MAESTROS[tipo]
        pesajes_col = _PESAJES_COL[tipo]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            with self._connect() as conn:
                canon = conn.execute(
                    f"SELECT id, {col} AS valor, activo FROM {tabla} WHERE id = ?",
                    (id_canonico,),
                ).fetchone()
                if not canon:
                    raise CatalogoError("Registro canónico no encontrado.")
                valor_canon = str(canon["valor"])

                dups = []
                for did in ids_duplicados:
                    row = conn.execute(
                        f"SELECT id, {col} AS valor FROM {tabla} WHERE id = ?",
                        (did,),
                    ).fetchone()
                    if row:
                        dups.append(row)

                if not dups:
                    raise CatalogoError("No se encontraron duplicados a fusionar.")

                # Historial: cualquier variante tipográfica → valor canónico
                for row in dups:
                    conn.execute(
                        f"""
                        UPDATE pesajes
                        SET {pesajes_col} = ?, estado_sincronizado = 0
                        WHERE {pesajes_col} = ? COLLATE NOCASE
                        """,
                        (valor_canon, str(row["valor"])),
                    )
                # También unificar el propio canónico por si había casing distinto en pesajes
                conn.execute(
                    f"""
                    UPDATE pesajes
                    SET {pesajes_col} = ?, estado_sincronizado = 0
                    WHERE {pesajes_col} = ? COLLATE NOCASE
                      AND {pesajes_col} != ?
                    """,
                    (valor_canon, valor_canon, valor_canon),
                )

                if int(canon["activo"]) == 0:
                    conn.execute(
                        f"UPDATE {tabla} SET activo = 1, actualizado_en = ? WHERE id = ?",
                        (now, id_canonico),
                    )

                for row in dups:
                    conn.execute(
                        f"""
                        UPDATE {tabla}
                        SET activo = 0, actualizado_en = ?
                        WHERE id = ?
                        """,
                        (now, int(row["id"])),
                    )
                conn.commit()
        return valor_canon, len(dups)

    def fusionar_similares(self, tipo: MaestroTipo) -> list[tuple[str, int]]:
        """
        Fusiona automáticamente todos los grupos duplicados.
        Conserva el valor con más usos en pesajes; empate → el de menor id.
        """
        resultados: list[tuple[str, int]] = []
        grupos = self.grupos_duplicados(tipo, solo_activos=True)
        pesajes_col = _PESAJES_COL[tipo]

        for grupo in grupos:
            # Contar usos
            counts: dict[int, int] = {}
            with self._lock:
                with self._connect() as conn:
                    for m in grupo:
                        row = conn.execute(
                            f"""
                            SELECT COUNT(*) AS n FROM pesajes
                            WHERE {pesajes_col} = ? COLLATE NOCASE
                            """,
                            (m.valor,),
                        ).fetchone()
                        counts[m.id] = int(row["n"]) if row else 0
            # Preferir más usos, luego id menor
            ordenados = sorted(grupo, key=lambda m: (-counts.get(m.id, 0), m.id))
            canon = ordenados[0]
            otros = [m.id for m in ordenados[1:]]
            valor, n = self.fusionar(tipo, canon.id, otros)
            resultados.append((valor, n))
        return resultados

    def eliminar(self, *_args, **_kwargs) -> None:
        """Bloqueado a propósito: maestros no se eliminan."""
        raise CatalogoError(
            "Prohibido eliminar maestros. Use desactivar (soft-delete) o fusionar."
        )
