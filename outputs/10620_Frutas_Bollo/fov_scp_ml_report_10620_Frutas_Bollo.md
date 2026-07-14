# Informe individual SCP vs ML — 10620_Frutas_Bollo

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10620 | Fichero: `TA_FOV_SCP_ML_10620_Frutas_Bollo.csv`
**Batch/Run:** ID_BATCH=[62] | ID_RUN_STAGING=[57] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **3.441 series candidatas**, **664 (19.3%)** son comparables en el semestre completo (6M). WAPE SCP=79.5%, WAPE ML=97.5%, mejora relativa ponderada=-22.7%, reduccion absoluta de error=-27.038.493, series comparables=664, historico total=149.644.466.

Frecuencia de victoria en 6M: ML gana 288 (43.4%), SCP gana 372 (56.0%), empate 4 (0.6%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **3.441**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 1.852 | 53.8% |
| COMPARABLE | 664 | 19.3% |
| NOT_COMPARABLE_ML_EXCLUDED | 662 | 19.2% |
| NOT_COMPARABLE_NO_HISTORY | 129 | 3.7% |
| NOT_COMPARABLE_MISSING_SCP | 126 | 3.7% |
| NOT_COMPARABLE_MISSING_ML | 8 | 0.2% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **2.503** (72.7% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 1.906 |
| ShortSeries | 597 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 3.441 | 183 | 5.3% |
| M2 | 3.441 | 216 | 6.3% |
| M3 | 3.441 | 341 | 9.9% |
| M4 | 3.441 | 301 | 8.7% |
| M5 | 3.441 | 308 | 9.0% |
| M6 | 3.441 | 377 | 11.0% |
| RECENT_3M | 3.441 | 428 | 12.4% |
| OLDER_3M | 3.441 | 468 | 13.6% |
| 6M | 3.441 | 664 | 19.3% |

---

## 3. Semestre completo (6M)

WAPE SCP=79.5%, WAPE ML=97.5%, mejora relativa ponderada=-22.7%, reduccion absoluta de error=-27.038.493, series comparables=664, historico total=149.644.466.

Frecuencia de victoria: ML gana 288 (43.4%), SCP gana 372 (56.0%), empate 4 (0.6%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=71.5%, WAPE ML=94.3%, mejora relativa ponderada=-31.8%, reduccion absoluta de error=-14.196.911, series comparables=428, historico total=62.449.009.

Frecuencia de victoria: ML gana 139 (32.5%), SCP gana 275 (64.3%), empate 14 (3.3%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=78.9%, WAPE ML=87.4%, mejora relativa ponderada=-10.8%, reduccion absoluta de error=-7.404.816, series comparables=468, historico total=87.195.457.

Frecuencia de victoria: ML gana 199 (42.5%), SCP gana 246 (52.6%), empate 23 (4.9%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): -31.8%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): -10.8%. La mejora mantiene el mismo signo en ambos trimestres.

% victorias ML: 32.5% (primer trimestre) vs 42.5% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 183 | 58.3% | 53.8% | +7.8% | 43.2% | 49.2% | 7.7% |
| M2 | 216 | 66.5% | 83.6% | -25.6% | 31.0% | 59.3% | 9.7% |
| M3 | 341 | 71.9% | 83.5% | -16.0% | 33.7% | 61.3% | 5.0% |
| M4 | 301 | 75.9% | 76.5% | -0.8% | 42.2% | 49.5% | 8.3% |
| M5 | 308 | 74.5% | 75.9% | -1.9% | 37.3% | 55.2% | 7.5% |
| M6 | 377 | 71.7% | 71.4% | +0.4% | 42.7% | 53.1% | 4.2% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +7.8% vs +0.4%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 288 (43.4%), SCP gana 372 (56.0%), empate 4 (0.6%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **-27.038.493** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| MovingAverage3M | 252 | 44.8% | 103.0% | 135.8% | -31.9% | -7.5% | no |
| SeasonalNaive | 186 | 50.0% | 56.2% | 70.2% | -24.9% | +0.9% | no |
| AutoARIMA | 79 | 40.5% | 88.8% | 101.6% | -14.5% | -13.0% | no |
| AutoETS | 38 | 44.7% | 76.0% | 69.3% | +8.8% | -7.7% | no |
| HistoricAverage | 26 | 46.2% | 117.6% | 97.1% | +17.4% | -2.6% | no |
| MovingAverage12M | 21 | 33.3% | 69.1% | 105.6% | -53.0% | -56.7% | no |
| ADIDA | 19 | 10.5% | 100.9% | 207.7% | -105.8% | -78.6% | no |
| AutoTheta | 14 | 42.9% | 156.0% | 130.6% | +16.3% | -6.7% | no |
| TSB | 13 | 7.7% | 86.4% | 123.4% | -42.9% | -48.5% | no |
| CrostonSBA | 6 | 33.3% | 198.3% | 428.8% | -116.3% | -90.8% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| seasonal discrete | 530 | 41.5% | 83.4% | 108.0% | -29.4% | -9.9% | no |
| syntetos-boylan | 121 | 50.4% | 131.7% | 135.6% | -3.0% | +1.6% | no |
| x11 seasonal | 13 | 53.8% | 37.5% | 27.4% | +26.9% | +11.7% | no |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| seasonal_discontinuous_acceptable | 246 | 48.4% | 91.4% | 90.6% | +0.8% | -1.9% | no |
| intermittent_insuficient | 173 | 35.3% | 73.6% | 117.7% | -59.9% | -27.7% | no |
| lumpy_insuficient | 140 | 39.3% | 92.8% | 147.0% | -58.3% | -17.7% | no |
| intermittent_recentRelease | 24 | 54.2% | 121.0% | 124.4% | -2.8% | +6.4% | no |
| lumpy_acceptable | 20 | 45.0% | 107.0% | 109.2% | -2.1% | -2.9% | no |
| seasonal_discontinuous_insuficient | 18 | 55.6% | 102.6% | 103.7% | -1.1% | +2.8% | no |
| intermittent_acceptable | 12 | 41.7% | 57.6% | 109.5% | -90.1% | -33.2% | no |
| lumpy_recentRelease | 9 | 44.4% | 112.9% | 108.1% | +4.3% | -5.0% | si |
| smooth_insuficient | 6 | 50.0% | 23.4% | 16.2% | +30.7% | +4.4% | si |
| erratic_acceptable | 5 | 40.0% | 61.8% | 60.7% | +1.8% | -3.6% | si |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| seasonal_discontinuous_acceptable_acceptable | 246 | 48.4% | 91.4% | 90.6% | +0.8% | -1.9% | no |
| intermittent_insuficient_insuficient | 173 | 35.3% | 73.6% | 117.7% | -59.9% | -27.7% | no |
| lumpy_insuficient_insuficient | 140 | 39.3% | 92.8% | 147.0% | -58.3% | -17.7% | no |
| intermittent_recentRelease_recentRelease | 24 | 54.2% | 121.0% | 124.4% | -2.8% | +6.4% | no |
| lumpy_acceptable_acceptable | 20 | 45.0% | 107.0% | 109.2% | -2.1% | -2.9% | no |
| seasonal_discontinuous_insuficient_insuficient | 18 | 55.6% | 102.6% | 103.7% | -1.1% | +2.8% | no |
| intermittent_acceptable_acceptable | 12 | 41.7% | 57.6% | 109.5% | -90.1% | -33.2% | no |
| lumpy_recentRelease_recentRelease | 9 | 44.4% | 112.9% | 108.1% | +4.3% | -5.0% | si |
| smooth_insuficient_insuficient | 6 | 50.0% | 23.4% | 16.2% | +30.7% | +4.4% | si |
| erratic_acceptable_acceptable | 5 | 40.0% | 61.8% | 60.7% | +1.8% | -3.6% | si |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| seasonal_discontinuous_acceptable | 246 | 48.4% | 91.4% | 90.6% | +0.8% | -1.9% | no |
| intermittent_insuficient | 173 | 35.3% | 73.6% | 117.7% | -59.9% | -27.7% | no |
| lumpy_insuficient | 140 | 39.3% | 92.8% | 147.0% | -58.3% | -17.7% | no |
| intermittent_recentRelease | 24 | 54.2% | 121.0% | 124.4% | -2.8% | +6.4% | no |
| lumpy_acceptable | 20 | 45.0% | 107.0% | 109.2% | -2.1% | -2.9% | no |
| seasonal_discontinuous_insuficient | 18 | 55.6% | 102.6% | 103.7% | -1.1% | +2.8% | no |
| intermittent_acceptable | 12 | 41.7% | 57.6% | 109.5% | -90.1% | -33.2% | no |
| lumpy_recentRelease | 9 | 44.4% | 112.9% | 108.1% | +4.3% | -5.0% | si |
| smooth_insuficient | 6 | 50.0% | 23.4% | 16.2% | +30.7% | +4.4% | si |
| erratic_acceptable | 5 | 40.0% | 61.8% | 60.7% | +1.8% | -3.6% | si |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| seasonal discrete | 530 | 41.5% | 83.4% | 108.0% | -29.4% | -9.9% | no |
| syntetos-boylan | 121 | 50.4% | 131.7% | 135.6% | -3.0% | +1.6% | no |
| x11 seasonal | 13 | 53.8% | 37.5% | 27.4% | +26.9% | +11.7% | no |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 662 filas. `HAS_ML_EXCLUDED=1` (recuento real): 2.503 filas. La diferencia (1.841) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 3136 | +99.9% | 3162.0% | 2.7% | ML | syntetos-boylan | SeasonalNaive | seasonal_discontinuous_acceptable |
| 1547 | +99.9% | 81974.2% | 100.0% | ML | syntetos-boylan | MovingAverage3M | intermittent_recentRelease |
| 928 | +99.6% | 33772.1% | 122.2% | ML | seasonal discrete | MovingAverage3M | seasonal_discontinuous_acceptable |
| 2985 | +99.3% | 14053.8% | 100.0% | ML | syntetos-boylan | MovingAverage3M | intermittent_insuficient |
| 3060 | +99.2% | 26391.7% | 200.0% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 1721 | +99.1% | 10887.3% | 100.0% | ML | syntetos-boylan | nan | intermittent_obsolete |
| 2830 | +99.1% | 10760.0% | 100.0% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 3213 | +98.6% | 215.4% | 3.0% | ML | seasonal discrete | HistoricAverage | lumpy_insuficient |
| 759 | +96.5% | 94.7% | 3.3% | ML | seasonal discrete | SeasonalNaive | seasonal_discontinuous_acceptable |
| 1719 | +96.4% | 2760.0% | 100.0% | ML | syntetos-boylan | nan | intermittent_obsolete |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 4306 | -19254.0% | 1.2% | 222.7% | SCP | seasonal discrete | ADIDA | intermittent_insuficient |
| 837 | -9938.1% | 10.5% | 1052.8% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 3796 | -8708.1% | 333.3% | 29360.4% | SCP | syntetos-boylan | ADIDA | lumpy_insuficient |
| 836 | -6368.9% | 10.2% | 661.2% | SCP | seasonal discrete | MovingAverage12M | lumpy_insuficient |
| 309 | -4836.6% | 12.2% | 604.7% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 616 | -4481.7% | 66.1% | 3028.7% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 96 | -4089.7% | 38.2% | 1599.8% | SCP | seasonal discrete | MovingAverage12M | lumpy_insuficient |
| 319 | -3501.4% | 64.0% | 2305.4% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 711 | -3442.0% | 64.8% | 2294.3% | SCP | seasonal discrete | ADIDA | lumpy_insuficient |
| 1995 | -3281.9% | 7.8% | 263.0% | SCP | seasonal discrete | MovingAverage12M | seasonal_discontinuous_acceptable |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- 480 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **no mejora** el WAPE global ponderado frente a SCP (-22.7%). A nivel de serie individual, la mediana de mejora es -7.5% y ML gana en el 43.4% de las series comparables (19.3% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
