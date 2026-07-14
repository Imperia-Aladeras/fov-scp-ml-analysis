# Informe individual SCP vs ML — 10204_SKLUM

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10204 | Fichero: `TA_FOV_SCP_ML_10204_SKLUM.csv`
**Batch/Run:** ID_BATCH=[63] | ID_RUN_STAGING=[63] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **10.210 series candidatas**, **5.027 (49.2%)** son comparables en el semestre completo (6M). WAPE SCP=35.7%, WAPE ML=35.5%, mejora relativa ponderada=+0.5%, reduccion absoluta de error=7.588, series comparables=5.027, historico total=4.711.623.

Frecuencia de victoria en 6M: ML gana 2.742 (54.5%), SCP gana 2.244 (44.6%), empate 41 (0.8%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **10.210**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 5.027 | 49.2% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 2.705 | 26.5% |
| NOT_COMPARABLE_ML_EXCLUDED | 1.998 | 19.6% |
| NOT_COMPARABLE_NO_HISTORY | 415 | 4.1% |
| NOT_COMPARABLE_MISSING_SCP | 65 | 0.6% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **4.475** (43.8% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| ShortSeries | 2.727 |
| MissingHistory | 1.724 |
| NewRelease | 24 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 10.210 | 4.897 | 48.0% |
| M2 | 10.210 | 4.909 | 48.1% |
| M3 | 10.210 | 4.901 | 48.0% |
| M4 | 10.210 | 4.932 | 48.3% |
| M5 | 10.210 | 4.941 | 48.4% |
| M6 | 10.210 | 4.953 | 48.5% |
| RECENT_3M | 10.210 | 4.991 | 48.9% |
| OLDER_3M | 10.210 | 5.007 | 49.0% |
| 6M | 10.210 | 5.027 | 49.2% |

---

## 3. Semestre completo (6M)

WAPE SCP=35.7%, WAPE ML=35.5%, mejora relativa ponderada=+0.5%, reduccion absoluta de error=7.588, series comparables=5.027, historico total=4.711.623.

Frecuencia de victoria: ML gana 2.742 (54.5%), SCP gana 2.244 (44.6%), empate 41 (0.8%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=35.6%, WAPE ML=35.5%, mejora relativa ponderada=+0.4%, reduccion absoluta de error=3.891, series comparables=4.991, historico total=2.431.362.

Frecuencia de victoria: ML gana 2.637 (52.8%), SCP gana 2.275 (45.6%), empate 79 (1.6%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=35.4%, WAPE ML=35.4%, mejora relativa ponderada=+0.2%, reduccion absoluta de error=1.754, series comparables=5.007, historico total=2.280.262.

Frecuencia de victoria: ML gana 2.608 (52.1%), SCP gana 2.332 (46.6%), empate 67 (1.3%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +0.4%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): +0.2%. La mejora mantiene el mismo signo en ambos trimestres.

% victorias ML: 52.8% (primer trimestre) vs 52.1% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 4.897 | 37.1% | 38.3% | -3.2% | 47.4% | 49.6% | 2.9% |
| M2 | 4.909 | 34.8% | 35.0% | -0.5% | 50.9% | 46.4% | 2.7% |
| M3 | 4.901 | 33.7% | 31.9% | +5.2% | 51.0% | 45.7% | 3.3% |
| M4 | 4.932 | 35.3% | 37.3% | -5.6% | 48.9% | 48.6% | 2.5% |
| M5 | 4.941 | 35.9% | 36.9% | -2.7% | 50.2% | 47.0% | 2.8% |
| M6 | 4.953 | 34.3% | 30.8% | +10.1% | 49.6% | 47.8% | 2.6% |

M1 (mas reciente) vs M6 (mas antiguo): mejora -3.2% vs +10.1%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 2.742 (54.5%), SCP gana 2.244 (44.6%), empate 41 (0.8%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **7.588** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| MovingAverage3M | 1.063 | 52.3% | 34.8% | 34.6% | +0.5% | +1.9% | no |
| AutoTheta | 1.013 | 64.5% | 36.2% | 35.0% | +3.1% | +12.1% | no |
| HistoricAverage | 855 | 61.2% | 43.2% | 39.9% | +7.6% | +9.1% | no |
| SeasonalNaive | 747 | 40.3% | 34.4% | 36.6% | -6.6% | -8.5% | no |
| AutoARIMA | 511 | 47.9% | 31.4% | 33.4% | -6.1% | -1.4% | no |
| AutoETS | 468 | 50.0% | 35.7% | 35.4% | +0.8% | +0.2% | no |
| MovingAverage12M | 349 | 62.5% | 37.1% | 33.1% | +10.8% | +10.1% | no |
| TSB | 12 | 66.7% | 97.5% | 95.5% | +2.1% | +20.5% | no |
| CrostonSBA | 4 | 25.0% | 86.4% | 79.2% | +8.3% | -15.1% | si |
| ADIDA | 3 | 66.7% | 83.3% | 71.9% | +13.7% | +12.5% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 4.798 | 54.8% | 35.2% | 35.1% | +0.3% | +4.4% | no |
| seasonal discrete | 215 | 50.2% | 95.6% | 86.5% | +9.5% | +0.4% | no |
| preserve current forecast | 7 | 28.6% | 62.2% | 69.4% | -11.6% | -11.1% | si |
| syntetos-boylan | 7 | 57.1% | 112.1% | 100.0% | +10.8% | +14.2% | si |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient | 1.884 | 63.3% | 34.9% | 31.8% | +8.9% | +11.4% | no |
| smooth_acceptable | 1.604 | 50.9% | 32.6% | 33.1% | -1.6% | +0.7% | no |
| smooth_recentRelease | 524 | 47.9% | 29.4% | 30.6% | -3.8% | -1.5% | no |
| erratic_insuficient | 438 | 49.3% | 48.6% | 51.1% | -5.2% | +0.0% | no |
| erratic_acceptable | 411 | 49.6% | 41.8% | 45.0% | -7.8% | +0.0% | no |
| erratic_recentRelease | 62 | 30.6% | 62.3% | 72.9% | -16.9% | -10.8% | no |
| lumpy_insuficient | 37 | 35.1% | 92.0% | 152.6% | -65.9% | -22.0% | no |
| seasonal_discontinuous_acceptable | 18 | 16.7% | 88.1% | 165.1% | -87.4% | -45.0% | no |
| intermittent_insuficient | 17 | 70.6% | 105.5% | 82.4% | +21.9% | +16.7% | no |
| lumpy_acceptable | 12 | 50.0% | 157.3% | 306.2% | -94.7% | -2.3% | no |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient_insuficient | 1.884 | 63.3% | 34.9% | 31.8% | +8.9% | +11.4% | no |
| smooth_acceptable_acceptable | 1.604 | 50.9% | 32.6% | 33.1% | -1.6% | +0.7% | no |
| smooth_recentRelease_recentRelease | 524 | 47.9% | 29.4% | 30.6% | -3.8% | -1.5% | no |
| erratic_insuficient_insuficient | 438 | 49.3% | 48.6% | 51.1% | -5.2% | +0.0% | no |
| erratic_acceptable_acceptable | 411 | 49.6% | 41.8% | 45.0% | -7.8% | +0.0% | no |
| erratic_recentRelease_recentRelease | 62 | 30.6% | 62.3% | 72.9% | -16.9% | -10.8% | no |
| lumpy_insuficient_insuficient | 37 | 35.1% | 92.0% | 152.6% | -65.9% | -22.0% | no |
| seasonal_discontinuous_acceptable_acceptable | 18 | 16.7% | 88.1% | 165.1% | -87.4% | -45.0% | no |
| intermittent_insuficient_insuficient | 17 | 70.6% | 105.5% | 82.4% | +21.9% | +16.7% | no |
| lumpy_acceptable_acceptable | 12 | 50.0% | 157.3% | 306.2% | -94.7% | -2.3% | no |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient | 1.884 | 63.3% | 34.9% | 31.8% | +8.9% | +11.4% | no |
| smooth_acceptable | 1.604 | 50.9% | 32.6% | 33.1% | -1.6% | +0.7% | no |
| smooth_recentRelease | 524 | 47.9% | 29.4% | 30.6% | -3.8% | -1.5% | no |
| erratic_insuficient | 438 | 49.3% | 48.6% | 51.1% | -5.2% | +0.0% | no |
| erratic_acceptable | 411 | 49.6% | 41.8% | 45.0% | -7.8% | +0.0% | no |
| erratic_recentRelease | 62 | 30.6% | 62.3% | 72.9% | -16.9% | -10.8% | no |
| lumpy_insuficient | 37 | 35.1% | 92.0% | 152.6% | -65.9% | -22.0% | no |
| seasonal_discontinuous_acceptable | 18 | 16.7% | 88.1% | 165.1% | -87.4% | -45.0% | no |
| intermittent_insuficient | 17 | 70.6% | 105.5% | 82.4% | +21.9% | +16.7% | no |
| lumpy_acceptable | 12 | 50.0% | 157.3% | 306.2% | -94.7% | -2.3% | no |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 4.798 | 54.8% | 35.2% | 35.1% | +0.3% | +4.4% | no |
| seasonal discrete | 215 | 50.2% | 95.6% | 86.5% | +9.5% | +0.4% | no |
| preserve current forecast | 7 | 28.6% | 62.2% | 69.4% | -11.6% | -11.1% | si |
| syntetos-boylan | 7 | 57.1% | 112.1% | 100.0% | +10.8% | +14.2% | si |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 1.998 filas. `HAS_ML_EXCLUDED=1` (recuento real): 4.475 filas. La diferencia (2.477) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 143075 | +99.1% | 23000.0% | 200.0% | ML | seasonal discrete | AutoTheta | smooth_acceptable |
| 142950 | +98.3% | 5800.0% | 100.0% | ML | seasonal discrete | AutoTheta | erratic_insuficient |
| 1029 | +97.5% | 4000.0% | 100.0% | ML | seasonal discrete | MovingAverage3M | smooth_acceptable |
| 8800 | +95.6% | 664.7% | 29.4% | ML | x11 seasonal | AutoTheta | erratic_insuficient |
| 46 | +95.4% | 2183.3% | 100.0% | ML | seasonal discrete | AutoTheta | smooth_acceptable |
| 10004 | +90.7% | 1075.0% | 100.0% | ML | seasonal discrete | MovingAverage3M | intermittent_insuficient |
| 1269 | +86.9% | 6866.7% | 900.0% | ML | seasonal discrete | MovingAverage3M | lumpy_acceptable |
| 8676 | +86.2% | 3143.2% | 433.3% | ML | x11 seasonal | AutoTheta | erratic_insuficient |
| 9230 | +85.5% | 443.3% | 64.2% | ML | x11 seasonal | MovingAverage3M | erratic_insuficient |
| 4028 | +85.4% | 71.1% | 10.4% | ML | x11 seasonal | HistoricAverage | smooth_recentRelease |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 233 | -8450.0% | 33.3% | 2850.0% | SCP | x11 seasonal | SeasonalNaive | erratic_insuficient |
| 9344 | -4766.7% | 46.3% | 2253.8% | SCP | x11 seasonal | AutoTheta | erratic_acceptable |
| 635 | -4533.3% | 60.0% | 2780.0% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 310 | -3500.0% | 50.0% | 1800.0% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 185 | -2816.7% | 57.1% | 1666.7% | SCP | seasonal discrete | MovingAverage12M | erratic_insuficient |
| 158 | -2666.7% | 150.0% | 4150.0% | SCP | seasonal discrete | MovingAverage12M | lumpy_insuficient |
| 673 | -2455.6% | 75.0% | 1916.7% | SCP | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 2754 | -2390.4% | 26.4% | 656.8% | SCP | x11 seasonal | AutoETS | smooth_acceptable |
| 561 | -2157.1% | 100.0% | 2257.1% | SCP | seasonal discrete | MovingAverage12M | lumpy_acceptable |
| 331 | -1966.7% | 112.5% | 2325.0% | SCP | seasonal discrete | MovingAverage12M | lumpy_acceptable |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Se han detectado posibles artefactos de codificacion en columnas VALUE_LEVEL_*.
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- 1153 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+0.5%). A nivel de serie individual, la mediana de mejora es +4.2% y ML gana en el 54.5% de las series comparables (49.2% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
