# extract_simulator.py — harvest English translations from the unofficial WS simulator.
#
# The simulator (a fan-made Weiss Schwarz game) ships per-set CardData.txt files with English
# NAME, TRAIT1..TRAIT3 and per-ability TEXT, written in roughly the OFFICIAL taxonomy. These fill
# the JP-only gap the official EN list cannot (~21.5k cards that never released in English).
#
# Keys: every entry is keyed by strict_key (publisher + set + normalized number), identical to
# build_db.py. We keep ONLY entries that map to a real JP card ("set parity") — the simulator
# marks renumbered EN sets with an EN/SX/WX prefix, so those produce keys no JP card has and are
# dropped here automatically.
#
# IMPORTANT: the simulator SHARES the official EN list's legacy disparity errors (e.g. the permuted
# BD/W63-102/103/104, and Disgaea only under the renumber DG/ENS03). So these artifacts are the RAW
# source; build_db.py still applies its curated en_card_blocked() exclusions on top when consuming
# them. See documentation/en-name-matching.md.
#
# Usage:  python pipeline/extract_simulator.py ["<path to ...StreamingAssets/Cards>"]
# Output (pipeline/):  name_sim.json {key: name} · traits_sim.json {key: [t1,t2]} ·
#                      abilities_sim.json {key: [text, ...]}
import os, re, json, sys

D = os.path.dirname(os.path.abspath(__file__))
# Date-stamped folder — changes on every simulator re-download. Override via argv[1].
DEFAULT_SIM = r"C:\Users\CRUIZ\Juegos\Weiss Schwarz 0.6.5.2 (本体+DLC整合済み) 19 JUNIO\Weiss Schwarz_Data\StreamingAssets\Cards"
SIM_DIR = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIM

def strict_key(code):   # identical to build_db.py (tolerant of EN's 'E' insertion + parallel suffixes)
    m = re.match(r"([^/]+)/([A-Za-z]+\d+)-(.+)$", code or "")
    if not m: return None
    suf = re.sub(r"(\d)[A-Za-z]+$", r"\1", re.sub(r"^([A-Za-z]*)E(\d)", r"\1\2", m.group(3).upper(), count=1))
    return (m.group(1).upper(), m.group(2).upper(), suf)
def skey_str(code):
    k = strict_key(code)
    return "/".join(k) if k else None

# --- JP cards define the parity set: keep only simulator entries that map to a real JP card ---
clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
JP = {skey_str(c["card_number"]) for c in clean if not c.get("excluded")}
JP.discard(None)
print(f"simulator dir: {SIM_DIR}")
print(f"JP parity keys: {len(JP)}")

CARD = re.compile(r"^(?:Character|Event|Climax|Card)\s*:\s*(\S+)")
names, traits, abilities = {}, {}, {}
seen = set()
files = entries = 0

def commit(cur):
    """Record one parsed card if it maps to a JP card and hasn't been seen (first printing wins)."""
    if not cur or not cur["key"] or cur["key"] not in JP or cur["key"] in seen:
        return
    k = cur["key"]; seen.add(k)
    if cur["name"]:  names[k] = cur["name"]
    tl = [t for t in cur["traits"] if t]
    if tl:           traits[k] = tl
    if cur["texts"]: abilities[k] = cur["texts"]

for root, _, fs in os.walk(SIM_DIR):
    if "CardData.txt" not in fs:
        continue
    files += 1
    cur = None
    with open(os.path.join(root, "CardData.txt"), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.rstrip("\n"); t = s.strip()
            m = CARD.match(t)
            if m:
                commit(cur); entries += 1
                cur = {"key": skey_str(m.group(1)), "name": None, "traits": [], "texts": []}
            elif cur is None:
                continue
            elif s.startswith("Name "):    cur["name"] = s[5:].strip()
            elif s[:5] == "Trait" and s[5:6].isdigit():   # Trait1 / Trait2 / Trait3 (in file order)
                p = s.split(None, 1)
                if len(p) > 1: cur["traits"].append(p[1].strip())
            elif t.startswith("Text "):    cur["texts"].append(t[5:].strip())
            elif t == "EndCard":           commit(cur); cur = None
    commit(cur)   # last card in the file

for fn, obj in (("name_sim.json", names), ("traits_sim.json", traits), ("abilities_sim.json", abilities)):
    with open(os.path.join(D, fn), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=0)

print(f"files={files} card entries={entries} | parity-matched cards={len(seen)}")
print(f"wrote name_sim.json={len(names)}  traits_sim.json={len(traits)}  abilities_sim.json={len(abilities)}")
