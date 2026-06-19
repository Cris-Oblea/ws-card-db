# ws-card-db — How it works (overview)

> Starting document of `documentation/`. Summarizes WHAT it does, HOW it works, HOW it was built and WHAT technologies it uses. Expand as the project grows (see the rule in the `CLAUDE.md`).

## What it does
Measures the **power cost per ability** of Weiss Schwarz cards, to serve as a **balance reference when designing custom cards** ("I want this effect → it costs X power"). Cost = power SUBTRACTED from the base (`power_real = power_base − cost`), always in **multiples of 500**.

## How it works (the flow)
1. **Harvest** (`pipeline/ingest/harvest_cardlist.py`): scrapes the official JP list (ws-tcg.com) with polite throttling and resumable state.
2. **Clean** (`clean_cardlist.py`): normalizes the raw → `cardlist_clean.json` (63,350 JP cards, UTF-8 NFKC).
3. **Date** (`date_sets.py` → `set_dates.json`): assigns `release_year` and `era` per set (legacy <2017 / modern ≥2017). `build_card_era.py` then projects that onto each card → `card_era.json` (era buckets configurable). Power-creep matters.
4. **Cost model** (in the `build_*.py`), three confidence levels:
   - **HIGH (measured):** derived from the card's real power vs its base.
   - **MEDIUM (residual):** inferred on cards with several abilities, subtracting the already-measured ones.
   - **LOW (estimated):** model when there's no measurement.
   - Base power ≈ `3000 + 2500·Level + 1500·Cost − 1000·[Soul trigger] − 1000·(Soul−1)`.
5. **Outputs:**
   - `build_official_list.py` → `Complete_Abilities_List.xlsx` (15,889 abilities; local Excel, generated on demand).
   - `build_db.py` → `site/ws.sqlite(.gz)` for the web.
   - `build_cost_sheet.py` → `Ability_Cost_Guide.xlsx` (model for costing new effects).
6. **Web** (`site/`): static app — downloads `ws.sqlite.gz`, gunzips with pako, sql.js in memory, queries in the browser. **No backend.**

## How it was built / validation
- Sources: official JP list (scrape) + official EN (harvest) + Bushiroad rules/manuals (`reference/`, `pipeline/sources/`).
- **Empirical validation:** ~98% accuracy against the official list. There are NO unit tests — the oracle is the official list + audits (`cardlist_audit.json`, counts, suspects).
- De-dup: keeps the base rarity, discards alt-art/parallels.

## Technologies
- **Python 3.14** (stdlib: json/sqlite3/re/urllib/csv/statistics/unicodedata) + **`openpyxl`** (Excel) + **`mcp>=1.0`** (the MCP server in `tools/ws-mcp/`).
- **Web:** HTML5 + vanilla JS + **`sql.js`** + **`pako`** + **SQLite**.

## Key data
- 63,350 JP cards + 18,532 EN · 15,889 distinct abilities · 74 Neo-Standard franchises · legacy/modern eras.
- `pipeline/translation_cache.json` = PERMANENT translation cache (**do not delete**).

## Status
Pipeline validated at 98%; web in production (~40k cards). In progress: bilingual JP→EN translation (10/16 batches) + accuracy improvement ("suspects" detection + golden costs).

## To go deeper
`pipeline/README.md` · `pipeline/Ability_Cost_Guide.md` · `pipeline/Conclusions.md` (the model in detail) · `STATUS.md` (live status).
