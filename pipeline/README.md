# Weiss Schwarz — Ability cost (workspace)

Project: **balance reference for CUSTOM cards**. "I want this effect → it costs X power".
Cost = power that is SUBTRACTED from a card relative to its base (`power_real = power_base − cost`), **always in multiples of 500**.

---

## ★ DELIVERABLES (what you'll use)

| File | What it is |
|---|---|
| **`Lista_Habilidades_COMPLETA.xlsx`** | **THE product.** The **15,889** distinct abilities in the game, each with its measured cost. Sheets: *All abilities* (the table), *Summary*, *How to use*. |
| `GUIA_COSTO_HABILIDADES.xlsx` / `.md` | The **model** for costing NEW effects that don't exist on any card (primitives + modifiers + composition + examples). Complements the list. |
| `phases_reference.md` | Reference of game phases/timing (from the official JP ruling). |

### How to read the list
- **Cost (500s)**: the power to subtract. **Method**: `measured` (direct delta on single-ability cards, the most reliable) ·
  `residual` (the ability only appears alongside others; the known ones are subtracted and its cost remains) ·
  `estimated` (median of its family; indicative).
- **Confidence** HIGH/MEDIUM/LOW according to number of samples and dispersion. **n** = samples. **Range** = measured min..max.
- **Official EN**: pulled from the English harvest and **verified** (markers + numbers + keywords match the JP); if it doesn't match, it's left blank (a wrong EN is never shown).

---

## How to regenerate the deliverable
```
python build_master_list.py      # -> Lista_Habilidades_COMPLETA.xlsx
python build_cost_sheet.py       # -> GUIA_COSTO_HABILIDADES.xlsx
```

### Active scripts (root)
| Script | Function | Reads |
|---|---|---|
| `build_master_list.py` | Builds the complete list (measured→residual→estimated) | `cardlist_clean.json`, `cardlist_en.json`, `card_era.json`, `official_en.py` |
| `official_en.py` | RELIABLE match of JP ability → official EN (consistency filter) | `cardlist_clean.json`, `cardlist_en.json` |
| `build_cost_sheet.py` | Generates the guide/model for novel effects | (standalone) |

### Canonical data (root)
| File | What it is |
|---|---|
| `cardlist_clean.json` | **JP source of truth**: 63,350 normalized cards (stats + abilities + markers). |
| `cardlist_en.json` | **Harvest from the official English site**: 18,532 cards with official EN text. |
| `card_era.json` | `card_number → legacy(<2017)/modern(≥2017)` (extracted; replaces the 76 MB CSV). |

---

## Simulator duel log (extra)
The simulator (Blake Thoennes, Unity) **does** leave a playable match log in `Player.log`
(under `%USERPROFILE%/AppData/LocalLow/Blake Thoennes/Weiss Schwarz/`), interleaved with
Unity noise. `parse_duel_log.py` cleans and structures it:
```
python parse_duel_log.py                 # uses the default Player.log
python parse_duel_log.py <path.log>      # a specific log (e.g. Player-prev.log)
```
Outputs in `duel_logs/`: `duel_<log>.txt` (readable transcript: pre-game / game by
phases / post-game) + `duel_<log>.json` (structured events + summary). It captures mulligan,
plays, resolved effects (with EN text), costs, attacks, encore, brainstorm, and the AI's
decisions (SearchValue). It reports every unclassified line (nothing is dropped silently).
Use for the project: an empirical record of **how a deck is piloted** (timing and real valuation),
complementing the AI scripts in `StreamingAssets/AIData/`.

## Folders
- **`pipeline/`** — scripts and raw data to *regenerate* the canonical data (JP/EN harvest, cleanup, set dating, features). To run them you must co-locate the data; normally you don't need to touch them.
- **`fuentes/`** — raw learning material: official rules (`ws_rule*.txt`), manual scans (`manual_*`), video transcript, macros, screenshots.
- **`_archive/`** — EVERYTHING obsolete/experimental (reversible, nothing deleted): the old v3 cost system (`costs_*`, `ws_decompose*`), the lossy EN (`en_match`, `variant_tr*`), the regression experiments (`v4_*`, `log_linear`) that **failed**, superseded primitive measurements, signature/translation intermediates, and the old list `Power_by_ability_OFICIAL.xlsx` (superseded).

---

## Cost model (summary)
`power_base = 3000 + 2500·level + 1500·cost − 1000·(trigger soul) − 1000·(soul−1)`
- **Resource economy**: card to hand/stock ≈ +1 resource ≈ +1000; to waiting = you lose a resource.
- **Era**: legacy ≈ 2× the modern cost (powercreep) → design with MODERN values.
- **Composition**: bundle = SUM · modal "choose 1 of N" = the strongest option · multi-trigger = value × number of triggers.
- **CX-combo / hard-gate**: floor ~500 regardless of power (paid in assembling the combo).
- **Method validation**: across 34,767 fully reconstructed multi cards, the additive cost is accurate to ≤500 in **98%** of cases (mean error 68 power).
