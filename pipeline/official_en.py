# official_en.py — RELIABLE match of a JP ability -> OFFICIAL EN text (harvest cardlist_en.json).
# Candidate by (title,number) or by title; aligns ability-by-ability ONLY if the EN card has
# the same number of abilities and ALL pairs pass the consistency filter (markers+numbers>=2+anchors).
# Returns {(jp_card_number, ability_index): en_text}. When in doubt it does NOT assign (honest).
import json, os, re, collections
D = os.path.dirname(os.path.abspath(__file__))
ZT = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")   # full-width digits/signs -> ASCII so \d+ matches

def _nums(t):
    # Multiset of the numeric magnitudes in a text (e.g. "deal 2 damage, draw 1" -> {2:1}).
    # Used as a fingerprint: a JP ability and its EN candidate must mention the SAME numbers.
    c = collections.Counter(re.findall(r"\d+", (t or "").translate(ZT)))
    c.pop("1", None)   # drop "1": the official EN sometimes omits/adds it ("draw a card"); only magnitudes >=2 must match
    return c

# JP ability markers and the English keyword the official EN text must contain if the marker is present.
MK = [("自","AUTO"),("永","CONT"),("起","ACT"),("カウンター","COUNTER")]
# JP keyword -> English word its translation must contain. A cheap semantic checksum: if the JP says
# "damage" the EN candidate must say "damage", etc. Guards against pairing unrelated abilities.
ANCHORS = [("ダメージ","damage"),("引く","draw"),("クロック","clock"),("ストック","stock"),
    ("控え室","waiting"),("山札","deck"),("レベル","level"),("ソウル","soul"),
    ("助太刀","backup"),("応援","assist"),("集中","brainstorm"),("アンコール","encore"),
    ("思い出","memory"),("手札","hand"),("パワー","power"),("選","choose"),
    ("戻","return"),("【レスト】","rest"),("【スタンド】","stand"),("舞台","stage"),("加え","add")]

def _consistent(jp_text, jp_markers, en_text):
    # True only if the EN text is a plausible translation of this JP ability. Three checks, ALL required:
    if not en_text: return False
    enl = en_text.lower()
    jm = "".join(jp_markers or "")
    for jp, en in MK:                                     # (1) marker check: JP's 【自】 -> EN must say "AUTO", etc.
        if jp in jm and en.lower() not in enl: return False
    if _nums(jp_text) != _nums(en_text): return False     # (2) the numbers (>=2) must match exactly
    for jp, en in ANCHORS:                                # (3) every JP keyword present must have its EN word present
        if jp in (jp_text or "") and en not in enl: return False
    return True

def _key(code):
    # Loose card key = (publisher, number) with the set code DROPPED and any 'E' prefix stripped.
    # Looser than build_db's strict_key on purpose: this module confirms the match with the ability
    # consistency filter, so the key only needs to narrow the candidate pool.
    m = re.match(r"([^/]+)/([^-]+)-E?(\d+)", code or "")
    return (m.group(1), str(int(m.group(3)))) if m else None

def _ra(c):
    # Real abilities only: drop vanilla/placeholder dashes.
    return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","")]

def build(clean, en_cards):
    # Index the EN cards two ways so we can fall back from a precise to a broad candidate pool:
    #   by_kn: (publisher, number) -> [ability-lists]   (preferred)
    #   by_t:  publisher           -> [ability-lists]   (fallback when the number doesn't line up)
    by_kn = collections.defaultdict(list); by_t = collections.defaultdict(list)
    for e in en_cards:
        k = _key(e.get("code", "")); ab = [x for x in (e.get("ability") or []) if x.strip()]
        if not ab: continue
        if k: by_kn[k].append(ab); by_t[k[0]].append(ab)
    out = {}
    for c in clean:
        if c["type"] != "Character": continue
        jp_abs = _ra(c)
        if not jp_abs: continue
        k = _key(c["card_number"])
        # prefer the exact (publisher,number) pool; if none, widen to every EN card of the same publisher
        cands = by_kn.get(k) if (k and k in by_kn) else (by_t.get(k[0]) if k else None)
        if not cands: continue
        n = len(jp_abs)
        match = None
        for en_ab in cands:
            if len(en_ab) != n: continue                  # only a card with the SAME ability count can align 1:1
            ok = all(_consistent(jp_abs[i].get("text",""), jp_abs[i].get("markers"), en_ab[i])
                     for i in range(n))                    # every JP ability must pass the filter against its EN peer
            if ok:
                if match is not None and match != en_ab:   # >1 distinct consistent candidate -> ambiguous, refuse
                    match = None; break
                match = en_ab
        if match:                                          # assign EN text positionally: JP ability i -> EN ability i
            for i in range(n):
                out[(c["card_number"], i)] = match[i]
    return out

if __name__ == "__main__":
    clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
    en = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))
    m = build(clean, en)
    cards = {k[0] for k in m}
    print("abilities (card,idx) with RELIABLE official EN:", len(m), "| cards:", len(cards))
