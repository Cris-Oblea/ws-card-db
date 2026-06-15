# build_db.py — builds ws.sqlite for the query app.
#
# Mirrors the validated cost model of build_official_list.py (measured -> residual ->
# estimated) but, instead of an aggregated Excel, it emits a per-CARD / per-ABILITY SQLite
# so the app can answer: for THIS card, what does each effect cost in power?
#
# Output: ../docs/ws.sqlite   (the static site loads it in the browser via sql.js)
#
# NOTE: the cost logic is intentionally kept identical to build_official_list.py. The model is
# WIP; when it improves, re-run this to regenerate the DB. (TODO: unify both into cost_model.py.)
import json, os, re, sqlite3, collections, statistics as st, unicodedata

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "..", "docs", "ws.sqlite")

# ---------------- shared helpers (verbatim from build_official_list.py) ----------------
def _nk(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
def pb(c):
    t = 1 if "soul" in (c.get("trigger") or []) else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*t - 1000*(c["soul"]-1)
def ra(c):
    return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","ｰ","")]
def base_num(cn):
    return re.sub(r"(\d)[A-Za-z]+$", r"\1", cn or "")
ZT = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")
TRAIT = re.compile(r"《[^》]*》"); NAME = re.compile(r"「[^」]*」")
def gen(t):
    t = t.translate(ZT); t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    t = re.sub(r"、?《T》(?:[かや・/／、]《T》)+", "《T》", t)
    return re.sub(r"\s+", " ", t).strip()
def r500(x): return int(round(x/500.0)*500)
def mode500(xs): return collections.Counter(r500(x) for x in xs).most_common(1)[0][0]

KW = {"助太刀":"Backup","応援":"Assist","集中":"Brainstorm","アンコール":"Encore","経験":"Experience",
      "記憶":"Memory","絆":"Bond","チェンジ":"Change","加速":"Accelerate","共鳴":"Resonance",
      "シフト":"Shift","大活躍":"Great Performance","フォース":"Force","ヒール":"Heal","バウンス":"Bounce"}
FAMPAT = [
  ("Burn", r"相手に\d+ダメージ"), ("Heal", r"自分のクロック[^。]{0,20}(控え室|ストック|手札|思い出)に置"),
  ("Clock Kick", r"相手のキャラ[^。]{0,20}(クロック置場|クロックに)置"),
  ("Bounce", r"相手のキャラ[^。]{0,12}手札に戻"), ("Return to Deck", r"相手の(控え室|キャラ)[^。]{0,20}山札に(戻|加え)"),
  ("Reverse Opp", r"相手のキャラ[^。]{0,12}【リバース】"), ("Opp Disrupt", r"相手の(手札|ストック|山札|思い出|レベル置場|クロック)"),
  ("Salvage", r"自分の(控え室|思い出)[^。]{0,22}手札に(戻す|加える)"), ("Search", r"山札[^。]{0,14}見[てる][^。]{0,28}(手札|加える)"),
  ("Look Deck", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見"), ("Comeback", r"(控え室|山札)[^。]{0,22}キャラ[^。]{0,14}舞台に置"),
  ("Stock Gen", r"(山札の上|デッキトップ|山札の上から)[^。]{0,12}ストック置場に置"), ("Draw", r"引く"),
  ("Add to Hand", r"手札に(加える|加え|戻す)"), ("Power Pump (board)", r"あなたの[^。]{0,16}キャラすべてに[^。]{0,8}パワーを[＋+]"),
  ("Power Pump (self)", r"このカードのパワーを[＋+]"), ("Power Pump", r"キャラ[^。]{0,10}パワーを[＋+]"),
  ("Power Debuff", r"パワーを[－\-]"), ("Soul", r"ソウルを[＋+\-－]"), ("Level", r"レベルを[＋+\-－]"),
  ("Grant Ability", r"』を与える|の能力を得"), ("Mill (self)", r"山札の上から\d+枚を[^。]{0,8}控え室"),
  ("Move", r"(前列|後列|別の枠|横の枠|の枠)に[^。]{0,6}(動かす|置く|移動)"), ("Stand/Rest", r"【スタンド】|【レスト】"),
  ("Stock Boost", r"ストック置場に置"), ("Choice", r"次の効果から|から\d+つを選"),
  ("Early Play", r"レベル\d+以下[^。]{0,12}手札からプレイ|レベルを参照しない"),
  ("Cannot Attack", r"アタックできない|サイドアタックできない"), ("Restriction", r"できない|選べない|受けない"),
  ("Card Select", r"\d+枚(まで)?選"),
]
def family(text):
    for k, v in KW.items():
        if k in text: return v
    for name, pat in FAMPAT:
        if re.search(pat, text): return name
    return "Other"
def ability_type(markers):
    m = "".join(markers or "")
    if "永" in m: return "CONT"
    if "自" in m: return "AUTO"
    if "起" in m: return "ACT"
    return "OTHER"

# ---------------- load ----------------
clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
en_cards = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))
era = json.load(open(os.path.join(D, "card_era.json"), encoding="utf-8"))

# --- de-duplicate alt-art / rarity parallels (the JP list is full of them). A physical card =
# same base number + name + stats + EXACT effects. Cards that share a number/name but DIFFER in
# effect keep their own row. Keep the plain base printing as the representative. ---
def _ckey(c):
    return (base_num(c.get("card_number", "")), _nk(c.get("name")), c.get("power"), c.get("level"),
            c.get("cost"), c.get("soul"), tuple((a.get("type"), _nk(a.get("text"))) for a in ra(c)))
BASE_RARE = {"RR", "R", "U", "C", "CR", "CC", "TD"}           # base rarities; anything else = alt-art
def _better(cand, cur):
    cb, ub = cand.get("rare") in BASE_RARE, cur.get("rare") in BASE_RARE
    if cb != ub: return cb                                    # a base-rarity printing wins
    b = base_num(cand.get("card_number", ""))
    pc, pu = cand.get("card_number") == b, cur.get("card_number") == b
    if pc != pu: return pc                                    # else the plain base number
    return len(cand.get("card_number", "")) < len(cur.get("card_number", ""))  # else the shortest
_dd = {}
for c in clean:
    if c.get("excluded"): continue
    k = _ckey(c)
    if k not in _dd or _better(c, _dd[k]): _dd[k] = c
_before = len(clean); clean = list(_dd.values())
print(f"alt-art de-dup: {_before} -> {len(clean)} distinct JP cards (removed {_before - len(clean)})")
def _load(fn):
    try: return json.load(open(os.path.join(D, fn), encoding="utf-8"))
    except FileNotFoundError: return {}
# Complete per-ability JP->EN translations (agent-made, official style), keyed by full JP text
# "【marker】 text". variant_tr_full.json (~15.9k, the complete set) takes precedence over the
# older partial translation_cache.json. Both keyed by normalized full text.
_cache = _load("translation_cache.json")
_vtf = _load("variant_tr_full.json")
CACHE = {}
for k, v in {**_cache, **_vtf}.items():
    CACHE[_nk(k)] = v
print(f"cards: {len(clean)} | en: {len(en_cards)} | translations: {len(CACHE)} (cache {len(_cache)} + full {len(_vtf)})")

# --- STRICT EN matching: same publisher + SET + number (e.g. ("DAL","W131",2)).
# The old official_en._key dropped the SET, so DAL/W131-002, DAL/W79-002, DAL/WE33-002 all
# collapsed to ("DAL",2) and cross-contaminated names/effects. We only assign EN data when the
# EXACT same card exists in the EN list; otherwise we leave it blank (better no EN than wrong EN).
def strict_key(code):
    m = re.match(r"([^/]+)/([A-Za-z]+\d+)-E?(\d+)", code or "")
    return (m.group(1).upper(), m.group(2).upper(), int(m.group(3))) if m else None
def _ra_en(e):
    return [a for a in (e.get("ability") or []) if a and a.strip()]
EN_BY = {}
for e in en_cards:
    kk = strict_key(e.get("code", ""))
    if kk: EN_BY.setdefault(kk, e)

# --- traits JP->EN dictionary: align clean.traits[i] <-> EN attributes[i] on exact-matched
#     cards (same count); the most common EN per JP trait wins (robust to occasional misorder). ---
_tp = collections.defaultdict(collections.Counter)
for c in clean:
    ec = EN_BY.get(strict_key(c["card_number"]))
    if not ec: continue
    jt, et = c.get("traits") or [], ec.get("attributes") or []
    if len(jt) == len(et):
        for a, b in zip(jt, et):
            if a and b: _tp[a][b] += 1
TRAIT_EN = {k: v.most_common(1)[0][0] for k, v in _tp.items()}

# --- neo-standard: neo_titles.json maps a neo-standard NAME (JP) to its series codes.
#     The franchise's ENGLISH name lives in the EN 'expansion' field -> gather them per neo so
#     the Title filter matches both JP ("デート・ア・ライブ") and EN ("Date A Live"). ---
neo_data = json.load(open(os.path.join(D, "pipeline", "neo_titles.json"), encoding="utf-8"))
NAME2NEO = {nt["name"]: nt for nt in neo_data}
CODE2NEO = {code: nt for nt in neo_data for code in nt.get("codes", [])}
NEO_EXP = collections.defaultdict(collections.Counter)   # neo JP name -> Counter(expansion -> #cards)
for e in en_cards:
    nt = CODE2NEO.get((e.get("code") or "").split("/")[0])
    if nt and e.get("expansion"): NEO_EXP[nt["name"]][e["expansion"]] += 1
# one clean EN franchise name per neo: the most common expansion BY CARD COUNT, stripped of
# vol/edition noise. Each neo is a SEPARATE standard (Fate, Fate/Grand Order, Apocrypha, Prisma).
def _clean_exp(s):
    s = re.sub(r"\s*Vol\.\s*\d+", "", s)
    s = re.sub(r"^\[TD\]\s*|^(Trial Deck|Booster Pack|Extra Booster)\s+", "", s)
    s = re.sub(r"\s*【[^】]*】|\s*（[^）]*）", "", s)
    return "" if s.startswith("PR Card") else s.strip()
NEO_ENNAME = {}
for nm, exps in NEO_EXP.items():
    cnt = collections.Counter()
    for raw, k in exps.items():
        ce = _clean_exp(raw)
        if ce: cnt[ce] += k
    if cnt: NEO_ENNAME[nm] = cnt.most_common(1)[0][0]
NEO_EN_OFFICIAL = _load("neo_en.json")   # curated OFFICIAL EN franchise titles (all 164 neo names)
def _has_cjk(s):
    return any("぀" <= ch <= "ヿ" or "㐀" <= ch <= "鿿" or "＀" <= ch <= "￯" for ch in (s or ""))
def neo_en(nm):   # EN title: curated official franchise name first; else Latin-as-is; else from set
    return NEO_EN_OFFICIAL.get(nm) or (nm if (nm and not _has_cjk(nm)) else NEO_ENNAME.get(nm, ""))

# --- per-series SIDE corrections (source data left these as 'Other'); user-provided, per code. ---
_W, _S, _O = "Weiss", "Schwarz", "Other"
SIDE_FIX = {
    "G86": _S, "GIM": _W, "GAS": _W, "GAW": _S, "GBB": _S, "GBC": _S, "GBD": _S, "GBL": _S,
    "GBY": _W, "GC3": _S, "GDC": _W, "GDR": _S, "GDS": _W, "GDY": _W, "GEM": _W, "GFQ": _S,
    "GGA": _S, "GGG": _S, "GGH": _S, "GGU": _S, "GHH": _S, "GHM": _W, "GID": _W, "GIY": _S,
    "GKB": _S, "GKL": _S, "GKM": _S, "GLT": _W, "GMF": _S, "GMM": _W, "GMR": _S, "GMS": _W,
    "GNH": _W, "GNM": _S, "GNS": _S, "GNY": _W, "GOI": _W, "GOK": _W, "GOM": _W, "GOS": _W,
    "GRK": _W,
    "GSB": _S, "GSC": _S, "GSD": _S, "GSK": _S, "GSO": _S, "GSP": _W, "GSR": _W, "GSS": _W,
    "GTD": _W, "GYF": _S,
}
# per-card overrides (side and/or color) for individual source-data glitches.
CARD_FIX = {
    "IAS/S93-E01": {"side": _S}, "IMC/W115-E01": {"side": _W}, "IMS/S93-E01": {"side": _S},
    "ISC/S110-E01": {"side": _S}, "WS/WSPR-P26": {"side": _W}, "WS/WSPR-P27": {"side": _W},
    "VA/WE30-55": {"color": "red"},
}

# ---------------- cost model: measured -> residual -> estimated (Characters only) ----------
variant_occ = collections.defaultdict(list)
iso = collections.defaultdict(lambda: {"m": [], "l": []})
variant_text = {}
char_cards = []
for c in clean:
    if c["type"] != "Character" or c["excluded"]: continue
    if c["power"] is None or c["level"] is None or c["cost"] is None or c["soul"] is None: continue
    ab = ra(c)
    if not ab: continue
    sigs = []
    for i, a in enumerate(ab):
        mk = "".join(a.get("markers") or [])
        sig = mk + " :: " + gen(a.get("text", ""))
        sigs.append(sig)
        variant_occ[sig].append((c["card_number"], i, mk, a.get("text", "")))
        variant_text.setdefault(sig, (mk, gen(a.get("text", ""))))
    delta = pb(c) - c["power"]
    e = era.get(c["card_number"])
    char_cards.append((c["card_number"], delta, sigs, e))
    if len(ab) == 1:
        (iso[sigs[0]]["m"] if e == "modern" else iso[sigs[0]]["l"]).append(delta)

ALLV = set(variant_occ)
cost = {}; method = {}; nsamp = {}; rng = {}
for sig, d in iso.items():
    use = d["m"] if len(d["m"]) >= 2 else (d["m"] + d["l"])
    if not use: continue
    if not d["m"] and len(d["l"]) == 1: continue
    cost[sig] = mode500(use); method[sig] = "measured"; nsamp[sig] = len(use); rng[sig] = (min(use), max(use))
neg_fams = {family(variant_text[s][1]) for s, c in cost.items() if c < 0}
multi = [(cn, dl, sg, e) for (cn, dl, sg, e) in char_cards if len(sg) > 1]
for _ in range(10):
    res = collections.defaultdict(list)
    for cn, dl, sg, e in multi:
        unk = [s for s in sg if s not in cost]
        if len(unk) == 1:
            res[unk[0]].append(dl - sum(cost[s] for s in sg if s in cost))
    new = 0
    for sig, samples in res.items():
        if sig in cost: continue
        val = mode500(samples)
        if val < 0 and family(variant_text[sig][1]) not in neg_fams: continue
        cost[sig] = val; method[sig] = "residual"; nsamp[sig] = len(samples); rng[sig] = (min(samples), max(samples)); new += 1
    if new == 0: break
errs = [abs(dl - sum(cost[s] for s in sg)) for cn, dl, sg, e in multi if all(s in cost for s in sg)]
if errs:
    print(f"validation |err|<=500 on {sum(1 for x in errs if x<=500)/len(errs)*100:.0f}% (n={len(errs)})")
fam_known = collections.defaultdict(list)
for sig, cst in cost.items(): fam_known[family(variant_text[sig][1])].append(cst)
fam_med = {f: r500(st.median(v)) for f, v in fam_known.items()}
for sig in ALLV:
    if sig in cost: continue
    cost[sig] = fam_med.get(family(variant_text[sig][1]), 500); method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)
CONF = {"measured": "HIGH", "residual": "MEDIUM", "estimated": "LOW"}

def ab_cost(card_number, markers, text):
    """cost/method/family for one ability instance (None if not a measurable Character ability)."""
    sig = "".join(markers or "") + " :: " + gen(text or "")
    if sig in cost:
        return cost[sig], method[sig], CONF[method[sig]], family(variant_text.get(sig, ("", gen(text or "")))[1])
    return None, None, None, family(gen(text or ""))

# ---------------- build SQLite ----------------
if os.path.exists(OUT): os.remove(OUT)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
db = sqlite3.connect(OUT)
db.executescript("""
PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
CREATE TABLE cards (
  card_number TEXT PRIMARY KEY, base_number TEXT, series TEXT,
  name TEXT, name_en TEXT, name_kana TEXT, neo_titles TEXT,
  type TEXT, color TEXT, level INTEGER, cost INTEGER, power INTEGER, soul INTEGER,
  trigger TEXT, traits TEXT, rare TEXT, side TEXT, expansion INTEGER, parallel INTEGER, era TEXT,
  power_base INTEGER, budget INTEGER, model_cost_total INTEGER, real_delta INTEGER,
  picture TEXT, image_en TEXT, traits_en TEXT, title_search TEXT, en_exclusive INTEGER
);
CREATE TABLE abilities (
  card_number TEXT, idx INTEGER, ability_type TEXT, family TEXT,
  jp_text TEXT, en_text TEXT, power_cost INTEGER, method TEXT, confidence TEXT,
  PRIMARY KEY (card_number, idx)
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
""")

def join(v):
    if not v: return ""
    return " / ".join(v) if isinstance(v, (list, tuple)) else str(v)

crows, arows = [], []
for c in clean:
    if c.get("excluded"): continue            # keep only valid printings in the queryable DB
    cn = c["card_number"]; ec = EN_BY.get(strict_key(cn))   # exact EN card (same set+number) or None
    en_abs = _ra_en(ec) if ec else []
    is_char = c["type"] == "Character" and None not in (c.get("level"), c.get("cost"), c.get("soul"), c.get("power"))
    power_base = pb(c) if is_char else None
    budget = (power_base - 500) if power_base is not None else None
    abs_ = ra(c)
    model_total = 0; have_cost = False
    ab_buf = []
    align = ec is not None and len(en_abs) == len(abs_)   # same card + same ability count -> safe positional EN
    for i, a in enumerate(abs_):
        pc, meth, conf, fam = ab_cost(cn, a.get("markers"), a.get("text"))
        en = en_abs[i] if align else CACHE.get(_nk((("".join(a.get("markers") or "")) + " " + (a.get("text") or "")).strip()), "")
        if pc is not None: model_total += pc; have_cost = True
        ab_buf.append((cn, i, ability_type(a.get("markers")), fam, a.get("text") or "", en, pc, meth, conf))
    real_delta = (power_base - c["power"]) if power_base is not None else None
    name_en = ec.get("name") if ec else None
    # traits in EN (translated via the dictionary) + a hidden title-search blob (JP + EN franchise)
    traits_en = " / ".join([x for x in (TRAIT_EN.get(t) for t in (c.get("traits") or [])) if x])
    neos = c.get("neo_titles") or []
    ts = list(neos)
    for nm in neos:
        nt = NAME2NEO.get(nm)
        if nt:
            ts.append(nt.get("name_kana", "")); ts += nt.get("codes", []); ts.append(neo_en(nm))
    title_search = " ".join(t for t in ts if t).lower()
    fix = CARD_FIX.get(cn, {})                                             # per-card overrides win
    side = fix.get("side") or SIDE_FIX.get((c.get("series") or "").upper(), c.get("side"))
    color = fix.get("color", c.get("color"))
    crows.append((
        cn, base_num(cn), c.get("series"), c.get("name"), name_en, c.get("name_kana"),
        join(c.get("neo_titles")), c.get("type"), color, c.get("level"), c.get("cost"),
        c.get("power"), c.get("soul"), join(c.get("trigger")), join(c.get("traits")),
        c.get("rare"), side, c.get("expansion"), c.get("parallel"), era.get(cn),
        power_base, budget, (model_total if have_cost else None), real_delta,
        c.get("picture"), (ec.get("image") if ec else None), traits_en, title_search, 0,
    ))
    arows.extend(ab_buf)

# --- English-EXCLUSIVE sets (WX/SX set codes): present ONLY in the EN cardlist, absent from the
# JP source. Add them as their OWN English titles (en_exclusive=1) — they NEVER merge with the JP
# title (CCS-JP and CCS-EN are separate; AOT-JP and AOT-EN are separate). Per-ability power cost
# stays NULL (the cost model is measured from JP data; computing it the same way for these only is
# a future task). EX_TITLE = the English title per EN-exclusive series ("(EN)" where a JP one exists. ---
EX_TITLE = {
    "ATLA": "Avatar: The Last Airbender", "AT": "Adventure Time", "BNJ": "Batman Ninja",
    "EIS": "The Eminence in Shadow", "GGST": "Guilty Gear -Strive-", "MOB": "Mob Psycho 100",
    "RWBY": "RWBY", "SDS": "The Seven Deadly Sins",
    "AOT": "Attack on Titan (EN)", "CCS": "Cardcaptor Sakura (EN)",   # overlap with a JP title
}
EX = re.compile(r"^([^/]+)/(?:WX|SX)\d+-", re.I)
def _en_type(txt):
    if "【CONT】" in txt or "【CONTINUOUS】" in txt: return "CONT"
    if "【AUTO】" in txt: return "AUTO"
    if "【ACT】" in txt: return "ACT"
    return "OTHER"
def _i(x):
    try: return int(x)
    except (TypeError, ValueError): return None      # EN cardlist stores stats as strings ("" for n/a)
# --- cost model for EN-exclusive cards: SAME methodology as JP, applied over the ENGLISH text ---
def gen_en(t):   # generalize EN ability text (trait/name -> placeholder, KEEP numbers), like JP gen()
    t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    t = re.sub(r"、?《T》(?:[ /／・]《T》)+", "《T》", t)
    return re.sub(r"\s+", " ", t).strip().lower()
# (a) raw JP costs per EN-sig (keep ALL samples to combine with EN measurements -> robust mode)
xs = collections.defaultdict(list)
for r in arows:                                  # arows so far = JP abilities only
    if r[5] and r[6] is not None: xs[gen_en(r[5])].append(r[6])
def en_family(t):   # ordered, precise EN family detection (CX combo / burn / clock-kick BEFORE heal)
    tl = re.sub(r"\s+", " ", t.lower())
    if "cxcombo" in tl.replace(" ", "").replace("【", "").replace("】", "") or "cx combo" in tl: return "CX Combo"
    if re.search(r"deal \d+ damage to your opponent", tl): return "Burn"
    if "into your opponent's clock" in tl or "into their clock" in tl: return "Clock Kick"  # field disruption
    if re.search(r"(top card of |a card from )?your clock[^.]{0,40}your waiting room", tl): return "Heal"  # OWN clock only
    for fam, kw in (("Backup", "backup"), ("Assist", "assist"), ("Brainstorm", "brainstorm"),
                    ("Encore", "encore"), ("Experience", "experience"), ("Memory", "memory")):
        if kw in tl: return fam
    if re.search(r"return[^.]{0,40}opponent[^.]{0,20}(character|hand)", tl): return "Bounce"
    if re.search(r"(look at|reveal|search)[^.]{0,40}deck", tl): return "Search"
    if "your waiting room" in tl and " hand" in tl: return "Salvage"
    if "draw" in tl: return "Draw"
    if re.search(r"[+\-]\d+ power", tl): return "Power Pump"
    if re.search(r"[+\-]\d+ soul", tl): return "Soul"
    return "Other"
# (b) collect EN-exclusive cards
ex_cards = []; seen_ex = set(); ex_series = set()
for e in en_cards:
    code = e.get("code") or ""
    if not EX.match(code) or code in seen_ex: continue
    seen_ex.add(code); series = code.split("/")[0]; ex_series.add(series)
    lv, co, pw, so = _i(e.get("level")), _i(e.get("cost")), _i(e.get("power")), _i(e.get("soul"))
    is_char = e.get("type") == "Character" and None not in (lv, co, pw, so)
    trig = [str(x).lower() for x in (e.get("trigger") or [])]
    pbase = (3000 + 2500*lv + 1500*co - 1000*(1 if "soul" in trig else 0) - 1000*(so-1)) if is_char else None
    abils = [a for a in (e.get("ability") or []) if a and a.strip()]
    ex_cards.append({"e": e, "code": code, "series": series, "lv": lv, "co": co, "pw": pw, "so": so,
                     "trig": trig, "attrs": e.get("attributes") or [], "pbase": pbase,
                     "delta": (pbase - pw) if pbase is not None else None, "is_char": is_char,
                     "rare": e.get("rarity"),
                     "sigs": [(i, _en_type(a), a, gen_en(a)) for i, a in enumerate(abils)]})
# de-dup EN-exclusive alt-art parallels too (same rule: base-rarity printing represents the card)
_exdd = {}
for c in ex_cards:
    k = (base_num(c["code"]), _nk(c["e"].get("name")), c["pw"], c["lv"], c["co"], c["so"],
         tuple((at, _nk(tx)) for (_, at, tx, _) in c["sigs"]))
    cur = _exdd.get(k)
    if cur is None or (c["rare"] in BASE_RARE and cur["rare"] not in BASE_RARE): _exdd[k] = c
ex_cards = list(_exdd.values())
# (c) base cost per EN-sig = MODE of all samples (JP cross + EN single-ability deltas). The mode
#     (not one card's delta) avoids outliers and lets the many JP samples dominate -> robust.
en_direct = collections.defaultdict(list)
for c in ex_cards:
    if c["is_char"] and len(c["sigs"]) == 1 and c["delta"] is not None:
        en_direct[c["sigs"][0][3]].append(c["delta"])
encost = {}; enmethod = {}
for s in set(xs) | set(en_direct):
    encost[s] = mode500(xs.get(s, []) + en_direct.get(s, []))
    enmethod[s] = "measured" if s in en_direct else "matched"
# (d) residual on multi-ability EN cards (fill the one unknown from delta - sum(known))
multi = [c for c in ex_cards if c["is_char"] and len(c["sigs"]) > 1 and c["delta"] is not None]
for _ in range(10):
    res = collections.defaultdict(list); new = 0
    for c in multi:
        unk = [s for (_, _, _, s) in c["sigs"] if s not in encost]
        if len(unk) == 1:
            res[unk[0]].append(c["delta"] - sum(encost[s] for (_, _, _, s) in c["sigs"] if s in encost))
    for s, vals in res.items():
        if s in encost: continue
        encost[s] = mode500(vals); enmethod[s] = "residual"; new += 1
    if new == 0: break
# (e) estimate the rest by family median (reuse the JP family medians) -- Characters only
for c in ex_cards:
    if not c["is_char"]: continue
    for (_, _, txt, s) in c["sigs"]:
        if s not in encost: encost[s] = fam_med.get(en_family(txt), 500); enmethod[s] = "estimated"
# (f) CX-combo / hard-gate floor: such an ability is worth >= 500 (you pay by assembling the combo)
for c in ex_cards:
    if not c["is_char"]: continue
    for (_, _, txt, s) in c["sigs"]:
        if en_family(txt) == "CX Combo" and encost.get(s, 0) < 500:
            encost[s] = 500; enmethod[s] = "estimated"
ENCONF = {"measured": "HIGH", "matched": "MEDIUM", "residual": "MEDIUM", "estimated": "LOW"}
# (f) emit rows
for c in ex_cards:
    e = c["e"]; code = c["code"]; title = EX_TITLE.get(c["series"], c["series"])
    model_total = 0; have = False; ab_buf = []
    for (i, atype, txt, s) in c["sigs"]:
        pc = encost.get(s) if c["is_char"] else None         # cost model is Characters only
        meth = enmethod.get(s) if pc is not None else None
        if pc is not None: model_total += pc; have = True
        ab_buf.append((code, i, atype, en_family(txt), "", txt, pc, meth, ENCONF.get(meth)))
    crows.append((
        code, base_num(code), c["series"], e.get("name"), e.get("name"), "", title, e.get("type"),
        (e.get("color") or "").lower(), c["lv"], c["co"], c["pw"], c["so"], " / ".join(c["trig"]),
        " / ".join(c["attrs"]), e.get("rarity"), {"W": "Weiss", "S": "Schwarz"}.get(e.get("side"), e.get("side")),
        None, 0, None, c["pbase"], (c["pbase"] - 500 if c["pbase"] is not None else None),
        (model_total if have else None), c["delta"], "", e.get("image"), " / ".join(c["attrs"]), title.lower(), 1,
    ))
    arows.extend(ab_buf)
print(f"English-exclusive cards added (WX/SX): {len(ex_cards)}")

db.executemany("INSERT INTO cards VALUES (%s)" % ",".join("?"*29), crows)
db.executemany("INSERT INTO abilities VALUES (%s)" % ",".join("?"*9), arows)
db.executescript("""
CREATE INDEX i_color ON cards(color);
CREATE INDEX i_level ON cards(level);
CREATE INDEX i_cost  ON cards(cost);
CREATE INDEX i_soul  ON cards(soul);
CREATE INDEX i_type  ON cards(type);
CREATE INDEX i_side  ON cards(side);
CREATE INDEX i_series ON cards(series);
CREATE INDEX i_ab_card ON abilities(card_number);
CREATE INDEX i_ab_cost ON abilities(power_cost);
CREATE INDEX i_ab_fam ON abilities(family);
""")
meta = [
    ("schema", "1"),
    ("cards", str(len(crows))),
    ("abilities", str(len(arows))),
    ("validation", (f"{sum(1 for x in errs if x<=500)/len(errs)*100:.0f}% |err|<=500 (n={len(errs)})" if errs else "n/a")),
    ("note", "Power cost per ability is WIP. Confidence: HIGH=measured, MEDIUM=residual, LOW=estimated."),
]
db.executemany("INSERT INTO meta VALUES (?,?)", meta)
# neo-standards (official deck-construction groups): each is a SEPARATE standard with its own
# set codes. The app uses this for an exact title filter (pick a neo -> match its codes only).
db.execute("CREATE TABLE neos (jp_name TEXT, en_name TEXT, kana TEXT, codes TEXT, en_only INTEGER)")
neo_rows = [(nt["name"], neo_en(nt["name"]), nt.get("name_kana", ""), " ".join(nt.get("codes", [])), 0)
            for nt in neo_data]
# EN-exclusive titles (one per EN-exclusive series). codes = the series.
#  en_only=1: the English title is ONLY the exclusive cards (CCS-EN: the JP CCS cards differ).
#  en_only=2: the English title ALSO includes the JP cards (AOT: AOT1/AOT2 are identical in EN+JP,
#             so the EN title = JP cards + exclusive; the JP title stays just AOT1/AOT2).
EX_MERGE_JP = {"AOT"}
neo_rows += [("", EX_TITLE.get(s, s), "", s, 2 if s in EX_MERGE_JP else 1) for s in sorted(ex_series)]
db.executemany("INSERT INTO neos VALUES (?,?,?,?,?)", neo_rows)
db.commit()
db.execute("VACUUM"); db.commit(); db.close()
sz = os.path.getsize(OUT) / 1048576
print(f"wrote {OUT}  ({sz:.1f} MB)  | cards={len(crows)} abilities={len(arows)}")

# Ship a gzipped copy: the app fetches ws.sqlite.gz (small download, under GitHub's file limit)
# and decompresses it in the browser before loading it into sql.js.
import gzip, shutil
with open(OUT, "rb") as fi, gzip.open(OUT + ".gz", "wb", compresslevel=9) as fo:
    shutil.copyfileobj(fi, fo)
print(f"gzipped -> {OUT}.gz  ({os.path.getsize(OUT + '.gz')/1048576:.1f} MB)")
