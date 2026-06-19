# ws-card-db — Status

> Living status file. Update at the end of each session.  
> Repo: [CrisRP-dev/ws-card-db](https://github.com/CrisRP-dev/ws-card-db) · Portfolio project **1 of 3**.

**Last updated:** 2026-06-17

## Current state

- **Query app:** static site in `site/` (~39.9k cards, sql.js + `ws.sqlite`). Run locally: `python -m http.server` from `site/`.
- **Cost pipeline:** validated ~98% (15,889 abilities). Excel cost sheets generated on demand via `pipeline/build_official_list.py` (local, not versioned).
- **EN-exclusive sets (WX/SX):** 1,439 cards with EN-native costing.
- **GitHub Pages:** not enabled (private repo).

## Resume phrases

| Task | Say |
|---|---|
| Bilingual translation | *"continue with the translation"* |
| Cost accuracy (saturday session) | *"golden costs session"* or *"suspects report"* |

## Blocked / paused

### Bilingual JP→EN translation (paused — usage limit, 2026-06-15)

Infrastructure is ready (`pipeline/_tr_extract.py`, `_tr_manifest.json`, workflow ~41 Sonnet agents).

**Gap after official-EN rescue (not yet merged to DB):**

| Field | Remaining |
|---|---|
| Abilities | ~7,327 |
| Card names | ~22,446 |
| Traits | ~548 |

**Local progress (not merged):** `pipeline/_tr_batches/` — **10 / 16** ability `.out.json` files done (`0001`, `0004`, `0007`–`0013`, `0015`). Name batches (24) and trait batch (1) have input JSON only; no `.out.json` yet.

**Steps to resume:**

1. `python pipeline/_tr_extract.py` (refresh batches/gap)
2. Run translation workflow → write remaining `.out.json`
3. Validate each output covers all keys in its batch
4. Merge into `abilities_tr.json`, `name_tr.json`, `trait_tr.json`
5. `python pipeline/build_db.py` → rebuild `site/ws.sqlite`

**Phase 2 (later):** flavor text (~37k JP), neo-standard title names (74 JP-only franchises).

## Next up (not blocked)

### English migration (deferred — code & folders)

Docs, `CLAUDE.md` and `.claude/agents/` are already English (2026-06-17). Still pending — do it as a careful, dedicated pass (some of it changes behavior), verifying the pipeline still runs after each step. The native **Japanese card data stays as-is** (it's the source).

- ✅ Done (2026-06-19): translated the remaining Spanish in code comments and Excel labels (`pipeline/build_master_list.py`, `build_official_list.py`, `build_cost_sheet.py`, `official_en.py`, `build_features.py`). The DB/web (`build_db.py`, `site/`) were already English. Japanese card data kept as-is (it's the source); the two `.xlsx` output filenames are left as-is.
- Rename the folder **`pipeline/fuentes/` → `pipeline/sources/`** and update every code reference to it.

### Cost accuracy improvement (planned saturday sessions)

User still sees wrong costs in places. Plan not implemented yet:

1. Generate `suspects_report.xlsx` (top variants by impact × uncertainty)
2. Create `golden_costs.json` + wire into builder (anchor + regression check)
3. Validate ~20 variants per session → rebuild → measure improvement

**Error hotspots:** estimated/LOW, bad residual seeds, era mixing, CX-combo/gate floor, drawback sign.

### Era / dating

- `release_year` / `era` features exist in `features_by_card.csv` but not fully propagated into the live cost motor
- Study power-creep elbows (~2015, ~2024 — distinct from 2017 Standby marker)
- Non-additive operators (modal/replacement) still assumed as sum in residual

## Dependencies

- **Consumes:** official JP/EN card lists, Bushiroad rules (see `reference/`, `pipeline/fuentes/`)
- **Feeds:** `ws-sim-ai` (card costs + structured data)
- **Related:** card images live in `WSAI/Galería/` (4.1 GB, not in git)

## Do not commit

- Regenerable JSON (`cardlist_clean.json`, `ws.sqlite`, etc.) — see `.gitignore`
- `pipeline/_tr_batches/` temp outputs (regenerable)
