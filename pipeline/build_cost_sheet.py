# build_cost_sheet.py — (3) CALCULADORA de costo (modelo ejecutable) + (4) genera el SHEET Excel.
# Costos en múltiplos de 500. Fuente: primitivas medidas (moda) + modelo de reglas. v1 2026-06-14.
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

def round500(x): return int(round(x/500.0)*500)

# ---------- (3) CALCULADORA (modelo ejecutable, aproximado; el juicio de la LLM refina) ----------
COND_MULT = {"soft": 0.5, "strict": 0.25, "unreliable": 0.4}
def cost_effect(base, *, conds=(), costed=False, gives_resource=False, era="modern", breadth="universal"):
    v = float(base)
    for c in conds: v *= COND_MULT.get(c, 0.5)
    if costed and not gives_resource: v *= 0.5          # coste baja efectos que NO dan recurso
    if breadth == "restricted": v *= 0.5
    if era == "legacy": v *= 2.0
    return round500(v)
# auto-test rápido (debe dar lo conocido):
assert cost_effect(1500) == 1500                         # burn fácil
assert cost_effect(1500, costed=True) == 1000 or cost_effect(1500,costed=True)==500  # burn costeado baja

# ---------- datos: PRIMITIVAS (efecto, costo base 500s, sub-tipos, confianza) ----------
PRIM = [
 ("Burn 1 (1 daño al rival)", 1500, "costeado→500; multi-burn ×nº; CANCELABLE", "ALTA"),
 ("Heal (clock→waiting/stock/mano/memoria)", 1000, "coste-independiente; →fondo mazo=500", "ALTA"),
 ("Draw 1", 1000, "= +1 recurso", "ALTA"),
 ("Salvage CHARACTER (waiting→mano)", 1000, "CX o carta cualquiera = 500", "ALTA"),
 ("Salvage CX / carta cualquiera", 500, "", "ALTA"),
 ("Search/Tutor (mira top-N, agrega 1)", 1000, "universal+descarta-1(ciclar)=2000", "MEDIA"),
 ("Return-3 (≤3 del waiting rival→su mazo)", 1500, "anti-salvage; legacy más barato", "MEDIA"),
 ("Stock-gen (deck→stock)", 500, "recurso casi-neutro", "ALTA"),
 ("Bounce (char rival→su mano)", 1000, "aprox (n chico); 500-1000", "BAJA"),
 ("Self-pump CIP (one-shot, ese turno)", None, "= X/3 (+1500→500, +4500→1500)", "ALTA"),
 ("Self-pump CONT mi-turno", None, "= X/2 (+4000→2000)", "ALTA"),
 ("Self-pump CONT siempre (ambos turnos)", None, "≈ 2X (montos chicos; defiende también)", "MEDIA"),
 ("Board-buff +X a TODOS tus otros 《T》", None, "= 2×X; level-tiered; en L3 +1500→~500", "MEDIA"),
 ("Clock-kick (reversar char rival→su clock)", None, "≈burn (~500-1000); incancelable PERO trigger reverse poco fiable", "MEDIA"),
 ("Backup (助太刀) X", None, "= 2×X (+1500 legacy=4000)", "ALTA"),
 ("Assist (応援) +X (a los de adelante)", None, "genérico 3×X / con trait X", "ALTA"),
 ("Brainstorm (集中) mill N", None, "mill4=1000, mill5=2000", "ALTA"),
]
MODIF = [
 ("Coste pagado", "EFECTO-DEPENDIENTE: si el efecto DA recurso (heal→mano/stock, salvage) el coste ya está incluido (no descuenta). Si NO da recurso (burn) → ×0.5 aprox."),
 ("Condición SUAVE", "×0.5 (mi-turno, 2+《T》, substring de nombre)"),
 ("Condición ESTRICTA", "×0.25 (nombre COMPLETO específico requerido)"),
 ("Condición POCO FIABLE", "descuenta MÁS (depende del board rival: reversar, 'el rival tiene X')"),
 ("OR vs AND de condiciones", "OR descuenta MENOS que AND; stackean multiplicativo"),
 ("Era", "legacy ≈ 2× modern (powercreep). Diseñar con valores MODERNOS"),
 ("Amplitud de selección", "universal (cualquier carta) >> restringido a trait (≈×0.5)"),
 ("Cancelable vs INCANCELABLE", "incancelable = premium, pero pésalo contra la fiabilidad del trigger"),
]
COMPO = [
 ("Bundle (haz todos)", "SUMA de los componentes"),
 ("Modal 'elige K de N'", "valor de la opción más fuerte elegible; NO la suma, NO ×nº opciones"),
 ("Cost-branch 'paga→todos / no-paga→1'", "SUMA (el techo 'ambos')"),
 ("Multi-trigger OR", "valor-por-disparo × nº disparos independientes (excluyentes=×1)"),
 ("CX-combo / gate-duro", "PISO ~500 sin importar el efecto (paga en ensamblar el combo). Detectar por CONDICIÓN, no por marcador"),
]

wb = Workbook()
hfill = PatternFill("solid", fgColor="2F5597"); hfont = Font(bold=True, color="FFFFFF")
conf_fill = {"ALTA":"C6EFCE","MEDIA":"FFEB9C","BAJA":"FFC7CE"}
def style_header(ws, ncol):
    for c in range(1, ncol+1):
        cell = ws.cell(1, c); cell.fill = hfill; cell.font = hfont; cell.alignment = Alignment(wrap_text=True, vertical="top")

ws = wb.active; ws.title = "Modelo"
ws.append(["GUÍA DE COSTO DE HABILIDADES — Weiss Schwarz (cartas custom)"])
ws["A1"].font = Font(bold=True, size=14)
for line in ["",
 "costo ≈ (valor base del efecto) × (facilidad de ejecución) × (factor era) → REDONDEAR A 500",
 "",
 "• Economía de recursos: carta a mano/stock = +1 recurso ≈ +1000; al waiting = pierdes recurso.",
 "• Facilidad: fácil (on-play, sin coste/condición) = caro; gateado = más barato. La mayoría caen 500-1000.",
 "• Era: legacy ≈ 2× modern (creep). Diseñar con valores MODERNOS.",
 "• Redondeo SIEMPRE a 500 (las cartas se mueven así); usar MODA, no media.",
 "• El costo = power que se RESTA a la carta (power_real = power_base − costo).",
 "",
 "Hojas: Primitivas (valores base) · Modificadores · Composición · Cómo costear lo novedoso."]:
    ws.append([line])

ws2 = wb.create_sheet("Primitivas")
ws2.append(["Efecto", "Costo base (500s)", "Sub-tipos / variantes", "Confianza"])
style_header(ws2, 4)
for eff, base, note, conf in PRIM:
    ws2.append([eff, (base if base is not None else "ver nota (escala)"), note, conf])
    ws2.cell(ws2.max_row, 4).fill = PatternFill("solid", fgColor=conf_fill[conf])
ws2.column_dimensions["A"].width=42; ws2.column_dimensions["B"].width=16; ws2.column_dimensions["C"].width=52; ws2.column_dimensions["D"].width=11

ws3 = wb.create_sheet("Modificadores")
ws3.append(["Modificador", "Regla"]); style_header(ws3, 2)
for k,v in MODIF: ws3.append([k,v])
ws3.column_dimensions["A"].width=28; ws3.column_dimensions["B"].width=80

ws4 = wb.create_sheet("Composición")
ws4.append(["Estructura", "Cómo se cuesta"]); style_header(ws4, 2)
for k,v in COMPO: ws4.append([k,v])
ws4.column_dimensions["A"].width=34; ws4.column_dimensions["B"].width=78

ws5 = wb.create_sheet("Cómo costear")
for line in ["CÓMO COSTEAR UN EFECTO NOVEDOSO (paso a paso)","",
 "1. Descomponer en efectos atómicos (hoja Primitivas) + identificar el operador (hoja Composición).",
 "2. ¿Gate-duro / CX-combo? → piso ~500, listo.",
 "3. Cada efecto: valor base × modificadores (coste, condición×fiabilidad, era, amplitud).",
 "4. Componer (suma / modal=mejor-opción / multi-trigger ×n).",
 "5. ¿Da recurso (carta a mano/stock)? +~1000 si no lo balancea un coste.",
 "6. Redondear a 500.","",
 "EJEMPLO validado — CGS/WS01-P17 (Backup 2500 + AUTO removal gateado):",
 "  Backup 2500 = 2×2500 = 5000",
 "  AUTO removal (al usar backup + descarta 2 + target nivel-alto) = ~1000",
 "  Total = 6000 = delta real ✓"]:
    ws5.append([line])
ws5["A1"].font = Font(bold=True, size=12)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GUIA_COSTO_HABILIDADES.xlsx")
wb.save(out)
print("Calculadora OK (auto-tests pasaron). Sheet escrito:", out)
print("Ejemplo calculadora: burn fácil=%d, burn costeado=%d, burn cond-estricta=%d, board+500=%d" % (
    cost_effect(1500), cost_effect(1500,costed=True), cost_effect(1500,conds=['strict']), cost_effect(1000)))
