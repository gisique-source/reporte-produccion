"""Almacenamiento local SQLite (local-first)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime
from typing import Optional

from config import (
    DB_PATH,
    MODO_FARDO_CONTINUAR,
    MODO_FARDO_DEFAULT,
    MODO_FARDO_REINICIAR,
)
from models import DatosEtiqueta, RegistroPesaje, ResumenDia
from audit_store import SCHEMA_SYNC_AUDITORIA, SyncAuditMixin
from audit_pesaje import SCHEMA_PESAJE_AUDITORIA, PesajeAuditMixin

try:
    from catalog import CatalogoMaestros
except ImportError:  # pragma: no cover
    CatalogoMaestros = None  # type: ignore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pesajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    cliente TEXT NOT NULL,
    lote TEXT NOT NULL,
    color TEXT NOT NULL,
    denier TEXT NOT NULL,
    corte TEXT NOT NULL,
    nro_fardo TEXT NOT NULL,
    peso_bruto REAL NOT NULL,
    peso_neto REAL NOT NULL,
    estado_sincronizado INTEGER NOT NULL DEFAULT 0,
    operario TEXT NOT NULL DEFAULT '',
    peso_total REAL NOT NULL DEFAULT 0,
    tara_carreta REAL NOT NULL DEFAULT 0,
    tara_fardo REAL NOT NULL DEFAULT 0,
    beteado TEXT NOT NULL DEFAULT '1',
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_pesajes_sync ON pesajes(estado_sincronizado);
CREATE INDEX IF NOT EXISTS idx_pesajes_fecha ON pesajes(fecha_hora);

CREATE TABLE IF NOT EXISTS app_settings (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

_MESES_ES = (
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
)
_MESES_NOMBRE = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def format_fecha_corta(d: date) -> str:
    return f"{d.day}-{_MESES_ES[d.month]}-{d.strftime('%y')}"


def format_fecha_editable(d: date) -> str:
    """Formato editable en UI: DD/MM/YYYY."""
    return d.strftime("%d/%m/%Y")


def parse_fecha_produccion(texto: str) -> Optional[date]:
    """Acepta DD/MM/YYYY o D-Mes-YY (ej. 4-Ago-26)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    # Formato corto planta: 4-Ago-26
    parts = texto.replace("/", "-").split("-")
    if len(parts) == 3:
        try:
            dia = int(parts[0])
            mes_txt = parts[1].strip().capitalize()
            anio = int(parts[2])
            if anio < 100:
                anio += 2000
            mes = next(
                (i for i, m in enumerate(_MESES_ES) if m and m.lower() == mes_txt.lower()),
                None,
            )
            if mes:
                return date(anio, mes, dia)
        except ValueError:
            return None
    return None


def nombre_mes(month: int) -> str:
    return _MESES_NOMBRE[month]


class PesajeDatabase(SyncAuditMixin, PesajeAuditMixin):
    """Acceso thread-safe a pesajes.db."""

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._init_db()
        self.catalogo = CatalogoMaestros(path=self.path, lock=self._lock)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                conn.executescript(SCHEMA_SYNC_AUDITORIA)
                conn.executescript(SCHEMA_PESAJE_AUDITORIA)
                self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(pesajes)").fetchall()}
        if "activo" not in cols:
            conn.execute(
                "ALTER TABLE pesajes ADD COLUMN activo INTEGER NOT NULL DEFAULT 1"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pesajes_activo ON pesajes(activo)"
        )
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pesajes_lote_fardo
                ON pesajes (lote COLLATE NOCASE, CAST(nro_fardo AS INTEGER))
                """
            )
        except sqlite3.IntegrityError:
            # Duplicados históricos: la validación en insertar/actualizar igual aplica.
            pass
        conn.commit()

    def existe_fardo_en_lote(
        self,
        lote: str,
        nro_fardo: str,
        *,
        excluir_id: Optional[int] = None,
    ) -> bool:
        """True si ya hay un fardo con ese Nº en el mismo lote (incluye ocultos)."""
        with self._lock:
            with self._connect() as conn:
                return self._existe_fardo_en_lote(
                    conn, lote, nro_fardo, excluir_id=excluir_id
                )

    @staticmethod
    def _existe_fardo_en_lote(
        conn: sqlite3.Connection,
        lote: str,
        nro_fardo: str,
        *,
        excluir_id: Optional[int] = None,
    ) -> bool:
        lote = (lote or "").strip()
        nro = str(nro_fardo or "").strip()
        if not lote or not nro:
            return False
        sql = """
            SELECT id FROM pesajes
            WHERE lote = ? COLLATE NOCASE
              AND CAST(nro_fardo AS INTEGER) = CAST(? AS INTEGER)
              AND nro_fardo GLOB '[0-9]*'
        """
        params: list[object] = [lote, nro]
        if excluir_id is not None:
            sql += " AND id != ?"
            params.append(int(excluir_id))
        row = conn.execute(sql + " LIMIT 1", params).fetchone()
        return row is not None

    def _asegurar_fardo_unico(
        self,
        conn: sqlite3.Connection,
        lote: str,
        nro_fardo: str,
        *,
        excluir_id: Optional[int] = None,
    ) -> None:
        if self._existe_fardo_en_lote(
            conn, lote, nro_fardo, excluir_id=excluir_id
        ):
            raise ValueError(
                f"Ya existe el fardo {str(nro_fardo).strip()} en el lote "
                f"{(lote or '').strip()}. No pueden repetirse en el mismo lote."
            )

    def insertar(self, datos: DatosEtiqueta, fecha_hora: Optional[str] = None) -> int:
        fh = fecha_hora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._connect() as conn:
                self._asegurar_fardo_unico(conn, datos.lote, datos.nro_fardo)
                cur = conn.execute(
                    """
                    INSERT INTO pesajes (
                        fecha_hora, cliente, lote, color, denier, corte,
                        nro_fardo, peso_bruto, peso_neto, estado_sincronizado,
                        operario, peso_total, tara_carreta, tara_fardo, beteado,
                        activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        fh,
                        datos.cliente,
                        datos.lote,
                        datos.color,
                        datos.dn,
                        datos.corte,
                        datos.nro_fardo,
                        datos.peso_bruto,
                        datos.peso_neto,
                        datos.operario,
                        datos.peso_total,
                        datos.tara_carreta,
                        datos.tara_fardo,
                        datos.beteado,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

    def pendientes(self, limite: int = 50) -> list[RegistroPesaje]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM pesajes
                    WHERE estado_sincronizado = 0 AND activo = 1
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (limite,),
                ).fetchall()
        return [self._row_to_registro(r) for r in rows]

    def marcar_sincronizados(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE pesajes SET estado_sincronizado = 1 WHERE id IN ({placeholders})",
                    ids,
                )
                conn.commit()

    def get_setting(self, clave: str, default: str = "") -> str:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT valor FROM app_settings WHERE clave = ?",
                    (clave,),
                ).fetchone()
        return str(row["valor"]) if row else default

    def set_setting(self, clave: str, valor: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO app_settings (clave, valor) VALUES (?, ?)
                    ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
                    """,
                    (clave, valor),
                )
                conn.commit()

    def get_modo_fardo(self) -> str:
        modo = self.get_setting("modo_fardo", MODO_FARDO_DEFAULT)
        if modo not in (MODO_FARDO_CONTINUAR, MODO_FARDO_REINICIAR):
            return MODO_FARDO_DEFAULT
        return modo

    def set_modo_fardo(self, modo: str) -> None:
        if modo not in (MODO_FARDO_CONTINUAR, MODO_FARDO_REINICIAR):
            modo = MODO_FARDO_DEFAULT
        self.set_setting("modo_fardo", modo)

    def ultimo_nro_fardo(
        self, *, solo_hoy: bool = False, dia: Optional[date] = None
    ) -> int:
        """
        Máximo Nº de fardo numérico (global o del día).
        Incluye registros ocultos para no afectar el correlativo.
        """
        with self._lock:
            with self._connect() as conn:
                if solo_hoy:
                    d = dia or date.today()
                    inicio = d.strftime("%Y-%m-%d 00:00:00")
                    fin = d.strftime("%Y-%m-%d 23:59:59")
                    row = conn.execute(
                        """
                        SELECT MAX(CAST(nro_fardo AS INTEGER)) AS m
                        FROM pesajes
                        WHERE fecha_hora BETWEEN ? AND ?
                          AND nro_fardo GLOB '[0-9]*'
                        """,
                        (inicio, fin),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT MAX(CAST(nro_fardo AS INTEGER)) AS m
                        FROM pesajes
                        WHERE nro_fardo GLOB '[0-9]*'
                        """
                    ).fetchone()
        val = row["m"] if row else None
        return int(val) if val is not None else 0

    def ultimo_nro_fardo_antes(self, dia: date) -> int:
        """Máximo Nº de fardo anterior a ``dia`` (p. ej. correlativo del día previo)."""
        inicio = dia.strftime("%Y-%m-%d 00:00:00")
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT MAX(CAST(nro_fardo AS INTEGER)) AS m
                    FROM pesajes
                    WHERE fecha_hora < ?
                      AND nro_fardo GLOB '[0-9]*'
                    """,
                    (inicio,),
                ).fetchone()
        val = row["m"] if row else None
        return int(val) if val is not None else 0

    def siguiente_nro_fardo(
        self, modo: Optional[str] = None, *, dia: Optional[date] = None
    ) -> int:
        """
        Correlativo de Nº Fardo (los ocultos siguen contando en el máximo).
        - continuar: último global + 1
        - reiniciar: serie del día (fecha producción) desde 1
        """
        modo = modo or self.get_modo_fardo()
        if modo == MODO_FARDO_REINICIAR:
            return self.ultimo_nro_fardo(solo_hoy=True, dia=dia) + 1
        return self.ultimo_nro_fardo(solo_hoy=False) + 1

    def por_fecha(
        self, dia: date, *, incluir_ocultos: bool = False
    ) -> list[RegistroPesaje]:
        inicio = dia.strftime("%Y-%m-%d 00:00:00")
        fin = dia.strftime("%Y-%m-%d 23:59:59")
        filtro = "" if incluir_ocultos else "AND activo = 1"
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT * FROM pesajes
                    WHERE fecha_hora BETWEEN ? AND ?
                    {filtro}
                    ORDER BY id ASC
                    """,
                    (inicio, fin),
                ).fetchall()
        return [self._row_to_registro(r) for r in rows]

    def por_rango(
        self, desde: date, hasta: date, *, incluir_ocultos: bool = False
    ) -> list[RegistroPesaje]:
        """Registros entre dos fechas (inclusive), ordenados por fecha_hora."""
        if hasta < desde:
            desde, hasta = hasta, desde
        inicio = desde.strftime("%Y-%m-%d 00:00:00")
        fin = hasta.strftime("%Y-%m-%d 23:59:59")
        filtro = "" if incluir_ocultos else "AND activo = 1"
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT * FROM pesajes
                    WHERE fecha_hora BETWEEN ? AND ?
                    {filtro}
                    ORDER BY fecha_hora ASC, id ASC
                    """,
                    (inicio, fin),
                ).fetchall()
        return [self._row_to_registro(r) for r in rows]

    def obtener(self, registro_id: int) -> Optional[RegistroPesaje]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM pesajes WHERE id = ?", (registro_id,)
                ).fetchone()
        return self._row_to_registro(row) if row else None

    def actualizar(self, registro_id: int, datos: DatosEtiqueta) -> None:
        """Modifica un registro existente (no borra)."""
        with self._lock:
            with self._connect() as conn:
                self._asegurar_fardo_unico(
                    conn, datos.lote, datos.nro_fardo, excluir_id=registro_id
                )
                cur = conn.execute(
                    """
                    UPDATE pesajes SET
                        cliente = ?, lote = ?, color = ?, denier = ?, corte = ?,
                        nro_fardo = ?, peso_bruto = ?, peso_neto = ?,
                        operario = ?, peso_total = ?, tara_carreta = ?,
                        tara_fardo = ?, beteado = ?,
                        estado_sincronizado = 0
                    WHERE id = ? AND activo = 1
                    """,
                    (
                        datos.cliente,
                        datos.lote,
                        datos.color,
                        datos.dn,
                        datos.corte,
                        datos.nro_fardo,
                        datos.peso_bruto,
                        datos.peso_neto,
                        datos.operario,
                        datos.peso_total,
                        datos.tara_carreta,
                        datos.tara_fardo,
                        datos.beteado,
                        registro_id,
                    ),
                )
                if cur.rowcount == 0:
                    raise ValueError("Registro no encontrado o está oculto.")
                conn.commit()

    def ocultar(self, registro_id: int) -> None:
        """Soft-delete: activo=0. No elimina y no libera el Nº de fardo."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE pesajes SET activo = 0, estado_sincronizado = 0 WHERE id = ? AND activo = 1",
                    (registro_id,),
                )
                if cur.rowcount == 0:
                    raise ValueError("Registro no encontrado o ya oculto.")
                conn.commit()

    def restaurar(self, registro_id: int) -> None:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE pesajes SET activo = 1, estado_sincronizado = 0 WHERE id = ? AND activo = 0",
                    (registro_id,),
                )
                if cur.rowcount == 0:
                    raise ValueError("Registro no encontrado o ya visible.")
                conn.commit()

    def listar_anios(self, *, desde: int = 2020) -> list[int]:
        """Años navegables: desde `desde` hasta el año actual (y los que tengan data)."""
        hoy = date.today().year
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT DISTINCT CAST(substr(fecha_hora, 1, 4) AS INTEGER) AS anio
                    FROM pesajes
                    ORDER BY anio DESC
                    """
                ).fetchall()
        anios = {int(r["anio"]) for r in rows}
        for y in range(desde, hoy + 1):
            anios.add(y)
        return sorted(anios, reverse=True)

    def listar_meses(self, year: int) -> list[int]:
        """Siempre los 12 meses (para migrar data de cualquier mes)."""
        return list(range(1, 13))

    def listar_dias_mes(self, year: int, month: int) -> list[ResumenDia]:
        """Todos los días del mes (con o sin registros)."""
        return self.resumen_mes(year, month)

    def resumen_mes(self, year: int, month: int) -> list[ResumenDia]:
        """Totales bruto/neto por día del mes (solo activos)."""
        import calendar

        days_in_month = calendar.monthrange(year, month)[1]
        prefix = f"{year:04d}-{month:02d}"
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT substr(fecha_hora, 1, 10) AS dia,
                           SUM(peso_bruto) AS bruto,
                           SUM(peso_neto) AS neto,
                           COUNT(*) AS cant
                    FROM pesajes
                    WHERE fecha_hora LIKE ? AND activo = 1
                    GROUP BY substr(fecha_hora, 1, 10)
                    """,
                    (f"{prefix}%",),
                ).fetchall()

        by_day = {
            int(r["dia"][8:10]): (float(r["bruto"]), float(r["neto"]), int(r["cant"]))
            for r in rows
        }
        result: list[ResumenDia] = []
        for d in range(1, days_in_month + 1):
            bruto, neto, cant = by_day.get(d, (0.0, 0.0, 0))
            fecha = date(year, month, d)
            result.append(
                ResumenDia(
                    dia=d,
                    fecha=format_fecha_corta(fecha),
                    peso_bruto=bruto,
                    peso_neto=neto,
                    cantidad=cant,
                )
            )
        return result

    def contar_pendientes(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM pesajes
                    WHERE estado_sincronizado = 0 AND activo = 1
                    """
                ).fetchone()
        return int(row["n"])

    @staticmethod
    def _row_to_registro(row: sqlite3.Row) -> RegistroPesaje:
        keys = row.keys()
        return RegistroPesaje(
            id=row["id"],
            fecha_hora=row["fecha_hora"],
            cliente=row["cliente"],
            lote=row["lote"],
            color=row["color"],
            denier=row["denier"],
            corte=row["corte"],
            nro_fardo=row["nro_fardo"],
            peso_bruto=float(row["peso_bruto"]),
            peso_neto=float(row["peso_neto"]),
            estado_sincronizado=int(row["estado_sincronizado"]),
            operario=row["operario"] if "operario" in keys else "",
            peso_total=float(row["peso_total"]) if "peso_total" in keys else 0.0,
            tara_carreta=float(row["tara_carreta"]) if "tara_carreta" in keys else 0.0,
            tara_fardo=float(row["tara_fardo"]) if "tara_fardo" in keys else 0.0,
            beteado=row["beteado"] if "beteado" in keys else "1",
            activo=int(row["activo"]) if "activo" in keys else 1,
        )
