# Multiplicative cost-decomposition model (PARTIALLY wired: Power Pump (self) + Salvage + Look & Reorder)

> Status: a validated **conceptual** model for how a single ability's power-cost is built up. Derived on
> the `Power Pump (self)` family (where the effect base is literally the `+N` printed on the card, so the
> model is directly checkable), and since generalized to `Salvage` (whose base is the swap's net advantage,
> not a printed number) and `Look & Reorder` (base halved per condition) — see "Wiring status" below. Cabled
> in `cost_model.py` for these three families only; Search/Removal (Hand)/Power Debuff/etc. are qualitatively
> harder and still use the flat family median. Source of the rules: the project owner (the cost designer /
> oracle), cross-checked against the measured/residual data.

## The formula

```
ability_cost = floor500( base_effect × Σ_triggers(trigger_difficulty) × (1/2)^(temporal + Σ conditions) )
```

- `base_effect` = the **NET advantage** of the effect (card-flow / tempo gain), not the raw action.
- `Σ_triggers(trigger_difficulty)` = sum over the ability's activation timings of each timing's difficulty
  factor: **easy = 1, hard = ½**. One easy trigger ⇒ ×1; two easy ⇒ ×2; one hard ⇒ ×½ (unifies the trigger
  COUNT and the trigger DIFFICULTY into one term).
- **Payment (`［…］`) is NOT a factor** — it is an interchangeable resource channel (see below), so it is gone
  from the formula.

Two levels, do not mix them:
- **Within one ability:** modifiers are **multiplicative** (the rule below).
- **Across a card's abilities:** costs **add up** (`card_real_delta = Σ ability_cost`). Abilities are
  independent — each is costed in isolation, then summed. This is the additive backbone the live model
  already validates at ~99% (card = sum of its abilities).

## Component rules

### base_effect — the NET advantage
The base is the effect's **net** value (card advantage / tempo), NOT the raw verb.
- A salvage that nets **+1** card (recover, no hand-discard) ≈ **1000**.
- A salvage that nets **0** (recover 1 but also discard 1 from hand — `-1 +1 = 0`, no plus) ≈ **500** — HALF
  of net+1. It still has selection value (dump a dead card, take a live one), so it is 500, not 0.
- **Power Pump (self):** the printed power number `N` (a `+4000` pump has base 4000). This is what makes
  the family ideal for validating the model — base is readable.
- **Search (to hand):** ~1000.  Cross-family note from the owner: **Power Debuff (remove the opponent's
  power) base > Power Pump (self) base.**
- **Flexibility shifts the base, and designers balance it against riders.** A salvage restricted to a
  `《trait》` character is worth LESS than an unrestricted "recover any card" salvage. Clean balanced pair —
  both net-0 on-enter salvages paying `［1 stock + discard 1］`, both measure **500**: `5HY/W90-024[1]`
  (NO trait-lock, no rider) = `PJS/S91-T34[1]` (trait-LOCKED **+** a pump rider). The trait-lock restriction
  (−) exactly funds the pump rider (+), so both land at the net-0 salvage value of 500.
- **A small RIDER does not add cost** (within one ability). `PD/S22-055` = `［1 stock + discard 1］ on-enter,
  recover 1` (net-0, NO rider) measures **500**; `PJS/S91-T34` = the SAME net-0 salvage **plus** a `+1000
  (turn)` pump rider also measures **500**. The rider (a new-era addition) is folded in for free.

### triggers — Σ of per-trigger DIFFICULTY (count × difficulty in one term)
Every AUTO/CONT needs ≥1 activation timing (the base trigger is free — without one it could never fire,
same logic as "a pump with no condition is a no-op"). The trigger term is the **sum over all triggers of
each one's difficulty**:
- **easy = ×1** (reliable timings: on-enter `手札から舞台に置かれた時`, on-attack `アタックした時`, on-play).
- **hard = ×½** (conditional timings: on-reverse `【リバース】した時`, on-leave `舞台から控え室に置かれた時`,
  when-sent-to-waiting-room).
- **count adds up:** two easy triggers ⇒ ×2.
- **ACT (`【起】`):** no event trigger — activated in the main phase by paying its cost.
- **Evidence (all measured):**
  - `DAL/W131-039` — search (500) with TWO easy triggers (on-enter OR on-attack) = `500 × (1+1) = 1000`.
  - `IMC/W41-T23` vs `BD/W54-P17` — IDENTICAL salvage+1 paying `［2 stock］`, differing ONLY in trigger:
    on-enter (easy) = **1000**, on-leave (hard) = **500**. Clean ÷2 for trigger difficulty.
  - 2×2 over all salvage sigs: net+1 / easy = **1000** (n=137), net+1 / hard = **500** (n=67).

### temporal duration — ÷2
A pump limited to a turn window — `あなたのターン中` / `そのターン中` / `次の…ターンの終わりまで` — is worth half
of a permanent one. A genuinely permanent pump does NOT take this ÷2.
- **Evidence:** the owner's `+4000` example — `【永】 during your turn, if 2+ 《T》, +4000` = `4000 × ½(turn)
  × ½(cond) = 1000` (matches the measured residual).

### conditions — ÷2 each
Each restriction gate (`if you have… / when… / トリガー以上 / カード名に「N」…`) halves the value, and they
multiply. Confirmed factors from isolated measured/residual self-pumps (cost ÷ N):

| condition | n | factor |
|---|---|---|
| presence (`いるなら`) | 50 | **0.50** |
| count 2+ (`2枚以上`) | 26 | **0.50** |
| count 3+ (`3枚以上`) | 19 | **0.50** |
| name (`カード名に「N」`) | 8 | **0.50** |

### rounding — OPEN
The owner's rule is **round DOWN** (`1500 ÷ 2 = 750 → 500`). The aggregate data does NOT cleanly confirm
it: the `750` half-step lands on **both** 500 and 1000 across real cards, and round-down scored slightly
worse than round-nearest in reproduction (49.7% vs 53.8% exact). This is unresolved because the rounding
choice is masked by modifier-detection errors — it can't be validated until `k` is parsed reliably.

## Open questions (need DATA investigation — the owner cannot specify these from design)
1. ~~Payment factors~~ **— RESOLVED 2026-06-21: payment is NOT a budget factor.** The `［…］` activation
   bracket and the card's own COST/level are **interchangeable resource channels paid OUTSIDE the power
   budget**. Clean evidence: `T27` (L3 / cost-2, salvage+1 on-enter, **FREE**) = `IMC/W41-T23` (L0 / cost-0,
   same salvage+1 on-enter, **pays 2 stock**) = **1000** — a cost-0 card pays 2 stock to do what an L3
   does free; same effect + trigger ⇒ same budget. A **NEUTRAL** payment (pay stock, rest, the card's own
   cost) is just fuel — it does not change your net position, so it does not move the budget.
   - But a **REAL-LOSS** payment DOES move the budget, because it lowers your net position — and it does so
     via the **net-advantage base**, not as a separate factor. Real losses: **hand discard** (−1 card),
     **self-damage to clock** (deck-top→clock, waiting-room→bottom-of-clock; −life), **sacrifice your own
     stage character** (−board). Evidence (pure-recover salvages, easy trigger): FREE = **1000**, but paying
     **self-damage to clock = 500** (÷2), the same drop a discard gives.
   - **Caveat — net advantage is by VALUE, not card COUNT.** A discard-1-recover-1 that UPGRADES quality
     (dump a dead climax, take a key character) is still ~1000, while pure cycling is ~500. So real-loss
     payments are NOT a clean fixed per-type factor; they fold into the net-advantage base, whose magnitude
     depends on the value swing. (This refines — and partly reopens — the earlier "payment not a factor": the
     truth is *neutral* payments are not a factor, *loss* payments enter via net advantage, value-weighted.)
   - The cost-type list is large and open-ended: `discard_hand(N)`, `rest(self)` / `rest(N)` (resting your
     own characters — owner confirms it moves the budget), `deck_to_clock`, `wr_to_clock`, `sac_other_char`,
     `self_to_clock` / `self_to_memory` / `self_to_wr`, `return_self`, trait/named-restricted variants of
     each, etc. **Method note (owner):** to measure a cost's effect you must read the **complete effect in
     context with its cost**, never the `［…］` bracket in isolation; and a **negative/drawback** effect is
     not usable as a measurement sample. The per-type magnitudes remain UNRESOLVED (thin, value-entangled).
2. **"Hard" condition strength:** very restrictive gates (`ストック7枚以上`, opponent-relative) showed ~×0.25
   in the data, i.e. possibly a stronger discount than the standard ×0.5 — unconfirmed.
3. **Cross-family bases:** quantify the family base values (Power Debuff > Power Pump self, etc.).

## Empirical status (why this is worth doing, and its ceiling)
On 541 measured/residual self-pumps (ground truth):

| estimator | within ±500 | mean &#124;err&#124; |
|---|---|---|
| flat family median (current model) | 75.0% | 660 |
| **multiplicative `N × …`** | **83.9%** | **459** |

So the multiplicative model is a **clear win over the flat median** for the LOW-confidence ESTIMATED tail
(the flat median is absurd for pumps — it gives a `+500` and a `+8000` pump the same cost). But every
modeling variant tried (trigger-as-discount, trigger-as-multiplier, round-nearest, round-floor) plateaus
at **~54% exact / ~84% within ±500**. The residual ~16% is largely **irreducible from text parsing**:
condition-strength variation, per-card designer adjustments, and the genuinely-split half-step rounding.

## Wiring status — PARTIAL cabling, three families done

- **CABLED: Power Pump (self)** (2026-06-21). `cost_model.py` step 3d (`pump_self_estimate`) overrides the
  flat family-median ESTIMATE of self-pump sigs with `base N × (1/2)^(temporal + #conditions)`, floored at
  500. Estimated-only — measured/residual untouched. Result: the 484 estimated self-pumps now scale with
  `N` (e.g. `+10000 if hand ≤1` = 5000 instead of the old flat 500) instead of all sitting at 500. Gates
  held: validation 99%, Explained% 95.5% (≥94), suspects +14 (negligible).

  **Extended to SCALING pumps** (per-unit `+N per matching card` instead of a flat printed `+N`, e.g.
  5HY/W101-004's "…このカードのパワーを、あなたの《5th Year》の枚数×500に等しい値、上げる"). `pump_self_estimate`
  now branches on `_PUMP_SCALE` (「につき」/「枚数」) to `_pump_scale_estimate`, which reads the per-unit rate
  (`_PUMP_RATE1`/`_PUMP_RATE2`) and multiplies by an assumed matching-card count — 0.5 for a single-NAMED
  count-source (`「N」1枚につき`, the narrowest/most-restricted case), 1 for `それらのカード` (a small,
  already-selected group), 4 for `相手のキャラの枚数` (the opponent's whole board, typically large), else 2 (a
  generic own-trait count) — then applies the same temporal/position-restriction ÷2 factors. Validated
  90.5% exact / 97.5% within ±500 on 644/735 isolated samples — the best fit of any estimator cabled so far.

- **CABLED: Look & Reorder** (2026-07-22, `look_reorder_estimate`). Base 1000, halved per `_PUMP_COND` match
  (the same condition-counter reused from Power Pump), guarded against the `Brainstorm`-keyword variant and
  a "keep only some" partial-look shape so those don't get mis-halved. Thin data (14 isolated samples) so
  the guards are deliberately narrow — this is a smaller, lower-confidence win than Pump/Salvage, kept
  because the alternative (flat family median) was actively wrong on a user-flagged card (5HY/W101-003,
  whose name-restricted Look & Reorder must cost 500, not the ungated 1000).

- **CABLED: Salvage** (2026-07-22, `salvage_estimate`). Salvage's base isn't a printed number like Pump's —
  it's the swap's NET ADVANTAGE, so instead of parsing a magnitude, the estimator classifies the package
  into one of two buckets read off 729 isolated single-ability measured samples:
  - **net-0 "pure recycle" → 500**: the payment discards the SAME broad category (CX) as the salvage
    TARGET (also CX), or the target is a single SPECIFIC NAMED card (`「N」`, a narrow/low-flexibility get).
  - **net+1 "upgrade" → 1000**: anything else — most commonly discarding a CX/any card for an
    unrestricted or trait-restricted CHARACTER.

  Validated against the 729 samples: **86.1% within ±500** (comparable margin to Pump's own 84% vs the flat
  median's 75.0%; exact match is lower at 35.8%, but ±500 is the metric that drives Explained%). A further
  attempt to also fold in trigger-difficulty and a "hand-discard credits the upgrade back down" rule (the
  theory in the Payment section above) made the fit WORSE, not better — salvage's payment-credit
  interactions are genuinely more tangled than a clean multiplier, matching the still-open Payment item
  below. Shipped as the plain 2-way categorical read; rebuilt `site/`: Explained% unchanged at 95.6%,
  suspects 3544→3537 (small real improvement, no regression).

- **NOT cabled: Search, Removal (Hand), Power Debuff, …** Investigated Search on the same 2026-07-22 pass (1080
  isolated samples) and found it's qualitatively harder than Salvage: its variance is dominated by WHICH
  deck-manipulation mechanic a package uses (e.g. "search whole deck by trait" = 500 vs "reveal top 3, add
  any card" = 2000 — two disjoint mechanics, not the same base modulated by a condition), so a single
  base-formula doesn't fit the way it does for Pump/Salvage. Would need a per-mechanic base LOOKUP table
  (many distinct search mechanics), not a formula — a bigger, separate effort. Left on the flat family
  median for now rather than force a shaky wire. Trigger-difficulty (easy ×1 / hard ×½) is still not wired
  anywhere as a standalone factor (folded ad hoc into Pump's own `#conditions` count instead).

- **Next levers** when resumed: build the Search per-mechanic base table (start from the isolated-sample
  clusters already in this session's analysis — "trait-deck-search" ≈500, "top-3-reveal-any" ≈2000, etc.);
  golden-cost overrides for cards the formula can't nail; pin the OPEN items (hard-condition strength,
  rounding direction, per-cost-type magnitudes) before cabling more families.
