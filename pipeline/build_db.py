# build_db.py — builds ws.sqlite for the query app.
#
# Mirrors the validated cost model of build_official_list.py (measured -> residual ->
# estimated) but, instead of an aggregated Excel, it emits a per-CARD / per-ABILITY SQLite
# so the app can answer: for THIS card, what does each effect cost in power?
#
# Output: ../site/ws.sqlite   (the static site loads it in the browser via sql.js)
#
# NOTE: the per-ability cost MATH lives in cost_model.py (the single source, shared with
# build_official_list.py). This file owns only the SQLite I/O around it: schema/emit, the EN matching /
# exclusion machinery, gzip + cache-bust. The model is WIP; when it improves, re-run this to regen the DB.
import json, os, re, sqlite3, collections, html, unicodedata
from cost_model import (_nk, pb, ra, base_num, gen, r500, mode500, family, ability_type,
                        gen_en, en_family, build_cost_model, en_cost_model, ENCONF)

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "..", "site", "ws.sqlite")

# ---------------- load ----------------
clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
en_cards = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))
era = json.load(open(os.path.join(D, "card_era.json"), encoding="utf-8"))
# expansion_id -> release_date ("YYYY-MM-DD"): per-card release date metadata (no new harvesting; the
# ingest sub-pipeline already dated every set). A card's c["expansion"] is the expansion_id key.
_set_dates = json.load(open(os.path.join(D, "ingest", "set_dates.json"), encoding="utf-8"))
RELEASE_DATE = {s["expansion_id"]: s.get("release_date") for s in _set_dates}

# --- de-duplicate the JP list: alt-art/rarity parallels AND cross-set-code reprints (some sets are
# listed under two codes, e.g. Frieren SFN/S108 == SFN/S128). A card = same publisher prefix + name +
# stats + EXACT effects (cards that differ in effect keep their own row). The representative prefers
# a printing that HAS an official EN match (so we keep its English), then a base rarity. ---
def _skey(code):   # publisher + set + normalized card id. Handles EN's inserted 'E' (E001/TE08/PE01)
    # Split "PUB/SET-SUFFIX" (e.g. "DAL/W131-E012SP"). The suffix is then normalized so JP and EN forms
    # of the SAME card collapse to one key:
    #   inner re.sub  ^([A-Za-z]*)E(\d) -> \1\2 : drop the 'E' the EN codes insert before the number
    #                                             (TE08 -> T08, E012 -> 012), keeping any trial/promo letter
    #   outer re.sub  (\d)[A-Za-z]+$    -> \1    : strip a parallel/rarity suffix (012SP -> 012)
    m = re.match(r"([^/]+)/([A-Za-z]+\d+)-(.+)$", code or "")   # and trial(T)/promo(P) prefixes + parallels
    if not m: return None
    suf = re.sub(r"(\d)[A-Za-z]+$", r"\1", re.sub(r"^([A-Za-z]*)E(\d)", r"\1\2", m.group(3).upper(), count=1))
    return (m.group(1).upper(), m.group(2).upper(), suf)
EN_STRICT = {_skey(e.get("code", "")) for e in en_cards}; EN_STRICT.discard(None)   # keys that HAVE an EN printing
def _ckey(c):
    # Identity of a physical card for de-dup: publisher prefix + normalized name + full stat line +
    # the EXACT list of (type, normalized text) abilities. Two printings collapse ONLY if all of this
    # matches, so a same-name card with a different effect (e.g. a regional variant) keeps its own row.
    return ((c.get("card_number", "") or "").split("/")[0], _nk(c.get("name")), c.get("power"),
            c.get("level"), c.get("cost"), c.get("soul"),
            tuple((a.get("type"), _nk(a.get("text"))) for a in ra(c)))
BASE_RARE = {"RR", "R", "U", "C", "CR", "CC", "TD"}           # base rarities; anything else = alt-art
def _better(cand, cur):
    ce, ue = _skey(cand.get("card_number", "")) in EN_STRICT, _skey(cur.get("card_number", "")) in EN_STRICT
    if ce != ue: return ce                                    # keep the printing that has an EN match
    cb, ub = cand.get("rare") in BASE_RARE, cur.get("rare") in BASE_RARE
    if cb != ub: return cb                                    # else a base-rarity printing
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
print(f"de-dup (alt-art + cross-set): {_before} -> {len(clean)} distinct JP cards")
def _load(fn):
    try: return json.load(open(os.path.join(D, fn), encoding="utf-8"))
    except FileNotFoundError: return {}
# Complete per-ability JP->EN translations (agent-made, official style), keyed by full JP text
# "【marker】 text". variant_tr_full.json (~15.9k, the complete set) takes precedence over the
# older partial translation_cache.json. Both keyed by normalized full text.
_cache = _load("translation_cache.json")
_vtf = _load("variant_tr_full.json")
_aboff = _load("abilities_official_en.json")     # official EN abilities (strict match) propagated by text
_abtr = _load("abilities_tr.json")               # agent-translated abilities (full bilingual pass)
CACHE = {}
for k, v in {**_cache, **_vtf, **_aboff, **_abtr}.items():
    CACHE[_nk(k)] = v
ABTR = {_nk(k): v for k, v in _abtr.items()}   # LLM ability translations only — the ONLY trusted EN for blocked cards
print(f"cards: {len(clean)} | en: {len(en_cards)} | translations: {len(CACHE)} (cache {len(_cache)} + full {len(_vtf)})")

# --- STRICT EN matching: same publisher + SET + number (e.g. ("DAL","W131",2)).
# The old official_en._key dropped the SET, so DAL/W131-002, DAL/W79-002, DAL/WE33-002 all
# collapsed to ("DAL",2) and cross-contaminated names/effects. We only assign EN data when the
# EXACT same card exists in the EN list; otherwise we leave it blank (better no EN than wrong EN).
def strict_key(code):   # same as _skey above: tolerant of EN's 'E' and trial(T)/promo(P)/parallel suffixes
    m = re.match(r"([^/]+)/([A-Za-z]+\d+)-(.+)$", code or "")
    if not m: return None
    suf = re.sub(r"(\d)[A-Za-z]+$", r"\1", re.sub(r"^([A-Za-z]*)E(\d)", r"\1\2", m.group(3).upper(), count=1))
    return (m.group(1).upper(), m.group(2).upper(), suf)
def _ra_en(e):
    return [a for a in (e.get("ability") or []) if a and a.strip()]
EN_BY = {}
for e in en_cards:
    kk = strict_key(e.get("code", ""))
    if kk: EN_BY.setdefault(kk, e)

# --- Curated legacy DISPARITY exclusions --------------------------------------------------------
# Some old franchises were RENUMBERED / CONSOLIDATED for their English release, so the EN set code
# no longer lines up card-for-card with the JP one (e.g. EN DG/S03 merges JP DG/S02+SE08+SE17; the
# JP/EN trial-deck numbering also diverges). strict_key (same publisher+set+number) then links the
# WRONG English card -> wrong name/abilities. We refuse the EN match for these cases (better a blank
# than a wrong EN, consistent with the strict-matching philosophy). Per-franchise rationale is from
# manual review against the live site; see documentation/ and STATUS.md.
EN_BLOCK_PUB   = {"DG", "P4", "PI", "LL"}   # whole franchise: EN release is a mutated renumber of JP
EN_BLOCK_CARD  = {"BD/W63-102", "BD/W63-103", "BD/W63-104",   # confirmed permuted matches (BanG Dream!)
                  "NK/W30-002", "NK/W30-026", "NK/W30-052", "NK/W30-076"}   # Nisekoi regional variants (JP/EN same code, DIFFERENT effect)
# Manual name overrides: the JP side of the NK/W30 regional variants (乙女心 = "Maiden's Heart") whose
# same-code EN printing is a DIFFERENT card ("The One"); that EN printing is added as its own row below.
# --- upstream scrape corruption fixes (applied to DISPLAYED names) -------------------------------
# Two classes: (1) un-decoded HTML entities (&clubs; &hearts; &#9829; ...) -> html.unescape;
# (2) characters lost to a literal "?" in the source (irrecoverable upstream) -> targeted replace.
# The "?" patterns are specific enough to never hit a genuine question mark.
# NOTE: BD/WE42 "Mas?uerade Rhapsody Re?uest" is INTENTIONAL stylization in the official name
# (the "?" is part of the title, per user) — NOT corruption, so it is deliberately NOT repaired here.
_NAME_REPL = [("Fr?ulein", "Fräulein"), ("Stra?e", "Straße"),          # ä / ß lost to "?" upstream
              ("D?j? Vu", "Déjà Vu"), ("Clover?Club", "Clover♣Club")]  # é/à / ♣ lost
def fix_name(s):
    if not s: return s
    s = html.unescape(s)                       # &clubs; -> ♣, &hearts;/&#9829; -> ♥, &#9825; -> ♡
    for bad, good in _NAME_REPL:
        if bad in s: s = s.replace(bad, good)
    return s

# --- search folding: accent- AND case-insensitive key for the lookup box (so "deja vu" finds
# "Déjà Vu"). NFKD splits accents into base + combining mark; we drop the Latin combining marks
# (U+0300-036F) and lowercase. Japanese is preserved: dakuten/handakuten (U+3099/309A) are OUTSIDE
# that range, so が stays distinct from か.
def fold(s):
    if not s: return ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not (0x0300 <= ord(ch) <= 0x036f)).lower()

NAME_OVERRIDE = {
    "NK/W30-002": "Maiden's Heart, Chitoge", "NK/W30-026": "Maiden's Heart, Seishiro",
    "NK/W30-052": "Maiden's Heart, Marika",  "NK/W30-076": "Maiden's Heart, Kosaki",
}
EN_BLOCK_ENSET = {("BD", "W03")}            # EN-only special booster of band trial decks; no JP counterpart
FT_ALLOW_SET   = {"S120"}                   # Fairy Tail: only S120 maps cleanly to JP; S02/S09/SE10 don't
def en_card_blocked(cn):
    """True if this JP card must get NO English NAME at all (its franchise/set was renumbered, so even
    same-JP-name propagation could graft a wrong English name). Abilities still translate by text."""
    k = strict_key(cn)
    if k is None: return False
    pub, st = k[0], k[1]
    if pub in EN_BLOCK_PUB: return True                       # DG / P4 / PI / LL: drop the whole franchise
    if pub == "FT" and st not in FT_ALLOW_SET: return True    # Fairy Tail: keep only S120
    if base_num(cn) in EN_BLOCK_CARD: return True             # specific permuted cards
    return False
def en_match(cn):
    """EN_BY lookup for a JP card_number with the curated legacy-disparity exclusions applied."""
    if en_card_blocked(cn): return None
    ec = EN_BY.get(strict_key(cn))
    if ec is None: return None
    ek = strict_key(ec.get("code", ""))                      # safeguard: never pull from an EN-only renumber set
    if ek and (ek[0], ek[1]) in EN_BLOCK_ENSET: return None
    return ec

# agent translations (full bilingual pass) + reuse of official EN names across same-name cards
NAME_TR = _load("name_tr.json"); TRAIT_TR = _load("trait_tr.json")
# Unofficial-simulator translations (built by pipeline/extract_simulator.py), keyed by strict_key
# string "PUB/SET/SUF". They fill the JP-only gap the official EN list can't (~20k cards). The
# simulator shares the official list's legacy disparity errors, so every read is gated by
# en_card_blocked() (blocked franchises never pull from it). See documentation/en-name-matching.md.
NAME_SIM = _load("name_sim.json"); TRAITS_SIM = _load("traits_sim.json"); ABILS_SIM = _load("abilities_sim.json")
# Heart of the Cards (pipeline/fetch_hotc.py) — JP-name -> EN-name. HotC translates the original JP
# cards, so it is JP-ALIGNED and has the CORRECT name even for renumbered legacy sets. Non-official
# phrasing, so it's the LAST name fallback — but it applies even to en_card_blocked() franchises.
NAME_HOTC = _load("name_hotc.json")
def _skey_s(cn):
    k = strict_key(cn); return "/".join(k) if k else None
def sim_for(d, cn):
    return None if en_card_blocked(cn) else d.get(_skey_s(cn))
NAME_OFFICIAL = {}
for c in clean:
    ec = en_match(c["card_number"])
    if ec and ec.get("name"): NAME_OFFICIAL.setdefault(c.get("name"), ec["name"])

# --- traits JP->EN dictionary: align clean.traits[i] <-> EN attributes[i] on exact-matched
#     cards (same count); the most common EN per JP trait wins (robust to occasional misorder). ---
_tp = collections.defaultdict(collections.Counter)
for c in clean:
    ec = en_match(c["card_number"])
    if not ec: continue
    jt, et = c.get("traits") or [], ec.get("attributes") or []
    if len(jt) == len(et):
        for a, b in zip(jt, et):
            if a and b: _tp[a][b] += 1
for c in clean:                              # extend the dictionary with simulator traits (positional, same count)
    simt = sim_for(TRAITS_SIM, c["card_number"]); jt = c.get("traits") or []
    if simt and len(jt) == len(simt):
        for a, b in zip(jt, simt):
            if a and b: _tp[a][b] += 1
TRAIT_EN = {k: v.most_common(1)[0][0] for k, v in _tp.items()}

# --- neo-standard: neo_titles.json maps a neo-standard NAME (JP) to its series codes.
#     The franchise's ENGLISH name lives in the EN 'expansion' field -> gather them per neo so
#     the Title filter matches both JP ("デート・ア・ライブ") and EN ("Date A Live"). ---
neo_data = json.load(open(os.path.join(D, "ingest", "neo_titles.json"), encoding="utf-8"))
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

# ---------------- cost model: the single-source cascade (cost_model.build_cost_model) ----------
# All the per-ability MATH (replay folding + measured -> residual -> estimated, Characters only) lives in
# cost_model.py and is shared verbatim with build_official_list.py. Run it over the de-duplicated JP cards
# and read the results off the returned object; this file only does the SQLite I/O around it.
M = build_cost_model(clean)
if M.RP_ORPHANS:
    print(f"replay folding: {len(M.REPLAY_SIGS)} replays -> {len(M.CITER_SIGS)} citers | {len(M.RP_ORPHANS)} orphans (no citer): {M.RP_ORPHANS[:6]}")
else:
    print(f"replay folding: {len(M.REPLAY_SIGS)} replays -> {len(M.CITER_SIGS)} citers | 0 orphans")
if M.validation_pct is not None:
    print(f"validation |err|<=500 on {M.validation_pct:.0f}% (n={M.validation_n})")
fam_med = M.fam_med                 # JP family medians (reused by the EN-exclusive pass below)
ab_cost = M.ab_cost                 # per-ability cost lookup (honors the replay sig override)
ab_std = M.ab_std                   # per-ability STANDARD (standard_cost, mode_share, n_samples)
validation_pct, validation_n = M.validation_pct, M.validation_n   # for the meta row

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
  residual INTEGER, is_suspect INTEGER, release_date TEXT,
  picture TEXT, image_en TEXT, traits_en TEXT, title_search TEXT, en_exclusive INTEGER, text_en TEXT,
  search_fold TEXT
);
CREATE TABLE abilities (
  card_number TEXT, idx INTEGER, ability_type TEXT, family TEXT,
  jp_text TEXT, en_text TEXT, power_cost INTEGER, method TEXT, confidence TEXT,
  standard_cost INTEGER, mode_share REAL, n_samples INTEGER,
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
    cn = c["card_number"]; ec = en_match(cn)   # exact EN card (same set+number), legacy-disparity-filtered
    en_abs = _ra_en(ec) if ec else []
    is_char = c["type"] == "Character" and None not in (c.get("level"), c.get("cost"), c.get("soul"), c.get("power"))
    power_base = pb(c) if is_char else None
    budget = (power_base - 500) if power_base is not None else None
    abs_ = ra(c)
    model_total = 0; have_cost = False
    std_total = 0; have_std = False   # Sum of per-ability STANDARDS -> the card's explained budget
    ab_buf = []
    align = ec is not None and len(en_abs) == len(abs_)   # same card + same ability count -> safe positional EN
    sim_ab = sim_for(ABILS_SIM, cn)                        # simulator EN ability texts (JP-only gap filler)
    sim_align = (not align) and bool(sim_ab) and len(sim_ab) == len(abs_)
    ab_blocked = base_num(cn) in EN_BLOCK_CARD             # permuted/variant card: official-EN cache is the wrong card's effect
    for i, a in enumerate(abs_):
        pc, meth, conf, fam = ab_cost(cn, i, a.get("markers"), a.get("text"))
        std, mshare, nsamp = ab_std(cn, i, a.get("markers"), a.get("text"))   # the package STANDARD + its evidence
        key = _nk((("".join(a.get("markers") or "")) + " " + (a.get("text") or "")).strip())
        en = en_abs[i] if align else (CACHE.get(key) or (sim_ab[i] if sim_align else ""))   # official -> cache(text) -> sim
        if ab_blocked: en = ABTR.get(key, "")              # blocked cards: trust ONLY the LLM translation of their real JP text
        if pc is not None: model_total += pc; have_cost = True
        if std is not None: std_total += std; have_std = True
        ab_buf.append((cn, i, ability_type(a.get("markers")), fam, a.get("text") or "", en, pc, meth, conf,
                       std, mshare, nsamp))
    real_delta = (power_base - c["power"]) if power_base is not None else None
    # residual = the designer's UNEXPLAINED adjustment = real budget - sum of standard costs.
    # is_suspect = the card deviates from the standard price by >= 500 (a cost anomaly worth review).
    residual = (real_delta - std_total) if (real_delta is not None and have_std) else None
    is_suspect = 1 if (residual is not None and abs(residual) >= 500) else 0
    name_en = NAME_OVERRIDE.get(cn) or (ec.get("name") if ec else None)   # manual overrides first (regional variants)
    if not name_en and not en_card_blocked(cn):                  # official EN -> simulator (blocked sets skip both, they're renumbered)
        name_en = NAME_OFFICIAL.get(c.get("name")) or NAME_SIM.get(_skey_s(cn))
    if not name_en:                                              # HotC + LLM names: JP-aligned, CORRECT even for blocked legacy
        name_en = NAME_HOTC.get(_nk(c.get("name"))) or NAME_TR.get(c.get("name"))
    name_en = fix_name(name_en)                                  # decode HTML entities + repair "?"-corrupted source names
    # traits in EN (aligned dict -> agent translation) + a hidden title-search blob (JP + EN franchise)
    traits_en = " / ".join([x for x in ((TRAIT_EN.get(t) or TRAIT_TR.get(t)) for t in (c.get("traits") or [])) if x])
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
        cn, base_num(cn), c.get("series"), fix_name(c.get("name")), name_en, c.get("name_kana"),
        join(c.get("neo_titles")), c.get("type"), color, c.get("level"), c.get("cost"),
        c.get("power"), c.get("soul"), join(c.get("trigger")), join(c.get("traits")),
        c.get("rare"), side, c.get("expansion"), c.get("parallel"), era.get(cn),
        power_base, budget, (model_total if have_cost else None), real_delta,
        residual, is_suspect, RELEASE_DATE.get(c.get("expansion")),
        c.get("picture"), (ec.get("image") if ec else None), traits_en, title_search, 0,
        (" ".join(en_abs) if (ec is not None and not align) else None),   # official full EN when the JP/EN ability split differs
        fold(" ".join(x for x in (fix_name(c.get("name")), name_en, join(c.get("neo_titles")), cn, title_search) if x)),
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
# --- cost model for EN-exclusive cards: SAME methodology as JP (gen_en/en_family/en_cost_model from
#     cost_model.py), applied over the ENGLISH text. This file owns only the EN-card collection + dedup. ---
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
# (c) the EN-EXCLUSIVE cost cascade (measured -> matched -> residual -> estimated, CX floor) is the MATH;
#     run it from cost_model. arows so far = JP abilities only (each tuple [5]=en_text, [6]=power_cost).
encost, enmethod = en_cost_model(arows, ex_cards, fam_med)
# (f) emit rows
for c in ex_cards:
    e = c["e"]; code = c["code"]; title = EX_TITLE.get(c["series"], c["series"])
    model_total = 0; have = False; ab_buf = []
    for (i, atype, txt, s) in c["sigs"]:
        pc = encost.get(s) if c["is_char"] else None         # cost model is Characters only
        meth = enmethod.get(s) if pc is not None else None
        if pc is not None: model_total += pc; have = True
        # EN-exclusive: the EN cascade value IS the standard (no pooled JP mode -> mode_share None, n 0)
        ab_buf.append((code, i, atype, en_family(txt), "", txt, pc, meth, ENCONF.get(meth), pc, None, 0))
    # residual / suspect on the same basis as JP cards (std_total == model_total here)
    residual = (c["delta"] - model_total) if (c["delta"] is not None and have) else None
    is_suspect = 1 if (residual is not None and abs(residual) >= 500) else 0
    crows.append((
        code, base_num(code), c["series"], fix_name(e.get("name")), fix_name(e.get("name")), "", title, e.get("type"),
        (e.get("color") or "").lower(), c["lv"], c["co"], c["pw"], c["so"], " / ".join(c["trig"]),
        " / ".join(c["attrs"]), e.get("rarity"), {"W": "Weiss", "S": "Schwarz"}.get(e.get("side"), e.get("side")),
        None, 0, None, c["pbase"], (c["pbase"] - 500 if c["pbase"] is not None else None),
        (model_total if have else None), c["delta"], residual, is_suspect, None,
        "", e.get("image"), " / ".join(c["attrs"]), title.lower(), 1,
        None,   # text_en (EN-exclusive abilities are already per-ability)
        fold(" ".join(x for x in (fix_name(e.get("name")), title, code) if x)),
    ))
    arows.extend(ab_buf)
print(f"English-exclusive cards added (WX/SX): {len(ex_cards)}")

# --- NK/W30 regional variants: 4 Nisekoi cards share a JP/EN code but have DIFFERENT effects by
#     language. The JP printing (乙女心 "Maiden's Heart") stays in the main DB above (its wrong EN match
#     is blocked + name-overridden); here we add the ENGLISH printing ("The One", different effect) as
#     its OWN en_exclusive row under the EN code NK/W30-E0xx, grouped under Nisekoi. ---
NK_VARIANTS = ["NK/W30-E002", "NK/W30-E026", "NK/W30-E052", "NK/W30-E076"]
EN_RAW = {e.get("code"): e for e in en_cards}
_nkneo = "ニセコイ"; _nt = NAME2NEO.get(_nkneo)
NK_TS = " ".join(x for x in ([_nkneo] + ([_nt.get("name_kana", "")] + _nt.get("codes", []) if _nt else []) + [neo_en(_nkneo)]) if x).lower()
nk_added = 0
for code in NK_VARIANTS:
    e = EN_RAW.get(code)
    if not e: continue
    nk_added += 1
    lv, co, pw, so = _i(e.get("level")), _i(e.get("cost")), _i(e.get("power")), _i(e.get("soul"))
    is_char = e.get("type") == "Character" and None not in (lv, co, pw, so)
    trig = [str(x).lower() for x in (e.get("trigger") or [])]
    pbase = (3000 + 2500*lv + 1500*co - 1000*(1 if "soul" in trig else 0) - 1000*(so-1)) if is_char else None
    attrs = e.get("attributes") or []
    model_total = 0; have = False; ab_buf = []
    for i, a in enumerate([x for x in (e.get("ability") or []) if x and x.strip()]):
        if is_char:
            s = gen_en(a)
            pc, meth = (encost[s], enmethod.get(s, "matched")) if s in encost else (fam_med.get(en_family(a), 500), "estimated")
        else:
            pc, meth = None, None
        if pc is not None: model_total += pc; have = True
        ab_buf.append((code, i, _en_type(a), en_family(a), "", a, pc, meth, ENCONF.get(meth), pc, None, 0))
    delta = (pbase - pw) if pbase is not None else None
    residual = (delta - model_total) if (delta is not None and have) else None
    is_suspect = 1 if (residual is not None and abs(residual) >= 500) else 0
    crows.append((
        code, base_num(code), "NK", fix_name(e.get("name")), fix_name(e.get("name")), "", _nkneo, e.get("type"),
        (e.get("color") or "").lower(), lv, co, pw, so, " / ".join(trig),
        " / ".join(attrs), e.get("rarity"), {"W": "Weiss", "S": "Schwarz"}.get(e.get("side"), e.get("side")),
        None, 0, None, pbase, (pbase - 500 if pbase is not None else None),
        (model_total if have else None), delta, residual, is_suspect, None,
        "", e.get("image"), " / ".join(attrs), NK_TS, 1, None,
        fold(" ".join(x for x in (fix_name(e.get("name")), _nkneo, code, NK_TS) if x)),
    ))
    arows.extend(ab_buf)
print(f"NK/W30 EN-variant cards added: {nk_added}")

db.executemany("INSERT INTO cards VALUES (%s)" % ",".join("?"*34), crows)
db.executemany("INSERT INTO abilities VALUES (%s)" % ",".join("?"*12), arows)
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
# --- Explained% : the acceptance metric (replaces the near-tautological consistency %) ---------
# Among valid COSTED Character cards (a non-null residual = the model standardized every ability), the
# share whose residual is within +/-500 = the designer's unexplained adjustment is small. This is a real
# OUT-OF-SAMPLE check (per-card actual vs the package STANDARDS), not the residual cascade re-summing
# itself. Crows columns: type=7, residual=24, is_suspect=25.
_costed = [r for r in crows if r[7] == "Character" and r[24] is not None]
_explained = sum(1 for r in _costed if abs(r[24]) <= 500)
explained_pct = (100.0 * _explained / len(_costed)) if _costed else None
suspect_count = sum(1 for r in crows if r[25] == 1)
if explained_pct is not None:
    print(f"Explained%: {explained_pct:.1f}% of costed Character cards on-budget (|residual|<=500) "
          f"(n={len(_costed)}) | suspects (|residual|>=500): {suspect_count}")
    assert explained_pct >= 94.0, f"Explained% {explained_pct:.1f}% below the 94% acceptance baseline"
meta = [
    ("schema", "1"),
    ("cards", str(len(crows))),
    ("abilities", str(len(arows))),
    ("explained_pct", (f"{explained_pct:.1f}" if explained_pct is not None else "n/a")),
    ("explained_n", str(len(_costed))),
    ("suspects", str(suspect_count)),
    ("validation", (f"{explained_pct:.0f}% explained (|residual|<=500, n={len(_costed)})"
                    if explained_pct is not None else "n/a")),
    ("note", "Per-card residual = real budget - sum of ability STANDARD costs; is_suspect = |residual|>=500. "
             "Confidence reflects the standard's evidence: HIGH=measured & n>=3 & mode_share>=60, "
             "MEDIUM=residual or weak measured, LOW=estimated."),
]
db.executemany("INSERT INTO meta VALUES (?,?)", meta)
# neo-standards (official deck-construction groups): each is a SEPARATE standard with its own
# set codes. The app uses this for an exact title filter (pick a neo -> match its codes only).
db.execute("CREATE TABLE neos (jp_name TEXT, en_name TEXT, kana TEXT, codes TEXT, en_only INTEGER)")
# JP neos that ALSO contain EN-exclusive variant cards (e.g. Nisekoi's 4 NK/W30 "The One" printings,
# which share the JP series code NK). en_only=2 makes the Title filter select the whole series
# (JP cards + EN variants); without it the en_exclusive split would hide the 4 variants.
NEO_WITH_EN_VARIANTS = {"ニセコイ"}
neo_rows = [(nt["name"], neo_en(nt["name"]), nt.get("name_kana", ""), " ".join(nt.get("codes", [])),
             2 if nt["name"] in NEO_WITH_EN_VARIANTS else 0)
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
import gzip, hashlib
raw = open(OUT, "rb").read()
with gzip.GzipFile(OUT + ".gz", "wb", compresslevel=9, mtime=0) as fo:   # mtime=0 -> deterministic gz
    fo.write(raw)
print(f"gzipped -> {OUT}.gz  ({os.path.getsize(OUT + '.gz')/1048576:.1f} MB)")

# Cache-bust the web app: stamp a short hash of the DB CONTENT as ?v= in app.js, so a rebuild is
# never served stale and the URL changes for ANY data change (not just card/ability counts).
ver = hashlib.sha1(raw).hexdigest()[:10]
_appjs = os.path.join(D, "..", "site", "app.js")
try:
    _t = open(_appjs, encoding="utf-8").read()
    _n = re.sub(r"(ws\.sqlite\.gz\?v=)\w+", r"\g<1>" + ver, _t)
    if _n != _t:
        open(_appjs, "w", encoding="utf-8").write(_n)
        print(f"bumped app.js cache version -> ws.sqlite.gz?v={ver}")
except FileNotFoundError:
    pass
