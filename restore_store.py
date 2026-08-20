"""Upsert de pesajes/maestros al restaurar desde la API nube."""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from catalog import MaestroTipo, normalizar_maestro


class RestoreStoreMixin:
    """Métodos de restauración; requiere _lock y _connect en la clase base."""

    def contar_pesajes(self, *, solo_activos: bool = False) -> int:
        filtro = "WHERE activo = 1" if solo_activos else ""
        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                row = conn.execute(
                    f"SELECT COUNT(*) AS n FROM pesajes {filtro}"
                ).fetchone()
        return int(row["n"])

    def upsert_pesaje_remoto(self, item: dict[str, Any]) -> str:
        """
        Inserta o actualiza un pesaje venido de la nube.
        Retorna: 'insertado' | 'actualizado' | 'omitido'.
        Clave preferida: id_local; fallback: (lote, nro_fardo).
        Los registros restaurados quedan estado_sincronizado = 1.
        """
        id_local = _as_int(item.get("id_local"))
        lote = str(item.get("lote") or "").strip()
        nro_fardo = str(item.get("nro_fardo") or "").strip()
        if not lote or not nro_fardo:
            return "omitido"

        fecha_hora = str(item.get("fecha_hora") or "").strip()
        if not fecha_hora:
            return "omitido"

        campos = (
            fecha_hora,
            str(item.get("cliente") or "").strip(),
            lote,
            str(item.get("color") or "").strip(),
            str(item.get("denier") or "").strip(),
            str(item.get("corte") or "").strip(),
            nro_fardo,
            _as_float(item.get("peso_bruto")),
            _as_float(item.get("peso_neto")),
            1,  # ya está en la nube
            str(item.get("operario") or "").strip(),
            _as_float(item.get("peso_total")),
            _as_float(item.get("tara_carreta")),
            _as_float(item.get("tara_fardo")),
            str(item.get("beteado") or "1").strip() or "1",
            1 if _as_int(item.get("activo"), default=1) else 0,
        )

        with self._lock:  # type: ignore[attr-defined]
            with self._connect() as conn:  # type: ignore[attr-defined]
                existing_id = self._resolver_id_existente(
                    conn, id_local=id_local, lote=lote, nro_fardo=nro_fardo
                )
                if existing_id is not None:
                    conn.execute(
                        """
                        UPDATE pesajes SET
                            fecha_hora = ?, cliente = ?, lote = ?, color = ?,
                            denier = ?, corte = ?, nro_fardo = ?,
                            peso_bruto = ?, peso_neto = ?, estado_sincronizado = ?,
                            operario = ?, peso_total = ?, tara_carreta = ?,
                            tara_fardo = ?, beteado = ?, activo = ?
                        WHERE id = ?
                        """,
                        (*campos, existing_id),
                    )
                    conn.commit()
                    return "actualizado"

                if id_local is not None and id_local > 0:
                    conn.execute(
                        """
                        INSERT INTO pesajes (
                            id, fecha_hora, cliente, lote, color, denier, corte,
                            nro_fardo, peso_bruto, peso_neto, estado_sincronizado,
                            operario, peso_total, tara_carreta, tara_fardo,
                            beteado, activo
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (id_local, *campos),
                    )
                    self._fix_sqlite_sequence(conn, max(id_local, 0))
                else:
                    conn.execute(
                        """
                        INSERT INTO pesajes (
                            fecha_hora, cliente, lote, color, denier, corte,
                            nro_fardo, peso_bruto, peso_neto, estado_sincronizado,
                            operario, peso_total, tara_carreta, tara_fardo,
                            beteado, activo
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        campos,
                    )
                conn.commit()
                return "insertado"

    def upsert_maestro_remoto(
        self,
        tipo: MaestroTipo,
        *,
        valor: str,
        codigo: str = "",
        activo: int = 1,
    ) -> str:
        """Asegura un ítem de catálogo. Retorna insertado|actualizado|omitido."""
        valor = (valor or "").strip()
        if not valor:
            return "omitido"
        catalogo = getattr(self, "catalogo", None)
        if catalogo is None:
            return "omitido"

        # Reutiliza el catálogo (crea o reactiva) sin lanzar si ya existe activo.
        items = catalogo.listar(tipo, solo_activos=False)
        key = normalizar_maestro(valor)
        for m in items:
            if normalizar_maestro(m.valor) == key:
                if int(m.activo) == 1 and int(activo) == 1:
                    if codigo and codigo != (m.codigo or ""):
                        try:
                            catalogo.actualizar(tipo, m.id, m.valor, codigo)
                            return "actualizado"
                        except Exception:  # noqa: BLE001
                            return "omitido"
                    return "omitido"
                if int(activo) == 1 and int(m.activo) == 0:
                    catalogo.reactivar(tipo, m.id)
                    if codigo:
                        try:
                            catalogo.actualizar(tipo, m.id, valor, codigo)
                        except Exception:  # noqa: BLE001
                            pass
                    return "actualizado"
                return "omitido"

        if int(activo) != 1:
            return "omitido"
        catalogo.crear(tipo, valor, codigo=codigo)
        return "insertado"

    @staticmethod
    def _resolver_id_existente(
        conn: sqlite3.Connection,
        *,
        id_local: Optional[int],
        lote: str,
        nro_fardo: str,
    ) -> Optional[int]:
        if id_local is not None and id_local > 0:
            row = conn.execute(
                "SELECT id FROM pesajes WHERE id = ?", (id_local,)
            ).fetchone()
            if row:
                return int(row["id"])
        row = conn.execute(
            """
            SELECT id FROM pesajes
            WHERE lote = ? COLLATE NOCASE
              AND CAST(nro_fardo AS INTEGER) = CAST(? AS INTEGER)
              AND nro_fardo GLOB '[0-9]*'
            LIMIT 1
            """,
            (lote, nro_fardo),
        ).fetchone()
        return int(row["id"]) if row else None

    @staticmethod
    def _fix_sqlite_sequence(conn: sqlite3.Connection, min_id: int) -> None:
        """Evita que AUTOINCREMENT reutilice IDs ya restaurados."""
        if min_id <= 0:
            return
        row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'pesajes'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES ('pesajes', ?)",
                (min_id,),
            )
        elif int(row["seq"]) < min_id:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = 'pesajes'",
                (min_id,),
            )


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
