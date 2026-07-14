# Informe individual SCP vs ML — 10664_DV_Flora

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10664 | Fichero: `TA_FOV_SCP_ML_10664_DV_Flora.csv`
**Batch/Run:** ID_BATCH=[63] | ID_RUN_STAGING=[60] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **365 series candidatas**, **221 (60.5%)** son comparables en el semestre completo (6M). WAPE SCP=18.0%, WAPE ML=17.2%, mejora relativa ponderada=+4.2%, reduccion absoluta de error=89.393, series comparables=221, historico total=11.789.430.

Frecuencia de victoria en 6M: ML gana 105 (47.5%), SCP gana 116 (52.5%), empate 0 (0.0%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **365**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 221 | 60.5% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 95 | 26.0% |
| NOT_COMPARABLE_MISSING_SCP | 20 | 5.5% |
| NOT_COMPARABLE_NO_HISTORY | 20 | 5.5% |
| NOT_COMPARABLE_ML_EXCLUDED | 9 | 2.5% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **101** (27.7% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 63 |
| ShortSeries | 38 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 365 | 172 | 47.1% |
| M2 | 365 | 195 | 53.4% |
| M3 | 365 | 193 | 52.9% |
| M4 | 365 | 191 | 52.3% |
| M5 | 365 | 182 | 49.9% |
| M6 | 365 | 163 | 44.7% |
| RECENT_3M | 365 | 208 | 57.0% |
| OLDER_3M | 365 | 210 | 57.5% |
| 6M | 365 | 221 | 60.5% |

---

## 3. Semestre completo (6M)

WAPE SCP=18.0%, WAPE ML=17.2%, mejora relativa ponderada=+4.2%, reduccion absoluta de error=89.393, series comparables=221, historico total=11.789.430.

Frecuencia de victoria: ML gana 105 (47.5%), SCP gana 116 (52.5%), empate 0 (0.0%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=19.4%, WAPE ML=17.3%, mejora relativa ponderada=+10.8%, reduccion absoluta de error=127.563, series comparables=208, historico total=6.103.880.

Frecuencia de victoria: ML gana 104 (50.0%), SCP gana 102 (49.0%), empate 2 (1.0%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=16.3%, WAPE ML=17.0%, mejora relativa ponderada=-4.2%, reduccion absoluta de error=-38.733, series comparables=210, historico total=5.685.550.

Frecuencia de victoria: ML gana 95 (45.2%), SCP gana 111 (52.9%), empate 4 (1.9%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +10.8%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): -4.2%. La mejora cambia de signo entre trimestres.

% victorias ML: 50.0% (primer trimestre) vs 45.2% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 172 | 33.4% | 32.2% | +3.6% | 44.8% | 54.1% | 1.2% |
| M2 | 195 | 13.9% | 11.4% | +18.1% | 47.7% | 50.8% | 1.5% |
| M3 | 193 | 16.5% | 14.4% | +13.0% | 47.2% | 51.8% | 1.0% |
| M4 | 191 | 20.3% | 18.1% | +10.9% | 50.8% | 45.5% | 3.7% |
| M5 | 182 | 12.9% | 13.8% | -6.7% | 46.2% | 52.2% | 1.6% |
| M6 | 163 | 18.2% | 22.0% | -21.1% | 41.7% | 57.1% | 1.2% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +3.6% vs -21.1%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 105 (47.5%), SCP gana 116 (52.5%), empate 0 (0.0%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **89.393** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| MovingAverage3M | 43 | 58.1% | 22.0% | 42.2% | -92.2% | +7.8% | no |
| AutoETS | 40 | 57.5% | 19.0% | 17.4% | +8.7% | +4.5% | no |
| SeasonalNaive | 39 | 43.6% | 16.1% | 14.4% | +10.4% | -2.9% | no |
| AutoARIMA | 38 | 36.8% | 24.8% | 31.2% | -25.9% | -10.8% | no |
| AutoTheta | 24 | 37.5% | 16.2% | 13.8% | +15.1% | -17.6% | no |
| HistoricAverage | 14 | 21.4% | 48.2% | 83.5% | -73.2% | -17.2% | no |
| MovingAverage12M | 14 | 57.1% | 38.7% | 45.6% | -17.7% | +2.2% | no |
| TSB | 6 | 83.3% | 87.1% | 89.9% | -3.2% | +10.8% | si |
| ADIDA | 2 | 0.0% | 105.0% | 128.0% | -21.9% | -18.1% | si |
| (sin clasificar) | 1 | 100.0% | 228.0% | 100.0% | +56.1% | +56.1% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 lineal | 138 | 41.3% | 17.3% | 18.1% | -4.4% | -6.7% | no |
| seasonal discrete | 50 | 56.0% | 74.1% | 76.0% | -2.5% | +3.6% | no |
| syntetos-boylan | 21 | 61.9% | 198.4% | 266.5% | -34.3% | +22.4% | no |
| x11 seasonal | 8 | 50.0% | 18.4% | 13.1% | +28.8% | -32.7% | si |
| copy last year | 4 | 75.0% | 125.0% | 101.2% | +19.0% | +7.1% | si |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 111 | 48.6% | 16.7% | 15.1% | +9.1% | -1.8% | no |
| erratic_acceptable | 42 | 19.0% | 27.6% | 30.2% | -9.5% | -19.2% | no |
| lumpy_acceptable | 20 | 60.0% | 21.3% | 60.8% | -185.7% | +7.3% | no |
| seasonal_discontinuous_acceptable | 19 | 68.4% | 60.9% | 66.4% | -9.1% | +12.3% | no |
| intermittent_acceptable | 12 | 50.0% | 94.3% | 98.4% | -4.3% | -3.2% | no |
| intermittent_insuficient | 4 | 75.0% | 118.2% | 78.6% | +33.5% | +37.8% | si |
| lumpy_insuficient | 4 | 75.0% | 203.4% | 193.1% | +5.1% | +39.4% | si |
| smooth_insuficient | 3 | 100.0% | 35.8% | 20.3% | +43.2% | +28.2% | si |
| intermittent_recentRelease | 3 | 66.7% | 150.5% | 136.1% | +9.5% | +65.3% | si |
| seasonal_discontinuous_insuficient | 2 | 0.0% | 52.4% | 60.9% | -16.1% | -70.4% | si |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable_acceptable | 111 | 48.6% | 16.7% | 15.1% | +9.1% | -1.8% | no |
| erratic_acceptable_acceptable | 42 | 19.0% | 27.6% | 30.2% | -9.5% | -19.2% | no |
| lumpy_acceptable_acceptable | 20 | 60.0% | 21.3% | 60.8% | -185.7% | +7.3% | no |
| seasonal_discontinuous_acceptable_acceptable | 19 | 68.4% | 60.9% | 66.4% | -9.1% | +12.3% | no |
| intermittent_acceptable_acceptable | 12 | 50.0% | 94.3% | 98.4% | -4.3% | -3.2% | no |
| intermittent_insuficient_insuficient | 4 | 75.0% | 118.2% | 78.6% | +33.5% | +37.8% | si |
| lumpy_insuficient_insuficient | 4 | 75.0% | 203.4% | 193.1% | +5.1% | +39.4% | si |
| smooth_insuficient_insuficient | 3 | 100.0% | 35.8% | 20.3% | +43.2% | +28.2% | si |
| intermittent_recentRelease_recentRelease | 3 | 66.7% | 150.5% | 136.1% | +9.5% | +65.3% | si |
| seasonal_discontinuous_insuficient_insuficient | 2 | 0.0% | 52.4% | 60.9% | -16.1% | -70.4% | si |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 111 | 48.6% | 16.7% | 15.1% | +9.1% | -1.8% | no |
| erratic_acceptable | 42 | 19.0% | 27.6% | 30.2% | -9.5% | -19.2% | no |
| lumpy_acceptable | 20 | 60.0% | 21.3% | 60.8% | -185.7% | +7.3% | no |
| seasonal_discontinuous_acceptable | 19 | 68.4% | 60.9% | 66.4% | -9.1% | +12.3% | no |
| intermittent_acceptable | 12 | 50.0% | 94.3% | 98.4% | -4.3% | -3.2% | no |
| intermittent_insuficient | 4 | 75.0% | 118.2% | 78.6% | +33.5% | +37.8% | si |
| lumpy_insuficient | 4 | 75.0% | 203.4% | 193.1% | +5.1% | +39.4% | si |
| smooth_insuficient | 3 | 100.0% | 35.8% | 20.3% | +43.2% | +28.2% | si |
| intermittent_recentRelease | 3 | 66.7% | 150.5% | 136.1% | +9.5% | +65.3% | si |
| seasonal_discontinuous_insuficient | 2 | 0.0% | 52.4% | 60.9% | -16.1% | -70.4% | si |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 lineal | 138 | 41.3% | 17.3% | 18.1% | -4.4% | -6.7% | no |
| seasonal discrete | 50 | 56.0% | 74.1% | 76.0% | -2.5% | +3.6% | no |
| syntetos-boylan | 21 | 61.9% | 198.4% | 266.5% | -34.3% | +22.4% | no |
| x11 seasonal | 8 | 50.0% | 18.4% | 13.1% | +28.8% | -32.7% | si |
| copy last year | 4 | 75.0% | 125.0% | 101.2% | +19.0% | +7.1% | si |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 9 filas. `HAS_ML_EXCLUDED=1` (recuento real): 101 filas. La diferencia (92) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 34 | +85.8% | 719.6% | 102.4% | ML | seasonal discrete | AutoTheta | seasonal_discontinuous_acceptable |
| 208 | +83.1% | 775.0% | 130.8% | ML | syntetos-boylan | MovingAverage3M | lumpy_insuficient |
| 392 | +81.9% | 68.0% | 12.3% | ML | x11 lineal | MovingAverage3M | intermittent_insuficient |
| 374 | +75.2% | 698.8% | 173.3% | ML | seasonal discrete | MovingAverage3M | lumpy_acceptable |
| 422 | +73.7% | 345.4% | 90.8% | ML | seasonal discrete | AutoARIMA | seasonal_discontinuous_acceptable |
| 173 | +72.9% | 368.4% | 100.0% | ML | seasonal discrete | MovingAverage3M | seasonal_discontinuous_acceptable |
| 437 | +70.6% | 133.4% | 39.3% | ML | seasonal discrete | AutoETS | seasonal_discontinuous_acceptable |
| 403 | +68.6% | 425.0% | 133.3% | ML | syntetos-boylan | MovingAverage3M | intermittent_recentRelease |
| 434 | +68.4% | 361.6% | 114.4% | ML | seasonal discrete | TSB | lumpy_acceptable |
| 52 | +67.4% | 35.5% | 11.6% | ML | x11 seasonal | SeasonalNaive | erratic_acceptable |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 367 | -5313.8% | 69.2% | 3746.0% | SCP | seasonal discrete | TSB | lumpy_acceptable |
| 135 | -400.0% | 11.2% | 55.8% | SCP | x11 lineal | MovingAverage3M | lumpy_acceptable |
| 330 | -380.3% | 40.2% | 193.3% | SCP | seasonal discrete | HistoricAverage | lumpy_acceptable |
| 286 | -372.2% | 25.0% | 118.1% | SCP | syntetos-boylan | MovingAverage12M | lumpy_acceptable |
| 430 | -298.9% | 18.5% | 73.7% | SCP | x11 lineal | AutoETS | erratic_acceptable |
| 102 | -295.1% | 16.9% | 66.6% | SCP | x11 seasonal | AutoTheta | erratic_acceptable |
| 265 | -257.9% | 51.2% | 183.1% | SCP | x11 lineal | AutoTheta | erratic_acceptable |
| 98 | -223.3% | 71.6% | 231.5% | SCP | x11 lineal | MovingAverage3M | erratic_acceptable |
| 479 | -147.7% | 434.0% | 1075.1% | SCP | seasonal discrete | AutoARIMA | smooth_acceptable |
| 244 | -145.7% | 16.6% | 40.8% | SCP | x11 lineal | AutoTheta | smooth_acceptable |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- Hay series con historico mensual negativo (posible ajuste/devolucion) que siguen siendo comparables en 6M.
- 73 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+4.2%). A nivel de serie individual, la mediana de mejora es -2.4% y ML gana en el 47.5% de las series comparables (60.5% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
