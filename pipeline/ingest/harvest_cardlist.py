# -*- coding: utf-8 -*-
"""
Harvest the ENTIRE official Weiss Schwarz JP card list to a local JSON file,
using the official JSON endpoint ws-tcg.com/manage/CardListUser/searchJson.

- Polite throttle, retries w/ backoff.
- Incremental JSONL writes (resumable via state file).
- Final consolidation to a single deduped JSON array.
Read-only on everything else. Writes ONLY new files in this folder.
"""
import urllib.request, json, ssl, time, os, io

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
JSONL     = os.path.join(OUT_DIR, "cardlist_full.jsonl")
STATE     = os.path.join(OUT_DIR, "cardlist_full.state.json")
FINAL     = os.path.join(OUT_DIR, "cardlist_full.json")
LOG       = os.path.join(OUT_DIR, "harvest_cardlist.log")

URL = ("https://ws-tcg.com/manage/CardListUser/searchJson"
       "?keyword=&keyword_or=&keyword_not=&keyword_type%5B%5D=all"
       "&show_page_count=100&page={page}")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (WS power-cost research; https://github.com/CrisRP-dev/ws-card-db)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://ws-tcg.com/cardlist/search/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
CTX = ssl.create_default_context()
THROTTLE = 0.25

def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def fetch_page(page, retries=4):
    # GET one results page with retry + exponential backoff (1s, 2s, 4s, 8s). Re-raises the last error
    # if all attempts fail, so the caller can record the page as failed and move on.
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL.format(page=page), headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise last

def load_state():
    # Resume point. last_page = highest page already written to the JSONL; a fresh run starts at 0 so
    # the loop begins at page 1. failed_pages lets a later run see which pages need re-fetching.
    if os.path.exists(STATE):
        with io.open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"last_page": 0, "total": None, "page_count": None, "failed_pages": []}

def save_state(s):
    with io.open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f)

def main():
    state = load_state()
    first = fetch_page(1)
    page_count = first.get("page_count")
    total = first.get("total")
    state["page_count"] = page_count
    state["total"] = total
    log("catalog total=%s page_count=%s | resuming after page %s"
        % (total, page_count, state["last_page"]))

    start = state["last_page"] + 1                 # continue right after the last page we persisted
    # append mode keeps prior pages if resuming
    jf = io.open(JSONL, "a", encoding="utf-8")
    failed = set(state.get("failed_pages", []))

    for page in range(start, page_count + 1):
        try:
            data = first if page == 1 else fetch_page(page)   # reuse the page-1 fetch we already did
        except Exception as e:
            log("PAGE %d FAILED after retries: %s" % (page, e))
            failed.add(page)                       # don't abort the whole harvest for one bad page
            state["failed_pages"] = sorted(failed)
            save_state(state)
            continue
        items = data.get("items", []) or []
        for c in items:
            jf.write(json.dumps(c, ensure_ascii=False) + "\n")   # one card per line (JSONL)
        jf.flush(); os.fsync(jf.fileno())          # force to disk so a crash never loses a written page
        state["last_page"] = page
        if page % 25 == 0 or page == page_count:   # checkpoint the resume state every 25 pages
            state["failed_pages"] = sorted(failed)
            save_state(state)
            log("page %d/%d done (%d cards on page)" % (page, page_count, len(items)))
        time.sleep(THROTTLE)                        # polite delay between requests

    jf.close()
    state["failed_pages"] = sorted(failed)
    save_state(state)

    # consolidate -> single deduped JSON array (dedupe by id)
    log("consolidating JSONL -> %s" % os.path.basename(FINAL))
    seen, cards = set(), []
    with io.open(JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            cid = c.get("id")
            if cid in seen:
                continue
            seen.add(cid)
            cards.append(c)
    with io.open(FINAL, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False)
    series = sorted({c.get("title_number") for c in cards})
    log("DONE: %d unique cards | %d distinct series | failed_pages=%s"
        % (len(cards), len(series), state["failed_pages"]))
    log("output: %s" % FINAL)

if __name__ == "__main__":
    main()
