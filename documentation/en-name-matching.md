# English name/text matching & legacy disparity exclusions

How the build assigns **official English** data to each Japanese card, and why a curated set of
legacy sets is deliberately excluded from that matching.

## How EN data is attached (`pipeline/build_db.py`)

Two independent mechanisms, by design:

- **Abilities → matched by TEXT.** Each JP ability text is looked up in the translation cache
  (`translation_cache.json` + `variant_tr_full.json` + `abilities_official_en.json`). This is
  **robust to set renumbering** — it does not care whether a set's JP and EN codes line up.
- **Names / traits / positional EN → matched by CARD NUMBER** via `strict_key`
  (publisher + set + normalized number). `name_en` comes from the EXACT same-code EN card, or, if
  none, propagates from another card sharing the same full JP name (`NAME_OFFICIAL`).

This asymmetry is why a legacy card can show translated abilities but a blank/garbled name: the
text match still works while the number match breaks.

## Translation cascade (priority order)

`build_db.py` fills each field from the best available source, top to bottom:

1. **Official EN** — exact same-code EN card (`cardlist_en.json`), or same-JP-name propagation
   (`NAME_OFFICIAL`). Best phrasing; only ~18.7k of 40.4k cards (the rest never released in English).
2. **Unofficial simulator** — `name_sim.json` / `traits_sim.json` / `abilities_sim.json`, built by
   `pipeline/extract_simulator.py` from a fan-made WS game's `CardData.txt` files (its identity is
   deliberately not named in public docs — see `NOTICE.md`). English in roughly the official
   taxonomy, keyed by `strict_key`. Abilities/traits are taken **positionally only when the count
   matches** the JP ability count (the simulator sometimes splits abilities differently); names need
   no alignment. **Site-wide ability EN coverage: 99.87%** (as of 2026-07-22) — see below for how.
   - **Macro synthesis (2026-07-22).** Many abilities are written in `CardData.txt` as a single
     scripted macro line (e.g. `*GainPowerWithEnoughCharacters(5000,2,Granblue)`) instead of a `Text`
     line — the simulator's engine only needs the macro to run the effect, not a prose description.
     `extract_simulator.py` now synthesizes real English for these: it looks up the macro name
     against two sources, in priority order — (a) the simulator's OWN engine definitions,
     `StreamingAssets/CommonEffects(copy).txt`, read live from the local install at runtime and
     **never copied into the repo** (it's the simulator's internal source, more sensitive to
     redistribute than the hand-curated fallback below); (b) `pipeline/sources/macros.tsv` (236
     curated macro → English-template mappings, tracked in the repo) as a fallback where the engine
     source has no `Text` line for a macro. Each macro's own call arguments are substituted into the
     matched template's placeholders (`POWER`, `NUMBER`, `TRAITLIST`, ...).
   - **Ability counting is depth-aware.** Only a TOP-LEVEL line (brace depth 0 in `CardData.txt`) is
     its own ability — a macro or `Text` line nested inside another ability's block (a conditional,
     a cost block, or a `GainEffect { ... }` temporary grant) describes a clause that
     `cardlist_clean.json` already embeds inside the OUTER ability's single JP text, and must not be
     counted as a second ability, or the simulator's count stops matching the JP count and the
     WHOLE card's simulator text gets rejected by the alignment check above (not just the nested bit).
   - **The printed "Backup" keyword ability is a known, permanent gap in the simulator's own data**
     (marker `【起】`+`【カウンター】`, text `助太刀N レベルM...`) — the simulator stores it as a bare
     numeric stat field, never as ability text, which used to make every Backup-having card's
     simulator count come up 1 short (2,821 cards). `build_db.py` now excludes this specific ability
     from the count comparison and maps simulator indices around its slot, so the card's OTHER
     abilities aren't penalized for a gap that isn't fixable on the extraction side.
3. **Heart of the Cards** — `name_hotc.json`, scraped by `pipeline/fetch_hotc.py`, keyed by the
   Japanese NAME (so it applies even to blocked franchises). HotC translates the ORIGINAL JP cards,
   so it is JP-ALIGNED and CORRECT even for renumbered legacy (e.g. it gives DG/S02-T05 the right
   "Universe Police Justice Flonne" where official EN/sim grafted the wrong "Laharl & Flonne").
   Non-official phrasing, so it is the LAST name fallback → names reach ~95.2%. Names only (set pages
   carry no effect text). HotC rate-limits scraping, so the scraper paces slowly + retries on stubs.
4. **Blank** — better than wrong.

⚠️ The simulator SHARES the official list's legacy disparity errors (same permuted BD/W63; Disgaea
only under the renumber `DG/ENS03`), so **every simulator read is gated by `en_card_blocked()`** —
blocked franchises (below) never pull from it. The extractor also keeps only entries whose
`strict_key` maps to a real JP card ("set parity"), dropping the simulator's `EN`/`SX`/`WX`-prefixed
renumber sets automatically.

## The legacy disparity problem

For several **old franchises**, Bushiroad **renumbered or consolidated** the Japanese sets for their
English release, so `strict_key` links the WRONG English card (wrong name + wrong positional EN).
Examples found by manual review against the live site:

- **Disgaea (DG):** EN `DG/S03` merges JP `DG/S02` + `SE08` + `SE17`; the JP `T##` / EN `TE##` trial
  numbering also diverges, so e.g. JP `DG/S02-T05` (Space Detective Justice Flonne, L1, 2 effects)
  was mislabeled with the EN vanilla `TE05` "Laharl & Flonne".
- **BanG Dream! (BD):** `BD/W63-102/103/104` are permuted (Ran↔Aya↔Kasumi); `BD/W03` is an EN-only
  special booster of the band trial decks that never released in JP under that code.
- **Fairy Tail (FT):** only `FT/S120` lines up with JP; `FT/S02` (EN renumber), `S09`, `SE10` do not.
- **Love Live! (LL), Persona 4 (P4), Prisma Illya (PI):** EN releases are renumbered/merged mutations
  of the JP sets (PI fused two extra boosters into one EN set).

Automated detection of the *wrong* matches is unreliable: stats-mismatch and ability-count-mismatch
both produce mostly FALSE positives, because the official EN source differs systematically from JP
even on correct cards (off-by-one levels, abilities split differently, soul variance). The only
ground truth is character identity. So exclusions are a **curated manual list**, not a heuristic.

## The curated exclusions (in `build_db.py`)

`en_card_blocked(cn)` / `en_match(cn)` refuse EN data for:

| Rule | Scope |
|---|---|
| `EN_BLOCK_PUB = {DG, P4, PI, LL}` | whole franchise — EN release is a mutated renumber of JP |
| `FT_ALLOW_SET = {S120}` | Fairy Tail: keep only `S120`, block `S02/S09/SE10` |
| `EN_BLOCK_CARD = {BD/W63-102/-103/-104, NK/W30-002/-026/-052/-076}` | specific permuted cards + Nisekoi regional variants |
| `EN_BLOCK_ENSET = {(BD, W03)}` | safeguard: EN-only special booster (no JP counterpart) |
| `NAME_OVERRIDE = {NK/W30-002: "Maiden's Heart, Chitoge", ...}` | manual JP names for the regional variants |

**Regional variants (NK/W30):** 4 Nisekoi cards share a JP/EN code but have a DIFFERENT effect by
language. The JP card (乙女心 "Maiden's Heart") is blocked from its same-code EN match (which is a
different card), gets its name from `NAME_OVERRIDE`, and its `en_text` is blanked (the text cache
would otherwise return the EN variant's wrong effect). The ENGLISH printing ("The One", different
effect) is added as its OWN `en_exclusive` row under code `NK/W30-E0xx`, grouped under Nisekoi — so
all 8 cards exist. See the `NK_VARIANTS` block in build_db.py.

Effect: a blocked card keeps its (correct) **JP** stats/abilities and its **text-matched EN ability
translations**; only the unreliable **EN name** is withheld (left blank — "better blank than wrong").
Measured impact at introduction: removed 320 wrong/untrusted `name_en` (17,101 → 16,781), kept all
correct ones (FT/S120, AOT, CCS, 5toubun, etc. unaffected). JP stats are never affected — the EN
official list itself has mis-tagged levels/soul, but the DB stores JP (the source of truth).

> Not EN-exclusive sets: AOT `SX04` and CCS `WX01` (the `WX`/`SX` prefix) are EN-native cards with
> no JP counterpart — they are handled by the `en_exclusive` path, not by this matching, and are
> intentionally left as-is.

## Extending

When a new disparate legacy set is found (browse the live site, spot a wrong English name on a JP
card), add it to the appropriate set in `build_db.py` and re-run `python pipeline/build_db.py`.
