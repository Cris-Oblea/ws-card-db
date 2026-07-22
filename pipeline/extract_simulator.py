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
# MACROS: some abilities are written as a single scripted shorthand line, e.g.
# "*GainPowerWithEnoughCharacters(5000,2,Granblue)", instead of a Text line -- the simulator's game
# engine only needs the macro to RUN the effect, not a prose description, so plenty of simple
# mechanical abilities (flat pumps, assists, encores...) have no English text at all in the raw
# file. pipeline/sources/macros.tsv (curated reference, not code) maps each macro name to an
# English template with placeholders (POWER, NUMBER, TRAITLIST, ...); we substitute the macro
# call's own arguments into that template so these abilities get real English too, instead of
# silently staying blank. Confirmed 2026-07-22: about a quarter of all simulator cards have at
# least one macro-only ability with no Text line, so skipping this would leave ~25% incomplete.
#
# Usage:  python pipeline/extract_simulator.py ["<path to ...StreamingAssets/Cards>"]
# Output (pipeline/):  name_sim.json {key: name} · traits_sim.json {key: [t1,t2]} ·
#                      abilities_sim.json {key: [text, ...]}
import os, re, json, sys, csv

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

# --- macro -> English template, loaded from the curated reference table (fallback source) ---
MACROS = {}
with open(os.path.join(D, "sources", "macros.tsv"), encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        MACROS[row["macro"]] = row["description"]

# --- macro -> (exact param names, template), parsed LIVE from the simulator's own engine source
# (StreamingAssets/CommonEffects(copy).txt, a sibling of the Cards folder) -- this is the actual
# definition the game runs, so it's authoritative and even NAMES each parameter in its own
# declaration order (e.g. "Define: OnPlayMillGainPowerForEach(NUMBER,POWER,TRAITLIST)" -- notice
# NUMBER comes before POWER here, contradicting the fixed-priority guess PLACEHOLDER_ORDER above
# has to make for the curated-only fallback). We only read this file at RUNTIME, never copy its
# content into the repo: it's the simulator's own internal source, a step further from what we're
# comfortable redistributing than the user's own hand-curated macros.tsv (see NOTICE.md -- this
# project already deliberately avoids naming/describing the simulator itself in public docs).
MACROS_CE = {}
def _load_common_effects(sim_dir):
    # StreamingAssets/Cards -> StreamingAssets/CommonEffects(copy).txt (one level up from Cards).
    path = os.path.join(os.path.dirname(sim_dir.rstrip("\\/")), "CommonEffects(copy).txt")
    if not os.path.isfile(path):
        return
    DEFINE = re.compile(r"^Define:\s*(\w+)(?:\((.*)\))?\s*$")
    name, params, text_lines = None, [], []
    def flush():
        if name and text_lines:   # only keep it if the engine itself gives a Text line
            MACROS_CE[name] = (params, text_lines[0])
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.strip()
            m = DEFINE.match(t)
            if m:
                flush()
                name = m.group(1)
                params = [p.strip() for p in m.group(2).split(",")] if m.group(2) else []
                text_lines = []
            elif t.startswith("Text "):
                text_lines.append(t[5:].strip())
        flush()

# Placeholder tokens a template can contain, in the FIXED order the macro's own positional
# arguments are written in (verified against real calls, e.g. GainPowerWithEnoughCharacters
# (POWER,NUMBER,TRAITLIST) and OnActGivePower(POWER,TIMESPERTURN) -- POWER always comes first when
# present, a small count/times-per-turn number comes next, and a trait/name/requirement string
# comes last). This is NOT the order the words appear in the template's prose -- e.g.
# GainPowerWithEnoughCharacters's text says "...TRAITLIST...NUMBER...POWER" but its arguments are
# (POWER, NUMBER, TRAITLIST). So placeholders are matched to arguments by this priority list, not
# by where they sit in the sentence.
# "X" is deliberately NOT a placeholder: templates only ever use it to EXPLAIN a computed value in
# prose ("+X power where X is 500 times that character's level"), never as something we substitute
# -- treating it as one caused false failures (e.g. LevelAssist takes 0 args; its "X" is narrative).
PLACEHOLDER_ORDER = ["POWER", "TIMESPERTURN", "NUMBER", "TRAITLIST", "CARDNAME", "NAME", "REQUIREMENT", "COLOR"]

def split_macro_args(argstr):
    """Split a macro call's comma-separated arguments, respecting a backslash-escaped comma
    inside a single argument (card names sometimes contain a real comma, e.g. 'Hero of Biscotti\\, Cinque')."""
    if argstr == "":
        return []
    parts, buf, i = [], "", 0
    while i < len(argstr):
        if argstr[i] == "\\" and i + 1 < len(argstr) and argstr[i + 1] == ",":
            buf += ","; i += 2; continue     # un-escape \, -> , and keep it IN the current argument
        if argstr[i] == ",":
            parts.append(buf); buf = ""; i += 1; continue
        buf += argstr[i]; i += 1
    parts.append(buf)
    return [p.strip() for p in parts]

def humanize_traitlist(v):
    # Multiple traits are pipe-separated in the raw call ("Master|Servant|Homunculus"); render as
    # readable English. "Any" is the engine's own keyword for "no trait restriction" -- keep as-is,
    # it already reads fine ("Choose 1 of your Any characters" isn't used; templates phrase around it).
    return " or ".join(v.split("|"))

def _sub_token(text, token, value):
    # A CommonEffects Text line sometimes writes a param bare ("NUMBER cards") and sometimes with a
    # literal $ prefix ("$TRAITLIST characters") for the exact same parameter -- match either form.
    pattern = r"\$?(?<!\w)" + re.escape(token) + r"(?!\w)"
    return re.sub(pattern, lambda _m: value, text)

def synthesize_from_common_effects(name, args):
    """Try the authoritative, engine-sourced definition first: exact param names in their OWN
    declared order, no guessing. Returns None if this macro isn't defined there (caller falls back
    to the curated macros.tsv heuristic) or if the argument count doesn't match."""
    entry = MACROS_CE.get(name)
    if entry is None:
        return None
    params, template = entry
    if len(args) < len(params):    # extra trailing args are fine, same policy as the tsv fallback
        return None
    text = template
    for param, val in zip(params, args):
        if "|" in val:
            val = humanize_traitlist(val)
        text = _sub_token(text, param, val)
    return text

def synthesize_macro(name, argstr_or_none):
    """Return the English text for one macro line, or None if the macro/args can't be resolved
    (caller then just skips this ability line rather than emit something wrong)."""
    args = split_macro_args(argstr_or_none) if argstr_or_none is not None else []
    ce = synthesize_from_common_effects(name, args)
    if ce is not None:
        return ce
    template = MACROS.get(name)
    if template is None:
        return None
    # Which placeholders does this template actually use, in our fixed priority order? A literal
    # "_" is a handful of templates' own placeholder spelling (e.g. "deal _ damage") -- treat it as
    # one more numeric slot, checked right after NUMBER since it plays the same role.
    has_minmax = "MIN-MAX" in template
    has_underscore = re.search(r"(?<!\w)_(?!\w)", template) is not None
    # Word-boundary check, NOT plain substring -- "NAME" is literally contained inside "CARDNAME",
    # so a naive `p in template` would wrongly detect BOTH and demand an extra phantom argument.
    present = [p for p in PLACEHOLDER_ORDER if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", template)]
    if has_underscore:
        present.insert(min(2, len(present)), "_")   # numeric slot, same priority band as NUMBER
    needed = len(present) + (2 if has_minmax else 0)   # MIN-MAX consumes 2 positional args on its own
    # Extra trailing args beyond what the ENGLISH needs are fine (the game engine may pass more than
    # the description mentions, e.g. an internal trait key the template doesn't narrate) -- only a
    # SHORTFALL means we can't safely fill every placeholder, so only bail out on that.
    if len(args) < needed:
        return None
    text = template
    i = 0
    if has_minmax:                                      # MIN-MAX is always the pair of args (checked first
        text = text.replace("MIN-MAX", f"{args[0]}-{args[1]}")   # in practice it's the only placeholder)
        i = 2
    for ph in present:
        val = args[i]; i += 1
        if ph == "TRAITLIST":
            val = humanize_traitlist(val)
        token = "_" if ph == "_" else ph
        text = re.sub(r"(?<!\w)" + re.escape(token) + r"(?!\w)", lambda _m: val, text)  # ALL occurrences
    return text

_load_common_effects(SIM_DIR)
print(f"CommonEffects macros loaded from engine source: {len(MACROS_CE)}"
      + (" (file not found next to Cards/ -- falling back to macros.tsv only)" if not MACROS_CE else ""))

# --- JP cards define the parity set: keep only simulator entries that map to a real JP card ---
clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
JP = {skey_str(c["card_number"]) for c in clean if not c.get("excluded")}
JP.discard(None)
print(f"simulator dir: {SIM_DIR}")
print(f"JP parity keys: {len(JP)}")

CARD = re.compile(r"^(?:Character|Event|Climax|Card)\s*:\s*(\S+)")
MACRO_LINE = re.compile(r"^\*(\w+)(?:\((.*)\))?$")   # "*HexProof" (no args) or "*Name(a,b,...)"
names, traits, abilities = {}, {}, {}
seen = set()
files = entries = 0
macro_hits = macro_misses = 0
unresolved_macros = {}   # macro name -> how many times we failed to synthesize it (for the report)

def commit(cur):
    """Record one parsed card if it maps to a JP card and hasn't been seen (first printing wins)."""
    if not cur or not cur["key"] or cur["key"] not in JP or cur["key"] in seen:
        return
    k = cur["key"]; seen.add(k)
    if cur["name"]:  names[k] = cur["name"]
    tl = [t for t in cur["traits"] if t]
    if tl:           traits[k] = tl
    if cur["texts"]: abilities[k] = cur["texts"]

# CardData.txt is a flat, line-oriented format: a "Character: CODE" line opens a card, then Name/Trait*/
# Text* lines describe it, until "EndCard" (or the next card header). We parse it as a small state machine:
# `cur` is the card being accumulated; committing a card resets it.
#
# One ability = one TOP-LEVEL element: either a bare macro line, or a block ("Auto: Event { ... }")
# whose own "Text " line always ends up back at brace depth 0 once every nested "{...}" inside it has
# closed (verified against real examples). Any block can internally nest a SUB-ability inside itself
# -- a macro sub-action inside a conditional/cost block, or a fully separate "GainEffect { ... Text
# ... }" that temporarily grants another whole ability -- and those inner constructs have their OWN
# Text/macro lines too. But cardlist_clean.json already embeds that inner description as a clause
# INSIDE the outer ability's single JP text, so it must NOT be counted as a second ability, or the
# card's simulator ability count no longer matches JP and build_db.py's alignment check rejects the
# WHOLE card (every ability goes blank, not just the extra one). So: only count a Text/macro line
# when depth == 0 (truly outside every block); anything encountered at depth > 0 is internal to
# whatever ability's block we're currently inside and is silently ignored.
for root, _, fs in os.walk(SIM_DIR):
    if "CardData.txt" not in fs:
        continue
    files += 1
    cur = None
    depth = 0
    with open(os.path.join(root, "CardData.txt"), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.rstrip("\n"); t = s.strip()
            m = CARD.match(t)
            if m:                                        # new card header -> commit the previous, start fresh
                commit(cur); entries += 1
                cur = {"key": skey_str(m.group(1)), "name": None, "traits": [], "texts": []}
                depth = 0
            elif cur is None:
                continue                                 # lines before the first card header -> ignore
            elif s.startswith("Name "):    cur["name"] = s[5:].strip()
            elif s[:5] == "Trait" and s[5:6].isdigit():   # Trait1 / Trait2 / Trait3 (kept in file order)
                p = s.split(None, 1)
                if len(p) > 1: cur["traits"].append(p[1].strip())
            elif t.startswith("Text "):
                if depth == 0:                  # only a TOP-LEVEL Text line is its own ability; one
                    cur["texts"].append(t[5:].strip())   # nested inside a block describes a clause
                                                          # already embedded in the outer ability's JP text
            elif t == "EndCard":           commit(cur); cur = None              # explicit card terminator
            else:
                mm = MACRO_LINE.match(t)
                # A macro line IS one ability slot, same as a "Text " line -- appended here, in the
                # same left-to-right scan, so it lands in the correct position relative to any Text
                # lines around it -- but again, only when it's a standalone top-level macro (depth 0),
                # not one nested inside another ability's own block.
                if mm and depth == 0:
                    synth = synthesize_macro(mm.group(1), mm.group(2))
                    if synth:
                        cur["texts"].append(synth); macro_hits += 1
                    else:
                        macro_misses += 1
                        unresolved_macros[mm.group(1)] = unresolved_macros.get(mm.group(1), 0) + 1
            if cur is not None:
                depth += t.count("{") - t.count("}")
    commit(cur)   # last card in the file (no trailing EndCard/header to trigger the commit)

for fn, obj in (("name_sim.json", names), ("traits_sim.json", traits), ("abilities_sim.json", abilities)):
    with open(os.path.join(D, fn), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=0)

print(f"files={files} card entries={entries} | parity-matched cards={len(seen)}")
print(f"wrote name_sim.json={len(names)}  traits_sim.json={len(traits)}  abilities_sim.json={len(abilities)}")
print(f"macro lines synthesized to English: {macro_hits} | unresolved (unknown macro or arg-count mismatch): {macro_misses}")
if unresolved_macros:
    top = sorted(unresolved_macros.items(), key=lambda kv: -kv[1])[:15]
    print("top unresolved macros:", ", ".join(f"{n}x{c}" for n, c in top))
