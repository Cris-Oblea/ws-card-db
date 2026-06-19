# -*- coding: utf-8 -*-
"""
Build card_era.json: map every card_number -> its release ERA.

This is the per-CARD projection of the per-EXPANSION dating produced by date_sets.py
(set_dates.json). card_era.json is consumed by the cost builders (build_db / build_master_list
/ build_official_list), which read it from the parent (canonical) folder.

Run AFTER date_sets.py (it needs set_dates.json).

Reads:  ../cardlist_clean.json (card_number, expansion) + set_dates.json (release_year per expansion)
Writes: ../card_era.json   = {card_number: era}

ERA BUCKETS (edit ERA_BUCKETS to change or extend the eras):
  Each bucket is (name, min_release_year). A card's era = the LAST bucket whose
  min_release_year <= the card's set release year. The default reproduces the classic
  legacy/modern split at 2017. To split finer by trigger generation, add buckets, e.g.:
      ("pre_standby", 0), ("standby", 2017), ("choice", 2019)
  (trigger debuts per build_features.py: standby 2017, choice 2019, ...).
"""
import json, os
from collections import Counter

D = os.path.dirname(os.path.abspath(__file__))

ERA_BUCKETS = [
    ("legacy", 0),       # released before the first cutoff below
    ("modern", 2017),    # released in 2017 or later
]


def era_for(year, fallback):
    """Last bucket whose min_year <= year. If the year is unknown, use the fallback era."""
    if year is None:
        return fallback
    name = ERA_BUCKETS[0][0]
    for n, y0 in ERA_BUCKETS:
        if year >= y0:
            name = n
    return name


cards = json.load(open(os.path.join(D, "..", "cardlist_clean.json"), encoding="utf-8"))
sd = {r["expansion_id"]: r for r in json.load(open(os.path.join(D, "set_dates.json"), encoding="utf-8"))}

out, no_set = {}, 0
for c in cards:
    rec = sd.get(c.get("expansion"))
    if rec is None:
        no_set += 1                                   # card whose set has no dating record -> skipped
        continue
    out[c["card_number"]] = era_for(rec.get("release_year"), rec.get("era") or ERA_BUCKETS[0][0])

with open(os.path.join(D, "..", "card_era.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)

print(f"card_era.json: {len(out)} cards | buckets={[b[0] for b in ERA_BUCKETS]} | cards without a dated set={no_set}")
print("  by era:", dict(Counter(out.values())))
