# WEBAPP.md — the static lookup website (`site/`)

> Detail doc for the **deliverable web app**. What it does, how it works end-to-end, the files, the pinned CDN dependencies + their offline risk, the cache-busting scheme, how to run/deploy it, and the `ws.sqlite` schema contract `app.js` depends on. The `CLAUDE.md` stays the source of truth for the stack; this file is the depth behind it.

## What it does
A single-page, **backend-free** app to **search any Weiss Schwarz card and see the power cost of each of its effects**. You can filter by type/color/side/trigger, by level/cost/soul/power, by trait, by Neo-Standard title (either language), by series, and by ability cost/confidence. Click a card to open a detail modal with its image, stats, the **power-budget breakdown** (base power → what the effects spend → printed power → the designer's residual, with a `SUSPECT` flag when `|residual| ≥ 500`), and a per-ability list showing each effect's standard cost + evidence.

## How it works (end to end)
Everything runs in the browser — there is **no server**. On load, `app.js` `boot()`:

1. **Fetch** `ws.sqlite.gz` (the gzipped SQLite that `pipeline/build_db.py` produced) as an `ArrayBuffer`, in parallel with instantiating the sql.js WASM engine.
2. **Inflate** the gzip in-browser with **pako** (`pako.inflate` → raw SQLite bytes).
3. **Load** those bytes into **sql.js** (SQLite compiled to WebAssembly): `new SQL.Database(bytes)` holds the **entire database in memory**.
4. **Query** in memory: every filter/search/detail view is just a parameterized `SELECT` run through `query()` (prepare → bind → step → getAsObject → free). No network per query.

Because the whole dataset (~40k cards / ~16k abilities) lives in RAM, the app is careful about **rendering**, not fetching: `run()` always fetches and paints **one page** of rows (`LIMIT/OFFSET`), never all of them, and builds the table body as a single `innerHTML` string. SQLite's indexes (see the schema below) do the filtering work.

### The load can fail
The only hard external dependencies are the two CDN scripts and the `.gz` fetch. If any of them is unreachable, `boot()`'s `catch` writes an error into the header `#status` line instead of leaving a blank page. The most likely real-world cause is a **CDN outage** (see the risk note below).

## The files
| File | Role |
|---|---|
| `site/index.html` | The page skeleton + all the mount points (element IDs) `app.js` reads. Loads the CSS and the three scripts. ~120 lines. |
| `site/app.js` | All behavior: fetch/inflate/load the DB, build the filter WHERE clause, run queries, render the results table and the detail modal, wire every event. ~320 lines. |
| `site/style.css` | All styling. Dark theme driven by CSS custom properties in `:root`; two-column app shell (fixed sidebar + fluid results); the detail modal overlay. ~130 lines. |
| `site/ws.sqlite.gz` | The **generated** data (gzipped SQLite). Produced by `pipeline/build_db.py` — **never edit by hand**; it is a binary artifact, not source. |

`index.html` → `app.js` wiring is entirely by **element id**: `app.js` queries `#q`, `#f-type`, `#results tbody`, `#detail`, etc. Renaming an id in the HTML without updating `app.js` (or vice-versa) silently breaks that control.

## CDN dependencies (pinned) and the offline risk
Read straight off `site/index.html`. Both are loaded from **cdnjs** and are **version-pinned**:

| Library | Version | URL |
|---|---|---|
| **pako** (gunzip / zlib in JS) | **2.1.0** | `https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js` |
| **sql.js** (SQLite → WebAssembly) | **1.10.3** | `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js` |

sql.js also fetches a **matching `sql-wasm.wasm`** at runtime from the **same versioned path** — `app.js` points there via `initSqlJs({ locateFile: f => https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f} })`. **The version in that `locateFile` URL must stay in lockstep with the `<script>` version in `index.html`** — a mismatch loads a JS shim and a WASM binary that don't agree.

**Availability risk:** if cdnjs is unreachable (outage, firewall, or offline use), **the app cannot load at all** — pako/sql.js are the engine, not enhancements. This is the single biggest fragility of the "no backend" design.

**How you WOULD vendor them locally** (optional future hardening — *not* implemented today, noted so it's a known lever):
1. Download `pako.min.js`, `sql-wasm.js`, and `sql-wasm.wasm` (the exact pinned versions) into `site/` (e.g. a `site/vendor/` folder).
2. Point the two `<script src=…>` in `index.html` and the `locateFile` in `app.js` at those local paths.
3. Bump the `?v=N` on the changed files and re-test.
This removes the CDN dependency (works fully offline) at the cost of committing ~1–2 MB of vendored libraries to the repo. Keep it a deliberate decision — don't do it as a side effect of another change.

## Cache-busting (`?v=N`)
There are **two different** `?v=` schemes — don't confuse them:

- **`style.css?v=19` and `app.js?v=21`** in `index.html` are **MANUAL** version stamps. When you edit `style.css` or `app.js`, **bump the number by hand** so browsers fetch the new file instead of a cached copy. (These are independent counters; bump whichever file you changed.)
- **`ws.sqlite.gz?v=<hash>`** inside `app.js` (the `fetch(...)` in `boot()`) is **AUTOMATIC**. `build_db.py`, at the end of its run, computes a short SHA-1 of the DB **content** and rewrites that `?v=` in `app.js`. So any data rebuild changes the URL and can never be served stale — **do not edit that value by hand**, and note that a rebuild will itself modify `app.js` (the hash line), which is expected.

## Run locally
```
python pipeline/build_db.py    # site/ws.sqlite.gz isn't committed -- build it once first
cd site && python -m http.server 8000
```
Then open http://localhost:8000/ . A plain static file server is enough — there is nothing to build or transpile. (Opening `index.html` via `file://` will fail: the CDN scripts and the `fetch` of the `.gz` need an `http(s)` origin.)

## Deploy
The site is served by **GitHub Pages**, built by `.github/workflows/deploy-pages.yml` on every push to
`main`: the workflow runs `pipeline/build_db.py` fresh (checking out with LFS enabled so
`cardlist_clean.json` resolves to its real content) and deploys whatever's in `site/` afterward — no
manual step, no need to commit a rebuilt `ws.sqlite.gz` yourself. `site/ws.sqlite.gz` (and the
uncompressed `ws.sqlite`) are gitignored on purpose: each rebuild is a ~10-13MB gzip blob that git can't
delta-compress between versions, and 79 historical committed copies had bloated `.git` by ~820MB before
this was fixed (2026-07-22). `site/app.js` stays committed — its `?v=` hash reflects the last local build,
but the live site always serves whatever CI just built, which is internally consistent regardless.

## The `ws.sqlite` schema contract (what `app.js` depends on)
`app.js` reads these tables/columns directly. **A schema change in `pipeline/build_db.py` requires a matching `app.js` change** — this section is the contract between them. (Full authoritative schema is the `CREATE TABLE` block in `build_db.py`.)

### `cards` (one row per card; PK `card_number`)
Columns `app.js` uses:
- **List view** (`run()` SELECT): `card_number`, `name`, `name_en`, `type`, `color`, `level`, `cost`, `power`, `soul`, `model_cost_total`; ordered by `series, card_number`.
- **Filters** (`buildWhere()`): `search_fold` (folded name/title blob for accent-insensitive search), `type`, `color`, `side`, `level`, `cost`, `soul`, `trigger` (joined string, matched with `LIKE`), `power`, `traits` + `traits_en`, `series`, `en_exclusive`, `title_search`.
- **Detail modal** (`showDetail()` does `SELECT *`, then reads): `power_base`, `real_delta`, `model_cost_total`, `residual`, `is_suspect`, `power`, `image_en`, `picture`, `type`, `name_en`/`name`/`card_number`, `color`, `side`, `level`, `cost`, `trigger`, `rare`, `release_date`, `era`, `series`, `neo_titles`, `traits`, `traits_en`, `text_en`.

Other columns exist in the table (`base_number`, `name_kana`, `expansion`, `parallel`, `budget`) and are not currently read by the UI.

### `abilities` (one row per ability; PK `card_number, idx`)
Read by `showDetail()` and by the ability-cost/search subqueries in `buildWhere()`: `card_number`, `idx` (printed order — `ORDER BY idx`), `ability_type`, `family`, `jp_text`, `en_text`, `power_cost`, `method`, `confidence` (`HIGH`/`MEDIUM`/`LOW`), `standard_cost`, `mode_share`, `n_samples`.
- The detail headline cost is `standard_cost` (falling back to `power_cost`); the tooltip/evidence line uses `n_samples`, `mode_share`, `method`.
- The free-text search and the "Ability power cost" filter both use correlated subqueries: `card_number IN (SELECT card_number FROM abilities WHERE …)` over `en_text`/`jp_text`, `power_cost`, `confidence`.

### `meta` (key/value build stats)
`app.js` reads `cards`, `abilities`, `note`, `validation` to render the header summary line. Other keys present: `schema`, `explained_pct`, `explained_n`, `suspects`.

### `neos` (deck-construction groups for the Title filter)
`app.js` reads `jp_name`, `en_name`, `codes` (space-joined set codes), `en_only`. Used to build `NEO_MAP` (name in either language → its set codes) and the autocomplete `<datalist>`. `en_only` disambiguates the edition when filtering: `2` = the title spans JP cards + EN variants (match series codes alone); otherwise the query also pins `en_exclusive` to the neo's flag so JP and EN-exclusive editions of the same franchise don't bleed together. (The `kana` column exists but the UI doesn't read it.)

### Indexes
`build_db.py` creates indexes on `cards(color/level/cost/soul/type/side/series)` and `abilities(card_number/power_cost/family)` — they back the filter/subquery patterns above.

## Conventions when touching `site/`
- **Vanilla JS only** — no frameworks/build step (per `CLAUDE.md`).
- **Bump `?v=N`** on `app.js`/`style.css` in `index.html` whenever you change them; leave the auto `ws.sqlite.gz?v=` hash alone.
- **Mind the ~40k rows** — keep queries indexed and keep rendering paginated; never draw the whole result set.
- **Escape all data** into HTML via `escHtml` (already used throughout) to avoid injection from card text.
- Verify a change by running the local server above and exercising the golden path (search → filter → open a card) in a real browser.
