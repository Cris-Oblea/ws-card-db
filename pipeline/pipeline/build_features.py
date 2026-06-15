# -*- coding: utf-8 -*-
"""
Propaga features de ERA (y demas) a cada (carta, habilidad) -> sustrato tidy para
el auto-descubrimiento de formulas (feature-extraction + symbolic regression).

Outputs:
  features_by_card.csv     : 1 fila por (Character, habilidad no-vanilla). Columnas =
                             features + targets (card_delta, variant_cost).
  variant_era_cost.csv     : 1 fila por (sig_variant x era) con costo medido (mediana
                             de delta de cartas AISLADAS) -> vista era-aware + creep.

Features de era derivadas del timeline EMPIRICO de debut de triggers JP:
  launch 2008 | treasure/shot 2009 | gate 2012 | standby 2017 | choice 2019 | nuevos 2026
  -> trigger_era ordinal 0..5 ; standby_era / choice_era boolean.

Reads: cardlist_clean.json, set_dates.json, costs_by_variant.json. Solo escribe los 2 CSV.
"""
import json, os, re, csv, statistics
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
def jload(p): return json.load(open(os.path.join(D, p), encoding="utf-8"))
cards = jload("cardlist_clean.json")
sd = {r["expansion_id"]: r for r in jload("set_dates.json")}
vcost = {v["sig"]: v for v in jload("costs_by_variant.json")}

CUT = 2017
EXCLUDE_CARDS = {"WS/KDN-246"}   # carta gag de Kidani (trigger 'bushi' falso)

def base_power(c):
    trig = 1 if c.get("trigger") == ["soul"] else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*trig - 1000*(c["soul"]-1)

# --- sig (replica sig_engine) ---
ZTAB = str.maketrans("０１２３４５６７８９＋－＆／％", "0123456789+-&/%")
TRAIT = re.compile(r"《[^》]*》"); NAME1 = re.compile(r"「[^」]*」"); NAME2 = re.compile(r"『[^』]*』")
NUM = re.compile(r"\d+")
def gen(text, keepnum):
    t = (text or "").translate(ZTAB)
    t = TRAIT.sub("《T》", t); t = NAME1.sub("「N」", t); t = NAME2.sub("『N』", t)
    if not keepnum: t = NUM.sub("#", t)
    return re.sub(r"\s+", " ", t).strip()
def vanilla(t): return (not t) or t.strip() in ("-","ー","－","")

KEYWORDS = {"アラーム":"Alarm","アンコール":"Encore","応援":"Assist","絆":"Bond","助太刀":"Backup",
    "大活躍":"GreatPerformance","集中":"Brainstorm","チェンジ":"Change","記憶":"Memory","経験":"Experience",
    "シフト":"Shift","加速":"Accelerate","共鳴":"Resonance","フォース":"Force","合体":"Fusion",
    "分離":"Sunder","リンク":"Link","継承":"Inheritance"}
def detect_kw(text, markers):
    kws = {en for jp,en in KEYWORDS.items() if jp in (text or "")}
    if markers and any("ターン" in (m or "") for m in markers): kws.add("UsageLimit")
    return ",".join(sorted(kws))

def ability_type(markers):
    m = "".join(markers or [])
    if "【永】" in m: return "CONT"
    if "【自】" in m: return "AUTO"
    if "【起】" in m: return "ACT"
    return "OTHER"

def trigger_era(y):
    # debut empirico de triggers -> ordinal de mecanica-era
    return 5 if y>=2026 else 4 if y>=2019 else 3 if y>=2017 else 2 if y>=2012 else 1 if y>=2009 else 0
ERA_LABEL = {0:"launch",1:"treasure-shot",2:"gate",3:"standby",4:"choice",5:"2026+"}

# ---- build per-(card,ability) rows ----
rows = []
iso_by_var_era = defaultdict(lambda: defaultdict(list))   # sig_variant -> era -> [delta]
for c in cards:
    if c.get("type") != "Character" or c.get("excluded") or c.get("power") is None: continue
    if c.get("card_number") in EXCLUDE_CARDS: continue
    rec = sd.get(c.get("expansion"))
    yr = rec["release_year"] if rec else None
    if not yr: continue
    abils = [a for a in c["abilities"] if not vanilla(a.get("text"))]
    if not abils: continue
    bp = base_power(c); delta = bp - c["power"]
    era = "modern" if yr >= CUT else "legacy"
    tera = trigger_era(yr)
    card_trig = "soul" if c.get("trigger") == ["soul"] else "none"
    for i, a in enumerate(abils):
        txt = a.get("text"); mk = a.get("markers") or []
        sv = "".join(mk) + " :: " + gen(txt, True)
        sf = "".join(mk) + " :: " + gen(txt, False)
        vc = vcost.get(sv, {})
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
        if len(abils) == 1:
            iso_by_var_era[sv][era].append(delta)

COLS = ["card_number","series","set_code","release_date","release_year","era","trigger_era","trigger_era_label",
        "standby_era","choice_era","card_trigger","level","cost","soul","base_power","real_power","card_delta",
        "n_abilities","isolated","ab_index","type","markers","keywords","variant_cost","variant_conf",
        "variant_method","sig_family","sig_variant","text_jp"]
with open(os.path.join(D,"features_by_card.csv"),"w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)

# ---- variant x era cost view (creep-aware) ----
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
print(f"features_by_card.csv : {len(rows)} filas (carta x habilidad)")
print("  por era:", dict(Counter(r['era'] for r in rows)))
print("  por trigger_era:", dict(sorted(Counter(r['trigger_era_label'] for r in rows).items())))
print("  aisladas (isolated=1):", sum(r['isolated'] for r in rows))
print("  con variant_cost joineado:", sum(1 for r in rows if r['variant_cost'] is not None))
comparable = [r for r in ve if r['n_legacy']>=5 and r['n_modern']>=5]
crept = [r for r in comparable if r['crept']]
print(f"\nvariant_era_cost.csv : {len(ve)} variantes; comparables(nL>=5,nM>=5)={len(comparable)}; CREPEARON={len(crept)}")
for r in sorted(crept, key=lambda r:r['shift'])[:8]:
    print(f"  shift={int(r['shift']):+5} {int(r['cost_legacy'])}->{int(r['cost_modern'])} (nL={r['n_legacy']},nM={r['n_modern']}) {r['sig_variant'][:58]}")
