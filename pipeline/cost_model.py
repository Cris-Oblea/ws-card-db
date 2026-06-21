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
def pb(c):   # vanilla (ability-less) base power. Validated on 99.7% of vanilla characters.
    t = 1 if "soul" in (c.get("trigger") or []) else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*t - 1000*(c["soul"]-1)
def ra(c):   # real abilities = non-empty ability rows (drop dash placeholders)
    return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","ｰ","")]
def base_num(cn):  # strip rarity/parallel suffix: DAL/W99-001SP -> DAL/W99-001 (same card, only art differs)
    return re.sub(r"(\d)[A-Za-z]+$", r"\1", cn or "")
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
  ("Burn", r"相手に\d+ダメージ"), ("Heal", r"自分のクロック[^。]{0,20}(控え室|ストック|手札|思い出)に置"),
  ("Clock Kick", r"相手のキャラ[^。]{0,20}(クロック置場|クロックに)置"),
  ("Bounce", r"相手のキャラ[^。]{0,12}手札に戻"), ("Return to Deck", r"相手の(控え室|キャラ)[^。]{0,20}山札に(戻|加え)"),
  ("Reverse Opp", r"相手のキャラ[^。]{0,12}【リバース】"), ("Opp Disrupt", r"相手の(手札|ストック|山札|思い出|レベル置場|クロック)"),
  ("Salvage", r"自分の(控え室|思い出)[^。]{0,22}手札に(戻す|加える)"), ("Search", r"山札[^。]{0,14}見[てる][^。]{0,28}(手札|加える)"),
  ("Look Deck", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見"), ("Comeback", r"(控え室|山札)[^。]{0,22}キャラ[^。]{0,14}舞台に置"),
  ("Stock Gen", r"(山札の上|デッキトップ|山札の上から)[^。]{0,12}ストック置場に置"), ("Draw", r"引く"),
  ("Add to Hand", r"手札に(加える|加え|戻す)"), ("Power Pump (board)", r"あなたの[^。]{0,16}(キャラ|「N」|《T》)すべてに[^。]{0,8}パワーを[＋+]"),
  ("Power Pump (self)", r"このカードのパワーを[＋+]"), ("Power Pump", r"キャラ[^。]{0,10}パワーを[＋+]"),
  ("Power Debuff", r"パワーを[－\-]"), ("Soul", r"ソウルを[＋+\-－]"), ("Level", r"レベルを[＋+\-－]"),
  ("Grant Ability", r"』を与える|の能力を得"), ("Mill (self)", r"山札の上から\d+枚を[^。]{0,8}控え室"),
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
CXC_PAT = re.compile(r"クライマックス置場に「N」が(ある|あり)|「N」が(クライマックス置場に)?置かれた|クライマックスコンボ|ＣＸコンボ|CXコンボ")
def family(text):
    if CXC_PAT.search(text): return "CX Combo"   # FIRST: a combo encapsulates whatever sub-effects it mixes
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
CONF = {"measured": "HIGH", "residual": "MEDIUM", "estimated": "LOW", "replay-body": "HIGH"}
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
    if method == "replay-body":
        return "HIGH"
    if method == "measured":
        if (n_samples or 0) >= CONF_MIN_N and (mode_share or 0) >= CONF_MIN_SHARE:
            return "HIGH"
        return "MEDIUM"
    if method == "residual":
        return "MEDIUM"
    return "LOW"   # estimated

CXC_FLOOR = 500   # a CX-combo ability is worth >= 500: the cost is paid by ASSEMBLING the combo, not in power


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
    def family(text): return family(text)
    def is_cxc(self, sig): return family(self.variant_text[sig][1]) == "CX Combo"
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
        sig = self.RP_SIG_OVERRIDE.get((card_number, idx), "".join(markers or "") + " :: " + gen(text or ""))
        if sig in self.cost:
            return (self.cost[sig], self.method[sig],
                    conf_evidence(self.method[sig], self.nsamp.get(sig), self.mshare.get(sig)),
                    family(self.variant_text.get(sig, ("", gen(text or "")))[1]))
        return None, None, None, family(gen(text or ""))

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
        delta = pb(c) - c["power"]
        char_cards.append((c["card_number"], delta, sigs, None))
        if len(ab) == 1:
            iso[sigs[0]].append(delta)

    ALLV = set(variant_occ)
    cost = {}; method = {}; nsamp = {}; rng = {}
    mshare = {}   # sig -> mode_share % of the modal value among pooled MEASURED samples (only measured sigs)

    def is_cxc(sig): return family(variant_text[sig][1]) == "CX Combo"
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
    neg_fams = {family(variant_text[s][1]) for s, c in cost.items() if c < 0}
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
            if val < 0 and family(variant_text[sig][1]) not in neg_fams: continue
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
        if sig in replay_sigs: continue   # structural 0s are not effect costs -> don't bias family medians
        if not is_absorber(sig): fam_known[family(variant_text[sig][1])].append(cst)
    fam_med = {f: r500(st.median(v)) for f, v in fam_known.items()}
    for sig in ALLV:
        if sig in cost or is_absorber(sig): continue
        cost[sig] = fam_med.get(family(variant_text[sig][1]), 500); method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)
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
    # STEP 3c estimate any leftover sig: CXC -> CXC family median (floored), else its family median.
    cxc_known = [c for s, c in cost.items() if is_cxc(s)]
    cxc_med = max(CXC_FLOOR, r500(st.median(cxc_known))) if cxc_known else CXC_FLOOR
    fam_med["CX Combo"] = cxc_med
    for sig in ALLV:
        if sig in cost: continue
        base = cxc_med if is_cxc(sig) else fam_med.get(family(variant_text[sig][1]), 500)
        cost[sig] = base; method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)
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
