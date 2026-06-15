# Conclusiones — Costo de habilidades en Weiss Schwarz (2026-06-14)

## 1. Lo que se entregó
**`Lista_Habilidades_COMPLETA.xlsx`** — las **15.889 habilidades distintas** que existen en el juego (todo el universo de Characters medibles), cada una con un **costo en power** (múltiplo de 500), su familia, el texto JP real, el EN oficial cuando se pudo verificar, y dos columnas críticas de honestidad: **Método** y **Confianza**. Más la **`GUIA_COSTO_HABILIDADES`** para costear efectos que NO existen en ninguna carta.

Sirve para lo que querías: **consultar "este efecto → cuesta X"** y **inspirarte para cartas nuevas**.

## 2. El modelo de costo (lo que de verdad entendí del juego)
El power que se le RESTA a una carta por tener una habilidad **≈ la ventaja neta de recursos/tempo que esa habilidad da.**
- **Economía de recursos** (el porqué profundo): llevar una carta a **mano o stock = +1 recurso ≈ +1000**; mandarla al waiting = perder recurso. Por eso un heal a la mano *siempre* trae coste: el coste **paga** por el recurso, no lo descuenta.
- **Facilidad de ejecución**: un efecto on-play sin coste ni condición es CARO; gateado (coste, condición, trigger poco fiable) es más barato. Como la mayoría vienen gateados, **la moda de costos cae en 500–1000**.
- **Era**: las cartas legacy (<2017) cuestan ~2× lo que costaría hoy el mismo efecto (powercreep). Hay que diseñar con valores **modernos**.
- **Composición**: bundle (haz todo) = **SUMA**; modal (elige 1 de N) = la **mejor opción**, no la suma; multi-trigger = valor × nº de disparos.
- **CX-combo / gate-duro**: piso de ~500 sin importar la potencia (el costo se paga en ensamblar el combo, no en power).
- **Familias distintas, regímenes distintos**: el burn se cuesta por *facilidad*, el heal por *destino*, el board-buff por *cantidad×2*. No se unifican.

## 3. Qué funcionó y qué no (la lección metodológica)
- ❌ **La regresión NO sirvió** (lineal, log-lineal, symbolic/gplearn, random-forest). Probado a fondo y descartado: los modificadores son **efecto-dependientes** (un coste baja un burn pero *paga* un heal), así que no existe un coeficiente universal. Esto era contraintuitivo —tú mismo esperabas que la regresión armara la tabla— pero los datos lo refutaron.
- ❌ **El descompositor v3 (ridge/iterativo) tampoco** — descomponer TODA carta a la vez propaga errores y da costos absurdos (0, −6500). Esa fue la lista vieja "pésima y llena de errores".
- ✅ **Lo que sí funciona: MEDIR, no inferir.** Las cartas de **una sola habilidad** dan el costo exacto (delta directo, sin descomposición). Desde esa base limpia se **propaga por residual** (en cartas multi, restar lo ya conocido) y lo irreducible se **estima** por familia.
- ✅ **La prueba de que el método es correcto:** reconstruí 34.767 cartas multi-habilidad sumando los costos de sus partes y el resultado **acierta al ≤500 en el 98%** (error medio 68 power). El modelo aditivo + residual es sólido.

## 4. Confianza y límites (honesto)
- **Medido (3.835)** = lo más fiable, costo directo. **Residual (8.580)** = derivado restando seeds limpios. **Estimado (3.474)** = mediana de familia, orientativo.
- **ALTA+MEDIA confianza = 4.279 filas**; el resto es BAJA (muchos residuales de 1 muestra). Pero ojo: la validación global del 98% dice que incluso los BAJA aciertan en agregado — la marca BAJA es prudencia, no "está mal".
- **EN oficial en 5.087 filas** (32%), todas **verificadas** (markers+números+keywords calzan con el JP); donde no se pudo verificar quedó en blanco, nunca un EN equivocado. El japonés es la verdad; el EN es comodidad.
- Lo que queda fino: bundles raros (modal/cost-branch que no son SUMA), per-marker pumps (valor variable), y la cola larga de efectos únicos.

## 5. Cómo usarlo para cartas custom
1. **Efecto que ya existe** → búscalo en la lista (filtra por Familia), mira el Costo y el Método/Confianza.
2. **Efecto nuevo** → usa la GUÍA: descompón en primitivas, aplica modificadores (coste, condición×fiabilidad, era, amplitud), compón (suma/modal/multi-trigger), redondea a 500.
3. **Regla de oro**: piensa en recursos. ¿La habilidad te da una carta (mano/stock)? ≈ +1000. ¿Es fácil de disparar? más cara. ¿Depende de un climax? piso 500.

## 6. Si se quiere seguir (opcional)
- Subir confianza de los residuales ponderando por la calidad de sus seeds (un residual de seeds ALTA es casi ALTA).
- Más cobertura de EN (alinear EN en cartas multi con más reglas).
- Validar a mano una muestra de "estimado" para calibrar las medianas de familia.
- Detectar y costear aparte los operadores no-aditivos (modal/replacement) que hoy el residual asume como suma.
