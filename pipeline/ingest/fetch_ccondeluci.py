# -*- coding: utf-8 -*-
"""Fetch WeissSchwarz-ENG-DB (CCondeluci) = official EN text as JSON -> ../cardlist_en.json

The community CCondeluci/WeissSchwarz-ENG-DB GitHub repo stores the OFFICIAL English card text as one
JSON file per set under its DB/ folder. We list that folder via the GitHub API, download each set file,
concatenate all the card records, and write the single canonical cardlist_en.json that the builders read
for official English names/abilities. Read-only on everything else."""
import urllib.request, json, ssl, io, os, time, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")   # force UTF-8 stdout (Windows console default is cp1252)
D = os.path.dirname(os.path.abspath(__file__))
UA = "ws-power-research (https://github.com/Cris-Oblea/ws-card-db)"
ctx = ssl.create_default_context()

def get(url, accept=None):
    # HTTP GET with retry + exponential backoff (1s, 2s, 4s). The GitHub API needs the vnd.github accept
    # header; raw file downloads don't, hence the optional `accept`.
    h = {"User-Agent": UA}
    if accept: h["Accept"] = accept
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40, context=ctx) as r:
                return r.read()
        except Exception as e:
            if attempt == 3: raise                 # last attempt -> let the error propagate
            time.sleep(2 ** attempt)

# 1) list the DB/ directory (one .json per set) via the GitHub contents API
listing = json.loads(get("https://api.github.com/repos/CCondeluci/WeissSchwarz-ENG-DB/contents/DB",
                         accept="application/vnd.github+json"))
files = [it for it in listing if it["name"].endswith(".json")]
print("DB set files:", len(files))

# 2) download every set file and flatten all card records into one list. Set files are either a bare
#    JSON array or an object wrapping the array under "cards"/"data" — handle both shapes.
allcards = []
for i, it in enumerate(files):
    data = json.loads(get(it["download_url"]))
    cards = data if isinstance(data, list) else (data.get("cards") or data.get("data") or [])
    allcards.extend(cards)
    if i % 30 == 0 or i == len(files) - 1:
        print(f"  {i+1}/{len(files)} files ({len(allcards)} cards)")
    time.sleep(0.03)                               # light throttle between raw downloads

# 3) write the canonical EN list one level up (consumed by the builders)
with io.open(os.path.join(D, "..", "cardlist_en.json"), "w", encoding="utf-8") as f:
    json.dump(allcards, f, ensure_ascii=False)

print("\nTOTAL EN cards:", len(allcards))
if allcards:
    c = allcards[0]
    print("fields:", list(c.keys()))
    import json as j
    print("sample:", j.dumps(c, ensure_ascii=False)[:600])
print("saved: cardlist_en.json")
