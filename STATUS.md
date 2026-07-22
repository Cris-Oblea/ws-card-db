# ws-card-db — Status

> Living status file. Update at the end of each session.  
> Repo: [Cris-Oblea/ws-card-db](https://github.com/Cris-Oblea/ws-card-db).

**Last updated:** 2026-07-22

## Current state

- **Query app:** static site in `site/` (~40.4k cards, sql.js + `ws.sqlite`). Run locally: `python -m http.server` from `site/`.
- **Cost pipeline:** validated ~98% (15,346 abilities). Excel cost sheets generated on demand via `pipeline/build_official_list.py` (local, not versioned).
- **EN-exclusive sets (WX/SX):** 1,439 cards with EN-native costing.
- **EN coverage: names 100% · ability text 100% · traits 100%.** Cascade official EN → simulator → Heart of the Cards → LLM (`name_tr`/`abilities_tr`/`trait_tr`) → blank. Curated **legacy-disparity exclusions** (DG/P4/PI/LL whole-franchise, FT only S120, BD W63-102/103/104 + W03) prevent renumbered old sets from grafting the wrong English name. See `documentation/en-name-matching.md`. Remaining: only 2 `#NAME?` data-error cells — all real cards are bilingual.
- **Translation sources:** `pipeline/extract_simulator.py` (fan WS game `CardData.txt` → `name_sim.json`/`traits_sim.json`/`abilities_sim.json`, ~+19.8k names; set-parity filtered) · `pipeline/fetch_hotc.py` (Heart of the Cards → `name_hotc.json`, 2,909 names, JP-name-keyed; correct even for blocked legacy; rate-limited, paces slowly) · LLM pass (`pipeline/_tr2_extract.py` → batches → agents → `name_tr.json`/`abilities_tr.json`/`trait_tr.json`). Re-run the sim extractor with the new dated path when the simulator updates.
- **NK/W30 regional variants:** 4 Nisekoi cards modeled as 8 (4 JP "Maiden's Heart" + 4 EN-exclusive "The One", same code, different effect by language). See `documentation/en-name-matching.md`.
- **Repo visibility:** public since 2026-07-22. **GitHub Pages:** auto-deploys on every push to `main` via `.github/workflows/deploy-pages.yml`, which now runs `build_db.py` fresh in CI — `site/ws.sqlite(.gz)` is no longer committed (79 historical committed copies had bloated `.git` by ~820MB; see `documentation/WEBAPP.md` "Deploy").

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

### JP/EN data refresh — ✅ DONE + BUILT 2026-07-21/22 (uncommitted, awaiting owner review)

- **Data-refresh plan** (architect) — every located hand-fix (color, side, name, power/level, EN
  legacy-disparity) lives in code (`clean_cardlist.py` `OVERRIDES`, `build_db.py`
  `CARD_FIX`/`SIDE_FIX`/`NAME_OVERRIDE`/`EN_BLOCK_*`) — survives a re-harvest by construction (verified
  byte-for-byte reproducible from raw). Uma Musume (UMA, 837 cards) was already JP-covered in June; its
  **English release was the actually-new thing** (confirmed: `cardlist_en.json` now has 195 UMA/ EN
  entries — matches the whole +195 EN growth below).
- **Ingest execution** (pipeline-dev, full re-harvest — see root-cause note below): **63,350 → 64,663 JP
  cards (+1,313)**, **EN 18,532 → 18,727 (+195, all Uma Musume)**, 5 new sets (GBF Granblue Fantasy, BRD
  Brown Dust 2, RZ Re:Zero Vol.4, GA Bunko, IMC iM@S Cinderella 2026) + 131 promos, all released
  2026-06-09→07-21. 0 excluded, 0 data-quality flags, all overrides/hand-fixes verified intact, only 10
  pre-existing cards changed (benign upstream wording/katakana→kanji fixes, zero stat changes).
- ✅ **Follow-up (2026-07-22): simulator translations DID cover the new sets.** Re-ran
  `pipeline/extract_simulator.py` against a newer simulator install (dated 21 JULIO 2026) — it turned out
  to already have the new sets. Result: **502/503 new-set cards now have English** (up from 0). Rebuilt
  `site/`: still 40,393 cards/66,817 abilities, Explained% 95.6%, suspects 3544 — no regression. Distinct
  abilities count is now **15,346** (was 15,889 pre-refresh; a plausible drop, not a bug — new cards mostly
  reuse existing ability signatures rather than adding net-new ones). See [[translation-sources]] for the
  general translation-cascade approach; the specific simulator source has separate handling — see
  `NOTICE.md` (its description was deliberately genericized, not removed) for why.
- ✅ **Macro synthesis added to `extract_simulator.py` (2026-07-22) — big ability-EN coverage win.**
  The user caught that some GBF cards showed no English abilities despite the simulator clearly
  having the effect — root cause: ~25% of ALL simulator cards (not just new ones) have at least one
  ability written as a scripted macro line (e.g. `*GainPowerWithEnoughCharacters(5000,2,Granblue)`)
  instead of a `Text` line, because the game engine only needs the macro to run the effect, not a
  prose description. `pipeline/sources/macros.tsv` (236 curated macro -> English-template mappings,
  already in the repo) is now used to synthesize real English for these by substituting each macro
  call's own arguments into its template. Fixed along the way: two bugs in the substitution logic (a
  bare "X" wrongly treated as a placeholder — it's narrative-only in every template that uses it;
  "NAME" matching as a false substring of "CARDNAME", demanding a phantom extra argument).
  **Upgraded further same day**: the user pointed to the simulator's OWN engine source,
  `StreamingAssets/CommonEffects(copy).txt` (read live at runtime only — never copied into the repo,
  since it's the simulator's internal source, a step closer to the thing under the Bushiroad C&D
  than the user's own hand-curated `macros.tsv`; see `NOTICE.md`). It names each macro's parameters
  in their OWN declared order (e.g. `OnPlayMillGainPowerForEach(NUMBER,POWER,TRAITLIST)` — NUMBER
  before POWER, contradicting the fixed-priority guess the tsv-only fallback has to make), so it's
  authoritative where present; `macros.tsv` remains the fallback for macros CE doesn't define a
  `Text` line for. 30,081 of 30,150 macro lines resolve (99.8%). The ~69 still unresolved have NO
  English description anywhere in either source (internal sub-routines like `CountSoulTriggers`) —
  nothing left to extract without inventing prose.
- ✅ **Third bug found the same day (user again — spotted `BRD/W139-004` still blank): nested
  `GainEffect { ... }` blocks were double-counted as an extra ability.** A CX-combo-style ability
  that temporarily GRANTS a whole extra ability to a card is written as an outer block containing a
  `GainEffect { ... }` sub-block with its OWN `Text` line for the granted effect — but in
  `cardlist_clean.json` that granted effect is just a quoted clause INSIDE the outer ability's single
  JP text, not a separate ability. The parser was counting both, inflating that card's ability count
  by 1 and breaking build_db.py's positional-alignment check for the WHOLE card (all its abilities
  went blank, not just the extra one). Fixed via brace-depth tracking that suppresses a nested
  `GainEffect`'s own `Text`/macro lines. (First attempt at this had a self-defeating bug — checked
  for the block closing on the SAME line it opened, before its own `{` had even been seen — fixed by
  only checking on a line that actually closed a brace.) **Final site-wide ability EN coverage:
  98.9% (66,069/66,817)**, up from 98.4%. New-set coverage after this fix: GBF 85.7% (was 73.6%),
  BRD 87.0%, GA Bunko ~90%, RZ/IMC already ~98% (older franchises, more mature simulator data).
  Rebuilt `site/`: unchanged 40,393 cards/66,817 abilities,
  Explained% 95.6%, suspects 3544 (EN text doesn't feed the cost model, so no regression risk there
  by construction).
- ✅ **Fourth bug, same day (user again — `BRD/W139-003` still blank): the GainEffect fix was too
  narrow.** The real rule isn't "suppress nested GainEffect specifically" — it's "only a TOP-LEVEL
  (brace depth 0) Text/macro line is its own ability; ANY nested one (inside a plain conditional/cost
  block, not just GainEffect) is internal to whatever ability's block it's in." Replaced the
  GainEffect-specific stack with a plain depth counter gating every Text/macro line on `depth == 0`.
  **Site-wide ability EN coverage jumped to 99.86% (66,724/66,817)**; new sets: GBF 93.4%, BRD 94.9%,
  RZ/GA0/GA1/IMC all 98.4-99.0%.
- ✅ **Systematic audit of the remaining ~93 (user asked to check ALL cards site-wide, not go
  card-by-card).** Categorized: (1) a real, distinct bug — the printed "Backup" keyword ability
  (marker 【起】+【カウンター】, text "助太刀N レベルM...") is stored by the simulator as a bare numeric
  stat field, never as ability Text, so every Backup-having card's simulator count was 1 short of the
  real JP count, breaking the WHOLE card's alignment even when the simulator had perfectly good text
  for its OTHER abilities — affects 2,821 cards site-wide. Fixed in `build_db.py` (excludes
  Backup-keyword abilities from the count comparison, maps sim indices around their slot); modest
  aggregate gain (+3, most of those 2,821 cards were already covered via official-EN/cache for their
  other abilities) but fixes the actual reported case (`GBF/S134-015`) correctly. (2) Genuine simulator
  content gaps (e.g. `BD/W47-T11a`'s 2nd ability isn't in the raw file at all, no bug to fix). (3)
  Special link-tag-only markers like `RZ/S132-038`'s "王選" (just a keyword name, not prose — would
  need its own curated tag-translation table, doesn't exist). **Final site-wide coverage: 99.87%
  (66,727/66,817)** — the remainder is categories 2-3, not fixable without new reference material.
- ✅ **Multiplicative cost model extended: Salvage cabled, Search investigated (2026-07-22).** Picked up
  exactly where the June 21 rollout left off (only `Power Pump (self)` was cabled). `salvage_estimate()`
  in `cost_model.py` reads Salvage's base as a 2-way categorical split (net-0 recycle = 500, net+1 upgrade
  = 1000) instead of a formula, since Salvage's value is the swap's net advantage, not a printed number.
  Validated on 729 isolated single-ability measured samples: **86.1% within ±500** vs the flat median's
  75.0% (comparable to Pump's own 84%/75% win). Search was investigated too (1080 samples) but found to be
  qualitatively harder — its cost is dominated by WHICH deck-manipulation mechanic a package uses (not the
  same base modulated by conditions), needing a per-mechanic lookup table rather than a formula — correctly
  left on the flat median instead of forcing an unreliable wire. Rebuilt `site/`: Explained% unchanged
  95.6%, suspects 3544→3537 (small real improvement, no regression). See `documentation/pump_cost_model.md`
  for the full write-up and next steps (a Search base table).
- **Root-cause fix — harvest wasn't resuming:** `harvest_cardlist.py` already supports proper incremental
  resume (JSONL + state file, appends from `last_page`), but `cardlist_full.jsonl` /
  `cardlist_full.state.json` were missing on disk (only the June 15 consolidated `cardlist_full.json`
  survived) — likely wiped by a plain `git clean -fd` at some point, since **`.gitignore` only listed
  `cardlist_full.json`**, not the two resume files (`ARCHITECTURE.md` already claimed they were ignored —
  it was aspirational, not true). **Fixed**: both now added to `.gitignore`. Next refresh should resume
  incrementally instead of re-scraping all ~65k cards, as long as nobody manually deletes those two files.
- **Build (2026-07-22):** ran `build_db.py` on the combined new-cards + CXC-floor-fix state. **40,393
  cards / 66,817 abilities** shipped to `site/ws.sqlite.gz`. **Explained% 95.6%** (unchanged from the
  CXC-only number — the +1,313 new cards didn't regress it), **suspects 3544** (up from 3481 pre-refresh,
  expected — more cards, some brand-new signatures not yet well measured). Validation |err|≤500 on 99%.
  **Nothing committed yet** — 19 files sitting as working-tree changes, owner wants to review before commit.
- ✅ **CX-Combo floor investigation** (cost-analyst, done 2026-07-21): lowered `CXC_FLOOR` from **500 → 0**
  in `pipeline/cost_model.py` (+ the EN pass). Only ~230 CXC sigs were clamped by the 500 floor, ALL
  single-occurrence residuals; flooring a lone CX-Combo absorber above its card's own residual was itself
  manufacturing suspects. Empirically **Explained% 95.5→95.6%** and **suspects 3555→3481 (−74)** — no
  regression, well above the 94% gate. **Owner decision (2026-07-21): keep floor=0, do NOT go full
  no-floor.** A full recompute with the floor fully disabled (diagnostic only, not shipped) found **89**
  sigs would go negative (not cost-analyst's original 62 estimate — a fuller cascade recompute finds
  more), and the distribution is damning: 32 sit at a plausible -500, but **29 land between -5000 and
  -6500**, with 17 landing on the exact same -6500 across unrelated card text — almost certainly cascade
  noise from an over-costed companion ability elsewhere on those cards (see the Search-family lead above),
  not real designer signal. Publishing those would hurt the site's credibility more than "no floor" gains
  in philosophical purity. Revisit full no-floor only after the Search over-cost (and similar) are fixed.

### ⏳ NOT STARTED: extend the multiplicative cost model beyond Power Pump (self)

Owner request 2026-07-21: apply `documentation/pump_cost_model.md`'s multiplicative model to more
ESTIMATED-tail families (today only `Power Pump (self)` is cabled). Launched a `cost-analyst` agent to
pin down salvage/search bases + decide on wiring trigger-difficulty, but it **hit the account session
limit before making any change** — `pipeline/cost_model.py` still has ZERO multiplicative-model code
beyond the pre-existing Power Pump (self) cabling (verified via diff). Needs a fresh session to actually
start: see `pump_cost_model.md` §"Next levers" for exactly where to pick up (salvage/search bases, hard-
condition-strength ×0.25 vs ×0.5, rounding direction — all still open per that doc).

### English migration (deferred — code & folders)

Docs, `CLAUDE.md` and `.claude/agents/` are already English (2026-06-17). Still pending — do it as a careful, dedicated pass (some of it changes behavior), verifying the pipeline still runs after each step. The native **Japanese card data stays as-is** (it's the source).

- ✅ Done (2026-06-19): translated the remaining Spanish in code comments and Excel labels (`pipeline/build_master_list.py`, `build_official_list.py`, `build_cost_sheet.py`, `official_en.py`, `build_features.py`). The DB/web (`build_db.py`, `site/`) were already English. Japanese card data kept as-is (it's the source); the two `.xlsx` output filenames are left as-is.
- ✅ Done (2026-06-19): renamed `pipeline/fuentes/` → `pipeline/sources/` (+ all references) and translated the Spanish `.xlsx`/`.md` filenames to English (`Complete_Abilities_List`, `Ability_Cost_Guide`, `Conclusions.md`). Generated `.xlsx` are no longer versioned (gitignored).

### Cost accuracy improvement — THE focus from now on

Translation is done, so future sessions are **only** about cost-model accuracy. (The "98%" is a consistency metric, not per-ability correctness — validate against real cards via the live site.)

**Done 2026-06-20:**
- ✅ **CX Combo** is its own family, detected by climax-area text, resolved LAST as the residual absorber, floor ≥0 (no arbitrary 500 minimum since 2026-07-21 — see the floor-investigation entry above), no ceiling.
- ✅ **【リプレイ】 (replay)** abilities folded into their citer and counted once (handles pure-anchor / cost-gated / CX-combo / modal-wrapper). All 21 replay cards reconstruct exactly.

**Next leads:**
1. **Over-costed companion families surfaced by the CXC absorber** — standout: **Search effects valued ~+8000** (`SAO/S51-073`). Likely a mis-costed family → investigate/correct.
   - **Corroborating evidence (2026-07-21):** ran the CX-Combo model with `CXC_FLOOR` fully disabled (diagnostic only, not shipped — see the CXC floor decision below) to see what the raw unfloored residuals look like. ~90 sigs go negative; 17 of them land on EXACTLY -6500 with otherwise unrelated card text, incl. `SAO/S51-073` itself. That's the same card already flagged for the Search over-cost — strong evidence the -6500 cluster IS that same downstream noise (an over-costed companion ability elsewhere on the card dragging the CXC absorber deeply negative), not independent signal. Worth fixing the Search family cost first, then re-checking whether the -6500 cluster shrinks.
   - **Saved for follow-up:** the full list (all ~90 cards/sigs, sorted most-negative-first, with sample size/method/full JP text) is at `pipeline/analysis/cxc_negative_candidates.csv` (gitignored, local-only, like the rest of `pipeline/analysis/` — regenerate via the diagnostic if lost). Use it to hunt which OTHER ability family on each of those cards is over-costed.
2. `suspects_report.xlsx` (top variants by impact × uncertainty) → `golden_costs.json` (anchor + regression) → validate ~20 variants/session → rebuild → measure.

**Error hotspots:** estimated/LOW, bad residual seeds, era mixing, gate floor, drawback sign, over-costed families (Search).

### Era / dating

- `release_year` / `era` features exist in `features_by_card.csv` but not fully propagated into the live cost motor
- Study power-creep elbows (~2015, ~2024 — distinct from 2017 Standby marker)
- Non-additive operators (modal/replacement) still assumed as sum in residual

## Dependencies

- **Consumes:** official JP/EN card lists, Bushiroad rules (see `reference/`, `pipeline/sources/`)
- Card images are not versioned (not tracked in git, see `.gitignore`)

## Do not commit

- Regenerable/local-only JSON (`pipeline/ingest/cardlist_full.json` raw harvest, `site/ws.sqlite`
  uncompressed, etc.) — see `.gitignore`. **`pipeline/cardlist_clean.json` is NOT in this list** — it
  IS committed on purpose (the JP source of truth; see `documentation/ARCHITECTURE.md` §4). Verified
  2026-07-21: it's fully reproducible byte-for-byte from the on-disk raw harvest + the code-level
  override layers (`clean_cardlist.py` `OVERRIDES`, `build_db.py` `CARD_FIX`/`SIDE_FIX`) — there are
  no orphaned direct hand-edits to protect.
- `pipeline/_tr_batches/` temp outputs (regenerable)
