# Extract the distinct JP items still missing an English translation (abilities, card names,
# traits) and write them as batch files for the translation workflow. Re-runnable.
import json, os, re, unicodedata, collections
D = os.path.dirname(os.path.abspath(__file__))
def _nk(s): return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
def load(fn):
    try: return json.load(open(os.path.join(D, fn), encoding="utf-8"))
    except FileNotFoundError: return {}
def ra(c): return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","ｰ","")]

clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
en = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))

# combined existing translations
CACHE = {}
for fn in ("translation_cache.json", "variant_tr_full.json", "abilities_tr.json"):
    for k, v in load(fn).items(): CACHE[_nk(k)] = v
NAME_TR = load("name_tr.json"); TRAIT_TR = load("trait_tr.json")

# official EN names already known (strict set+number match) -> reuse, don't re-translate
import re as _re
def skey(code):
    m = _re.match(r"([^/]+)/([A-Za-z]+\d+)-E?(\d+)", code or "")
    return (m.group(1).upper(), m.group(2).upper(), int(m.group(3))) if m else None
EN_BY = {}
for e in en:
    k = skey(e.get("code", ""))
    if k: EN_BY.setdefault(k, e)
NAME_OFFICIAL = {}
for c in clean:
    if c.get("excluded"): continue
    ec = EN_BY.get(skey(c["card_number"]))
    if ec and ec.get("name"): NAME_OFFICIAL.setdefault(c.get("name"), ec["name"])
# trait JP->EN already known (aligned from strict matches)
TRAIT_OFFICIAL = {}
for c in clean:
    ec = EN_BY.get(skey(c["card_number"]))
    if ec:
        jt, et = c.get("traits") or [], ec.get("attributes") or []
        if len(jt) == len(et):
            for a, b in zip(jt, et):
                if a and b: TRAIT_OFFICIAL.setdefault(a, b)

ab_need, name_need, trait_need = set(), set(), set()
for c in clean:
    if c.get("excluded"): continue
    for a in ra(c):
        key = ("".join(a.get("markers") or []) + " " + (a.get("text") or "")).strip()
        if _nk(key) not in CACHE: ab_need.add(key)
    nm = c.get("name")
    if nm and nm not in NAME_OFFICIAL and nm not in NAME_TR: name_need.add(nm)
    for t in (c.get("traits") or []):
        if t and t not in TRAIT_OFFICIAL and t not in TRAIT_TR: trait_need.add(t)

BD = os.path.join(D, "_tr_batches")
os.makedirs(BD, exist_ok=True)
for f in os.listdir(BD): os.remove(os.path.join(BD, f))
manifest = []
def dump(kind, items, size):
    items = sorted(items)
    for i in range(0, len(items), size):
        p = os.path.join(BD, f"{kind}_{i//size:04d}.json")
        json.dump(items[i:i+size], open(p, "w", encoding="utf-8"), ensure_ascii=False)
        manifest.append({"kind": kind, "in": p, "out": p.replace(".json", ".out.json"), "n": len(items[i:i+size])})

dump("ability", ab_need, 480)
dump("name", name_need, 950)
dump("trait", trait_need, 600)
json.dump(manifest, open(os.path.join(D, "_tr_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(f"abilities: {len(ab_need)} | names: {len(name_need)} | traits: {len(trait_need)}")
print(f"batches: {len(manifest)}  (ability {sum(1 for m in manifest if m['kind']=='ability')}, "
      f"name {sum(1 for m in manifest if m['kind']=='name')}, trait {sum(1 for m in manifest if m['kind']=='trait')})")
