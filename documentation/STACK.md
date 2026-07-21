# STACK.md — languages, runtimes, dependencies, and a from-scratch setup

> The **technology inventory** for ws-card-db: exactly what you need installed to build and run every part
> of it, why the stack is deliberately tiny, the external data sources it pulls from, and the scraping
> etiquette to respect when refreshing them. The top-level **`CLAUDE.md` remains the source of truth** for
> the stack; this file is the hands-on depth behind it. For the *how-to* sequences see
> [`RUNBOOK.md`](RUNBOOK.md); for the module map see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Languages & runtimes

| Part | Language / runtime | Version |
|---|---|---|
| Pipeline (harvest → clean → date → features → cost → build) | **Python** | **3.14** (developed on 3.14.5) |
| MCP server (`tools/ws-mcp/`) | Python | 3.14 |
| Web app (`site/`) | **HTML5 + vanilla JavaScript** (no framework, no build step) | ES2020-era browser |
| In-browser database | **SQLite** via `sql.js` (SQLite compiled to WebAssembly) | see §3 |

There is **no bundler, transpiler, linter config, or CI**. The pipeline is plain scripts you run by hand;
the site is three static files you open in a browser. This is intentional — see §5.

## 2. Python dependencies

The pipeline **core is standard-library only**. The only third-party packages are for Excel output and the
MCP server. They live in the top-level **`requirements.txt`**:

| Package | Version pin | Used by | Why |
|---|---|---|---|
| `openpyxl` | `>=3.1.5` | `pipeline/build_official_list.py`, `build_master_list.py`, `build_cost_sheet.py` | Write the `.xlsx` cost sheets |
| `mcp` | `>=1.28.0` | `tools/ws-mcp/server.py` | FastMCP server (portfolio status + card search tools) |

> `tools/ws-mcp/requirements.txt` also lists `mcp>=1.0` (a looser pin for running the server standalone).
> Installing the top-level `requirements.txt` satisfies both.

### Standard-library modules the pipeline relies on
No install needed — these ship with CPython 3.14, but listing them makes the dependency surface explicit:

`json` · `sqlite3` · `re` · `urllib.request` · `csv` · `statistics` · `unicodedata` · `glob` · `ssl` ·
`gzip` · `hashlib` · `html` · `io` · `os` · `sys` · `time` · `datetime` · `bisect` · `collections` ·
`difflib` · `pathlib`.

The two that carry the most weight:
- **`unicodedata`** — every string is NFKC-normalized (full-width ↔ half-width Japanese must fold to one
  form). This is a project-wide invariant; see the `_nk()` helper reused across the builders.
- **`sqlite3`** — builds the `site/ws.sqlite` the web app queries.

## 3. Web dependencies (pinned CDN)

The site loads exactly two libraries from a CDN. **The versions are pinned in `site/index.html`** and the
`sql.js` version is *repeated* in `site/app.js` (the WASM `locateFile` URL) — **the two must stay in sync**.

| Library | Version | Source | Role |
|---|---|---|---|
| **pako** | `2.1.0` | `cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js` | Gunzip `ws.sqlite.gz` in the browser |
| **sql.js** | `1.10.3` | `cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js` (+ `sql-wasm.wasm` via `locateFile`) | Run SQLite in the browser |

The only shipped data file is **`site/ws.sqlite.gz`** (the gzipped database). See [`WEBAPP.md`](WEBAPP.md)
for how the app loads and queries it, and the offline-risk note on the CDN dependency.

## 4. Setup from scratch (fresh machine)

1. **Install Python 3.14+.** Verify:
   ```
   python --version        # -> Python 3.14.x
   ```
   On Windows, tick "Add python.exe to PATH" in the installer.
2. **Clone the repo** and enter it:
   ```
   git clone <repo-url> ws-card-db
   cd ws-card-db
   ```
3. **Install the Python deps** (a virtualenv is optional but recommended):
   ```
   python -m pip install -r requirements.txt
   ```
   That is the *entire* toolchain for the pipeline and the MCP server.
4. **Run the site with the standard library** — no npm, no install:
   ```
   cd site && python -m http.server 8000     # -> http://localhost:8000/
   ```
5. To *rebuild* the data (not needed just to browse — the tracked JSON + shipped `ws.sqlite.gz` are enough),
   follow [`RUNBOOK.md`](RUNBOOK.md).

That's it. Because the canonical inputs (`cardlist_clean.json`, `cardlist_en.json`, the translation JSONs)
are committed to git, a fresh clone can build the Excel sheets and the SQLite **without re-scraping anything**.

## 5. Why stdlib-first

- **Longevity without a subscription.** The owner must be able to keep this running for years with zero paid
  tooling and minimal maintenance. Fewer dependencies = fewer things that break on a Python bump or a
  yanked package.
- **The data is the product, not the framework.** This is a research/data project; the value is in the
  measured costs, not in any library. Plain `dict`/`list`/`csv`/`sqlite3` keep the logic transparent.
- **Reproducibility.** A stdlib script produces the same output on any machine with the right Python. No
  lockfile drift, no native-build surprises.
- **The web is backend-free on purpose** so it can be hosted as static files (GitHub Pages) forever, with
  no server to pay for or patch.

## 6. External data sources & scraping etiquette

The pipeline refreshes its inputs from four external sources. **None is hit during a normal build** — you
only touch them when adding a new card set or refreshing translations. All the fetchers already implement
polite behavior; keep it that way.

| Source | Script | What it gives | Etiquette already built in |
|---|---|---|---|
| **ws-tcg.com** (official JP card-list JSON endpoint) | `pipeline/ingest/harvest_cardlist.py` | The entire JP card list (the JP source of truth) | 0.25 s throttle, retry w/ exponential backoff, **resumable** state file, descriptive `User-Agent` with a contact address |
| **ws-tcg.com/products** (JP products archive) | `pipeline/ingest/harvest_products.py` | Real Japanese release dates (発売日) for legacy sets | 0.3 s throttle, backoff, dedupe by product code |
| **ws-tcg.com filter-options** | `pipeline/ingest/fetch_filter_options.py` | Expansion taxonomy + Neo-Standard title groupings | single request, mimics the site's own XHR |
| **CCondeluci/WeissSchwarz-ENG-DB** (GitHub) | `pipeline/ingest/fetch_ccondeluci.py` | Official **English** card text | GitHub API listing + raw downloads, light 0.03 s throttle, backoff |
| **heartofthecards.com** | `pipeline/fetch_hotc.py` | JP-aligned English **names** (correct even for renumbered legacy sets) | slow pacing (default 6 s), **stub-detection + backoff** (HotC rate-limits bursts), incremental save |
| **Unofficial WS simulator** (local `CardData.txt` files) | `pipeline/extract_simulator.py` | English name/traits/abilities for ~21.5k cards that never released in EN | reads **local files only**, no network |

**Rules of thumb when refreshing:**
- Keep the `User-Agent` string (it identifies the project and a contact) — do not spoof an anonymous browser.
- Do not lower the throttles or remove the backoff/retry logic.
- The harvest is **resumable**; if it stops, re-run it — it continues from the last saved page, it does not
  re-download what it already has.
- **Never** delete `pipeline/translation_cache.json` — it is the permanent, hand-built translation store
  (see [`ARCHITECTURE.md`](ARCHITECTURE.md) and `CLAUDE.md`).

## To go deeper
- Module map & data flow → [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Step-by-step rebuild recipes → [`RUNBOOK.md`](RUNBOOK.md)
- The cost math → [`COST_MODEL.md`](COST_MODEL.md)
- The web app → [`WEBAPP.md`](WEBAPP.md)
- EN matching & legacy disparity → [`en-name-matching.md`](en-name-matching.md)
