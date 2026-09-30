"""Cliente HTTP de paradas: catálogo y push de eventos."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import (
    PARADAS_API_BASE,
    PARADAS_AREA,
    PARADAS_PLANTA,
    PARADAS_TOKEN,
    SYNC_TIMEOUT_S,
)
from paradas_store import ParadaLocal, ParadasStore


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {PARADAS_TOKEN}",
        "X-Paradas-Planta": PARADAS_PLANTA,
        "X-Precix-Planta": PARADAS_PLANTA,
    }
    return headers


def _leer(resp) -> dict:
    raw = resp.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"error": raw[:240]}
    return data if isinstance(data, dict) else {"error": "respuesta no JSON"}


def bajar_catalogo(store: ParadasStore) -> tuple[bool, str]:
    if not PARADAS_TOKEN:
        return False, "Falta PRECIX_SYNC_TOKEN para bajar tipos de parada."
    params = urllib.parse.urlencode(
        {"planta": PARADAS_PLANTA, "area": PARADAS_AREA}
    )
    url = f"{PARADAS_API_BASE}/catalogo?{params}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
            data = _leer(resp)
    except urllib.error.HTTPError as exc:
        body = _leer(exc)
        return False, str(body.get("error") or exc.reason or exc.code)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if not data.get("ok", True) and data.get("error"):
        return False, str(data["error"])
    store.reemplazar_catalogo(
        list(data.get("maquinaria") or []),
        list(data.get("tipos") or []),
    )
    return True, ""


def push_evento(store: ParadasStore, parada: ParadaLocal) -> tuple[bool, str]:
    if not PARADAS_TOKEN:
        store.marcar_sync(
            parada.id, ok=False, http=0, error="Falta PRECIX_SYNC_TOKEN"
        )
        return False, "Falta PRECIX_SYNC_TOKEN"
    body: dict[str, Any] = {
        "id_local": parada.id,
        "planta": PARADAS_PLANTA,
        "inicio": parada.inicio,
        "fin": (parada.fin or "").strip() or None,
        "turno": parada.turno or "",
        "operario": parada.operario or "",
        "observaciones": parada.observaciones or "",
        "activo": parada.activo,
    }
    payload = json.dumps(body).encode("utf-8")
    headers = _headers()
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{PARADAS_API_BASE}/eventos",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
            data = _leer(resp)
            http = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        data = _leer(exc)
        http = int(exc.code or 0)
        msg = str(data.get("error") or exc.reason or http)
        if data.get("codigo"):
            msg = f"{data['codigo']}: {msg}"
        store.marcar_sync(parada.id, ok=False, http=http, error=msg)
        return False, msg
    except Exception as exc:  # noqa: BLE001
        store.marcar_sync(parada.id, ok=False, http=0, error=str(exc))
        return False, str(exc)

    if data.get("ok") is False:
        msg = str(data.get("error") or "rechazado")
        store.marcar_sync(parada.id, ok=False, http=http, error=msg)
        return False, msg
    store.marcar_sync(
        parada.id,
        ok=True,
        http=http,
        id_remoto=str(data.get("id_remoto") or ""),
    )
    return True, ""


def bajar_clasificacion(store: ParadasStore, *, dias: int = 31) -> tuple[bool, str]:
    """Trae de la nube máquina y tipo ya clasificados. No pisa inicio/fin locales pendientes."""
    if not PARADAS_TOKEN:
        return False, "Falta PRECIX_SYNC_TOKEN"
    from datetime import date, timedelta

    hoy = date.today()
    desde = (hoy - timedelta(days=max(1, dias))).isoformat()
    params = urllib.parse.urlencode(
        {
            "planta": PARADAS_PLANTA,
            "desde": desde,
            "hasta": hoy.isoformat(),
            "limit": 200,
            "incluir_inactivos": 1,
        }
    )
    url = f"{PARADAS_API_BASE}/eventos?{params}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
            data = _leer(resp)
    except urllib.error.HTTPError as exc:
        body = _leer(exc)
        return False, str(body.get("error") or exc.reason or exc.code)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if data.get("ok") is False:
        return False, str(data.get("error") or "rechazado")
    items = data.get("items") or []
    if not isinstance(items, list):
        return False, "respuesta sin items"
    for item in items:
        if isinstance(item, dict):
            store.aplicar_clasificacion(item)
    return True, ""


def flush_pendientes(store: ParadasStore) -> tuple[int, int]:
    ok_n = err_n = 0
    for parada in store.pendientes():
        ok, _msg = push_evento(store, parada)
        if ok:
            ok_n += 1
        else:
            err_n += 1
    return ok_n, err_n


def turno_actual(hora: Optional[int] = None) -> str:
    from datetime import datetime

    h = datetime.now().hour if hora is None else hora
    if 6 <= h < 14:
        return "Mañana"
    if 14 <= h < 22:
        return "Tarde"
    return "Noche"
