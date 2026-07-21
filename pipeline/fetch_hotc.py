# fetch_hotc.py — scrape Heart of the Cards (heartofthecards.com) English card NAMES.
#
# HotC translates the ORIGINAL Japanese cards (JP card codes, JP + EN name side by side), so it is
# JP-ALIGNED: HotC carries the CORRECT name even for legacy sets that were renumbered in English
# (e.g. Disgaea), where BOTH the official EN list AND the simulator carry the WRONG name. HotC's
# English phrasing is non-official, so it is the LAST fallback in build_db.py's name cascade
# (official -> simulator -> HotC -> blank).
#
# We key by the Japanese NAME (NFKC-normalized), so the dictionary applies by name (robust to any
# JP/EN card-number differences) -- the same mechanism as NAME_OFFICIAL. Only NAMES are scraped: the
# set-listing pages carry name/type/color; effect text lives on per-card detail pages (one request
# each -- too many to scrape politely), so abilities/traits are left to the other sources.
#
# HotC rate-limits bursts (returns a ~400-byte stub page once tripped, recovering after a cooldown),
# so we pace slowly and back off + retry on stubs. Runs MERGE into the existing name_hotc.json, so
# you can scrape the blocked franchises first and the rest later.
#
# Usage:  python pipeline/fetch_hotc.py ["franchise-name regex"] [delay_seconds]
#   e.g.  python pipeline/fetch_hotc.py "Disgaea|Persona|Prisma Illya|Love Live|Fairy Tail" 6
#         python pipeline/fetch_hotc.py            # all sets, default pacing
# Output (pipeline/):  name_hotc.json  {nk(JP name): EN name}
import os, re, json, time, html, sys, unicodedata, urllib.request

D = os.path.dirname(os.path.abspath(__file__))
INDEX = "https://www.heartofthecards.com/code/cardlist.html?pagetype=ws"        # the set-listing index page
SET   = "https://www.heartofthecards.com/code/cardlist.html?pagetype=ws&cardset=%s"  # one set's card table
UA    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ws-card-db personal research"}
# Each card row in a set page renders as two <a> cells: the card link, then a cell whose <a> holds the
# ENGLISH name and the JP name separated by <br>. This regex captures (english, japanese) from that pair.
ROW   = re.compile(r'card=WS_[^"]+">[^<]*</a></td><td[^>]*><a[^>]*>([^<]+)<br>([^<]+)</a>')
STUB  = 2000   # size threshold: real set pages are 50k-110k bytes; a rate-limit throttle stub is only ~400

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")
def nk(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
def has_cjk(s):
    return any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in (s or ""))
def fetch_set(cs, tries=5):
    """Fetch a set page; retry with backoff if the server returns a throttle stub."""
    for t in range(tries):
        try:
            p = fetch(SET % cs)
        except Exception:
            p = ""
        if len(p) > STUB and "cardlist" in p:
            return p
        time.sleep(min(45, 12 * (t + 1)))   # back off and let the rate limit recover
    return None

flt   = sys.argv[1] if len(sys.argv) > 1 else None
delay = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0

idx = fetch(INDEX)
seen, sets = set(), []
for code, name in re.findall(r'cardset=([^"]+)">([^<]+)</a>', idx):
    if code in seen:
        continue
    seen.add(code); name = html.unescape(name).strip()
    if flt and not re.search(flt, name, re.I):
        continue
    sets.append((code, name))
print(f"sets to scrape: {len(sets)}" + (f"   (filter: {flt})" if flt else "") + f"   delay={delay}s")

out = os.path.join(D, "name_hotc.json")
names = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
print(f"existing names: {len(names)}")

def save():
    with open(out, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, sort_keys=True, indent=0)

ok = stub = 0
for i, (cs, name) in enumerate(sets):
    p = fetch_set(cs)
    if p is None:
        stub += 1; print(f"  [{i+1}/{len(sets)}] STUB gave up: {cs}  [{name}]", flush=True); continue
    ok += 1
    before = len(names)
    for en, jp in ROW.findall(p):
        jp = html.unescape(jp); en = html.unescape(en).strip()
        k = nk(jp)
        if k and en and has_cjk(jp):
            names.setdefault(k, en)   # keep first (earlier runs / priority franchises win)
    print(f"  [{i+1}/{len(sets)}] {cs:<22} +{len(names)-before:>3} -> {len(names)} total  [{name}]", flush=True)
    if i % 5 == 0:
        save()   # incremental: survive kills + let progress be monitored
    time.sleep(delay)

save()
print(f"done: scraped {ok}/{len(sets)} sets ({stub} stubs) · {len(names)} total names", flush=True)
