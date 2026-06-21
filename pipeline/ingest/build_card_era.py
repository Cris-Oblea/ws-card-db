# -*- coding: utf-8 -*-
"""
Build card_era.json: map every card_number -> its release ERA.

This is the per-CARD projection of the per-EXPANSION dating produced by date_sets.py
(set_dates.json). card_era.json is consumed by the cost builders (build_db / build_master_list
/ build_official_list), which read it from the parent (canonical) folder.

Run AFTER date_sets.py (it needs set_dates.json).

Reads:  ../cardlist_clean.json (card_number, expansion) + set_dates.json (release_date per expansion)
Writes: ../card_era.json   = {card_number: era}

ERAS: the 6 trigger-debut eras are defined ONCE in eras.py (single source of truth,
shared with date_sets.py and the future cost_model.py). A card's era = the LAST era
whose start_month <= the card's set release MONTH ("YYYY-MM"). Sets without a
release_date fall back to the first era (Genesis); cards whose set has no dating
record at all are skipped (counted as cards-without-a-dated-set).
"""
import json, os
from collections import Counter

from eras import ERAS, era_for_month

D = os.path.dirname(os.path.abspath(__file__))

FALLBACK_ERA = ERAS[0][0]   # undated set -> oldest era (Genesis)

cards = json.load(open(os.path.join(D, "..", "cardlist_clean.json"), encoding="utf-8"))
sd = {r["expansion_id"]: r for r in json.load(open(os.path.join(D, "set_dates.json"), encoding="utf-8"))}

out, no_set = {}, 0
for c in cards:
    rec = sd.get(c.get("expansion"))
    if rec is None:
        no_set += 1                                   # card whose set has no dating record -> skipped
        continue
    rd = rec.get("release_date")
    ym = rd[:7] if rd else None                        # "YYYY-MM" (month precision); None -> fallback era
    out[c["card_number"]] = era_for_month(ym, FALLBACK_ERA)

with open(os.path.join(D, "..", "card_era.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)

# ---------- report ----------
dist = Counter(out.values())
print(f"card_era.json: {len(out)} cards | eras={[n for n, _ in ERAS]} | cards without a dated set={no_set}")
print("  by era:")
for name, start in ERAS:
    print(f"    {name:8} (>= {start}) = {dist.get(name, 0)}")
