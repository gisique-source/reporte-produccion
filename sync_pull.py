"""Descarga (pull) desde la API nube → SQLite local (bootstrap / reinstalación)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from catalog import MaestroTipo
from config import (
    SYNC_PLANTA,
    SYNC_PULL_PAGE_SIZE,
    SYNC_PULL_URL,
    SYNC_TIMEOUT_S,
    SYNC_TOKEN,
)
from db import PesajeDatabase

logger = logging.getLogger(__name__)

_MAESTRO_KEYS: dict[str, MaestroTipo] = {
    "clientes": "cliente",
    "cliente": "cliente",
    "colores": "color",
    "color": "color",
    "deniers": "denier",
    "denier": "denier",
    "cortes": "corte",
    "corte": "corte",
    "operarios": "operario",
    "operario": "operario",
}


@dataclass
class PullResult:
    ok: bool
    insertados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    maestros_ok: int = 0
    paginas: int = 0
    total_remoto: Optional[int] = None
    mensaje: str = ""
    http_status: int = 0
    errores: list[str] = field(default_factory=list)


class SyncPullClient:
    """
    GET paginado a /pesajes/export (o PRECIX_SYNC_PULL_URL).
    Upsert local por id_local / (lote, nro_fardo); marca sync=1.
    """

    def __init__(self, db: PesajeDatabase) -> None:
        self.db = db

    def restore(
        self,
        *,
        desde: Optional[str] = None,
        hasta: Optional[str] = None,
        incluir_inactivos: bool = True,
        max_paginas: int = 200,
    ) -> PullResult:
        if not SYNC_TOKEN:
            return PullResult(ok=False, mensaje="Falta PRECIX_SYNC_TOKEN")
        if not SYNC_PULL_URL:
            return PullResult(ok=False, mensaje="Falta PRECIX_SYNC_PULL_URL")

        result = PullResult(ok=True)
        cursor: Optional[str] = None
        maestros_aplicados = False

        for _ in range(max(1, max_paginas)):
            page, status, err = self._get_page(
                cursor=cursor,
                desde=desde,
                hasta=hasta,
                incluir_inactivos=incluir_inactivos,
            )
            if err:
                result.ok = False
                result.http_status = status
                result.mensaje = err
                result.errores.append(err)
                break

            assert page is not None
            result.paginas += 1
            if page.get("total") is not None:
                try:
                    result.total_remoto = int(page["total"])
                except (TypeError, ValueError):
                    pass

            if not maestros_aplicados:
                result.maestros_ok += self._aplicar_maestros(page.get("maestros"))
                maestros_aplicados = True

            items = page.get("items") or page.get("pesajes") or []
            if not isinstance(items, list):
                result.ok = False
                result.mensaje = "Respuesta sin lista items/pesajes"
                break

            for raw in items:
                if not isinstance(raw, dict):
                    result.omitidos += 1
                    continue
                try:
                    accion = self.db.upsert_pesaje_remoto(raw)
                except Exception as exc:  # noqa: BLE001
                    result.omitidos += 1
                    result.errores.append(str(exc)[:160])
                    continue
                if accion == "insertado":
                    result.insertados += 1
                elif accion == "actualizado":
                    result.actualizados += 1
                else:
                    result.omitidos += 1

            next_cursor = page.get("next_cursor")
            if next_cursor in (None, "", False):
                break
            cursor = str(next_cursor)

        if result.ok and not result.mensaje:
            result.mensaje = (
                f"+{result.insertados} · ~{result.actualizados} · "
                f"omitidos {result.omitidos} · maestros {result.maestros_ok}"
            )
        logger.info(
            "Pull restore: ok=%s insertados=%s actualizados=%s paginas=%s msg=%s",
            result.ok,
            result.insertados,
            result.actualizados,
            result.paginas,
            result.mensaje,
        )
        return result

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {SYNC_TOKEN}",
        }
        if SYNC_PLANTA:
            headers["X-Precix-Planta"] = SYNC_PLANTA
        return headers

    def _get_page(
        self,
        *,
        cursor: Optional[str],
        desde: Optional[str],
        hasta: Optional[str],
        incluir_inactivos: bool,
    ) -> tuple[Optional[dict[str, Any]], int, str]:
        params: dict[str, str] = {
            "planta": SYNC_PLANTA,
            "limit": str(max(1, min(SYNC_PULL_PAGE_SIZE, 1000))),
            "incluir_inactivos": "1" if incluir_inactivos else "0",
        }
        if desde:
            params["desde"] = desde
        if hasta:
            params["hasta"] = hasta
        if cursor:
            params["cursor"] = cursor

        url = f"{SYNC_PULL_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                raw = resp.read().decode("utf-8", errors="replace")
                if not (200 <= status < 300):
                    return None, status, f"HTTP {status}"
                data = json.loads(raw) if raw.strip() else {}
                if not isinstance(data, dict):
                    return None, status, "JSON raíz no es objeto"
                if data.get("ok") is False:
                    return None, status, str(data.get("error") or "ok=false")
                return data, status, ""
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # noqa: BLE001
                pass
            msg = f"HTTP {exc.code}" + (f" · {detail}" if detail else "")
            return None, int(exc.code), msg
        except urllib.error.URLError as exc:
            return None, 0, str(exc.reason)
        except json.JSONDecodeError as exc:
            return None, 0, f"JSON inválido: {exc}"
        except Exception as exc:  # noqa: BLE001
            return None, 0, str(exc)

    def _aplicar_maestros(self, maestros: Any) -> int:
        if not isinstance(maestros, dict):
            return 0
        n = 0
        for key, tipo in _MAESTRO_KEYS.items():
            lista = maestros.get(key)
            if not isinstance(lista, list):
                continue
            for entry in lista:
                valor, codigo, activo = _parse_maestro_entry(entry)
                if not valor:
                    continue
                accion = self.db.upsert_maestro_remoto(
                    tipo, valor=valor, codigo=codigo, activo=activo
                )
                if accion in ("insertado", "actualizado"):
                    n += 1
        return n


def _parse_maestro_entry(entry: Any) -> tuple[str, str, int]:
    if isinstance(entry, str):
        return entry.strip(), "", 1
    if not isinstance(entry, dict):
        return "", "", 0
    valor = str(
        entry.get("valor")
        or entry.get("nombre")
        or entry.get("valor_mm")
        or ""
    ).strip()
    codigo = str(entry.get("codigo") or "").strip()
    activo_raw = entry.get("activo", 1)
    try:
        activo = 1 if int(activo_raw) else 0
    except (TypeError, ValueError):
        activo = 1
    return valor, codigo, activo
