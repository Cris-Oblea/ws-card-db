# CLAUDE.md — ws-card-db

Proyecto 1 del portafolio **WSAI**. Pipeline de extracción/análisis que mide el **costo de poder por habilidad** de las cartas Weiss Schwarz (validado ~98% contra la lista oficial JP: 15.889 habilidades / 63.350 cartas) + una **web estática de consulta**. Repo personal (CrisRP-dev/ws-card-db).

> ⚠️ **Este archivo es la FUENTE DE VERDAD del stack y las convenciones.** Cuando el proyecto crezca (nuevas libs, nueva tecnología, nueva carpeta), se actualiza ACÁ. Los agentes leen este archivo y NO hardcodean versiones, así que no hay que modificarlos cuando el stack cambia.

## Documentación (REGLA — para mantener el repo ordenado)
- **Cualquier cambio de stack/convenciones se actualiza EN ESTE `CLAUDE.md`** apenas pasa (nueva lib, versión, carpeta). Es la fuente de verdad; nunca dejarlo viejo.
- **Todo el funcionamiento del proyecto vive documentado en `documentation/`**: qué hace, **cómo funciona**, **cómo se construyó**, **qué tecnologías** usa, la arquitectura y las decisiones. ⚠️ Acá la doc va en `documentation/` (y no en `docs/`) porque **`docs/` ya es la web app desplegada** (GitHub Pages). El `CLAUDE.md` es el índice/resumen; `documentation/` es el detalle.
- Mantener `documentation/` + este `CLAUDE.md` al día **es parte de terminar un cambio**, igual que el código. Un cambio sin doc actualizada no está terminado.

## Propósito de fondo
La razón de ser: **referencia de balance para diseñar cartas CUSTOM** — *"quiero este efecto → cuesta X power"*. El costo es el power que se le RESTA a una carta respecto a su base (`power_real = power_base − costo`), **siempre en múltiplos de 500**. Medir el costo de las 15.889 habilidades reales da la vara para costear efectos nuevos que no existen en ninguna carta.

## Qué es (dos productos)
1. **Pipeline (Python):** scrapea la lista oficial JP, normaliza, fecha por era, y calcula el costo de poder de cada habilidad (medido → residual → estimado). Salida: Excel (`deliverables/`) + SQLite para la web.
2. **Web de consulta (estática):** buscá cualquier carta y mirá el desglose de costo de cada efecto. Sin backend — corre todo en el navegador.

## Stack (lo volátil — se actualiza ACÁ al crecer)
- **Python 3.14** — stdlib (`json`, `sqlite3`, `re`, `urllib.request`, `csv`, `statistics`, `unicodedata`, `glob`) + **`openpyxl`** (Excel) + **`mcp>=1.0`** (FastMCP).
- **Web:** HTML5 + JS vanilla + **`sql.js`** (SQLite en el navegador) + **`pako`** (gunzip). Datos en `docs/ws.sqlite.gz`. Versionado de cache con `?v=N`.
- **MCP server** (`tools/ws-mcp/server.py`): tools de estado cross-repo del portafolio + búsqueda de cartas.
- Sin CI; sin suite de tests formal (ver "Validación").

## Estructura
- `pipeline/` — scripts canónicos: `build_official_list.py`, `build_db.py`, `build_master_list.py`, `build_cost_sheet.py`, `official_en.py` + las fuentes JSON (`cardlist_clean.json` = verdad JP, `cardlist_en.json`, `card_era.json`, `translation_cache.json`).
- `pipeline/pipeline/` — subpipeline: `harvest_cardlist.py` → `clean_cardlist.py` → `date_sets.py` → `build_features.py`.
- `pipeline/fuentes/` — reglas oficiales, macros, manuales (material de referencia, **no es código**).
- `deliverables/` — los Excel finales (versionados).
- `docs/` — la web (`index.html`, `app.js`, `style.css`, `ws.sqlite.gz`).
- `tools/ws-mcp/` — el MCP server.
- `reference/` — PDFs oficiales de Bushiroad.

## Cómo correr
- Excel de habilidades: `python pipeline/build_official_list.py`
- SQLite para la web: `python pipeline/build_db.py`
- Web local: `cd docs && python -m http.server 8000` → http://localhost:8000/
- MCP server: `python tools/ws-mcp/server.py`

## Convenciones
- **Costos** siempre múltiplos de **500** (economía de poder del juego).
- **Confianza:** `HIGH` (medido) · `MEDIUM` (residual) · `LOW` (estimado).
- **Era:** `legacy` (<2017, ~2x más caro) · `modern` (≥2017). El power-creep importa.
- **Dedup:** quedarse con la rareza base, descartar alt-art/parallels.
- **Encoding:** UTF-8 + normalización NFKC (full/half-width japonés).

## Qué NO tocar
- `pipeline/fuentes/` y `reference/` — material de referencia, no código.
- `pipeline/translation_cache.json` — caché PERMANENTE de traducción (reusa trabajo previo, no borrar).
- `.gitignore` — ya excluye lo regenerable (raw harvest, features.csv, ws.sqlite sin comprimir).

## Validación (en vez de tests clásicos)
Esto es un proyecto de **datos/research**: la "prueba" es **empírica** — % de acierto contra la lista oficial + audits (`cardlist_audit.json`, conteos, suspects). NO hay unit tests tradicionales. Quien valide (el `reviewer`) lo hace con **conteos y audits de datos**, no con assertions.

## Flujo de trabajo (LIVIANO — proyecto personal, sin equipo)
No hay issue obligatorio, ni tablero, ni PR revisado por otra persona. El flujo es:
```
pedido → architect (plan + trade-offs)  →  🚦 vos aprobás  →  el dev-agent que corresponda  →  reviewer (audita)
```
Saltá pasos cuando la tarea sea chica/obvia. Commit/push a `main` directo (o PR liviano si querés revisar el diff). Tareas read-only (consultar, buscar) no necesitan flujo.

## Agentes (en `.claude/agents/`)
Definidos por **ROL** (difieren a este CLAUDE.md para el stack, así no se rompen al crecer):
- **`architect`** — planea, evalúa trade-offs. No programa. (genérico, reutilizable)
- **`reviewer`** — audita calidad y datos al final. (genérico, reutilizable)
- **`pipeline-dev`** — mantiene/mejora el pipeline de extracción, limpieza y build.
- **`cost-analyst`** — el modelo de costo, la validación y la mejora de precisión.
- **`web-maintainer`** — la web estática de consulta.

## Relación con el portafolio WSAI
- Salió del taller `wsai/analisis/` → **este repo es la versión canónica limpia** (si editás el pipeline, hacelo acá, no en `wsai/analisis/`, para no generar drift).
- Lo consume **ws-sim-ai** (P3) para razonar valor/tempo/economía con números fundamentados.
