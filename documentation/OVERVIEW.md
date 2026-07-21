# ws-card-db — How it works (overview)

> Starting document of `documentation/`. Summarizes WHAT it does, HOW it works, HOW it was built and WHAT technologies it uses. Expand as the project grows (see the rule in the `CLAUDE.md`).

## What it does
Measures the **power cost per ability** of Weiss Schwarz cards, to serve as a **balance reference when designing custom cards** ("I want this effect → it costs X power"). Cost = power SUBTRACTED from the base (`power_real = power_base − cost`), always in **multiples of 500**.

## How it works (the flow)
1. **Harvest** (`pipeline/ingest/harvest_cardlist.py`): scrapes the official JP list (ws-tcg.com) with polite throttling and resumable state.
2. **Clean** (`clean_cardlist.py`): normalizes the raw → `cardlist_clean.json` (63,350 JP cards, UTF-8 NFKC).
3. **Date** (`date_sets.py` → `set_dates.json`): assigns `release_date`/`release_year` per set; `build_card_era.py` projects a descriptive format-era label (Genesis/Bounty/Gate/Standby/Choice/Horizon, bounded by climax trigger-icon debuts) onto each card → `card_era.json`. Date/era are **metadata only — NOT a cost driver** (validated: there is no power-creep at the package level; the apparent creep was effect-mix shift + dispersion).
4. **Cost model** (single-sourced in `pipeline/cost_model.py`, imported by both `build_*.py`):
   - **Package = full signature** (`''.join(markers) + ' :: ' + gen(text)`). The **standard cost** of a package = the **MODE (rounded 500)** of its measured per-card actuals, pooled across ALL years (no era split). Each standard carries its evidence: **`mode_share`** (% the modal value takes) and **`n_samples`**.
   - **Per-card residual** = real budget (`power_base − power`) **− Σ(ability standard costs)** = the designer's unexplained adjustment. A card is a **suspect** when `abs(residual) >= 500` (a cost anomaly worth review).
   - **Confidence reflects the standard's EVIDENCE**, not just the method:
     - **HIGH** = `measured` AND `n_samples >= 3` AND `mode_share >= 60` (a tight, well-sampled mode). Structural replay-body zeros are also HIGH.
     - **MEDIUM** = `residual`, or `measured` with weaker n / mode-share.
     - **LOW** = `estimated` (family median, no reliable mode).
   - **CX-Combo / replay** keep the residual-ABSORBER cascade (CX-combo floored at ≥500; replay body folded into its citer, counted once).
   - Base power ≈ `3000 + 2500·Level + 1500·Cost − 1000·[Soul trigger] − 1000·(Soul−1)`.
5. **Outputs:**
   - `build_official_list.py` → `Complete_Abilities_List.xlsx` (15,889 abilities; local Excel, generated on demand).
   - `build_db.py` → `site/ws.sqlite(.gz)` for the web.
   - `build_cost_sheet.py` → `Ability_Cost_Guide.xlsx` (model for costing new effects).
6. **Web** (`site/`): static app — downloads `ws.sqlite.gz`, gunzips with pako, sql.js in memory, queries in the browser. **No backend.**

## How it was built / validation
- Sources: official JP list (scrape) + official EN (harvest) + Bushiroad rules/manuals (`reference/`, `pipeline/sources/`).
- **Empirical validation:** the acceptance metric is **Explained%** = share of valid costed Character cards whose per-card residual is within ±500 (currently **94.5%**, n≈31.9k; acceptance floor 94%). It is a real out-of-sample check (per-card actual vs the package STANDARDS), unlike the older near-tautological residual-resum consistency %. There are NO unit tests — the oracle is the official list + audits (`cardlist_audit.json`, counts, suspects: ~4.2k cards flagged `is_suspect`).
- De-dup: keeps the base rarity, discards alt-art/parallels.

## Technologies
- **Python 3.14** (stdlib: json/sqlite3/re/urllib/csv/statistics/unicodedata) + **`openpyxl`** (Excel) + **`mcp>=1.0`** (the MCP server in `tools/ws-mcp/`).
- **Web:** HTML5 + vanilla JS + **`sql.js`** + **`pako`** + **SQLite**.

## Key data
- 63,350 JP cards + 18,532 EN · 15,889 distinct abilities · 74 Neo-Standard franchises · release-date metadata (trigger-debut format eras as flavor, not a cost driver).
- `pipeline/translation_cache.json` = PERMANENT translation cache (**do not delete**).

## Status
Pipeline validated at 98%; web in production (~40k cards). In progress: bilingual JP→EN translation (10/16 batches) + accuracy improvement ("suspects" detection + golden costs).

## To go deeper
The detailed docs in `documentation/`:
- **[`STACK.md`](STACK.md)** — languages, runtimes, exact dependency versions, from-scratch setup, external data sources + scraping etiquette.
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — the two products, repo map, the full data-flow diagram, the JSON artifact catalogue (writer/reader/tracked-or-regenerable), and the module graph with `cost_model.py` as the single source of cost math.
- **[`RUNBOOK.md`](RUNBOOK.md)** — hands-on, no-AI, step-by-step: full rebuild in stage order, regenerating just the DB / Excel, running the site, deploying to Pages, the MCP server, and change recipes (new set, new cost family, debugging a suspect, EN exclusions).
- **[`COST_MODEL.md`](COST_MODEL.md)** — the power-cost math end to end (the detail behind `pipeline/cost_model.py`).
- **[`WEBAPP.md`](WEBAPP.md)** — the static lookup site (`site/`): how it loads and queries the SQLite in the browser.
- **[`en-name-matching.md`](en-name-matching.md)** — how official EN is attached + the legacy-disparity exclusions.

Also: `pipeline/README.md` (pipeline quick reference) · `pipeline/Ability_Cost_Guide.md` · `pipeline/Conclusions.md` · `STATUS.md` (live status).
