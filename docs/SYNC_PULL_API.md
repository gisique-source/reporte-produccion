# Precix-Weight ← API nube — Export / restauración (PULL)

Contrato para que el **sistema web (core)** exponga un endpoint de descarga.
La app de planta Precix-Weight ya implementa el cliente (`sync_pull.py`) y el botón
**Auditoría → Traer desde nube**.

Flujo:

```
[Sistema web / Supabase]
        ↓  GET /api/v1/precix/pesajes/export  (Bearer + planta)
[Precix-Weight SyncPullClient]
        ↓  upsert SQLite (id_local ó lote+nro_fardo)
[pesajes.db local]  ·  estado_sincronizado = 1
```

Complementa el push documentado en `SYNC_API_CONTEXTO.md` (POST de subida).

---

## 1. Por qué hace falta

Tras reinstalar la PC de planta, cambiar de equipo o perder `pesajes.db`, la app
solo tiene el esquema vacío. El historial ya subido vive en el core.

Este endpoint permite **reconstruir la DB local** desde la nube sin copiar el
archivo `.db` a mano.

No reemplaza el backup de `pesajes.db` (auditoría local y settings no viajan).

---

## 2. Endpoint a implementar (servidor)

```http
GET /api/v1/precix/pesajes/export
Authorization: Bearer {PRECIX_SYNC_TOKEN}
X-Precix-Planta: {codigo_planta}
Accept: application/json
```

### Query params

| Param | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `planta` | string | recomendado | Ej. `ATE-EXTRUSORA-1`. Debe coincidir con el token / header |
| `desde` | string | no | `YYYY-MM-DD` inclusive (filtro por fecha del pesaje) |
| `hasta` | string | no | `YYYY-MM-DD` inclusive |
| `limit` | int | no | Tamaño de página (cliente pide ≤ 500; servidor máx. sugerido 1000) |
| `cursor` | string | no | Opaco; vacío = primera página |
| `incluir_inactivos` | `0`\|`1` | no | Default `1`. Si `0`, solo `activo = 1` |

### Auth

Misma regla que el POST de subida:

- Sin Bearer → **401**
- Token de otra planta → **403** (no filtrar solo por query `planta` sin validar token)
- Preferir resolver planta desde el token y usar `X-Precix-Planta` / `planta` como chequeo

---

## 3. Respuesta JSON (shape que consume el cliente)

```json
{
  "ok": true,
  "planta": "ATE-EXTRUSORA-1",
  "total": 1284,
  "next_cursor": "eyJpZCI6NTAwfQ",
  "items": [
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
      "beteado": "1",
      "activo": 1
    }
  ],
  "maestros": {
    "clientes": [
      { "valor": "Catalina Peru SAC", "codigo": "", "activo": 1 }
    ],
    "colores": [
      { "valor": "Marron 580", "codigo": "", "activo": 1 }
    ],
    "deniers": [
      { "valor": "4.0", "codigo": "", "activo": 1 }
    ],
    "cortes": [
      { "valor": "65", "codigo": "", "activo": 1 }
    ],
    "operarios": [
      { "valor": "Juan Perez", "codigo": "", "activo": 1 }
    ]
  }
}
```

### Campos raíz

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `ok` | bool | sí | `false` + `error` string si falló |
| `planta` | string | sí | Código de planta de los datos |
| `items` | array | sí | Lista de pesajes (alias aceptado: `pesajes`) |
| `next_cursor` | string\|null | sí | `null` / omitido / `""` = no hay más páginas |
| `total` | int | no | Total de filas que cumplen el filtro (todas las páginas) |
| `maestros` | object | no | Catálogo; el cliente lo aplica **solo en la 1.ª página** |

### Cada ítem de `items` (mismo shape que el POST de subida)

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `id_local` | int | **sí** | PK original en la PC de planta. Clave de restauración |
| `fecha_hora` | string | sí | `YYYY-MM-DD HH:MM:SS` |
| `cliente` | string | sí | Texto |
| `lote` | string | sí | |
| `color` | string | sí | |
| `denier` | string | sí | |
| `corte` | string | sí | |
| `nro_fardo` | string | sí | |
| `peso_bruto` | number | sí | |
| `peso_neto` | number | sí | |
| `operario` | string | no | |
| `peso_total` | number | no | |
| `tara_carreta` | number | no | |
| `tara_fardo` | number | no | |
| `beteado` | string | no | Default `"1"` |
| `activo` | int | sí | `1` / `0` soft-delete |

Alias de lista: el cliente también acepta `pesajes` en lugar de `items`.

### Maestros (recomendado)

Enviar en la **primera página**. Cada entrada puede ser:

- string: `"Catalina Peru SAC"`, o
- objeto: `{ "valor": "...", "codigo": "", "activo": 1 }`

Claves aceptadas: `clientes`/`cliente`, `colores`/`color`, `deniers`/`denier`,
`cortes`/`corte`, `operarios`/`operario`.

Si el core aún no tiene tablas de maestros, omitir `maestros` o mandar `{}`.
El cliente igual reconstruye catálogo a partir de textos únicos en los pesajes
(operarios ya se seed-ean desde pesajes al abrir la app).

---

## 4. Paginación

1. Primera request: sin `cursor` (o vacío).
2. Si `next_cursor` tiene valor, el cliente vuelve a llamar con `cursor=<ese valor>`.
3. Cuando `next_cursor` es `null` / `""` / ausente, termina.

Cursor sugerido (servidor): base64 de `{ "id": <último id remoto o id_local> }` o
offset estable. Debe ser **estable** ante inserts concurrentes (preferir keyset
por `id_local` ASC o `recibido_en` + id).

Orden recomendado de `items`: `id_local ASC` (facilita correlativos en planta).

---

## 5. Comportamiento del cliente Precix (ya implementado)

| Situación | Acción local |
|-----------|--------------|
| Existe fila con mismo `id` = `id_local` | `UPDATE` campos; `estado_sincronizado = 1` |
| No hay ese id, pero sí mismo `lote`+`nro_fardo` | `UPDATE` esa fila |
| No existe | `INSERT` con `id = id_local` (si viene) y ajusta `sqlite_sequence` |
| Registro restaurado | Queda **sincronizado** (`estado_sincronizado = 1`) para no re-subir |

UI:

- **Auditoría → Traer desde nube**
  - Sí = historial completo de la planta
  - No = usa filtros Desde/Hasta de la pantalla
- Si `pesajes` está vacío al arrancar y hay token → ofrece restauración automática

Variables de entorno (planta):

| Variable | Default |
|----------|---------|
| `PRECIX_SYNC_TOKEN` | (obligatorio) |
| `PRECIX_SYNC_URL` | POST subida `.../pesajes` |
| `PRECIX_SYNC_PULL_URL` | Si vacío: `{PRECIX_SYNC_URL}/export` |
| `PRECIX_DEFAULT_PLANTA` / `PRECIX_PLANTA` | `ATE-EXTRUSORA-1` |
| `PRECIX_SYNC_PULL_PAGE_SIZE` | `500` |
| `PRECIX_SYNC_TIMEOUT_S` | `10` |

---

## 6. Errores HTTP

| HTTP | Cliente |
|------|---------|
| `200` | Procesa página |
| `401` / `403` | Aborta; muestra detalle |
| `404` | Aborta (endpoint no implementado) |
| `5xx` / timeout | Aborta; se puede reintentar manualmente |

Error de negocio sugerido:

```json
{ "ok": false, "error": "planta no autorizada" }
```

---

## 7. Ejemplo curl

```bash
# Primera página (todo el historial de la planta)
curl -sS "https://tu-dominio.vercel.app/api/v1/precix/pesajes/export?planta=ATE-EXTRUSORA-1&limit=500&incluir_inactivos=1" \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "X-Precix-Planta: ATE-EXTRUSORA-1" \
  -H "Accept: application/json"

# Con rango de fechas
curl -sS "https://tu-dominio.vercel.app/api/v1/precix/pesajes/export?planta=ATE-EXTRUSORA-1&desde=2026-01-01&hasta=2026-08-20&limit=500" \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "X-Precix-Planta: ATE-EXTRUSORA-1"
```

---

## 8. Pseudocódigo servidor

```text
function ExportPesajes(req):
  planta = resolvePlanta(req.token, req.header, req.query.planta)
  if not authorized: return 401/403

  limit = clamp(req.query.limit, 1, 1000)
  cursor = decode(req.query.cursor)   # null = start

  query = select from precix_pesajes
          where planta_codigo = planta
          and (fecha between desde..hasta if set)
          and (activo = 1 if incluir_inactivos = 0)
          and (id_local > cursor.id_local if cursor)
          order by id_local asc
          limit limit

  rows = query.fetch()
  next = encode({ id_local: rows[-1].id_local }) if len(rows) == limit else null

  maestros = null
  if cursor is null:
    maestros = buildMaestrosFromCatalogOrDistinct(planta)

  return 200 {
    ok: true,
    planta,
    total: countMatching(planta, filters),
    items: mapRowToPushShape(rows),   # mismos campos que POST body
    next_cursor: next,
    maestros
  }
```

`mapRowToPushShape` debe devolver exactamente el mismo shape que acepta el POST
de subida (`id_local`, `fecha_hora`, …, `activo`), para que push y pull sean simétricos.

---

## 9. Checklist implementación web

- [ ] Ruta `GET /api/v1/precix/pesajes/export`
- [ ] Auth Bearer = mismo `PRECIX_SYNC_TOKEN` que el POST
- [ ] Filtro estricto por planta
- [ ] Paginación con `next_cursor` estable
- [ ] `items[]` con `id_local` siempre presente
- [ ] Incluir `activo` (soft-delete)
- [ ] (Opcional) `maestros` en primera página
- [ ] CORS no aplica (cliente desktop `urllib`, no browser)
- [ ] Probar con curl + botón **Traer desde nube** en Precix

---

## 10. Qué NO debe ir en este endpoint

- Tokens / secretos en la respuesta
- Credenciales de otras plantas
- Datos de auditoría local (`sync_auditoria`, `pesaje_auditoria`) — se regeneran
- El archivo binario `pesajes.db` — el contrato es JSON paginado

---

## 11. Archivos cliente (referencia)

| Archivo | Rol |
|---------|-----|
| `sync_pull.py` | GET paginado + aplicación |
| `restore_store.py` | Upsert SQLite |
| `sync.py` → `pull_now()` | API usada por la UI |
| `ui/auditoria_view.py` | Botón Traer desde nube |
| `config.py` | `SYNC_PULL_URL`, page size |
| `docs/SYNC_API_CONTEXTO.md` | Contrato del POST (subida) |
