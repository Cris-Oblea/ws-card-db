# Weiss Schwarz — Costo de habilidades (workspace)

Proyecto: **referencia de balance para cartas CUSTOM**. "Quiero este efecto → cuesta X power".
Costo = power que se le RESTA a una carta respecto a su base (`power_real = power_base − costo`), **siempre en múltiplos de 500**.

---

## ★ ENTREGABLES (lo que vas a usar)

| Archivo | Qué es |
|---|---|
| **`Lista_Habilidades_COMPLETA.xlsx`** | **EL producto.** Las **15.889** habilidades distintas del juego, cada una con su costo medido. Hojas: *Todas las habilidades* (la tabla), *Resumen*, *Cómo usar*. |
| `GUIA_COSTO_HABILIDADES.xlsx` / `.md` | El **modelo** para costear efectos NUEVOS que no existen en ninguna carta (primitivas + modificadores + composición + ejemplos). Complementa la lista. |
| `phases_reference.md` | Referencia de fases/timing del juego (del ruling oficial JP). |

### Cómo leer la lista
- **Costo (500s)**: el power a restar. **Método**: `medido` (delta directo en cartas de 1 habilidad, lo más fiable) ·
  `residual` (la habilidad solo sale acompañada; se restan las ya conocidas y queda su costo) ·
  `estimado` (mediana de su familia; orientativo).
- **Confianza** ALTA/MEDIA/BAJA según nº de muestras y dispersión. **n** = muestras. **Rango** = min..max medido.
- **EN oficial**: traída del harvest inglés y **verificada** (markers + números + keywords calzan con el JP); si no calza, queda en blanco (nunca se muestra un EN equivocado).

---

## Cómo regenerar el entregable
```
python build_master_list.py      # -> Lista_Habilidades_COMPLETA.xlsx
python build_cost_sheet.py       # -> GUIA_COSTO_HABILIDADES.xlsx
```

### Scripts activos (raíz)
| Script | Función | Lee |
|---|---|---|
| `build_master_list.py` | Construye la lista completa (medido→residual→estimado) | `cardlist_clean.json`, `cardlist_en.json`, `card_era.json`, `official_en.py` |
| `official_en.py` | Match CONFIABLE habilidad JP → EN oficial (filtro de consistencia) | `cardlist_clean.json`, `cardlist_en.json` |
| `build_cost_sheet.py` | Genera la guía/modelo para efectos novedosos | (autónomo) |

### Datos canónicos (raíz)
| Archivo | Qué es |
|---|---|
| `cardlist_clean.json` | **Fuente de verdad JP**: 63.350 cartas normalizadas (stats + habilidades + markers). |
| `cardlist_en.json` | **Harvest del sitio oficial inglés**: 18.532 cartas con texto EN oficial. |
| `card_era.json` | `card_number → legacy(<2017)/modern(≥2017)` (extraído; reemplaza al CSV de 76 MB). |

---

## Log de duelos del simulador (extra)
El simulador (Blake Thoennes, Unity) **sí** deja un log de partida jugable en `Player.log`
(en `%USERPROFILE%/AppData/LocalLow/Blake Thoennes/Weiss Schwarz/`), entremezclado con
ruido de Unity. `parse_duel_log.py` lo limpia y estructura:
```
python parse_duel_log.py                 # usa el Player.log por defecto
python parse_duel_log.py <ruta.log>      # un log específico (p.ej. Player-prev.log)
```
Salidas en `duel_logs/`: `duel_<log>.txt` (transcript legible: pre-partida / partida por
fases / post-partida) + `duel_<log>.json` (eventos estructurados + resumen). Captura mulligan,
jugadas, efectos resueltos (con texto EN), costos, ataques, encore, brainstorm y las decisiones
de la IA (SearchValue). Reporta toda línea sin clasificar (nada se descarta en silencio).
Uso para el proyecto: registro empírico de **cómo se pilotea** un mazo (timing y valoración real),
complementa los AI scripts de `StreamingAssets/AIData/`.

## Carpetas
- **`pipeline/`** — scripts y datos crudos para *regenerar* lo canónico (harvest JP/EN, limpieza, datación de sets, features). Para correrlos hay que co-locar los datos; normalmente no hace falta tocarlos.
- **`fuentes/`** — material de aprendizaje crudo: reglas oficiales (`ws_rule*.txt`), scans del manual (`manual_*`), transcripción de video, macros, screenshots.
- **`_archive/`** — TODO lo obsoleto/experimental (reversible, nada borrado): el viejo sistema de costos v3 (`costs_*`, `ws_decompose*`), el EN lossy (`en_match`, `variant_tr*`), los experimentos de regresión (`v4_*`, `log_linear`) que **fallaron**, mediciones de primitivas superadas, intermedios de firmas/traducción, y la lista vieja `Power_by_ability_OFICIAL.xlsx` (superada).

---

## Modelo de costo (resumen)
`power_base = 3000 + 2500·nivel + 1500·costo − 1000·(trigger soul) − 1000·(soul−1)`
- **Economía de recursos**: carta a mano/stock ≈ +1 recurso ≈ +1000; al waiting = pierdes recurso.
- **Era**: legacy ≈ 2× el costo moderno (powercreep) → diseña con valores MODERNOS.
- **Composición**: bundle = SUMA · modal "elige 1 de N" = la opción más fuerte · multi-trigger = valor × nº disparos.
- **CX-combo / gate-duro**: piso ~500 sin importar la potencia (paga en ensamblar el combo).
- **Validación del método**: en 34.767 cartas multi totalmente reconstruidas, el costo aditivo acierta a ≤500 en el **98%** (error medio 68 power).
