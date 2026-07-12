# cost_model.py — THE single source of the power-cost MATH for ws-card-db.
#
# Both build_official_list.py (Excel) and build_db.py (SQLite) import this module so the per-ability
# cost is computed in EXACTLY ONE place. Previously the whole cascade (helpers + taxonomy + replay
# folding + measured->residual->estimated) was duplicated near-verbatim in both builders (and a third
# time in cost_standardize.py); any tweak had to be mirrored by hand, with no guarantee the two
# deliverables stayed in sync. This module removes that risk: the two builders now share ONE codepath.
#
# What lives here: the MATH only (the cost cascade and everything it needs). What stays in the callers:
# all I/O and presentation — openpyxl sheet generation (Excel), SQLite schema/emit, the EN matching /
# exclusion machinery, gzip + cache-bust. Each caller does `build_cost_model(clean)` and reads the
# per-signature / per-ability costs off the returned result.
#
# Era note: the cost no longer depends on era. card_era.json was relabeled to FORMAT names
# (Genesis/Bounty/Gate/Standby/Choice/Horizon), so the old `era == "modern"` test never matched and the
# legacy/modern split was dead code — every sample already pooled into one bucket. The split is removed:
# Step-1 measured is the mode over ALL years. Era/date is metadata, handled by the callers, not by cost.
#
# Standard / suspect layer: build_cost_model exposes, per signature, the STANDARD cost (the mode the model
# uses) plus its EVIDENCE — mode_share (% the modal value takes among pooled measured samples) and n_samples.
# The callers turn that into a per-card residual (real budget - sum of ability standards) and an is_suspect
# flag (|residual| >= 500). Confidence is remapped to reflect that evidence (conf_evidence below).
#
# Payment credits (how much a payment bracket ［…］ buys down) are NOT needed for the per-card cost and are
# kept as a STANDALONE reference in cost_standardize.py (writes analysis/payment_credits.csv); see that file.
#
# Stdlib only. Costs are always multiples of 500 (the game's power economy).
import re, collections, statistics as st, unicodedata

# ---------------- shared helpers ----------------
def _nk(s):  # normalize encoding noise (full/half-width, quote styles, ALL spacing); does NOT change meaning
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
def pb(c):   # vanilla (ability-less) base power. A reverse-engineered linear fit, validated to delta 0 on
    # ALL L0-L2 vanillas. No L3 vanilla is ever printed, but the extrapolation is sound (a theoretical L3
    # cost2/soul1 vanilla = 11500) — do NOT trim it. Over-high L3 deltas come from UNRELIABLE cards
    # (demo/trial/promo, intentionally under-statted) contaminating the samples, NOT from a formula bias.
    t = 1 if "soul" in (c.get("trigger") or []) else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*t - 1000*(c["soul"]-1)
_REMINDER = re.compile(r"[（(].*[）)]", re.S)   # text wholly wrapped in parens = reminder / flavor text
def ra(c):   # real abilities = non-empty rows; drop dash placeholders AND markerless parenthetical reminders
    out = []
    for a in c["abilities"]:
        t = (a.get("text") or "").strip()
        if t in ("-", "ー", "－", "ｰ", ""): continue
        # Markerless text fully wrapped in （）/() is beginner/trigger-icon REMINDER text (e.g. "（bounce：…）",
        # "（このデッキの切り札！…）") — it has no 自/永/起 marker and is not a real ability. Drop it.
        if not a.get("markers") and _REMINDER.fullmatch(t): continue
        out.append(a)
    return out
def base_num(cn):  # strip rarity/parallel suffix: DAL/W99-001SP -> DAL/W99-001 (same card, only art differs)
    return re.sub(r"(\d)[A-Za-z]+$", r"\1", cn or "")
# Reliability of a card as a COST-MEASUREMENT source. Only A-suffix demo / learn-to-play prints (e.g.
# LSS/WE27-A16) use intentionally "closed" (under-curve) stats, so their delta must NOT seed the standard
# (they're still costed & shown — just not measured FROM). Everything else is trustworthy: all P promos
# (mostly on-budget) and every alt-art parallel (SR/RRR/N/SP/SSP/SEC/RE/... = same card, different art,
# identical stats). (User's rule.)
def reliable(c):
    return not re.match(r"^A\d", (c.get("card_number", "") or "").rsplit("-", 1)[-1])
ZT = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")
TRAIT = re.compile(r"《[^》]*》"); NAME = re.compile(r"「[^」]*」")
def gen(t):
    t = t.translate(ZT); t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    # trait COUNT does not affect cost (user rule): any trait restriction = 1 category. Collapse a list of
    # traits to a single 《T》; only NO-trait (generic) stays distinct (and pricier).
    t = re.sub(r"、?《T》(?:[かや・/／、]《T》)+", "《T》", t)
    return re.sub(r"\s+", " ", t).strip()
def r500(x): return int(round(x/500.0)*500)
def mode500(xs): return collections.Counter(r500(x) for x in xs).most_common(1)[0][0]
def mode500_share(xs):
    """Mode (rounded 500) of xs PLUS the modal value's evidence: (mode, mode_share_pct, n).
    mode_share = % of pooled samples that round to the modal value -> the standard's reliability."""
    rounded = [r500(x) for x in xs]
    cnt = collections.Counter(rounded)
    mode, mode_n = cnt.most_common(1)[0]
    return mode, round(100.0 * mode_n / len(rounded), 1), len(rounded)

# ---------------- taxonomy: family + ability type ----------------
KW = {"助太刀":"Backup","応援":"Assist","集中":"Brainstorm","アンコール":"Encore","経験":"Experience",
      "記憶":"Memory","絆":"Bond","チェンジ":"Change","加速":"Accelerate","共鳴":"Resonance",
      "シフト":"Shift","大活躍":"Great Performance","フォース":"Force","ヒール":"Heal","バウンス":"Bounce"}
FAMPAT = [
  ("Burn", r"相手に\d+ダメージ"),
  # A heal = move from the TOP OF YOUR CLOCK to ANY zone (waiting / stock / hand / memory / bottom-deck).
  # ALL heal types are ONE family — they all cost ~1000 power (to a resource zone you pay an extra cost,
  # e.g. discard/kill, so it nets neutral). Detected BEFORE the generic Stock Boost / Add to Hand / Card
  # Select that wrongly stole the "ストック置場" / "手札に(戻|加)" wordings (the old single 'ストック'/'手札'
  # pattern missed them).
  ("Heal", r"自分のクロック[^。]{0,18}(控え室に置|ストック置場に置|手札に(戻|加)|思い出|山札の下に置)"),
  ("Clock Kick", r"相手のキャラ[^。]{0,20}(クロック置場|クロックに)置"),
  # Bounce = return an OPPONENT character to hand. 相手の…キャラ allows a qualifier (前列の / 後列の / レベルN以下の)
  # between 相手の and キャラ, so "相手の前列のキャラを1枚選び、手札に戻す" is caught here instead of leaking to the
  # Add to Hand (戻す) / Card Select (選) grab-bags. Distance to 手札に戻 kept tight so a "when opp char reverses,
  # return THIS card to hand" (self-return) does NOT match.
  ("Bounce", r"相手の[^。]{0,10}キャラ[^。]{0,14}手札に戻"), ("Return to Deck", r"相手の(控え室|キャラ)[^。]{0,20}山札に(戻|加え)"),
  ("Reverse Opp", r"相手のキャラ[^。]{0,12}【リバース】"), ("Opp Disrupt", r"相手の(手札|ストック|山札|思い出|レベル置場|クロック)"),
  # RevealTopSalvage: reveal the DECK TOP, then salvage a (often level-X-gated) character from the waiting
  # room. A costlier salvage MECHANIC (the cheap discard-only prints measure ~2000) — checked BEFORE generic
  # Salvage so it peels off. Payment still drives the per-sig cost; the family is for grouping/estimate. (User.)
  ("RevealTopSalvage", r"山札[^。]{0,10}公開[^。]{0,50}控え室[^。]{0,34}手札に(戻|加え)"),
  ("Salvage", r"自分の(控え室|思い出)[^。]{0,34}手札に(戻|加え)"),
  # Search = look at your DECK and take a card to HAND. Two phrasings: 見る (look) and 公開 (reveal the top,
  # then conditionally add). The reveal-top dig crosses a sentence break (…公開する。…なら手札に加え), so its
  # branch uses . (not [^。]) to bridge it; 山札…公開 anchors it to own-deck reveal, 手札に加え to taking to hand.
  # RevealTopSalvage (reveal -> salvage from 控え室) is checked earlier, so only the plain deck-dig lands here.
  ("Search", r"山札[^。]{0,14}見[てる][^。]{0,28}(手札|加える)|山札[^。]{0,10}公開.{0,90}手札に加え"),
  # Look & Reorder = look at top N then put them back in ANY order (好きな順番) — a scry/setup, distinct from a
  # plain "look" (no reorder = cards return in their original order). Checked BEFORE the generic Look Deck;
  # AFTER Search (a look that TAKES to hand is a Search, not a reorder). User taxonomy.
  ("Look & Reorder", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見[^。]{0,30}好きな順番"),
  ("Look Deck", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見"), ("Comeback", r"(控え室|山札)[^。]{0,22}キャラ[^。]{0,14}舞台に置"),
  ("Stock Gen", r"(山札の上|デッキトップ|山札の上から)[^。]{0,12}ストック置場に置"),
  # Add to Hand: a card ends up in hand. 戻す (return) is included, but NOT "このカードを手札に戻す" — returning THIS
  # card to hand is almost always a PAYMENT (［このカードを手札に戻す］ cost bracket), so letting it match here stole
  # the ability from its real EFFECT family (…パワーを＋N / ソウルを＋N / draw). The negative lookbehind lets those
  # fall through to Power Pump / Soul / Draw. (Returning an OTHER own char — そのキャラ/「N」を…手札に戻す — still matches.)
  ("Add to Hand", r"手札に(加える|加え)|(?<!このカードを)手札に戻す"), ("Power Pump (board)", r"あなたの[^。]{0,16}(キャラ|「N」|《T》)すべてに[^。]{0,8}パワーを[＋+]"),
  # Draw = 引く/引き. Placed AFTER the pump families on purpose: a "draw N and pump" combo (引き…パワーを＋) is a
  # combat trick whose meaningful cost is the pump (and Power Pump (self) carries the multiplicative cabling), so
  # pump wins; only a pure draw (typically draw-then-discard "loot") falls through to Draw. 引き = continuative
  # (the sentence keeps going, e.g. 引き、…控え室に置く) — the bare 引く missed it, leaking loot to Card Select.
  ("Power Pump (self)", r"このカードのパワーを[＋+]"), ("Power Pump", r"キャラ[^。]{0,16}パワーを[＋+]"), ("Draw", r"引[くき]"),
  ("Power Debuff", r"パワーを[－\-]"), ("Soul", r"ソウルを[＋+\-－]"), ("Level", r"レベルを[＋+\-－]"),
  ("Mill (self)", r"山札の上から\d+枚を[^。]{0,8}控え室"),
  ("Move", r"(前列|後列|別の枠|横の枠|の枠)に[^。]{0,6}(動かす|置く|移動)"), ("Stand/Rest", r"【スタンド】|【レスト】"),
  ("Stock Boost", r"ストック置場に置"), ("Choice", r"次の効果から|から\d+つを選"),
  ("Early Play", r"レベル\d+以下[^。]{0,12}手札からプレイ|レベルを参照しない"),
  ("Cannot Attack", r"アタックできない|サイドアタックできない"), ("Restriction", r"できない|選べない|受けない"),
  ("Card Select", r"\d+枚(まで)?選"),
]
# CX Combo: an ability HARD-GATED to a specific named climax. Detected on the gen()-normalized text
# (names already collapsed to 「N」) by the climax-area gate, NOT by the 【CXコンボ】 marker (legacy
# cards predate it). Two gate shapes + the explicit modern marker:
#   クライマックス置場に「N」が(ある|あり)  = "if [name] is in your climax area" (the classic combo trigger)
#   「N」が(クライマックス置場に)?置かれた     = "when [name] is placed (in the climax area)" (on-place flavor)
#   クライマックスコンボ / ＣＸコンボ / CXコンボ = the explicit tagged marker (kept for the few oddballs)
# Deliberately NOT matched: あなたのクライマックスが…置かれた ("when ANY/your climax is placed"), which is a
# generic on-climax trigger, not gated to a specific combo CX -> it must keep its own family.
CXC_PAT = re.compile(r"(クライマックス|CX|ＣＸ)置場に「N」が(ある|あり)|「N」が((クライマックス|CX|ＣＸ)置場に)?置かれた|クライマックスコンボ|ＣＸコンボ|CXコンボ")
# On-reverse families (user taxonomy): when THIS card is reversed, a specific revenge / self effect. Checked
# BEFORE the generic families because "そのキャラを【リバース】" / "山札の下に置く" / "思い出にする" would otherwise
# fall to Other. RedBomb* = trade the opponent away; AutoKick* = the card removes ITSELF on reverse.
ONREV_PAT = [
    ("RedBombLevelX",    re.compile(r"【リバース】した時.*公開.*バトル相手のレベルが[ＸX]以下.*【リバース】してよい")),
    ("AntiEarlyRedBomb", re.compile(r"【リバース】した時.*バトル相手のレベルが相手のレベルより高い.*【リバース】してよい")),
    ("RedBombLevel0",    re.compile(r"【リバース】した時.*バトル相手のレベルが0以下.*【リバース】してよい")),
    ("AutoKickToBottom", re.compile(r"【リバース】した時.*このカードを山札の下に置く")),
    ("AutoKickToMemory", re.compile(r"【リバース】した時.*このカードを思い出にする")),
]
# Modal effect = "choose 1 of the next N effects" — cost the CHOICE as its own family, NOT by whichever
# sub-effect happens to match first (a "look-3 OR heal-1" must NOT pollute the Heal family — that's how a
# family never converges). Requires the CHOOSING (…のうち…選 / 次の効果から…選), so a "do both" bundle
# (次の2つの効果を…行う) is deliberately NOT a modal.
MODAL_PAT = re.compile(r"(次の[\dＸ０-９]+つの効果のうち|次の効果から)[^。]{0,16}選")
# Grant = someone GAINS an auto/cont/act ability (give OR gain): 次の能力を与える / 『…』を与える / 能力を得る /
# 『…』を得る. Detected EARLY, like Modal, because the GRANTED ability's text (a look-deck, a heal, an encore,
# "cannot move"…) must NOT decide the family. Requires "能力を" or "』を" before 与え/得, so it does NOT match
# "ダメージを与える" (deal damage) nor "『…』を持つ" (HAS the ability — that's a condition, e.g. an Assist target).
GRANT_PAT = re.compile(r"(能力を|』を)(与え|得)")
# Dual-nature "Pump & Grant": a SINGLE ability that BOTH pumps power AND grants an ability, e.g.
# "そのターン中、このカードのパワーを＋N し、…次の能力を得る。『【自】…』". The pump must live in the CITING text
# (OUTSIDE the granted 『…』 quote) — a pump that sits INSIDE the quote is just a GRANT OF A PUMP ability,
# not a dual effect, and stays a pure grant. Detected at the same priority as the bare grant (before
# KW/FAMPAT) so the pump aspect is no longer swallowed by the Grant Ability label. The pump regexes are
# reused VERBATIM from FAMPAT (no drift). Cost-neutral by construction: the dual sigs' measured/residual
# costs are signature-keyed (family-independent) and the dual family median equals the Grant median, so no
# estimate moves either.
_PUMP_RES = [re.compile(p) for n, p in FAMPAT if n.startswith("Power Pump")]
_GRANTED_QUOTE = re.compile(r"『[^』]*』")
def _is_citing_pump(text):
    return any(p.search(_GRANTED_QUOTE.sub("", text)) for p in _PUMP_RES)  # pump must be in the CITING text
def family(text, markers=""):
    # CX Combo FIRST (a combo encapsulates whatever sub-effects it mixes): the official 【CXコンボ】 MARKER is
    # the definitive signal; also the climax-area gate in the text (incl. the "CX置場" abbreviation).
    if "CXコンボ" in markers or "ＣＸコンボ" in markers or CXC_PAT.search(text): return "CX Combo"
    if MODAL_PAT.search(text): return "Modal"          # a "choose 1 of N" modal — its own family
    if GRANT_PAT.search(text):                         # grants an ability — its own family, not what's granted
        return "Pump & Grant" if _is_citing_pump(text) else "Grant Ability"  # dual if it also pumps (outside the quote)
    for name, pat in ONREV_PAT:
        if pat.search(text): return name
    for k, v in KW.items():
        if k in text: return v
    for name, pat in FAMPAT:
        if re.search(pat, text): return name
    return "Other"
def ability_type(markers):
    m = "".join(markers or "")
    if "永" in m: return "CONT"
    if "自" in m: return "AUTO"
    if "起" in m: return "ACT"
    return "OTHER"

# A NO-OP ability: an AUTO/CONT/ACT whose WHOLE effect is just declaring/saying a quote ("…と宣言してよい")
# with no game action — no resource, no opponent interaction, no power change. It costs 0 (a structural
# zero, like a replay body, but a SEPARATE category). The declaration must be the LAST clause ($), so a
# card that declares THEN does something real (e.g. then both players search) is NOT matched.
NOOP_PAT = re.compile(r"[「『][^」』]*[」』]と(宣言し|言っ)て(も)?よい[。\s]*$")
def is_noop(text): return bool(NOOP_PAT.search(text or ""))

# ---------------- EN-side cost math (for English-EXCLUSIVE WX/SX cards) ----------------
# Same methodology as JP, applied over the ENGLISH ability text. The caller owns the EN-card iteration
# and dedup; this module owns the cost MATH (gen_en, en_family, and en_cost_model below).
def gen_en(t):   # generalize EN ability text (trait/name -> placeholder, KEEP numbers), like JP gen()
    t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    t = re.sub(r"、?《T》(?:[ /／・]《T》)+", "《T》", t)
    return re.sub(r"\s+", " ", t).strip().lower()
def en_family(t):   # ordered, precise EN family detection (CX combo / burn / clock-kick BEFORE heal)
    tl = re.sub(r"\s+", " ", t.lower())
    if "cxcombo" in tl.replace(" ", "").replace("【", "").replace("】", "") or "cx combo" in tl: return "CX Combo"
    if re.search(r"deal \d+ damage to your opponent", tl): return "Burn"
    if "into your opponent's clock" in tl or "into their clock" in tl: return "Clock Kick"  # field disruption
    if re.search(r"(top card of |a card from )?your clock[^.]{0,40}your waiting room", tl): return "Heal"  # OWN clock only
    for fam, kw in (("Backup", "backup"), ("Assist", "assist"), ("Brainstorm", "brainstorm"),
                    ("Encore", "encore"), ("Experience", "experience"), ("Memory", "memory")):
        if kw in tl: return fam
    if re.search(r"return[^.]{0,40}opponent[^.]{0,20}(character|hand)", tl): return "Bounce"
    if re.search(r"(look at|reveal|search)[^.]{0,40}deck", tl): return "Search"
    if "your waiting room" in tl and " hand" in tl: return "Salvage"
    if "draw" in tl: return "Draw"
    if re.search(r"[+\-]\d+ power", tl): return "Power Pump"
    if re.search(r"[+\-]\d+ soul", tl): return "Soul"
    return "Other"

# ---------------- replay folding helpers ----------------
# A 【リプレイ】 (REPLAY) is NEVER a standalone effect: its text is not AUTO/CONT/ACT, it is the BODY of a
# CITING ability (an AUTO/CONT/ACT that names it via "〔action〕する / を発動する / を使用する / トリガー").
# The replay "develops" wherever it is cited, so its cost belongs to the citer and is counted ONCE.
REPLAY_MARK = "【リプレイ】"
_RP_VERB = re.compile(r"^(を発動する|を発動|を使用する|を使用|をトリガー|する)")
def _rp_action_prefixes(rtext):
    r = rtext.strip(); cands = []
    for m in re.finditer(r"[\s　]+", r): cands.append(r[:m.start()])   # raw prefixes (keep internal spaces)
    cands.append(r)
    return sorted({x for x in cands if len(x.strip()) >= 2}, key=len, reverse=True)   # longest (most specific) first
def _rp_find_citer(rtext, abs_, ri):
    for cand in _rp_action_prefixes(rtext):
        for j, a in enumerate(abs_):
            if j == ri or REPLAY_MARK in "".join(a.get("markers") or []): continue
            ct = a.get("text") or ""; idx = ct.find(cand)
            while idx != -1:
                after = ct[idx + len(cand):]
                if _RP_VERB.match(after) or re.match(r"^[。、，）\)]", after) or after == "":
                    return j, cand
                idx = ct.find(cand, idx + 1)
    return None, None

# Method -> base confidence. Kept as a plain dict so the Excel builder (build_official_list.py) can still
# subscript CONF[method] for its method-based label. The DB uses conf_evidence() below, which UPGRADES a
# measured sig to HIGH only when its standard has real evidence (n>=3 AND mode_share>=60).
CONF = {"measured": "HIGH", "residual": "MEDIUM", "estimated": "LOW", "replay-body": "HIGH", "noop": "HIGH"}
# Evidence thresholds for the DB confidence remap (see conf_evidence()).
CONF_MIN_N = 3        # a HIGH standard needs at least this many pooled measured samples
CONF_MIN_SHARE = 60   # ...AND the modal value must take at least this % of them

def conf_evidence(method, n_samples, mode_share):
    """Confidence that reflects the STANDARD's evidence, not just the method:
      HIGH      = 'measured' AND n_samples >= 3 AND mode_share >= 60  (a tight, well-sampled mode)
      HIGH      = 'replay-body' (structural zero — always certain)
      MEDIUM    = 'residual', OR 'measured' with weaker n / mode_share
      LOW       = 'estimated' (sparse, no reliable mode)
    n_samples / mode_share may be None (residual/estimated sigs carry no pooled measured mode)."""
    if method in ("replay-body", "noop"):
        return "HIGH"
    if method == "measured":
        if (n_samples or 0) >= CONF_MIN_N and (mode_share or 0) >= CONF_MIN_SHARE:
            return "HIGH"
        return "MEDIUM"
    if method == "residual":
        return "MEDIUM"
    return "LOW"   # estimated

CXC_FLOOR = 500   # a CX-combo ability is worth >= 500: the cost is paid by ASSEMBLING the combo, not in power

# ---- partial cabling: Power Pump (self) multiplicative estimate (see documentation/pump_cost_model.md) ----
# For an ESTIMATED self-pump sig, replace the flat family-median GUESS (which ignores N entirely — it gives a
# +500 and a +8000 pump the same value) with the owner's multiplicative model: base N x (1/2)^(temporal +
# #conditions). base = the printed +N (text-readable); a permanent unconditional pump keeps full N; "during
# your turn" and each なら/場合 gate halve it. Only THIS family is cabled (its base is readable); the
# net-advantage families (salvage/search/…) need card-flow understanding the parser does not have. Beats the
# flat median on the MEASURED pumps (84% vs 75% within +/-500), and only touches estimated (LOW) sigs.
_PUMP_SELF_N = re.compile(r"このカードのパワーを[＋+](\d+)")
_PUMP_TEMP   = re.compile(r"ターン中|ターンの終わりまで|そのターン")
_PUMP_COND   = re.compile(r"なら|場合|いれば")
_PUMP_SCALE  = re.compile(r"につき|枚数")
def pump_self_estimate(gen_text):
    """Multiplicative estimate for a Power Pump (self) gen sig; None if N is unreadable or the pump SCALES
    per-unit (base is not a flat N). Floored at 500 (a real pump effect costs at least 500)."""
    if _PUMP_SCALE.search(gen_text): return None
    mt = _PUMP_SELF_N.search(gen_text)
    if not mt: return None
    n = int(mt.group(1))
    if n <= 0: return None
    k = (1 if _PUMP_TEMP.search(gen_text) else 0) + len(_PUMP_COND.findall(gen_text))
    return max(500, r500(n * (0.5 ** k)))


class CostModel:
    """Result of build_cost_model(clean). Holds the per-signature cost cascade and the lookups both
    builders need. The MATH is done in build_cost_model; this object just exposes the results:
      cost/method/nsamp/rng  — per-signature dicts (signature = ''.join(markers) + ' :: ' + gen(text))
      variant_text           — sig -> (markers, gen_text)
      variant_occ            — sig -> [(card_number, idx, markers, text)]  (occurrences)
      RP_SIG_OVERRIDE        — (card_number, idx) -> signature (folded citer / verbatim replay body)
      REPLAY_SIGS, CITER_SIGS, RP_ORPHANS  — replay-folding bookkeeping
      char_cards             — [(card_number, delta, [sig...], era)]  Character cards used as samples
      fam_med                — family -> median cost (incl. "CX Combo")
    Methods: family(), is_cxc(), is_absorber(), ab_cost(), conf(), and the EN pass en_cost(...)."""
    def __init__(self, cost, method, nsamp, rng, mshare, variant_text, variant_occ,
                 rp_sig_override, replay_sigs, citer_sigs, rp_orphans, char_cards, fam_med, allv):
        self.cost = cost; self.method = method; self.nsamp = nsamp; self.rng = rng
        self.mshare = mshare   # sig -> mode_share % of the modal value among pooled measured samples (None if N/A)
        self.variant_text = variant_text; self.variant_occ = variant_occ
        self.RP_SIG_OVERRIDE = rp_sig_override
        self.REPLAY_SIGS = replay_sigs; self.CITER_SIGS = citer_sigs; self.RP_ORPHANS = rp_orphans
        self.char_cards = char_cards; self.fam_med = fam_med; self.ALLV = allv

    # taxonomy passthroughs (so callers can use the model object as the one entry point)
    @staticmethod
    def family(text, markers=""): return family(text, markers)
    def is_cxc(self, sig): return family(self.variant_text[sig][1], self.variant_text[sig][0]) == "CX Combo"
    def is_absorber(self, sig): return self.is_cxc(sig) or sig in self.CITER_SIGS

    # --- the per-signature STANDARD and its evidence (the converged model's price list) ---
    def std(self, sig): return self.cost.get(sig)              # standard cost = the model's per-signature value
    def mode_share(self, sig): return self.mshare.get(sig)     # % the modal value takes (None for residual/estimated)
    # nsamp(sig) already lives on self.nsamp (number of pooled samples behind the standard)

    def conf(self, sig_or_method):
        """Evidence-aware confidence. Pass a SIGNATURE (preferred — uses its n_samples + mode_share) or,
        for backward compat, a raw method string (falls back to the method-only CONF dict)."""
        if sig_or_method in self.method:
            sig = sig_or_method
            return conf_evidence(self.method[sig], self.nsamp.get(sig), self.mshare.get(sig))
        return CONF.get(sig_or_method)   # legacy: a bare method string

    def ab_cost(self, card_number, idx, markers, text):
        """cost/method/confidence/family for one ability instance (None cost if not a measurable
        Character ability). Honors the replay sig override (folded citer / zeroed replay body).
        Confidence is evidence-aware (conf_evidence over the sig's n_samples + mode_share)."""
        mk = "".join(markers or "")
        sig = self.RP_SIG_OVERRIDE.get((card_number, idx), mk + " :: " + gen(text or ""))
        if sig in self.cost:
            vt = self.variant_text.get(sig, (mk, gen(text or "")))
            return (self.cost[sig], self.method[sig],
                    conf_evidence(self.method[sig], self.nsamp.get(sig), self.mshare.get(sig)),
                    family(vt[1], vt[0]))
        return None, None, None, family(gen(text or ""), mk)

    def ab_std(self, card_number, idx, markers, text):
        """standard_cost / mode_share / n_samples for one ability instance (None,None,0 if not measurable).
        Honors the replay sig override. standard_cost == the model's value (cost[sig])."""
        sig = self.RP_SIG_OVERRIDE.get((card_number, idx), "".join(markers or "") + " :: " + gen(text or ""))
        if sig in self.cost:
            return self.cost[sig], self.mshare.get(sig), self.nsamp.get(sig, 0)
        return None, None, 0


def _fold_replays(clean):
    """Pass 1 of the cascade: detect each 【リプレイ】 and FOLD its body into its citing ability.
    Returns (RP_SIG_OVERRIDE, REPLAY_SIGS, CITER_SIGS, RP_ORPHANS)."""
    rp_sig_override = {}; replay_sigs = set(); citer_sigs = set(); rp_orphans = []
    for c in clean:
        if c["type"] != "Character" or c["excluded"]: continue
        abs_ = ra(c)
        for ri, a in enumerate(abs_):
            if REPLAY_MARK not in "".join(a.get("markers") or []): continue
            rtext = (a.get("text") or "").strip()
            cj, cand = _rp_find_citer(rtext, abs_, ri)
            if cj is None:                                   # no citer on this card -> leave the replay untouched
                rp_orphans.append((c["card_number"], rtext[:40])); continue
            reff = rtext[len(cand):].lstrip(" 　!！")          # replay EFFECT = replay text minus the leading action
            cmk = "".join(abs_[cj].get("markers") or []); rmk = "".join(abs_[ri].get("markers") or [])
            csig = cmk + " :: " + gen((abs_[cj].get("text") or "") + " " + reff)   # fold body into the citer sig
            rsig = rmk + " :: " + gen(rtext)
            rp_sig_override[(c["card_number"], cj)] = csig
            rp_sig_override[(c["card_number"], ri)] = rsig
            citer_sigs.add(csig); replay_sigs.add(rsig)
    return rp_sig_override, replay_sigs, citer_sigs, rp_orphans


def build_cost_model(clean):
    """Run the FULL measured -> residual -> estimated cascade over the (already de-duplicated) clean JP
    Character cards and return a CostModel. This is the single source of the per-ability power cost; both
    build_official_list.py and build_db.py call it and read the results off the returned object.

    `clean` = the de-duplicated cardlist_clean rows (the CALLER does its own de-dup, which differs between
    the two builders — that I/O detail is intentionally NOT in this module)."""
    rp_sig_override, replay_sigs, citer_sigs, rp_orphans = _fold_replays(clean)

    # collect Character abilities: per-signature occurrences + isolated single-ability deltas (pooled over
    # ALL years -- NO era split: the cost no longer depends on era).
    variant_occ = collections.defaultdict(list)   # sig -> [(card, idx, markers, text)]
    iso = collections.defaultdict(list)           # sig -> [isolated single-ability delta...]  (one pool, all years)
    variant_text = {}                              # sig -> (markers, gen_text)
    noop_sigs = set()                              # sigs whose whole effect is a no-op declaration -> cost 0
    char_cards = []                                # (card_number, delta, [sig...], era)  -- era kept as metadata only
    for c in clean:
        if c["type"] != "Character" or c["excluded"]: continue
        if c["power"] is None or c["level"] is None or c["cost"] is None or c["soul"] is None: continue
        ab = ra(c)
        if not ab: continue
        sigs = []
        for i, a in enumerate(ab):
            mk = "".join(a.get("markers") or [])
            sig = rp_sig_override.get((c["card_number"], i), mk + " :: " + gen(a.get("text", "")))
            sigs.append(sig)
            variant_occ[sig].append((c["card_number"], i, mk, a.get("text", "")))
            variant_text.setdefault(sig, (mk, sig.split(" :: ", 1)[1]))   # gen text from the sig (folded for citers)
            if is_noop(a.get("text", "")): noop_sigs.add(sig)             # "declare 『X』" and nothing else -> 0
        delta = pb(c) - c["power"]
        char_cards.append((c["card_number"], delta, sigs, None))
        if len(ab) == 1 and reliable(c):      # only normal prints seed the measured standard (no demo A-prints)
            iso[sigs[0]].append(delta)

    ALLV = set(variant_occ)
    cost = {}; method = {}; nsamp = {}; rng = {}
    mshare = {}   # sig -> mode_share % of the modal value among pooled MEASURED samples (only measured sigs)

    def fam_of(sig): return family(variant_text[sig][1], variant_text[sig][0])   # text + markers (honors 【CXコンボ】)
    def is_cxc(sig): return fam_of(sig) == "CX Combo"
    # A residual ABSORBER soaks a card's leftover delta (delta - sum(others)) instead of being
    # measured/estimated in isolation. Two kinds: CX-combo sigs (gated + pay-to-assemble, hardest to
    # measure directly) AND replay CITER sigs (they carry the folded replay body, counted once on the
    # citer). Both are deferred out of the NON-absorber residual (step 2) and the NON-absorber family
    # estimate (step 3a), then absorbed in step 3b.
    def is_absorber(sig): return is_cxc(sig) or sig in citer_sigs

    # STEP 0 replay bodies -> 0. The 【リプレイ】 row is NOT a standalone effect (its body was folded into
    # the citer sig above); fix it at 0 BEFORE step 1 (method "replay-body", HIGH-confidence structural 0).
    for sig in replay_sigs:
        if sig in ALLV:
            cost[sig] = 0; method[sig] = "replay-body"; nsamp[sig] = 0; rng[sig] = (0, 0)
    # STEP 0b no-op declares -> 0. An ability whose whole effect is "declare 『X』" does nothing (no
    # resource / no opponent interaction / no power) -> structural 0 (method "noop", HIGH confidence).
    for sig in noop_sigs:
        if sig in ALLV and sig not in cost:
            cost[sig] = 0; method[sig] = "noop"; nsamp[sig] = 0; rng[sig] = (0, 0)
    # STEP 1 measured -- single-ability cards, mode over ALL years (no era split).
    for sig, samples in iso.items():
        if sig in cost: continue                       # a zeroed replay body is already fixed at 0
        if not samples: continue
        # a single isolated sample is unstable -> don't lock it as HIGH measured; let the multi-card
        # residual (or family estimate) give it a sane value instead. (Unified guard: build_official_list
        # had this, build_db lacked it; keeping it here is the single behavior change of the refactor.)
        if len(samples) == 1: continue
        mode, share, n = mode500_share(samples)
        cost[sig] = mode; method[sig] = "measured"; nsamp[sig] = n; rng[sig] = (min(samples), max(samples)); mshare[sig] = share
    # families that may legitimately cost NEGATIVE (drawbacks) = those seen negative in MEASURED data
    neg_fams = {fam_of(s) for s, c in cost.items() if c < 0}
    multi = [(cn, dl, sg, e) for (cn, dl, sg, e) in char_cards if len(sg) > 1]
    # STEP 2 NON-absorber residual: solve the lone unknown ONLY when it is NOT an absorber sig (CXC or
    # citer). A still-unknown absorber keeps its card "unresolved" here -> deferred to step 3b.
    for _ in range(10):
        res = collections.defaultdict(list)
        for cn, dl, sg, e in multi:
            unk = [s for s in sg if s not in cost]
            if len(unk) == 1 and not is_absorber(unk[0]):
                res[unk[0]].append(dl - sum(cost[s] for s in sg if s in cost))
        new = 0
        for sig, samples in res.items():
            if sig in cost: continue
            val = mode500(samples)
            # a beneficial ability can't be a drawback: a negative residual means the seeds over-counted
            # -> reject it, let step 3 estimate a sane positive.
            if val < 0 and fam_of(sig) not in neg_fams: continue
            cost[sig] = val; method[sig] = "residual"; nsamp[sig] = len(samples); rng[sig] = (min(samples), max(samples)); new += 1
        if new == 0: break
    # checkpoint validation: measured+residual only (estimated/unresolved excluded), same basis as before.
    errs = [abs(dl - sum(cost[s] for s in sg)) for cn, dl, sg, e in multi if all(s in cost for s in sg)]
    validation_pct = (sum(1 for x in errs if x <= 500) / len(errs) * 100) if errs else None
    validation_n = len(errs)
    # STEP 3a NON-absorber family estimate: give every remaining NON-absorber sig a value NOW, so the only
    # unknown left on an absorber card is its CXC / citer sig (step 3b then absorbs it from the delta).
    fam_known = collections.defaultdict(list)
    for sig, cst in cost.items():
        if sig in replay_sigs or sig in noop_sigs: continue   # structural 0s are not effect costs -> don't bias family medians
        if not is_absorber(sig): fam_known[fam_of(sig)].append(cst)
    fam_med = {f: r500(st.median(v)) for f, v in fam_known.items()}
    for sig in ALLV:
        if sig in cost or is_absorber(sig): continue
        cost[sig] = fam_med.get(fam_of(sig), 500); method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)
    # STEP 3b absorber residual ABSORBER: with all non-absorber sigs known, derive each CXC / citer sig
    # from the cards where it is now the lone unknown -> absorber = delta - sum(others). CXC floored at
    # >= 500; a citer floored at >= 0 (the folded replay body never gives power back to the card).
    for _ in range(10):
        res = collections.defaultdict(list)
        for cn, dl, sg, e in multi:
            unk = [s for s in sg if s not in cost]
            if len(unk) == 1 and is_absorber(unk[0]):
                res[unk[0]].append(dl - sum(cost[s] for s in sg if s in cost))
        new = 0
        for sig, samples in res.items():
            if sig in cost: continue
            v = mode500(samples)
            cost[sig] = max(CXC_FLOOR, v) if is_cxc(sig) else max(0, v); method[sig] = "residual"
            nsamp[sig] = len(samples); rng[sig] = (min(samples), max(samples)); new += 1
        if new == 0: break
    # STEP 3b2 ESTIMATED upgrade: a NON-absorber sig that only ever co-occurred with an unresolved absorber
    # (CXC / citer) was "trapped" at step 2 -> it fell to a family-median GUESS in 3a. Now that every absorber
    # has a value (3b), that sig may be the lone unknown on its card and can be solved from the card's OWN
    # delta instead of the guess. Same mode + drawback (negative) guard as step 2; only sigs still flagged
    # "estimated" are replaced, and ONLY when every OTHER sig on the card is non-estimated (so the residual
    # equation uses trusted terms). Iterated, since one upgrade can unlock another.
    for _ in range(10):
        res = collections.defaultdict(list)
        for cn, dl, sg, e in multi:
            unk = [s for s in sg if method.get(s) == "estimated"]
            # solvable iff every OTHER sig is RESOLVED (in cost) and TRUSTED (not itself a 3a guess)
            if len(unk) == 1 and all(s in cost and method.get(s) != "estimated" for s in sg if s != unk[0]):
                res[unk[0]].append(dl - sum(cost[s] for s in sg if s != unk[0]))
        new = 0
        for sig, samples in res.items():
            if method.get(sig) != "estimated": continue
            val = mode500(samples)
            if val < 0 and fam_of(sig) not in neg_fams: continue   # beneficial sig can't be a drawback (as step 2)
            cost[sig] = val; method[sig] = "residual"; nsamp[sig] = len(samples)
            rng[sig] = (min(samples), max(samples)); new += 1
        if new == 0: break
    # STEP 3c estimate any leftover sig: CXC -> CXC family median (floored), else its family median.
    cxc_known = [c for s, c in cost.items() if is_cxc(s)]
    cxc_med = max(CXC_FLOOR, r500(st.median(cxc_known))) if cxc_known else CXC_FLOOR
    fam_med["CX Combo"] = cxc_med
    for sig in ALLV:
        if sig in cost: continue
        base = cxc_med if is_cxc(sig) else fam_med.get(fam_of(sig), 500)
        cost[sig] = base; method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)
    # STEP 3d partial cabling: override the flat-median ESTIMATE of Power Pump (self) sigs with the
    # multiplicative model (estimated-only; measured/residual untouched). Stays method "estimated" (LOW) —
    # still a guess, just an N-scaled one instead of a flat family median.
    for sig in ALLV:
        if method.get(sig) != "estimated" or fam_of(sig) != "Power Pump (self)": continue
        est = pump_self_estimate(variant_text[sig][1])
        if est is not None: cost[sig] = est
    # enforce the CXC floor on EVERY CX-combo sig (incl. a single-ability measured combo below 500)
    for sig in ALLV:
        if is_cxc(sig) and cost[sig] < CXC_FLOOR: cost[sig] = CXC_FLOOR

    m = CostModel(cost, method, nsamp, rng, mshare, variant_text, variant_occ,
                  rp_sig_override, replay_sigs, citer_sigs, rp_orphans, char_cards, fam_med, ALLV)
    m.validation_pct = validation_pct; m.validation_n = validation_n
    return m


def en_cost_model(jp_arows, ex_cards, fam_med):
    """EN-EXCLUSIVE cost pass: same methodology as JP, over the ENGLISH text. The CALLER owns the EN-card
    iteration / dedup and builds:
      jp_arows  = the JP ability rows already emitted, each a tuple whose [5]=en_text and [6]=power_cost
                  (only rows with an EN text AND a known JP cost feed the cross-measurement).
      ex_cards  = the de-duplicated EN-exclusive cards, each a dict with keys:
                  is_char (bool), delta (int|None), sigs ([(idx, atype, raw_en_text, gen_en_sig)...])
      fam_med   = the JP family medians (reused to estimate EN sigs with no measurement).
    Returns (encost, enmethod): sig -> cost / method. ENCONF maps method -> confidence in the caller."""
    # (a) raw JP costs per EN-sig (keep ALL samples to combine with EN measurements -> robust mode)
    xs = collections.defaultdict(list)
    for r in jp_arows:                               # JP abilities only
        if r[5] and r[6] is not None: xs[gen_en(r[5])].append(r[6])
    # (b) single-ability EN-exclusive Character deltas, per EN-sig
    en_direct = collections.defaultdict(list)
    for c in ex_cards:
        if c["is_char"] and len(c["sigs"]) == 1 and c["delta"] is not None:
            en_direct[c["sigs"][0][3]].append(c["delta"])
    # (c) base cost per EN-sig = MODE of all samples (JP cross + EN single-ability deltas)
    encost = {}; enmethod = {}
    for s in set(xs) | set(en_direct):
        encost[s] = mode500(xs.get(s, []) + en_direct.get(s, []))
        enmethod[s] = "measured" if s in en_direct else "matched"
    # (d) residual on multi-ability EN cards (fill the one unknown from delta - sum(known))
    multi = [c for c in ex_cards if c["is_char"] and len(c["sigs"]) > 1 and c["delta"] is not None]
    for _ in range(10):
        res = collections.defaultdict(list); new = 0
        for c in multi:
            unk = [s for (_, _, _, s) in c["sigs"] if s not in encost]
            if len(unk) == 1:
                res[unk[0]].append(c["delta"] - sum(encost[s] for (_, _, _, s) in c["sigs"] if s in encost))
        for s, vals in res.items():
            if s in encost: continue
            encost[s] = mode500(vals); enmethod[s] = "residual"; new += 1
        if new == 0: break
    # (e) estimate the rest by family median (reuse the JP family medians) -- Characters only
    for c in ex_cards:
        if not c["is_char"]: continue
        for (_, _, txt, s) in c["sigs"]:
            if s not in encost: encost[s] = fam_med.get(en_family(txt), 500); enmethod[s] = "estimated"
    # (f) CX-combo / hard-gate floor: such an ability is worth >= 500 (you pay by assembling the combo)
    for c in ex_cards:
        if not c["is_char"]: continue
        for (_, _, txt, s) in c["sigs"]:
            if en_family(txt) == "CX Combo" and encost.get(s, 0) < 500:
                encost[s] = 500; enmethod[s] = "estimated"
    return encost, enmethod


ENCONF = {"measured": "HIGH", "matched": "MEDIUM", "residual": "MEDIUM", "estimated": "LOW"}
