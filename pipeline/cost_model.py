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
        # Dash-only placeholder rows meaning "no ability" -- several distinct Unicode dash characters show up
        # across the raw JP data (ASCII hyphen, katakana long-vowel mark, fullwidth/halfwidth hyphen, HYPHEN
        # U+2010, HORIZONTAL BAR U+2015): all mean the same "vanilla, no text here", not a real ability.
        if t in ("-", "ー", "－", "ｰ", "‐", "―", ""): continue
        # Markerless text fully wrapped in （）/() is beginner/trigger-icon REMINDER text (e.g. "（bounce：…）",
        # "（このデッキの切り札！…）") — it has no 自/永/起 marker and is not a real ability. Drop it.
        if not a.get("markers") and _REMINDER.fullmatch(t): continue
        # Markerless text starting with ※ is a printed PRINT/LEGALITY notice, never a real ability -- e.g.
        # "cannot be used in official/sanctioned tournaments", "domestic/overseas distribution only", "treated
        # as the same-name card as X, the English print can't be used in JP-run tournaments", date-gated ban
        # notices, foil-type notices. Verified: every real markerless ※ row in the corpus (94 total) is one of
        # these, none are gameplay text.
        if not a.get("markers") and t.startswith("※"): continue
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
# ｢｣ (halfwidth corner brackets, U+FF62/FF63) are a rare print-style variant of the standard fullwidth
# quoting brackets 「」 (same meaning, same NAME-collapsing target) -- a handful of prints (mostly the whole
# GC/S16-* set) use them instead. Left un-mapped, NAME.sub below can't recognize them, so a name like
# ｢王の素質｣ never collapses to 「N」, which silently breaks every FAMPAT/CXC_PAT/KW check downstream that
# expects the 「N」 placeholder (21 abilities corpus-wide, mostly CX-Combo-gated abilities that were
# misclassifying into whatever generic family the un-collapsed text happened to resemble instead).
ZT = str.maketrans("０１２３４５６７８９＋－｢｣", "0123456789+-「」")
TRAIT = re.compile(r"《[^》]*》"); NAME = re.compile(r"「[^」]*」")
def gen(t):
    t = t.translate(ZT); t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    # trait COUNT does not affect cost (user rule): any trait restriction = 1 category. Collapse a list of
    # traits to a single 《T》; only NO-trait (generic) stays distinct (and pricier). と (and) added to the
    # connector class -- some prints join a long trait list with と instead of か/や/・/／/、 (e.g. a 9-trait
    # "《本》と《ヒトデ》と《演劇》と…" self-identity grant); safe to add since と only fires here when it's directly
    # sandwiched between two 《T》 placeholders, which can only happen in a real trait list. Confirmed via
    # Kcl/WE50-51.
    t = re.sub(r"、?《T》(?:[かやとも・/／、]《T》)+", "《T》", t)
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
# KW = keyword mechanics that ARE the effect (the keyword names what the ability DOES), so they legitimately
# pre-empt the FAMPAT effect-text match. DELIBERATELY EXCLUDED are the CONDITION/state keywords 記憶 (Memory:
# "if you have a card in memory"), 経験 (Experience: "if your level-zone level-sum >= N") and 共鳴 (Resonance:
# "［reveal a named card from hand］"): these merely GATE a separate effect, so the ability must be filed by what
# it actually does (…このカードのパワーを＋N -> Power Pump (self), a search -> Search, …), NOT diverted to a keyword
# family. Their effects scatter across every family — a keyword family for a condition never converges, and it
# hid pumps/searches from the multiplicative estimate (the memory/experience "…なら" then reads as a ÷2 condition).
KW = {"助太刀":"Backup","応援":"Assist","集中":"Brainstorm","アンコール":"Encore",
      "絆":"Bond","チェンジ":"Change","加速":"Accelerate",
      "シフト":"Shift","大活躍":"Great Performance","フォース":"Force","ヒール":"Heal",
      "バウンス":"Removal (Hand)",  # official keyword name for the same effect as the FAMPAT text-pattern below
      "継承":"AddMarker (Self)"}  # official keyword: THIS card (+ its own markers) becomes a marker under
      # a newly-played ally -- the "self" source variant of the AddMarker (...) family group (see below)
FAMPAT = [
  # Widened to also accept SYMMETRIC "deal damage to ALL players" (すべてのプレイヤーに) — the user: still a
  # Burn, just a symmetric one (you take the same hit too).
  ("Burn", r"相手に(\d+|[ＸX])ダメージ|すべてのプレイヤーに、?(\d+|[ＸX])ダメージ"),   # Ｘ (variable) damage — deck-mill burns deal 相手にＸダメージ, missed by \d+
  # Damage Reflect: a distinct family from Burn even though the final effect is also "opponent takes damage"
  # -- the AMOUNT here is variable by mirroring whatever damage you just took (相手に同じダメージを与える, "deal
  # the SAME damage"), not a printed fixed number, and the trigger mechanism (uncancelled damage received
  # during this card's battle) is completely different from Burn's usual on-play/on-attack triggers. Kept
  # separate so its cost standard isn't blended with fixed-number Burn's. Confirmed by the user via
  # KS/W49-001 and KI/S44-077 (same core phrase, different payment-cost brackets).
  # Gap crosses a sentence break (the optional-payment "…てよい。そうしたら、…" wrapper sits between the trigger
  # and the payoff), so needs . (not [^。]) like the Modal/Search conditional-payoff patterns elsewhere.
  # Gap widened 40->60: a longer ［cost］…そうしたら、… payment wrapper (condition + pay-cost bracket) pushed
  # past the old limit. Confirmed via VS/W50-T18.
  ("Damage Reflect", r"あなたの受けたダメージがキャンセルされなかった時.{0,60}相手に同じダメージを与える"),
  # Multi Trigger Check: during this attack, check for a trigger N times instead of once (N is usually 2,
  # occasionally more — generalized to any digit rather than hardcoding "Double", since the per-signature
  # measured cost already scales naturally with whatever N a specific card prints). A well-known WS mechanic
  # that had NO family at all before this pass (330+ occurrences landing in Other). User taxonomy.
  ("Multi Trigger Check", r"トリガーステップにトリガーチェックを[0-9０-９]+回行う"),
  # Side Attack (No Soul Loss): an OFFENSIVE damage tool, not a defensive one (user correction) -- normally
  # side-attacking loses Soul equal to the defender's level minus your Soul, which can make a side attack
  # deal LESS damage than a front attack against a higher-level defender; this ignores that penalty entirely,
  # so you reliably deal full damage via the side attack's other benefits (e.g. bypassing a strong front
  # defender) instead of being punished for using it.
  ("Side Attack (No Soul Loss)", r"サイドアタックしてもソウルが減少しない"),
  # A heal = move from the TOP OF YOUR CLOCK to ANY zone (waiting / stock / hand / memory / bottom-deck).
  # ALL heal types are ONE family — they all cost ~1000 power (to a resource zone you pay an extra cost,
  # e.g. discard/kill, so it nets neutral). Detected BEFORE the generic Stock Boost / Add to Hand / Card
  # Select that wrongly stole the "ストック置場" / "手札に(戻|加)" wordings (the old single 'ストック'/'手札'
  # pattern missed them).
  ("Heal", r"自分のクロック[^。]{0,18}(控え室に置|ストック置場に置|手札に(戻|加)|思い出|山札の下に置)"),
  # Deck Copy Limit: a DECKBUILDING permission, not a gameplay ability at all — raises how many copies of a
  # named card (usually itself) may be run together. Effectively a static rules-text exception with no
  # in-game action, hence a near-zero measured cost. User taxonomy.
  ("Deck Copy Limit", r"デッキに(好きな枚数|(合計)?\d+枚まで)入れることができる"),
  # HandSizeLimit+1 (user's own name): another rules-modifying static, like Deck Copy Limit above — this one
  # literally raises the hand-size cap rather than granting a gameplay action.
  ("HandSizeLimit+1", r"あなたの手札の枚数上限を[＋+]\d+"),
  # Color Bypass: a passive CONT permission letting this card (or a whole card TYPE — events/climaxes) be
  # played ignoring the color requirement. Distinct from Summon (an ACTIVE effect that puts a DIFFERENT
  # character into play bypassing its cost/level) — this is a permanent, intrinsic property of the card
  # itself, no cost paid, no selection. User taxonomy.
  ("Color Bypass", r"色条件を満たさずに(手札から)?プレイできる"),
  # Hexproof: the user's own term (borrowed from a different TCG they know) for "this card cannot be
  # targeted by the opponent's effects" -- a pure protection CONT, no action of its own.
  # 選ばれず (negative continuative, joining a following clause) accepted alongside 選ばれない (negative
  # terminal, ending the sentence) -- same negation, different conjugation because the sentence continues into
  # a 2nd clause (e.g. "…選ばれず、…色を得る。"). Confirmed via PJS/S125-043.
  ("Hexproof", r"このカードは相手の効果に選ばれ(ない|ず)"),
  # Reverse Immunity (Cost 0): a DIFFERENT protection family from Hexproof (user: same category — protection
  # — but a distinct specific mechanic) — conditionally IMMUNE to becoming reversed at all when the character
  # it's battling is cost 0 or lower. A defensive tech common in "Standby"-format decks per the user.
  ("Reverse Immunity (Cost 0)", r"このカードの正面のキャラのコストが0以下なら、このカードは【リバース】しない"),
  # Reverse Immunity generalized the same way as the Bomb family below (user's explicit instruction) --
  # every distinct CONDITION gates a genuinely different real cost, so each gets its own explicit name
  # rather than one broad "Reverse Immunity" bucket. This variant: immune while your hand is large AND
  # you're playing solo (no other own characters) -- a completely different condition from Cost 0, same
  # destination/purpose.
  ("Reverse Immunity (Hand4/Solo)", r"あなたの手札が\d+枚以上で、他のあなたのキャラがいないなら、このカードは【リバース】しない"),
  # Reverse Immunity (Paid): a 3rd variant -- ACTIVE and TEMPORARY (pay a cost, reactively, for immunity
  # only until end of turn), unlike the two passive/permanent CONT variants above. Same destination/purpose
  # (this card can't be reversed), different activation shape -> its own explicit name, same convention.
  ("Reverse Immunity (Paid)", r"あなたはコストを払ってよい。そうしたら、そのターン中、このカードは【リバース】しない"),
  # Reverse Immunity (Grant): a 4th variant, split by WHO it protects rather than what gates it -- every
  # variant above protects THIS card (the one with the ability); this one grants the SAME immunity to a
  # CHOSEN ALLY instead, reactively and payment-gated. Same destination/purpose (that character can't be
  # reversed this turn), different target. User-named (2026-07-23). Confirmed via ALL/S90-080.
  ("Reverse Immunity (Grant)", r"あなたはコストを払ってよい。そうしたら、そのターン中、そのキャラは【リバース】しない"),
  # Reverse Immunity (Level Comparison): a 5th condition variant -- immune whenever this card's battle
  # opponent outlevels the actual opponent PLAYER's own level (a level-race tech). User-named (2026-07-23).
  # Confirmed via SHS/W71-095.
  ("Reverse Immunity (Level Comparison)", r"このカードの正面のキャラのレベルが相手のレベルより高いなら、このカードは【リバース】しない"),
  # Clock Kick is DELIBERATELY NOT a Removal variant, even though it also relocates an opponent's stage
  # character: its real purpose is dealing UNCANCELLABLE damage (bypassing the climax-reveal cancel that a
  # normal Burn allows), using the clock-placement as the delivery mechanism — not board control. Contrast
  # with a "GreenBomb"-style effect (heals 1 damage to the opponent FIRST, then clocks the character): that
  # extra heal step is what marks it as damage-family too. Plain Clock Kick (no heal step) stays its own
  # family. User taxonomy (explicit exclusion).
  # Clock Kick was actually DEAD (0 real matches, confirmed absent from the 69-family catalog) even before
  # this session's other fixes: the original "(クロック置場|クロックに)置" alternation never required the に
  # between 置場 and 置, so it could never match the real phrasing "クロック置場に置く" (needs literal
  # クロック置場に置, not クロック置場+置 with no に) -- a latent bug, not something this session introduced.
  # Fixed by requiring に in BOTH alternatives. Also widened: (1) allow a qualifier between 相手の and キャラ
  # (レベル/コスト/前列 conditions push the old zero-gap "相手のキャラ" literal past its limit); (2) accept
  # "このカードの正面のキャラ" (the character THIS card is facing in combat -- i.e. its battle opponent) as an
  # equivalent way real prints refer to the target without the word 相手.
  # 3rd branch: "そのバトル相手"/"このカードのバトル相手" -- a PRONOUN referring back to a target already fixed by
  # the trigger clause itself (e.g. "このカードのバトル相手が【リバース】した時…そのバトル相手をクロック置場に置く" --
  # SAO/S47-107). No 選び verb here at all: nothing needs to be SELECTED, since the trigger already pinned
  # down which single character is meant. Every other branch needs 選び because it's picking one out of a
  # broader class ("相手の…キャラ" = any matching opponent character); this pronoun form never does.
  # Last branch: antecedent established in an EARLIER trigger clause ("このカードのバトル相手が【リバース】した
  # 時"), then a bare そのキャラ pronoun refers back to it later in the same sentence -- same cross-clause
  # shape as the Removal (Memory) 4th branch below. .{0,60} crosses the gap since it's a different clause.
  # Last branch: a payment-gated variant of the same pronoun-antecedent shape above -- the trigger clause sets
  # up このカードとバトル中のキャラ/このカードのバトル相手 as antecedent, then a ［cost］…そうしたら、…そのキャラを
  # クロック置場に置く payoff follows several sentences later (crosses 。, so needs . not [^。]). Confirmed via
  # PT/W07-031, CTB/W118-047.
  # Last branch: a BULK variant, no 選び (choose) verb -- "相手の前列のキャラすべてを、クロック置場に…置く" removes
  # every qualifying character at once (usually payment-gated), the same "bulk, no selection needed" shape
  # already added to Removal (Waiting Room). Confirmed via GBF/S134-082.
  ("Clock Kick", r"相手の[^。]{0,20}キャラ[^。]{0,20}(クロック置場に置|クロックに置)|このカードの正面のキャラ[^。]{0,10}選(び|んで)[^。]{0,16}(クロック置場に置|クロックに置)|(そのバトル相手|このカードのバトル相手)を?[^。]{0,10}(クロック置場に置|クロックに置)|このカードのバトル相手が【リバース】した時.{0,60}そのキャラを[^。]{0,10}(クロック置場に置|クロックに置)|(このカードとバトル中のキャラ|このカードのバトル相手).{0,90}(あなたは)?そのキャラを[^。]{0,4}クロック置場に置|相手の[^。]{0,10}キャラすべてを[^。]{0,10}クロック置場に[^。]{0,10}置"),
  # Removal (Hand): return an OPPONENT character to hand — same final purpose as every other Removal variant
  # below (get the opponent's stage character out of play), just a different destination. Named per-variant
  # (not one flat "Removal") because the destination materially changes the character's cost to the game:
  # bouncing to hand lets the opponent immediately replay it, so it measures far cheaper than a permanent
  # removal to the bottom of the deck — folding them into one bucket would blur two different cost floors.
  # 相手の…キャラ allows a qualifier (前列の / 後列の / レベルN以下の) between 相手の and キャラ, so "相手の前列のキャラを
  # 1枚選び、手札に戻す" is caught here instead of leaking to the Add to Hand (戻す) / Card Select (選) grab-bags.
  # Distance to 手札に戻 kept tight so a "when opp char reverses, return THIS card to hand" (self-return) does
  # NOT match. (Formerly named "Bounce" — renamed into the Removal(...) group, same regex/cost data.)
  # 2nd branch: same battle-opponent-pronoun gap fixed repeatedly across the Removal(...)/Clock Kick/Reverse
  # Opp/Return to Deck families -- "このカードとバトルしているキャラ" (this card's battle opponent) established as
  # the antecedent in the trigger clause, then a bare そのキャラ pronoun in the payoff. Confirmed via DC/W01-016.
  ("Removal (Hand)", r"相手の[^。]{0,10}キャラ[^。]{0,14}手札に戻|(このカードとバトルしているキャラ|このカードのバトル相手)[^。]{0,20}レベル[^。]{0,20}(あなたは)?そのキャラを[^。]{0,4}手札に戻"),
  # Return to Deck: opponent's waiting-room card(s)/character -> the OPPONENT's OWN deck. Verb widened to
  # also accept 置く (many prints say "山札の上か下に置く" rather than 戻す/加える -- same destination, different
  # phrasing).
  # 2nd branch: same battle-opponent-pronoun gap as Removal (Hand)/Clock Kick/Reverse Opp above -- the
  # antecedent (このカードのバトル相手/バトルしているキャラ/バトル中のキャラ) is set up in the trigger clause, then a
  # bare そのキャラ pronoun in the payoff refers back to it. Confirmed via BM/S15-051, CN/SE02-05.
  ("Return to Deck", r"相手の(控え室|キャラ)[^。]{0,20}山札[^。]{0,6}に(戻|加え|置)|(このカードのバトル相手|このカードとバトルしているキャラ|このカードとバトル中の).{0,80}そのキャラを[^。]{0,4}山札の(上|下)に[^。]{0,8}置"),
  # Retreat (own-stage-char branch): choosing one of YOUR OWN characters currently ON THE STAGE and returning
  # it to hand (a self-bounce/withdrawal). Checked here, BEFORE Add to Hand, because Add to Hand's own negative
  # lookbehind only excludes "このカードを手札に戻す" (see below) -- it does NOT exclude "自分の舞台の…選び…手札に
  #戻す", so without this earlier branch it would win first and steal the label. The "このカードを手札に戻す"
  # (this card retreats itself) branch stays lower in the list, right after Mill (self) -- see that comment.
  # Retreat (own-stage branch), widened: real prints often say "他の自分の…キャラ" (another of your own
  # characters) instead of spelling out the literal word 自分の舞台の -- context already implies the stage
  # (only stage characters are normally choosable by a triggered ability), so the literal-word requirement
  # missed a real chunk of this shape.
  # Third branch: a bare "自分の《T》のキャラ" (no 舞台/他の qualifier at all) -- e.g. an アラーム-gated ability that
  # just says "choose one of your <Trait> characters and return it to hand", relying on context (only stage
  # characters are normally choosable) rather than spelling out either qualifier. MUST exclude 自分の being
  # immediately followed by another explicit source zone (控え室/山札/思い出置場/クロック置場/手札) -- those are
  # Salvage/Summon/Memory Bank/etc.'s territory (e.g. "自分の控え室のキャラを…選び、手札に戻す" is a Salvage, not a
  # stage retreat), and without this exclusion the bare pattern would shadow-steal them since Retreat is
  # checked earlier in the list.
  ("Retreat", r"自分の舞台(の|にいる)[^。]{0,14}(キャラ|「N」)[^。]{0,10}選び[^。]{0,10}手札に戻|他の自分の[^。]{0,14}(キャラ|「N」)[^。]{0,10}選び[^。]{0,10}手札に戻|自分の(?!控え室|山札|思い出置場|クロック置場|手札)[^。]{0,14}(キャラ|「N」)[^。]{0,10}選び[^。]{0,10}手札に戻"),
  # AllMemoryCleanse: a symmetric effect ("すべてのプレイヤーは…") that trims EVERY player's Memory down to a
  # kept amount, sending the rest to that player's own waiting room. Distinct from Salvage/Retreat (those
  # move ONE player's cards, chosen by name/type) — this is a board-wide housekeeping effect that benefits
  # both players equally (fewer cards in Memory = a more compressed deck at the next refresh). The kept-count
  # clause sits inside a 『…』 quoted action block, so the gap to 控え室に置 must cross that sentence break
  # (. not [^。], matching the Modal/Search convention elsewhere in this list). User taxonomy.
  ("AllMemoryCleanse", r"すべてのプレイヤー.{0,90}思い出.{0,60}控え室に置"),
  # Removal (Waiting Room): proactively remove an opponent's STAGE character straight to their waiting room
  # (a kill, not a reverse/bounce/clock-kick — those have their own families). Usually a main-phase on-enter
  # play, e.g. picking off a low-cost/low-level front-row character before the battle phase even starts.
  # Distinct from Opp Disrupt below, which targets the opponent's RESOURCE ZONES (hand/stock/deck/memory/
  # clock), not a character. (Formerly named "Disruption" — renamed into the Removal(...) group, same
  # regex/cost data; user taxonomy.)
  # Gap widened 16->24 (a compound color+trait condition, e.g. "前列のコスト0以下の、緑か《T》の", pushed past
  # the old limit); also accepts "このカードの正面のキャラ" (the character THIS card faces in combat), the same
  # opponent-reference alternative added to Clock Kick above. Also added a 2nd family: Removal (Stock) --
  # a character card is ALWAYS owned by its original controller in Weiss Schwarz (no zone ever mixes cards
  # from different owners), so an unmarked "ストックに置く" destination on an opponent's character can only mean
  # the OPPONENT's OWN stock, not the actor's -- same "get it out of play" purpose as every other Removal
  # variant, just parked in a zone the opponent can later spend as a cost rather than recur from. (User
  # correction: my first write-up wrongly described this as the ACTOR capturing the character into their own
  # stock, which cross-owner mixing rules make impossible.)
  # 3rd branch: a BULK variant with no "選び" (choose) verb at all -- "相手の前列のレベルN以下のキャラすべてを、
  # 控え室に置く" removes every qualifying character at once, so there's nothing to select. Usually gated behind
  # a ［cost］ payment bracket. Confirmed via KK/SPR-002, CL/WE04-10.
  ("Removal (Waiting Room)", r"相手の[^。]{0,24}キャラを[^。]{0,10}選び[^。]{0,10}控え室に置|このカードの正面のキャラ[^。]{0,10}選(び|んで)[^。]{0,10}控え室に置|相手の[^。]{0,10}レベル[^。]{0,8}以下の[^。]{0,10}キャラすべてを.{0,10}控え室に置"),
  # Same battle-opponent-reference gap fixed for Deck Top/Bottom/Memory above -- confirmed via LB/W06-T06 /
  # LB/W06-018 / FH/SE03-001, which were falling through to the late generic "Stock Boost" catch-all
  # (ストック置場に置, checked much later in this list) instead of the earlier, more specific Removal (Stock).
  ("Removal (Stock)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選(び|んで)[^。]{0,16}ストック[^。]{0,4}に置|このカードとバトル(中の|している)[^。]{0,10}キャラ[^。]{0,10}選(び|んで)[^。]{0,16}ストック[^。]{0,4}に置|(そのバトル相手|このカードのバトル相手)を?[^。]{0,10}ストック[^。]{0,4}に置|(このカードのバトル相手|このカードとバトル(中の|している)キャラ)が【リバース】した時.{0,60}そのキャラを[^。]{0,10}ストック[^。]{0,4}に置"),
  # Removal (Deck Bottom) / (Deck Top) / (Memory) / (Swap): the remaining printed destinations that send an
  # opponent's STAGE character elsewhere — same final purpose as Removal (Hand)/(Waiting Room) above (getting
  # the character out of the stage), each split into its OWN meaningfully-named variant rather than one
  # flat "Removal" bucket, because the destination changes the cost floor (a permanent bottom-of-deck removal
  # denies recursion much harder than a temporary Memory removal that returns the character at the next
  # Encore step, which in turn differs from a forced swap that still leaves the opponent a replacement).
  # Swap: the opponent must replace the removed character with a weaker one pulled from their OWN waiting
  # room; the strong character still leaves the stage, so it's a Removal variant, not a different mechanic.
  # Its 入れ替える sits after a second, nested "相手は…選び" clause, so it needs the wide . gap (crossing the
  # sentence break some prints put before it) instead of [^。]. User taxonomy.
  # 2nd branch: "このカードのバトル相手"/"このカードとバトル中のキャラ" -- ways real prints refer to the opponent's
  # character WITHOUT the possessive 相手の (they mean the same thing: the character this card is battling).
  # Pronoun branches (そのバトル相手/このカードのバトル相手, no 選び needed -- see the Clock Kick comment above for
  # why: the trigger clause already pinned down the single target). "山札の上か下に置" (attacker's choice of
  # top OR bottom) is folded in here too rather than split into its own family -- it's the same permanent-
  # removal purpose, just letting the attacker pick the position.
  # "そのバトル中のキャラ" ("that battling character") is a 5th way real prints refer back to a pronoun antecedent
  # established earlier in the trigger clause (このカードとバトル中のキャラが【リバース】した時…そのバトル中のキャラを…) --
  # same shape as そのバトル相手/このカードのバトル相手 above, just a different pronoun phrasing. Confirmed via ID/W10-093.
  ("Removal (Deck Bottom)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選(び|んで)[^。]{0,16}山札の下に置|このカードのバトル相手[^。]{0,20}選(び|んで)[^。]{0,16}山札の下に置|このカードとバトル(中の|している)[^。]{0,10}キャラ[^。]{0,10}選(び|んで)[^。]{0,16}山札の下に置|(そのバトル相手|このカードのバトル相手)を?[^。]{0,10}山札の(下に置|上か下に置)|このカードのバトル相手が【リバース】した時.{0,60}そのキャラを[^。]{0,10}山札の下に置|このカードとバトル(中の|している)キャラが【リバース】した時.{0,60}そのバトル中のキャラを[^。]{0,10}山札の下に置"),
  # Deck Top was missing the "このカードとバトルしているキャラが【リバース】した時" trigger-pronoun branch that its
  # Deck Bottom sibling already had -- the same battle-opponent-reference gap class fixed repeatedly elsewhere
  # this session (Bomb's _BOMB_OPP, Clock Kick, Removal (Stock)). Found via DC/W01-059.
  ("Removal (Deck Top)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選(び|んで)[^。]{0,16}山札の上に置|このカードとバトル(中の|している)[^。]{0,10}キャラ[^。]{0,10}選(び|んで)[^。]{0,16}山札の上に置|(そのバトル相手|このカードのバトル相手)を?[^。]{0,10}山札の上に置|(このカードのバトル相手|このカードとバトル(中の|している)キャラ)が【リバース】した時.{0,60}そのキャラを[^。]{0,10}山札の上に置"),
  # Verb widened にし -> にし|にする (dictionary form, no polite/optional suffix -- some prints phrase this as a
  # flat mandatory action, "…選び、思い出にする。", not "…にしてよい/にします").
  # 4th branch: "このカードのバトル相手が【リバース】した時…そのキャラを思い出に…" -- the ANTECEDENT (このカードのバトル
  #相手) is established in the TRIGGER clause, and そのキャラ (a bare pronoun) refers back to it later in the
  # sentence, crossing the '.{0,60}' gap between them. This is a genuine "removal on reverse" (needs the
  # opponent to already be reversed via combat before it can be removed) -- distinct from the RedBomb/Blue
  # Bomb family above (those trigger on THIS card's OWN reverse, not the opponent's). User taxonomy.
  # Same battle-opponent-reference gap fixed for Deck Top/Bottom above -- confirmed via KF/S05-032
  # ("このカードとバトル中のキャラが【リバース】した時...そのキャラを思い出にする").
  ("Removal (Memory)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選(び|んで)[^。]{0,16}(思い出にし|思い出にする)|このカードの正面のキャラ[^。]{0,10}選(び|んで)[^。]{0,16}(思い出にし|思い出にする)|(そのバトル相手|このカードのバトル相手)を?[^。]{0,10}(思い出にし|思い出にする)|(このカードのバトル相手|このカードとバトル(中の|している)キャラ)が【リバース】した時.{0,60}そのキャラを[^。]{0,10}(思い出にし|思い出にする)"),
  ("Removal (Swap)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選(び|んで).{0,90}入れ替え"),
  # ReviveOpponent (provisional name, pending user confirmation): the reverse of Removal — put a character
  # from the OPPONENT's OWN waiting room onto a stage slot. Since a character always stays owned by its
  # original controller, an unmarked "舞台" here can only mean the OPPONENT's stage: this "revives" an
  # opponent character so a later reverse-requiring finisher/removal effect of your OWN has a legal target
  # (some opponents deliberately empty their board to deny exactly that). User taxonomy / RSL/S56-002.
  ("ReviveOpponent", r"相手の控え室の[^。]{0,20}キャラを[^。]{0,10}選び[^。]{0,14}(舞台|前列|後列)の[^。]{0,10}枠に置"),
  # Opp Disrupt widened: (1) added 控え室 (waiting room) -- previously only hand/stock/deck/memory/level-zone/
  # clock were covered, missing a common "force the opponent to reset/thin their own waiting room" shape.
  # (2) added the REFLEXIVE construction 相手は自分の… (the opponent, acting on THEIR OWN zone -- 自分 here
  # is the opponent's own reflexive, not the acting player's) alongside the possessive 相手の…, since most
  # real prints phrase it "相手は自分の控え室のCXを1枚選び、そのカード以外を…山札に戻し…" (topic marker 相手は, not
  # possessive 相手の) and the literal-possessive-only pattern silently missed all of them.
  # 2nd branch: the same battle-opponent-pronoun antecedent shape used across the whole Removal(...)/Clock
  # Kick/Return to Deck cluster -- このカードのバトル相手/このカードとバトルしているキャラ established as antecedent in
  # the trigger, then a bare そのキャラ/そのバトル中のキャラ/そのバトル相手 pronoun in the payoff forces the REVERSE.
  # Often wrapped in a 共鳴/経験 condition + ［cost］ bracket, so the gap to the payoff must cross a 。 (use .
  # not [^。]). Confirmed via WTR/S85-014, SBY/W136-017, LS/W05-059, NM/S24-056, FS/S36-055, TL/W37-073.
  ("Reverse Opp", r"相手のキャラ[^。]{0,12}【リバース】|(このカードのバトル相手|このカードとバトルしているキャラ|そのバトル相手)[^。]{0,20}レベル[^。]{0,40}その(バトル中の)?キャラ(を|は)?[^。]{0,4}【リバース】(する|してよい)|(このカードのバトル相手).{0,60}その(バトル相手|キャラ)を?[^。]{0,4}【リバース】する"),
  # 3rd branch: wipe all markers in the marker area tied to one of the OPPONENT's stage slots -- confirmed
  # by the user as a kind of disruption, even though it doesn't literally say 相手の(zone) since the zone is
  # referenced indirectly via "the marker area corresponding to that [chosen opponent] slot."
  # 4th branch: locking the opponent OUT of their own [ACT] abilities is a kind of disruption too, same as
  # denying a resource zone above -- user taxonomy (2026-07-23): "hay diferentes formas de hacer disruption al
  # oponente, hacer que no pueda usar act es una de ellas" (there are different ways to disrupt the opponent;
  # preventing ACT use is one of them). Confirmed via LB/W02-E11, N1/WE06-17. NOTE: this is checked earlier in
  # the list than Look & Reorder, so a compound ability that ALSO has a look/reorder clause in the same text
  # (e.g. NIK/S117-052) now files as Opp Disrupt instead -- a real, deliberate side effect of this fold, not a
  # bug; flagged for the broader Restriction/Opp Disrupt review the user asked for next.
  # 5th branch: a compound punishment on reverse -- the opponent is forced to bounce their OWN battling
  # character to hand AND discard a card from their OWN hand, two actions against their own zones bundled
  # into one payoff. Same disruption spirit as the branches above (opponent forced to act against their own
  # resources), just two actions instead of one. Confirmed via P4/S08-001, CHA/W40-014 (each phrases the
  # battle-opponent reference differently, hence 2 separate sigs for the same mechanic).
  ("Opp Disrupt", r"相手の(手札|ストック|山札|思い出|レベル置場|クロック|控え室)|相手は自分の(手札|ストック|山札|思い出|レベル置場|クロック|控え室)|相手の枠を[^。]{0,6}選び[^。]{0,20}マーカー置場のマーカー[^。]{0,10}控え室に置|相手は[^。]{0,14}【起】を使えない|相手は自分のバトル中のキャラを[^。]{0,4}手札に戻し[^。]{0,10}自分の手札を[^。]{0,10}選び[^。]{0,6}控え室に置"),
  # RevealTopSalvage: reveal the DECK TOP, then salvage a (often level-X-gated) character from the waiting
  # room. A costlier salvage MECHANIC (the cheap discard-only prints measure ~2000) — checked BEFORE generic
  # Salvage so it peels off. Payment still drives the per-sig cost; the family is for grouping/estimate. (User.)
  ("RevealTopSalvage", r"山札[^。]{0,10}公開[^。]{0,50}控え室[^。]{0,34}手札に(戻|加え)"),
  ("Salvage", r"自分の(控え室|思い出)[^。]{0,34}手札に(戻|加え)"),
  # Stock Search: look at your OWN STOCK and take a card to hand -- same "dig your resources for a specific
  # card" purpose as Salvage/Search, but the SOURCE zone is stock (a resource pile normally spent on costs,
  # not usually searchable), so it's a distinct enough mechanic to name separately rather than folding into
  # either.
  ("Stock Search", r"自分のストックを[^。]{0,10}見[^。]{0,20}選(び|んで)[^。]{0,20}手札に(戻|加え)"),
  # CX Exchange: swap a climax card between two zones (deck<->hand, hand<->waiting room, etc.), matched by
  # trigger icon or color rather than name -- a combo-assembly tool (trade a currently-useless climax for
  # one whose trigger icon you actually need), distinct from a plain Search/Salvage since BOTH sides move at
  # once (a true swap, not a one-way get). Anchored on the game's own "それらのCXを入れ替える" phrasing.
  # TWO separate CX-selection clauses (one per zone) before the final swap verb, rather than requiring the
  # literal "それらのCXを入れ替え" wording -- some prints just say "…選び、入れ替える" without echoing それらのCXを.
  ("CX Exchange", r"(CX|クライマックス)を[^。]{0,10}選[^。]{0,100}(CX|クライマックス)を[^。]{0,10}選[^。]{0,20}入れ替え"),
  # Memory Bank: bank a NAMED own waiting-room card into Memory (usually gated by a low own-Memory-count
  # condition, e.g. "if your Memory has 2 or fewer cards"). Distinct final purpose from Salvage (destination
  # is hand) and from Removal (Memory) (that's the OPPONENT's character) — this is your OWN card, parked in
  # Memory rather than recovered to hand, typically to set up a later Memory-count payoff or a Memory-sourced
  # Comeback/Summon combo on the SAME card (see e.g. SMP/W82-035, whose 3rd ability later pulls these exact
  # banked cards back out of Memory to hand). User taxonomy.
  # Source widened to include クロック置場 (own clock) alongside 控え室 -- same "bank a card into Memory" purpose
  # regardless of which own zone it came from. Verb widened にし -> にし|にする for the same reason as
  # Removal (Memory) above.
  ("Memory Bank", r"自分の(控え室|クロック置場)の[^。]{0,20}を[^。]{0,10}選び[^。]{0,10}(思い出にし|思い出にする)"),
  # Ally Memory Bank: same destination/purpose as the ONREV-gated AutoKickToMemory (self, on reverse -> own
  # Memory), but targeting an ALLY that just reversed instead of this card itself -- doesn't match ONREV_PAT
  # (that's strictly self-referential "このカードが【リバース】した時"), so it needed its own FAMPAT branch.
  # Banking a just-defeated ally in Memory protects it from further board-state effects. User-named
  # (2026-07-23). Confirmed via GBF/S134-014, DD/WE12-17.
  ("Ally Memory Bank", r"他のあなたの[^。]{0,40}が【リバース】した時.{0,60}(あなたは)?そのキャラを[^。]{0,6}思い出に(し|する)"),
  # MemorySelf: a plain ACT ability that sends THIS CARD itself into Memory -- NOT a Retreat (the user's
  # correction: this fires in the main phase, has nothing to do with attacking/battle, and isn't a combat
  # escape -- it's a bare main-phase self-relocation whose only real effect is shrinking your own board by
  # one card, banking it in Memory). Named "MemorySelf" rather than a generic "Compress": the user pointed out
  # that banking a card in Memory is only ONE of several ways to achieve a similar board-tidying effect (e.g.
  # keeping a lot of clean stock is another) -- a broad conceptual name would wrongly lump genuinely different
  # mechanics together, so the family is named for the SPECIFIC zone/action, not the abstract goal. The
  # on-reverse "self to Memory" shape is a completely different family (AutoKickToMemory, resolved earlier via
  # ONREV_PAT before FAMPAT even runs) -- this only catches the non-reactive, ACT-triggered case. Confirmed
  # via LB/W02-033.
  ("MemorySelf", r"このカードを(思い出にし|思い出にする)"),
  # Search = look at your DECK and take a card to HAND. Two phrasings: 見る (look) and 公開 (reveal the top,
  # then conditionally add). The reveal-top dig crosses a sentence break (…公開する。…なら手札に加え), so its
  # branch uses . (not [^。]) to bridge it; 山札…公開 anchors it to own-deck reveal, 手札に加え to taking to hand.
  # RevealTopSalvage (reveal -> salvage from 控え室) is checked earlier, so only the plain deck-dig lands here.
  ("Search", r"山札[^。]{0,14}見[てる][^。]{0,28}(手札|加える)|山札[^。]{0,10}公開.{0,90}手札に加え"),
  # Deck Thin: look at your OWN deck for a specific/trait card and send it to the WAITING ROOM instead of
  # hand — a targeted mill (thin a specific unwanted/situational card out of your deck), not a Search (which
  # takes the found card to hand). Checked after Search since the destination is mutually exclusive (手札 vs
  # 控え室), so order doesn't matter for correctness, but grouped here thematically. User taxonomy.
  ("Deck Thin", r"自分の山札[^。]{0,10}見[^。]{0,20}選(び|んで)[^。]{0,10}控え室に置"),
  # Deck Mill: BLINDLY put the top N (or up to N, or a variable X) cards of your own deck straight into the
  # waiting room -- no 見る (look)/選ぶ (choose) verb at all, unlike Deck Thin just above (which specifically
  # views the revealed cards and picks which one to discard). NEVER fold this into Brainstorm/集中, even though
  # both end up putting cards in the waiting room: Brainstorm is a RULES-LEVEL different mechanic -- its
  # revealed cards sit in an intermediate "resolution zone" before being discarded, while a plain mill sends
  # cards straight to the waiting room with no such step. Brainstorm stays reserved for the keyword mechanic
  # ONLY (via the KW dict); this plain on-play mill is its own family (checked AFTER Deck Thin so the
  # look+choose shape keeps its own family first).
  ("Deck Mill", r"自分の山札の上から[^。]{0,14}控え室に置"),
  # Look & Reorder = look at top N then put them back in ANY order (好きな順番) — a scry/setup, distinct from a
  # plain "look" (no reorder = cards return in their original order). Checked BEFORE the generic Look Deck;
  # AFTER Search (a look that TAKES to hand is a Search, not a reorder). User taxonomy.
  ("Look & Reorder", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見[^。]{0,30}好きな順番"),
  # Clock Reorder: the same "look, then set back in any order" scry purpose as Look & Reorder above, but
  # applied to your OWN CLOCK instead of your deck -- a distinct zone, so it needed its own name.
  # Verb widened 並べ直す -> also accept 置く: some prints phrase the reorder as "…好きな順番で置く" (put back down
  # in preferred order) rather than "並べ直す" (rearrange) -- same reorder-in-place action, different verb.
  # Also accepts a ［cost: discard this card］ bracket in front, which was stealing the family. Confirmed via
  # ZM/W03-T13.
  ("Clock Reorder", r"自分のクロックすべてを[^。]{0,10}(クロック置場に)?[^。]{0,6}好きな順番で(並べ直す|置)"),
  ("Look Deck", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見"),
  # Summon (renamed from "Comeback" — the old name collided with the official CLIMAX TRIGGER ICON "Comeback",
  # a different game concept entirely; the user flagged the confusion). Final purpose: put YOUR OWN character
  # directly onto the STAGE from ANY other zone (waiting room, deck, hand, Memory, clock), bypassing the
  # normal play sequence (no cost paid, no level check) — a resource cheat, distinct from Salvage/Search
  # (destination is hand — the card still has to be played normally afterward). Was DEAD (0 matches) before
  # this session: its "舞台に置" required the literal 4-char run, but real cards say "舞台の好きな枠に置く" /
  # "舞台の別々の枠に置く" (a placement-slot descriptor breaks the literal substring), so every card fell
  # through to the generic Card Select/Stand-Rest/Move grab-bags instead. Also widened to accept a NAMED
  # target («N») in addition to the literal word キャラ (most real prints name the specific character rather
  # than saying キャラ), and to accept 手札/思い出置場/クロック置場 as additional sources (a Summon combo often
  # stashes the target in Memory or the clock first, then recruits it from there — see e.g. ID/W13-122,
  # PJS/S91-P52-style clock swaps feed the SAME waiting-room pool this pulls from). Scoped to 自分の (own
  # zone) with a (?!相手) guard through every gap so an "either your own char to stock OR the OPPONENT's WR
  # char to stage" compound (a different, more aggressive steal mechanic) can't bridge across the "か、相手の…"
  # clause and false-match on the opponent branch. Deliberately does NOT match "このカードがいた枠に置" (placing
  # into the slot THIS card just vacated) — that phrasing is the signature of the "Change" mechanic below
  # (this card retreats AS the cost, a replacement fills its exact slot), a different final purpose even
  # though the destination looks similar.
  # Gap widened 22->32 (a level+cost double condition, e.g. "自分のレベル以下でコスト0以下の《T》の", pushed past
  # the old limit); destination widened to accept 前列/後列 too (some prints place directly into a row instead
  # of the generic 舞台); added a 2nd branch for "…プレイしてよい" (play it, ignoring the color requirement) --
  # same bypass-the-normal-play-sequence purpose, just a different verb than 置く.
  ("Summon", r"自分の(控え室|山札|手札|思い出置場|クロック置場)(?:(?!相手)[^。]){0,32}(キャラ|「N」)(?:(?!相手)[^。]){0,14}(舞台|前列|後列)(に|の(?:(?!相手)[^。]){0,6}枠に)置"),
  ("Summon", r"自分の(控え室|山札)[^。]{0,30}レベル以下の[^。]{0,20}(キャラ|「N」)[^。]{0,10}選(び|んで)[^。]{0,20}色条件を満たさずに[^。]{0,10}プレイ"),
  # 3rd branch: source is HAND (not WR/deck) and the bypass condition is phrased as "レベル条件と色条件を満たして
  # いるなら…コストを払わずにプレイ" (if level/color conditions are met, play without paying cost) rather than
  # "色条件を満たさずに" -- same purpose (play a character bypassing its normal requirement), different wording.
  ("Summon", r"自分の手札の[^。]{0,10}(キャラ|「N」)[^。]{0,10}選[^。]{0,30}コストを払わずにプレイ"),
  # 4th branch: reveal the top of your own deck, then conditionally place THAT card onto the stage -- same
  # "source deck, destination stage" purpose as the 1st branch above, just sourced via a REVEAL instead of a
  # free choice, and the reveal-then-conditional-payoff structure crosses a 。 (needs . not [^。]). Confirmed
  # via DC/W01-E16, DC/WE08-43.
  ("Summon", r"自分の山札.{0,10}公開する.{0,40}(キャラ|「N」).{0,20}(舞台|前列|後列)(に|の.{0,6}枠に)置"),
  # Change (text-form, no keyword marker): this card retreats to the waiting room/clock/Memory AS the cost of
  # its own ability, and a replacement character (from hand or waiting room) fills the EXACT slot it just
  # vacated ("このカードがいた枠に置く") — functionally identical to the official チェンジ keyword mechanic (already
  # in the KW dict above), just spelled out in full text instead of using the keyword shorthand. Folded into
  # the SAME family name so both detection paths share one cost standard, matching how the バウンス keyword and
  # its FAMPAT text-pattern counterpart both resolve to Removal (Hand). User taxonomy.
  # Verb widened to also accept 動かす (moved into the vacated slot, not just 置く) -- the defensive variant
  # of this mechanic ("…このカードがいた枠に防御キャラとして動かす") uses this verb instead. A 2nd branch catches the
  # same defensive-swap shape phrased as "…このカードと入れ替えてよい" (swap places with this card) instead of
  # spelling out このカードがいた枠 -- same mechanic (this card is replaced by a hand character as the defender).
  ("Change", r"このカードがいた枠に[^。]{0,10}(置|動かす)|自分の手札の[^。]{0,10}選び[^。]{0,10}防御キャラとしてこのカードと入れ替え"),
  # Clock/WR Exchange: swap the card at the BOTTOM of your own clock for a character in your own waiting
  # room — the clock's SIZE never changes (still the same number of clock cards), only WHICH card sits in
  # one clock slot changes. Distinct from Heal (that permanently REMOVES a card from the clock, from the
  # TOP, to some other zone — a net reduction) and from Summon (destination here is the clock, not the
  # stage). User: useful for fixing your board's COLOR requirements (swap in a needed color from the
  # waiting room) or for freeing a specific character trapped in the clock so a later Salvage/Summon can
  # reach it. User taxonomy.
  # 2nd branch: THIS CARD is sitting at the TOP of your clock ("アラーム このカードがクロックの1番上にあるなら…"),
  # and IT (not a generic bottom-of-clock card) is what trades for a chosen waiting-room character. Same
  # underlying purpose (trade which card sits in the clock), just the clock-side is this card itself and at
  # the top rather than the bottom -- confirmed by the user as a real, if rare, shape.
  ("Clock/WR Exchange", r"自分のクロックの下から[^。]{0,20}控え室の[^。]{0,20}を[^。]{0,10}選び[^。]{0,10}入れ替え|このカードがクロックの1番上にある[^。]{0,30}控え室の[^。]{0,10}キャラを[^。]{0,10}このカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Clock/Stage Exchange: sibling of Clock/WR Exchange, same self-referential "this card sits at the top of
  # your clock" shape, but the OTHER side of the trade is a bare "自分のキャラ" (one of your characters) with NO
  # waiting-room/level-zone qualifier at all -- meaning an in-play STAGE character, not a discarded one. A
  # stage character is a materially different resource (already on board, contributing power/abilities) than
  # a waiting-room character, so per the user's "split by variant, don't lump" rule (established for Bomb and
  # Reverse Immunity) this gets its own name rather than folding into Clock/WR Exchange. Confirmed via
  # DC4/W81-073: "あなたは自分のキャラを1枚とこのカードを選び、入れ替えてよい" -- no 控え室 anywhere in the sentence.
  # Positioned AFTER Clock/WR Exchange so that WR-qualified prints keep matching the more specific pattern
  # first; this only catches the zone-unqualified leftover shape.
  ("Clock/Stage Exchange", r"このカードがクロックの1番上にあ[りる][^。]{0,45}あなたは自分のキャラを1枚とこのカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Level/WR Exchange: swap a card in your own LEVEL ZONE for a card in your own waiting room -- sibling of
  # Clock/WR Exchange (same "trade which card sits in a resource zone" purpose, different zone pair). 2nd
  # branch: THIS CARD is the level-zone side specifically ("レベル置場にこのカードがあるなら…控え室の…とこのカードを
  #選び、入れ替え"), the same self-referential shape as the Clock/WR variant above -- confirmed by the user
  # as real (few cards, but they exist): summoning-style effects can source from level zone or clock, not
  # just waiting room/deck.
  # 置場/置き場 spelling variant: some prints spell the level zone with the okurigana き (レベル置き場), others
  # without (レベル置場) -- same zone, purely a print-style difference. Confirmed via CN/SE02-10.
  # カード/キャラ word variant: some prints call the waiting-room swap partner a generic "カード" (card) rather
  # than specifically "キャラ" (character) -- same swap, different word choice. Confirmed via UMA/W134-039.
  ("Level/WR Exchange", r"自分のレベル置き?場の[^。]{0,20}と[^。]{0,4}控え室の[^。]{0,20}を[^。]{0,6}選び[^。]{0,10}入れ替え|レベル置き?場にこのカードがある[^。]{0,30}控え室の[^。]{0,10}(キャラ|カード)を[^。]{0,10}このカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Hand/Level Exchange: a 4th sibling of Clock/WR Exchange, Level/WR Exchange, and Memory/WR Exchange --
  # same "trade which card sits in a resource zone" purpose, this time Hand <-> Level. Confirmed by the user
  # via SHS/W71-023 (on-play, paid) and LRC/WE47-14 (ACT, self-discard cost -- note the cost there is "put
  # THIS CARD into the waiting room", not a hand discard: this card is on the stage when the ability fires,
  # so leaving play is a zone-transfer, never a "discard" -- discard specifically means from hand).
  ("Hand/Level Exchange", r"自分の手札[^。]{0,20}とレベル置場[^。]{0,20}を[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Memory/WR Exchange: another sibling of Clock/WR Exchange and Level/WR Exchange -- same "trade which card
  # sits in a resource zone" purpose, this time the zone pair is Memory <-> waiting room. Confirmed by the
  # user via HOL/W104-136.
  ("Memory/WR Exchange", r"自分の控え室の[^。]{0,20}と思い出置場の[^。]{0,20}を[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Memory/Stage Exchange: another sibling of Clock/Stage Exchange -- while THIS card sits in your Memory
  # zone, trade it for an own stage character (matching a trait), so this card returns to the stage and the
  # chosen character goes to Memory instead. User-named (2026-07-23). Confirmed via KMS/W133-018.
  ("Memory/Stage Exchange", r"思い出置場にこのカードがあり.{0,80}自分の《T》のキャラを[^。]{0,10}このカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Level/Stage Exchange: completes the Clock/Stage + Memory/Stage sibling group -- choose an own Level-zone
  # card and this card (on stage), swap them. User-named (2026-07-23). Confirmed via GZL/SE33-14.
  ("Level/Stage Exchange", r"自分のレベル置場の[^。]{0,20}を[^。]{0,10}このカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Memory/Hand Exchange: THIS CARD is in Memory (記憶 condition-keyword) and swaps for a chosen HAND
  # character -- a 5th sibling of the Clock/WR-style Exchange group, zone pair Memory <-> Hand. Confirmed by
  # the user via KMS/W133-T03.
  ("Memory/Hand Exchange", r"思い出置場にこのカードがあるなら[^。]{0,60}自分の手札の[^。]{0,20}とこのカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Memory Partner Swap: THIS CARD is in Memory and swaps for a SPECIFIC NAMED partner card also sitting in
  # Memory -- not a resource-zone trade like the siblings above, but switching which of two named identities
  # occupies the shared Memory slot. Confirmed by the user via KMS/W133-P04S.
  ("Memory Partner Swap", r"自分の思い出置場の[^。]{0,20}とこのカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # LastAttacker: a REPLAY/finisher shape -- put EVERY other one of your own characters into the waiting
  # room, then swap this card for a specific NAMED waiting-room ally. Per the user's explanation: this is the
  # last attack of a sequence -- you sacrifice your whole remaining board to bring in one more (fresh,
  # ready-to-attack) character and swing with it too. Distinct from the plain resource-zone Exchange group
  # above (this isn't tidying a resource zone, it's a board-wipe finisher). Confirmed via UMA/W134-056.
  ("LastAttacker", r"あなたは他の自分のキャラすべてを、?控え室に置き[^。]{0,10}控え室の[^。]{0,20}とこのカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Effect Copy: play another one of your OWN character's named on-play [AUTO] ability as if it were this
  # card's own -- a genuine "replicate an ability" mechanic, distinct from Grant Ability (that GIVES a NEW
  # ability to a target; this REUSES an EXISTING ability already printed on another of your characters).
  # Confirmed by the user via IMC/WE51-42.
  ("Effect Copy", r"を1つ選び[^。]{0,10}選んだ【自】を持つキャラの【自】としてプレイする"),
  # Clock/Hand Exchange: a clock character comes to hand, and (as a SEPARATE step, not a true simultaneous
  # swap) a hand card goes to the clock -- net effect is the same shape as Clock/WR Exchange (trade WHICH
  # card sits in a clock slot) but the other side of the trade is your hand instead of your waiting room, a
  # meaningfully different resource (a hand card is more valuable than a waiting-room one), so it gets its
  # own name rather than folding in.
  # Dropped the を-anchor (a compound "カード名に「N」を含む" qualifier has an EARLIER を that isn't the real
  # selection verb's, so anchoring on を was unreliable) in favor of just requiring 選び within a wider gap.
  # The gap between "…手札に戻してよい" and "自分の手札を…" crosses a sentence break (。そうしたら、) in most real
  # prints, so it needs . (not [^。]) there, matching the Search/Modal convention elsewhere in this list.
  # The clock refill source varies -- some prints refill from a chosen HAND card, others from the DECK TOP
  # (a lesser commitment than a specific hand card). Either way the net shape is the same: you permanently
  # gain a clock character to hand, paid for by feeding the clock a replacement so its count stays put.
  ("Clock/Hand Exchange", r"自分のクロック置場の[^。]{0,30}選び[^。]{0,10}手札に戻.{0,20}(自分の手札を[^。]{0,10}選び|自分の山札の上から1枚を)[^。]{0,10}クロック置場に置"),
  # Return to Deck (Own): send YOUR OWN waiting-room card(s) back into YOUR OWN deck (top or bottom) — the
  # mirror of the existing "Return to Deck" family (which targets the OPPONENT's waiting room/deck). A
  # self-recycle: redraw a specific card later, or just declutter the waiting room. Distinct from Summon
  # (destination is the deck, not the stage) and from Stock Gen (destination is the deck, not stock).
  # Source widened to include 自分の手札 (a hand-sourced own-CX shuffle-back is the same self-recycle purpose);
  # destination widened to also accept "山札に戻し" (shuffled back generally, no 上/下 position specified).
  # Gap 20->34 (a trigger-icon descriptor, "トリガーアイコンがtreasureのクライマックス", is long); verb widened to
  # accept 戻す (dictionary form) alongside 戻し (continuative).
  ("Return to Deck (Own)", r"自分の(控え室|手札)の[^。]{0,34}を[^。]{0,10}選(び|んで)[^。]{0,6}(山札の(上|下)に[^。]{0,8}置|山札に戻(し|す))"),
  # Free Refresh (user's own name): return ALL of your own waiting-room cards to your deck at once, no
  # selection -- the bigger-scale cousin of Return to Deck (Own). User: functionally like a deck Refresh
  # (the waiting room fully empties back into the deck) but WITHOUT the normal 1-damage refresh penalty.
  ("Free Refresh", r"自分の控え室のカードすべてを[^。]{0,10}山札に戻"),
  # Stock Gen widened: sources beyond just the deck top -- own hand, waiting room, or Memory can ALSO feed
  # your stock (e.g. discard a hand card face-down as stock instead of to the waiting room). Same final
  # purpose (grow/refill your stock) regardless of which own zone supplies the card.
  # Gap widened 20->50 for the hand/waiting-room/Memory sources -- a compound multi-card select clause
  # ("キャラを1枚までとイベントかクライマックスを1枚まで選んで相手に見せ") runs long before reaching the destination.
  ("Stock Gen", r"(山札の上|デッキトップ|山札の上から)[^。]{0,20}ストック置場[^。]{0,4}に[^。]{0,10}置|(自分の手札|自分の控え室|自分の思い出置場)[^。]{0,50}ストック置場[^。]{0,4}に[^。]{0,10}置"),
  # Stock Recall: recover the TOP card of your OWN stock straight to hand -- a distinct resource-recovery
  # family from Search (deck->hand)/Salvage (waiting room->hand)/Add to Hand (generic fallback), since STOCK
  # is a resource you'd normally rather spend than give up, so pulling one back is its own real mechanic.
  # Confirmed by the user (2026-07-23) via 4 cards on a mix of triggers (a named-card trigger check, low hand
  # size, this card's dealt damage being cancelled, a qualifying battle opponent reversing) -- BD/W54-009,
  # KMS/W133-080, KC/S67-009, GRI/S72-043.
  ("Stock Recall", r"自分のストックの上から[^。]{0,6}枚?を[^。]{0,6}手札に戻"),
  # Clock Gen: sibling of Stock Gen -- your own DECK TOP goes to your CLOCK instead of your stock. Distinct
  # destination (clock advances your level/damage count differently than stock does), same "deck-top-into-
  # a-resource-zone" final purpose.
  ("Clock Gen", r"自分の山札の上から[^。]{0,14}クロック置場に置"),
  # The "AddMarker (...)" group: park a card face-up/down as a MARKER under this (or another named) card, to
  # be retrieved later (often at the next Draw Phase, onto a stage slot) — a banked resource, not an
  # immediate effect. User: markers can genuinely come from ANY zone (deck top, deck search, waiting room,
  # stage, or the card itself) — the family name must say WHICH zone, "AddMarker (ZONE)", the same
  # parenthetical convention as Removal (...)/Reverse Immunity (...). Checked in source-specificity order so
  # the more specific zones peel off before the general waiting-room bucket claims everything with "マーカー
  #として…置" in it.
  # Deck Top: a revealed/checked TOP card of your own deck (usually gated on a trait match, "then return it
  # if not"). Crosses a sentence break (reveal-then-conditionally-mark) via `.`.
  ("AddMarker (Deck Top)", r"自分の山札の上から.{0,60}マーカーとして[^。]{0,14}置"),
  # Deck Search: your OWN DECK is SEARCHED (見て, not 上から revealed) for a specific/named card, which
  # becomes the marker — a real search, not a blind top-card peek, so it's a different zone-access shape
  # even though both ultimately come "from the deck."
  ("AddMarker (Deck Search)", r"自分の山札を見て[^。]{0,20}マーカーとして[^。]{0,14}置"),
  # Waiting Room (the dominant remaining source once Deck Top/Search are peeled off above) — kept
  # unanchored beyond that exclusion and keyed on the destination phrase alone (マーカーとして…置く), which no
  # other family's text can plausibly contain, since the exact WR-selection phrasing varies a lot (with/
  # without a trait filter, with/without a name-group restriction, etc.).
  # The 2nd branch is the RETRIEVAL half of the same overall marker-banking mechanic: cards previously banked
  # as markers (via the "…として置く" branch above, often on an earlier turn) come back out from under this
  # card onto the stage. Same underlying purpose (a marker is just a temporarily-parked character), so it
  # stays the same family rather than forking into yet another destination split.
  # Banking-half gap widened 8->14 (a placement-order descriptor, "…好きな順番で裏向きに置く", pushed past the
  # old limit). Retrieval-half broadened from "-> stage only" to ANY destination + 置/戻 verb -- real prints
  # retrieve a banked marker to hand, stock, or the climax area too, not just back onto the stage; "マーカー"
  # alone is a specific enough anchor that no other family's text could plausibly contain it.
  ("AddMarker (Waiting Room)", r"マーカーとして[^。]{0,14}置|マーカー[^。]{0,30}選(び|んで)[^。]{0,16}(置|戻)"),
  # Marker Currency: a banked marker can substitute for a STOCK card when paying a cost (event cost, ACT
  # cost, ...) — a distinct final purpose from the AddMarker (...) group itself (that's the banking
  # mechanic; this is a payment-substitution rule built ON TOP of an already-banked marker).
  ("Marker Currency", r"マーカー[^。]{0,14}ストック[^。]{0,6}のかわりに[^。]{0,10}控え室に置"),
  # Marker Cleanup: discard ALL markers under this card to the waiting room, unconditionally (no selection,
  # "すべて" -- distinct from the AddMarker (...) retrieval branch, which requires CHOOSING one marker to
  # bring back). A forced end-of-effect/end-of-turn/on-level-up cleanup of the whole banked pile at once.
  ("Marker Cleanup", r"このカードの下のマーカーをすべて控え室に置く"),
  # Add to Hand: a card ends up in hand. 戻す (return) is included, but NOT "このカードを手札に戻す" — returning THIS
  # card to hand is almost always a PAYMENT (［このカードを手札に戻す］ cost bracket), so letting it match here stole
  # the ability from its real EFFECT family (…パワーを＋N / ソウルを＋N / draw). The negative lookbehind lets those
  # fall through to Power Pump / Soul / Draw. (Returning an OTHER own char — そのキャラ/「N」を…手札に戻す — still matches.)
  # Retreat (reactive pronoun branch): a reactive "そのキャラ/カードを…手札に戻す" that refers back to one of YOUR
  # OWN characters mentioned earlier (e.g. "他のあなたのキャラが…控え室に置かれた時…そうしたら、そのカードを手札に戻す")
  # is a self-bounce, not Add to Hand. Resolve the pronoun's scope: an own-POSSESSIVE (自分の|あなたの — an OWNED
  # character, not the bare actor あなたは) must precede その…手札に戻 with NO opponent reference in between — the
  # (?!相手|このカードとバトル) guard runs through every char (. to cross sentence breaks). 相手 catches 相手の/バトル相手;
  # このカードとバトル catches "このカードとバトルしているキャラ" (= the OPPONENT's battler, referenced without the word
  # 相手 — a reverse-trigger bounce that would else false-match). Keeps 相手はそのカードを手札に戻す (opponent's forced
  # return) OUT. Placed right before Add to Hand so higher-priority families (Grant/CXC/Salvage/…) claim theirs first.
  ("Retreat", r"(自分の|あなたの)(?:(?!相手|このカードとバトル).)*?その(カード|キャラ)を[^。]{0,8}手札に戻"),
  # Power Pump (board) gap widened 8->20 and を made optional: some prints put the duration clause AFTER the
  # target ("…キャラすべてに、次の相手のターンの終わりまで、パワーを＋500", target before duration) instead of before
  # it, pushing past the old distance; others drop the を particle entirely ("パワー+500" with no を). Confirmed
  # via KC/S25-035 (stock-dump-then-pump combo) and BRD/W139-086 (turn-asymmetric dual pump) and NS/W04-103
  # (bare pump, no を).
  ("Add to Hand", r"手札に(加える|加え)|(?<!このカードを)手札に戻す"), ("Power Pump (board)", r"あなたの[^。]{0,16}(キャラ|「N」|《T》)すべてに[^。]{0,20}パワー(を)?[＋+]"),
  # Draw = 引く/引き/引い (dictionary, continuative, and the very common て-form 引いて/引いた — a plain "-i" stem
  # match catches all three conjugations at once; the narrower 引[くき] used until now silently missed every
  # "…引いてよい" optional draw, leaking a large slice of real Draw/DrawDiscard prints to Card Select). Placed
  # AFTER the pump families on purpose: a "draw N and pump" combo (引き…パワーを＋) is a combat trick whose
  # meaningful cost is the pump (and Power Pump (self) carries the multiplicative cabling), so pump wins; only
  # a pure draw (typically draw-then-discard "loot") falls through to Draw.
  # Power Pump: the plain キャラ…パワー branch stays at distance 16. The second branch anchors on a SELECTED
  # target (キャラを…選) and allows a longer gap to パワー, so a "select a char, 次の相手のターンの終わりまで, パワーを＋"
  # (the long "until next opponent turn" duration ~21 chars) is caught instead of leaking to Card Select /
  # Stand/Rest. Requiring the 選 keeps a CONDITIONAL キャラ ("…が《T》のキャラなら…パワーを＋" = self-pump) from matching.
  ("Power Pump (self)", r"このカードのパワーを[＋+]"),
  # 3rd branch: a NAMED target («N») instead of the literal word キャラ -- some prints select a specific own
  # character by name to pump rather than saying キャラ. Narrowly scoped to 自分の…選 (a selected own target)
  # to avoid touching the two well-established, heavily-measured branches above.
  # 4th branch: a 2-target selection that includes the CITING card itself ("…キャラを1枚とこのカードを選び、…パワーを
  # +N" -- choose another character AND this card, both get the pump). 5th branch: a FIXED/named/positional
  # target with no selection verb at all ("他のあなたの…枠の「N」に、パワーを+N" -- a specific named ally in a
  # specific board slot). Same final purpose as the branches above (give power); confirmed by the user to
  # fold in via AOT/S50-026 and AOT/S50-015.
  ("Power Pump", r"キャラ[^。]{0,16}パワーを[＋+]|キャラを[^。]{0,6}選[^。]{0,18}パワーを[＋+]|自分の「N」を[^。]{0,6}選[^。]{0,18}パワーを[＋+]|キャラを[^。]{0,6}とこのカードを[^。]{0,6}選[^。]{0,18}パワーを[＋+]|他のあなたの[^。]{0,20}「N」に、?パワーを[＋+]"),
  # DiscardCharacterToDraw: pay by DISCARDING A CHARACTER from hand (［…手札の…キャラ…控え室に置…］ cost bracket),
  # then draw. A specific payment-shaped draw (you spend a card to dig), distinct from a bare Draw — split out
  # BEFORE Draw so it doesn't hide in the generic 引く family. The cost bracket must contain 手札→キャラ→控え室に置
  # (all within one ［…］), and a 引く must follow it. (User taxonomy.)
  ("DiscardCharacterToDraw", r"［[^］]*手札[^］]*キャラ[^］]*控え室に置[^］]*］.*引[くきい]"),
  # DrawDiscard: draw N then discard M cards from HAND to the waiting room (…引き、自分の手札を…選び、控え室に置く).
  # A hand-FIX / quality filter (net card gain is only N−M, often 0), distinct from a pure Draw (+N advantage) —
  # split out BEFORE Draw so the two don't share a blended cost median. After DiscardCharacterToDraw so a card
  # that BOTH discards a char as cost AND draw-discards keeps the more specific payment-shaped label.
  ("DrawDiscard", r"引[くきい].{0,20}手札を[\dＸ]+枚.{0,4}選.{0,6}控え室に置"),
  ("Draw", r"引[くきい]"),
  # Hand Discount: a static buff for a NAMED, DIFFERENT card sitting in hand (its cost OR level -N),
  # checked BEFORE Early Play below (whose broader 手札の…レベルを－ pattern would otherwise wrongly claim the
  # level-reduction variant — confirmed via GRI/S84-028, which was landing in Early Play despite targeting
  # an external named card, not "this card"). Common on both events and characters per the user.
  ("Hand Discount", r"あなたの手札の「N」の(コスト|レベル)を[－\-]"),
  # Early Play (in hand): lowering THIS card's level WHILE IN HAND (手札の…レベルを－N) makes it playable before you
  # reach that level — functionally Early Play. Checked BEFORE the generic Level (レベルを±), which would else grab it.
  # Scoped to 手札の so an on-STAGE level-down (舞台の…レベルを－, a stat mod often paired with a pump) is NOT caught.
  ("Early Play", r"手札の[^。]{0,8}レベルを[－\-]"),
  # Grant Trait: assign a chosen character a designated TRAIT for the turn (temporarily makes it count as a
  # <Trait> it doesn't normally have -- combos with other trait-gated effects). A stat-grant sibling of
  # Soul/Level below, just targeting the trait slot instead of a number.
  # Widened to also accept granting a TRIGGER ICON to an external target ("すべての領域の「N」のトリガーアイコンに
  #soulを与える") -- same purpose as granting a trait (extend a chosen/named external card's identity), just
  # a different identity slot.
  # Trigger-icon branch gap widened around 「N」 (…領域の、「N」と「N」のトリガーアイコンに… has a 、 before the name
  # and a と before the trailing の, which the tight "の「N」の" literal missed).
  # 2 more branches folded in (same final purpose -- assign a trait -- just no selection verb since the
  # target is already fixed/described rather than chosen): "このカードの正面のキャラに…を与える" (the character
  # facing this card, a fixed reference) and "他のあなたの…キャラすべてに…を与える" (every one of your other
  # characters, or every character whose name matches, a described-not-chosen group).
  # 2 more branches: "相手の前列/後列のキャラすべてに…を与える" (every character on one of the OPPONENT's rows, a
  # described-not-chosen group, same as the 他のあなたの…すべて branch above but on the opponent's side); and a
  # bare "あなたのキャラすべてに…を与える" with no 他の qualifier (ALL your characters, this card included --
  # confirmed via MK/S33-010, whose trigger fires off an ALLY's battle so this card itself is a valid target).
  # Last branch: a name-matched OPPONENT target ("相手のカード名に「N」を含むキャラすべてに…を与える") -- same
  # described-not-chosen group shape as the row-qualified opponent branch above, just matched by name instead
  # of row. Confirmed via RZ/SE35-48.
  ("Grant Trait", r"キャラを[^。]{0,10}選[^。]{0,20}(特徴を1つ与える|《T》を与える)|[^。]{0,6}「N」[^。]{0,10}のトリガーアイコンに\w+を与える|このカードの正面のキャラに[^。]{0,10}《T》を与える|他のあなたの[^。]{0,20}キャラ(すべて)?に[^。]{0,20}《T》を与える|相手の(前列|後列)のキャラすべてに[^。]{0,10}《T》を与える|あなたのキャラすべてに[^。]{0,20}《T》を与える|相手のカード名に「N」を含むキャラすべてに[^。]{0,10}《T》を与える"),
  # Grant Color: same "extend an identity slot" purpose as Grant Trait/Grant Trigger Icon (Class) above, but
  # the slot is COLOR (affects legal play/payment) instead of a trait or trigger icon. User-named
  # (2026-07-23). Confirmed via KGL/S95-059.
  ("Grant Color", r"他のあなたの[^。]{0,20}「N」すべてに[^。]{0,10}(赤|青|緑|黄|紫)を与える"),
  # Grant Trait (All): a symmetric variant -- EVERY other character regardless of owner (both players'
  # boards) gains the trait, unlike every other Grant Trait branch above (each scoped to just one side).
  # Sibling naming matches the existing Strip Trait (All) (a symmetric-scope split, same convention).
  # User-named (2026-07-23). Confirmed via DG/S02-032 (a legacy S02-era card).
  ("Grant Trait (All)", r"^他のキャラすべてに[^。]{0,6}《T》を与える。?$"),
  # Grant Ability: same "extend a chosen/named target's identity" purpose as GRANT_PAT above, but this exact
  # shape (grant the 【カウンター】 keyword to a named EVENT card sitting in hand) doesn't match GRANT_PAT's
  # "能力を/』を" requirement -- 【カウンター】 is a specific keyword name, not the generic word 能力. Kept as its
  # own FAMPAT branch (checked after GRANT_PAT's early pre-check already ran) rather than widening GRANT_PAT
  # itself, since GRANT_PAT also drives the Pump & Grant dual-nature check and this shape never pumps.
  # Confirmed via RW/W20-012, HOL/W104-014.
  ("Grant Ability", r"手札のイベントの[^。]{0,10}に[^。]{0,6}【カウンター】を与える"),
  # Grant Trigger Icon (Class): grants a trigger icon to an entire CLASS of climaxes (any CX that already
  # has trigger icon X, in all zones), not a specific NAMED target -- broader in scope than Grant Trait
  # above, so it needed its own name even though the underlying mechanic (extend an identity slot) is
  # conceptually the same.
  # 2nd branch: the condition clause ("あなたのCX置場にトリガーアイコンがXのCXがあるなら") and the grant clause ("あなた
  # のすべての領域のCXのトリガーアイコンにYを与える") are two SEPARATE clauses bridged by a なら…あなたの gap, not one
  # continuous run like the branch above -- confirmed via NIK/S117-P06, GA10/S131-012.
  ("Grant Trigger Icon (Class)", r"トリガーアイコンが\w+の(CX|クライマックス)のトリガーアイコンに\w+を与える|トリガーアイコンが\w+の(CX|クライマックス)があるなら.{0,20}のCXのトリガーアイコンに\w+を与える"),
  # Trigger Icon Reuse: use a specific trigger icon's bonus effect (salvage/gate/choice/...) OUTSIDE of an
  # actual trigger check -- e.g. "you may choose a card in your waiting room with the gate effect" lets you
  # pull off a Gate-icon-style pickup even when no climax with that icon actually triggered. Confirmed by
  # the user: some cards let you use Gate's payoff on something that isn't even a climax.
  ("Trigger Icon Reuse", r"あなたは\w+の効果で[^。]{0,20}(選んでよい|選ぶ)"),
  # Strip Trait: the negative-polarity mirror of Grant Trait -- choose an OPPONENT's character and one of
  # its traits, it loses that trait until end of turn (denies it to trait-gated effects/Assist/etc.).
  # User: conceptually part of the broader "disruption" theme (interferes with the opponent's board), but
  # specific enough to be its own named family rather than folding into Removal (Waiting Room)/Opp Disrupt.
  # Gap after the trait-selection clause widened 20->40: JJ/SE42-01 inserts a marker-wipe clause ("そのキャラの
  # 下のマーカーすべてを、控え室に置き") between choosing the trait and the character actually losing it -- still
  # filed as plain Strip Trait per the user (the marker wipe is a minor secondary detail on a small cluster,
  # not worth a combined family name).
  ("Strip Trait", r"相手のキャラを[^。]{0,6}と[^。]{0,10}特徴を[^。]{0,10}選[^。]{0,40}その特徴をすべて失う"),
  # Strip Trait (All): a wider-scope sibling -- choose 1 trait present somewhere on the opponent's stage, and
  # ALL of the opponent's characters (not just the chosen one) lose that trait until end of turn. Genuinely
  # broader than plain Strip Trait (board-wide vs single-target), so it gets its own name per the user's
  # "split by variant" rule. Confirmed via LRC/W105-P04 and Fks/W120-016.
  ("Strip Trait (All)", r"相手の舞台にいるキャラの特徴を[^。]{0,10}選[^。]{0,10}相手のキャラすべては[^。]{0,20}その特徴をすべて失う"),
  # Self Identity Grant: this card (not a chosen target) permanently/conditionally gains a TRAIT, an
  # ALTERNATE NAME, or a TRIGGER ICON -- three different "identity slots" but the same final purpose (this
  # card's own identity is extended so other trait/name/icon-gated effects elsewhere can reach it). Distinct
  # from Grant Trait above (that targets ANOTHER chosen character). User taxonomy.
  # Widened: (1) "手札にこのカードがあるなら" as another condition prefix (gains the identity while IN HAND, not
  # just on stage/in all zones); (2) a bare "このカードは…を得る" with NO condition prefix at all (an
  # unconditional, permanent grant — e.g. a fixed color) or deriving the color from this card's own markers.
  # Bare final-clause branch added: "このカードのカード名は…としても扱う" (this card's name is ALSO treated as X) is
  # the shared destination regardless of which zone/condition precedes it (在 hand, in Memory, in the
  # waiting room, a combined condition, etc.) -- enumerating every prefix was missing real cases; anchoring
  # on the destination clause alone (like AddMarkerWaitingRoom does for マーカーとして) is more robust.
  ("Self Identity Grant", r"(舞台にこのカードがいるなら|すべての領域にあるこのカード(は|の)|手札にこのカードがあるなら)[^。]{0,20}(を得る|得る|としても扱う)|このカードは[^。]{0,24}を得る|このカードのカード名は[^。]{0,40}としても扱う"),
  # Self Identity Strip: the mirror of Self Identity Grant above -- this card LOSES its own trait(s) entirely
  # while on stage, instead of gaining an identity slot. User-named (2026-07-23). Confirmed via SG/W70-013.
  ("Self Identity Strip", r"舞台にこのカードがいるなら[^。]{0,6}このカードは《T》をすべて失う"),
  ("Power Debuff", r"パワーを[－\-]"), ("Soul", r"ソウルを[＋+\-－]"), ("Level", r"レベルを[＋+\-－]"),
  ("Mill (self)", r"山札の上から\d+枚を[^。]{0,8}控え室"),
  # Retreat: THIS card (or another of your own STAGE characters) returns to hand -- a self-bounce/withdrawal,
  # not Salvage (that's WAITING ROOM -> hand) and not Bounce (that's the OPPONENT's character -> hand). The
  # "このカードを手札に戻す" branch excludes a trailing ］ so it only fires as a standalone EFFECT, not when that
  # same phrase is the leading ［…］ PAYMENT bracket for a different ability (Power Pump/Soul/Draw/etc. already
  # correctly keep those -- same cost-bracket-steals-family issue as the earlier Add to Hand fix). Checked
  # AFTER Mill (self) so a "mill self, then MAY retreat" dual effect keeps its self-mill as the primary family
  # (its defining action; the retreat is a conditional payoff), matching how other dual-nature abilities this
  # session (Backup/Brainstorm/CX Combo payoffs) were left on their real mechanic. KNOWN GAP (not caught): a
  # reactive "そのキャラ/カードを手札に戻す" referring back to an own character mentioned earlier in the same
  # clause (e.g. P3/S01-090) -- skipped because そのカード/キャラ sometimes refers to the OPPONENT's character
  # instead (~4% of a broad そのキャラ/カード…手札に戻す sample), and safely resolving the pronoun needs more
  # than a fixed-distance regex; left for a future pass.
  ("Retreat", r"このカードを手札に戻(す|してよい)(?!］)"),
  # Attack Redirect: instead of the normal attacker/target, choose a different opponent character to attack
  # (e.g. front-attack a back-row character). A combat-targeting trick, not a Move (nobody's position on the
  # stage changes). Checked before Move so it doesn't get read as a generic reposition.
  ("Attack Redirect", r"かわりに相手の[^。]{0,16}キャラを[^。]{0,10}選び[^。]{0,24}(フロントアタック|アタック)"),
  # Attack Cancel: erase an incoming attack ENTIRELY (trigger/counter/damage/battle steps never happen at
  # all) and skip straight to the next attack-declaration step -- distinct from Attack Redirect above (which
  # sends the SAME attack to a different target, it still resolves) and from every Reverse Immunity variant
  # (those prevent the REVERSAL outcome, not the attack itself). User-named (2026-07-23). Confirmed via
  # JJ/S66-048.
  ("Attack Cancel", r"そのアタックを中止し[^。]{0,10}次のアタック宣言ステップに進む"),
  # Move: reposition a character ALREADY on the stage into a different open slot -- entering play for the
  # FIRST time from another zone is Summon, not Move. Split by whose character moves (user taxonomy): moving
  # your OWN character is a defensive/tactical trick (dodge a matchup, set up a Backup/Assist angle); forcibly
  # moving the OPPONENT's is a disruption/combat trick (break their blocking assignment) -- same action, a
  # different final purpose depending on whose board it targets, so it needed two names, not one. Checked
  # opponent-branch FIRST since it's the more specific case; own-branch is the fallback for everything else
  # that reaches this point with a stage-slot verb (self-moves say "このカードを…枠に動かす" without 自分の, so a
  # plain "not opponent" fallback catches them too, rather than trying to enumerate every own-phrasing). The
  # "枠に" requirement was widened from a fixed literal-prefix list (前列に/後列に/の枠に/…) to ANY "…枠に", since
  # real prints commonly precede it with other words the old prefix list didn't cover (e.g. "…いない枠に",
  # "…いる枠に"). A negative lookahead excludes the "動かせない" (CANNOT be moved) negative form -- that's a
  # restriction/lock on movement, not an actual move action, and belongs to Restriction instead. The
  # opponent-branch requires 相手の…キャラを…選び (the SELECTION verb tied to 相手の) rather than just "相手の…キャラ
  # …枠に動か" anywhere in the sentence — some own-character moves land the mover in a slot DESCRIBED relative
  # to an opponent's character ("…自分の《T》のキャラを1枚選び…正面に相手のキャラがいる枠に動かしてよい" — IMC/W43-103),
  # and the loose version wrongly grabbed that later, unrelated 相手のキャラ mention.
  ("Move (Opponent)", r"相手の[^。]{0,20}キャラを[^。]{0,10}選び[^。]{0,30}枠[^。]{0,4}(動か(?!せない)|置く|移動)"),
  ("Move (Own)", r"[^。]{0,40}枠[^。]{0,4}(動か(?!せない)|置く|移動)"),
  ("Stand/Rest", r"【スタンド】|【レスト】"),
  ("Stock Boost", r"ストック置場に置"), ("Choice", r"次の効果から|から\d+つを選"),
  ("Early Play", r"レベル\d+以下[^。]{0,12}手札からプレイ|レベルを参照しない"),
  # Free Play (Alt Cost): pay an alternate cost (almost always discarding/returning a specific NAMED own
  # card) to play THIS card for 0 cost — distinct from Early Play (that's about the LEVEL gate, not the cost)
  # and from Summon (that's ANOTHER character entering play; here it's this card's OWN play, just for free).
  # Anchored on the game's exact templated phrasing for this mechanic (30 cards share it verbatim). User
  # taxonomy.
  ("Free Play (Alt Cost)", r"手札のこのカードをプレイするにあたり.{0,60}コスト0でプレイできる"),
  # Cost Substitute: distinct from Free Play (Alt Cost) above -- that one discounts THIS card's OWN play
  # cost; this one lets THIS card (from hand) substitute for a STOCK payment on a DIFFERENT card's ACT
  # ability elsewhere on the board. Confirmed by the user via LRC/WE47-06.
  # Widened to the general shape (dropped the 【起】-cost-specific trigger requirement): any time this card
  # substitutes for ANOTHER resource being paid/discarded elsewhere on the board, not just a stock cost --
  # confirmed via HOL/W104-027 (substitutes for 2 CHARACTER discards, not stock) and RZ/S132-073 (substitutes
  # for a stock payment, same as the original shape, just via a differently-worded trigger clause).
  ("Cost Substitute", r"あなたが自分の[^。]{0,10}の【起】のコストを払う時[^。]{0,10}手札のこのカードを[^。]{0,20}ストック[^。]{0,20}のかわりに控え室に置|手札のこのカードを[^。]{0,20}(のかわりに|の代わりに)控え室に置"),
  # "Cannot Attack" (an effect YOU inflict ON THE OPPONENT so THEIR character can't attack — a disruption
  # tool) is DELETED outright, not just narrowed. The user clarified the concept it was meant for, and after
  # checking the real corpus: every single occurrence of the old broad pattern (523/527) was actually
  # SELF-referential (このカード…できない, this card restricting its OWN attacking — a Drawback, moved below),
  # and after narrowing to require 相手の explicitly it sat at 0 real matches. Investigating why turned up
  # the reason: every real "make the opponent's character unable to attack" case in the corpus is delivered
  # via a GRANT (temporarily give that specific character the restriction, e.g. ALL/S90-072), which already
  # resolves correctly to Grant Ability (grants are checked before FAMPAT and the granted text can't decide
  # the family) — there is no standalone-FAMPAT-level case left for this name to catch. Same "delete once
  # confirmed genuinely empty" treatment as the old generic Card Select catch-all.
  # Drawback: THIS card cannot attack (unconditionally OR gated on any game-state condition — a missing
  # ally, low stock/clock, an opponent's board state, etc.). User's rule: ANY effect that adds power to a
  # card is a drawback -- when YOUR OWN cards come with can't-attack effects, conditional or not, they're
  # still drawbacks. Checked here, immediately after the narrowed Cannot Attack and BEFORE the generic
  # Restriction catch-all below (which would otherwise
  # swallow "…できない" first, since Restriction's own pattern is a bare "できない").
  ("Drawback", r"このカード[^。]{0,20}(アタックできない|サイドアタックできない|フロントアタックできない|ダイレクトアタックできない)"),
  ("Restriction", r"できない|選べない|受けない|動かせない"),
  # Self Sacrifice: the card's OWN ability sacrifices ANOTHER of your own characters to the waiting room, as
  # a direct mandatory/optional part of its effect (not a bracketed ［…］ payment — the "選び" selection verb
  # is how real payment brackets almost never phrase it, keeping this from stealing a cost bracket's family).
  # Distinct from Drawback (there the OPPONENT acts against your zones); here your OWN card's effect does it
  # to your OWN board. User taxonomy.
  # 2nd branch: a RANDOM hand card (自分の手札をランダムに1枚選び), not a chosen character -- same self-cost
  # purpose (the card's own effect costs its controller a resource), just an unchosen/random target.
  ("Self Sacrifice", r"(自分の|他の自分の)[^。]{0,20}キャラを[^。]{0,10}選び[^。]{0,6}控え室に置(く|き)|自分の手札をランダムに[^。]{0,10}選び[^。]{0,6}控え室に置"),
  # Delayed Sacrifice: a 2-ability LINKED variant of Self Sacrifice above -- ability 1 (on entering the
  # stage) just MARKS a target ("choose another of your own characters," no discard yet); ability 2 (later,
  # when THIS card leaves the stage) discards whichever character was marked. Two separate FAMPAT branches,
  # one per ability, since ab_cost() prices each ability independently. The 1st branch is anchored to the
  # FULL ability text (^...$) since a bare "choose another own character" fragment could otherwise appear as
  # a substring inside many unrelated compound abilities. User-named (2026-07-23). Confirmed via P4/S08-101.
  ("Delayed Sacrifice", r"^このカードが舞台に置かれた時[^。]{0,6}(あなたは)?他の自分のキャラを[^。]{0,6}選ぶ。?$|このカードの効果で選んだキャラを[^。]{0,6}控え室に置"),
  # Drawback: a negative effect against the CARD'S OWN CONTROLLER. Originally scoped only to "the OPPONENT
  # acts against your zones" (相手は/が…あなたの…選び…に置), confirmed via BD/W54-P03. Widened (2026-07-22,
  # Other-audit) to the broader BUT SAME-SPIRIT case of a SELF-inflicted risk with no opponent involved at
  # all -- the user confirmed this is still "Drawback" (the defining trait is "bad for the controller," not
  # WHO performs the bad action). Confirmed via vanilla-power-delta math across 8 example cards (LB/W02-065,
  # FT/S09-069, SAO/S51-P02, GST/SE22-09, MB/S10-019, PD/S29-105, IMC/W43-P02, KC/S42-021): every one prices
  # at or ABOVE vanilla (the Drawback signature -- power GIVEN as compensation, not taken), across 9
  # completely different triggers (level-up, unpaid cost, no matching ally, front-attacked-with-no-opponent,
  # Encore step, a linked ally leaving, opponent playing any climax, uncancelled damage) all sharing the SAME
  # final destination (this card discards ITSELF, unconditionally once triggered) -- the trigger varies, the
  # effect doesn't, so one family covers all of them. (Contrast `DC/W09-008`, same "self, on leaving stage"
  # shape but priced BELOW vanilla -- a real beneficial ability, not a drawback -- correctly excluded since
  # its actual trigger, "舞台から控え室に置かれた時," redirects to Memory instead of discarding outright.)
  ("Drawback", r"相手(は|が)[^。]{0,4}あなたの[^。]{0,20}を[^。]{0,10}選び[^。]{0,14}(山札の(上|下)|控え室|クロック置場)に置"),
  ("Drawback", r"このカードを控え室に置く(?!］)"),
  # A conditional, no-upside self-risk: reveal your own deck top; if it fails a check, your OWN clock
  # advances (a downside -- more clock cards is generally bad). Same "self-risk, no opponent" Drawback
  # spirit as the branch above. Crosses a sentence break (。) to the conditional clause, so needs . not [^。].
  ("Drawback", r"自分の山札の上から[^。]{0,10}公開する.{0,30}クロック置場に置"),
  # "This card's power does not increase or decrease": looks protective (immune to a Bomb/Drawback-style
  # opposing power cut) but the user's ruling is Drawback -- locking your OWN power also blocks every
  # BENEFICIAL modifier (Backup/Assist/Power Pump from teammates), and those are more common/valuable in
  # practice than a targeted power reduction would be, so the net effect on the controller is negative.
  ("Drawback", r"このカードはパワーが増減しない"),
  # Self-inflicted damage ("あなたに...ダメージを与える" -- deal damage to YOURSELF, not the opponent), on any
  # trigger, with no compensating benefit in the same clause. Same "self-risk, no opponent, compensated by
  # power elsewhere on the card" Drawback spirit as the branches above -- validated via vanilla-power-delta
  # across 3 real cards (NM/S24-049 +500, LB/W06-067 net 0 once its paired Encore is priced in, AOH/W127-048
  # +2000, all AT/ABOVE vanilla, the Drawback signature). "同じ" (the SAME amount, mirroring damage dealt to
  # the opponent back onto yourself when it was cancelled) is folded in alongside a literal digit/Ｘ, since
  # it's the same self-punishing shape just phrased relative to an earlier amount instead of a fixed number.
  ("Drawback", r"あなたに.{0,6}(\d+|[ＸX]|同じ)ダメージを与える"),
  # User's standing rule (2026-07-23, Other-audit round 11): ANY effect that gives power to a card is a
  # Drawback -- full stop, no separate name needed per shape. Drawbacks range 500-2000 depending on how bad
  # the granted downside is; going deeper than that (naming each individual self-risk shape) isn't worth the
  # time. Two more shapes folded in under this rule, both "self-risk, no opponent, no stated compensation in
  # the same clause" like the branches above:
  # (1) put a card from your OWN stock (top or bottom) into your OWN waiting room, with nothing gained in the
  # same clause -- confirmed via GC/S16-031, IM/S14-087, CL/WE07-75, DC/W23-056, KS/W55-028.
  ("Drawback", r"自分のストックの(上|下)から[^。]{0,6}枚?を[^。]{0,6}控え室に置"),
  # (2) on play, reveal the top of your own deck; if it's a climax, bury THIS card back into the deck and
  # shuffle (a proactive self-mulligan that costs a whole turn's tempo) -- confirmed via BM/S15-005,
  # SG/W39-008, SGS/S37-040, IM/S21-011.
  ("Drawback", r"自分の山札[^。]{0,10}公開する.{0,40}このカードを山札に戻.{0,20}シャッフル"),
  # 6 more shapes folded in under the same "self-risk, no opponent, no stated compensation" Drawback rule,
  # confirmed via the Other-family audit (2026-07-23):
  # (3) self -> bottom of deck, on a trigger OTHER than 【リバース】 (attack-end, Encore step, an アラーム clock-
  # top condition) -- the ONREV-gated version of this exact action is the established AutoKickToBottom family
  # (a separate, EARLIER-checked detection path via ONREV_PAT, not touched here); this branch only catches
  # the non-onrev-triggered leftover. Confirmed via CTB/W118-026, TRV/S92-069, ALL/S127-060.
  ("Drawback", r"このカードを[^。]{0,4}山札の下に置"),
  # (4) self -> own clock, gated by a marker or other condition broader than a bare on-reverse trigger (e.g.
  # "leaving the stage" generally, not just reversing) -- more clock cards is a real downside. The pure
  # on-reverse version is the established AutoKickToClock family (ONREV_PAT, unaffected). Confirmed via
  # MKI/W126-080.
  ("Drawback", r"このカードを[^。]{0,4}クロック置場に置"),
  # (5) dump your ENTIRE stock or deck into your OWN waiting room, no benefit in the same clause -- the
  # blunter, unqualified sibling of the "top/bottom 1 card" branch above. Confirmed via VRG/WE52-13.
  ("Drawback", r"自分の(山札|ストック)すべてを[^。]{0,6}控え室に置"),
  # (6) shuffle your own stock (no zone change, just randomize order) -- a mild self-inflicted loss of
  # planning certainty over your own resource. Confirmed via GIM/W124-056, GA17/S131-T12.
  ("Drawback", r"自分のストックを[^。]{0,4}シャッフルする"),
  # (7) this card's battle opponent never reverses -- a self-imposed combat limitation (this card can win
  # fights but never finish an opponent off). Confirmed via RKN/S115-085.
  ("Drawback", r"このカードのバトル相手は【リバース】しない"),
  # (8) voluntarily REVERSE this card yourself, with no stated benefit in the same clause -- surrendering
  # your own stand state (can't attack, vulnerable) is a real downside even though the trigger varies.
  # Confirmed via KMD/W96-058.
  ("Drawback", r"(あなたは)?このカードを【リバース】する(?!か)"),
  # (9) self -> bottom of your OWN STOCK, on a reveal-conditional trigger. Same self-relocation-with-no-
  # stated-benefit spirit as the deck-bottom/clock/waiting-room branches above. Confirmed via OVL/SE54-23.
  ("Drawback", r"このカードを[^。]{0,4}ストック置場の下に置"),
  # Switch Attack: choose another of your own STAGE characters (front row OR back row, explicitly row-
  # qualified so this doesn't swallow the Level/Memory-zone Exchange siblings above, which are checked
  # earlier anyway but use a bare "自分のキャラ"/"自分の《T》のキャラ" with no row qualifier) and swap positions
  # with THIS card. User's explanation (2026-07-23): the real purpose is to hand the attack off to a second
  # character in the SAME turn -- IMS/S61-103 swaps this card (front-row center, post-attack) into the back
  # row and pulls a back-row ally into the vacated attacking slot, functionally a bonus attack (similar in
  # effect to a re-Stand); BD/W125-039 confirmed as the SAME mechanic via a combo explanation with its
  # sibling BD/W125-082 (a CX Combo that re-Stands 039 after the swap, letting it clock-kick and attack
  # again, repeatable with another copy of 082) -- both cards use the swap to enable an extra attack this
  # turn, just via different combo shapes. User-named.
  ("Switch Attack", r"自分の(前列|後列)の(キャラ|「N」)を[^。]{0,10}このカードを[^。]{0,6}選び[^。]{0,10}入れ替え"),
  # Name Alias: a rules-text alias -- this card's (or another character's) card name is ALSO treated as (or
  # explicitly NOT treated as) a different named card, for the purpose of qualifying/disqualifying it under
  # other cards' name-matching conditions. Distinct from the official 【リンク】 marker (Link Identity above,
  # which is a bare, punctuation-free self-name declaration) -- this is regular ability text with a real
  # "も扱う"/"として扱わない" clause. Confirmed via LB/W02-108, PT/W07-029, RZ/S46-034 (grant an alias) and
  # 5HY/W83-021 (the negative form: explicitly deny an alias this card would otherwise be assumed to have).
  ("Name Alias", r"このカードは[^。]{0,6}「N」としても扱う|カード名は[^。]{0,10}「N」としても扱う|カード名は「N」として扱わない"),
  # Strip Trait (Own): the same action as Strip Trait/Strip Trait (All) below (remove a trait entirely), but
  # targeting your OWN side instead of the opponent's -- split out as its own scoped sibling per the user's
  # established "split by scope" convention (Bomb/Removal/Reverse Immunity all do this already), rather than
  # folding self-targeting into the opponent-targeting family. Confirmed via KJ8/S123-014, SGS/S37-088.
  ("Strip Trait (Own)", r"他のあなたの[^。]{0,20}キャラすべては[^。]{0,10}《T》をすべて失う"),
  # "Card Select" (a generic "\d+枚選" catch-all) is DELIBERATELY REMOVED as of the 2026-07-22 family-taxonomy
  # audit -- the user identified it as a meaningless label ("card select can be anything, dozens of unrelated
  # mechanics all select N cards"). Every recurring pattern that used to fall here now has its own real,
  # purpose-named family earlier in this list (Summon, Removal (...), AddMarker (...), Stock Gen, CX
  # Exchange, Memory Bank, Change, Clock/Hand Exchange, Self Sacrifice, Grant Trait, etc.). What's left after
  # exhausting this whole list is a genuine one-off: a bespoke card-specific mechanic that doesn't recur
  # often enough to represent a real family (e.g. a single ultra-rare finisher's unique combo of effects).
  # Those honestly fall through to "Other" below -- an honest label for "doesn't fit anywhere else", unlike
  # the old "Card Select" which pretended dozens of unrelated mechanics were one family. Do NOT re-add a
  # generic \d+枚選 catch-all here; if a NEW recurring pattern surfaces, give it a real name instead.
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
# A 4th CX Combo gate shape: pay the cost by discarding a SPECIFIC NAMED CLIMAX from hand ("手札の「N」を…
# 控え室に置" as the ［…］ cost bracket). Can't be detected on gen()-normalized text alone like the 3 shapes
# above, because gen() collapses EVERY name (character/event/climax) to the same generic 「N」 -- there is
# no way to tell from the generalized text whether this specific discarded card happens to be a climax.
# Needs the RAW (pre-gen) name cross-referenced against the actual climax card list, which build_cost_model
# populates into _CLIMAX_NAMES from its `clean` parameter (kept in-module, no new file I/O — see its own
# docstring). Checked from ab_cost() below (which still has the raw text), not from the pure family()
# function (which only ever sees already-generalized text). User taxonomy, found via CHA/W40-077.
_CLIMAX_NAMES = set()
_CX_DISCARD_GATE = re.compile(r"手札の「([^」]+)」を[^。]{0,10}控え室に置")
def _cx_discard_gate(raw_text):
    m = _CX_DISCARD_GATE.search(raw_text or "")
    return bool(m and m.group(1) in _CLIMAX_NAMES)
# On-reverse families (user taxonomy): when THIS card is reversed, a specific revenge / self effect. Checked
# BEFORE the generic families because "そのキャラを【リバース】" / "山札の下に置く" / "思い出にする" would otherwise
# fall to Other. AutoKick* = the card removes/relocates ITSELF on reverse (no opponent involved at all).
ONREV_PAT = [
    ("AutoKickToBottom", re.compile(r"【リバース】した時.*このカードを山札の下に置く")),
    # Verb widened する->する|して: some prints phrase this as optional ("…思い出にしてよい"), not just the
    # mandatory dictionary form. Found via GL/S52-052 (a conditional, optional variant landing in Other).
    ("AutoKickToMemory", re.compile(r"【リバース】した時.*このカードを思い出に(する|して)")),
    # 2nd trigger: "舞台から控え室に置かれた時" (about to be discarded to the waiting room from the stage, for
    # ANY reason, not just on reverse) redirects into Memory instead. Priced BELOW vanilla (confirmed via
    # DC/W09-008) -- a real beneficial upgrade (Memory > waiting room for recursion), NOT a Drawback, even
    # though it shares the "self, conditional" shape with the Drawback self-discard cluster nearby.
    ("AutoKickToMemory", re.compile(r"舞台から控え室に置かれた時.*このカードを思い出に(する|して)")),
    # This card puts ITSELF into its own clock on reverse (a self-relocation, not a Bomb -- the opponent's
    # character is never touched). Found via the ZM/W03-xxx "アラーム" clock-alarm card cluster.
    # "あなたは" made optional -- many prints phrase this as a flat mandatory action ("…このカードをクロック
    #置場に置く。") without the polite "あなたは…てよい" wrapper.
    ("AutoKickToClock",  re.compile(r"(バトル中の)?このカードが【リバース】した時.*(あなたは)?このカードをクロック置場に置")),
    # This card returns ITSELF to the deck and shuffles, on reverse -- a sibling of AutoKickToBottom, but a
    # genuinely different resource value: AutoKickToBottom guarantees a FIXED position (you know exactly when
    # you'll draw it back), while shuffling into the deck puts it at a RANDOM position (no such guarantee).
    # Confirmed by the user via DG/S02-058.
    # "バトル中の" made an accepted alternative to "バトルしている" -- same sibling AutoKickToClock already treats
    # these as interchangeable print-style phrasings of "while this card is in battle." Confirmed via MB/S10-092.
    ("AutoKickToDeckShuffle", re.compile(r"(バトルしている|バトル中の)このカードが【リバース】した時.*このカードを山札に戻.*シャッフル")),
]
# RedBomb/BlueBomb/YellowBomb/GreenBomb* = trade the OPPONENT's character away after THIS card wins its own
# battle (becomes reversed and the battle opponent qualifies under a level/cost condition) -- "punish the
# loser." User taxonomy: same underlying FUNCTION (a bomb) across every color, but the exact condition
# threshold AND the color/destination both change the ability's real cost, so every combination gets its
# OWN distinct family name -- never merged into one flat "Bomb" bucket (mirrors how Removal (...) is split
# by destination for the same reason). Color -> destination/action: red=re-reverse the opponent, blue=send
# them to the bottom of their own deck, yellow=send them to their own stock (+ the opponent loses a stock
# card too, present on 464/466 real samples, though the regex keys only on the destination since that alone
# is already a reliable signal). green=heal+clock, per the user, but NOT YET FOUND in this exact shape in
# the corpus after a real search -- flagged for the user to point at a concrete example before implementing.
# Condition types found: a FIXED level threshold (0, 1, 2, 3...), a FIXED cost threshold (0, 1...), the
# "AntiEarly" comparison (opponent's level > the CONTROLLING PLAYER's own game-level -- punishes early rush
# with an over-leveled character), and a variable Ｘ/X (computed by a formula elsewhere on the card). Each
# gets its own name suffix (LevelN / CostN / AntiEarly / LevelX) combined with the color, computed here
# rather than listed as ~20+ near-duplicate static strings.
_BOMB_TRIGGER = re.compile(r"(バトル中の)?このカードが【リバース】した時")
# "バトル相手の" is the common phrasing, but some prints say "このカードとバトルしているキャラの"/"このカードとバトル
#中のキャラの" instead -- same referent (the character THIS card is fighting), different wording. Both
# inner groups are non-capturing so the digit capture below stays group(1).
_BOMB_OPP = r"(?:バトル相手|このカードとバトル(?:中の|している)キャラ)の"
_BOMB_LEVEL = re.compile(_BOMB_OPP + r"レベルが(\d+)以下")
_BOMB_COST = re.compile(_BOMB_OPP + r"コストが(\d+)以下")
_BOMB_LEVELX = re.compile(_BOMB_OPP + r"レベルが[ＸX]以下")
_BOMB_ANTIEARLY = re.compile(_BOMB_OPP + r"レベルが相手のレベルより高い")
_BOMB_ACTION = {
    # Accepts both そのキャラ and そのバトル相手 as the pronoun -- real prints use either. Red covers BOTH
    # re-reverse AND Memory -- per the user, Memory is a newer-era variant of red, not a distinct 5th color,
    # since both are "soft"/temporary removals as opposed to Blue's permanent deck-bottom or Yellow's
    # economic stock-denial.
    "Red":    re.compile(r"あなたは(そのキャラ|そのバトル相手)を【リバース】してよい|(そのキャラ|そのバトル相手)を思い出にし"),
    "Blue":   re.compile(r"(そのキャラ|そのバトル相手)を山札の下に置"),
    "Yellow": re.compile(r"(そのキャラ|そのバトル相手)をストック置場に置"),
    # Green = heal the OPPONENT's clock (move their top clock card to their own waiting room -- structurally
    # the same "Heal" mechanic already established elsewhere in this taxonomy, just applied to the
    # OPPONENT's clock) as an ENABLING step, THEN bury the just-reversed battle opponent into that freed
    # clock slot. Confirmed via a real example (AZL/S102-P02/T48) after Blue/Yellow/Red searches came up
    # empty for this shape -- crosses a sentence break (。そうしたら、) so needs . not [^。].
    "Green":  re.compile(r"相手のクロックの上から1枚を[^。]{0,10}控え室に置.{0,20}(そのキャラ|そのバトル相手)をクロック置場に置"),
}
def _dynamic_bomb_name(text):
    if not _BOMB_TRIGGER.search(text): return None
    color = None
    for c, pat in _BOMB_ACTION.items():
        if pat.search(text): color = c; break
    if color is None: return None
    if _BOMB_ANTIEARLY.search(text): return f"AntiEarly{color}Bomb"
    if _BOMB_LEVELX.search(text): return f"{color}BombLevelX"
    m = _BOMB_LEVEL.search(text)
    if m: return f"{color}BombLevel{m.group(1)}"
    m = _BOMB_COST.search(text)
    if m: return f"{color}BombCost{m.group(1)}"
    return None
# Modal effect = "choose 1 of the next N effects" — cost the CHOICE as its own family, NOT by whichever
# sub-effect happens to match first (a "look-3 OR heal-1" must NOT pollute the Heal family — that's how a
# family never converges). Requires the CHOOSING (…のうち…選 / 次の効果から…選), so a "do both" bundle
# (次の2つの効果を…行う) is deliberately NOT a modal.
# "以下の効果のうち" ("among the following effects") is the same modal-choice phrasing as "次の...つの効果のうち",
# just worded with 以下 (following) instead of 次 (next) -- confirmed via STG/S60-001.
MODAL_PAT = re.compile(r"(次の[\dＸ０-９]+つの効果のうち|次の効果から|以下の効果のうち)[^。]{0,16}選")
# Grant = someone GAINS an auto/cont/act ability (give OR gain): 次の能力を与える / 『…』を与える / 能力を得る /
# 『…』を得る. Detected EARLY, like Modal, because the GRANTED ability's text (a look-deck, a heal, an encore,
# "cannot move"…) must NOT decide the family. Requires "能力を" or "』を" before 与え/得, so it does NOT match
# "ダメージを与える" (deal damage) nor "『…』を持つ" (HAS the ability — that's a condition, e.g. an Assist target).
# "次の能力を持つ" is the ONE narrow exception: unlike the excluded 『keyword』を持つ (a search CRITERION for some
# OTHER card, e.g. "choose a character that HAS 'Backup'"), "次の能力を持つ" self-referentially describes THIS
# card gaining a brand-new ability right here -- a real grant, just phrased with 持つ (possess) instead of
# 与え/得. Scoped tightly to that exact 4-character run so it can't swallow the excluded 『keyword』を持つ shape.
# Confirmed as the only real match corpuswide via SS/W14-079.
GRANT_PAT = re.compile(r"(能力を|』を)(与え|得)|次の能力を持つ")
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
    # Link Identity: the official 【リンク】 marker's WHOLE "ability" is just its own bare name (e.g. "ASMR",
    # "Groovy Mix") -- an identity tag other cards' text can reference/search for, carrying zero game action
    # of its own. Verified across the full corpus: every real 【リンク】-marked row has no Japanese punctuation
    # at all (a genuine effect would have at least a 。), so this check can't misfire on a real ability that
    # merely also happens to carry the marker. Intentional zero-function flavor, named so it stops looking
    # like an unaudited leftover in Other.
    if "リンク" in markers and "。" not in text and "、" not in text: return "Link Identity"
    # Declare: an AUTO/CONT/ACT whose WHOLE effect is announcing a flavor quote ("…と宣言してよい"/"…と言ってよい")
    # with no real game action -- already costed 0 via is_noop() (a structural no-op, same treatment as a
    # replay body), but previously had no family name of its own and fell to Other despite being fully
    # audited/intentional.
    if is_noop(text) or DECLARE_LIST_PAT.search(text) or _DECLARE_NAMELIST_PAT.match(text.strip()): return "Declare"
    # CX Combo FIRST (a combo encapsulates whatever sub-effects it mixes): the official 【CXコンボ】 MARKER is
    # the definitive signal; also the climax-area gate in the text (incl. the "CX置場" abbreviation).
    if "CXコンボ" in markers or "ＣＸコンボ" in markers or CXC_PAT.search(text): return "CX Combo"
    if MODAL_PAT.search(text): return "Modal"          # a "choose 1 of N" modal — its own family
    if GRANT_PAT.search(text):                         # grants an ability — its own family, not what's granted
        return "Pump & Grant" if _is_citing_pump(text) else "Grant Ability"  # dual if it also pumps (outside the quote)
    for name, pat in ONREV_PAT:
        if pat.search(text): return name
    dyn_bomb = _dynamic_bomb_name(text)
    if dyn_bomb: return dyn_bomb
    for k, v in KW.items():
        if k not in text: continue
        # "『応援』を持つ" ([a card] that HAS the Assist ability) — any keyword cited this way is being used as a
        # SEARCH/SELECTION CRITERION for some OTHER card (e.g. "look at your deck, choose a card that has
        # 『Change』, add it to hand" — a Search, not a Change ability), never the keyword's own performance.
        # General guard (applies to all 12 keywords, not just one) — same category as the 記憶/経験/共鳴
        # condition-keyword exclusion above: found via a 291-card audit of the "Change" family, where cards
        # searching for OTHER cards with the Change keyword were wrongly filed as Change themselves.
        if re.search("『" + re.escape(k) + "』を持つ", text): continue
        # "アンコールステップ" (the Encore STEP, a phase/timing reference — "at the start of the Encore step…") CONTAINS
        # the keyword アンコール but is NOT the Encore keyword MECHANIC. Only divert to Encore if アンコール appears
        # OUTSIDE that phrase; otherwise it's a timing-gated effect that must file by what it actually does.
        if k == "アンコール" and "アンコール" not in text.replace("アンコールステップ", ""): continue
        # "あなたが『集中』を使った時、…" (when you use Brainstorm [elsewhere on this card or another], if X…) only
        # NAMES 集中 as the TRIGGER an AUTO effect is gated on -- it is not itself performing the flip-cards
        # action, same category as the already-excluded 記憶/経験/共鳴 condition-keywords (see the block
        # comment above KW). The real effect here is whatever comes after (often Power Pump or Burn) -- must
        # fall through to FAMPAT instead of being swallowed into "Brainstorm". A genuine Brainstorm ability
        # reads "【起】集中 ［cost］ 山札の上から…" (集中 right after the ACT marker, describing ITS OWN action).
        if k == "集中" and re.search(r"『集中』を使った", text): continue
        return v
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
# Same "Declare" no-op family as NOOP_PAT above, but 3 more textual shapes that don't fit its single-quoted
# "'X' と宣言してもよい" template: (1) a LIST-form declare ("among the following card names, the one you chose,
# declare" -- no single quoted name, since the choice is open); (2) a MANDATORY, SYMMETRIC declare by every
# player ("すべてのプレイヤーは『…』と宣言する", no optional てよい); (3) the companion clause that makes a later
# declared name retroactively apply to a card already in the climax area. All carry zero game action of their
# own, same as the base NOOP_PAT shape. Confirmed via SMP/W60-T01, STG/S60-T06, GRI/S84-115.
DECLARE_LIST_PAT = re.compile(r"以下のカード名のうちあなたが選んだ1つを宣言する|すべてのプレイヤーは.{0,20}と宣言する|クライマックス置場のカードのカード名は宣言したカード名としても扱う")
# A 4th Declare shape: the text is NOTHING but a back-to-back list of quoted card names, no verb/punctuation
# at all -- the raw OPTIONS list for an adjacent list-form Declare ability on the same card (e.g. the menu
# DECLARE_LIST_PAT's "among the following names" ability actually offers). Zero game action of its own, same
# as every other Declare shape. Confirmed via SMP/W60-T01, GRI/S84-115.
_DECLARE_NAMELIST_PAT = re.compile(r"^(「[^」]*」)+$")

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
    if re.search(r"return[^.]{0,40}opponent[^.]{0,20}(character|hand)", tl): return "Removal (Hand)"
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
    # A replay row reads "〔ACTION NAME〕　〔effect body〕" (e.g. "全力全開！　このカードを…"). The citing
    # ability refers back to the replay by that ACTION NAME ("…「全力全開！」を発動する"). We don't know where
    # the name ends, so generate every candidate name = the text up to each whitespace boundary, plus the
    # whole string, then try them LONGEST-first (the most specific name that still matches wins).
    r = rtext.strip(); cands = []
    for m in re.finditer(r"[\s　]+", r): cands.append(r[:m.start()])   # prefix ending at each space (name candidates)
    cands.append(r)                                                   # also try the entire replay text as the name
    return sorted({x for x in cands if len(x.strip()) >= 2}, key=len, reverse=True)   # longest (most specific) first
def _rp_find_citer(rtext, abs_, ri):
    # Locate the ability on THIS card that invokes the replay at index ri. Walk the candidate action-names
    # (longest first); for each, scan every OTHER non-replay ability; find the name as a substring; accept it
    # ONLY when what immediately follows is an activation verb (を発動する / を使用する / をトリガー / する) or a
    # clause break (。、，）) or end-of-text -- i.e. the ability genuinely "uses" that named action, rather than
    # just happening to contain those characters mid-sentence. Returns (citer_index, matched_name) or (None,None).
    for cand in _rp_action_prefixes(rtext):
        for j, a in enumerate(abs_):
            if j == ri or REPLAY_MARK in "".join(a.get("markers") or []): continue   # skip self + other replays
            ct = a.get("text") or ""; idx = ct.find(cand)
            while idx != -1:                                     # a name can appear more than once; check each hit
                after = ct[idx + len(cand):]                     # the text right after the candidate name
                if _RP_VERB.match(after) or re.match(r"^[。、，）\)]", after) or after == "":
                    return j, cand                               # verb/boundary follows -> a real invocation
                idx = ct.find(cand, idx + 1)                     # otherwise keep looking for the next occurrence
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

CXC_FLOOR = 0   # CX-combo absorbers are floored at 0 — the SAME non-negativity every other beneficial
                # absorber gets (a replay citer already uses max(0, v); step 2 rejects negative residuals for
                # beneficial families). By construction a CX combo is resolved LAST and IS the card's leftover
                # residual, whatever value that is — so it gets NO arbitrary 500 minimum. The one guard kept is
                # 0: a BENEFICIAL combo cannot cost negative (a negative only ever came from single-card over-
                # stat noise, e.g. an over-statted promo dumping its surplus onto its lone unknown CXC sig; CX
                # Combo is not in neg_fams, so it is not a real drawback family). Empirically, dropping the 500
                # floor to 0 RAISES the Explained% acceptance metric and CUTS the suspect count (flooring a lone
                # CXC absorber above its card's residual was itself manufacturing suspects).

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
# ---- scaling-pump sub-case: "+500 PER matching card" or "X = count x N" (base is a per-unit RATE, not a
# flat number) -- the printed rate alone isn't the cost; the model reads it as rate x an ASSUMED count of
# matching cards, since the parser can't know the real board state. Assumed count depends on WHAT is being
# counted (verified against 644 isolated single-ability measured samples, 2026-07-22):
#   - a SPECIFIC NAMED card ("「N」1枚につき") -- rare to have even 1 extra copy in play -> assume 0.5
#   - a small just-revealed/milled sample ("それらのカード", e.g. mill 2 then count matches among them,
#     not your whole board) -> assume 1
#   - the OPPONENT's characters ("相手のキャラの枚数") -- typically a fuller/less controllable board than
#     your own -> assume 4
#   - anything else (a generic trait/character count on YOUR board) -> assume 2
_PUMP_RATE1 = re.compile(r"1枚につき、このカードのパワーを[＋+](\d+)")
_PUMP_RATE2 = re.compile(r"枚数[×x](\d+)に等しい")
_PUMP_NAMED_CT = re.compile(r"「N」1枚につき")
_PUMP_SMALL_CT = re.compile(r"それらのカード")
_PUMP_OPP_CT   = re.compile(r"相手のキャラの枚数")
_PUMP_POS_RESTRICT = re.compile(r"後列|前列")
def _pump_scale_estimate(gen_text):
    mt = _PUMP_RATE1.search(gen_text) or _PUMP_RATE2.search(gen_text)
    if not mt: return None
    rate = int(mt.group(1))
    if rate <= 0: return None
    if _PUMP_NAMED_CT.search(gen_text): count = 0.5
    elif _PUMP_SMALL_CT.search(gen_text): count = 1
    elif _PUMP_OPP_CT.search(gen_text): count = 4
    else: count = 2
    factor = count
    if _PUMP_TEMP.search(gen_text): factor *= 0.5
    if _PUMP_POS_RESTRICT.search(gen_text): factor *= 0.5
    return max(500, r500(rate * factor))
def pump_self_estimate(gen_text):
    """Multiplicative estimate for a Power Pump (self) gen sig: a flat printed +N (base N x
    ½^(temporal + #conditions)), or -- if the pump SCALES per-unit -- rate x an assumed matching-card
    count (see _pump_scale_estimate). None if neither pattern is readable. Floored at 500."""
    if _PUMP_SCALE.search(gen_text):
        return _pump_scale_estimate(gen_text)
    mt = _PUMP_SELF_N.search(gen_text)
    if not mt: return None
    n = int(mt.group(1))
    if n <= 0: return None
    k = (1 if _PUMP_TEMP.search(gen_text) else 0) + len(_PUMP_COND.findall(gen_text))
    return max(500, r500(n * (0.5 ** k)))

# ---- partial cabling: Salvage multiplicative estimate (see documentation/pump_cost_model.md §"Salvage") ----
# Salvage's base is the NET ADVANTAGE of the swap, not a printed number like Pump's -- so instead of parsing
# a magnitude, this classifies the PACKAGE into one of two net-advantage buckets and reads the base off that:
#   - net-0 "pure recycle": the payment discards the SAME broad category (CX) as what's salvaged (CX too),
#     or the salvage TARGET is a single SPECIFIC NAMED card (「N」, i.e. a narrow, low-flexibility get) --
#     both patterns measured at a clean MODE of 500 across many isolated single-ability samples.
#   - net+1 "upgrade": anything else (most commonly: discard a CX/any card for an UNRESTRICTED or
#     trait-restricted CHARACTER) -- measured mode 1000.
# Validated against 729 isolated single-ability measured Character samples (2026-07-22): this 2-way split
# beats the flat family median on the metric that matters for Explained% -- 86.1% within +/-500 vs the flat
# median's 75.0% (comparable margin to Power Pump's own 84% vs 75% win). A further attempt to also fold in
# trigger-difficulty and a hand-loss payment credit made the fit WORSE, not better -- salvage's payment-credit
# interactions are genuinely more tangled than pump's (matches the OPEN item in pump_cost_model.md: "real-loss
# payments are NOT a clean fixed per-type factor"), so this stays a plain 2-way categorical read, no further
# multiplication. Only touches ESTIMATED (LOW) sigs, same as pump_self_estimate.
_SALV_BRACKET = re.compile(r"［([^］]*)］")
_SALV_CX = re.compile(r"CX|クライマックス")
_SALV_NAMED = re.compile(r"「N」(?!を含む)")   # "の「N」を選び" = one specific card (narrow) -- but "カード名に
# 「N」を含む" is a NAME-GROUP restriction (several cards sharing a name fragment, e.g. all "Yotsuba"-named
# cards), functionally a trait-lock, NOT a single low-flexibility target -- must NOT get the same discount.
def salvage_estimate(gen_text):
    """Multiplicative-model estimate for a Salvage gen sig: 500 for a same-category (CX<->CX) or
    named-target recycle, 1000 for an unrestricted/trait-restricted character upgrade."""
    m = _SALV_BRACKET.search(gen_text)
    payment = m.group(1) if m else ""
    rest = gen_text[m.end():] if m else gen_text
    pay_cx = bool(_SALV_CX.search(payment))
    tm = re.search(r"(.{0,40})手札に戻", rest)
    target_clause = tm.group(1) if tm else ""
    if (pay_cx and _SALV_CX.search(target_clause)) or _SALV_NAMED.search(target_clause):
        return 500
    return 1000

# ---- partial cabling: Look & Reorder (see documentation/pump_cost_model.md) ----
# "Look at top N, put back in any order" (好きな順番) -- a scry/setup effect, base 1000 unconditioned
# (10/10 isolated samples). A "なら/場合/いれば" condition gate halves it to 500 (1 isolated sample: a
# CX-gated attack-trigger version) -- same condition rule as Pump, reusing _PUMP_COND. Thin data (14 total
# isolated samples) so guarded narrowly: only the plain "look N, reorder all of them" shape, excluding the
# ALARM keyword variant (a different, recurring-check mechanic that measured 2000, not 500, despite also
# having a "なら" gate -- Alarm's own timing already IS the cost driver) and any "選び" partial-keep variant
# (choose SOME of the revealed cards to keep, discard rest -- a different, richer effect than pure reorder).
_LR_ALARM = re.compile(r"アラーム")
_LR_PARTIAL = re.compile(r"カードを\d*枚まで選び")
def look_reorder_estimate(gen_text):
    if _LR_ALARM.search(gen_text) or _LR_PARTIAL.search(gen_text):
        return None
    k = len(_PUMP_COND.findall(gen_text))
    return max(500, r500(1000 * (0.5 ** k)))


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
        Confidence is evidence-aware (conf_evidence over the sig's n_samples + mode_share).
        Family is overridden to "CX Combo" when this specific occurrence discards a NAMED CLIMAX as its
        cost (_cx_discard_gate, checked on the RAW text -- this can't be folded into the pooled
        signature's own family() call, since gen() collapses every name the same way and two cards
        sharing a signature could differ on whether their discarded card happens to be a climax)."""
        mk = "".join(markers or "")
        sig = self.RP_SIG_OVERRIDE.get((card_number, idx), mk + " :: " + gen(text or ""))
        if _cx_discard_gate(text):
            fam = "CX Combo"
        elif sig in self.cost:
            vt = self.variant_text.get(sig, (mk, gen(text or "")))
            fam = family(vt[1], vt[0])
        else:
            fam = family(gen(text or ""), mk)
        if sig in self.cost:
            return (self.cost[sig], self.method[sig],
                    conf_evidence(self.method[sig], self.nsamp.get(sig), self.mshare.get(sig)),
                    fam)
        return None, None, None, fam

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
            # The override map = (card_number, ability_index) -> the signature that ability MUST be counted under.
            # Downstream, the citer (index cj) is measured as if its text already included the replay body, and
            # the replay row itself (index ri) is measured under its own sig -- which STEP 0 then fixes at cost 0,
            # so the replay body's cost is counted exactly once (on the citer) and never double-counted.
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
    _CLIMAX_NAMES.clear()
    _CLIMAX_NAMES.update(c["name"] for c in clean if c.get("type") == "Climax" and c.get("name"))
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
    # HOW (residual by subtraction): on a multi-ability card whose per-card delta = sum of ALL its ability
    # costs, if every ability but one already has a cost, the missing one MUST equal delta - sum(known). We
    # pool that inferred value across every card where the same sig is the lone unknown, then take the mode
    # (rounded 500) as its cost. FIXPOINT: solving one sig can turn a 2-unknown card into a 1-unknown card,
    # so we repeat the whole sweep; `new` counts sigs resolved this pass and we stop as soon as a pass
    # resolves nothing. range(10) is just a hard cap so a pathological graph can't loop forever.
    for _ in range(10):
        res = collections.defaultdict(list)
        for cn, dl, sg, e in multi:
            unk = [s for s in sg if s not in cost]                 # sigs on this card still lacking a cost
            if len(unk) == 1 and not is_absorber(unk[0]):         # exactly one unknown, and it's directly solvable
                res[unk[0]].append(dl - sum(cost[s] for s in sg if s in cost))   # inferred cost from this card
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
    # Build a per-family median from every sig already priced by measurement/residual (grouping by the sig's
    # family), then hand any still-unknown non-absorber sig that family's median as a fallback GUESS.
    fam_known = collections.defaultdict(list)
    for sig, cst in cost.items():
        if sig in replay_sigs or sig in noop_sigs: continue   # structural 0s are not effect costs -> don't bias family medians
        if not is_absorber(sig): fam_known[fam_of(sig)].append(cst)
    fam_med = {f: r500(st.median(v)) for f, v in fam_known.items()}
    for sig in ALLV:
        if sig in cost or is_absorber(sig): continue
        cost[sig] = fam_med.get(fam_of(sig), 500); method[sig] = "estimated"; nsamp[sig] = 0; rng[sig] = (None, None)   # 500 if the family has no data at all
    # STEP 3b absorber residual ABSORBER: with all non-absorber sigs known, derive each CXC / citer sig
    # from the cards where it is now the lone unknown -> absorber = delta - sum(others). BOTH kinds floored
    # at >= 0 (CXC via CXC_FLOOR==0): a beneficial combo / a folded replay body never gives power back.
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
    # STEP 3d partial cabling: override the flat-median ESTIMATE of Power Pump (self) and Salvage sigs with
    # their respective multiplicative/net-advantage models (estimated-only; measured/residual untouched).
    # Stays method "estimated" (LOW) — still a guess, just an evidence-based one instead of a flat median.
    for sig in ALLV:
        if method.get(sig) != "estimated": continue
        fam = fam_of(sig)
        if fam == "Power Pump (self)":
            est = pump_self_estimate(variant_text[sig][1])
        elif fam == "Salvage":
            est = salvage_estimate(variant_text[sig][1])
        elif fam == "Look & Reorder":
            est = look_reorder_estimate(variant_text[sig][1])
        else:
            continue
        if est is not None: cost[sig] = est
    # enforce the CXC floor (== 0) on EVERY CX-combo sig — clamps only a genuinely NEGATIVE combo (incl. a
    # single-ability measured combo whose lone over-statted print measured below 0) up to 0; positives pass.
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
    # (f) CX-combo non-negativity: floor a beneficial combo at 0 (== CXC_FLOOR), mirroring the JP model — no
    # arbitrary 500 minimum; the combo IS the residual, but a beneficial effect cannot cost negative.
    for c in ex_cards:
        if not c["is_char"]: continue
        for (_, _, txt, s) in c["sigs"]:
            if en_family(txt) == "CX Combo" and encost.get(s, 0) < CXC_FLOOR:
                encost[s] = CXC_FLOOR; enmethod[s] = "estimated"
    return encost, enmethod


ENCONF = {"measured": "HIGH", "matched": "MEDIUM", "residual": "MEDIUM", "estimated": "LOW"}
