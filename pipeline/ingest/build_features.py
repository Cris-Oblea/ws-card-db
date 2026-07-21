# -*- coding: utf-8 -*-
"""
Propagate ERA features (and others) to each (card, ability) -> tidy substrate for
the auto-discovery of formulas (feature-extraction + symbolic regression).

Outputs:
  features_by_card.csv     : 1 row per (Character, non-vanilla ability). Columns =
                             features + targets (card_delta, variant_cost).
  variant_era_cost.csv     : 1 row per (sig_variant x era) with measured cost (median
                             of delta from ISOLATED cards) -> era-aware view + creep.

Era features derived from the EMPIRICAL timeline of JP trigger debuts:
  launch 2008 | treasure/shot 2009 | gate 2012 | standby 2017 | choice 2019 | new ones 2026
  -> trigger_era ordinal 0..5 ; standby_era / choice_era boolean.

Reads: ../cardlist_clean.json (canonical), set_dates.json, costs_by_variant.json. Writes only the 2 CSVs.
"""
import json, os, re, csv, statistics
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
def jload(p): return json.load(open(os.path.join(D, p), encoding="utf-8"))
cards = jload("../cardlist_clean.json")          # canonical lives one level up (consumed by the builders)
sd = {r["expansion_id"]: r for r in jload("set_dates.json")}
vcost = {v["sig"]: v for v in jload("costs_by_variant.json")}

CUT = 2017                       # legacy/modern split year (this research substrate still uses the old binary era)
EXCLUDE_CARDS = {"WS/KDN-246"}   # Kidani gag card (fake 'bushi' trigger) — would corrupt the base-power fit

def base_power(c):
    # Vanilla power: the printed power an ability-less Character would have. card_delta = base - real =
    # the total power spent on abilities (the target the regression tries to explain).
    trig = 1 if c.get("trigger") == ["soul"] else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*trig - 1000*(c["soul"]-1)

# --- sig (replica sig_engine): turn ability text into a generalized signature ---
ZTAB = str.maketrans("０１２３４５６７８９＋－＆／％", "0123456789+-&/%")   # full-width -> ASCII
TRAIT = re.compile(r"《[^》]*》"); NAME1 = re.compile(r"「[^」]*」"); NAME2 = re.compile(r"『[^』]*』")
NUM = re.compile(r"\d+")
def gen(text, keepnum):
    # Replace card-specific traits/names with placeholders so abilities that differ only by their
    # trait/name collapse to ONE signature. keepnum=True keeps the numbers (sig_variant, exact effect);
    # keepnum=False masks them to "#" (sig_family, groups "+1000" with "+2000" as the same shape).
    t = (text or "").translate(ZTAB)
    t = TRAIT.sub("《T》", t); t = NAME1.sub("「N」", t); t = NAME2.sub("『N』", t)
    if not keepnum: t = NUM.sub("#", t)
    return re.sub(r"\s+", " ", t).strip()
def vanilla(t): return (not t) or t.strip() in ("-","ー","－","")   # placeholder/empty ability text

KEYWORDS = {"アラーム":"Alarm","アンコール":"Encore","応援":"Assist","絆":"Bond","助太刀":"Backup",
    "大活躍":"GreatPerformance","集中":"Brainstorm","チェンジ":"Change","記憶":"Memory","経験":"Experience",
    "シフト":"Shift","加速":"Accelerate","共鳴":"Resonance","フォース":"Force","合体":"Fusion",
    "分離":"Sunder","リンク":"Link","継承":"Inheritance"}
def detect_kw(text, markers):
    # Set of game keywords present in the text (助太刀 -> Backup, …). A per-turn marker (ターン) adds a
    # synthetic "UsageLimit" tag. Returned comma-joined so it fits one CSV cell.
    kws = {en for jp,en in KEYWORDS.items() if jp in (text or "")}
    if markers and any("ターン" in (m or "") for m in markers): kws.add("UsageLimit")
    return ",".join(sorted(kws))

def ability_type(markers):
    # Timing class from the JP marker: 永=Continuous, 自=Automatic, 起=Activated; else OTHER.
    m = "".join(markers or [])
    if "【永】" in m: return "CONT"
    if "【自】" in m: return "AUTO"
    if "【起】" in m: return "ACT"
    return "OTHER"

def trigger_era(y):
    # Map a release year to a trigger-generation ordinal (0..5) using the empirical trigger-icon debut
    # years. Higher ordinal = later mechanical era; used as a feature so the regression can see creep.
    return 5 if y>=2026 else 4 if y>=2019 else 3 if y>=2017 else 2 if y>=2012 else 1 if y>=2009 else 0
ERA_LABEL = {0:"launch",1:"treasure-shot",2:"gate",3:"standby",4:"choice",5:"2026+"}

# ---- build per-(card,ability) rows ----
# One CSV row per (Character, non-vanilla ability). iso_by_var_era collects the ISOLATED deltas (from
# single-ability cards) split by era, so we can compare a variant's cost legacy-vs-modern (creep view).
rows = []
iso_by_var_era = defaultdict(lambda: defaultdict(list))   # sig_variant -> era -> [delta]
for c in cards:
    if c.get("type") != "Character" or c.get("excluded") or c.get("power") is None: continue
    if c.get("card_number") in EXCLUDE_CARDS: continue
    rec = sd.get(c.get("expansion"))
    yr = rec["release_year"] if rec else None
    if not yr: continue                                    # undated set -> can't assign an era, skip
    abils = [a for a in c["abilities"] if not vanilla(a.get("text"))]
    if not abils: continue
    bp = base_power(c); delta = bp - c["power"]             # power spent across ALL this card's abilities
    era = "modern" if yr >= CUT else "legacy"
    tera = trigger_era(yr)
    card_trig = "soul" if c.get("trigger") == ["soul"] else "none"
    for i, a in enumerate(abils):
        txt = a.get("text"); mk = a.get("markers") or []
        sv = "".join(mk) + " :: " + gen(txt, True)         # sig_variant: exact effect (numbers kept)
        sf = "".join(mk) + " :: " + gen(txt, False)        # sig_family: effect SHAPE (numbers masked)
        vc = vcost.get(sv, {})                             # join the pre-measured variant cost, if any
        rows.append({
            "card_number": c["card_number"], "series": c.get("series"),
            "set_code": (rec.get("set_code") if rec else None), "release_date": rec.get("release_date") if rec else None,
            "release_year": yr, "era": era, "trigger_era": tera, "trigger_era_label": ERA_LABEL[tera],
            "standby_era": int(yr>=2017), "choice_era": int(yr>=2019), "card_trigger": card_trig,
            "level": c["level"], "cost": c["cost"], "soul": c["soul"],
            "base_power": bp, "real_power": c["power"], "card_delta": delta,
            "n_abilities": len(abils), "isolated": int(len(abils)==1),
            "ab_index": i, "type": ability_type(mk), "markers": "".join(mk),
            "keywords": detect_kw(txt, mk),
            "variant_cost": vc.get("cost"), "variant_conf": vc.get("conf"), "variant_method": vc.get("method"),
            "sig_family": sf, "sig_variant": sv, "text_jp": (txt or "").replace("\n"," ").strip(),
        })
        # only single-ability cards give an ISOLATED measurement (delta == this one ability's cost)
        if len(abils) == 1:
            iso_by_var_era[sv][era].append(delta)

COLS = ["card_number","series","set_code","release_date","release_year","era","trigger_era","trigger_era_label",
        "standby_era","choice_era","card_trigger","level","cost","soul","base_power","real_power","card_delta",
        "n_abilities","isolated","ab_index","type","markers","keywords","variant_cost","variant_conf",
        "variant_method","sig_family","sig_variant","text_jp"]
with open(os.path.join(D,"features_by_card.csv"),"w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)

# ---- variant x era cost view (creep-aware) ----
# For each variant with isolated samples in BOTH eras, compare the legacy vs modern median cost. A
# shift of >=500 flags "creep" for that specific effect (the project's finding: real creep is effect-mix
# shift, not per-package inflation — so few variants here should actually be flagged crept).
def med(xs): return statistics.median(xs)
ve = []
for sv, eras in iso_by_var_era.items():
    L, M = eras.get("legacy",[]), eras.get("modern",[])
    cl = med(L) if L else None; cm = med(M) if M else None
    crept = (cl is not None and cm is not None and abs(cm-cl) >= 500)
    ve.append({"sig_variant": sv, "n_legacy": len(L), "n_modern": len(M),
               "cost_legacy": cl, "cost_modern": cm,
               "shift": (cm-cl) if (cl is not None and cm is not None) else None,
               "crept": int(crept)})
ve.sort(key=lambda r: (r["shift"] is None, r["shift"] if r["shift"] is not None else 0))
with open(os.path.join(D,"variant_era_cost.csv"),"w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=["sig_variant","n_legacy","n_modern","cost_legacy","cost_modern","shift","crept"])
    w.writeheader(); w.writerows(ve)

# ---- report ----
from collections import Counter
print(f"features_by_card.csv : {len(rows)} rows (card x ability)")
print("  by era:", dict(Counter(r['era'] for r in rows)))
print("  by trigger_era:", dict(sorted(Counter(r['trigger_era_label'] for r in rows).items())))
print("  isolated (isolated=1):", sum(r['isolated'] for r in rows))
print("  with variant_cost joined:", sum(1 for r in rows if r['variant_cost'] is not None))
comparable = [r for r in ve if r['n_legacy']>=5 and r['n_modern']>=5]
crept = [r for r in comparable if r['crept']]
print(f"\nvariant_era_cost.csv : {len(ve)} variants; comparable(nL>=5,nM>=5)={len(comparable)}; CREPT={len(crept)}")
for r in sorted(crept, key=lambda r:r['shift'])[:8]:
    print(f"  shift={int(r['shift']):+5} {int(r['cost_legacy'])}->{int(r['cost_modern'])} (nL={r['n_legacy']},nM={r['n_modern']}) {r['sig_variant'][:58]}")
