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
4. **On-reverse families** — when THIS card is reversed: `RedBombLevelX`, `AntiEarlyRedBomb`,
   `RedBombLevel0`, `AutoKickToBottom`, `AutoKickToMemory`.
5. **Keyword mechanics (`KW`)** — the keyword *names* the effect: `Backup`(助太刀) · `Assist`(応援) ·
   `Brainstorm`(集中) · `Encore`(アンコール) · `Bond`(絆) · `Change`(チェンジ) · `Accelerate`(加速) ·
   `Shift`(シフト) · `Great Performance`(大活躍) · `Force`(フォース) · `Heal`(ヒール) ·
   `Removal (Hand)`(バウンス — the official keyword name for the same effect as the FAMPAT text-pattern below).
   *Condition* keywords (記憶 Memory, 経験 Experience, 共鳴 Resonance) are **deliberately excluded** — they
   only *gate* a separate effect, so the ability must file by what it actually does.
6. **`FAMPAT` effect-text patterns**, in order: `Burn`, `Heal`, `Clock Kick`, `Removal (Hand)`,
   `Return to Deck`, `Retreat`, `AllMemoryCleanse`, `Removal (Waiting Room)`, `Removal (Deck Bottom)`,
   `Removal (Deck Top)`, `Removal (Memory)`, `Removal (Swap)`, `ReviveOpponent`, `Reverse Opp`,
   `Opp Disrupt`, `RevealTopSalvage`, `Salvage`, `Search`, `Look & Reorder`, `Look Deck`, `Comeback`,
   `Stock Gen`, `AddMarkerWaitingRoom`, `Retreat` (reactive), `Add to Hand`, `Power Pump (board)`,
   `Power Pump (self)`, `Power Pump`, `DiscardCharacterToDraw`, `DrawDiscard`, `Draw`, `Early Play`,
   `Power Debuff`, `Soul`, `Level`, `Mill (self)`, `Retreat` (this card), `Move`, `Stand/Rest`,
   `Stock Boost`, `Choice`, `Cannot Attack`, `Restriction`, `Drawback`, `Card Select`.
7. **`Other`** — nothing matched.

**How a FAMPAT is matched.** Each entry is `(family_name, regex)`; `family()` runs `re.search(regex, text)`
on the `gen()`-normalized text and returns the first family whose regex hits. The regexes are tuned so
narrow, specific mechanics peel off *before* broad grab-bags (`Add to Hand`, `Card Select`, `Move`) that
would otherwise swallow them — e.g. `Retreat` (return your **own** stage character to hand) is checked before
`Add to Hand`, and `Removal (Hand)` (return the **opponent's** character) before both. The `KW`/FAMPAT
distance bounds (`[^。]{0,N}`) keep matches inside one clause so a payment bracket or a later sentence can't
false-match. (Every non-obvious regex carries an inline rationale in `cost_model.py` — read those before
editing one; a "simplification" usually re-opens a mislabel bug that a distance bound was closing.)

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
(a symmetric "every player trims Memory" housekeeping effect), `AddMarkerWaitingRoom` (bank a card as a
marker under this one, to retrieve later), and `Drawback` (the opponent acts against the card's own
controller's zones — the negative-polarity counterpart of Disruption/Opp Disrupt) were split out of the
`Card Select` grab-bag the same pass. User taxonomy throughout (methodology: classify by the ability's
final effect only — never by cost, trigger, or requirements, which belong to the cost math, not the name).

The family label serves two jobs: it groups abilities for the lookup site, and it supplies the **family
median** used to estimate signatures with no measurement (STEP 3a/3c). A family that never converges (because
a mixed pattern leaks into it) produces a meaningless median — which is exactly why the taxonomy is so
carefully ordered.

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

Not every printed line is a costed ability. Three concrete zero mechanisms exist:

- **Parenthetical reminders are dropped, not costed** (`ra()`). Text wholly wrapped in `（…）`/`(…)` with **no**
  `自/永/起` marker is beginner / trigger-icon reminder text (e.g. "（bounce：…）"), not a real ability. Dash
  placeholders (`-`, `ー`, …) are dropped too.
- **No-op declarations cost 0** (`is_noop`, STEP 0b). An ability whose whole effect is "declare/say 『X』"
  (`『…』と宣言してよい` as the final clause) performs no game action — no resource, no opponent interaction, no
  power change — so it is a structural 0. The declaration must be the *last* clause, so a card that declares
  and then does something real is not matched.
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
