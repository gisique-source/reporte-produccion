"""
Precix-Weight — Monitor de balanza, etiquetas y registros Gexim.
Punto de entrada. Ejecutar: python app.py

Sync nube (sistema integrado):
  set PRECIX_SYNC_ENABLED=1
  set PRECIX_SYNC_URL=https://tu-dominio.vercel.app/api/v1/precix/pesajes
  set PRECIX_SYNC_TOKEN=el-mismo-token-que-en-Vercel
  set PRECIX_DEFAULT_PLANTA=ATE-EXTRUSORA-1
  set PRECIX_SYNC_INTERVAL_MIN=5
"""

from ui import PrecixApp

if __name__ == "__main__":
    app = PrecixApp()
    app.mainloop()
