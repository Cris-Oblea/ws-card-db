# ws-card-db — Status

> Living status file. Update at the end of each session.  
> Repo: [Cris-Oblea/ws-card-db](https://github.com/Cris-Oblea/ws-card-db).

**Last updated:** 2026-07-23 (family-taxonomy audit round 9)

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
- ✅ **Look & Reorder cabled + scaling Power Pump estimator (2026-07-22).** Two user-reported miscosts:
  `5HY/W101-003` (a name-restricted Look & Reorder was priced at the ungated 1000 instead of 500) and
  `5HY/W101-004` (a per-unit-scaling Power Pump — "…×your ‹Trait› count×500" — was hitting the flat
  Power-Pump-(self) median instead of scaling with the count). Fixed: `look_reorder_estimate()` (base 1000,
  halved per condition, 14 isolated samples — thin data, narrowly guarded) and `_pump_scale_estimate()`
  (reads the per-unit rate, multiplies by an assumed matching-card count keyed off the count-source phrasing
  — 90.5% exact / 97.5% within ±500 on 644/735 isolated samples, the best fit of any estimator cabled so
  far). See `documentation/pump_cost_model.md`.
- ✅ **Family-taxonomy audit pass (2026-07-22).** User-driven methodology: a family name must reflect the
  ability's FINAL EFFECT only (never its cost/trigger/requirements — those are the cost model's job, not
  the name's). Built `pipeline/analysis/family_catalog.txt` (61 families, sig/occurrence/measured-residual-
  estimated counts) and used it to audit the 1547-signature "Card Select" grab-bag (the family had no
  in-game meaning — "select N cards" describes dozens of unrelated mechanics). Result: `Card Select` dropped
  1547 → 361 sigs. Changes in `pipeline/cost_model.py`:
  - **New `Removal (...)` group** — every ability whose final purpose is "get the opponent's STAGE character
    out of play," split by destination (not lumped into one family) because destination changes the cost
    floor, mirroring the existing per-color `RedBomb*` split: `Removal (Hand)` (renamed from `Bounce`, both
    the FAMPAT text-pattern AND the `バウンス` keyword entry in `KW`, AND the EN-side `en_family` pattern — all
    three pointed at the same effect and needed the same rename), `Removal (Waiting Room)` (renamed from
    `Disruption`), `Removal (Deck Bottom)`, `Removal (Deck Top)`, `Removal (Memory)` (usually temporary —
    returns to stage at the next Encore step), `Removal (Swap)` (opponent forced to replace it with a weaker
    character from their own waiting room). `Clock Kick` explicitly stays OUT of this group (user: its
    purpose is uncancellable damage delivery, not board control — contrast with a heal-then-clock "GreenBomb"
    variant, which IS a damage-family effect).
  - **`ReviveOpponent`** (name proposed by Claude, not yet confirmed by the user) — the mirror image of
    Removal: an opponent's own waiting-room character placed onto their own stage, to give one of the
    player's own reverse-requiring finishers a legal target (`RSL/S56-002`).
  - **`AllMemoryCleanse`** — a symmetric "every player trims their Memory to N" housekeeping effect.
  - **`AddMarkerWaitingRoom`** — park a card as a marker under this card, to retrieve later (banked resource,
    not an immediate effect); named for the dominant source (own waiting room) even though the regex is
    destination-anchored (`マーカーとして…置`) to also catch the rarer stage-source / self-becomes-marker
    variants without fragmenting into more sub-families than the data supports.
  - **`Drawback`** — the OPPONENT acts against the CARD'S OWN CONTROLLER's zones (e.g. "the opponent may
    choose a character from YOUR waiting room and put it on top of YOUR deck") — the negative-polarity
    mirror of Disruption/Opp Disrupt. Confirmed via `BD/W54-P03`'s full card context (two such drawback
    abilities justify its power being 1000 over vanilla for a level-1/cost-0 print).
  - **Two conjugation-coverage bugs found and fixed** (both are strict widenings, verified zero false
    positives against the full 15,889-ability corpus): `Draw`/`DrawDiscard`/`DiscardCharacterToDraw`'s
    `引[くき]` missed the very common て-form "…引いてよい" (may draw) — widened to `引[くきい]`. `Move`'s
    `動かす` (dictionary form only) missed "…動かしてよい" (may move) — widened to the stem `動か`.
  - Rebuilt `site/`: Explained% 95.6%→95.3%, suspects 3544→3594 — a small, expected dip (splitting a family
    into finer-grained ones means each new sub-family starts with fewer pooled samples behind its standard
    until more cards accumulate against it; still comfortably above the 94% floor).
  - `ReviveOpponent` name **confirmed by the user** in the follow-up round below.
- ✅ **Family-taxonomy audit, round 2 (2026-07-22, same session).** Continued the Card Select cleanup with
  full-card examples in English per the user's request (they don't read Japanese). Result: `Card Select`
  361 → 139 sigs.
  - **`Comeback` renamed to `Summon`** — the old name collided with the official CLIMAX TRIGGER ICON
    "Comeback", a different game concept (user-flagged). Same purpose as before (own character, any zone,
    straight onto the stage bypassing cost/level), widened to accept a NAMED target (`「N」`) in addition to
    the literal word キャラ (most real prints name the character rather than saying キャラ), and to accept
    手札/思い出置場/クロック置場 as additional sources.
  - **`Move` split into `Move (Own)` / `Move (Opponent)`** — same underlying action, but a different
    tactical purpose depending on whose board it targets, per the user's confirmation. Also fixed:
    the `枠に` requirement was a fixed literal-prefix list (前列に/後列に/の枠に/…) that missed common real
    phrasings ("…いない枠に", "…いる枠に"); widened to any "…枠に". Excluded the negative form 動かせない ("cannot
    be moved" — a lock/restriction, not an actual move) via a negative lookahead, and added it to
    `Restriction`'s pattern instead.
  - **`Change` (text-form)** — folded cards that spell out the official チェンジ keyword's mechanic in full
    text (this card retreats as the cost, a replacement fills its exact vacated slot, `このカードがいた枠に置く`)
    into the SAME family as the keyword-triggered `Change`, since it's the identical game mechanic.
  - **New families:** `Memory Bank` (own waiting-room card banked into Memory), `Return to Deck (Own)` (own
    waiting-room card back into own deck — mirrors the existing opponent-side `Return to Deck`), `Deck Thin`
    (deck search sent to waiting room instead of hand), `Free Play (Alt Cost)` (discard a named own card to
    play THIS card for 0 cost — 30 cards share the exact templated phrasing), `Self Sacrifice` (the card's
    own ability sacrifices another own character, not via a payment bracket — distinct from `Drawback`,
    where the OPPONENT acts against your zones), `Attack Redirect` (redirect this card's attack to a
    different opponent character), `Clock/WR Exchange` (swap the bottom card of your own clock for a
    waiting-room character — clock size unchanged, only content changes; user: useful for fixing color
    requirements or freeing a character the clock was trapping).
  - **Widened existing families:** `Return to Deck` (added 置く as a destination verb alongside 戻す/加える),
    `Retreat` own-stage branch (added "他の自分の…" alongside the literal "自分の舞台の…"), `Opp Disrupt` (added
    控え室 as a target zone, AND the REFLEXIVE construction 相手は自分の… — most real prints use this topic-marker
    phrasing, not the possessive 相手の…, and the possessive-only pattern silently missed all of them),
    `AddMarkerWaitingRoom` (added the RETRIEVAL half of the same marker mechanic — markers coming back out
    onto the stage, not just being banked).
  - **General KW-loop bug found and fixed**, same class as the earlier アンコール/集中 gate-vs-effect fixes but
    applying to ALL 12 keywords at once: `『keyword』を持つ` ("[a card] that HAS this keyword") always cites the
    keyword as a SEARCH CRITERION for some OTHER card, never the keyword's own action (e.g. a deck-search for
    cards with 『Change』 was wrongly filed as `Change` itself instead of `Search`). Found via a spot-check of
    the new `Change` family (291 sigs, 12 of them this false positive); fixed with one general guard instead
    of one-off exceptions. Affects all 12 KW entries, not just Change.
  - Rebuilt `site/`: Explained% flat at 95.3%, suspects 3594→3593 (no regression). `pipeline/analysis/
    family_catalog.txt` regenerated (69 families, up from 61). `documentation/COST_MODEL.md` §6 updated.
  - **Remaining:** `Card Select`'s long tail (139 sigs, mostly n≤2 one-offs) is unaudited, future work.
- ✅ **Family-taxonomy audit, round 3 (2026-07-22, same session) — `Card Select` eliminated completely.**
  User asked to get Card Select all the way to zero, then move on to auditing other effects still lacking
  a family. Worked through the remaining 99 → 34 → 10 signatures in three passes, widening gap/verb tolerances on
  existing families and adding new ones for genuine recurring patterns:
  - **New families:** `CX Exchange` (swap a climax card between two zones, matched by trigger icon — a
    combo-assembly tool), `Stock Search` (look at your own stock, take a card to hand), `Clock/Hand
    Exchange` (a clock character comes to hand, refilled from a hand or deck-top card), `Removal (Stock)`
    (opponent's stage character sent to the OPPONENT's OWN stock, 136 occurrences — **corrected 2026-07-22
    post-ship**: my first write-up wrongly described this as the ACTOR capturing the character into their
    own stock; the user caught it — Weiss Schwarz never mixes cards from different owners in one zone, so
    an unmarked ストックに置く destination on an opponent's character can only mean their own stock), `Grant
    Trait` (assign a chosen character a designated trait for the turn).
  - **Widened for gap/verb gaps found via real-card near-misses** (a level+cost double condition, a
    trigger-icon descriptor, a placement-order phrase, etc. kept pushing distances just past the old
    limits): `Summon`, `AddMarkerWaitingRoom`, `Memory Bank`, `Removal (Memory)`, `Removal (Waiting Room)`,
    `Removal (Deck Bottom)` (+ added `このカードのバトル相手`/`このカードとバトル中のキャラ` as opponent-reference
    alternatives to the possessive 相手の), `Stock Gen`, `Return to Deck (Own)`, `Retreat` (+ a 3rd bare
    "自分の…キャラ" branch — carefully excluded from also matching Salvage's territory, see below), `Self
    Sacrifice` (+ a random-hand-discard branch), `Power Pump` (+ a named-target branch), `Change` (+ a
    defensive-swap branch and a 動かす verb).
  - **Caught and reverted a real regression before it shipped:** the new bare Retreat branch
    ("自分の…キャラ…選び…手札に戻") was written too broadly and would have hijacked EVERY Salvage-shaped ability
    (自分の控え室のキャラ…手札に戻す) into Retreat instead, since Retreat is checked earlier in the list. Fixed
    with a negative lookahead excluding 控え室/山札/思い出置場/クロック置場/手札 right after 自分の. Verified with a
    direct before/after regex test, not just the aggregate counts, precisely because aggregate counts alone
    would NOT have caught this (Salvage's total count barely moved — the regression was masked by other
    families losing/gaining similar amounts elsewhere).
  - **Found a real pre-existing latent bug, unrelated to this session's other work:** `Clock Kick` had been
    **completely dead (0 real matches, absent from the family catalog) since before this session started**
    — its `(クロック置場|クロックに)置` alternation never required the に between 置場 and 置, so it could never
    match the actual phrasing `クロック置場に置く`. Found only because auditing why specific cards still landed
    in Card Select led to checking why Clock Kick wasn't claiming them. Fixed.
  - **`Card Select` (the generic `\d+枚選` catch-all FAMPAT entry) deleted outright once the tail (10
    signatures) was confirmed to be genuinely bespoke one-off card designs** (a unique named skill, a
    symmetric apocalyptic reset effect, a bare targeting step with no destination) rather than a recurring
    pattern. Those now honestly fall to `Other` instead of a misleadingly-generic label. **1547 → 0
    signatures across the full three-round audit.**
  - Rebuilt `site/`: Explained% flat at 95.3%, suspects 3593→3588 (small real improvement). `pipeline/
    analysis/family_catalog.txt` regenerated (74 families, up from 69). `documentation/COST_MODEL.md` §6
    updated, including an explicit "do not re-add a generic catch-all" note for future sessions.
  - **Next (per the user's own framing — "continue with other effects that don't have a family yet"):**
    audit the `Other` family itself (516 signatures) the same way — it's the function's honest fallback, but
    likely still contains recurring patterns that deserve a real name, same as Card Select did. Not started
    yet this session.
- ✅ **`Other` audit, round 1 (2026-07-22, same session).** After Card Select hit 0, moved straight to
  `Other` (3804 occurrences / 505 sigs) per the user's earlier request to continue with other un-familied
  effects.
  - **User-reported bug: `SAO/S47-107` (a plain, non-CX-combo Clock Kick) was in `Other`.** Root cause: a
    THIRD way real cards refer to "the opponent's character" (relative to the already-established
    相手の…キャラ / このカードの正面のキャラ) — `そのバトル相手`/`このカードのバトル相手` (a noun) or a bare `そのキャラ`
    pronoun whose antecedent lives in an earlier TRIGGER clause. Fixed across Clock Kick and every
    Removal (...) destination that actually has real corpus occurrences of the shape.
  - **Retroactive Bomb-taxonomy fix (user-driven, significant).** The user flagged that while every Bomb
    variant shares the same underlying function, the ability's real cost differs by BOTH level/cost
    threshold AND color — every combination needs its own distinct family, never merged. The PRE-EXISTING
    RedBombLevel0/RedBombLevelX/AntiEarlyRedBomb entries (from a prior session) wrongly lumped THREE
    different destinations (re-reverse/clock/stock) under one "Red" name — replaced with a dynamically-
    computed name (`_dynamic_bomb_name`) covering every combination: `RedBombLevel0`, `RedBombLevel1`,
    `RedBombLevel2`, `RedBombLevelX`, `AntiEarlyRedBomb` for re-reverse; the same suffixes under
    `BlueBomb*` (→ bottom of their own deck) and `YellowBomb*` (→ their own stock, usually +1 opponent
    stock loss too, 464/466 samples); `AutoKickToClock` added as a sibling of AutoKickToBottom/Memory (this
    card, self, to its own clock — no opponent involved, not a Bomb). **Green (heal+clock) not found in this
    exact shape after a real corpus search — flagged back to the user rather than guessed.**
  - **New families:** `Multi Trigger Check` (generalized to any N), `Deck Copy Limit`, `Color Bypass`,
    `Hexproof` (user's own term), `Reverse Immunity (Cost 0)`, `Level/WR Exchange`, `Free Refresh` (user's
    own term), `Self Identity Grant`.
  - `Other`: 3804 → ~1278 occurrences (505 → ~350 sigs) after this pass. Rebuilt `site/`: Explained% flat
    95.3%, suspects 3588→3607 (small expected uptick — several brand-new families start with thin sample
    pools). `pipeline/analysis/family_catalog.txt`: 101 families (was 74). `documentation/COST_MODEL.md`
    updated with the full write-up.
  - **Open, not yet resolved:** a self-reverse-trigger Bomb with a **Memory** destination (`BAV/W129-P01`,
    n=51) doesn't fit any of the 4 named colors — needs a 5th color name or a different treatment. Several
    more clusters identified (look-top-1-conditional-clock scry, self-discard-on-level-up, opponent
    trait-strip, self-discard-on-front-attack variants, hand-size/cost-reduction statics, marker-color
    self-grant) — presented to the user, not yet confirmed/implemented as of this writing.
- ✅ **Both open questions resolved + `Other` audit round 2 (2026-07-22, same session).**
  - Memory destination is NOT a 5th color — per the user, it's normally an AntiEarly effect that belongs
    to red, and red itself can be either re-reverse or Memory (a newer-era variant of the same color, both
    "soft"/temporary removals). Folded into Red alongside re-reverse.
  - Green Bomb confirmed via real cards (`AZL/S102-P02`/`T48`): heal the OPPONENT's clock (their top clock
    card → their own waiting room — the same "Heal" mechanic already established, just applied to the
    opponent's clock) as an enabler, then bury the just-reversed opponent into that freed clock slot. Was
    previously misclassified as "Opp Disrupt". User then confirmed the dynamic structure already handles
    ANY color × ANY condition automatically (verified `AntiEarlyGreenBomb`/`GreenBombLevelX` both resolve
    correctly with zero extra code) — that's the whole point of building it as a dynamic color×condition
    matrix instead of static per-combination strings.
  - Round 2 found the same opponent-reference gap class again: Bomb conditions only recognized "バトル相手の",
    not "このカードとバトルしている/バトル中のキャラの" — fixed via a shared `_BOMB_OPP` fragment. Removal (Deck
    Top) widened for the そのキャラ+earlier-antecedent shape. Self Identity Grant widened for a
    "手札にこのカードがあるなら" prefix and a bare unconditional "このカードは…を得る" (fixed color, or color
    derived from this card's own markers). Grant Trait widened to also accept granting a TRIGGER ICON.
    New families: `Clock Gen` (sibling of Stock Gen), `Marker Currency` (a banked marker substitutes for a
    stock card when paying a cost).
  - Gates flat both times (95.3%; suspects 3607→3606→3611). `Other` now ~340 sigs / ~1150 occurrences.
  - **Still open, presented but not yet confirmed:** Reverse Immunity generalization question
    (`AZL/S119-035` — same destination as `Reverse Immunity (Cost 0)` but a different condition: one broad
    family or split like Bomb?), a ~9-trigger self-discard cluster (proposed as one umbrella
    "Self-Discard (Conditional)" family, not yet confirmed), the look-top-1-conditional-clock scry
    (`MK/S11-T03_`), the opponent trait-strip (`Sks/W62-084`, candidate name "Strip Trait"), and two small
    hand-size/cost-reduction statics (`MAR/S124-P02EX`, `KJ8/S123-P02EX`).
- ✅ **`Other` audit round 3 (2026-07-22, same session) — all 5 open items resolved by the user.**
  - **`Reverse Immunity` generalized like Bomb**: every distinct condition gets its own explicit name.
    Added `Reverse Immunity (Hand4/Solo)` alongside the existing `Reverse Immunity (Cost 0)`.
  - **`Drawback` generalized** beyond "the opponent acts against you" to ANY self-inflicted, no-upside
    risk, confirmed via vanilla-power-delta math across 9 candidate cards spanning 9 different triggers
    (level-up, unpaid cost, no matching ally, front-attacked-with-no-opponent, Encore step, a linked ally
    leaving, opponent playing any climax, uncancelled damage, a conditional deck-reveal risk): 8/9 price
    at/above vanilla (the Drawback signature); the 9th (`DC/W09-008`) prices BELOW vanilla — a real
    beneficial ability, not a drawback — and instead widened `AutoKickToMemory`'s trigger to also cover
    "leaving the stage" (not just "on reverse").
  - **New families:** `Strip Trait` (negative-polarity mirror of `Grant Trait`), `HandSizeLimit+1` (a
    rules-modifying static), `Hand Discount` (a named external hand card's cost OR level −N — checked
    BEFORE `Early Play`, whose broader pattern was wrongly claiming the level-reduction variant).
  - Gates flat 95.3%, suspects 3611→3578 (**real improvement**, not just noise). `Other`: 3804 → 606
    occurrences (505 → 237 signatures) across the full 3-round audit. `pipeline/analysis/
    family_catalog.txt`: 113 families (was 74 at the start of the Other audit).
- ✅ **`Cannot Attack` narrowed, real content moved to `Drawback` (2026-07-22, same session).** Reviewing
  `PD/S29-105`'s full ability list surfaced a bigger issue: the user clarified `Cannot Attack` should mean
  an effect inflicted ON THE OPPONENT (a disruption tool), but 523/527 real occurrences of the old broad
  pattern were SELF-referential (this card restricting its own attacking) — a `Drawback` by the same rule
  just confirmed above, not a disruption. Narrowed `Cannot Attack` to require an explicit opponent
  reference (0 real matches currently, left as the correctly-scoped home for if/when one is found) and
  moved the self-referential shape to `Drawback` (56 sigs / 799 occurrences now). Gates flat 95.3%,
  suspects 3578 unchanged. **Also: fixed 3 stray direct Spanish quotes accidentally left in code comments
  and docs during this session's family-taxonomy write-ups — the repo is English-only, no exceptions for
  quoting the user verbatim.**
- ✅ **CX Combo discard-gate + delete Cannot Attack + AddMarker split by zone (2026-07-22, same session).**
  Three separate findings from reviewing specific real cards.
  - **`CHA/W40-077`** was showing `Grant Ability` instead of `CX Combo` — its cost bracket discards a
    SPECIFIC NAMED CLIMAX (a 4th CX Combo gate shape, distinct from the 3 already detected on
    gen()-normalized text). Can't be caught the same way since `gen()` collapses every name to the same
    generic placeholder, losing the information needed to tell "a named climax" from "a named character."
    Fixed with a name→card-type lookup: `build_cost_model` populates a module-level `_CLIMAX_NAMES` set from
    its `clean` parameter (no new file I/O — the data was already there), and `Model.ab_cost()` checks the
    RAW per-occurrence text against it, overriding to `CX Combo`. Scoped to the per-occurrence family label
    only, not the pooled per-signature standard cost (two cards sharing a signature could differ on whether
    their discarded card happens to be a climax).
  - **`Cannot Attack` deleted outright** (not just narrowed, as done earlier this session) — every real
    "make the opponent's character unable to attack" case in the corpus is delivered via a Grant (already
    correctly resolving to `Grant Ability`, confirmed via `ALL/S90-072`), so there was nothing left for the
    name to catch.
  - **The `AddMarker (...)` group renamed and split by source ZONE**, per the user's explicit convention
    ("AddMarker (ZONE)") — found via `ALL/S90-072`'s marker sourcing from the DECK TOP, not the waiting room
    the old flat name assumed. Split into `AddMarker (Deck Top)`, `AddMarker (Deck Search)` (a real search,
    not a blind top peek), `AddMarker (Waiting Room)` (the dominant remaining source), and
    `AddMarker (Self)` (this card + its own markers transfer onto a newly-played ally — the official 継承
    keyword, added to the `KW` dict).
  - Explained% 95.3% → **95.5%**, suspects 3578 → **3520** (both real gains). `pipeline/analysis/
    family_catalog.txt`: 115 families.
- ✅ **Family-taxonomy audit, round 7 — 9 more `Other` clusters resolved (2026-07-22, same session).**
  Reviewed the remaining `Other` dump in 5 major + 4 minor batches; the user confirmed or corrected each:
  - **`Side Attack (No Soul Loss)`** (new): the "サイドアタックしてもソウルが減少しない" mechanic. Initially
    mischaracterized as defensive; the user corrected it — this is an OFFENSIVE damage-reliability tool
    (lets a side-attack deal its full damage instead of being reduced/negated by the usual -1-per-level-gap
    soul-loss rule), used to guarantee damage through an otherwise-unfavorable side attack.
  - **`Clock/WR Exchange`** and **`Level/WR Exchange`** 2nd branches widened (self-referential "this card
    sits at the top of the clock / in the level zone" shapes, confirmed real though rare).
  - **`Clock/Stage Exchange`** (new, split off from `Clock/WR Exchange`): `DC4/W81-073`'s "アラーム この
    カードがクロックの1番上にあり…あなたは自分のキャラを1枚とこのカードを選び、入れ替えてよい" has NO waiting-room
    qualifier at all (unlike `ISC/S81-P02`'s explicit "自分の控え室のキャラ") — meaning the trade partner is an
    in-play STAGE character, not a discarded one. Per the user's "split by variant, don't lump" rule
    (established for Bomb/Reverse Immunity), this is its own family rather than a relaxed WR regex.
  - **`Grant Trigger Icon (Class)`** (new): grants a trigger-icon bonus to an entire CLASS of climax cards
    (any CX whose printed trigger icon is X), not a single named target — distinct from the existing
    named-target `Grant Trait`/icon-grant patterns.
  - **`Trigger Icon Reuse`** (new): "あなたは◯◯の効果で……選んでよい" — lets you additionally apply a trigger-icon
    effect you already resolved this turn, confirmed real (e.g. take an extra card off a Soul trigger).
  - **`Marker Cleanup`** (new): "このカードの下のマーカーをすべて控え室に置く" — bulk-discards all markers parked
    under this card, the disposal half of the marker-banking mechanic (`AddMarker (...)` is the deposit half).
  - **`Reverse Immunity (Paid)`** (new): "あなたはコストを払ってよい。そうしたら、そのターン中、このカードは【リバース】
    しない" — a THIRD Reverse Immunity variant (after `(Cost 0)` and `(Hand4/Solo)`), gated behind a generic
    paid cost rather than a fixed condition. Confirmed real per the user (exists alongside the other two).
  - **`Burn`** widened to also catch symmetric "all players take N damage" text (previously only matched
    opponent-only damage) — confirmed still a `Burn` per the user ("burning everyone is still a burn").
  - **`Clock Reorder`** (new): "自分のクロックすべてを好きな順番で並べ直す" — sibling of the existing deck-side
    Look & Reorder, same reordering mechanic applied to your own clock instead of your deck.
  - **`Opp Disrupt`** widened with a 3rd branch: wiping the opponent's entire marker area
    ("相手の枠を…選び…マーカー置場のマーカー…控え室に置") is a disruption tool against the opponent's board state,
    same family as the existing hand/stock/deck/etc. disruption branches.
  - Explained% flat at **95.5%**, suspects **3521** (up 1 from 3520 — effectively unchanged, within noise
    for a re-classification pass). `pipeline/analysis/family_catalog.txt`: **122 families** (was 115).
    `Other` down to **178 signatures / 399 occurrences** (from several hundred more at the batch's start).
- ✅ **Bug-fix pass (2026-07-22, same session) — no family-naming call needed.** `ra()`'s dash-placeholder
  filter was missing two Unicode dash variants (HYPHEN U+2010 `‐`, HORIZONTAL BAR U+2015 `―`) used by 18 real
  "no ability" rows — they were being costed/labeled as real abilities instead of dropped. Fixed in
  `cost_model.py` (canonical) + mirrored in `_tr2_extract.py`/`cost_standardize.py` (other active tools with
  their own copy; left the 2 known-superseded legacy tools alone). Also: `Removal (Deck Top)` /
  `Removal (Memory)` / `Removal (Stock)` were each missing the same battle-opponent-reference branch
  (`このカードとバトル(中の|している)キャラ`) their sibling `Removal (Deck Bottom)` already had — real cards fell
  through to `Grant Ability`, the generic `Stock Boost` catch-all, or `Other`. Fixed all three, verified
  against `DC/W01-059`, `KF/S05-032`, `LB/W06-T06`, `LB/W06-018`, `FH/SE03-001`. Explained% flat 95.5%,
  suspects 3521→3522 (noise).
- ✅ **Family-taxonomy audit, round 8 — 8 more `Other` clusters resolved, several user corrections
  (2026-07-22, same session).**
  - **`Grant Trait` widened** to accept a fixed/described target (face-off opponent, or "all of X"
    characters incl. name-matched groups) instead of requiring "choose 1" — same final purpose, user
    confirmed fold rather than split.
  - **`Deck Mill`** (new): blindly mill the top N/up-to-N/X of your own deck to the waiting room, no
    look/choose verb. **Deliberately kept separate from `Brainstorm`/集中** — the user was emphatic this is a
    RULES-LEVEL distinction, not just a different trigger: Brainstorm's official keyword reveals cards into
    an intermediate resolution zone before discarding, while a plain mill goes straight to the waiting room.
    Never fold simple milling into Brainstorm going forward.
  - **`MemorySelf`** (new, renamed from an initial "Compress" proposal): a plain ACT ability that sends THIS
    CARD itself into Memory. NOT a Retreat (user: fires in the main phase, unrelated to attacking/battle, not
    a combat escape). NOT the more generic "Compress" either — user: Memory-banking is only ONE of several
    ways to achieve a similar board-tidying effect (lots of clean stock is another), so name the specific
    mechanic, not the abstract goal.
  - **`Drawback` widened** for "this card's power does not increase or decrease" — looks protective at first
    glance, but user's ruling is Drawback: locking your own power also blocks every beneficial modifier
    (Backup/Assist/Power Pump from teammates), a net negative in practice.
  - **`Memory/WR Exchange`** (new): 3rd sibling of `Clock/WR Exchange` / `Level/WR Exchange`, zone pair is
    Memory ↔ waiting room.
  - **`Link Identity`** (new): the official 【リンク】 marker's whole "ability" is just its own bare name (e.g.
    "ASMR", "Groovy Mix") — a searchable identity tag, zero game action. Verified: every real 【リンク】-marked
    row in the corpus has no Japanese punctuation at all, so detection can't misfire on a real ability.
  - **`Declare`** (new): the pre-existing quote-declaration no-op ("…と宣言してよい"/"…と言ってよい", already costed 0
    via `is_noop()`) finally gets its own family name instead of falling to `Other`.
  - Explained% flat **95.5%**, suspects **3522 → 3517** (a small real gain). `pipeline/analysis/
    family_catalog.txt`: **126 families** (was 122). `Other` down to **151 signatures / 296 occurrences**.
- ✅ **Bug-fix pass (2026-07-22/23, same session) — markerless `※` print/legality notices.** 94 real
  markerless rows in the corpus start with `※` — all print/legal metadata (tournament-ban notices,
  domestic/overseas distribution notices, same-name-card notices, date-gated bans, foil-type notices), none
  gameplay text. Added to `ra()`'s drop-list, mirrored in `_tr2_extract.py`/`cost_standardize.py`. Side
  effect: 16 fewer spurious "distinct" cards after alt-art dedup (the dedup signature is built from `ra()`'s
  output, so two prints that only differed by a superficial print notice now correctly merge). Explained%
  flat 95.5%, suspects 3517→3516.
- ✅ **Family-taxonomy audit, round 9 — 4 more clusters resolved (2026-07-23, same session).**
  - **`Hand/Level Exchange`** (new): 4th sibling of `Clock/WR Exchange` / `Level/WR Exchange` /
    `Memory/WR Exchange`, zone pair Hand ↔ Level. **Terminology note from the user:** a stage card leaving
    play as an ability's own cost is "put into your waiting room," never "discard" (discard = from hand
    only) — apply this in all future EN citations.
  - **`Damage Reflect`** (new): "when the damage you received is not canceled, deal the SAME damage to your
    opponent." Kept separate from `Burn` — variable amount (mirrors incoming damage, not a printed number)
    and a reactive trigger completely unlike Burn's on-play/on-attack clauses.
  - **`Strip Trait` gap widened** (20→40 chars) for a marker-wipe clause inserted mid-sentence
    (`JJ/SE42-01`) — stays plain `Strip Trait`, the wipe is a minor secondary detail on a small cluster.
  - **`Strip Trait (All)`** (new): wider-scope sibling — a chosen trait is stripped from ALL of the
    opponent's characters, not just one. Board-wide vs single-target, genuinely broader scope.
  - **`AutoKickToDeckShuffle`** (new, in `ONREV_PAT`): self-to-deck-and-shuffle on reverse, sibling of
    `AutoKickToBottom` but a different resource value (random redraw position vs a guaranteed one).
  - Explained% flat **95.5%**, suspects **3516** (flat). `pipeline/analysis/family_catalog.txt`:
    **130 families** (was 126). `Other` down to **135 signatures / 238 occurrences**.
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
