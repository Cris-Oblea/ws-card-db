# Multiplicative cost-decomposition model (DRAFT — design spec, NOT yet wired into the live model)

> Status: a validated **conceptual** model for how a single ability's power-cost is built up. Derived on
> the `Power Pump (self)` family (where the effect base is literally the `+N` printed on the card, so the
> model is directly checkable), but intended to generalize to all families. **Not yet implemented** in
> `cost_model.py`; this is the agreed design + the open questions before any wiring. Source of the rules:
> the project owner (the cost designer / oracle), cross-checked against the measured/residual data.

## The formula

```
ability_cost = floor500( base_effect × n_triggers × (1/2)^(temporal + Σ conditions) × Π payment_factor )
```

Two levels, do not mix them:
- **Within one ability:** modifiers are **multiplicative** (the rule below).
- **Across a card's abilities:** costs **add up** (`card_real_delta = Σ ability_cost`). Abilities are
  independent — each is costed in isolation, then summed. This is the additive backbone the live model
  already validates at ~99% (card = sum of its abilities).

## Component rules

### base_effect
- **Power Pump (self):** the printed power number `N` (a `+4000` pump has base 4000). This is what makes
  the family ideal for validating the model — base is readable, not estimated.
- **Other families:** an effect-specific base (e.g. a "look 2 and reorder" ≈ 1000; a trait-search to hand
  ≈ 500). Cross-family note from the owner: **Power Debuff (remove the opponent's power) has a higher base
  than Power Pump (self)** — debuffing the opponent is dearer than pumping yourself.

### n_triggers — a MULTIPLIER, not a discount
Every ability needs an activation timing; the *base* trigger is free (without one it could never fire —
the same logic as "a pump with no condition is a pointless no-op"). What costs is having **more than one**:
- **AUTO (`【自】`):** one or more event triggers (`…時`). Each extra trigger lets the effect fire again in
  the turn, so **k triggers ⇒ ×k**.
- **CONT (`【永】`):** always-on; `n_triggers = 1`.
- **ACT (`【起】`):** no event trigger — activated in the main phase by paying its cost/requirement.
- **Evidence (measured, HIGH):** `DAL/W131-039` — a trait-search-to-hand (base 500) with **two** triggers
  ("when placed from hand" OR "when it attacks") measures `500 × 2 = 1000`.

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
1. **Payment factors (`［…］` leading activation-cost bracket):** how much the activation cost buys down the
   power-cost. The bracket is a WHOLE FAMILY of costs, **not just stock/discard** — it can be: pay stock,
   discard card(s) (generic vs `《trait》`-restricted vs named — stricter ⇒ bigger discount), **sacrifice /
   send other characters** (to waiting room / clock / memory), **take damage to yourself**, rest this card,
   return a card to hand/deck, reveal/exile, etc. Each is plausibly a multiplicative factor (the owner is
   sure it is never flat) but there is no clear method to isolate them yet. `cost_standardize.py`'s
   `payment_tags` already enumerates the type set; the matched-pairs credit data (`payment_credits.csv`) is
   thin and noisy — only `discard_hand` gives a usable signal so far.
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
