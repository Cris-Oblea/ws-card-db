# official_en.py — RELIABLE match of a JP ability -> OFFICIAL EN text (harvest cardlist_en.json).
# Candidate by (title,number) or by title; aligns ability-by-ability ONLY if the EN card has
# the same number of abilities and ALL pairs pass the consistency filter (markers+numbers>=2+anchors).
# Returns {(jp_card_number, ability_index): en_text}. When in doubt it does NOT assign (honest).
import json, os, re, collections
D = os.path.dirname(os.path.abspath(__file__))
ZT = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")

def _nums(t):
    c = collections.Counter(re.findall(r"\d+", (t or "").translate(ZT)))
    c.pop("1", None)   # the official EN sometimes omits/adds "1"; magnitudes >=2 must match
    return c

MK = [("自","AUTO"),("永","CONT"),("起","ACT"),("カウンター","COUNTER")]
ANCHORS = [("ダメージ","damage"),("引く","draw"),("クロック","clock"),("ストック","stock"),
    ("控え室","waiting"),("山札","deck"),("レベル","level"),("ソウル","soul"),
    ("助太刀","backup"),("応援","assist"),("集中","brainstorm"),("アンコール","encore"),
    ("思い出","memory"),("手札","hand"),("パワー","power"),("選","choose"),
    ("戻","return"),("【レスト】","rest"),("【スタンド】","stand"),("舞台","stage"),("加え","add")]

def _consistent(jp_text, jp_markers, en_text):
    if not en_text: return False
    enl = en_text.lower()
    jm = "".join(jp_markers or "")
    for jp, en in MK:
        if jp in jm and en.lower() not in enl: return False
    if _nums(jp_text) != _nums(en_text): return False
    for jp, en in ANCHORS:
        if jp in (jp_text or "") and en not in enl: return False
    return True

def _key(code):
    m = re.match(r"([^/]+)/([^-]+)-E?(\d+)", code or "")
    return (m.group(1), str(int(m.group(3)))) if m else None

def _ra(c):
    return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","")]

def build(clean, en_cards):
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
        cands = by_kn.get(k) if (k and k in by_kn) else (by_t.get(k[0]) if k else None)
        if not cands: continue
        n = len(jp_abs)
        match = None
        for en_ab in cands:
            if len(en_ab) != n: continue
            ok = all(_consistent(jp_abs[i].get("text",""), jp_abs[i].get("markers"), en_ab[i])
                     for i in range(n))
            if ok:
                if match is not None and match != en_ab:   # >1 distinct consistent candidate -> ambiguous
                    match = None; break
                match = en_ab
        if match:
            for i in range(n):
                out[(c["card_number"], i)] = match[i]
    return out

if __name__ == "__main__":
    clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
    en = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))
    m = build(clean, en)
    cards = {k[0] for k in m}
    print("abilities (card,idx) with RELIABLE official EN:", len(m), "| cards:", len(cards))
