# ws-card-db — Cómo funciona (overview)

> Documento de arranque de `documentation/`. Resume QUÉ hace, CÓMO funciona, CÓMO se construyó y QUÉ tecnologías usa. Ampliar a medida que el proyecto crece (ver la regla en el `CLAUDE.md`).

## Qué hace
Mide el **costo de poder por habilidad** de las cartas Weiss Schwarz, para servir de **referencia de balance al diseñar cartas custom** ("quiero este efecto → cuesta X power"). Costo = power que se le RESTA a la base (`power_real = power_base − costo`), siempre en **múltiplos de 500**.

## Cómo funciona (el flujo)
1. **Harvest** (`pipeline/pipeline/harvest_cardlist.py`): scrapea la lista oficial JP (ws-tcg.com) con throttle educado y estado reanudable.
2. **Clean** (`clean_cardlist.py`): normaliza el raw → `cardlist_clean.json` (63.350 cartas JP, UTF-8 NFKC).
3. **Date** (`date_sets.py`): asigna `release_year` y `era` (legacy <2017 / modern ≥2017) — el power-creep importa.
4. **Modelo de costo** (en los `build_*.py`), tres niveles de confianza:
   - **HIGH (medido):** se despeja del power real de la carta vs su base.
   - **MEDIUM (residual):** se infiere en cartas con varias habilidades, restando las ya medidas.
   - **LOW (estimado):** modelo cuando no hay medición.
   - Power base ≈ `3000 + 2500·Level + 1500·Cost − 1000·[Soul trigger] − 1000·(Soul−1)`.
5. **Salidas:**
   - `build_official_list.py` → `deliverables/Lista_Habilidades_COMPLETA.xlsx` (15.889 habilidades — EL producto).
   - `build_db.py` → `docs/ws.sqlite(.gz)` para la web.
   - `build_cost_sheet.py` → `GUIA_COSTO_HABILIDADES.xlsx` (modelo para costear efectos nuevos).
6. **Web** (`docs/`): app estática — descarga `ws.sqlite.gz`, gunzip con pako, sql.js en memoria, queries en el navegador. **Sin backend.**

## Cómo se construyó / validación
- Fuentes: lista oficial JP (scrape) + EN oficial (harvest) + reglas/manuales Bushiroad (`reference/`, `pipeline/fuentes/`).
- **Validación empírica:** ~98% de acierto contra la lista oficial. NO hay unit tests — el oráculo es la lista oficial + audits (`cardlist_audit.json`, conteos, suspects).
- De-dup: se queda la rareza base, descarta alt-art/parallels.

## Tecnologías
- **Python 3.14** (stdlib: json/sqlite3/re/urllib/csv/statistics/unicodedata) + **`openpyxl`** (Excel) + **`mcp>=1.0`** (el MCP server de `tools/ws-mcp/`).
- **Web:** HTML5 + JS vanilla + **`sql.js`** + **`pako`** + **SQLite**.

## Datos clave
- 63.350 cartas JP + 18.532 EN · 15.889 habilidades distintas · 74 franquicias Neo-Standard · eras legacy/modern.
- `pipeline/translation_cache.json` = caché PERMANENTE de traducción (**no borrar**).

## Estado
Pipeline validado 98%; web en producción (~40k cartas). En curso: traducción bilingüe JP→EN (10/16 batches) + mejora de precisión (detección de "suspects" + golden costs).

## Para profundizar
`pipeline/README.md` · `pipeline/GUIA_COSTO_HABILIDADES.md` · `pipeline/CONCLUSIONES.md` (el modelo en detalle) · `STATUS.md` (estado vivo).
