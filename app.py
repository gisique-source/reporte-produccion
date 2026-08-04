"""
Precix-Weight — Monitor de balanza, etiquetas y registros Gexim.
Punto de entrada. Ejecutar: python app.py

Sync nube (opcional):
  set PRECIX_SYNC_ENABLED=1
  set PRECIX_SYNC_URL=https://tu-api/pesajes
"""

from ui import PrecixApp

if __name__ == "__main__":
    app = PrecixApp()
    app.mainloop()
