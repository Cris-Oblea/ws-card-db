# Merge _tr/out_*.json (id->en) into the PERMANENT translation cache translation_cache.json (JP text -> en).
# INCREMENTAL + JP-keyed: loads the existing cache and ADDS new translations; never loses old ones.
# Keyed by JP ability text = stable ground truth, so it survives any cost-methodology/sig change.
# Result: a card's missing-English ability is translated exactly ONCE, ever. No agents.
import json, glob, os
D = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(D, "_tr")
CACHE_PATH = os.path.join(D, "translation_cache.json")

# 1) load the permanent cache (may not exist on the very first run)
try:
    cache = json.load(open(CACHE_PATH, encoding="utf-8"))   # jp_real -> en
except FileNotFoundError:
    cache = {}
before = len(cache)
print(f"existing cache entries: {before}")

# 2) what this build run asked to translate (id -> jp text, this run only)
to_translate = json.load(open(os.path.join(D, "to_translate.json"), encoding="utf-8"))
id2jp = {r["id"]: r["jp"] for r in to_translate}
want_jp = set(id2jp.values())
print(f"to_translate this run: {len(to_translate)} abilities")

# 3) collect agent output (id -> en) from every out file
got = {}
bad = []
out_files = sorted(glob.glob(os.path.join(TR, "out_*.json")))
for f in out_files:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        bad.append((os.path.basename(f), str(e))); continue
    for k, v in d.items():
        try:
            i = int(k)
        except ValueError:
            continue
        if isinstance(v, str) and v.strip():
            got[i] = v.strip()
print(f"out files: {len(out_files)} | translations collected: {len(got)}")
if bad:
    print("BAD FILES:", bad)

# 4) ADD new translations into the cache, keyed by JP text (do not clobber existing)
added = 0
for i, en in got.items():
    jp = id2jp.get(i)
    if jp and jp not in cache:
        cache[jp] = en; added += 1
print(f"added {added} new entries (cache: {before} -> {len(cache)})")

# 5) coverage for THIS run's requested abilities
covered = sum(1 for jp in want_jp if jp in cache)
missing = [r for r in to_translate if r["jp"] not in cache]
pct = 100 * covered // max(1, len(want_jp))
print(f"this run covered: {covered}/{len(want_jp)} ({pct}%)")
if missing:
    miss_chunks = sorted(set(r["id"] // 120 for r in missing))
    json.dump(missing, open(os.path.join(D, "residual_to_translate.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"MISSING {len(missing)} -> chunks {miss_chunks} ; wrote residual_to_translate.json")
else:
    print("ALL requested abilities covered.")

# 6) save the permanent cache
json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)
print(f"-> saved {CACHE_PATH} ({len(cache)} entries) [PERMANENT - never delete]")
