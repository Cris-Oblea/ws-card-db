# Ability Cost Guide — Weiss Schwarz (for CUSTOM cards)
*Balance reference: "I want this effect → it costs X power". Cost = how much power is SUBTRACTED from the card (power_real = power_base − cost). **Everything in multiples of 500.** Built by measurement (mode) + game model. v1 — 2026-06-14.*

> **Canonical model reference:** for the full, up-to-date explanation of how costs are computed, see
> **`documentation/COST_MODEL.md`**. This guide is the practical cheat-sheet for costing *novel* effects;
> `COST_MODEL.md` is the authority on the model itself. The **era factor below has been removed** — era is
> metadata, not a cost driver (see the note in §0 and §2).

---
## 0. HOW TO THINK ABOUT COST (the model)
**The power-cost ≈ the NET ADVANTAGE in resources/tempo that the effect provides.** Mental formula:

> **cost ≈ (base value of the effect) × (ease of execution) → round to 500**

- **Resource economy:** card to **hand or stock = +1 resource ≈ +1000**; card to **waiting = you lose a resource**. An effect that GIVES you a resource must carry a cost that balances it.
- **Ease:** easy (on-play, no cost, no condition) = expensive; with cost / condition / unreliable trigger = cheaper. MOST effects come "gated" → that's why most fall low (500-1000).
- **Era:** ~~legacy (<2017) ≈ 2× the modern cost (powercreep)~~ — **NOT a factor.** Era/date is descriptive metadata only; there is no per-package power-creep (the apparent creep was effect-mix shift + dispersion, verified empirically). Cost a novel effect the **same** regardless of era.
- **Rounding:** always to 500 (cards move in those increments). Use the **MODE**, not the mean.

---
## 1. PRIMITIVES — BASE value of each effect (clean, mode, 500s, pooled across ALL years)
*These are "easy" atomic effects (on-play, no cost). The gates (section 2) lower them.*

| Effect | Base cost | Notes / sub-types |
|---|---|---|
| **Burn 1** (1 damage to opponent) | **1500** | cancelable by climax. With cost → 500. Multi-burn ≈ ×number of instances. |
| **Heal** (clock → waiting/stock/hand/memory) | **1000** | cost-independent; → **bottom of deck = 500** (worse). |
| **Draw 1** | **1000** | = +1 resource. |
| **Salvage** char (waiting→hand) | **1000** | **CX or any card = 500**. |
| **Search/Tutor** (look at top-N, add 1) | **1000** | **universal + discard-1 (cycling) = 2000** (grab any card, incl. climax). |
| **Return-3** (return ≤3 from opponent's waiting to their deck) | **1500** | anti-salvage / dirty up opponent's deck. |
| **Stock-gen** (deck → stock) | **500** | near-neutral resource (you swap draw for stock). |
| **Bounce** (opponent character → their hand) | **500–1000** | (small n). |
| **Self power-pump** | **CIP one-shot (that turn) = X/3** · **CONT my-turn = X/2** · **CONT always ≈ 2X** | the "always" also defends, hence more expensive. |
| **Board-buff** "+X to ALL your other 《T》" | **2×X** | level-tiered (L0/1→+500, L2→+1000, L3→+1500); **at L3 the +1500 collapses to ~500**. |
| **Clock-kick** (reverse opponent char → their clock) | **≈ burn (~500-1000)** | uncancelable (premium) BUT the "reverse" trigger is unreliable → it compensates. |
| **Backup (助太刀) X** (keyword) | **2×X** | the +1500 backup measures **4000** (not 2×1500=3000) — a fixed per-value exception, confirmed as an all-years standard, not an era effect. |
| **Assist (応援) +X** (to those in front) | generic **3×X** / with trait **X** | |
| **Brainstorm** (集中) mill N | mill4=**1000**, mill5=**2000** | |
| **CIP +X power** already covered above (self-pump CIP = X/3) | | |

---
## 2. MODIFIERS (adjust the primitive — round to 500 at the end)
- **× COST paid:** **EFFECT-DEPENDENT** (not universal). If the effect GIVES a resource (heal→hand/stock, salvage), the cost *balances* it (it doesn't discount, it's already included). If the effect does NOT give a resource (burn), paying a cost **lowers** it (burn 1500→1000 with cost, →500 with cost+condition).
- **× CONDITION (multiplicative, graded by strictness AND reliability):**
  - soft (my-turn, 2+《T》, "card with 'X' in the name") = **×½**
  - strict (specific FULL name) = **×¼**
  - **unreliable** (depends on opponent's board: "reverse", "the opponent has X") = discounts **more** (it may not be usable).
  - OR of conditions discounts less than AND. They stack multiplicatively.
- **× ERA:** ~~legacy ≈ 2× modern~~ — **REMOVED.** Era is not a cost modifier (metadata only; no per-package creep — see §0).
- **SELECTION BREADTH:** universal (any card) >> restricted to a trait (≈ ½).
- **CANCELABLE vs UNCANCELABLE:** damage that passes through the trigger-check is canceled by a climax; that which moves cards (clock-kick, refresh) is NOT → premium, but weigh it against the trigger's reliability.

---
## 3. COMPOSITION OPERATORS (multi-effect cards)
- **Bundle (do all):** **SUM** of the components.
- **Modal "choose K of N":** value of the **eligible option(s)** (≈ the strongest), NOT the sum, NOT ×number of options.
- **Cost-branch "pay→all / don't-pay→choose 1":** **sum (the "both" ceiling)**.
- **Multi-trigger OR:** if the triggers are INDEPENDENT (both can occur) = value-per-trigger **× number of triggers**; if they are exclusive (only one ever) = ×1.

---
## 4. SPECIAL REGIME: CX-COMBO / hard-gate
An ability that **MANDATORILY depends on a specific climax** (in CX zone, or a proper name in level/memory) is priced as the **pure leftover residual** — the cost is paid in *assembling the combo*, not in power, so it carries **no fixed floor beyond 0 and no ceiling** (a combo can legitimately cost 0 power when the setup/gating already pays for it, up through several thousand for a big payoff). The only clamp is non-negativity: a beneficial combo never costs below 0. Detect it by the text CONDITION, not by the 【CXコンボ】 marker (legacy didn't have it). Do NOT sum its effects.

---
## 5. HOW TO COST A NOVEL EFFECT (step by step)
1. **Decompose** into atomic effects (section 1) + identify the composition operator (section 3).
2. **Hard-gate / CX-combo?** → price as the leftover residual, non-negative (floor 0, no ceiling), done.
3. For each effect: **base value** (section 1) × **modifiers** (section 2: cost, condition×reliability, breadth — no era factor).
4. **Compose** (sum / modal=best-option / multi-trigger×n).
5. **Does it give a resource (card to hand/stock)?** add ~1000 if it does NOT carry a cost that balances it.
6. **Round to 500.**

**Example (validated): CGS/WS01-P17** (Backup 2500 + AUTO "when you use the backup, discard 2 → send a high-level opponent char to the waiting"):
- Backup 2500 = 2×2500 = **5000**.
- AUTO = removal (removing an opponent char = board advantage), but gated (only when using backup + discard-2 + high-level target) → **~1000**.
- Total **6000** = the card's real delta. ✓

---
*Confidence: SOLID measured primitives (mode, n≥several). Still approximate/to-be-refined: bounce, pump-both-turns (large amounts), heal-bottom-of-deck, and soul (it almost never appears in isolation). The model costs both the known AND the novel by reasoning.*
