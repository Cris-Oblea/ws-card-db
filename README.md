# ws-card-db — Weiss Schwarz card database & power cost per ability

Project 1 of the **WSAI** portfolio. Two things:

1. An **extraction & analysis pipeline** that documents, for every *Character* card ability,
   **how much power it costs** (how much it lowers the card's base power). Validated at ~98%
   against the official Japanese card list (15,889 abilities, 63,350 cards).
2. A **query app** (static web, in progress): search any card and see all of its information
   plus the breakdown of **how much each effect subtracts from its base power**.

> ⚠️ The ability-cost decipher method is **WIP**: it works and is validated at ~98%, but it
> sometimes fails. That's why every cost is reported with a **confidence level** (HIGH =
> measured directly · MEDIUM = residual · LOW = estimated from family) and the database is
> **regenerated** whenever the model improves.

## Updating for new card releases

The pipeline is **re-runnable**: when Bushiroad releases new cards, re-scrape the official
list, re-clean, and rebuild — the database picks up the new cards automatically while the
cost model keeps being refined in parallel.

```
harvest -> clean -> cost model -> rebuild database -> publish app
```

## Structure

```
pipeline/        Extraction, cleaning, cost model and derived data
  build_official_list.py   Generates the official Excel (power cost per ability)
  official_en.py           Matches official EN text per ability
  cardlist_clean.json      63,350 cards with clean fields (source of the DB)
  cardlist_en.json         Official English text
  translation_cache.json   PERMANENT JP->EN translation cache (do not delete)
  card_era.json            legacy/modern dating per card
  ingest/                  Harvest, clean, set dating, features
  sources/                 Rules, macros and reference material
reference/       Official Bushiroad documents (reference)
site/            Query web app (sql.js + ws.sqlite.gz) — the deliverable, deployed to GitHub Pages
```

## Cost model (summary)

`Power_base = 3000 + 2500·Level + 1500·Cost − 1000·[trigger=Soul] − 1000·(Soul−1)`

An ability's **cost** = `Power_base − Power_real`. It is measured by isolating abilities on
single-ability cards (*measured*), propagated by residual on multi-ability cards (*residual*),
and, when there is no data, estimated from the family median (*estimated*).

## What is NOT versioned

- Card **images** (`Galería/`, ~4.1 GB) — re-downloadable from the official site.
- `cardlist_full.json` (raw harvest) and `features_by_card.csv` — regenerable by the pipeline.

---

**Private** personal repository. Card text and images are property of Bushiroad.
