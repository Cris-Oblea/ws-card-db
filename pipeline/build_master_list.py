# build_master_list.py — LISTA MAESTRA: TODAS las habilidades (variantes) con costo.
# Metodo por fila: MEDIDO (cartas de 1 hab, delta directo) -> RESIDUAL (resto seeds conocidos, con
# propagacion) -> ESTIMADO (mediana de la familia). EN oficial confiable (official_en). Todo en 500s.
import json, os, re, csv, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import official_en

D = os.path.dirname(os.path.abspath(__file__))
clean = json.load(open(os.path.join(D, "cardlist_clean.json"), encoding="utf-8"))
en_cards = json.load(open(os.path.join(D, "cardlist_en.json"), encoding="utf-8"))
era = json.load(open(os.path.join(D, "card_era.json"), encoding="utf-8"))  # {card_number: legacy|modern}

def pb(c):
    t = 1 if "soul" in (c.get("trigger") or []) else 0
    return 3000 + 2500*c["level"] + 1500*c["cost"] - 1000*t - 1000*(c["soul"]-1)
def ra(c):
    return [a for a in c["abilities"] if (a.get("text") or "").strip() not in ("-","ー","－","")]
ZT = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")
TRAIT = re.compile(r"《[^》]*》"); NAME = re.compile(r"「[^」]*」")
def gen(t):
    t = t.translate(ZT); t = TRAIT.sub("《T》", t); t = NAME.sub("「N」", t)
    return re.sub(r"\s+", " ", t).strip()
def r500(x): return int(round(x/500.0)*500)
def mode500(xs): return collections.Counter(r500(x) for x in xs).most_common(1)[0][0]

# ---------- FAMILIA (regex transparente, ampliada para reducir "Otro") ----------
KW = {"助太刀":"Backup","応援":"Assist","集中":"Brainstorm","アンコール":"Encore","経験":"Experience",
      "記憶":"Memory","絆":"Bond","チェンジ":"Change","加速":"Accelerate","共鳴":"Resonance",
      "シフト":"Shift","大活躍":"GreatPerformance","フォース":"Force","ヒール":"Heal","バウンス":"Bounce"}
FAMPAT = [
  ("Burn", r"相手に\d+ダメージ"),
  ("Heal", r"自分のクロック[^。]{0,20}(控え室|ストック|手札|思い出)に置"),
  ("ClockKick", r"相手のキャラ[^。]{0,20}(クロック置場|クロックに)置"),
  ("Bounce", r"相手のキャラ[^。]{0,12}手札に戻"),
  ("ReturnDeck", r"相手の(控え室|キャラ)[^。]{0,20}山札に(戻|加え)"),
  ("ReverseOpp", r"相手のキャラ[^。]{0,12}【リバース】"),
  ("OppDisrupt", r"相手の(手札|ストック|山札|思い出|レベル置場|クロック)"),
  ("Salvage", r"自分の(控え室|思い出)[^。]{0,22}手札に(戻す|加える)"),
  ("Search", r"山札[^。]{0,14}見[てる][^。]{0,28}(手札|加える)"),
  ("LookDeck", r"山札[^。]{0,4}(上から)?[^。]{0,6}\d+枚[^。]{0,8}見"),
  ("Comeback", r"(控え室|山札)[^。]{0,22}キャラ[^。]{0,14}舞台に置"),
  ("StockGen", r"(山札の上|デッキトップ|山札の上から)[^。]{0,12}ストック置場に置"),
  ("Draw", r"引く"),
  ("AddToHand", r"手札に(加える|加え|戻す)"),
  ("PowerBoardAll", r"あなたの[^。]{0,16}キャラすべてに[^。]{0,8}パワーを[＋+]"),
  ("PowerSelf", r"このカードのパワーを[＋+]"),
  ("PowerOther", r"キャラ[^。]{0,10}パワーを[＋+]"),
  ("PowerDebuff", r"パワーを[－\-]"),
  ("SoulMod", r"ソウルを[＋+\-－]"),
  ("LevelMod", r"レベルを[＋+\-－]"),
  ("GrantAbility", r"』を与える|の能力を得"),
  ("MillSelf", r"山札の上から\d+枚を[^。]{0,8}控え室"),
  ("Move", r"(前列|後列|別の枠|横の枠|の枠)に[^。]{0,6}(動かす|置く|移動)"),
  ("StandRest", r"【スタンド】|【レスト】"),
  ("StockBoost", r"ストック置場に置"),
  ("Choice", r"次の効果から|から\d+つを選"),
  ("EarlyPlay", r"レベル\d+以下[^。]{0,12}手札からプレイ|レベルを参照しない"),
  ("CannotAttack", r"アタックできない|サイドアタックできない"),
  ("CannotEffect", r"できない|選べない|受けない"),
  ("CardSelect", r"\d+枚(まで)?選"),
]
def family(text):
    for k, v in KW.items():
        if k in text: return v
    for name, pat in FAMPAT:
        if re.search(pat, text): return name
    return "Otro"

# ---------- recolectar cartas validas: delta + sigs de cada habilidad ----------
EN_AB = official_en.build(clean, en_cards)       # {(jp_code, ability_idx): en_text} confiable
cards = []                                       # (card_number, delta, [sig...], era)
variant_cards = collections.defaultdict(list)    # sig -> [card_number...]
variant_occ = collections.defaultdict(list)      # sig -> [(card_number, idx)...]
iso = collections.defaultdict(lambda: {"m": [], "l": []})  # sig -> deltas aislados modern/legacy
variant_text = {}                                # sig -> (markers, gen_text)
for c in clean:
    if c["type"] != "Character" or c["excluded"]: continue
    if c["power"] is None or c["level"] is None or c["cost"] is None or c["soul"] is None: continue
    ab = ra(c)
    if not ab: continue
    sigs = []
    for i, a in enumerate(ab):
        mk = "".join(a.get("markers") or [])
        sig = mk + " :: " + gen(a.get("text", ""))
        sigs.append(sig)
        variant_cards[sig].append(c["card_number"])
        variant_occ[sig].append((c["card_number"], i))
        variant_text.setdefault(sig, (mk, gen(a.get("text", ""))))
    delta = pb(c) - c["power"]
    e = era.get(c["card_number"])
    cards.append((c["card_number"], delta, sigs, e))
    if len(ab) == 1:
        (iso[sigs[0]]["m"] if e == "modern" else iso[sigs[0]]["l"]).append(delta)

ALLV = set(variant_cards)
print(f"variantes (habilidades distintas) totales: {len(ALLV)}")
print(f"cartas validas: {len(cards)}  | habilidades con EN oficial confiable: {len(EN_AB)}")

# ---------- PASO 1: MEDIDO (aisladas) ----------
cost = {}; method = {}; nsamp = {}; rng = {}; eralab = {}
for sig, d in iso.items():
    use = d["m"] if len(d["m"]) >= 2 else (d["m"] + d["l"])
    if not use: continue
    cost[sig] = mode500(use); method[sig] = "medido"; nsamp[sig] = len(use)
    rng[sig] = (min(use), max(use)); eralab[sig] = "modern" if len(d["m"]) >= 2 else ("legacy" if not d["m"] else "mix")
print(f"PASO1 medido: {len(cost)} variantes")

# ---------- PASO 2: RESIDUAL con propagacion ----------
multi = [(cn, dl, sg, e) for (cn, dl, sg, e) in cards if len(sg) > 1]
for it in range(10):
    res = collections.defaultdict(list)
    for cn, dl, sg, e in multi:
        unknown = [s for s in sg if s not in cost]
        if len(unknown) == 1:
            known_sum = sum(cost[s] for s in sg if s in cost)
            res[unknown[0]].append(dl - known_sum)
    new = 0
    for sig, samples in res.items():
        if sig in cost: continue
        cost[sig] = mode500(samples); method[sig] = "residual"; nsamp[sig] = len(samples)
        rng[sig] = (min(samples), max(samples)); eralab[sig] = "—"; new += 1
    print(f"  PASO2 iter {it+1}: +{new} variantes por residual (total {len(cost)})")
    if new == 0: break

# ---------- VALIDACION: error en cartas multi totalmente conocidas ----------
errs = []
for cn, dl, sg, e in multi:
    if all(s in cost for s in sg):
        errs.append(abs(dl - sum(cost[s] for s in sg)))
if errs:
    within = sum(1 for x in errs if x <= 500) / len(errs)
    print(f"VALIDACION (cartas multi conocidas n={len(errs)}): |error|<=500 en {within*100:.0f}% | err medio {sum(errs)/len(errs):.0f}")

# ---------- PASO 3: ESTIMADO (mediana de familia) ----------
fam_known = collections.defaultdict(list)
for sig, cst in cost.items():
    fam_known[family(variant_text[sig][1])].append(cst)
import statistics as st
fam_med = {f: r500(st.median(v)) for f, v in fam_known.items()}
for sig in ALLV:
    if sig in cost: continue
    f = family(variant_text[sig][1])
    cost[sig] = fam_med.get(f, 500); method[sig] = "estimado"; nsamp[sig] = 0
    rng[sig] = (None, None); eralab[sig] = "—"
print(f"PASO3 estimado: {sum(1 for s in ALLV if method[s]=='estimado')} variantes (resto)")

# ---------- EN por variante: cualquier ocurrencia (carta,idx) con EN confiable ----------
def variant_en(sig):
    for occ in variant_occ[sig]:
        if occ in EN_AB: return EN_AB[occ]
    return ""
def variant_ex(sig):
    for cn, idx in variant_occ[sig]:
        if (cn, idx) in EN_AB: return cn
    return variant_cards[sig][0]

# ---------- armar filas ----------
def conf(sig):
    m = method[sig]
    if m == "medido":
        lo, hi = rng[sig]
        if nsamp[sig] >= 5 and hi - lo <= 1000: return "ALTA"
        if nsamp[sig] >= 2: return "MEDIA"
        return "BAJA"
    if m == "residual":
        lo, hi = rng[sig]
        if nsamp[sig] >= 3 and hi - lo <= 1000: return "MEDIA"
        return "BAJA"
    return "BAJA"

rows = []
for sig in ALLV:
    mk, txt = variant_text[sig]
    lo, hi = rng[sig]
    rows.append({"fam": family(txt), "type": mk, "jp": txt, "en": variant_en(sig),
                 "cost": cost[sig], "metodo": method[sig], "n": nsamp[sig],
                 "rango": (f"{lo}..{hi}" if lo is not None else "—"), "era": eralab[sig],
                 "ex": variant_ex(sig), "conf": conf(sig), "ncards": len(variant_cards[sig])})
order = {"medido": 0, "residual": 1, "estimado": 2}
rows.sort(key=lambda r: (r["fam"], order[r["metodo"]], -r["cost"], -r["n"]))

# ---------- Excel ----------
wb = Workbook(); ws = wb.active; ws.title = "Todas las habilidades"
hdr = ["Familia", "Tipo", "Habilidad (JP real, generalizada)", "EN oficial",
       "Costo (500s)", "Método", "Confianza", "n", "Rango", "Era", "# cartas", "Carta ej."]
ws.append(hdr)
for c in range(1, len(hdr)+1):
    cell = ws.cell(1, c); cell.fill = PatternFill("solid", fgColor="2F5597")
    cell.font = Font(bold=True, color="FFFFFF"); cell.alignment = Alignment(wrap_text=True, vertical="top")
cf = {"ALTA": "C6EFCE", "MEDIA": "FFEB9C", "BAJA": "FFC7CE"}
mf = {"medido": "D9E1F2", "residual": "FCE4D6", "estimado": "F2F2F2"}
for r in rows:
    ws.append([r["fam"], r["type"], r["jp"], r["en"], r["cost"], r["metodo"], r["conf"],
               r["n"], r["rango"], r["era"], r["ncards"], r["ex"]])
    ws.cell(ws.max_row, 5).font = Font(bold=True)
    ws.cell(ws.max_row, 6).fill = PatternFill("solid", fgColor=mf[r["metodo"]])
    ws.cell(ws.max_row, 7).fill = PatternFill("solid", fgColor=cf[r["conf"]])
for col, w in zip("ABCDEFGHIJKL", [15, 10, 60, 58, 11, 10, 10, 5, 12, 8, 8, 13]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"

# hoja resumen
ws2 = wb.create_sheet("Resumen")
tot = len(rows)
bym = collections.Counter(r["metodo"] for r in rows)
byc = collections.Counter(r["conf"] for r in rows)
byf = collections.Counter(r["fam"] for r in rows)
ws2.append(["LISTA MAESTRA DE HABILIDADES — Weiss Schwarz (cartas custom)"]); ws2["A1"].font = Font(bold=True, size=13)
for line in ["", f"Habilidades (variantes) totales: {tot}", "",
    "Por método:", f"  medido (delta directo, cartas de 1 hab): {bym['medido']}",
    f"  residual (resto seeds conocidos, propagado): {bym['residual']}",
    f"  estimado (mediana de familia): {bym['estimado']}", "",
    "Por confianza:", f"  ALTA: {byc['ALTA']}   MEDIA: {byc['MEDIA']}   BAJA: {byc['BAJA']}", "",
    f"Con EN oficial verificado: {sum(1 for r in rows if r['en'])}", "",
    "Lee la hoja 'Cómo usar' para interpretar costo, método y confianza."]:
    ws2.append([line])
ws2.append([""]); ws2.append(["Por familia (top):"])
for f, n in byf.most_common():
    ws2.append([f"  {f}", n])
ws2.column_dimensions["A"].width = 52

ws3 = wb.create_sheet("Cómo usar")
for line in ["CÓMO USAR ESTA LISTA", "",
    "Qué es: referencia de balance para cartas CUSTOM. 'Quiero este efecto -> cuesta X power'.",
    "Costo = power que se le RESTA a la carta (power_real = power_base - costo). Siempre múltiplo de 500.",
    "power_base = 3000 + 2500·nivel + 1500·costo − 1000·(trigger soul) − 1000·(soul−1).", "",
    "COLUMNAS:",
    "  Método MEDIDO  = costo medido directo en cartas de UNA sola habilidad (lo más fiable).",
    "  Método RESIDUAL= la habilidad solo aparece junto a otras; se restan las ya conocidas y queda su costo.",
    "  Método ESTIMADO= no medible aún; se usa la mediana de su familia (orientativo, confianza BAJA).",
    "  Confianza ALTA/MEDIA/BAJA según nº de muestras y dispersión del rango.",
    "  n = muestras usadas; Rango = min..max de las mediciones; # cartas = en cuántas cartas aparece.", "",
    "PRINCIPIOS (de toda la sesión):",
    "  • Economía de recursos: carta a mano/stock = +1 recurso ≈ +1000; al waiting = pierdes recurso.",
    "  • Era: legacy (<2017) ≈ 2× el costo moderno (powercreep). Diseña con valores MODERNOS.",
    "  • Bundle = SUMA; modal 'elige 1 de N' = la opción más fuerte; multi-trigger = valor × nº disparos.",
    "  • CX-combo / gate-duro: piso ~500 sin importar la potencia (paga en ensamblar el combo).",
    "  • Para efectos NOVEDOSOS: descompón en primitivas, aplica modificadores, compón, redondea a 500.",
    "    (ver GUIA_COSTO_HABILIDADES.xlsx para el modelo completo y ejemplos)"]:
    ws3.append([line])
ws3["A1"].font = Font(bold=True, size=12); ws3.column_dimensions["A"].width = 100

out = os.path.join(D, "Lista_Habilidades_COMPLETA.xlsx"); wb.save(out)
print(f"\nTOTAL filas: {tot} | medido {bym['medido']} residual {bym['residual']} estimado {bym['estimado']}")
print(f"Otro (familia): {byf['Otro']} | con EN: {sum(1 for r in rows if r['en'])}")
print("escrito:", out)
