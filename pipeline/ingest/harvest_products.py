# -*- coding: utf-8 -*-
"""
Harvest the official Weiss Schwarz JP PRODUCTS archive (ws-tcg.com/products/)
to get the real Japanese release date (発売日) of every product.

The card list backend clamps all pre-2018 expansions to create_date 2018-01-10
(site migration date), so we need the human-facing products archive for the
true 発売日 of legacy sets. Modern sets (>=2018) already have a real create_date
in filter_options.json; we harvest them too for cross-validation.

Output: products_jp.json  = list of {code, title, category, date, year, month, day}
Read-only on everything else. Writes ONLY new files in this folder.
"""
import urllib.request, json, ssl, time, os, io, re

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT     = os.path.join(OUT_DIR, "products_jp.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (WS power-cost research; https://github.com/CrisRP-dev/ws-card-db)"}
CTX     = ssl.create_default_context()
THROTTLE = 0.3
BASE    = "https://ws-tcg.com/products/"

# Each product is an <a href=".../products/CODE/" class="products__link"> ... </a> block.
# NOTE: the href (with CODE) precedes the class attr, so capture from <a href.
RE_BLOCK = re.compile(r'<a\s+href="https://ws-tcg\.com/products/([a-zA-Z0-9_\-]+)/"\s+class="products__link">(.*?)</a>', re.S)
RE_CAT   = re.compile(r'class="products__catItem">([^<]+)<')
RE_NAME  = re.compile(r'class="products__name">\s*(.*?)\s*</p>', re.S)
RE_DATE  = re.compile(r'発売日[：:]\s*([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日')

def get(url, retries=4):
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e; time.sleep(2 ** a)
    raise last

def parse_page(html):
    out = []
    for code, blk in RE_BLOCK.findall(html):
        name = RE_NAME.search(blk)
        date = RE_DATE.search(blk)
        cat  = RE_CAT.search(blk)
        if not date:
            continue
        y, m, d = (int(x) for x in date.groups())
        nm = re.sub(r"<[^>]+>", "", name.group(1)).strip() if name else ""
        out.append({
            "code": code,
            "title": nm,
            "category": cat.group(1).strip() if cat else "",
            "date": f"{y:04d}-{m:02d}-{d:02d}",
            "year": y, "month": m, "day": d,
        })
    return out

def page_url(year, page):
    if page == 1:
        return f"{BASE}?p_year={year}"
    return f"{BASE}page/{page}/?p_year={year}"

def main():
    all_products = {}   # code -> record (dedupe by code; keep first/any)
    for year in range(2008, 2027):
        ytotal = 0
        for page in range(1, 30):
            html = get(page_url(year, page))
            if "products__link" not in html:        # beyond last page
                break
            recs = parse_page(html)
            new = 0
            for r in recs:
                if r["code"] not in all_products:
                    all_products[r["code"]] = r; new += 1
            ytotal += len(recs)
            time.sleep(THROTTLE)
            if new == 0:                             # page repeated -> no more
                break
        print(f"{year}: {ytotal} products listed", flush=True)
    products = sorted(all_products.values(), key=lambda r: (r["date"], r["code"]))
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=0)
    yrs = {}
    for p in products:
        yrs[p["year"]] = yrs.get(p["year"], 0) + 1
    print(f"DONE: {len(products)} unique products -> {os.path.basename(OUT)}")
    print("by year:", dict(sorted(yrs.items())))

if __name__ == "__main__":
    main()
