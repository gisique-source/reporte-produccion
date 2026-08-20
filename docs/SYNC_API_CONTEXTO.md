# Precix-Weight → API nube — Contexto de sincronización

Documento de contexto para implementar / conectar el sistema integrado en la nube con la app de planta **Precix-Weight** (extrusora Gexim).

**App local:** SQLite first (`pesajes.db`) + hilo `SyncWorker` que hace `POST` JSON periódico.  
**Repo:** `precix-weight` · módulos clave: `sync.py`, `models.py`, `db.py`, `catalog.py`, `config.py`.

---

## 1. Objetivo

Cada pesaje/fardo registrado en la PC de planta debe llegar a la API del sistema integrado (ERP / producción / nube) de forma **asíncrona, idempotente y tolerante a cortes de red**.

Flujo:

```
[Balanza RS-232] → [Precix-Weight UI] → [SQLite local]
                                            ↓  (estado_sincronizado = 0)
                                     [SyncWorker cada 30s]
                                            ↓  POST application/json
                                     [API sistema integrado]
                                            ↓  HTTP 2xx
                              marca local estado_sincronizado = 1
```

La UI **no espera** a la nube para imprimir ni guardar.

---

## 2. Configuración en la PC de planta (cliente)

Variables de entorno (Windows / Vercel del sistema integrado):

| Variable | Valores | Default | Descripción |
|----------|---------|---------|-------------|
| `PRECIX_SYNC_ENABLED` | `1` / `0` | — | Ya no es necesario: el cron corre mientras la app está abierta |
| `PRECIX_SYNC_URL` | URL absoluta | (ejemplo) | `POST /api/v1/precix/pesajes` |
| `PRECIX_SYNC_TOKEN` | string | _(vacío)_ | **Obligatorio** si sync ON → `Authorization: Bearer …` |
| `PRECIX_DEFAULT_PLANTA` o `PRECIX_PLANTA` | string | `ATE-EXTRUSORA-1` | Planta en body `planta` + header `X-Precix-Planta` |
| `PRECIX_SYNC_INTERVAL_MIN` | número | `5` | Minutos del cron interno (mín. 1 min) |
| `PRECIX_SYNC_INTERVAL_S` | número | — | Alternativa en segundos (si no hay `_MIN`) |
| `PRECIX_SYNC_TIMEOUT_S` | número | `10` | Timeout HTTP por request |

Ejemplo PowerShell (sesión actual):

```powershell
$env:PRECIX_SYNC_ENABLED = "1"
$env:PRECIX_SYNC_URL = "https://tu-dominio.vercel.app/api/v1/precix/pesajes"
$env:PRECIX_SYNC_TOKEN = "el-mismo-token-que-en-Vercel"
$env:PRECIX_DEFAULT_PLANTA = "ATE-EXTRUSORA-1"
$env:PRECIX_SYNC_INTERVAL_MIN = "1"
python app.py
```

Ver también `.env.sync.example` en la raíz del repo.

**UI del sistema integrado:** Producción → **Reportes de producción (pesajes)**  
ruta: `/operaciones/produccion/pesajes` (listado del día, filtros fecha/lote/cliente/planta, totales).

Migración SQL (lado nube): `supabase/migrations/20250804150000_precix_pesajes.sql`

> El cliente envía `Authorization: Bearer {PRECIX_SYNC_TOKEN}`. Sin token la API responde **401**.

---

## 3. Contrato HTTP actual (lo que ya envía Precix)

### 3.1 Endpoint

```http
POST {PRECIX_SYNC_URL}
Content-Type: application/json
Accept: application/json
Authorization: Bearer {PRECIX_SYNC_TOKEN}
X-Precix-Planta: {PRECIX_DEFAULT_PLANTA}
```

- Un **registro por request** (no batch todavía).
- El body incluye además `"planta": "ATE-EXTRUSORA-1"` cuando está configurada.
- Orden: por `id` local ascendente.
- Si un POST falla, **corta el lote** y reintenta ese registro en el próximo ciclo.
- Éxito = status HTTP **200** (upsert) o **201** (create). Body típico:

```json
{ "ok": true, "id_remoto": "uuid", "id_local": 42, "duplicado": false }
```

### 3.2 Body JSON (payload real — `RegistroPesaje.to_sync_payload`)

```json
{
  "id_local": 42,
  "fecha_hora": "2026-08-04 14:35:22",
  "cliente": "Catalina Peru SAC",
  "lote": "L-2408-01",
  "color": "Marron 580",
  "denier": "4.0",
  "corte": "65",
  "nro_fardo": "11",
  "peso_bruto": 228.6,
  "peso_neto": 226.2,
  "operario": "Juan Perez",
  "peso_total": 349.6,
  "tara_carreta": 121.0,
  "tara_fardo": 2.4,
  "activo": 1
}
```

### 3.3 Campos — tipado y semántica

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `id_local` | integer | sí | PK SQLite en la PC. **Clave de idempotencia** junto a `origen`/`planta` |
| `fecha_hora` | string | sí | `YYYY-MM-DD HH:MM:SS` (hora local de planta) |
| `cliente` | string | sí | Texto maestro (nombre), no ID remoto |
| `lote` | string | sí | Lote de producción |
| `color` | string | sí | Nombre color |
| `denier` | string | sí | Dn (ej. `"4.0"`) |
| `corte` | string | sí | mm (ej. `"65"`) |
| `nro_fardo` | string | sí | Correlativo como texto numérico |
| `peso_bruto` | number | sí | kg · `P.Total − Tara carreta` |
| `peso_neto` | number | sí | kg · `P.Total − Tara carreta − Tara fardo` |
| `operario` | string | no | Puede ser `""` |
| `peso_total` | number | no | kg en báscula (bruto de báscula) |
| `tara_carreta` | number | no | kg (default planta ~121) |
| `tara_fardo` | number | no | kg (default planta ~2.4) |
| `activo` | integer | sí | `1` activo · `0` soft-delete (oculto) |

**Código de barras local (no viaja hoy en el payload):** `{lote}-{nro_fardo}`  
Ej.: `L-2408-01-11`. Conviene guardarlo o regenerarlo igual en la nube.

**Fórmulas:**

```text
peso_bruto = max(peso_total - tara_carreta, 0)
peso_neto  = max(peso_total - tara_carreta - tara_fardo, 0)
```

### 3.4 Respuestas esperadas por el cliente

| HTTP | Comportamiento cliente |
|------|------------------------|
| `2xx` | Marca `estado_sincronizado = 1` en SQLite |
| `4xx/5xx` | Deja pendiente; muestra `HTTP {code}` en badge |
| Timeout / red | Reintento en el siguiente ciclo (`SYNC_INTERVAL_S`) |

Respuesta sugerida (opcional, no parseada aún):

```json
{
  "ok": true,
  "id_remoto": "uuid-o-int",
  "id_local": 42,
  "duplicado": false
}
```

---

## 4. Entidades que debe modelar el sistema integrado

### 4.1 Entidad principal: **Pesaje / Fardo** (transaccional)

Tabla sugerida `precix_pesajes` (o equivalente en tu dominio):

| Columna sugerida | Origen payload | Notas |
|------------------|----------------|-------|
| `id` | (generado nube) | PK remota |
| `planta_codigo` | config API / header | Ej. `EXTRUSORA-1` — **obligatorio multi-PC** |
| `id_local` | `id_local` | Único por planta |
| `fecha_hora` | `fecha_hora` | Timestamp producción |
| `fecha` | derivado | `DATE(fecha_hora)` para reportes |
| `cliente` | `cliente` | Texto o FK a maestro |
| `lote` | `lote` | |
| `color` | `color` | |
| `denier` | `denier` | |
| `corte` | `corte` | |
| `nro_fardo` | `nro_fardo` | |
| `peso_total` | `peso_total` | |
| `tara_carreta` | `tara_carreta` | |
| `tara_fardo` | `tara_fardo` | |
| `peso_bruto` | `peso_bruto` | |
| `peso_neto` | `peso_neto` | |
| `operario` | `operario` | |
| `codigo_barras` | derivado | `{lote}-{nro_fardo}` |
| `activo` | `activo` | Soft-delete |
| `recibido_en` | server | `NOW()` |
| `raw_json` | opcional | auditoría |

**Índice único recomendado:**

```text
UNIQUE (planta_codigo, id_local)
```

Así un reenvío del mismo fardo hace **UPSERT** (idempotente), no duplica filas.

Lógica API sugerida:

1. Validar JSON.
2. Upsert por `(planta, id_local)`.
3. Si el registro ya existía y cambian pesos/datos → actualizar (edición en planta re-marca sync = 0).
4. Responder `2xx`.

### 4.2 Entidades maestro (catálogo local — sync opcional fase 2)

En planta existen tablas SQLite (soft-delete, **sin DELETE físico**):

| Entidad | Tabla local | Campo valor | Uso en pesaje |
|---------|-------------|-------------|---------------|
| Cliente | `clientes` | `nombre` | `cliente` |
| Color | `colores` | `nombre` | `color` |
| Denier | `deniers` | `valor` | `denier` |
| Corte (mm) | `cortes` | `valor_mm` | `corte` |
| Operario | `operarios` | `nombre` | `operario` |

Campos comunes maestros: `id`, valor, `codigo` (opcional), `activo`, `creado_en`, `actualizado_en`.

**Hoy la app NO sincroniza maestros** a la nube. El pesaje manda los **textos ya resueltos**.  
En la API puedes:

- **Opción A (simple):** guardar solo strings en el pesaje.
- **Opción B (normalizado):** upsert maestros por nombre normalizado y guardar FK.

Endpoints sugeridos fase 2 (si quieres catálogo bidireccional):

```http
POST /api/v1/precix/maestros/{tipo}   # tipo = cliente|color|denier|corte|operario
GET  /api/v1/precix/maestros/{tipo}
```

### 4.3 Entidad auxiliar: **Planta / Origen**

Para varias PCs / líneas:

| Campo | Ejemplo |
|-------|---------|
| `codigo` | `ATE-EXTRUSORA-1` |
| `nombre` | Extrusora Ate |
| `timezone` | `America/Lima` |

Hoy no viaja en el JSON. Recomendación: fijarlo en la API por token/API-key de esa planta, o agregar al payload:

```json
"planta": "ATE-EXTRUSORA-1"
```

---

## 5. Comportamiento local que la API debe respetar

| Evento en planta | `estado_sincronizado` | `activo` | ¿Se envía hoy? |
|------------------|----------------------|----------|----------------|
| Nuevo pesaje / imprimir | `0` | `1` | Sí |
| Editar fardo (GUARDAR) | vuelve a `0` | `1` | Sí (UPSERT) |
| Ocultar (soft-delete) | `0` | `0` | **No** (filtro actual: solo `activo = 1`) |
| Restaurar oculto | `0` | `1` | Sí |

**Gap conocido:** ocultar un fardo ya sincronizado **no notifica** a la nube todavía.  
Al implementar la API, deja listo el campo `activo` y un upsert; luego se ampliará el cliente para empujar también bajas (`activo = 0`).

---

## 6. API mínima a implementar (checklist)

### Debe existir ya (para conectar Precix hoy)

- [ ] `POST /api/v1/precix/pesajes` (o la URL que pongas en `PRECIX_SYNC_URL`)
- [ ] Acepta el JSON de §3.2
- [ ] Idempotencia por `(planta, id_local)`
- [ ] Responde `2xx` si persistió / ya existía
- [ ] HTTPS en producción
- [ ] Log de recepción (`recibido_en`, body)

### Recomendado de inmediato

- [ ] Auth: Bearer o API Key por planta
- [ ] Validación de pesos (`peso_neto <= peso_bruto <= peso_total` con tolerancia)
- [ ] Endpoint health: `GET /api/v1/precix/health` → `{ "ok": true }`
- [ ] Identificar planta desde el token (no confiar solo en body)

### Fase 2 (opcional)

- [ ] Batch: `POST /api/v1/precix/pesajes/batch` con array
- [ ] Sync de soft-delete (`activo: 0`)
- [ ] Sync de maestros
- [ ] `GET` consulta por fecha / lote para dashboards
- [ ] **Restauración planta:** `GET /api/v1/precix/pesajes/export` — ver `docs/SYNC_PULL_API.md` (cliente ya listo)
- [ ] Webhook inverso (nube → planta) — no requerido por el cliente actual

---

## 7. Auth (cliente + API)

Header enviado por Precix:

```http
Authorization: Bearer <PRECIX_SYNC_TOKEN>
Content-Type: application/json
X-Precix-Planta: ATE-EXTRUSORA-1
```

Env en planta:

```text
PRECIX_SYNC_TOKEN=...
PRECIX_DEFAULT_PLANTA=ATE-EXTRUSORA-1
```

Sin token → la API responde **401** y el badge muestra el error.

---

## 8. Ejemplo curl (prueba manual de tu API)

```bash
curl -X POST "https://tu-dominio.com/api/v1/precix/pesajes" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d "{
    \"id_local\": 1,
    \"fecha_hora\": \"2026-08-04 15:00:00\",
    \"cliente\": \"Catalina Peru SAC\",
    \"lote\": \"L-TEST\",
    \"color\": \"Marron 580\",
    \"denier\": \"4.0\",
    \"corte\": \"65\",
    \"nro_fardo\": \"1\",
    \"peso_bruto\": 228.6,
    \"peso_neto\": 226.2,
    \"operario\": \"DEMO\",
    \"peso_total\": 349.6,
    \"tara_carreta\": 121.0,
    \"tara_fardo\": 2.4,
    \"activo\": 1
  }"
```

Reenvía el mismo `id_local` → no debe crear duplicado.

---

## 9. Pseudocódigo servidor (referencia)

```text
function UpsertPesaje(body, planta):
  validate(body)
  existing = find(planta, body.id_local)
  if existing:
    update(existing, body)   # incluye activo, pesos, maestros texto
    return 200 { ok, id_remoto, duplicado: true }
  else:
    id = insert(planta, body)
    return 201 { ok, id_remoto: id, duplicado: false }
```

---

## 10. Datos de empresa / contexto de negocio (Gexim)

| Concepto | Valor / nota |
|----------|----------------|
| Empresa | Gexim S.A.C. |
| Producto etiqueta | Fibra cortada de poliéster RPET |
| Página impresión | A4 vertical, etiqueta en origen ~11 mm × 15 mm |
| Planta | Extrusora (Ate) |
| Origen peso | Indicador Precix-Weight vía COM1 9600 8N1 |
| DB local | `pesajes.db` junto al `.exe` / script |

---

## 11. Archivos de referencia en el repo Precix

| Archivo | Qué mirar |
|---------|-----------|
| `sync.py` | Worker, POST, manejo de errores |
| `models.py` → `to_sync_payload()` | Shape exacto del JSON |
| `db.py` | `pendientes()`, `marcar_sincronizados()`, soft-delete |
| `catalog.py` | Maestros (fase 2) |
| `config.py` | `SYNC_*` / env vars |
| `app.py` | Comentario de activación sync |

---

## 12. Resumen ejecutivo para la otra PC

1. Migración: `supabase/migrations/20250804150000_precix_pesajes.sql`
2. Vercel: `PRECIX_SYNC_TOKEN` + `PRECIX_DEFAULT_PLANTA=ATE-EXTRUSORA-1`
3. Planta: mismas vars + `PRECIX_SYNC_ENABLED=1` + URL `/api/v1/precix/pesajes`
4. Cliente ya envía **Bearer** + `planta` + intervalo en minutos
5. UI nube: **Reportes de producción (pesajes)** (`/operaciones/produccion/pesajes`)
6. Soft-delete / maestros: fase 2 en el cliente
