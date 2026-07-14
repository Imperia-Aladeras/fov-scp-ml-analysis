# Informe individual SCP vs ML — 10629_Platanomelon

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10629 | Fichero: `TA_FOV_SCP_ML_10629_Platanomelon.csv`
**Batch/Run:** ID_BATCH=[66] | ID_RUN_STAGING=[65] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **1.117 series candidatas**, **619 (55.4%)** son comparables en el semestre completo (6M). WAPE SCP=52.7%, WAPE ML=50.9%, mejora relativa ponderada=+3.5%, reduccion absoluta de error=6.239, series comparables=619, historico total=342.888.

Frecuencia de victoria en 6M: ML gana 310 (50.1%), SCP gana 273 (44.1%), empate 36 (5.8%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **1.117**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 619 | 55.4% |
| NOT_COMPARABLE_ML_EXCLUDED | 192 | 17.2% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 191 | 17.1% |
| NOT_COMPARABLE_NO_HISTORY | 70 | 6.3% |
| NOT_COMPARABLE_MISSING_SCP | 45 | 4.0% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **380** (34.0% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| ShortSeries | 243 |
| MissingHistory | 137 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 1.117 | 478 | 42.8% |
| M2 | 1.117 | 471 | 42.2% |
| M3 | 1.117 | 487 | 43.6% |
| M4 | 1.117 | 501 | 44.9% |
| M5 | 1.117 | 507 | 45.4% |
| M6 | 1.117 | 545 | 48.8% |
| RECENT_3M | 1.117 | 554 | 49.6% |
| OLDER_3M | 1.117 | 596 | 53.4% |
| 6M | 1.117 | 619 | 55.4% |

---

## 3. Semestre completo (6M)

WAPE SCP=52.7%, WAPE ML=50.9%, mejora relativa ponderada=+3.5%, reduccion absoluta de error=6.239, series comparables=619, historico total=342.888.

Frecuencia de victoria: ML gana 310 (50.1%), SCP gana 273 (44.1%), empate 36 (5.8%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=51.4%, WAPE ML=49.7%, mejora relativa ponderada=+3.3%, reduccion absoluta de error=2.667, series comparables=554, historico total=159.026.

Frecuencia de victoria: ML gana 285 (51.4%), SCP gana 224 (40.4%), empate 45 (8.1%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=52.2%, WAPE ML=50.3%, mejora relativa ponderada=+3.5%, reduccion absoluta de error=3.359, series comparables=596, historico total=183.862.

Frecuencia de victoria: ML gana 270 (45.3%), SCP gana 257 (43.1%), empate 69 (11.6%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +3.3%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): +3.5%. La mejora mantiene el mismo signo en ambos trimestres.

% victorias ML: 51.4% (primer trimestre) vs 45.3% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 478 | 52.5% | 50.7% | +3.4% | 47.9% | 40.4% | 11.7% |
| M2 | 471 | 46.8% | 42.0% | +10.1% | 52.4% | 36.5% | 11.0% |
| M3 | 487 | 46.0% | 49.4% | -7.2% | 42.5% | 45.0% | 12.5% |
| M4 | 501 | 62.4% | 59.4% | +4.7% | 44.7% | 41.7% | 13.6% |
| M5 | 507 | 48.1% | 47.2% | +1.8% | 45.2% | 38.1% | 16.8% |
| M6 | 545 | 44.5% | 43.0% | +3.4% | 45.7% | 40.2% | 14.1% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +3.4% vs +3.4%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 310 (50.1%), SCP gana 273 (44.1%), empate 36 (5.8%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **6.239** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| MovingAverage3M | 118 | 54.2% | 48.8% | 50.2% | -2.9% | +8.3% | no |
| SeasonalNaive | 86 | 36.0% | 52.7% | 51.4% | +2.5% | -8.7% | no |
| HistoricAverage | 85 | 51.8% | 56.5% | 47.5% | +15.8% | +0.7% | no |
| AutoTheta | 74 | 51.4% | 48.1% | 45.4% | +5.6% | +2.3% | no |
| AutoARIMA | 71 | 57.7% | 54.2% | 50.3% | +7.2% | +3.1% | no |
| AutoETS | 59 | 50.8% | 49.3% | 50.0% | -1.6% | +3.4% | no |
| MovingAverage12M | 53 | 47.2% | 54.0% | 54.5% | -0.8% | +0.0% | no |
| TSB | 49 | 53.1% | 105.9% | 110.3% | -4.1% | +10.0% | no |
| ADIDA | 10 | 60.0% | 140.8% | 96.9% | +31.2% | +9.7% | no |
| CrostonClassic | 6 | 16.7% | 83.3% | 76.9% | +7.7% | -2.9% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 295 | 52.5% | 50.4% | 49.8% | +1.3% | +2.0% | no |
| seasonal discrete | 203 | 49.8% | 96.3% | 87.3% | +9.3% | +0.3% | no |
| x11 lineal | 70 | 44.3% | 48.6% | 43.5% | +10.4% | -3.4% | no |
| syntetos-boylan | 51 | 45.1% | 151.8% | 133.2% | +12.3% | +0.0% | no |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 238 | 51.7% | 48.1% | 46.6% | +3.3% | +1.6% | no |
| smooth_insuficient | 93 | 45.2% | 43.7% | 41.5% | +4.9% | -4.5% | no |
| intermittent_insuficient | 72 | 40.3% | 103.1% | 126.0% | -22.2% | +0.0% | no |
| erratic_acceptable | 71 | 54.9% | 62.7% | 61.9% | +1.2% | +5.1% | no |
| intermittent_acceptable | 40 | 52.5% | 104.5% | 98.8% | +5.4% | +5.6% | no |
| lumpy_acceptable | 31 | 77.4% | 117.1% | 98.5% | +15.9% | +27.8% | no |
| erratic_insuficient | 23 | 43.5% | 69.1% | 72.8% | -5.3% | -10.7% | no |
| lumpy_insuficient | 16 | 56.2% | 130.2% | 108.4% | +16.8% | +26.7% | no |
| intermittent_recentRelease | 14 | 35.7% | 84.3% | 88.1% | -4.5% | +0.0% | no |
| seasonal_discontinuous_acceptable | 10 | 40.0% | 123.5% | 106.5% | +13.7% | -18.3% | no |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable_acceptable | 238 | 51.7% | 48.1% | 46.6% | +3.3% | +1.6% | no |
| smooth_insuficient_insuficient | 93 | 45.2% | 43.7% | 41.5% | +4.9% | -4.5% | no |
| intermittent_insuficient_insuficient | 72 | 40.3% | 103.1% | 126.0% | -22.2% | +0.0% | no |
| erratic_acceptable_acceptable | 71 | 54.9% | 62.7% | 61.9% | +1.2% | +5.1% | no |
| intermittent_acceptable_acceptable | 40 | 52.5% | 104.5% | 98.8% | +5.4% | +5.6% | no |
| lumpy_acceptable_acceptable | 31 | 77.4% | 117.1% | 98.5% | +15.9% | +27.8% | no |
| erratic_insuficient_insuficient | 23 | 43.5% | 69.1% | 72.8% | -5.3% | -10.7% | no |
| lumpy_insuficient_insuficient | 16 | 56.2% | 130.2% | 108.4% | +16.8% | +26.7% | no |
| intermittent_recentRelease_recentRelease | 14 | 35.7% | 84.3% | 88.1% | -4.5% | +0.0% | no |
| seasonal_discontinuous_acceptable_acceptable | 10 | 40.0% | 123.5% | 106.5% | +13.7% | -18.3% | no |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 238 | 51.7% | 48.1% | 46.6% | +3.3% | +1.6% | no |
| smooth_insuficient | 93 | 45.2% | 43.7% | 41.5% | +4.9% | -4.5% | no |
| intermittent_insuficient | 72 | 40.3% | 103.1% | 126.0% | -22.2% | +0.0% | no |
| erratic_acceptable | 71 | 54.9% | 62.7% | 61.9% | +1.2% | +5.1% | no |
| intermittent_acceptable | 40 | 52.5% | 104.5% | 98.8% | +5.4% | +5.6% | no |
| lumpy_acceptable | 31 | 77.4% | 117.1% | 98.5% | +15.9% | +27.8% | no |
| erratic_insuficient | 23 | 43.5% | 69.1% | 72.8% | -5.3% | -10.7% | no |
| lumpy_insuficient | 16 | 56.2% | 130.2% | 108.4% | +16.8% | +26.7% | no |
| intermittent_recentRelease | 14 | 35.7% | 84.3% | 88.1% | -4.5% | +0.0% | no |
| seasonal_discontinuous_acceptable | 10 | 40.0% | 123.5% | 106.5% | +13.7% | -18.3% | no |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 295 | 52.5% | 50.4% | 49.8% | +1.3% | +2.0% | no |
| seasonal discrete | 203 | 49.8% | 96.3% | 87.3% | +9.3% | +0.3% | no |
| x11 lineal | 70 | 44.3% | 48.6% | 43.5% | +10.4% | -3.4% | no |
| syntetos-boylan | 51 | 45.1% | 151.8% | 133.2% | +12.3% | +0.0% | no |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 192 filas. `HAS_ML_EXCLUDED=1` (recuento real): 380 filas. La diferencia (188) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 411 | +87.5% | 1600.0% | 200.0% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 3264 | +83.3% | 600.0% | 100.0% | ML | seasonal discrete | MovingAverage3M | smooth_insuficient |
| 629 | +83.0% | 588.9% | 100.0% | ML | seasonal discrete | MovingAverage3M | intermittent_acceptable |
| 1687 | +82.4% | 566.7% | 100.0% | ML | syntetos-boylan | MovingAverage3M | lumpy_acceptable |
| 1820 | +80.6% | 775.0% | 150.0% | ML | seasonal discrete | MovingAverage3M | lumpy_acceptable |
| 1337 | +80.3% | 105.8% | 20.9% | ML | seasonal discrete | AutoETS | smooth_acceptable |
| 2019 | +80.3% | 152.5% | 30.1% | ML | x11 seasonal | AutoTheta | smooth_acceptable |
| 1989 | +80.0% | 250.0% | 50.0% | ML | syntetos-boylan | SeasonalNaive | intermittent_insuficient |
| 442 | +78.8% | 1100.0% | 233.3% | ML | seasonal discrete | AutoARIMA | erratic_acceptable |
| 1849 | +73.7% | 475.0% | 125.0% | ML | seasonal discrete | ADIDA | intermittent_insuficient |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 2115 | -1000.0% | 100.0% | 1100.0% | SCP | seasonal discrete | HistoricAverage | intermittent_insuficient |
| 1183 | -485.0% | 1000.0% | 5850.0% | SCP | seasonal discrete | TSB | intermittent_acceptable |
| 70 | -418.5% | 900.0% | 4666.7% | SCP | seasonal discrete | SeasonalNaive | seasonal_discontinuous_acceptable |
| 2504 | -300.0% | 33.3% | 133.3% | SCP | syntetos-boylan | MovingAverage3M | intermittent_insuficient |
| 3483 | -251.7% | 13.7% | 48.1% | SCP | x11 seasonal | AutoARIMA | erratic_acceptable |
| 989 | -250.0% | 40.0% | 140.0% | SCP | syntetos-boylan | TSB | intermittent_insuficient |
| 354 | -200.0% | 66.7% | 200.0% | SCP | syntetos-boylan | TSB | lumpy_acceptable |
| 2727 | -200.0% | 200.0% | 600.0% | SCP | seasonal discrete | HistoricAverage | intermittent_acceptable |
| 2816 | -152.4% | 16.3% | 41.1% | SCP | x11 lineal | MovingAverage3M | smooth_insuficient |
| 2670 | -148.5% | 106.5% | 264.5% | SCP | seasonal discrete | MovingAverage12M | lumpy_acceptable |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- 359 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+3.5%). A nivel de serie individual, la mediana de mejora es +0.5% y ML gana en el 50.1% de las series comparables (55.4% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
