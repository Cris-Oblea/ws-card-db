# -*- coding: utf-8 -*-
"""
Single source of truth for the Weiss Schwarz ERA model (month precision).

Why these eras?
---------------
The game's power economy shifts in lockstep with the CLIMAX TRIGGER-ICON
generations: each time Bushiroad introduced a new trigger family the average
card power (and therefore the power cost of an ability) re-baselined. We
therefore split history into 6 eras whose boundaries are the DEBUT MONTH of each
trigger-icon generation, derived from the trigger-debut analysis in
build_features.py. Month precision matters because several debut dates fall
mid-year, and a year-level bucket would mis-assign the sets released in the same
year on the wrong side of the debut.

This replaces the old binary legacy(<2017)/modern(>=2017) split. Both the ingest
scripts (date_sets.py, build_card_era.py) and the future cost_model.py import
ERAS / era_for_month from here so there is exactly ONE place to edit the
boundaries. Stdlib-only / dependency-free on purpose.

Era definition
--------------
Each era is (name, start_month) where start_month is "YYYY-MM". A card belongs to
the LAST era whose start_month <= the card's release month. Plain string
comparison on "YYYY-MM" is lexicographically correct for chronological order.

CANONICAL is the era used as the cost model's reference point (it replaces the
old "modern" reference): the era against which power-creep is normalised.
"""

# Ordered oldest -> newest. Boundaries = trigger-icon generation debut months.
ERAS = [
    ("Genesis", "0000-00"),  # pre-Bounty: original trigger set
    ("Bounty",  "2009-07"),  # Bounty trigger debut
    ("Gate",    "2013-01"),  # Gate trigger debut
    ("Standby", "2017-02"),  # Standby trigger debut
    ("Choice",  "2019-12"),  # Choice trigger debut
    ("Horizon", "2026-01"),  # Horizon trigger debut
]

# The cost model's reference era (replaces the old "modern" baseline).
CANONICAL = "Choice"


def era_for_month(ym, fallback=None):
    """Return the era name for a "YYYY-MM" release month.

    The result is the LAST era whose start_month <= ``ym`` (string comparison on
    "YYYY-MM" is chronologically correct). If ``ym`` is falsy/None the function
    returns ``fallback`` when given, otherwise the first (oldest) era name.
    """
    if not ym:
        return fallback if fallback is not None else ERAS[0][0]
    name = ERAS[0][0]
    for n, start in ERAS:
        if start <= ym:
            name = n
    return name
