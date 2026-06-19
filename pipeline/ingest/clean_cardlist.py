# -*- coding: utf-8 -*-
"""
Normalize the raw harvested cardlist (cardlist_full.json) into a clean,
work-ready JSON (cardlist_clean.json), plus an AUDIT (cardlist_audit.json)
to verify field-decoding mappings against real data before trusting them.

Reads:  cardlist_full.json   (raw harvest, in this folder)
Writes: ../cardlist_clean.json (canonical, consumed by the builders) + cardlist_audit.json (here)
Read-only on everything else.
"""
import json, os, re, io
from collections import Counter, defaultdict

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW     = os.path.join(OUT_DIR, "cardlist_full.json")
CLEAN   = os.path.join(OUT_DIR, "..", "cardlist_clean.json")   # canonical lives one level up (consumed by the builders)
AUDIT   = os.path.join(OUT_DIR, "cardlist_audit.json")
NEO     = os.path.join(OUT_DIR, "neo_titles.json")

GIF_RE = re.compile(r"\[\[([a-z0-9_]+)\.gif\]\]", re.I)
TAG_RE = re.compile(r"<[^>]+>")

# Verified against cardlist_audit.json (2026-06-07): kind 2=Character (has lvl+pow+soul),
# 3=Event (has lvl, no pow/soul), 4=Climax (no lvl/pow). No kind "1" exists.
CARD_KIND = {"2": "Character", "3": "Event", "4": "Climax"}
SIDE      = {"-1": "Weiss", "-2": "Schwarz", "-3": "Other"}
COLOR_FALLBACK = {"紫": "purple", "赤": "red", "青": "blue", "黄": "yellow", "緑": "green"}
# The 3 ability timing types (verified: only these 3 exist; 常 does NOT exist).
TIMING = {"【自】": "AUTO", "【永】": "CONT", "【起】": "ACT"}

# Known source-data errors -> corrections (official structured field wrong vs the
# printed card). Each entry overrides fields on the cleaned card.
OVERRIDES = {
    "P3/S01-19T": {"power": 6000},   # official lists '-'; real card = 6000 (verified by the user)
    "WS/WSPR-P19": {"level": None},  # wrong tag (level 13); it's a normal climax -> no level (don't exclude)
}

# Neo Standard title taxonomy: card-code (作品番号) -> list of title NAMES.
# A title groups several codes (BanG Dream! = BD,BDY); a code can be shared
# across titles (BDY -> BanG Dream! + Virtual Girl). Source: /filter-options -> neo_titles.json.
def _load_neo():
    try:
        with io.open(NEO, encoding="utf-8") as f:
            titles = json.load(f)
    except FileNotFoundError:
        return {}
    m = defaultdict(list)
    for t in titles:
        for code in t.get("codes", []):
            m[code].append(t.get("name"))
    return dict(m)
CODE2TITLES = _load_neo()

# Exclusion: cards unusable for measuring power objectively.
#  - stats outside the standard WS range (level/soul 0..3, power multiple of 500), or
#  - marked by Bushiroad itself as NOT tournament-usable (joke/promo).
NON_TOURNAMENT_MARK = "大会では使用できません"

def exclude_reason(card):
    lv, soul, pw = card["level"], card["soul"], card["power"]
    if lv is not None and not (0 <= lv <= 3):
        return "level_out_of_range"
    if not (0 <= soul <= 3):
        return "soul_out_of_range"
    if card["type"] == "Character" and (pw is None or pw % 500 != 0):
        return "power_not_mult_500"
    if card["text_raw"] and NON_TOURNAMENT_MARK in card["text_raw"]:
        return "non_tournament_official"
    return None

def gifs(s):
    return GIF_RE.findall(s or "")

def to_int(s):
    s = (s or "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        m = re.search(r"-?\d+", s)
        return int(m.group()) if m else None

def split_abilities(text):
    if not text:
        return []
    out = []
    # robust line-break split: matches <br>, <br/>, <br />, </br>, <BR>, <bR >, < br > etc.
    # (the source data has malformed/cased break tags; if missed, two abilities merge into one row)
    for part in re.split(r"<\s*/?\s*br\s*/?\s*>", text, flags=re.IGNORECASE):
        clean = TAG_RE.sub("", part)
        clean = GIF_RE.sub(r"\1", clean).strip()   # [[bounce.gif]] -> bounce
        if not clean:
            continue
        markers = []                                # capture stacked 【...】 (e.g. 【自】【カウンター】)
        m = re.match(r"^(【[^】]+】)\s*", clean)
        while m:
            markers.append(m.group(1))
            clean = clean[m.end():]
            m = re.match(r"^(【[^】]+】)\s*", clean)
        timing = next((TIMING[x] for x in markers if x in TIMING), None)  # AUTO/CONT/ACT or None
        out.append({"markers": markers, "type": timing, "text": clean.strip()})
    return out

def clean_card(c):
    traits = [c.get(k) for k in ("feature1", "feature2", "feature3")]
    traits = [t for t in traits if t and t != "-"]
    color_g = gifs(c.get("color"))
    code = c.get("title_number")
    d = {
        "id":          c.get("id"),
        "card_number": c.get("card_number"),
        "series":      code,                          # card-code prefix (作品番号)
        "neo_titles":  CODE2TITLES.get(code, []),     # Neo Standard series name(s)
        "name":        c.get("card_name"),
        "name_kana":   c.get("card_name_kana"),
        "type":        CARD_KIND.get(str(c.get("card_kind")), "?:" + str(c.get("card_kind"))),
        "card_kind_raw": c.get("card_kind"),
        "color":       color_g[0] if color_g else COLOR_FALLBACK.get((c.get("color") or "").strip(), (c.get("color") or None)),
        "level":       to_int(c.get("level")),
        "cost":        to_int(c.get("cost")),
        "power":       to_int(c.get("power")),
        "soul":        len(gifs(c.get("soul"))),
        "trigger":     gifs(c.get("card_trigger")),
        "traits":      traits,
        "rare":        c.get("rare"),
        "side_raw":    c.get("side"),
        "side":        SIDE.get(str(c.get("side")), c.get("side")),
        "expansion":   c.get("expansion"),
        "parallel":    c.get("variation"),
        "text_raw":    c.get("text"),
        "abilities":   split_abilities(c.get("text")),
        "picture":     c.get("picture"),
    }
    ov = OVERRIDES.get(d["card_number"])
    if ov:
        d.update(ov)                                   # fix source errors
    return d

def main():
    with io.open(RAW, encoding="utf-8") as f:
        raw = json.load(f)

    clean = [clean_card(c) for c in raw]

    # ---- EXCLUSION: flag (not delete) joke/unmeasurable cards ----
    for c in clean:
        r = exclude_reason(c)
        c["excluded"] = bool(r)
        c["exclude_reason"] = r
    excluded = [c for c in clean if c["excluded"]]
    chars_kept = [c for c in clean if c["type"] == "Character" and not c["excluded"]]

    # ---- AUDIT: verify the decodings against reality ----
    audit = {
        "n_raw": len(raw),
        "n_clean": len(clean),
        "excluded_total": len(excluded),
        "excluded_by_reason": dict(Counter(c["exclude_reason"] for c in excluded).most_common()),
        "characters_kept": len(chars_kept),
        "overrides_applied": list(OVERRIDES.keys()),
        "neo_titles_total": len({n for c in clean for n in c["neo_titles"]}),
        "cards_without_neo_title": sum(1 for c in clean if not c["neo_titles"]),
        "card_kind_values": {},
        "color_values": dict(Counter(c["color"] for c in clean).most_common()),
        "side_values": dict(Counter(str(c["side_raw"]) for c in clean).most_common()),
        "trigger_values": dict(Counter(t for c in clean for t in c["trigger"]).most_common()),
        "soul_distribution": dict(Counter(c["soul"] for c in clean).most_common()),
        "no_power_count": sum(1 for c in clean if c["power"] is None),
        "no_level_count": sum(1 for c in clean if c["level"] is None),
        "distinct_series": len({c["series"] for c in clean}),
    }
    # For each card_kind, show a sample + which numeric fields are populated
    by_kind = defaultdict(list)
    for c in clean:
        by_kind[str(c["card_kind_raw"])].append(c)
    for k, lst in sorted(by_kind.items()):
        s = lst[0]
        audit["card_kind_values"][k] = {
            "count": len(lst),
            "sample_card": s["card_number"],
            "sample_name": s["name"],
            "has_level": sum(1 for x in lst if x["level"] is not None),
            "has_power": sum(1 for x in lst if x["power"] is not None),
            "has_soul>0": sum(1 for x in lst if x["soul"] > 0),
            "mapped_type": s["type"],
        }

    with io.open(CLEAN, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False)
    with io.open(AUDIT, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    print("clean cards:", len(clean), "-> ", os.path.basename(CLEAN))
    print("excluded:", len(excluded), "by", audit["excluded_by_reason"])
    print("characters kept:", len(chars_kept))
    print("neo titles:", audit["neo_titles_total"], "| cards w/o title:", audit["cards_without_neo_title"])
    print("audit ->", os.path.basename(AUDIT))

if __name__ == "__main__":
    main()
