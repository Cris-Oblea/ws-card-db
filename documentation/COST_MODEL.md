# COST_MODEL.md — how ws-card-db prices an ability, end to end

> **Canonical explanation of the power-cost model.** This is the source-of-truth narrative for the math in
> `pipeline/cost_model.py` (the single implementation) and its read-only analysis companion
> `pipeline/cost_standardize.py`. It is written so that someone with general Python knowledge but no prior
> exposure to this codebase — and no AI assistant — can understand *why every stage exists* and *how the
> numbers are produced*. When the model changes, update this file. Shorter pointers live in
> `documentation/OVERVIEW.md`; the stack/convention source of truth is the top-level `CLAUDE.md`.

---

## 0. What "cost" means

Every card has a printed **power**. A card with abilities is printed with **less** power than a plain
(vanilla, ability-less) card of the same Level/Cost/Soul would have — the designer "pays" for the abilities
by subtracting power. We call that subtracted amount the **cost**:

```
power_real = power_base − cost          (so:  cost = power_base − power_real)
```

- **`power_real`** = the power actually printed on the card.
- **`power_base`** = what an ability-less card with the same stats *would* have (computed, see §1).
- **`cost`** = the power the abilities "spent". Always a **multiple of 500** (the game's power economy).

The whole project exists to measure that cost for the ~15,346 distinct abilities that appear in the game, so
a custom-card designer can look up *"I want this effect → it costs X power"*.

Two facts drive the entire design:

1. **You can only *measure* a cost cleanly on a card with exactly ONE ability** — there the whole delta
   `power_base − power_real` belongs to that single ability. Multi-ability cards mix several unknowns.
2. **Regression does not work here** (linear, log-linear, symbolic, random-forest were all tried and
   discarded — see `pipeline/Conclusions.md` §3). A cost modifier is *effect-dependent*: paying an
   activation cost *lowers* a burn but merely *pays for* a heal, so no universal coefficient exists. The
   model therefore **measures, then propagates, then estimates** — it does not fit a formula.

---

## 1. Base-power fit — `pb(c)`

`power_base` is a reverse-engineered linear fit of the vanilla curve:

```
power_base = 3000 + 2500·Level + 1500·Cost − 1000·[has Soul trigger] − 1000·(Soul − 1)
```

(`[has Soul trigger]` is 1 if the card's trigger list contains `soul`, else 0.) This is exact — it
reproduces the printed power to a delta of **0 on every L0–L2 vanilla in the data**. No L3 vanilla is ever
printed, but the extrapolation is sound and is deliberately **not** trimmed: apparently over-high L3 deltas
come from *unreliable* cards (demo/trial/promo prints that are intentionally under-statted), not from a bias
in the formula. See the comment on `pb()` in `cost_model.py`.

**Reliability filter — `reliable(c)`.** Only genuine prints may *seed* a measured standard. Cards whose
number ends in an `A#` suffix (learn-to-play / demo decks, e.g. `LSS/WE27-A16`) use intentionally
under-curve stats, so their delta is excluded from measurement — they are still costed and shown, just never
measured *from*. Everything else (P promos, and every alt-art parallel — SR/RRR/SP/… are the same card with
different art and identical stats) is trusted.

---

## 2. The package = the signature

A **package** is the unit the model prices. It is the full **signature** of an ability:

```
signature = ''.join(markers) + ' :: ' + gen(text)
```

- **markers** = the bracketed ability markers (`【自】`AUTO / `【永】`CONT / `【起】`ACT / `【CXコンボ】` / …).
- **`gen(text)`** = the ability text *normalized* so that trivial wording differences collapse to one
  signature:
  - full-width digits → ASCII;
  - every `《trait》` → the placeholder `《T》` (trait **count** does not affect cost — any trait restriction
    is one category — so a list like `《武器》か《メカ》` collapses to a single `《T》`; only a genuinely
    *trait-less* effect stays distinct and pricier);
  - every `「name」` → `「N」` (the specific character name never changes the cost);
  - runs of whitespace collapsed.

Crucially, the **activation-cost bracket `［…］` and the markers are PART of the signature** — payment is part
of the package. Two searches that do the same thing but pay differently are *different* packages, because
what you pay changes the net cost. (This is why the standardizer can later isolate what each payment
"buys down", §11.)

---

## 3. The MODE-based standard

For each package, its **standard cost** is the **MODE** (most frequent value, rounded to 500) of the
per-card actual costs measured on the isolated single-ability cards that share that signature — **pooled
across ALL years, with no era split** (see §10 for why era is not a factor). The mode, not the mean, because
costs are quantized to 500 and the designer's intended value is the one that recurs; a few off-curve cards
should not drag the standard.

Each standard is stored with its **evidence**, produced by `mode500_share()`:

- **`n_samples`** — how many pooled measured samples stand behind it.
- **`mode_share`** — the % of those samples that round to the modal value. High mode-share = a tight,
  reliable standard; low mode-share = a loose signature pooling genuinely different cards.

The per-card **residual** is then `real_delta − Σ(standard costs of the card's abilities)` — the part the
package standards do *not* explain, i.e. the designer's per-card adjustment. A card with `|residual| ≥ 500`
is flagged a **suspect** (§12).

---

## 4. The cascade: measured → residual → estimated

`build_cost_model(clean)` runs one pass that fills in a cost for *every* signature, in strict priority order.
Earlier (more trustworthy) stages win; later stages only fill what's still unknown.

**Pass 1 — replay folding** (`_fold_replays`, done first; see §8).

**STEP 0 — replay bodies → 0.** A `【リプレイ】` row is not a standalone effect; its body was folded into its
citer, so it is fixed at cost 0 (`method="replay-body"`, structural, HIGH confidence).

**STEP 0b — no-op declarations → 0.** An ability whose whole effect is "declare 『X』" with no game action is
a structural 0 (`method="noop"`, HIGH). See §9.

**STEP 1 — measured.** For each package seen on **isolated single-ability reliable cards**, the cost = the
MODE of those cards' deltas (§3). A signature with only **one** sample is *skipped here* (a lone sample is
unstable and must not lock in as HIGH-confidence measured) — it falls through to residual or estimation
instead. This is the only behavioural change made when the two old duplicated builders were merged into this
module.

**STEP 2 — residual (non-absorber).** The propagation step. On a multi-ability card the per-card delta =
the sum of all its ability costs. So if a card has exactly **one** ability whose cost is still unknown, that
unknown *must* equal `delta − Σ(known costs)`. Those inferred values are **pooled across every card where the
same signature is the lone unknown**, and the MODE becomes its cost (`method="residual"`, MEDIUM). This is a
**fixpoint iteration**: resolving one signature can turn a 2-unknown card into a 1-unknown card, so the whole
sweep repeats until a pass resolves nothing new (capped at 10 iterations for guaranteed termination). A
*negative* residual on a family never seen negative in measured data is rejected (a beneficial ability can't
be a drawback — the seeds over-counted), leaving it for estimation. **Absorber** signatures (CX-Combo and
replay-citer, §8) are *deferred* out of this step.

**STEP 3a — family-median estimate (non-absorber).** Every still-unknown non-absorber signature is given its
**family's median** of already-priced costs (`method="estimated"`, LOW). Structural zeros are excluded from
the medians so they don't bias them; a family with no data at all defaults to 500. This guarantees that the
only unknown left on an absorber card is its absorber signature.

**STEP 3b — absorber residual.** Now that every non-absorber signature has a value, each CX-Combo / citer
signature is derived by the same subtraction (`delta − Σ others`) on cards where it is the lone remaining
unknown. Both are floored at ≥ 0 (`CXC_FLOOR = 0`): a CX-Combo *is* the card's leftover residual, whatever
that value is — it gets **no arbitrary 500 minimum** — but a beneficial combo cannot cost negative (a
negative only ever came from single-card over-stat noise, and CX-Combo is not a measured-negative drawback
family). A citer is floored at ≥ 0 for the same non-negativity reason (a folded replay body never *gives*
power back).

**STEP 3b2 — estimated upgrade.** A non-absorber signature that only ever co-occurred with a
then-unresolved absorber was "trapped" at STEP 2 and fell to a family-median guess in 3a. Now that absorbers
are solved, it may be the lone unknown on its card and can be solved from that card's own delta — but only
when every *other* signature on the card is already trusted (not itself a 3a guess). Iterated, same guards as
STEP 2.

**STEP 3c — estimate the leftovers.** Any signature still unpriced gets its family median (CX-Combo gets the
CX-Combo median, floored at ≥ 0).

**STEP 3d — partial cabling for self-pumps.** The one place the flat family median is replaced by a smarter
guess. For an *estimated* `Power Pump (self)` signature, the cost is `base N × (½)^(temporal + #conditions)`,
floored at 500 (`pump_self_estimate`). Because a self-pump's base value is literally the printed `+N`, this
beats the flat median (a flat median gives a `+500` and a `+8000` pump the same cost). Measured/residual
self-pumps are untouched; it stays LOW confidence — an N-scaled guess, not a measurement. This is the only
wired piece of the multiplicative draft (§13).

Finally, the **CX-Combo floor** (≥ 0) is enforced on every CX-Combo signature — clamping only a genuinely
negative combo up to 0; positive values pass through unchanged (no ceiling, no 500 minimum).

---

## 5. Confidence taxonomy

Confidence describes **the standard's evidence, not merely the method** (`conf_evidence()`). Exact rules:

| Confidence | When |
|---|---|
| **HIGH** | `method = measured` **AND** `n_samples ≥ 3` **AND** `mode_share ≥ 60`. Also: `replay-body` and `noop` (structural zeros are always certain). |
| **MEDIUM** | `method = residual`; **or** `measured` with weaker evidence (n < 3 or mode_share < 60). |
| **LOW** | `method = estimated` (a family median / cabled guess — no reliable mode behind it). |

The thresholds are constants at the top of the module: `CONF_MIN_N = 3`, `CONF_MIN_SHARE = 60`. The Excel
builder can still ask for a method-only label via the plain `CONF` dict; the DB uses the evidence-aware
`conf_evidence`.

---

## 6. Family / type taxonomy

Every ability is classified two ways.

**Ability type** (`ability_type`, from the markers): `CONT` (`永`) · `AUTO` (`自`) · `ACT` (`起`) · else
`OTHER`.

**Family** (`family`) — *what the ability does*. It is decided by an **ordered** match; the first rule that
fires wins, and the order matters (more specific / higher-priority patterns are checked before grab-bag
ones). The order is:

1. **CX Combo** — the `【CXコンボ】` marker, or the climax-area text gate `CXC_PAT` (§7). A combo encapsulates
   whatever sub-effects it mixes, so it is decided first.
2. **Modal** — "choose 1 of the next N effects" (`MODAL_PAT`). The chosen sub-effect must not decide the
   family, or a "look-3 OR heal-1" would pollute Heal.
3. **Grant Ability / Pump & Grant** — the ability grants/gains an auto/cont/act ability (`GRANT_PAT`).
   *Pump & Grant* is the dual case where a pump lives in the citing text *outside* the granted `『…』` quote.
4. **On-reverse families** — when THIS card is reversed: `AutoKickToBottom`, `AutoKickToMemory`,
   `AutoKickToClock` (this card relocates ITSELF — no opponent involved), plus the **dynamically-computed
   Bomb family** (`_dynamic_bomb_name`, 2026-07-22 audit) — "punish the opponent after THIS card wins its
   own battle." Every combination of **level/cost threshold × color/destination** gets its own distinct
   name, computed rather than listed as ~20 near-duplicate static strings: `RedBombLevel0`,
   `RedBombLevel1`, `RedBombLevel2`, … `RedBombLevelX` (variable), `AntiEarlyRedBomb` (opponent's level >
   the controlling player's own game-level — a rush-punish) for **red** (re-reverse the opponent); the same
   Level/Cost/X/AntiEarly suffixes under `BlueBomb*` (opponent → bottom of their own deck) and
   `YellowBomb*` (opponent → their own stock, usually paired with a bonus "-1 opponent stock" clause) —
   **green** (heal + clock, per the user) has not yet been found in this exact self-reverse-trigger shape
   in the corpus, so it's not implemented. **Retroactively split (2026-07-22) from a prior-session design**
   that lumped re-reverse/clock/stock all under one "Red" name — the user clarified each color has a
   genuinely different cost, not just a different flavor.
5. **Keyword mechanics (`KW`)** — the keyword *names* the effect: `Backup`(助太刀) · `Assist`(応援) ·
   `Brainstorm`(集中) · `Encore`(アンコール) · `Bond`(絆) · `Change`(チェンジ) · `Accelerate`(加速) ·
   `Shift`(シフト) · `Great Performance`(大活躍) · `Force`(フォース) · `Heal`(ヒール) ·
   `Removal (Hand)`(バウンス — the official keyword name for the same effect as the FAMPAT text-pattern below) ·
   `AddMarker (Self)`(継承 — this card + its own markers transfer onto a newly-played ally).
   *Condition* keywords (記憶 Memory, 経験 Experience, 共鳴 Resonance) are **deliberately excluded** — they
   only *gate* a separate effect, so the ability must file by what it actually does. A **general guard**
   skips the KW shortcut whenever the matched keyword is cited as `『keyword』を持つ` ("[a card] that HAS
   this keyword") — that phrasing always means the keyword is a SEARCH/SELECTION CRITERION for some OTHER
   card (e.g. "look at your deck, choose a card that has 『Change』, add it to hand" is a Search, not a
   Change ability), never the keyword's own performance. Found via a 291-card audit of the `Change` family.
6. **`FAMPAT` effect-text patterns** — ~75 entries, full current order always in `pipeline/cost_model.py`
   (the list below is illustrative, not exhaustive — see `pipeline/analysis/family_catalog.txt`, gitignored,
   for the live per-family sig/occurrence counts): `Burn`, `Heal`, `Clock Kick`, `Removal (Hand)`,
   `Return to Deck`, `Retreat`, `AllMemoryCleanse`, `Removal (Waiting Room)`, `Removal (Stock)`,
   `Removal (Deck Bottom)`, `Removal (Deck Top)`, `Removal (Memory)`, `Removal (Swap)`, `ReviveOpponent`,
   `Reverse Opp`, `Opp Disrupt`, `RevealTopSalvage`, `Salvage`, `Stock Search`, `CX Exchange`,
   `Memory Bank`, `Search`, `Deck Thin`, `Look & Reorder`, `Look Deck`, `Summon`, `Change`,
   `Clock/WR Exchange`, `Clock/Hand Exchange`, `Return to Deck (Own)`, `Stock Gen`,
   `AddMarker (Deck Top)`, `AddMarker (Deck Search)`, `AddMarker (Waiting Room)`,
   `Retreat` (reactive), `Add to Hand`, `Power Pump (board)`, `Power Pump (self)`, `Power Pump`,
   `DiscardCharacterToDraw`, `DrawDiscard`, `Draw`, `Early Play`, `Grant Trait`, `Power Debuff`, `Soul`,
   `Level`, `Mill (self)`, `Retreat` (this card), `Attack Redirect`, `Move (Opponent)`, `Move (Own)`,
   `Stand/Rest`, `Stock Boost`, `Choice`, `Early Play` (level-gate), `Free Play (Alt Cost)`,
   `Restriction`, `Self Sacrifice`, `Drawback`. `Cannot Attack` was deleted (see below).
7. **`Other`** — nothing matched. As of the 2026-07-22 family-taxonomy audit, this is the ONLY generic
   fallback — the old `Card Select` catch-all (`\d+枚選`) was deliberately deleted (see below), so `Other`
   now also catches the tiny remainder of genuinely bespoke, one-off card designs that don't represent a
   real recurring family.

**How a FAMPAT is matched.** Each entry is `(family_name, regex)`; `family()` runs `re.search(regex, text)`
on the `gen()`-normalized text and returns the first family whose regex hits. The regexes are tuned so
narrow, specific mechanics peel off *before* broad grab-bags (`Add to Hand`, `Card Select`, `Move (Own)`)
that would otherwise swallow them — e.g. `Retreat` (return your **own** stage character to hand) is checked
before `Add to Hand`, and `Removal (Hand)` (return the **opponent's** character) before both. The `KW`/FAMPAT
distance bounds (`[^。]{0,N}`) keep matches inside one clause so a payment bracket or a later sentence can't
false-match. (Every non-obvious regex carries an inline rationale in `cost_model.py` — read those before
editing one; a "simplification" usually re-opens a mislabel bug that a distance bound was closing.)

**`Summon` (formerly `Comeback`), `Change`, and the "recruit onto the stage" families.** Renamed because
the old name `Comeback` collided with the OFFICIAL CLIMAX TRIGGER ICON of the same name — a distinct game
concept. `Summon`'s final purpose: put YOUR OWN character directly onto the STAGE from waiting room / deck /
hand / Memory / clock, bypassing the normal play sequence (no cost paid, no level check) — distinct from
Salvage/Search (destination is hand; the card still has to be played normally afterward). `Change` (text-form)
catches the SAME mechanic as the official チェンジ keyword — this card retreats AS the cost, and a replacement
fills the exact vacated slot (`このカードがいた枠に置く`) — spelled out in full text instead of the keyword
shorthand; both detection paths resolve to one family/cost standard. `Clock/WR Exchange` swaps the card at
the bottom of your own clock for a waiting-room character (the clock's size never changes, only its
content) — useful for fixing a board's color requirements or freeing a character the clock was trapping.
`Return to Deck (Own)` is the self-side mirror of the (opponent-targeting) `Return to Deck` family.

**`Move (Own)` / `Move (Opponent)`.** Repositioning a character ALREADY on the stage into a different open
slot — entering play for the first time is `Summon`, not Move. Split by whose character moves: your OWN
character (a defensive/tactical trick) and the OPPONENT's (a disruption/combat trick) are the SAME action
but a different final purpose depending on whose board it targets. The negative form `動かせない` ("cannot be
moved") is excluded from both — that's a lock/restriction, not an actual move, and instead files under
`Restriction`.

**Other Card-Select-audit families:** `Memory Bank` (bank a named own waiting-room/clock card into Memory,
usually gated by a low own-Memory-count condition — often paired with a later Summon/Salvage that pulls it
back out), `Deck Thin` (search your own deck for a specific/trait card and send it to the WAITING ROOM
instead of hand — a targeted mill, not a Search), `Stock Search` (look at your own STOCK and take a card to
hand — a resource pile not normally searchable), `Free Play (Alt Cost)` (discard a named own card to play
THIS card for 0 cost — the game's exact templated phrasing, 30 cards share it verbatim), `Self Sacrifice`
(the card's own ability sacrifices ANOTHER of your own characters to the waiting room, not via a bracketed
payment — distinct from `Drawback`, where the OPPONENT acts against your zones instead), `Attack Redirect`
(choose a different opponent character to attack instead of the normal target/attacker), `CX Exchange`
(swap a climax card between two zones, matched by trigger icon — a combo-assembly tool, not a one-way
get), `Clock/Hand Exchange` (a clock character comes to hand, refilled from a hand or deck-top card — the
hand-side sibling of `Clock/WR Exchange`), `Removal (Stock)` (opponent's stage character sent to the
OPPONENT's OWN stock — a character card is always owned by its original controller, no zone ever mixes
cards from different owners, so an unmarked "put it in the stock" destination on an opponent's character can
only mean their own stock, not the actor's), `Grant Trait` (assign a chosen character a designated trait for
the turn — a stat-grant sibling of `Soul`/`Level`, just targeting the trait slot).

**`Card Select` was completely eliminated (2026-07-22), not just shrunk.** The generic `\d+枚選` catch-all
FAMPAT entry was deleted outright once every recurring pattern it swallowed had a real, purpose-named home
(1547 → 361 → 139 → 34 signatures across three audit passes, then 0). The last ~10 signatures before
deletion were genuinely bespoke one-off card designs (a unique named skill, a symmetric apocalyptic reset,
a bare targeting step with no destination of its own) that don't represent a real recurring family — those
now honestly fall to `Other` instead of the misleadingly-generic `Card Select`. **Do not re-add a generic
catch-all regex to FAMPAT** — if a new recurring pattern surfaces, give it a real purpose-based name instead.
Also fixed in the same pass: `Clock Kick` had been **completely dead (0 real matches) since before this
session** — its original `(クロック置場|クロックに)置` alternation never required the に between 置場 and 置, so
it could never match the real phrasing `クロック置場に置く`. A latent bug, not something this session
introduced; caught only because auditing Card Select's remainder required checking why those cards weren't
landing in Clock Kick already.

**Auditing `Other` (started 2026-07-22, in progress).** Once `Card Select` hit zero, the user asked to
continue the same treatment on `Other` — the function's honest fallback for "nothing matched," which had
quietly accumulated 3804 occurrences / 505 signatures (some genuinely bespoke, many just missing a real
family). First pass so far:
- **Retroactively split the Bomb taxonomy by color** (see "On-reverse families" above) — the user caught
  that the pre-existing RedBomb entries wrongly lumped 3 different destinations under one name.
- **New families:** `Multi Trigger Check` (check for a trigger N times during an attack — generalized to
  any N rather than hardcoding "Double"), `Deck Copy Limit` (a deckbuilding permission, not a gameplay
  ability — near-zero cost), `Color Bypass` (a passive CONT permission to ignore the color requirement when
  playing this card/your events/your climaxes — distinct from `Summon`, which is an ACTIVE effect putting a
  DIFFERENT character into play), `Hexproof` (the user's own term — "cannot be chosen by opponent's
  effects"), `Reverse Immunity (Cost 0)` (a DIFFERENT, more specific protection — common in Standby-format
  decks per the user — immune to becoming reversed when facing a cost-0 character), `Level/WR Exchange`
  (sibling of `Clock/WR Exchange`, swapping a level-zone card for a waiting-room card instead of a clock
  card), `Free Refresh` (the user's own term — return your ENTIRE waiting room to your deck at once, no
  selection, without the normal 1-damage refresh penalty), `Self Identity Grant` (this card gains a trait,
  an alternate name, or a trigger icon — three different "identity slots," same purpose: extend what THIS
  card counts as; distinct from `Grant Trait`, which targets an external chosen character).
- Same class of gap found repeatedly: real cards refer to "the character THIS card just fought" several
  different ways depending on which side of the battle triggered the ability — `そのバトル相手` /
  `このカードのバトル相手` (a noun, used directly), or `そのキャラ` (a bare pronoun whose antecedent was
  established earlier, in the TRIGGER clause itself, e.g. `このカードのバトル相手が【リバース】した時…そのキャラを
  …`) — widened `Clock Kick`, `Removal (Deck Bottom)`, `Removal (Stock)`, and `Removal (Memory)` to catch
  this pronoun-with-earlier-antecedent shape (crossing the clause gap with `.` instead of `[^。]`).
- `Other`: 3804 → 606 occurrences (505 → 237 signatures) across three follow-up rounds, all resolved:
  - **Memory folds into Red** (not a 5th color) — per the user, Memory is a newer-era variant of red, not
    a distinct color. Both re-reverse and Memory are "soft"/temporary removals.
  - **Green Bomb confirmed** via real cards (`AZL/S102-P02`/`T48`): heal the OPPONENT's clock (their top
    clock card → their own waiting room — the same `Heal` mechanic, applied to the opponent's clock) as an
    enabler, then bury the just-reversed opponent into that freed clock slot. The dynamic color×condition
    structure needed zero extra code to support Green automatically once its action pattern was added.
  - Same opponent-reference gap recurred (`_BOMB_OPP` fragment: "バトル相手の" vs "このカードとバトルしている/バトル
    中のキャラの"); `Removal (Deck Top)` widened for the そのキャラ+antecedent shape; `Self Identity Grant`
    widened (a hand-only condition, and a bare unconditional grant — including deriving a color from this
    card's own markers); `Grant Trait` widened to also cover granting a trigger icon.
  - New families: `Clock Gen` (sibling of `Stock Gen`), `Marker Currency` (a banked marker substitutes for
    a stock card when paying a cost), `Strip Trait` (negative-polarity mirror of `Grant Trait`),
    `HandSizeLimit+1` (a rules-modifying static), `Hand Discount` (a named external hand card's cost OR
    level −N — checked BEFORE `Early Play`, whose broader pattern was wrongly claiming the level variant).
  - **`Reverse Immunity` and `Drawback` both generalized** on the SAME principle the user re-confirmed
    from Bomb: same final purpose can still need distinct family names (`Reverse Immunity`) or a broadened
    single name (`Drawback`) depending on whether the VARIANT changes real cost. `Reverse Immunity` got a
    2nd explicit variant (`Reverse Immunity (Hand4/Solo)`). `Drawback` widened from "the opponent acts
    against you" to ANY self-inflicted no-upside risk (regardless of who/what triggers it) — validated via
    vanilla-power-delta math across 9 candidate cards spanning 9 different triggers: 8/9 price at/above
    vanilla (the Drawback signature — power given, not taken); the 9th (`DC/W09-008`) priced BELOW vanilla,
    correctly excluded as a real beneficial ability instead (folded into a widened `AutoKickToMemory`
    trigger: "leaving the stage," not just "on reverse").
  - Gates flat 95.3% throughout; suspects improved 3611→3578 (a real gain, not just noise) once Drawback's
    broadened definition correctly captured several previously-misclassified cards. 113 families total
    (was 74 when the `Other` audit started).
  - **`Cannot Attack` deleted outright.** Reviewing one card's full ability list (`PD/S29-105`) surfaced a
    bigger issue: the user clarified `Cannot Attack` should mean an effect YOU inflict ON THE OPPONENT so
    THEIR character can't attack — a disruption tool. Checking the actual corpus, 523 of 527 real
    occurrences of the old broad pattern were SELF-referential (`このカード` restricting its OWN attacking,
    unconditionally or gated on any game state), which is a `Drawback` by the same rule confirmed above, not
    a disruption of the opponent — moved there, positioned right before the generic `Restriction` catch-all
    (which would otherwise swallow "…できない" first). After narrowing to require an explicit opponent
    reference, `Cannot Attack` sat at 0 real matches; investigating why turned up the reason: every genuine
    "opponent's character can't attack" case in the corpus is delivered via a Grant (temporarily give that
    specific character the restriction, e.g. `ALL/S90-072`), which already resolves correctly to
    `Grant Ability` (grants are checked before FAMPAT, and the granted text never decides the family) — there
    was no standalone case left for the name to catch, so it was deleted, same "delete once confirmed
    genuinely empty" treatment as the old generic `Card Select` catch-all.
  - **A 4th CX Combo gate shape**: paying the cost by discarding a SPECIFIC NAMED CLIMAX from hand (found via
    `CHA/W40-077`, which was showing `Grant Ability` instead). Can't be detected on the already-generalized
    text the other 3 gate shapes use, since `gen()` collapses every name (character/event/climax) to the
    same placeholder — needs the raw name cross-referenced against the actual climax card list.
    `build_cost_model` populates a module-level `_CLIMAX_NAMES` set from its `clean` parameter (no new file
    I/O), and `Model.ab_cost()` checks the RAW per-occurrence text against it, overriding the family to
    `CX Combo` when it matches — scoped to the per-occurrence label only, not the pooled per-signature
    standard cost, since two cards sharing a signature could differ on whether their discarded card happens
    to be a climax.
  - **The `AddMarker (...)` group, renamed and split by source ZONE**, per the user's explicit naming
    convention — the generic family for any marker-placement effect is `AddMarker (ZONE)`, naming whichever
    zone the marker is actually sourced from, since markers can come from ANY zone, not just the waiting room
    the old flat name implied. Found via `ALL/S90-072`, whose marker was sourced from the DECK TOP, not the
    waiting room the old name assumed. Split into `AddMarker (Deck Top)` (a revealed/checked top-of-deck
    card), `AddMarker (Deck Search)` (a real search of the whole deck, not a blind top peek),
    `AddMarker (Waiting Room)` (the dominant remaining source), and `AddMarker (Self)` (this card + its own
    markers transfer onto a newly-played ally — the official 継承 keyword, added to the `KW` dict).
  - Explained% 95.3% → **95.5%**, suspects 3578 → **3520** (both real gains — the CX Combo fix in particular
    routes those cards through the residual-absorber math correctly instead of a flat Grant-Ability
    estimate).

**Family-taxonomy audit, round 7 — 9 more `Other` clusters resolved.** Worked through the remaining `Other`
dump in 5 major + 4 minor batches, each confirmed or corrected by the user:

- **`Side Attack (No Soul Loss)`** (new): "サイドアタックしてもソウルが減少しない". Initially mischaracterized as
  defensive; the user corrected this — it's an OFFENSIVE damage-reliability tool. Normally a side attack's
  damage is reduced by the level gap between attacker and defender (soul −1 per level over); this effect lets
  the side attack ignore that reduction and deal its full damage, guaranteeing damage through an attack that
  would otherwise whiff or under-deal.
- **`Clock/WR Exchange`** / **`Level/WR Exchange`** 2nd branches widened to catch the self-referential shape
  ("this card sits at the top of the clock" / "in the level zone" and trades for a waiting-room character) —
  confirmed real, if rare.
- **`Clock/Stage Exchange`** (new, split off `Clock/WR Exchange`): `DC4/W81-073`'s "アラーム このカードがクロック
  の1番上にあり…あなたは自分のキャラを1枚とこのカードを選び、入れ替えてよい" has NO waiting-room qualifier at all — unlike
  `ISC/S81-P02`'s explicit "自分の控え室のキャラ" — meaning the trade partner is an in-play STAGE character, not a
  discarded one. Per the "split by variant, don't lump" rule established for Bomb and Reverse Immunity, this
  gets its own family instead of a relaxed WR regex that would blur two different resources together.
- **`Grant Trigger Icon (Class)`** (new): grants a trigger-icon bonus to an entire CLASS of climax cards
  (any CX whose printed trigger icon matches X, in all zones), not a single named target — a broader scope
  than the existing named-target `Grant Trait` pattern, even though the underlying mechanic (extend an
  identity slot) is conceptually the same.
- **`Trigger Icon Reuse`** (new): "あなたは◯◯の効果で……選んでよい" — lets you apply a trigger icon's bonus effect
  (salvage/gate/choice/…) OUTSIDE of an actual trigger check, e.g. pulling off a Gate-icon-style pickup even
  when no climax with that icon actually triggered. Confirmed real by the user.
- **`Marker Cleanup`** (new): "このカードの下のマーカーをすべて控え室に置く" — bulk-discards all markers parked under
  this card; the disposal half of the marker-banking mechanic (`AddMarker (...)` is the deposit half).
- **`Reverse Immunity (Paid)`** (new): "あなたはコストを払ってよい。そうしたら、そのターン中、このカードは【リバース】しない"
  — a THIRD Reverse Immunity variant (after `(Cost 0)` and `(Hand4/Solo)`), gated behind a generic paid cost
  instead of a fixed condition. Confirmed real by the user.
- **`Burn`** widened to also catch symmetric "all players take N damage" text (previously matched
  opponent-only damage). Confirmed: burning everyone is still a Burn.
- **`Clock Reorder`** (new): "自分のクロックすべてを好きな順番で並べ直す" — sibling of the existing deck-side Look &
  Reorder, same reordering mechanic applied to your own clock instead of your deck.
- **`Opp Disrupt`** widened with a 3rd branch: wiping the opponent's entire marker area ("相手の枠を…選び…
  マーカー置場のマーカー…控え室に置") is a disruption tool against the opponent's board state, joining the existing
  hand/stock/deck/etc. branches even though the zone reference here is indirect (via a chosen opponent slot,
  not a literal 相手の(zone) phrase).

Explained% flat at **95.5%**, suspects **3521** (up 1 from 3520 — effectively unchanged, within noise for a
re-classification pass). `pipeline/analysis/family_catalog.txt`: **122 families** (was 115). `Other` down to
**178 signatures / 399 occurrences**.

**Bug-fix pass (same session): two clean fixes, no family-naming call needed.**

- **`ra()`'s dash-placeholder filter was missing two Unicode dash variants** (HYPHEN U+2010 `‐`, HORIZONTAL
  BAR U+2015 `―`) actually used by 18 real "no ability" rows in the raw JP data — these were being costed
  and family-labeled as if they were real abilities instead of dropped. Fixed in `cost_model.py` (the
  canonical source both `build_db.py` and `build_official_list.py` import `ra()` from) and mirrored in the
  two other active tools with their own local copy (`_tr2_extract.py`, `cost_standardize.py`); the two
  known-superseded legacy tools (`build_master_list.py`, `_tr_extract.py`) were left untouched.
- **`Removal (Deck Top)` / `Removal (Memory)` / `Removal (Stock)` were each missing the same
  battle-opponent-reference branch** (`このカードとバトル(中の|している)キャラ`) that their sibling
  `Removal (Deck Bottom)` already had — the same gap class fixed repeatedly this session for Bomb's
  `_BOMB_OPP`, Clock Kick, etc. Real cards fell through to `Grant Ability`, the generic `Stock Boost`
  catch-all, or `Other` instead. Fixed all three, verified against real corpus text (`DC/W01-059`,
  `KF/S05-032`, `LB/W06-T06`, `LB/W06-018`, `FH/SE03-001`).

**Family-taxonomy audit, round 8 — 8 more `Other` clusters resolved, with several user corrections.**

- **`Grant Trait` widened** to also accept a fixed/described target (not just "choose 1"): a face-off
  opponent (`このカードの正面のキャラに…を与える`) or every matching character (`他のあなたの…キャラすべてに…を与える`,
  incl. name-matched groups). Same final purpose (assign a trait) — confirmed by the user to fold in rather
  than split.
- **`Deck Mill`** (new): blindly put the top N (or up to N, or a variable X) of your own deck straight into
  the waiting room — no 見る/選ぶ verb, unlike the existing `Deck Thin` (which views and picks). **Deliberately
  kept OUT of `Brainstorm`/集中**, even though both end in the waiting room: the user was emphatic that this
  is a rules-level distinction, not just a different trigger — the official 集中/Brainstorm keyword reveals
  cards into an intermediate *resolution zone* before discarding, while a plain mill sends cards straight to
  the waiting room with no such step. `Brainstorm` stays reserved for the keyword mechanic only.
- **`MemorySelf`** (new): a plain ACT ability that sends THIS CARD itself into Memory. NOT filed as a Retreat
  variant — the user's correction: it fires in the main phase, has nothing to do with attacking/battle, and
  isn't a combat escape, just a bare self-relocation. Also NOT named the more generic "Compress" — the user
  pointed out that banking a card in Memory is only ONE of several ways to achieve a similar board-tidying
  effect (having a lot of clean stock is another), so the family is named for the specific zone/action, not
  the abstract goal.
- **`Drawback` widened** to also cover "this card's power does not increase or decrease" — looks protective
  at first glance (immune to a Bomb/Drawback-style power cut), but the user's ruling is Drawback: locking
  your own power ALSO blocks every beneficial modifier (Backup/Assist/Power Pump from teammates), which are
  more common/valuable in practice than a targeted power reduction would be, so the net effect is negative.
- **`Memory/WR Exchange`** (new): a third sibling of `Clock/WR Exchange` and `Level/WR Exchange` — same
  "trade which card sits in a resource zone" purpose, this time Memory ↔ waiting room.
- **`Link Identity`** (new): the official 【リンク】 marker's whole "ability" is just its own bare name (e.g.
  "ASMR", "Groovy Mix") — an identity tag other cards' text can reference/search for, carrying zero game
  action. Verified across the full corpus: every real 【リンク】-marked row has no Japanese punctuation at all,
  so detecting on "marker present + no 。/、 in text" can't misfire on a real ability that happens to also
  carry the marker.
- **`Declare`** (new): an AUTO/CONT/ACT whose whole effect is announcing a flavor quote
  ("…と宣言してよい"/"…と言ってよい") — already costed 0 via the pre-existing `is_noop()` structural no-op check, but
  had no family name of its own and fell to `Other` despite being fully audited/intentional.

Explained% flat **95.5%**, suspects **3522 → 3517** (a small real gain). `pipeline/analysis/
family_catalog.txt`: **126 families** (was 122). `Other` down to **151 signatures / 296 occurrences**.

**Bug-fix pass (same session): markerless `※` print/legality notices.** Survey found 94 real markerless
rows in the corpus starting with `※` — all print/legal metadata ("cannot be used in official/sanctioned
tournaments", "domestic/overseas distribution only", "treated as the same-name card as X", date-gated ban
notices, foil-type notices), none gameplay text. Added to `ra()`'s drop-list (mirrored across the two other
active tools with their own copy, `_tr2_extract.py`/`cost_standardize.py`). Side effect: 16 fewer spurious
"distinct" cards after alt-art dedup (two prints previously looked different only because of a superficial
print-notice ability text; the dedup signature is built from `ra()`'s output, so removing the notice let
them correctly merge). Explained% flat 95.5%, suspects 3517 → 3516.

**Family-taxonomy audit, round 9 — 4 more clusters resolved.**

- **`Hand/Level Exchange`** (new): a 4th sibling of `Clock/WR Exchange`, `Level/WR Exchange`, and
  `Memory/WR Exchange` — same "trade which card sits in a resource zone" purpose, this time Hand ↔ Level.
  **Terminology correction from the user while reviewing the citation:** a card leaving the STAGE as an
  ability's cost should always be described as "put into your waiting room," never "discard" — discard
  specifically means a hand card. Worth remembering for all future EN citations.
- **`Damage Reflect`** (new): "during this card's battle, when the damage you received is not canceled, deal
  the SAME damage to your opponent." Same final effect as `Burn` (opponent takes damage) but the amount is
  variable by mirroring whatever you just took (not a printed number) and the trigger is a completely
  different mechanism (reactive to incoming damage, not an on-play/on-attack clause) — kept as its own family
  so its cost standard isn't blended with fixed-number Burn's.
- **`Strip Trait` gap widened** (20→40 chars) to also match `JJ/SE42-01`'s shape, where a marker-wipe clause
  sits between choosing the trait and the character losing it — still filed as plain `Strip Trait` (the
  marker wipe is a minor secondary detail on a small cluster, not worth a combined family name).
- **`Strip Trait (All)`** (new): a wider-scope sibling — choose 1 trait present on the opponent's stage, and
  ALL of the opponent's characters (not just one) lose it until end of turn. Genuinely broader in scope than
  plain `Strip Trait` (board-wide vs single-target), so it gets its own name.
- **`AutoKickToDeckShuffle`** (new, in `ONREV_PAT`): this card returns itself to the deck and shuffles, on
  reverse — a sibling of `AutoKickToBottom`, but a different resource value: `AutoKickToBottom` guarantees a
  fixed, known redraw position, while shuffling puts it at a random one.

Explained% flat **95.5%**, suspects **3516** (flat). `pipeline/analysis/family_catalog.txt`: **130 families**
(was 126). `Other` down to **135 signatures / 238 occurrences**.

**Family-taxonomy audit, round 10 — 7 more clusters resolved.**

- **`Power Pump` widened** with 2 more branches: a 2-target selection that includes the citing card itself
  ("choose another character AND this card, both get +N power"), and a fixed/named/positional target with
  no selection verb at all ("your other card named X in slot Y gets +N power"). Same final purpose as the
  existing family — folded in per the user.
- **`Effect Copy`** (new): play another of your own character's named on-play `[AUTO]` ability as if it were
  this card's own. Distinct from `Grant Ability` (that GIVES a new ability; this REUSES one already printed
  elsewhere on your board).
- **`LastAttacker`** (new): a REPLAY/finisher shape — sacrifice every other one of your own characters, then
  swap this card for a specific named waiting-room ally. Per the user: this is the last attack of a
  sequence, sacrificing your whole remaining board to bring in one more fresh attacker.
- **`Cost Substitute`** (new): distinct from `Free Play (Alt Cost)` (which discounts THIS card's own play
  cost) — this lets a hand card substitute for a STOCK payment on a *different* card's ACT ability elsewhere
  on the board.
- **`Memory/Hand Exchange`** (new): a 5th sibling of the Clock/WR-style Exchange group — this card sits in
  Memory and swaps for a chosen hand character.
- **`Memory Partner Swap`** (new): this card sits in Memory and swaps for a specific *named* partner card
  also in Memory — not a resource-zone trade like its siblings, but switching which of two named identities
  occupies a shared Memory slot.

Explained% flat **95.5%**, suspects **3516 → 3518** (noise, expected for several thin new sub-families).
`pipeline/analysis/family_catalog.txt`: **135 families** (was 130). `Other` down to
**123 signatures / 206 occurrences**.

**The `Removal (...)` group** (added in the family-taxonomy audit pass): every ability whose final purpose
is "get the opponent's STAGE character out of play" is a Removal variant, split by destination because the
destination changes the character's cost to the game (a bounce to hand lets the opponent replay it
immediately; a permanent removal to the bottom of the deck denies recursion entirely) — `Removal (Hand)`
(formerly `Bounce`), `Removal (Waiting Room)` (formerly `Disruption`), `Removal (Deck Bottom)`,
`Removal (Deck Top)`, `Removal (Memory)` (usually temporary — returns to the stage at the next Encore
step), `Removal (Swap)` (the opponent must replace it with a weaker character pulled from their own
waiting room). `Clock Kick` is **deliberately excluded** from this group even though it also relocates an
opponent's character to a zone: its real purpose is dealing *uncancellable damage* (bypassing the
climax-reveal cancel a normal Burn allows), using the clock placement as the delivery mechanism, not board
control. `ReviveOpponent` is the mirror-image family (an opponent's own waiting-room character placed onto
their own stage, to give one of your own reverse-requiring finishers a legal target). `AllMemoryCleanse`
(a symmetric "every player trims Memory" housekeeping effect), the `AddMarker (...)` group (bank a card as
a marker under this one, split by source zone — see below — and also catching the RETRIEVAL half of the
same mechanic, markers coming back out onto the stage), and `Drawback` (the opponent acts against the
card's own controller's zones — the negative-polarity counterpart of Disruption/Opp Disrupt) were split out
of the `Card Select` grab-bag the same pass. `Opp Disrupt` was widened to cover the opponent's waiting room
too, including the REFLEXIVE construction `相手は自分の…` (the opponent, acting on THEIR OWN zone — most real
prints phrase it this way, not the possessive `相手の…`). User taxonomy throughout (methodology: classify by
the ability's final effect only — never by cost, trigger, or requirements, which belong to the cost math,
not the name). `Card Select` went from the original 1547 signatures down to 0 across three audit passes.

The family label serves two jobs: it groups abilities for the lookup site, and it supplies the **family
median** used to estimate signatures with no measurement (STEP 3a/3c). A family that never converges (because
a mixed pattern leaks into it) produces a meaningless median — which is exactly why the taxonomy is so
carefully ordered.

**`Other` went from 123 signatures / 206 occurrences down to 0** across a single extended session
(2026-07-23), the same "eliminate the grab-bag" treatment `Card Select` got earlier. ~28 new families were
named (163 total, up from 135) — see the git history around this date for the full list; a few worth calling
out for the taxonomy itself: **`Drawback` absorbed most of the round** (grew from 4 branches to ~14) under
the user's explicit standing rule — *any effect that gives power to a card is a Drawback, no separate name
needed per shape, regardless of what triggers it or what specific self-risk it takes*. Concretely this
includes self-relocation on non-`【リバース】` triggers (attack-end, Encore step, `アラーム`-gated), total
stock/deck dumps, voluntarily reversing yourself, your battle opponent never reversing, revealing your own
hand or deck top with no other consequence, ceding control of your own deck to the opponent, and forced
self-or-ally sacrifices — the model prices these anywhere from +500 to +2000 depending on how bad the
downside actually is, exactly matching the "measured cost = the power given as compensation" principle from
§0. **`SummonFromMarker`** (new) names the mechanic "bring a banked marker onto the stage as a real
character" — flagged as **also present, but still mis-filed, in two already-established families**
(`Stand/Rest` and `AddMarker (Waiting Room)`); not yet reclassified — see the reviewer/roadmap notes for the
open "audit every family's actual content" task this surfaced. This round's session also fixed 2 real
parsing bugs unrelated to family logic (both in `pipeline/ingest/clean_cardlist.py`'s `split_abilities()`,
both a misplaced `<br>` splitting one ability into a bogus two) and one `gen()`-level bug (halfwidth corner
brackets `｢｣`, used across a whole print run, were invisible to the name-collapsing regex — see `ZT`).

---

## 7. The CX-Combo family

A **CX Combo** is an ability hard-gated to a specific named climax — you can only use it while that climax is
assembled, so its cost is paid by *assembling the combo*, not in power. It is therefore its **own family** and
is resolved **last** as the pure residual absorber, so it takes **whatever value is left over** — with **no
arbitrary 500 minimum and no ceiling** (`CXC_FLOOR = 0`). The only floor is 0: a beneficial combo cannot cost
negative (the same non-negativity every other beneficial absorber gets; a negative absorbed value came only
from single-card over-stat noise, and CX Combo is not a measured-negative drawback family). Empirically,
dropping the old 500 floor to 0 *raised* the Explained% acceptance metric (95.5→95.6%) and *cut* the suspect
count (3555→3481) — flooring a lone CX-Combo absorber above its card's own residual had been manufacturing
suspects. (Historical note: the removed 500 floor once lifted the CX-Combo *subset consistency* 93.4→95.0%,
but that is a different, more self-referential metric than the out-of-sample Explained%.)

Detection (`family()` + `CXC_PAT`), on the `gen()`-normalized text (names already `「N」`):

- the explicit **`【CXコンボ】` marker** (modern cards) — including the `CX置場` abbreviation;
- **`クライマックス置場に「N」が(ある|あり)`** — "if [name] is in your climax area" (the classic combo trigger);
- **`「N」が(クライマックス置場に)?置かれた`** — "when [name] is placed" (on-place flavor).

Deliberately **not** matched: `あなたのクライマックスが…置かれた` ("when *any* of your climaxes is placed"), a
generic on-climax trigger that is not gated to a specific combo CX.

In the cascade, CX-Combo signatures are **residual absorbers** (§4, STEP 3b): they are hardest to measure
directly, so instead of being estimated in isolation they soak up each card's leftover delta once every other
signature on the card is known, and they are resolved **last**.

> **Honest caveat** (from the project's own notes): the ~98% figure (§12) is *consistency*, not proven
> *correctness*. Making CX Combo its own family and resolving it last keeps the accounting self-consistent;
> whether each individual combo's absorbed value is the designer's true intent is not independently verifiable.

---

## 8. Replay folding

A `【リプレイ】` (REPLAY) row is **never a standalone effect**. Its text is not AUTO/CONT/ACT — it is the
**body** of a *citing* ability (an AUTO/CONT/ACT that invokes it by name, e.g. "…「全力全開！」を発動する").
The replay "develops" wherever it is cited, so its cost belongs to the citer and must be **counted once**.

`_fold_replays` does this before the cascade:

1. For each replay row, `_rp_find_citer` locates the ability on the same card that invokes it. The replay
   reads `〔ACTION NAME〕　〔effect body〕`; the citer refers back by the action name. Since we don't know where
   the name ends, `_rp_action_prefixes` generates every candidate name (the text up to each whitespace
   boundary, plus the whole string) and tries them **longest-first**. A candidate is accepted only when, in
   some *other* ability, it is immediately followed by an activation verb (`を発動する` / `を使用する` /
   `をトリガー` / `する`) or a clause boundary — i.e. that ability genuinely *uses* the named action.
2. The replay's **effect body** (its text minus the leading action name) is appended to the citer's text, and
   the citer is measured under that **combined** signature (`csig`, a *citer* signature = a residual absorber).
3. The replay row itself is measured under its own signature (`rsig`) — which STEP 0 fixes at **cost 0**.

Net result: the replay body's cost is counted exactly once, on the citer, and never double-counted. A replay
with no citer on the card is left untouched and recorded as an *orphan*.

---

## 9. Cost-0 / flavor rules

Not every printed line is a costed ability. Four concrete zero mechanisms exist:

- **Parenthetical reminders are dropped, not costed** (`ra()`). Text wholly wrapped in `（…）`/`(…)` with **no**
  `自/永/起` marker is beginner / trigger-icon reminder text (e.g. "（bounce：…）"), not a real ability. Dash
  placeholders (`-`, `ー`, …) and print/legality notices (markerless `※` text) are dropped too.
- **Structural-zero text costs 0** (`is_zero_flavor`, STEP 0b — a superset of the older `is_noop` check).
  Three shapes: (1) no-op declarations — an ability whose whole effect is "declare/say 『X』"
  (`『…』と宣言してよい` as the final clause, plus 3 related list-form/symmetric/bare-namelist Declare shapes) —
  performs no game action; (2) `Damage Source (Bottom)` — a purely cosmetic CONT that changes which cards get
  milled by this card's dealt damage without dealing MORE of it; (3) `Flavor Text` — promo cards whose whole
  "ability" is a joke with zero mechanical effect. Each of these still gets its own real family name via
  `family()` — the cost-forcing and the naming are independent mechanisms keyed off the same text pattern.
- **Replay bodies cost 0** (STEP 0, §8) — structural, because the cost is carried by the citer.

The underlying design principle is **net advantage**: an effect that nets neither player an advantage costs
nothing. A perfectly **symmetric** effect (both players get the same benefit) nets zero and is a design-level
zero for the same reason; in the current code the *concrete* structural zeros are the three above.

---

## 10. Era is metadata, NOT a cost driver

The model **does not depend on era**. Historically there was a binary `legacy`/`modern` split (legacy cards
assumed ~2× cost, "power-creep"), but that split is **removed** — and it was already **dead code**:
`card_era.json` was relabelled to hold *format* names (Genesis/Bounty/Gate/Standby/Choice/Horizon, bounded by
climax trigger-icon debut dates), so the old `era == "modern"` test never matched and every sample already
pooled into one bucket. STEP 1 now takes the mode over **all** years.

This is not just a convenience — it is an **empirical finding**, checked in `cost_standardize.py` (the
"creep vs dispersion" analysis, §11). For every well-sampled package (n ≥ 30) spanning ≥ 2 era buckets, the
per-era mode is computed (`per_year_modes`). **Every tight (high mode-share) high-n package is flat across all
six eras** — the standard does not move with time. The two packages whose per-era mode *appears* to shift are
both *loose* signatures (low mode-share) whose "mode" merely tracks which card mix landed in each era. So:

> The apparent power-creep is **effect-mix shift + dispersion**, not a real per-package price change.

`release_date` (YYYY-MM-DD, per card) and the format-era label are therefore **descriptive metadata only** —
useful for filtering/flavour on the site, never inputs to the cost.

---

## 11. The read-only standardizer — `cost_standardize.py`

This companion script **does not touch** the live model, DB, or cache. It re-implements `gen`/`family`/
`pb`/dedup byte-for-byte so its package signatures line up 1:1 with the live model, then writes analysis
artifacts into `pipeline/analysis/`:

- **`package_standards.csv`** — the standardized price list: per package, its `n_samples`, `mode_cost`,
  `mode_share_pct`, distinct-value count, family, type, payment key, an example card, and the JP text.
- **`suspects.csv`** — every isolated card whose actual cost deviates from its package mode by ≥ 500, ranked
  by `|deviation|` then `package_n` (anomalies in well-established, high-mode-share packages float to the
  top — those are the real suspects).
- **`payment_credits.csv`** — how much each payment type "buys down". The clean estimator is
  **body-matched**: group cards by `(ability_type, effect_body)` (the gen text with its leading `［…］`
  bracket stripped), then within a group compare two payment-variants that differ by **exactly one** payment
  tag — the cost gap is that tag's credit. (A coarser family baseline cross-checks it.) This reproduces the
  anchors: hand-discard credits real power (≈ −500 to −1000), deck-to-clock ≈ 0.
- **`cost_standardize_report.md`** — the written report, including validation anchors (Backup 3000/L2 → 6000,
  the generic searcher → 500, etc.) and the creep-vs-dispersion table.

---

## 12. Validation — why there are no unit tests, and what "98%" means

This is a **data / research** project, not an application: the proof is **empirical**, measured against the
official list (the oracle), never asserted in unit tests. There is nothing to `assert` — the correct cost of
a real ability is precisely what the model is trying to discover, so validation is done with **counts and
audits**, per `CLAUDE.md`.

Two different accuracy figures exist, and it matters which is which:

- **~98% "consistency"** (`Conclusions.md`, `CLAUDE.md`): reconstructing a multi-ability card by summing its
  ability costs lands within ±500 of the printed delta in ~98% of cases (mean error ~68 power). The live
  model's internal `validation_pct` (measured+residual only) is the same kind of check. This proves the
  **additive + residual accounting is self-consistent** — but it partly re-uses the residuals that were fit
  from those same cards, so it is not a fully out-of-sample test.
- **~94.5% "Explained%"** (`OVERVIEW.md`, the acceptance metric, n ≈ 31.9k, floor 94%): the share of valid
  costed Character cards whose per-card residual (actual vs the package **standards**) is within ±500. This
  is the honest out-of-sample number — the standards are a fixed price list, not re-fit per card.

The **suspects mechanism** is the audit tool: ~4.2k cards are flagged `is_suspect` (`|residual| ≥ 500`).
A suspect is not necessarily a model error — it may be a genuinely off-curve card — but the ranked list is
where to look when improving accuracy. Confidence sample counts (from `Conclusions.md`): ~3,835 measured,
~8,580 residual, ~3,474 estimated.

---

## 13. The multiplicative draft (spec, mostly not wired)

There is a separate **conceptual** model for how a *single* ability's cost is built up multiplicatively:

```
ability_cost = floor500( base_effect × Σ_triggers(difficulty) × (½)^(temporal + Σ conditions) )
```

with costs **adding** across a card's abilities. Full spec, evidence, and open questions are in
**`documentation/pump_cost_model.md`** — read it there. Status: it is a **design spec, not a wired model**.
The *only* piece cabled into `cost_model.py` today is **STEP 3d** — the `Power Pump (self)` estimate
(`pump_self_estimate`), where the base is the readable printed `+N`. The net-advantage families
(salvage/search/bounce/debuff/…) are **not** cabled: their base is the effect's net card-flow value, which
the text parser cannot read reliably, so they keep the flat family-median estimate. Do not treat the
multiplicative formula as governing the live numbers beyond self-pump estimation.

---

## 14. Where the pieces live

- **`pipeline/cost_model.py`** — the single implementation of everything above (helpers, taxonomy, replay
  folding, the cascade, the EN-exclusive pass). Both `build_official_list.py` (Excel) and `build_db.py`
  (SQLite) `import` it and read costs off `build_cost_model(clean)`; each caller owns its own I/O.
- **`pipeline/cost_standardize.py`** — read-only analysis (§11), writes `pipeline/analysis/`.
- **`documentation/OVERVIEW.md`** — the short project overview.
- **`documentation/pump_cost_model.md`** — the multiplicative draft (§13).
- **`pipeline/Conclusions.md` / `pipeline/Ability_Cost_Guide.md`** — the original narrative + the guide for
  costing effects that exist on no card (both point here for the canonical model).
