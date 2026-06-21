# Multiplicative cost-decomposition model (DRAFT — design spec, NOT yet wired into the live model)

> Status: a validated **conceptual** model for how a single ability's power-cost is built up. Derived on
> the `Power Pump (self)` family (where the effect base is literally the `+N` printed on the card, so the
> model is directly checkable), but intended to generalize to all families. **Not yet implemented** in
> `cost_model.py`; this is the agreed design + the open questions before any wiring. Source of the rules:
> the project owner (the cost designer / oracle), cross-checked against the measured/residual data.

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
   does free; same effect + trigger ⇒ same budget. A STOCK / rest / sacrifice payment does not change the
   net card-flow, so it does not move the budget. The ONLY "payment" that moves the budget is a **hand
   discard**, and it acts via the **net-advantage base** (it cancels card gain: a +1 salvage that discards
   1 becomes net-0 ⇒ base 1000 → 500), not as a separate payment factor. So payment is dropped from the
   formula entirely. (This supersedes the earlier "not separable" matched-pairs reading — it is not
   unmeasurable, it is genuinely not a power-budget axis.)
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

## Implications for wiring (deferred decision)
- Apply ONLY to `estimated` (LOW-confidence) sigs; never touch measured/residual (they already encode this).
- Highest-precision first: fire the multiplicative estimator where parsing is reliable (clean self-pumps
  with a readable `N` and detectable modifiers); fall back to the flat family median elsewhere.
- Pair with **golden-cost overrides** for the cards the formula can't nail (the irreducible tail).
