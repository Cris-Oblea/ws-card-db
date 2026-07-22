# Conclusions — Ability cost in Weiss Schwarz (2026-06-14)

> **Canonical model reference:** the up-to-date, detailed explanation of the cost model lives in
> **`documentation/COST_MODEL.md`**. This file is the original narrative/decision log; where the two differ,
> `COST_MODEL.md` wins. In particular, the era claim below has been **superseded** — see §2.

## 1. What was delivered
**`Complete_Abilities_List.xlsx`** — the **15,889 distinct abilities** that exist in the game (the entire universe of measurable Characters), each with a **cost in power** (multiple of 500), its family, the real JP text, the official EN when it could be verified, and two critical honesty columns: **Method** and **Confidence**. Plus the **`Ability_Cost_Guide`** for costing effects that do NOT exist on any card.

It serves what you wanted: **look up "this effect → costs X"** and **draw inspiration for new cards**.

## 2. The cost model (what I really understood about the game)
The power that is SUBTRACTED from a card for having an ability **≈ the net resource/tempo advantage that ability provides.**
- **Resource economy** (the deep reason): bringing a card to **hand or stock = +1 resource ≈ +1000**; sending it to waiting = losing a resource. That's why a heal to the hand *always* carries a cost: the cost **pays** for the resource, it does not discount it.
- **Ease of execution**: an on-play effect with no cost or condition is EXPENSIVE; gated (cost, condition, unreliable trigger) is cheaper. Since most come gated, **the mode of the costs falls in 500–1000**.
- **Era**: ~~legacy cards (<2017) cost ~2× what the same effect would cost today (powercreep)~~ — **SUPERSEDED.** Era/date is **descriptive metadata only, NOT a cost driver.** There is **no power-creep at the package level**: for every tight, well-sampled package the per-era mode is flat across all six format eras (verified in `cost_standardize.py`). The apparent creep was **effect-mix shift + dispersion**, not a real price change. Standards are the MODE pooled across ALL years — do NOT apply an era multiplier. (See `documentation/COST_MODEL.md` §10.)
- **Composition**: bundle (do everything) = **SUM**; modal (choose 1 of N) = the **best option**, not the sum; multi-trigger = value × number of triggers.
- **CX-combo / hard-gate**: priced as the pure leftover residual — no fixed floor beyond 0 and no ceiling (the cost is paid in assembling the combo, not in power; a combo can cost 0 power when the setup already pays for it). *(Superseded the old ~500 floor; see `documentation/COST_MODEL.md` §7.)*
- **Different families, different regimes**: burn is costed by *ease*, heal by *destination*, board-buff by *quantity×2*. They are not unified.

## 3. What worked and what didn't (the methodological lesson)
- ❌ **Regression did NOT work** (linear, log-linear, symbolic/gplearn, random-forest). Tested thoroughly and discarded: the modifiers are **effect-dependent** (a cost lowers a burn but *pays* a heal), so no universal coefficient exists. This was counterintuitive —you yourself expected regression to assemble the table— but the data refuted it.
- ❌ **The v3 decomposer (ridge/iterative) didn't either** — decomposing EVERY card at once propagates errors and yields absurd costs (0, −6500). That was the old "terrible and error-ridden" list.
- ✅ **What does work: MEASURE, don't infer.** Cards with **a single ability** give the exact cost (direct delta, no decomposition). From that clean base it **propagates by residual** (on multi cards, subtract what's already known) and the irreducible part is **estimated** by family.
- ✅ **The proof that the method is correct:** I reconstructed 34,767 multi-ability cards by summing the costs of their parts, and the result is **accurate to ≤500 in 98%** of cases (mean error 68 power). The additive + residual model is solid.

## 4. Confidence and limits (honest)
- **Measured (3,835)** = the most reliable, direct cost. **Residual (8,580)** = derived by subtracting clean seeds. **Estimated (3,474)** = family median, indicative.
- **HIGH+MEDIUM confidence = 4,279 rows**; the rest is LOW (many single-sample residuals). But note: the global 98% validation says that even the LOW ones are accurate in aggregate — the LOW mark is prudence, not "it's wrong".
- **Official EN on 5,087 rows** (32%), all **verified** (markers+numbers+keywords match the JP); where it could not be verified it was left blank, never a wrong EN. Japanese is the truth; EN is convenience.
- What remains rough: rare bundles (modal/cost-branch that are not SUM), per-marker pumps (variable value), and the long tail of unique effects.

## 5. How to use it for custom cards
1. **Effect that already exists** → look it up in the list (filter by Family), check the Cost and the Method/Confidence.
2. **New effect** → use the GUIDE: decompose into primitives, apply modifiers (cost, condition×reliability, breadth — **no era factor**), compose (sum/modal/multi-trigger), round to 500.
3. **Rule of thumb**: think in resources. Does the ability give you a card (hand/stock)? ≈ +1000. Is it easy to trigger? more expensive. Does it depend on a climax? it's the pure residual — floor 0, no ceiling (the combo's cost is paid in setup, not power).

## 6. If you want to continue (optional)
- Raise the confidence of the residuals by weighting them by the quality of their seeds (a residual built from HIGH seeds is almost HIGH).
- More EN coverage (align EN on multi cards with more rules).
- Manually validate a sample of "estimated" to calibrate the family medians.
- Detect and separately cost the non-additive operators (modal/replacement) that the residual currently assumes as a sum.
