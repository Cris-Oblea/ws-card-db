# -*- coding: utf-8 -*-
"""Fetch WeissSchwarz-ENG-DB (CCondeluci) = official EN text as JSON -> ../cardlist_en.json"""
import urllib.request, json, ssl, io, os, time, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
UA = "ws-power-research (agentic@propital.com)"
ctx = ssl.create_default_context()

def get(url, accept=None):
    h = {"User-Agent": UA}
    if accept: h["Accept"] = accept
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40, context=ctx) as r:
                return r.read()
        except Exception as e:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

listing = json.loads(get("https://api.github.com/repos/CCondeluci/WeissSchwarz-ENG-DB/contents/DB",
                         accept="application/vnd.github+json"))
files = [it for it in listing if it["name"].endswith(".json")]
print("DB set files:", len(files))

allcards = []
for i, it in enumerate(files):
    data = json.loads(get(it["download_url"]))
    cards = data if isinstance(data, list) else (data.get("cards") or data.get("data") or [])
    allcards.extend(cards)
    if i % 30 == 0 or i == len(files) - 1:
        print(f"  {i+1}/{len(files)} files ({len(allcards)} cards)")
    time.sleep(0.03)

with io.open(os.path.join(D, "..", "cardlist_en.json"), "w", encoding="utf-8") as f:   # canonical, one level up
    json.dump(allcards, f, ensure_ascii=False)

print("\nTOTAL EN cards:", len(allcards))
if allcards:
    c = allcards[0]
    print("fields:", list(c.keys()))
    import json as j
    print("sample:", j.dumps(c, ensure_ascii=False)[:600])
print("saved: cardlist_en.json")
