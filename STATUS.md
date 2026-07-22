# ws-card-db — Status

> Living status file. Update at the end of each session.  
> Repo: [CrisRP-dev/ws-card-db](https://github.com/CrisRP-dev/ws-card-db) · Portfolio project **1 of 3**.

**Last updated:** 2026-07-21

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

### Repo landing page + public-release prep (2026-07-21)

- ✅ `README.md` rewritten as a full landing page (badges, key metrics, quick start, architecture
  diagram, documentation map). GitHub "About" description + topics updated to match.
- ✅ Security/legal audit before a possible public release: full git-history scan (103 commits) for
  secrets/PII — clean. `.github/workflows/ci.yml` already runs a gitleaks secret scan on every push
  (discovered this session; `CLAUDE.md`'s old "no CI" claim was stale, now fixed).
- ✅ Removed a leaked personal-sounding contact email (`agentic@propital.com`) from 4 scraper
  `User-Agent` strings — the project has no public contact besides the GitHub repo itself.
- ✅ Added `NOTICE.md`: full IP/legal disclaimer, sourcing breakdown, and takedown-request process,
  as the written prerequisite the owner wants in place **before** flipping the repo public.
- ✅ Removed the unused MCP server (`tools/ws-mcp/`) — never used day to day, and `search_cards`/
  `get_card` were redundant with what the public site already shows. Dropped the `mcp` dependency;
  merged the gitleaks-action Dependabot PR, closed the now-moot mcp-version-bump PR.
- ⏳ **Not yet done:** actually flipping repo visibility to public (owner wants `NOTICE.md` reviewed
  first) and uncommenting the `push` trigger in `deploy-pages.yml`.

### Bilingual JP→EN translation — COMPLETE (2026-06-20)

EN coverage is now **names 100% · abilities 100% · traits 100%** (only 2 `#NAME?` data-error cells remain). Achieved via the cascade official EN → simulator → Heart of the Cards → LLM pass (see "Current state" + `documentation/en-name-matching.md`). The old `pipeline/_tr_batches/` + `_tr_extract.py` flow is superseded by `_tr2_extract.py` and the `name_tr.json`/`abilities_tr.json`/`trait_tr.json` artifacts that `build_db.py` loads.

**Phase 2 (later, optional):** flavor text (~37k JP) is still untranslated; neo-standard title names are covered.

## Next up (not blocked)

### In flight (launched 2026-07-21, check for results before re-launching)

- **Data-refresh plan** (architect): locate where hand-made per-card fixes (wrong color/type corrected,
  etc.) live relative to `pipeline/cardlist_clean.json`, and design a safe procedure to pull in new JP
  sets + new official EN text (incl. the new **Uma Musume** set and its "Inspire"/継承 keyword) without
  reverting those fixes. Report expected before any dev-agent touches the pipeline.
- **CX-Combo floor investigation** (cost-analyst): re-examine `CXC_FLOOR = 500` in `pipeline/cost_model.py`
  — the owner argues CX-Combo, being always resolved LAST as the pure residual absorber, shouldn't have an
  artificial floor (or ceiling) at all. Investigate empirically (how many sigs are actually clamped, does
  removing it hold `Explained% >= 94%`) before changing anything.

### English migration (deferred — code & folders)

Docs, `CLAUDE.md` and `.claude/agents/` are already English (2026-06-17). Still pending — do it as a careful, dedicated pass (some of it changes behavior), verifying the pipeline still runs after each step. The native **Japanese card data stays as-is** (it's the source).

- ✅ Done (2026-06-19): translated the remaining Spanish in code comments and Excel labels (`pipeline/build_master_list.py`, `build_official_list.py`, `build_cost_sheet.py`, `official_en.py`, `build_features.py`). The DB/web (`build_db.py`, `site/`) were already English. Japanese card data kept as-is (it's the source); the two `.xlsx` output filenames are left as-is.
- ✅ Done (2026-06-19): renamed `pipeline/fuentes/` → `pipeline/sources/` (+ all references) and translated the Spanish `.xlsx`/`.md` filenames to English (`Complete_Abilities_List`, `Ability_Cost_Guide`, `Conclusions.md`). Generated `.xlsx` are no longer versioned (gitignored).

### Cost accuracy improvement — THE focus from now on

Translation is done, so future sessions are **only** about cost-model accuracy. (The "98%" is a consistency metric, not per-ability correctness — validate against real cards via the live site.)

**Done 2026-06-20:**
- ✅ **CX Combo** is its own family, detected by climax-area text, resolved LAST as the residual absorber, floor ≥500, no ceiling. CXC subset 93.4%→95.0%; negative/zero/below-500 CXC costs → 0.
- ✅ **【リプレイ】 (replay)** abilities folded into their citer and counted once (handles pure-anchor / cost-gated / CX-combo / modal-wrapper). All 21 replay cards reconstruct exactly.

**Next leads:**
1. **Over-costed companion families surfaced by the CXC absorber** — standout: **Search effects valued ~+8000** (`SAO/S51-073`). Likely a mis-costed family → investigate/correct.
2. `suspects_report.xlsx` (top variants by impact × uncertainty) → `golden_costs.json` (anchor + regression) → validate ~20 variants/session → rebuild → measure.

**Error hotspots:** estimated/LOW, bad residual seeds, era mixing, gate floor, drawback sign, over-costed families (Search).

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
