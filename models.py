"""Modelos de datos reutilizables."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DatosEtiqueta:
    """Parámetros de la etiqueta / registro de producción."""

    color: str
    cliente: str
    lote: str
    dn: str
    corte: str
    nro_fardo: str
    fecha: str
    peso_bruto: float
    peso_neto: float
    # Extensión hoja de producción
    operario: str = ""
    peso_total: float = 0.0
    tara_carreta: float = 0.0
    tara_fardo: float = 0.0
    hora: str = ""
    beteado: str = "1"
    # Timestamp completo para SQLite (permite registros con fecha anterior)
    fecha_hora_registro: str = ""

    @property
    def codigo_barras(self) -> str:
        return f"{self.lote}-{self.nro_fardo}"

    @property
    def denier(self) -> str:
        return self.dn


@dataclass
class RegistroPesaje:
    """Fila de pesajes.db (local-first)."""

    id: int
    fecha_hora: str
    cliente: str
    lote: str
    color: str
    denier: str
    corte: str
    nro_fardo: str
    peso_bruto: float
    peso_neto: float
    estado_sincronizado: int
    operario: str = ""
    peso_total: float = 0.0
    tara_carreta: float = 0.0
    tara_fardo: float = 0.0
    beteado: str = "1"
    activo: int = 1

    def to_sync_payload(self) -> dict[str, Any]:
        """JSON mínimo para la API en la nube."""
        return {
            "id_local": self.id,
            "fecha_hora": self.fecha_hora,
            "cliente": self.cliente,
            "lote": self.lote,
            "color": self.color,
            "denier": self.denier,
            "corte": self.corte,
            "nro_fardo": self.nro_fardo,
            "peso_bruto": self.peso_bruto,
            "peso_neto": self.peso_neto,
            "operario": self.operario,
            "peso_total": self.peso_total,
            "tara_carreta": self.tara_carreta,
            "tara_fardo": self.tara_fardo,
            "activo": self.activo,
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResumenDia:
    dia: int
    fecha: str
    peso_bruto: float
    peso_neto: float
    cantidad: int


@dataclass
class RegistroAuditoriaSync:
    """Fila de historial de subidas a la API nube."""

    id: int
    enviado_en: str
    pesaje_id: int
    id_remoto: str
    http_status: int
    ok: int
    duplicado: int
    planta: str
    nro_fardo: str
    lote: str
    cliente: str
    color: str
    peso_bruto: float
    peso_neto: float
    fecha_hora_pesaje: str
    mensaje: str
    url: str


@dataclass
class MaestroItem:
    """Registro de tabla maestro (cliente, color, denier, corte)."""

    id: int
    valor: str
    activo: int = 1
    codigo: str = ""
