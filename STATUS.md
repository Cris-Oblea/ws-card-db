# ws-card-db — Status

> Living status file. Update at the end of each session.  
> Repo: [CrisRP-dev/ws-card-db](https://github.com/CrisRP-dev/ws-card-db) · Portfolio project **1 of 3**.

**Last updated:** 2026-06-20

## Current state

- **Query app:** static site in `site/` (~39.9k cards, sql.js + `ws.sqlite`). Run locally: `python -m http.server` from `site/`.
- **Cost pipeline:** validated ~98% (15,889 abilities). Excel cost sheets generated on demand via `pipeline/build_official_list.py` (local, not versioned).
- **EN-exclusive sets (WX/SX):** 1,439 cards with EN-native costing.
- **EN coverage: names 100% · ability text 100% · traits 100%.** Cascade official EN → simulator → Heart of the Cards → LLM (`name_tr`/`abilities_tr`/`trait_tr`) → blank. Curated **legacy-disparity exclusions** (DG/P4/PI/LL whole-franchise, FT only S120, BD W63-102/103/104 + W03) prevent renumbered old sets from grafting the wrong English name. See `documentation/en-name-matching.md`. Remaining: only 2 `#NAME?` data-error cells — all real cards are bilingual.
- **Translation sources:** `pipeline/extract_simulator.py` (fan WS game `CardData.txt` → `name_sim.json`/`traits_sim.json`/`abilities_sim.json`, ~+19.8k names; set-parity filtered) · `pipeline/fetch_hotc.py` (Heart of the Cards → `name_hotc.json`, 2,909 names, JP-name-keyed; correct even for blocked legacy; rate-limited, paces slowly) · LLM pass (`pipeline/_tr2_extract.py` → batches → agents → `name_tr.json`/`abilities_tr.json`/`trait_tr.json`). Re-run the sim extractor with the new dated path when the simulator updates.
- **NK/W30 regional variants:** 4 Nisekoi cards modeled as 8 (4 JP "Maiden's Heart" + 4 EN-exclusive "The One", same code, different effect by language). See `documentation/en-name-matching.md`.
- **GitHub Pages:** not enabled (private repo).

## Resume phrases

| Task | Say |
|---|---|
| Cost accuracy (saturday session) | *"golden costs session"* or *"suspects report"* |

## Done / recent

### Bilingual JP→EN translation — COMPLETE (2026-06-20)

EN coverage is now **names 100% · abilities 100% · traits 100%** (only 2 `#NAME?` data-error cells remain). Achieved via the cascade official EN → simulator → Heart of the Cards → LLM pass (see "Current state" + `documentation/en-name-matching.md`). The old `pipeline/_tr_batches/` + `_tr_extract.py` flow is superseded by `_tr2_extract.py` and the `name_tr.json`/`abilities_tr.json`/`trait_tr.json` artifacts that `build_db.py` loads.

**Phase 2 (later, optional):** flavor text (~37k JP) is still untranslated; neo-standard title names are covered.

## Next up (not blocked)

### English migration (deferred — code & folders)

Docs, `CLAUDE.md` and `.claude/agents/` are already English (2026-06-17). Still pending — do it as a careful, dedicated pass (some of it changes behavior), verifying the pipeline still runs after each step. The native **Japanese card data stays as-is** (it's the source).

- ✅ Done (2026-06-19): translated the remaining Spanish in code comments and Excel labels (`pipeline/build_master_list.py`, `build_official_list.py`, `build_cost_sheet.py`, `official_en.py`, `build_features.py`). The DB/web (`build_db.py`, `site/`) were already English. Japanese card data kept as-is (it's the source); the two `.xlsx` output filenames are left as-is.
- ✅ Done (2026-06-19): renamed `pipeline/fuentes/` → `pipeline/sources/` (+ all references) and translated the Spanish `.xlsx`/`.md` filenames to English (`Complete_Abilities_List`, `Ability_Cost_Guide`, `Conclusions.md`). Generated `.xlsx` are no longer versioned (gitignored).

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

- **Consumes:** official JP/EN card lists, Bushiroad rules (see `reference/`, `pipeline/sources/`)
- **Feeds:** `ws-sim-ai` (card costs + structured data)
- **Related:** card images live in `WSAI/Galería/` (4.1 GB, not in git)

## Do not commit

- Regenerable JSON (`cardlist_clean.json`, `ws.sqlite`, etc.) — see `.gitignore`
- `pipeline/_tr_batches/` temp outputs (regenerable)
