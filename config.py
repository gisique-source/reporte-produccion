"""Configuración global: serie, empresa, página A4, DB y sync."""

from __future__ import annotations

import os
import serial

# Carga .env local (Linux/dev) sin depender de python-dotenv.
# No sobrescribe variables ya definidas en el entorno (p. ej. Windows User).
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_dotenv(path: str = _ENV_FILE) -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if not key or key in os.environ:
                    continue
                val = val.strip().strip("'").strip('"')
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

# ---------------------------------------------------------------------------
# Puerto serie Precix-Weight
# ---------------------------------------------------------------------------
PORT = "COM1"
BAUDRATE = 9600
BYTESIZE = serial.EIGHTBITS
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
SERIAL_TIMEOUT = 0.5
RECONNECT_DELAY_S = 2.0
UI_REFRESH_MS = 500

# Taras por defecto (kg) — editables en UI
# P.Bruto = P.Total − Tara Carreta
# P.Neto  = P.Total − Tara Carreta − Tara Fardo
TARA_CARRETA_KG = 121.0
TARA_FARDO_KG = 2.4

# ---------------------------------------------------------------------------
# Datos fijos empresa
# ---------------------------------------------------------------------------
EMPRESA = "Gexim S.A.C."
PRODUCTO = "Fibra cortada de poliéster RPET"
DIRECCION = "Av. Tomás Alva Edison N° 215 Urb. Ind. Santa Rosa - Ate Lima - Perú"
TELEFONO = "(511) 480-0034"
EMAIL = "info@gexim.com.pe"
WEB = "www.gexim.com.pe"

# ---------------------------------------------------------------------------
# SQLite local-first + sync nube
# ---------------------------------------------------------------------------
# DB junto al exe / script (no dentro de _MEIPASS, que es de solo lectura)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_APP_DIR, "pesajes.db")

SYNC_API_URL = os.environ.get(
    "PRECIX_SYNC_URL",
    "https://example.com/api/v1/precix/pesajes",
)
SYNC_ENABLED = os.environ.get("PRECIX_SYNC_ENABLED", "0") == "1"
SYNC_TOKEN = (os.environ.get("PRECIX_SYNC_TOKEN") or "").strip()
# Código de planta (opcional en body/header; la API puede usar PRECIX_DEFAULT_PLANTA)
SYNC_PLANTA = (
    os.environ.get("PRECIX_PLANTA")
    or os.environ.get("PRECIX_DEFAULT_PLANTA")
    or "ATE-EXTRUSORA-1"
).strip()
SYNC_TIMEOUT_S = int(os.environ.get("PRECIX_SYNC_TIMEOUT_S", "10") or "10")


def _default_pull_url(push_url: str) -> str:
    """
    Deriva GET export desde el POST de subida.
    .../pesajes  →  .../pesajes/export
    """
    base = (push_url or "").rstrip("/")
    if not base:
        return "https://example.com/api/v1/precix/pesajes/export"
    if base.endswith("/export"):
        return base
    return f"{base}/export"


SYNC_PULL_URL = (
    os.environ.get("PRECIX_SYNC_PULL_URL") or _default_pull_url(SYNC_API_URL)
).strip()
# Página máxima pedida al export (el servidor puede devolver menos)
SYNC_PULL_PAGE_SIZE = int(os.environ.get("PRECIX_SYNC_PULL_PAGE_SIZE", "500") or "500")


def _sync_interval_seconds() -> int:
    """
    Cron interno mientras la app está abierta.
    PRECIX_SYNC_INTERVAL_MIN (minutos) o PRECIX_SYNC_INTERVAL_S; default 5 min.
    """
    raw_min = os.environ.get("PRECIX_SYNC_INTERVAL_MIN")
    raw_sec = os.environ.get("PRECIX_SYNC_INTERVAL_S")
    try:
        if raw_min is not None and str(raw_min).strip() != "":
            return max(60, int(float(str(raw_min).replace(",", ".")) * 60))
        if raw_sec is not None and str(raw_sec).strip() != "":
            return max(60, int(float(str(raw_sec).replace(",", "."))))
    except ValueError:
        pass
    return 5 * 60


SYNC_INTERVAL_S = _sync_interval_seconds()

# Modo correlativo de Nº Fardo (persistido también en SQLite)
# "continuar" = último global + 1 (incluye día anterior)
# "reiniciar" = serie desde 1
MODO_FARDO_CONTINUAR = "continuar"
MODO_FARDO_REINICIAR = "reiniciar"
MODO_FARDO_DEFAULT = MODO_FARDO_CONTINUAR
PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
MARGIN_TOP_MM = 15.0
MARGIN_LEFT_MM = 11.0
MARGIN_RIGHT_MM = 5.0
MARGIN_BOTTOM_MM = 5.0

LABEL_COLS = 10
LABEL_ROWS = 21
LABEL_WIDTH_MM = LABEL_COLS * 15.6
LABEL_HEIGHT_MM = LABEL_ROWS * 5.29
LABEL_ORIGIN_X_MM = MARGIN_LEFT_MM
LABEL_ORIGIN_Y_MM = MARGIN_TOP_MM

LABEL_LINE_RGB = (0x1A, 0x3A, 0x6E)
LABEL_TEXT_RGB = (0x1A, 0x3A, 0x6E)
