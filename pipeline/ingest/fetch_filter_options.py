# -*- coding: utf-8 -*-
"""Fetch the official filter taxonomy (incl. Neo Standard titles) to local.

The ws-tcg.com card-list search page is backed by a filter-options endpoint that returns every
dropdown value: expansions (with create_date, used by date_sets.py) and the Neo Standard "sides"
(the franchise groupings). We save the raw payload as filter_options.json and derive a tidy
neo_titles.json (franchise name -> its card-code prefixes) that clean_cardlist.py + the builders read.
The endpoint mimics the site's own XHR, hence the X-Requested-With / Referer headers."""
import urllib.request, json, ssl, os, io

D = os.path.dirname(os.path.abspath(__file__))
URL = "https://ws-tcg.com/manage/CardListUser/filter-options"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (WS power-cost research; https://github.com/Cris-Oblea/ws-card-db)",
    "X-Requested-With": "XMLHttpRequest",              # present it as the page's own AJAX call
    "Referer": "https://ws-tcg.com/cardlist/search/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
    data = json.loads(r.read().decode("utf-8"))

# save the raw taxonomy verbatim (date_sets.py reads its "expansions" for create_date)
with io.open(os.path.join(D, "filter_options.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

# Neo Standard titles: each "side" entry = {name, name_kana, side, title_number:"##BD##BDY##"}.
# title_number packs the franchise's card-code prefixes between "##" separators -> split into a codes[]
# list (drop the empty strings the leading/trailing "##" produce).
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
