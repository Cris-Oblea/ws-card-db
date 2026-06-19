# -*- coding: utf-8 -*-
"""
Assign a Japanese release date to every Weiss Schwarz set (expansion).

Sources, in priority order per set:
  1) archive  : exact 発売日 from products_jp.json, matched by normalized title.
  2) create_date: filter_options.json create_date when NOT clamped at the
                  2018-01-10 site-migration date (reliable for >= 2018 sets).
  3) curve    : monotonic interpolation of set-number -> date within each track
                (W = side -1, S = side -2), fitted on all dated sets.

Track property: within W## and within S##, set number is monotonic with date.

Outputs:
  set_dates.json  : list of {expansion_id, name, set_code, track, series,
                    cards, release_date, release_year, source, era}
  prints a quality + retention report.
Read-only on inputs. Writes ONLY set_dates.json under analisis/.
"""
import json, re, os, unicodedata, datetime, bisect
from collections import defaultdict, Counter

D = os.path.dirname(os.path.abspath(__file__))
def jload(p): return json.load(open(os.path.join(D, p), encoding="utf-8"))

CLAMP = "2018-01-10"               # site-migration create_date (means "unknown, pre-2018")
CUTOFF_YEAR = 2017                 # legacy < 2017 <= modern

# ---------- load expansions ----------
fo = jload("filter_options.json")
exps = {e["id"]: e for e in fo["expansions"]}

# ---------- expansion -> set_code, series, card_count (from cards) ----------
cards = jload("cardlist_clean.json")
exp_setcode = defaultdict(Counter)
exp_series  = defaultdict(Counter)
exp_cards   = Counter()
for c in cards:
    ex = c.get("expansion")
    exp_cards[ex] += 1
    m = re.search(r"/([A-Za-z]+)(\d+)", c.get("card_number", ""))
    if m:
        exp_setcode[ex][(m.group(1), int(m.group(2)))] += 1
    exp_series[ex][c.get("series", "")] += 1

def dom(counter):
    return counter.most_common(1)[0][0] if counter else None

# ---------- normalization for title matching ----------
PROD_WORDS = ["ブースターパック", "トライアルデッキ＋", "トライアルデッキプラス", "トライアルデッキ",
              "エクストラブースター", "プレミアムブースター", "ブースター", "[TD]", "ＴＤ", "TD",
              "クライマックスブースター", "ミーツ", "Vol.", "vol.", "プラス"]
def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKC", s)
    for w in PROD_WORDS:
        s = s.replace(unicodedata.normalize("NFKC", w), "")
    s = s.lower()
    s = re.sub(r"[\s「」『』【】（）()\[\]〜~・,．\.！!？?＆&'\"’“”―\-—_/:：]", "", s)
    return s

# ---------- products ----------
products = jload("products_jp.json")
for p in products:
    p["norm"] = norm(p["title"])

# index products by normalized title
prod_by_norm = defaultdict(list)
for p in products:
    if p["norm"]:
        prod_by_norm[p["norm"]].append(p)

import difflib
def best_product(ename, era_max_year):
    """Find best archive product for an expansion name, preferring exact-ish, within era window."""
    n = norm(ename)
    if not n: return None, 0.0
    # 1) exact normalized equality
    cands = [p for p in prod_by_norm.get(n, []) if p["year"] <= era_max_year + 1]
    if cands:
        return min(cands, key=lambda p: p["date"]), 1.0
    # 2) containment (expansion name contains product title or vice versa)
    best, bestr = None, 0.0
    for p in products:
        if p["year"] > era_max_year + 1:
            continue
        pn = p["norm"]
        if not pn: continue
        if n == pn:
            r = 1.0
        elif n in pn or pn in n:
            r = 0.92
        else:
            r = difflib.SequenceMatcher(None, n, pn).ratio()
        if r > bestr:
            best, bestr = p, r
    return best, bestr

# ---------- build records ----------
recs = []
for eid, e in exps.items():
    side = str(e.get("side"))
    track = {"-1": "W", "-2": "S"}.get(side, "PR")
    sc = dom(exp_setcode.get(eid))
    set_code = f"{sc[0]}{sc[1]}" if sc else None
    set_num = sc[1] if sc else None
    set_alpha = sc[0] if sc else None
    series = dom(exp_series.get(eid))
    cd = (e.get("create_date") or "")[:10]
    clamped = cd.startswith(CLAMP)
    recs.append({
        "expansion_id": eid, "name": e.get("name"), "set_code": set_code,
        "set_alpha": set_alpha, "set_num": set_num, "track": track,
        "series": series, "cards": exp_cards.get(eid, 0),
        "create_date": cd, "clamped": clamped,
        "release_date": None, "source": None,
        "match_title": None, "match_q": None,
    })

# pass 1: create_date for non-clamped
for r in recs:
    if not r["clamped"] and r["create_date"]:
        r["release_date"] = r["create_date"]; r["source"] = "create_date"

# pass 2: archive title match (refines/overrides; needed for clamped legacy)
match_q = []
for r in recs:
    era_max = 2017 if r["clamped"] else (int(r["create_date"][:4]) if r["create_date"] else 2026)
    p, q = best_product(r["name"], era_max)
    match_q.append((q, r["name"], p["title"] if p else None, p["date"] if p else None))
    if p:
        r["match_title"] = p["title"]; r["match_q"] = round(q, 3)
    if p and q >= 0.90:
        # prefer archive date for clamped sets; for modern, keep create_date unless very close title
        if r["clamped"]:
            r["release_date"] = p["date"]; r["source"] = "archive"
        elif r["source"] is None:
            r["release_date"] = p["date"]; r["source"] = "archive"

# pass 3: monotonic curve per track (alpha+ within track) for still-missing
def to_ord(d):
    y, m, dd = (int(x) for x in d.split("-")); return datetime.date(y, m, dd).toordinal()
def from_ord(o): return datetime.date.fromordinal(o).isoformat()

# group anchors by set_alpha (W01.., S01.., WE.., SE..) since numbering resets per alpha
anchors = defaultdict(list)   # alpha -> sorted [(set_num, ord)]
for r in recs:
    if r["release_date"] and r["set_alpha"] and r["set_num"] is not None:
        anchors[r["set_alpha"]].append((r["set_num"], to_ord(r["release_date"])))
for a in anchors:
    anchors[a] = sorted(anchors[a])

def interp(alpha, num):
    arr = anchors.get(alpha)
    if not arr or len(arr) < 2: return None
    xs = [x for x, _ in arr]; ys = [y for _, y in arr]
    if num <= xs[0]:  # extrapolate low using first segment slope
        if xs[1] == xs[0]: return ys[0]
        slope = (ys[1]-ys[0])/(xs[1]-xs[0]); return int(ys[0]+slope*(num-xs[0]))
    if num >= xs[-1]:
        if xs[-1] == xs[-2]: return ys[-1]
        slope = (ys[-1]-ys[-2])/(xs[-1]-xs[-2]); return int(ys[-1]+slope*(num-xs[-1]))
    i = bisect.bisect_left(xs, num)
    if xs[i] == num: return ys[i]
    x0, x1, y0, y1 = xs[i-1], xs[i], ys[i-1], ys[i]
    return int(y0 + (y1-y0)*(num-x0)/(x1-x0))

for r in recs:
    if not r["release_date"] and r["set_alpha"] and r["set_num"] is not None:
        o = interp(r["set_alpha"], r["set_num"])
        if o: r["release_date"] = from_ord(o); r["source"] = "curve"

# finalize era + year
for r in recs:
    if r["release_date"]:
        r["release_year"] = int(r["release_date"][:4])
        r["era"] = "modern" if r["release_year"] >= CUTOFF_YEAR else "legacy"
    else:
        r["release_year"] = None; r["era"] = "unknown"

with open(os.path.join(D, "set_dates.json"), "w", encoding="utf-8") as f:
    json.dump(recs, f, ensure_ascii=False, indent=0)

# ---------- report ----------
print("=== SET DATING REPORT ===")
src = Counter(r["source"] for r in recs)
print("sets by source:", dict(src), "| total", len(recs))
era = Counter(r["era"] for r in recs)
print("sets by era:", dict(era))
# card-weighted retention
cards_by_era = Counter()
for r in recs: cards_by_era[r["era"]] += r["cards"]
tot = sum(cards_by_era.values())
print("CARDS by era:", dict(cards_by_era), f"| modern share = {100*cards_by_era['modern']//max(tot,1)}%")
# match quality histogram (legacy clamped only)
print("\n--- title-match quality (top unmatched legacy, q<0.90) ---")
low = sorted([m for m in match_q if m[0] < 0.90], reverse=True)[:0]  # placeholder
bad = [m for m in match_q if m[2] is not None and m[0] < 0.90]
for q, nm, pt, pd_ in sorted([m for m in match_q if m[0] < 0.90])[:12]:
    print(f"  q={q:.2f}  exp={nm[:28]!r:30} best_prod={str(pt)[:28]!r}")
# show clamped sets that ended up on curve (no archive match)
curve_legacy = [r for r in recs if r["source"]=="curve"]
print(f"\nsets dated by CURVE (no archive/create_date): {len(curve_legacy)}")
for r in sorted(curve_legacy, key=lambda r:(r['track'],r['set_num'] or 0))[:12]:
    print(f"  {r['set_code']:7} {str(r['name'])[:26]:26} -> {r['release_date']} ({r['era']})")
