# Informe individual SCP vs ML — 10666_Grupo_Alacant

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10666 | Fichero: `TA_FOV_SCP_ML_10666_Grupo_Alacant.csv`
**Batch/Run:** ID_BATCH=[63] | ID_RUN_STAGING=[59] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **1.639 series candidatas**, **788 (48.1%)** son comparables en el semestre completo (6M). WAPE SCP=38.4%, WAPE ML=33.7%, mejora relativa ponderada=+12.4%, reduccion absoluta de error=3.144.034, series comparables=788, historico total=65.899.508.

Frecuencia de victoria en 6M: ML gana 407 (51.6%), SCP gana 369 (46.8%), empate 12 (1.5%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **1.639**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 788 | 48.1% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 498 | 30.4% |
| NOT_COMPARABLE_ML_EXCLUDED | 198 | 12.1% |
| NOT_COMPARABLE_NO_HISTORY | 125 | 7.6% |
| NOT_COMPARABLE_MISSING_SCP | 25 | 1.5% |
| NOT_COMPARABLE_MISSING_ML | 5 | 0.3% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **695** (42.4% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 373 |
| ShortSeries | 181 |
| NewRelease | 141 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 1.639 | 649 | 39.6% |
| M2 | 1.639 | 684 | 41.7% |
| M3 | 1.639 | 636 | 38.8% |
| M4 | 1.639 | 662 | 40.4% |
| M5 | 1.639 | 534 | 32.6% |
| M6 | 1.639 | 489 | 29.8% |
| RECENT_3M | 1.639 | 733 | 44.7% |
| OLDER_3M | 1.639 | 731 | 44.6% |
| 6M | 1.639 | 788 | 48.1% |

---

## 3. Semestre completo (6M)

WAPE SCP=38.4%, WAPE ML=33.7%, mejora relativa ponderada=+12.4%, reduccion absoluta de error=3.144.034, series comparables=788, historico total=65.899.508.

Frecuencia de victoria: ML gana 407 (51.6%), SCP gana 369 (46.8%), empate 12 (1.5%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=31.4%, WAPE ML=25.7%, mejora relativa ponderada=+18.0%, reduccion absoluta de error=2.875.439, series comparables=733, historico total=50.878.053.

Frecuencia de victoria: ML gana 375 (51.2%), SCP gana 330 (45.0%), empate 28 (3.8%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=52.7%, WAPE ML=54.3%, mejora relativa ponderada=-3.0%, reduccion absoluta de error=-240.991, series comparables=731, historico total=15.021.455.

Frecuencia de victoria: ML gana 308 (42.1%), SCP gana 317 (43.4%), empate 106 (14.5%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +18.0%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): -3.0%. La mejora cambia de signo entre trimestres.

% victorias ML: 51.2% (primer trimestre) vs 42.1% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 649 | 23.1% | 20.3% | +12.1% | 51.8% | 44.1% | 4.2% |
| M2 | 684 | 30.2% | 23.9% | +20.9% | 44.6% | 49.0% | 6.4% |
| M3 | 636 | 36.1% | 28.7% | +20.3% | 39.8% | 55.5% | 4.7% |
| M4 | 662 | 41.4% | 49.4% | -19.3% | 29.0% | 57.7% | 13.3% |
| M5 | 534 | 44.1% | 37.6% | +14.7% | 50.9% | 37.8% | 11.2% |
| M6 | 489 | 48.4% | 46.9% | +3.1% | 54.4% | 34.8% | 10.8% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +12.1% vs +3.1%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 407 (51.6%), SCP gana 369 (46.8%), empate 12 (1.5%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **3.144.034** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| SeasonalNaive | 432 | 46.8% | 31.9% | 24.1% | +24.5% | -0.4% | no |
| MovingAverage3M | 166 | 53.0% | 73.4% | 79.8% | -8.6% | +2.7% | no |
| AutoTheta | 40 | 77.5% | 50.3% | 55.3% | -10.0% | +13.6% | no |
| HistoricAverage | 40 | 52.5% | 78.3% | 90.0% | -15.1% | +1.7% | no |
| AutoETS | 39 | 53.8% | 22.8% | 18.2% | +20.2% | +8.9% | no |
| MovingAverage12M | 19 | 52.6% | 101.9% | 91.6% | +10.1% | +1.0% | no |
| ADIDA | 17 | 76.5% | 133.1% | 108.4% | +18.6% | +12.1% | no |
| AutoARIMA | 16 | 50.0% | 60.6% | 38.8% | +36.0% | -6.7% | no |
| CrostonSBA | 8 | 62.5% | 139.1% | 115.9% | +16.7% | +12.7% | si |
| TSB | 6 | 66.7% | 99.7% | 112.7% | -13.1% | +18.7% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 400 | 48.5% | 26.8% | 21.9% | +18.3% | -0.6% | no |
| seasonal discrete | 260 | 54.2% | 47.1% | 43.3% | +8.1% | +2.4% | no |
| syntetos-boylan | 94 | 57.4% | 136.2% | 119.2% | +12.5% | +4.3% | no |
| copy parent behaviour | 17 | 52.9% | 144.9% | 136.3% | +5.9% | +2.0% | no |
| preserve current forecast | 13 | 38.5% | 387.6% | 434.0% | -12.0% | -13.9% | no |
| copy last year | 4 | 100.0% | 63.7% | 57.7% | +9.4% | +14.9% | si |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| erratic_insuficient | 271 | 51.3% | 27.5% | 23.7% | +13.9% | +1.1% | no |
| intermittent_insuficient | 134 | 52.2% | 75.1% | 83.4% | -11.0% | +2.4% | no |
| smooth_insuficient | 116 | 45.7% | 21.1% | 20.7% | +2.1% | -0.9% | no |
| lumpy_insuficient | 89 | 65.2% | 46.0% | 29.1% | +36.7% | +16.4% | no |
| intermittent_recentRelease | 52 | 38.5% | 86.8% | 88.3% | -1.7% | -10.6% | no |
| erratic_acceptable | 42 | 45.2% | 21.0% | 10.5% | +50.1% | -5.2% | no |
| seasonal_discontinuous_acceptable | 20 | 55.0% | 14.7% | 23.9% | -61.9% | +1.6% | no |
| smooth_acceptable | 17 | 70.6% | 71.8% | 55.1% | +23.3% | +9.1% | no |
| intermittent_acceptable | 14 | 42.9% | 100.6% | 117.6% | -16.9% | -9.0% | no |
| lumpy_recentRelease | 13 | 61.5% | 126.1% | 127.0% | -0.8% | +5.4% | no |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| erratic_insuficient_insuficient | 271 | 51.3% | 27.5% | 23.7% | +13.9% | +1.1% | no |
| intermittent_insuficient_insuficient | 134 | 52.2% | 75.1% | 83.4% | -11.0% | +2.4% | no |
| smooth_insuficient_insuficient | 116 | 45.7% | 21.1% | 20.7% | +2.1% | -0.9% | no |
| lumpy_insuficient_insuficient | 89 | 65.2% | 46.0% | 29.1% | +36.7% | +16.4% | no |
| intermittent_recentRelease_recentRelease | 52 | 38.5% | 86.8% | 88.3% | -1.7% | -10.6% | no |
| erratic_acceptable_acceptable | 42 | 45.2% | 21.0% | 10.5% | +50.1% | -5.2% | no |
| seasonal_discontinuous_acceptable_acceptable | 20 | 55.0% | 14.7% | 23.9% | -61.9% | +1.6% | no |
| smooth_acceptable_acceptable | 17 | 70.6% | 71.8% | 55.1% | +23.3% | +9.1% | no |
| intermittent_acceptable_acceptable | 14 | 42.9% | 100.6% | 117.6% | -16.9% | -9.0% | no |
| lumpy_recentRelease_recentRelease | 13 | 61.5% | 126.1% | 127.0% | -0.8% | +5.4% | no |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| erratic_insuficient | 271 | 51.3% | 27.5% | 23.7% | +13.9% | +1.1% | no |
| intermittent_insuficient | 134 | 52.2% | 75.1% | 83.4% | -11.0% | +2.4% | no |
| smooth_insuficient | 116 | 45.7% | 21.1% | 20.7% | +2.1% | -0.9% | no |
| lumpy_insuficient | 89 | 65.2% | 46.0% | 29.1% | +36.7% | +16.4% | no |
| intermittent_recentRelease | 52 | 38.5% | 86.8% | 88.3% | -1.7% | -10.6% | no |
| erratic_acceptable | 42 | 45.2% | 21.0% | 10.5% | +50.1% | -5.2% | no |
| seasonal_discontinuous_acceptable | 20 | 55.0% | 14.7% | 23.9% | -61.9% | +1.6% | no |
| smooth_acceptable | 17 | 70.6% | 71.8% | 55.1% | +23.3% | +9.1% | no |
| intermittent_acceptable | 14 | 42.9% | 100.6% | 117.6% | -16.9% | -9.0% | no |
| lumpy_recentRelease | 13 | 61.5% | 126.1% | 127.0% | -0.8% | +5.4% | no |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 400 | 48.5% | 26.8% | 21.9% | +18.3% | -0.6% | no |
| seasonal discrete | 260 | 54.2% | 47.1% | 43.3% | +8.1% | +2.4% | no |
| syntetos-boylan | 94 | 57.4% | 136.2% | 119.2% | +12.5% | +4.3% | no |
| copy parent behaviour | 17 | 52.9% | 144.9% | 136.3% | +5.9% | +2.0% | no |
| preserve current forecast | 13 | 38.5% | 387.6% | 434.0% | -12.0% | -13.9% | no |
| copy last year | 4 | 100.0% | 63.7% | 57.7% | +9.4% | +14.9% | si |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 198 filas. `HAS_ML_EXCLUDED=1` (recuento real): 695 filas. La diferencia (497) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 3076 | +100.0% | 1159125.1% | 200.0% | ML | syntetos-boylan | MovingAverage3M | lumpy_recentRelease |
| 3074 | +99.9% | 251925.0% | 200.0% | ML | syntetos-boylan | MovingAverage3M | lumpy_recentRelease |
| 4530 | +94.0% | 1956.7% | 118.3% | ML | seasonal discrete | AutoETS | erratic_acceptable |
| 2800 | +92.1% | 2532.2% | 200.0% | ML | syntetos-boylan | MovingAverage3M | lumpy_insuficient |
| 4568 | +90.5% | 2100.0% | 200.0% | ML | syntetos-boylan | MovingAverage3M | intermittent_acceptable |
| 2798 | +87.8% | 827.3% | 100.9% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 4658 | +87.3% | 827.9% | 104.9% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 4352 | +83.5% | 523.0% | 86.2% | ML | seasonal discrete | ADIDA | intermittent_insuficient |
| 4589 | +81.7% | 730.2% | 133.3% | ML | x11 seasonal | MovingAverage3M | erratic_insuficient |
| 4283 | +80.7% | 516.8% | 100.0% | ML | seasonal discrete | MovingAverage3M | intermittent_insuficient |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 4323 | -342.1% | 30.3% | 134.0% | SCP | seasonal discrete | MovingAverage3M | intermittent_recentRelease |
| 3503 | -270.7% | 7.9% | 29.4% | SCP | x11 seasonal | SeasonalNaive | smooth_insuficient |
| 2763 | -246.8% | 30.8% | 106.9% | SCP | x11 seasonal | SeasonalNaive | erratic_acceptable |
| 2976 | -227.8% | 17.0% | 55.7% | SCP | x11 seasonal | AutoETS | erratic_acceptable |
| 3988 | -207.8% | 50.0% | 153.9% | SCP | seasonal discrete | MovingAverage3M | intermittent_recentRelease |
| 4471 | -201.3% | 35.6% | 107.4% | SCP | seasonal discrete | MovingAverage3M | lumpy_acceptable |
| 4335 | -200.7% | 38.6% | 116.0% | SCP | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 3385 | -199.9% | 29.1% | 87.1% | SCP | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 3980 | -193.1% | 7.1% | 20.8% | SCP | seasonal discrete | AutoARIMA | seasonal_discontinuous_acceptable |
| 3401 | -187.0% | 27.7% | 79.5% | SCP | seasonal discrete | MovingAverage3M | intermittent_insuficient |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Se han detectado posibles artefactos de codificacion en columnas VALUE_LEVEL_*.
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- Hay series con historico mensual negativo (posible ajuste/devolucion) que siguen siendo comparables en 6M.
- 372 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+12.4%). A nivel de serie individual, la mediana de mejora es +1.5% y ML gana en el 51.6% de las series comparables (48.1% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
