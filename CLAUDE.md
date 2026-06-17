# CLAUDE.md — ws-card-db

Project 1 of the **WSAI** portfolio. An extraction/analysis pipeline that measures the **power cost per ability** of Weiss Schwarz cards (validated ~98% against the official JP list: 15,889 abilities / 63,350 cards) + a **static lookup website**. Personal repo (CrisRP-dev/ws-card-db).

> ⚠️ **This file is the SOURCE OF TRUTH for the stack and conventions.** When the project grows (new libs, new technology, new folder), update it HERE. The agents read this file and do NOT hardcode versions, so there's no need to modify them when the stack changes.

## Language
This repository is **English-only**. All documentation, code comments, commit messages and communication must be in **English** — keep it universal for a potential public release.

## Documentation (RULE — to keep the repo tidy)
- **Any stack/convention change is updated IN THIS `CLAUDE.md`** as soon as it happens (new lib, version, folder). It is the source of truth; never let it go stale.
- **The entire workings of the project live documented in `documentation/`**: what it does, **how it works**, **how it was built**, **what technologies** it uses, the architecture and the decisions. ⚠️ Here the docs go in `documentation/` (and not in `docs/`) because **`docs/` is already the deployed web app** (GitHub Pages). The `CLAUDE.md` is the index/summary; `documentation/` is the detail.
- Keeping `documentation/` + this `CLAUDE.md` up to date **is part of finishing a change**, just like the code. A change without updated docs is not finished.

## Underlying purpose
The reason it exists: **a balance reference for designing CUSTOM cards** — *"I want this effect → it costs X power"*. The cost is the power SUBTRACTED from a card relative to its base (`power_real = power_base − cost`), **always in multiples of 500**. Measuring the cost of the 15,889 real abilities gives the yardstick for costing new effects that don't exist on any card.

## What it is (two products)
1. **Pipeline (Python):** scrapes the official JP list, normalizes, dates by era, and computes the power cost of each ability (measured → residual → estimated). Output: Excel (`deliverables/`) + SQLite for the web.
2. **Lookup website (static):** search any card and see the cost breakdown of each effect. No backend — everything runs in the browser.

## Stack (the volatile part — updated HERE as it grows)
- **Python 3.14** — stdlib (`json`, `sqlite3`, `re`, `urllib.request`, `csv`, `statistics`, `unicodedata`, `glob`) + **`openpyxl`** (Excel) + **`mcp>=1.0`** (FastMCP).
- **Web:** HTML5 + vanilla JS + **`sql.js`** (SQLite in the browser) + **`pako`** (gunzip). Data in `docs/ws.sqlite.gz`. Cache versioning with `?v=N`.
- **MCP server** (`tools/ws-mcp/server.py`): cross-repo portfolio status tools + card search.
- No CI; no formal test suite (see "Validation").

## Structure
- `pipeline/` — canonical scripts: `build_official_list.py`, `build_db.py`, `build_master_list.py`, `build_cost_sheet.py`, `official_en.py` + the JSON sources (`cardlist_clean.json` = JP truth, `cardlist_en.json`, `card_era.json`, `translation_cache.json`).
- `pipeline/pipeline/` — sub-pipeline: `harvest_cardlist.py` → `clean_cardlist.py` → `date_sets.py` → `build_features.py`.
- `pipeline/fuentes/` — official rules, macros, manuals (reference material, **not code**).
- `deliverables/` — the final Excel files (versioned).
- `docs/` — the web (`index.html`, `app.js`, `style.css`, `ws.sqlite.gz`).
- `tools/ws-mcp/` — the MCP server.
- `reference/` — official Bushiroad PDFs.

## How to run
- Abilities Excel: `python pipeline/build_official_list.py`
- SQLite for the web: `python pipeline/build_db.py`
- Local web: `cd docs && python -m http.server 8000` → http://localhost:8000/
- MCP server: `python tools/ws-mcp/server.py`

## Conventions
- **Costs** always multiples of **500** (the game's power economy).
- **Confidence:** `HIGH` (measured) · `MEDIUM` (residual) · `LOW` (estimated).
- **Era:** `legacy` (<2017, ~2x more expensive) · `modern` (≥2017). Power-creep matters.
- **Dedup:** keep the base rarity, discard alt-art/parallels.
- **Encoding:** UTF-8 + NFKC normalization (full/half-width Japanese).

## What NOT to touch
- `pipeline/fuentes/` and `reference/` — reference material, not code.
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
