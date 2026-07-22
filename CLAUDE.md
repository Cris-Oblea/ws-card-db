# CLAUDE.md — ws-card-db

Project 1 of the **WSAI** portfolio. An extraction/analysis pipeline that measures the **power cost per ability** of Weiss Schwarz cards (validated ~98% against the official JP list: 15,889 abilities / 63,350 cards) + a **static lookup website**. Personal repo (CrisRP-dev/ws-card-db).

> ⚠️ **This file is the SOURCE OF TRUTH for the stack and conventions.** When the project grows (new libs, new technology, new folder), update it HERE. The agents read this file and do NOT hardcode versions, so there's no need to modify them when the stack changes.

## Language
This repository is **English-only**. All documentation, code comments, commit messages and communication must be in **English** — keep it universal for a potential public release.

## Documentation (RULE — to keep the repo tidy)
- **Any stack/convention change is updated IN THIS `CLAUDE.md`** as soon as it happens (new lib, version, folder). It is the source of truth; never let it go stale.
- **The entire workings of the project live documented in `documentation/`**: what it does, **how it works**, **how it was built**, **what technologies** it uses, the architecture and the decisions. ⚠️ Here the docs go in `documentation/` (and not in `site/`) because **`site/` is already the deployed web app** (GitHub Pages). The `CLAUDE.md` is the index/summary; `documentation/` is the detail.
- Keeping `documentation/` + this `CLAUDE.md` up to date **is part of finishing a change**, just like the code. A change without updated docs is not finished.

## Underlying purpose
The reason it exists: **a balance reference for designing CUSTOM cards** — *"I want this effect → it costs X power"*. The cost is the power SUBTRACTED from a card relative to its base (`power_real = power_base − cost`), **always in multiples of 500**. Measuring the cost of the 15,889 real abilities gives the yardstick for costing new effects that don't exist on any card.

## What it is (two products)
1. **Pipeline (Python):** scrapes the official JP list, normalizes, dates by era, and computes the power cost of each ability (measured → residual → estimated). Output: the SQLite that powers the static site (the deliverable); Excel cost sheets are generated locally on demand.
2. **Lookup website (static):** search any card and see the cost breakdown of each effect. No backend — everything runs in the browser.

## Stack (the volatile part — updated HERE as it grows)
- **Python 3.14** — stdlib (`json`, `sqlite3`, `re`, `urllib.request`, `csv`, `statistics`, `unicodedata`, `glob`) + **`openpyxl`** (Excel).
- **Web:** HTML5 + vanilla JS + **`sql.js`** (SQLite in the browser) + **`pako`** (gunzip). Data in `site/ws.sqlite.gz`. Cache versioning with `?v=N`.
- **CI:** GitHub Actions (`ci.yml`) — Python compile smoke + gitleaks secret scan on every push/PR. No formal test suite (see "Validation").

## Structure
- `pipeline/` — canonical scripts: `build_official_list.py`, `build_db.py`, `build_master_list.py`, `build_cost_sheet.py`, `official_en.py`, `extract_simulator.py` (harvests EN translations from the fan simulator's `CardData.txt`), `fetch_hotc.py` (scrapes EN names from heartofthecards.com) + the JSON sources (`cardlist_clean.json` = JP truth, `cardlist_en.json`, `card_era.json`, `translation_cache.json`, `name_sim.json`/`traits_sim.json`/`abilities_sim.json` = simulator translations, `name_hotc.json` = Heart of the Cards names).
- `pipeline/cost_model.py` — **the SINGLE SOURCE of the power-cost MATH** (helpers + family/type taxonomy + replay folding + the measured→residual→estimated cascade + the EN-exclusive pass). `build_official_list.py` and `build_db.py` both `import` it and read costs off `build_cost_model(clean)`; each caller does its own I/O (Excel sheets / SQLite emit + EN matching) around it. Cost no longer depends on era (the legacy/modern split was dead and is removed — `card_era.json` holds FORMAT names, so era/date is metadata only). Keep the board-pump regex `あなたの…(キャラ|「N」|《T》)すべてに…パワーを＋` exact. NOTE: `build_master_list.py` is an older, divergent cost variant (no CXC, no replay folding, different family labels) NOT wired to this module — superseded by the two canonical builders.
- `pipeline/ingest/` — sub-pipeline: `harvest_cardlist.py` → `clean_cardlist.py` → `date_sets.py` → `build_features.py`.
- `pipeline/cost_standardize.py` — READ-ONLY cost analysis (does not touch the live model/DB/cache): standardizes the per-ability *package* price (mode over all years, no era split), hunts cost suspects, and estimates payment-bracket credits. Outputs to `pipeline/analysis/`.
- `pipeline/analysis/` — generated analysis artifacts: `package_standards.csv` (the standardized price list), `suspects.csv` (cards deviating from their package mode), `payment_credits.csv` (per-payment credit), `cost_standardize_report.md` (the written report).
- `pipeline/sources/` — official rules, macros, manuals (reference material, **not code**).
- `site/` — the web app = **the deliverable** (`index.html`, `app.js`, `style.css`, `ws.sqlite.gz`); deployed to GitHub Pages.
- `reference/` — official Bushiroad PDFs.

## How to run
- Abilities Excel: `python pipeline/build_official_list.py`
- SQLite for the web: `python pipeline/build_db.py`
- Local web: `cd site && python -m http.server 8000` → http://localhost:8000/

## Conventions
- **Costs** always multiples of **500** (the game's power economy).
- **Confidence (evidence-based):** `HIGH` (measured with `n_samples ≥ 3` and `mode_share ≥ 60%`) · `MEDIUM` (residual, or measured with weaker evidence) · `LOW` (estimated). Reflects the standard's evidence, not just the method.
- **Cost = a fixed per-package STANDARD (the MODE of the signature's samples, pooled across ALL years — NO era split).** A package = the full ability signature (markers + normalized text, brackets/payment INCLUDED). The DB shows the per-card **actual** budget vs that standard; the **residual** (`real_delta − Σ standard_cost`) is the designer's adjustment, and a card with `|residual| ≥ 500` is a **suspect**. There is **no power-creep at the package level** (validated: high-n packages have a flat mode 2008→now); the apparent creep was effect-mix shift + dispersion.
- **Era / date:** descriptive **metadata only** (NOT a cost driver). `release_date` (YYYY-MM-DD) is stored per card; the format-era label (Genesis/Bounty/Gate/Standby/Choice/Horizon, bounded by climax trigger-icon debuts) is optional flavor.
- **Dedup:** keep the base rarity, discard alt-art/parallels.
- **Encoding:** UTF-8 + NFKC normalization (full/half-width Japanese).
- **Code comments (permanent policy):** ALL code — existing and new — carries inline comments explaining HOW each non-trivial piece of logic works, not only WHY. This is a deliberate project rule (the repo must stay operable by hand, without AI assistance) and OVERRIDES the default "no comments unless the WHY is non-obvious" guidance. Comments in English; update them when the code changes (a change with stale comments is not finished).

## What NOT to touch
- `pipeline/sources/` and `reference/` — reference material, not code.
- `pipeline/translation_cache.json` — PERMANENT translation cache (reuses prior work, do not delete).
- `.gitignore` — already excludes the regenerable artifacts (raw harvest, features.csv, uncompressed ws.sqlite).

## Validation (instead of classic tests)
This is a **data/research** project: the "proof" is **empirical** — % accuracy against the official list + audits (`cardlist_audit.json`, counts, suspects). There are NO traditional unit tests. Whoever validates (the `reviewer`) does so with **data counts and audits**, not with assertions.

## Workflow (LIGHTWEIGHT — personal project, no team)
There's no mandatory issue, no board, no PR reviewed by another person. The flow is:
```
request → architect (plan + trade-offs)  →  🚦 you approve  →  the appropriate dev-agent  →  reviewer (audits)
```
Skip steps when the task is small/obvious. Commit/push to `main` directly (or a lightweight PR if you want to review the diff). Read-only tasks (querying, searching) don't need the flow.

## Agents (in `.claude/agents/`)
Defined by **ROLE** (they defer to this CLAUDE.md for the stack, so they don't break as it grows):
- **`architect`** — plans, weighs trade-offs. Does not code. (generic, reusable)
- **`reviewer`** — audits quality and data at the end. (generic, reusable)
- **`pipeline-dev`** — maintains/improves the extraction, cleaning and build pipeline.
- **`cost-analyst`** — the cost model, validation and accuracy improvement.
- **`web-maintainer`** — the static lookup website.

## Relationship to the WSAI portfolio
- It came out of the `wsai/analisis/` workshop → **this repo is the clean canonical version** (if you edit the pipeline, do it here, not in `wsai/analisis/`, to avoid drift).
- It is consumed by **ws-sim-ai** (P3) to reason about value/tempo/economy with grounded numbers.
