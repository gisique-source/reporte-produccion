"""Sincronización en segundo plano: SQLite local → API nube."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Optional

from config import SYNC_API_URL, SYNC_ENABLED, SYNC_INTERVAL_S, SYNC_TIMEOUT_S
from db import PesajeDatabase

logger = logging.getLogger(__name__)


class SyncWorker:
    """
    Hilo daemon: cada N segundos envía registros con estado_sincronizado = 0.
    Fallos de red → reintento silencioso en el siguiente ciclo (no bloquea UI).
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
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="SyncWorker", daemon=True
        )
        self._thread.start()

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
        pendientes = self.db.pendientes()
        if not pendientes:
            return 0

        ok_ids: list[int] = []
        for reg in pendientes:
            if self._post(reg.to_sync_payload()):
                ok_ids.append(reg.id)
            else:
                # Conservar orden: si uno falla, reintentar el resto en el próximo ciclo
                break

        if ok_ids:
            self.db.marcar_sincronizados(ok_ids)
            from datetime import datetime

            self.last_ok_at = datetime.now().strftime("%H:%M:%S")
            self.last_error = ""
        return len(ok_ids)

    def _post(self, payload: dict) -> bool:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SYNC_API_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=SYNC_TIMEOUT_S) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return False
        except urllib.error.URLError as exc:
            self.last_error = str(exc.reason)
            return False
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            return False
