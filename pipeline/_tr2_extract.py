# _tr2_extract.py — extract the REMAINING untranslated names + abilities into batches for the
# LLM translation pass (post simulator + HotC). Output -> pipeline/_tr2/{name,ability}_NNN.json.
# Names keyed by JP name (-> name_tr.json); abilities keyed by "markers text" (-> abilities_tr.json,
# which build_db loads into CACHE via _nk()). Junk/placeholder names are skipped.
import sqlite3, json, re, os

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "_tr2"); os.makedirs(OUT, exist_ok=True)
con = sqlite3.connect(os.path.join(D, "..", "site", "ws.sqlite")); c = con.cursor()

def junk(s):   # data-error / placeholder names that can't be translated
    return (not s) or s.startswith("#") or s.strip() in ("―", "ー", "-", "")

names = sorted({r[0] for r in c.execute(
    "SELECT name FROM cards WHERE COALESCE(name_en,'')='' AND COALESCE(name,'')<>''") if not junk(r[0])})

# abilities need the JP markers (not stored in the DB) -> pull from cardlist_clean
cl = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
CLEAN = {cc["card_number"]: cc for cc in cl}
def ra(cc): return [a for a in cc.get("abilities", []) if (a.get("text") or "").strip() not in ("-", "ー", "－", "ｰ", "")]
seen, abils = set(), []
for cn, idx, jp in c.execute("SELECT card_number,idx,jp_text FROM abilities WHERE COALESCE(en_text,'')='' ORDER BY card_number,idx"):
    cc = CLEAN.get(cn)
    mk = "".join(ra(cc)[idx].get("markers") or []) if (cc and idx < len(ra(cc))) else ""
    key = (mk + " " + (jp or "")).strip()
    if not key or key in seen:
        continue
    seen.add(key)
    abils.append({"key": key, "markers": mk, "text": jp})

def write_batches(items, size, prefix):
    n = 0
    for i in range(0, len(items), size):
        with open(os.path.join(OUT, f"{prefix}_{n:03d}.json"), "w", encoding="utf-8") as f:
            json.dump(items[i:i + size], f, ensure_ascii=False)
        n += 1
    return n

nb = write_batches([{"jp": x} for x in names], 200, "name")
ab = write_batches(abils, 120, "ability")
print(f"names={len(names)} -> {nb} batches | abilities={len(abils)} -> {ab} batches  (in {OUT})")
con.close()
