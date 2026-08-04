"""Sincronización en segundo plano: SQLite local → API nube (Bearer)."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from config import (
    SYNC_API_URL,
    SYNC_ENABLED,
    SYNC_INTERVAL_S,
    SYNC_PLANTA,
    SYNC_TIMEOUT_S,
    SYNC_TOKEN,
)
from db import PesajeDatabase
from models import RegistroPesaje

logger = logging.getLogger(__name__)


@dataclass
class _PostResult:
    ok: bool
    http_status: int = 0
    id_remoto: str = ""
    duplicado: bool = False
    mensaje: str = ""


class SyncWorker:
    """
    Hilo daemon: cada N segundos (configurable) envía registros con
    estado_sincronizado = 0. Auth: Authorization Bearer + planta.
    Cada intento se registra en sync_auditoria (éxito o error).
    """

    def __init__(self, db: PesajeDatabase) -> None:
        self.db = db
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_error: str = ""
        self.last_ok_at: str = ""

    def start(self) -> None:
        if not SYNC_ENABLED:
            logger.info("Sync deshabilitado (PRECIX_SYNC_ENABLED!=1)")
            return
        if not SYNC_TOKEN:
            self.last_error = "Falta PRECIX_SYNC_TOKEN"
            logger.warning(
                "Sync habilitado pero sin PRECIX_SYNC_TOKEN — la API responderá 401"
            )
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="SyncWorker", daemon=True
        )
        self._thread.start()
        logger.info(
            "SyncWorker iniciado · cada %ss · planta=%s · url=%s",
            SYNC_INTERVAL_S,
            SYNC_PLANTA,
            SYNC_API_URL,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def sync_now(self) -> int:
        """Un ciclo manual; retorna cantidad marcada como sincronizada."""
        return self._flush_pending()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._flush_pending()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                logger.debug("Sync ciclo error: %s", exc)
            self._stop.wait(SYNC_INTERVAL_S)

    def _flush_pending(self) -> int:
        if SYNC_ENABLED and not SYNC_TOKEN:
            self.last_error = "Falta PRECIX_SYNC_TOKEN"
            return 0

        pendientes = self.db.pendientes()
        if not pendientes:
            return 0

        ok_ids: list[int] = []
        for reg in pendientes:
            result = self._post(reg)
            self._auditar(reg, result)
            if result.ok:
                ok_ids.append(reg.id)
                self.last_error = ""
            else:
                self.last_error = result.mensaje or f"HTTP {result.http_status}"
                break

        if ok_ids:
            self.db.marcar_sincronizados(ok_ids)
            from datetime import datetime

            self.last_ok_at = datetime.now().strftime("%H:%M:%S")
        return len(ok_ids)

    def _auditar(self, reg: RegistroPesaje, result: _PostResult) -> None:
        try:
            self.db.registrar_auditoria_sync(
                pesaje_id=reg.id,
                ok=result.ok,
                http_status=result.http_status,
                id_remoto=result.id_remoto,
                duplicado=result.duplicado,
                planta=SYNC_PLANTA,
                nro_fardo=str(reg.nro_fardo),
                lote=reg.lote,
                cliente=reg.cliente,
                color=reg.color,
                peso_bruto=reg.peso_bruto,
                peso_neto=reg.peso_neto,
                fecha_hora_pesaje=reg.fecha_hora,
                mensaje=result.mensaje,
                url=SYNC_API_URL,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo registrar auditoría: %s", exc)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if SYNC_TOKEN:
            headers["Authorization"] = f"Bearer {SYNC_TOKEN}"
        if SYNC_PLANTA:
            headers["X-Precix-Planta"] = SYNC_PLANTA
        return headers

    def _enrich_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        if SYNC_PLANTA and "planta" not in data:
            data["planta"] = SYNC_PLANTA
        return data

    def _post(self, reg: RegistroPesaje) -> _PostResult:
        payload = self._enrich_payload(reg.to_sync_payload())
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SYNC_API_URL,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                if not (200 <= status < 300):
                    return _PostResult(
                        ok=False,
                        http_status=status,
                        mensaje=f"HTTP {status}",
                    )
                id_remoto = ""
                duplicado = status == 200
                mensaje = "OK"
                try:
                    raw = resp.read().decode("utf-8", errors="replace")
                    if raw.strip():
                        data = json.loads(raw)
                        if isinstance(data, dict):
                            if data.get("ok") is False:
                                return _PostResult(
                                    ok=False,
                                    http_status=status,
                                    mensaje=str(data.get("error") or "ok=false"),
                                )
                            id_remoto = str(data.get("id_remoto") or "")
                            if "duplicado" in data:
                                duplicado = bool(data.get("duplicado"))
                            mensaje = "upsert" if duplicado else "creado"
                except (json.JSONDecodeError, UnicodeError):
                    pass
                return _PostResult(
                    ok=True,
                    http_status=status,
                    id_remoto=id_remoto,
                    duplicado=duplicado,
                    mensaje=mensaje,
                )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # noqa: BLE001
                pass
            msg = f"HTTP {exc.code}" + (f" · {detail}" if detail else "")
            return _PostResult(ok=False, http_status=int(exc.code), mensaje=msg)
        except urllib.error.URLError as exc:
            return _PostResult(ok=False, http_status=0, mensaje=str(exc.reason))
        except Exception as exc:  # noqa: BLE001
            return _PostResult(ok=False, http_status=0, mensaje=str(exc))
