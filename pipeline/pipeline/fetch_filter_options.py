# -*- coding: utf-8 -*-
"""Baja la taxonomia oficial de filtros (incl. titulos Neo Standard) a local."""
import urllib.request, json, ssl, os, io

D = os.path.dirname(os.path.abspath(__file__))
URL = "https://ws-tcg.com/manage/CardListUser/filter-options"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (WS power-cost research; contact agentic@propital.com)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://ws-tcg.com/cardlist/search/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
    data = json.loads(r.read().decode("utf-8"))

with io.open(os.path.join(D, "filter_options.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

# Neo Standard titles: each "side" entry = {name, name_kana, side, title_number:"##BD##BDY##"}
titles = [{"name": s.get("name"), "name_kana": s.get("name_kana"),
           "side": s.get("side"),
           "codes": [c for c in (s.get("title_number") or "").split("##") if c]}
          for s in data.get("sides", [])]
with io.open(os.path.join(D, "neo_titles.json"), "w", encoding="utf-8") as f:
    json.dump(titles, f, ensure_ascii=False, indent=1)

print("master keys:", list(data.keys()))
print("Neo Standard titles:", len(titles))
print("multi-code titles:", sum(1 for t in titles if len(t["codes"]) > 1))
c2t = {}
for t in titles:
    for c in t["codes"]:
        c2t.setdefault(c, []).append(t["name"])
print("distinct codes:", len(c2t), "| shared codes:", sum(1 for v in c2t.values() if len(v) > 1))
print("saved: filter_options.json, neo_titles.json")
