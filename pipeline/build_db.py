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
try:
    _rawcache = json.load(open(os.path.join(D, "translation_cache.json"), encoding="utf-8"))
except FileNotFoundError:
    _rawcache = {}
CACHE = {_nk(k): v for k, v in _rawcache.items()}
print("cards:", len(clean), "| en:", len(en_cards), "| translation cache:", len(_rawcache))

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
  picture TEXT, image_en TEXT
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
    crows.append((
        cn, base_num(cn), c.get("series"), c.get("name"), name_en, c.get("name_kana"),
        join(c.get("neo_titles")), c.get("type"), c.get("color"), c.get("level"), c.get("cost"),
        c.get("power"), c.get("soul"), join(c.get("trigger")), join(c.get("traits")),
        c.get("rare"), c.get("side"), c.get("expansion"), c.get("parallel"), era.get(cn),
        power_base, budget, (model_total if have_cost else None), real_delta,
        c.get("picture"), (ec.get("image") if ec else None),
    ))
    arows.extend(ab_buf)

db.executemany("INSERT INTO cards VALUES (%s)" % ",".join("?"*26), crows)
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
