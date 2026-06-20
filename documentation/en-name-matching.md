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
| `EN_BLOCK_CARD = {BD/W63-102, -103, -104}` | specific permuted BanG Dream! cards |
| `EN_BLOCK_ENSET = {(BD, W03)}` | safeguard: EN-only special booster (no JP counterpart) |

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
