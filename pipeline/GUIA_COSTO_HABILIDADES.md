# Guía de Costo de Habilidades — Weiss Schwarz (para cartas CUSTOM)
*Referencia de balance: "quiero este efecto → cuesta X power". Costo = cuánto power se le RESTA a la carta (power_real = power_base − costo). **Todo en múltiplos de 500.** Construido por medición (moda) + modelo de juego. v1 — 2026-06-14.*

---
## 0. CÓMO PENSAR EL COSTO (el modelo)
**El power-cost ≈ VENTAJA NETA de recursos/tempo que da el efecto.** Fórmula mental:

> **costo ≈ (valor base del efecto) × (facilidad de ejecución) × (factor era) → redondear a 500**

- **Economía de recursos:** carta a **mano o stock = +1 recurso ≈ +1000**; carta al **waiting = pierdes recurso**. Un efecto que te DA recurso debe llevar coste que lo balancee.
- **Facilidad:** fácil (on-play, sin coste, sin condición) = caro; con coste / condición / trigger poco fiable = más barato. La MAYORÍA de efectos vienen "gateados" → por eso la mayoría caen bajo (500-1000).
- **Era:** legacy (<2017) ≈ **2×** el costo moderno (powercreep). Diseña con valores MODERNOS.
- **Redondeo:** siempre a 500 (las cartas se mueven así). Usa la **MODA**, no la media.

---
## 1. PRIMITIVAS — valor BASE de cada efecto (limpio, moda, 500s, MODERN)
*Estos son efectos atómicos "fáciles" (on-play, sin coste). Las trabas (sección 2) los bajan.*

| Efecto | Costo base | Notas / sub-tipos |
|---|---|---|
| **Burn 1** (1 daño al rival) | **1500** | cancelable por climax. Con coste → 500. Multi-burn ≈ ×nº instancias. |
| **Heal** (clock → waiting/stock/mano/memoria) | **1000** | coste-independiente; → **fondo del mazo = 500** (peor). |
| **Draw 1** | **1000** | = +1 recurso. |
| **Salvage** char (waiting→mano) | **1000** | **CX o carta cualquiera = 500**. |
| **Search/Tutor** (mira top-N, agrega 1) | **1000** | **universal + descarta-1 (ciclar) = 2000** (agarrar cualquier carta, incl. climax). |
| **Return-3** (devolver ≤3 del waiting rival a su mazo) | **1500** | anti-salvage / ensuciar mazo rival. |
| **Stock-gen** (deck → stock) | **500** | recurso casi-neutro (cambias draw por stock). |
| **Bounce** (personaje rival → su mano) | **500–1000** | (n chico). |
| **Self power-pump** | **CIP one-shot (ese turno) = X/3** · **CONT mi-turno = X/2** · **CONT siempre ≈ 2X** | el "siempre" defiende también, por eso más caro. |
| **Board-buff** "+X a TODOS tus otros 《T》" | **2×X** | level-tiered (L0/1→+500, L2→+1000, L3→+1500); **en L3 el +1500 colapsa a ~500**. |
| **Clock-kick** (reversar char rival → su clock) | **≈ burn (~500-1000)** | incancelable (premium) PERO trigger "reversar" poco fiable → se compensa. |
| **Backup (助太刀) X** (keyword) | **2×X** | +1500 legacy = 4000 (grandfather). |
| **Assist (応援) +X** (a los de adelante) | genérico **3×X** / con trait **X** | |
| **Brainstorm** (集中) mill N | mill4=**1000**, mill5=**2000** | |
| **CIP +X power** ya cubierto arriba (self-pump CIP = X/3) | | |

---
## 2. MODIFICADORES (ajustan la primitiva — redondear a 500 al final)
- **× COSTE pagado:** **EFECTO-DEPENDIENTE** (no universal). Si el efecto DA recurso (heal→mano/stock, salvage), el coste lo *balancea* (no descuenta, ya está incluido). Si el efecto NO da recurso (burn), pagar coste lo **baja** (burn 1500→1000 con coste, →500 con coste+condición).
- **× CONDICIÓN (multiplicativo, graduado por estrictez Y fiabilidad):**
  - suave (mi-turno, 2+《T》, "carta con 'X' en el nombre") = **×½**
  - estricta (nombre COMPLETO específico) = **×¼**
  - **poco fiable** (depende del board rival: "reversar", "el rival tiene X") = descuenta **más** (puede no poder usarse).
  - OR de condiciones descuenta menos que AND. Stackean multiplicativo.
- **× ERA:** legacy ≈ **2×** modern.
- **AMPLITUD de selección:** universal (cualquier carta) >> restringido a trait (≈ ½).
- **CANCELABLE vs INCANCELABLE:** el daño que pasa por trigger-check se cancela con climax; el que mueve cartas (clock-kick, refresh) NO → premium, pero pésalo contra la fiabilidad del trigger.

---
## 3. OPERADORES DE COMPOSICIÓN (cartas multi-efecto)
- **Bundle (haz todos):** **SUMA** de los componentes.
- **Modal "elige K de N":** valor de la(s) **opción(es) elegible(s)** (≈ la más fuerte), NO la suma, NO ×nº de opciones.
- **Cost-branch "paga→todos / no-paga→elige 1":** **suma (el techo "ambos")**.
- **Multi-trigger OR:** si los disparos son INDEPENDIENTES (ambos pueden ocurrir) = valor-por-disparo **× nº de disparos**; si son excluyentes (solo uno jamás) = ×1.

---
## 4. RÉGIMEN ESPECIAL: CX-COMBO / gate-duro
Una habilidad que **depende OBLIGATORIAMENTE de un climax específico** (en CX zone, o nombre propio en level/memoria) tiene un **PISO de ~500 casi sin importar cuán potente sea** (el costo se paga en ensamblar el combo, no en power). Detéctalo por la CONDICIÓN de texto, no por el marcador 【CXコンボ】 (legacy no lo tenía). NO sumes sus efectos.

---
## 5. CÓMO COSTEAR UN EFECTO NOVEDOSO (paso a paso)
1. **Descomponer** en efectos atómicos (sección 1) + identificar el operador de composición (sección 3).
2. **¿Gate-duro / CX-combo?** → piso ~500, listo.
3. Para cada efecto: **valor base** (sección 1) × **modificadores** (sección 2: coste, condición×fiabilidad, era, amplitud).
4. **Componer** (suma / modal=mejor-opción / multi-trigger×n).
5. **¿Da recurso (carta a mano/stock)?** súmale ~1000 si NO lleva coste que lo balancee.
6. **Redondear a 500.**

**Ejemplo (validado): CGS/WS01-P17** (Backup 2500 + AUTO "al usar el backup, descarta 2 → manda al waiting un char rival de nivel alto"):
- Backup 2500 = 2×2500 = **5000**.
- AUTO = removal (sacar char rival = ventaja de board), pero gateado (solo al usar backup + descarte-2 + target nivel-alto) → **~1000**.
- Total **6000** = el delta real de la carta. ✓

---
*Confianza: primitivas SÓLIDAS medidas (moda, n≥varias). Aún aproximados/por-refinar: bounce, pump-both-turns (montos grandes), heal-fondo-mazo, y soul (casi nunca aparece aislado). El modelo costea lo conocido Y lo novedoso por razonamiento.*
