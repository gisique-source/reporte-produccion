"""
Carga masiva desde pegado Excel (TSV/CSV del portapapeles).

- Detecta encabezados con regex flexible
- Normaliza espacios / mayúsculas / acentos para emparejar maestros
- Marca valores de catálogo inexistentes para crearlos al vuelo
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from catalog import CatalogoMaestros, MaestroTipo
from config import TARA_CARRETA_KG, TARA_FARDO_KG
from db import format_fecha_editable
from models import DatosEtiqueta

# Claves internas de columna → patrones de encabezado (regex, case-insensitive)
_HEADER_PATTERNS: dict[str, re.Pattern[str]] = {
    "fardo": re.compile(r"^(n[ºo°.]?\s*)?(fardo|nro|numero|#)$", re.I),
    "cliente": re.compile(r"^clientes?$", re.I),
    "lote": re.compile(r"^lotes?$", re.I),
    "color": re.compile(r"^colou?rs?$", re.I),
    "dn": re.compile(r"^(dn|denier|den)$", re.I),
    "corte": re.compile(r"^(corte|cortes?|mm)$", re.I),
    "total": re.compile(r"^(p\.?\s*)?total(es)?$", re.I),
    "tara_c": re.compile(r"^tara\s*(carr(eta)?|c\.?)$", re.I),
    "tara_f": re.compile(r"^tara\s*(fardo|f\.?)$", re.I),
    "bruto": re.compile(r"^(p\.?\s*)?bruto$", re.I),
    "neto": re.compile(r"^(p\.?\s*)?neto$", re.I),
    "hora": re.compile(r"^(hora|time|hh:mm)", re.I),
    "operario": re.compile(r"^(operario|operador|op\.?)$", re.I),
}

# Orden por defecto si no hay encabezado (compatible con hoja / Excel típico)
_DEFAULT_ORDER = (
    "fardo",
    "cliente",
    "lote",
    "color",
    "dn",
    "corte",
    "total",
    "tara_c",
    "tara_f",
    "bruto",
    "neto",
    "hora",
    "operario",
)

_MAESTRO_KEYS: dict[str, MaestroTipo] = {
    "cliente": "cliente",
    "color": "color",
    "dn": "denier",
    "corte": "corte",
    "operario": "operario",
}


def normalizar_texto(texto: str) -> str:
    """
    Normalización robusta para comparar valores de maestro:
    - quita acentos
    - minúsculas
    - colapsa espacios / tabs / NBSP
    - unifica comas decimales en números simples
    """
    s = (texto or "").replace("\u00a0", " ").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = re.sub(r"[\s_\-./\\]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _patron_flexible(normalizado: str) -> re.Pattern[str]:
    """Regex que tolera espacios opcionales entre caracteres/token."""
    tokens = normalizado.split()
    if not tokens:
        return re.compile(r"^$")
    partes = [re.escape(t) for t in tokens]
    return re.compile(r"^\s*" + r"\s+".join(partes) + r"\s*$", re.I)


def resolver_maestro(
    texto: str, candidatos: list[str]
) -> tuple[Optional[str], str]:
    """
    Busca el valor canónico en el catálogo.
    Retorna (valor_canonico | None, texto_limpio_propuesto).
    """
    crudo = (texto or "").replace("\u00a0", " ").strip()
    crudo = re.sub(r"\s+", " ", crudo)
    if not crudo:
        return None, ""

    n = normalizar_texto(crudo)
    # 1) igualdad normalizada exacta
    for c in candidatos:
        if normalizar_texto(c) == n:
            return c, crudo

    # 2) regex flexible (espacios / guiones)
    pat = _patron_flexible(n)
    for c in candidatos:
        if pat.match(normalizar_texto(c)) or pat.match(c):
            return c, crudo

    # 3) contiene / contenido (p. ej. "Marron 580" vs "Marrón580")
    n_compact = n.replace(" ", "")
    for c in candidatos:
        cn = normalizar_texto(c).replace(" ", "")
        if cn == n_compact:
            return c, crudo

    return None, crudo


def parse_float(texto: str, default: float = 0.0) -> float:
    s = (texto or "").strip().replace(" ", "").replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _split_clipboard(texto: str) -> list[list[str]]:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not texto.strip():
        return []
    # Excel usa tab; a veces exportan con ;
    sep = "\t"
    if "\t" not in texto and ";" in texto:
        sep = ";"
    elif "\t" not in texto and "," in texto:
        # CSV simple (evitar romper decimales: solo si muchas comas por fila)
        lines = texto.split("\n")
        if lines and lines[0].count(",") >= 3:
            sep = ","

    rows: list[list[str]] = []
    for line in texto.split("\n"):
        if not line.strip():
            continue
        cells = [c.strip().strip('"') for c in line.split(sep)]
        rows.append(cells)
    return rows


def _map_headers(cells: list[str]) -> Optional[dict[str, int]]:
    """Si la fila parece encabezado, retorna mapa clave→índice."""
    mapping: dict[str, int] = {}
    hits = 0
    for i, cell in enumerate(cells):
        key_cell = re.sub(r"\s+", " ", cell.strip())
        key_cell = re.sub(r"[^\w\s.#º°]", "", key_cell, flags=re.UNICODE)
        for key, pat in _HEADER_PATTERNS.items():
            if pat.search(key_cell.replace(" ", "")) or pat.search(key_cell):
                if key not in mapping:
                    mapping[key] = i
                    hits += 1
                break
    if hits >= 3 and ("cliente" in mapping or "fardo" in mapping or "lote" in mapping):
        return mapping
    return None


def _default_mapping(ncols: int) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, key in enumerate(_DEFAULT_ORDER):
        if i < ncols:
            mapping[key] = i
    return mapping


@dataclass
class FilaImport:
    nro_fardo: str
    cliente: str
    lote: str
    color: str
    dn: str
    corte: str
    operario: str
    peso_total: float
    tara_carreta: float
    tara_fardo: float
    peso_bruto: float
    peso_neto: float
    hora: str = ""
    # Canónicos resueltos (None = faltante en maestros)
    cliente_ok: Optional[str] = None
    color_ok: Optional[str] = None
    dn_ok: Optional[str] = None
    corte_ok: Optional[str] = None
    operario_ok: Optional[str] = None
    errores: list[str] = field(default_factory=list)

    @property
    def tiene_faltantes(self) -> bool:
        return any(
            v is None and raw
            for v, raw in (
                (self.cliente_ok, self.cliente),
                (self.color_ok, self.color),
                (self.dn_ok, self.dn),
                (self.corte_ok, self.corte),
                (self.operario_ok, self.operario),
            )
        )

    @property
    def lista_para_importar(self) -> bool:
        return bool(self.nro_fardo) and not self.errores and not self.tiene_faltantes


@dataclass
class ResultadoParseo:
    filas: list[FilaImport]
    mapeo: dict[str, int]
    aviso: str = ""


def parsear_pegado(
    texto: str,
    catalogo: CatalogoMaestros,
    *,
    tara_c_default: float = TARA_CARRETA_KG,
    tara_f_default: float = TARA_FARDO_KG,
) -> ResultadoParseo:
    rows = _split_clipboard(texto)
    if not rows:
        return ResultadoParseo([], {}, "Portapapeles vacío.")

    header_map = _map_headers(rows[0])
    if header_map:
        data_rows = rows[1:]
        mapeo = header_map
        aviso = f"Encabezado detectado · {len(data_rows)} filas"
    else:
        data_rows = rows
        mapeo = _default_mapping(len(rows[0]))
        aviso = f"Sin encabezado · orden por defecto · {len(data_rows)} filas"

    cats = {
        "cliente": catalogo.valores_activos("cliente"),
        "color": catalogo.valores_activos("color"),
        "dn": catalogo.valores_activos("denier"),
        "corte": catalogo.valores_activos("corte"),
        "operario": catalogo.valores_activos("operario"),
    }

    filas: list[FilaImport] = []
    for cells in data_rows:
        def get(key: str, default: str = "") -> str:
            idx = mapeo.get(key)
            if idx is None or idx >= len(cells):
                return default
            return cells[idx].strip()

        fardo = get("fardo")
        # Saltar filas de totales / vacías
        if not fardo and not get("cliente") and not get("lote"):
            continue
        if re.search(r"total", fardo, re.I) and not re.search(r"\d", fardo):
            continue

        total = parse_float(get("total"))
        tc = parse_float(get("tara_c"), tara_c_default)
        tf = parse_float(get("tara_f"), tara_f_default)
        bruto = parse_float(get("bruto"))
        neto = parse_float(get("neto"))
        if not get("bruto"):
            bruto = max(total - tc, 0.0)
        if not get("neto"):
            neto = max(total - tc - tf, 0.0)

        cli_raw = get("cliente")
        col_raw = get("color")
        dn_raw = get("dn")
        corte_raw = get("corte")
        op_raw = get("operario")

        cli_ok, cli_prop = resolver_maestro(cli_raw, cats["cliente"])
        col_ok, col_prop = resolver_maestro(col_raw, cats["color"])
        dn_ok, dn_prop = resolver_maestro(dn_raw, cats["dn"])
        corte_ok, corte_prop = resolver_maestro(corte_raw, cats["corte"])
        op_ok, op_prop = resolver_maestro(op_raw, cats["operario"])

        errores: list[str] = []
        if not fardo:
            errores.append("Sin Nº fardo")

        filas.append(
            FilaImport(
                nro_fardo=re.sub(r"[^\d]", "", fardo) or fardo,
                cliente=cli_prop or cli_raw,
                lote=re.sub(r"\s+", " ", get("lote")).strip(),
                color=col_prop or col_raw,
                dn=dn_prop or dn_raw,
                corte=corte_prop or corte_raw,
                operario=op_prop or op_raw,
                peso_total=total,
                tara_carreta=tc,
                tara_fardo=tf,
                peso_bruto=bruto,
                peso_neto=neto,
                hora=get("hora"),
                cliente_ok=cli_ok,
                color_ok=col_ok,
                dn_ok=dn_ok,
                corte_ok=corte_ok,
                operario_ok=op_ok,
                errores=errores,
            )
        )

    seen: dict[tuple[str, str], int] = {}
    for f in filas:
        nro = f.nro_fardo.strip()
        lote = f.lote.strip()
        if not nro or not lote:
            continue
        clave = (
            lote.casefold(),
            str(int(nro)) if nro.isdigit() else nro,
        )
        if clave in seen:
            f.errores.append(
                f"Fardo {nro} repetido en el lote {lote} (mismo pegado)"
            )
        else:
            seen[clave] = 1

    return ResultadoParseo(filas, mapeo, aviso)


def maestros_faltantes(filas: list[FilaImport]) -> dict[MaestroTipo, list[str]]:
    """Valores únicos a crear por tipo de maestro."""
    faltantes: dict[MaestroTipo, list[str]] = {
        "cliente": [],
        "color": [],
        "denier": [],
        "corte": [],
        "operario": [],
    }
    seen: dict[MaestroTipo, set[str]] = {k: set() for k in faltantes}

    for f in filas:
        pares = (
            ("cliente", f.cliente_ok, f.cliente),
            ("color", f.color_ok, f.color),
            ("denier", f.dn_ok, f.dn),
            ("corte", f.corte_ok, f.corte),
            ("operario", f.operario_ok, f.operario),
        )
        for tipo, ok, raw in pares:
            if ok is None and raw:
                key = normalizar_texto(raw)
                if key not in seen[tipo]:  # type: ignore[index]
                    seen[tipo].add(key)  # type: ignore[index]
                    faltantes[tipo].append(raw)  # type: ignore[index]
    return faltantes


def crear_maestros_faltantes(
    catalogo: CatalogoMaestros, filas: list[FilaImport]
) -> int:
    """Crea maestros faltantes y re-resuelve las filas. Retorna cantidad creada."""
    falt = maestros_faltantes(filas)
    creados = 0
    for tipo, valores in falt.items():
        for v in valores:
            try:
                catalogo.crear(tipo, v)
                creados += 1
            except Exception:  # noqa: BLE001
                # Ya existe (carrera / case) — ignorar
                pass

    # Re-resolver
    cats = {
        "cliente": catalogo.valores_activos("cliente"),
        "color": catalogo.valores_activos("color"),
        "dn": catalogo.valores_activos("denier"),
        "corte": catalogo.valores_activos("corte"),
        "operario": catalogo.valores_activos("operario"),
    }
    for f in filas:
        if f.cliente_ok is None and f.cliente:
            f.cliente_ok, _ = resolver_maestro(f.cliente, cats["cliente"])
            if f.cliente_ok:
                f.cliente = f.cliente_ok
        if f.color_ok is None and f.color:
            f.color_ok, _ = resolver_maestro(f.color, cats["color"])
            if f.color_ok:
                f.color = f.color_ok
        if f.dn_ok is None and f.dn:
            f.dn_ok, _ = resolver_maestro(f.dn, cats["dn"])
            if f.dn_ok:
                f.dn = f.dn_ok
        if f.corte_ok is None and f.corte:
            f.corte_ok, _ = resolver_maestro(f.corte, cats["corte"])
            if f.corte_ok:
                f.corte = f.corte_ok
        if f.operario_ok is None and f.operario:
            f.operario_ok, _ = resolver_maestro(f.operario, cats["operario"])
            if f.operario_ok:
                f.operario = f.operario_ok
    return creados


def fila_a_datos(fila: FilaImport, dia: date) -> DatosEtiqueta:
    now = datetime.now()
    hora = fila.hora.strip()
    if not hora:
        hora = now.strftime("%I:%M %p").lstrip("0").lower()
    # Intentar anexar hora al timestamp si viene HH:MM
    fh_time = now.time()
    m = re.match(r"(\d{1,2}):(\d{2})", hora)
    if m:
        try:
            from datetime import time as dtime

            hh, mm = int(m.group(1)), int(m.group(2))
            if "p" in hora.lower() and hh < 12:
                hh += 12
            if "a" in hora.lower() and hh == 12:
                hh = 0
            fh_time = dtime(min(hh, 23), min(mm, 59), now.second)
        except ValueError:
            pass
    fh = datetime.combine(dia, fh_time).strftime("%Y-%m-%d %H:%M:%S")
    return DatosEtiqueta(
        color=fila.color_ok or fila.color,
        cliente=fila.cliente_ok or fila.cliente,
        lote=fila.lote,
        dn=fila.dn_ok or fila.dn,
        corte=fila.corte_ok or fila.corte,
        nro_fardo=str(fila.nro_fardo),
        fecha=format_fecha_editable(dia),
        peso_bruto=fila.peso_bruto,
        peso_neto=fila.peso_neto,
        operario=fila.operario_ok or fila.operario,
        peso_total=fila.peso_total,
        tara_carreta=fila.tara_carreta,
        tara_fardo=fila.tara_fardo,
        hora=hora,
        fecha_hora_registro=fh,
    )
