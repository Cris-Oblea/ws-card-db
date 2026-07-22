# RUNBOOK.md — operating ws-card-db by hand (no AI assistance)

> The **hands-on operator's manual**. Every command you need to rebuild the data, regenerate the outputs,
> run the site, deploy it, and handle the common change requests — assuming **no AI help**, just a terminal
> and this file. Commands are shown for Windows PowerShell (the dev machine); on macOS/Linux replace
> `python` with `python3` if needed. See [`STACK.md`](STACK.md) for what to install first,
> [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the stages connect, and [`COST_MODEL.md`](COST_MODEL.md)
> for the cost math.

---

## 0. Prerequisites (once per machine)

```
python --version                         # must be 3.14+
python -m pip install -r requirements.txt # installs openpyxl
```

All commands below are run **from the repo root** (`ws-card-db/`) unless stated otherwise.

> **You usually do NOT need to rebuild anything.** The canonical inputs (`cardlist_clean.json`,
> `cardlist_en.json`, the translation JSONs) and the shipped `site/ws.sqlite.gz` are committed. Rebuild
> only when you change the cost model, add a card set, or refresh translations.

---

## 1. Full rebuild, in stage order

Run these **in order**. Each stage writes the inputs the next one reads (see the data flow in
[`ARCHITECTURE.md`](ARCHITECTURE.md)). Stages 1–2 hit the network; the rest are local.

```
# ── INGEST (only when adding/refreshing card data; otherwise skip to stage 6) ──
python pipeline/ingest/harvest_cardlist.py       # 1. scrape JP list      -> ingest/cardlist_full.json
python pipeline/ingest/fetch_filter_options.py   #    taxonomy+neo titles -> ingest/filter_options.json, neo_titles.json
python pipeline/ingest/clean_cardlist.py         # 2. normalize           -> cardlist_clean.json (+ audit)
python pipeline/ingest/harvest_products.py       # 3. JP release dates    -> ingest/products_jp.json
python pipeline/ingest/date_sets.py              #    date every set      -> ingest/set_dates.json
python pipeline/ingest/build_card_era.py         #    per-card era        -> card_era.json
python pipeline/ingest/fetch_ccondeluci.py       #    official EN text    -> cardlist_en.json

# ── TRANSLATIONS (only when new JP cards lack English; the pass is otherwise DONE) ──
python pipeline/extract_simulator.py "<...\StreamingAssets\Cards>"  # simulator EN -> *_sim.json
python pipeline/fetch_hotc.py                    # HotC EN names          -> name_hotc.json

# ── BUILD THE DELIVERABLES ──
python pipeline/build_official_list.py           # 6. Excel abilities list -> Complete_Abilities_List.xlsx
python pipeline/build_db.py                       # 7. web database         -> site/ws.sqlite(.gz) + bumps app.js
```

Each script **prints a report** (counts, validation %, what it wrote). Read it — that is how you validate
this data project (there are no unit tests; see `CLAUDE.md` → "Validation").

> `build_features.py` is **not** part of this sequence — it is a research substrate, not on the shipping
> path (see [`ARCHITECTURE.md`](ARCHITECTURE.md) §6).

---

## 2. Regenerate just ONE thing

**Just the web database** (after a cost-model or translation change — the common case):
```
python pipeline/build_db.py
```
This reads the existing `cardlist_clean.json` / `cardlist_en.json` / `card_era.json` / translation JSONs,
recomputes costs via `cost_model.py`, writes `site/ws.sqlite`, gzips it to `ws.sqlite.gz`, and stamps a new
`?v=` cache-bust hash into `site/app.js`. It also **asserts** the acceptance floor (Explained% ≥ 94%) — if
that assertion fires, the model regressed; investigate before shipping.

**Just the Excel abilities sheet:**
```
python pipeline/build_official_list.py
```

**Just the cost-guide Excel** (the model for costing novel effects — standalone, no data inputs):
```
python pipeline/build_cost_sheet.py
```

**Just the read-only cost analysis** (does **not** touch the live model/DB/cache — safe to run anytime):
```
python pipeline/cost_standardize.py              # -> pipeline/analysis/*.csv + report
```

---

## 3. Run the site locally

```
cd site
python -m http.server 8000
# open http://localhost:8000/
```
The app fetches `ws.sqlite.gz`, gunzips it with pako, and runs SQLite (sql.js) in the browser. If you just
rebuilt the DB, a plain refresh picks it up (the `?v=` hash changed). See [`WEBAPP.md`](WEBAPP.md) for
internals and troubleshooting.

---

## 4. Deploy to GitHub Pages

The site is static — deploying = pushing the `site/` files. `ws.sqlite.gz` is tracked; the uncompressed
`ws.sqlite` is gitignored (the app only needs the `.gz`).

```
git add site/ws.sqlite.gz site/app.js            # the rebuilt DB + the bumped cache version
git commit -m "data: rebuild ws.sqlite"
git push
```
GitHub Pages serves the `site/` directory (per the repo's Pages settings). After the push, the live site
updates within a minute or two. **Always commit `app.js` together with `ws.sqlite.gz`** so the cache-bust
version matches the data you shipped.

> Commit each discrete change on its own (project convention — see `CLAUDE.md`). Don't batch a data rebuild
> with unrelated code changes.

---

## 5. Common change recipes

### A. A new card set was released
1. Re-run the **ingest** stages (§1, stages 1–3) to pull the new JP cards, date the new set, and refresh
   the official EN text. The harvest is resumable and only fetches what's new.
2. If the new cards have no English yet, refresh the translation sources (§1 translations block). The
   JP→EN pass is otherwise **done**; `extract_simulator.py` and `fetch_hotc.py` are the ongoing non-AI
   refreshers for new sets — **not** something to re-run wholesale.
3. Rebuild the deliverables (§1, stages 6–7).
4. Sanity-check the printed reports: card/ability counts went up, Explained% still ≥ 94%, no new orphan
   warnings. Then deploy (§4).

### B. Add a new cost family
The cost taxonomy lives in **`pipeline/cost_model.py`** (the single source). Add/adjust the family
detection there, then re-run `build_db.py` and `build_official_list.py`. **How** the families work and the
measured→residual→estimated cascade are explained in [`COST_MODEL.md`](COST_MODEL.md). Do not add family
logic to `build_master_list.py` (superseded) or to the builders — they must stay thin I/O around the model.

### C. Debug a suspect cost
A card is flagged `is_suspect` when `|residual| ≥ 500` (its actual budget deviates from the sum of standard
package costs). To inspect one card's per-ability breakdown:
```
$env:DBG_CARD="RZ/SE35-11"; python pipeline/build_official_list.py
```
To dump every variant matching a substring (and its isolated samples):
```
$env:DBG_SIG="レベル×500"; python pipeline/build_official_list.py
```
For the standardized price list + a ranked list of suspects, run the read-only analysis (§2) and read
`pipeline/analysis/suspects.csv` and `cost_standardize_report.md`. Root-cause fixes go in `cost_model.py`.

### D. Add a legacy-disparity EN exclusion
Some old franchises were renumbered/merged for their English release, so a same-code EN card is the *wrong*
card. The curated exclusions live in **`pipeline/build_db.py`**:
- `EN_BLOCK_PUB` — block a whole publisher/franchise (e.g. `DG`, `P4`, `PI`, `LL`).
- `EN_BLOCK_CARD` — block specific permuted card numbers.
- `EN_BLOCK_ENSET` / `FT_ALLOW_SET` — set-level allow/block refinements.
Add the offending publisher or card there, re-run `build_db.py`, and confirm the card now shows **no** (or
the correct) English rather than a wrong graft. The rationale and mechanism are in
[`en-name-matching.md`](en-name-matching.md).

---

## 6. Safety notes

- **Never delete `pipeline/translation_cache.json`** — it is the permanent, hand-built translation store.
  Losing it means re-doing all the by-hand translation work.
- The regenerable artifacts are gitignored on purpose; don't force-commit `cardlist_full.json`,
  `features_by_card.csv`, `ws.sqlite` (uncompressed), the `.xlsx` files, or the `_tr*` scratch folders.
- After a `git add`, run `git status` and check you're not committing a huge regenerable file or scratch
  output before you push.
- `build_db.py` asserts Explained% ≥ 94%. If it aborts, the cost model regressed — fix the model, don't
  lower the floor.

## To go deeper
- What to install → [`STACK.md`](STACK.md)
- How the pieces connect → [`ARCHITECTURE.md`](ARCHITECTURE.md)
- The cost math → [`COST_MODEL.md`](COST_MODEL.md)
- The web app → [`WEBAPP.md`](WEBAPP.md)
