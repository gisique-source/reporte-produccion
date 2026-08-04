"""Lector RS-232 del indicador Precix-Weight (hilo secundario)."""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

import serial

from config import (
    BAUDRATE,
    BYTESIZE,
    PARITY,
    PORT,
    RECONNECT_DELAY_S,
    SERIAL_TIMEOUT,
    STOPBITS,
)

WEIGHT_RE = re.compile(
    r"(?P<status>ST|US)\s*,\s*GS\s*(?P<weight>[+-]?\d+(?:[.,]\d+)?)\s*,?\s*(?P<unit>kg)?",
    re.IGNORECASE,
)


class SerialWeightReader:
    """Lee el indicador Precix-Weight en un hilo daemon sin bloquear la GUI."""

    def __init__(self, port: str = PORT) -> None:
        self.port = port
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.weight: Optional[float] = None
        self.unit: str = "kg"
        self.status: str = "--"
        self.connected: bool = False
        self.last_error: str = ""
        self.raw_line: str = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="SerialWeightReader", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "weight": self.weight,
                "unit": self.unit,
                "status": self.status,
                "connected": self.connected,
                "last_error": self.last_error,
                "raw_line": self.raw_line,
            }

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _parse_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        match = WEIGHT_RE.search(line)
        if not match:
            return
        weight_txt = match.group("weight").replace(",", ".")
        try:
            weight = float(weight_txt)
        except ValueError:
            return
        self._set(
            weight=weight,
            unit=(match.group("unit") or "kg").lower(),
            status=match.group("status").upper(),
            raw_line=line,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            ser: Optional[serial.Serial] = None
            try:
                ser = serial.Serial(
                    port=self.port,
                    baudrate=BAUDRATE,
                    bytesize=BYTESIZE,
                    parity=PARITY,
                    stopbits=STOPBITS,
                    timeout=SERIAL_TIMEOUT,
                )
                self._set(connected=True, last_error="")
                buffer = ""
                while not self._stop.is_set():
                    chunk = ser.read(ser.in_waiting or 1)
                    if not chunk:
                        continue
                    buffer += chunk.decode("ascii", errors="ignore")
                    while "\n" in buffer or "\r" in buffer:
                        for sep in ("\n", "\r"):
                            if sep in buffer:
                                line, _, buffer = buffer.partition(sep)
                                self._parse_line(line)
                                break
            except serial.SerialException as exc:
                self._set(connected=False, last_error=str(exc), status="--")
            except Exception as exc:  # noqa: BLE001
                self._set(connected=False, last_error=str(exc), status="--")
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:  # noqa: BLE001
                        pass
                self._set(connected=False)

            if not self._stop.is_set():
                time.sleep(RECONNECT_DELAY_S)
