"""Configuración global: serie, empresa, página A4, DB y sync."""

from __future__ import annotations

import os
import serial

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


def _sync_interval_seconds() -> int:
    """
    Intervalo entre ciclos de sync.
    Preferir PRECIX_SYNC_INTERVAL_MIN (minutos); si no, PRECIX_SYNC_INTERVAL_S;
    default 1 minuto.
    """
    raw_min = os.environ.get("PRECIX_SYNC_INTERVAL_MIN")
    raw_sec = os.environ.get("PRECIX_SYNC_INTERVAL_S")
    try:
        if raw_min is not None and str(raw_min).strip() != "":
            return max(15, int(float(str(raw_min).replace(",", ".")) * 60))
        if raw_sec is not None and str(raw_sec).strip() != "":
            return max(15, int(float(str(raw_sec).replace(",", "."))))
    except ValueError:
        pass
    return 60  # 1 minuto


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
