# _tr2_extract.py — extract the REMAINING untranslated names + abilities into batches for the
# LLM translation pass (post simulator + HotC). Output -> pipeline/_tr2/{name,ability}_NNN.json.
# Names keyed by JP name (-> name_tr.json); abilities keyed by "markers text" (-> abilities_tr.json,
# which build_db loads into CACHE via _nk()). Junk/placeholder names are skipped.
import sqlite3, json, re, os

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "_tr2"); os.makedirs(OUT, exist_ok=True)
# Read the ALREADY-BUILT DB: the missing-EN rows here are exactly whatever build_db.py could not fill
# from official EN / simulator / HotC, so this must run AFTER a build_db.py pass.
con = sqlite3.connect(os.path.join(D, "..", "site", "ws.sqlite")); c = con.cursor()

def junk(s):   # data-error / placeholder names that can't be translated (drop, don't send to the LLM)
    return (not s) or s.startswith("#") or s.strip() in ("―", "ー", "-", "")

# Names still lacking an English name (name_en empty but a JP name exists), de-duplicated + sorted.
names = sorted({r[0] for r in c.execute(
    "SELECT name FROM cards WHERE COALESCE(name_en,'')='' AND COALESCE(name,'')<>''") if not junk(r[0])})

# Abilities still lacking EN. The DB stores jp_text but NOT the JP markers (【自】…), and the translation
# key downstream is "markers text" — so re-attach the markers by looking the ability up positionally in
# cardlist_clean (abilities keep their original order, so DB idx == index into the card's real abilities).
cl = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
CLEAN = {cc["card_number"]: cc for cc in cl}
def ra(cc): return [a for a in cc.get("abilities", []) if (a.get("text") or "").strip() not in ("-", "ー", "－", "ｰ", "")]
seen, abils = set(), []
for cn, idx, jp in c.execute("SELECT card_number,idx,jp_text FROM abilities WHERE COALESCE(en_text,'')='' ORDER BY card_number,idx"):
    cc = CLEAN.get(cn)
    mk = "".join(ra(cc)[idx].get("markers") or []) if (cc and idx < len(ra(cc))) else ""
    key = (mk + " " + (jp or "")).strip()
    if not key or key in seen:                        # de-dup by full key: translate each distinct ability once
        continue
    seen.add(key)
    abils.append({"key": key, "markers": mk, "text": jp})

def write_batches(items, size, prefix):
    # Split a list into fixed-size JSON files prefix_000.json, prefix_001.json, … (LLM-sized chunks).
    n = 0
    for i in range(0, len(items), size):
        with open(os.path.join(OUT, f"{prefix}_{n:03d}.json"), "w", encoding="utf-8") as f:
            json.dump(items[i:i + size], f, ensure_ascii=False)
        n += 1
    return n

nb = write_batches([{"jp": x} for x in names], 200, "name")   # names -> name_NNN.json (200 each)
ab = write_batches(abils, 120, "ability")                     # abilities -> ability_NNN.json (120 each)
print(f"names={len(names)} -> {nb} batches | abilities={len(abils)} -> {ab} batches  (in {OUT})")
con.close()
