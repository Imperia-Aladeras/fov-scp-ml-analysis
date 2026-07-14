# Informe individual SCP vs ML — 10467_Embutidos_Martinez

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10467 | Fichero: `TA_FOV_SCP_ML_10467_Embutidos_Martinez.csv`
**Batch/Run:** ID_BATCH=[63] | ID_RUN_STAGING=[62] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **389 series candidatas**, **241 (62.0%)** son comparables en el semestre completo (6M). WAPE SCP=10.6%, WAPE ML=10.4%, mejora relativa ponderada=+2.3%, reduccion absoluta de error=105.244, series comparables=241, historico total=43.821.612.

Frecuencia de victoria en 6M: ML gana 142 (58.9%), SCP gana 99 (41.1%), empate 0 (0.0%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **389**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 241 | 62.0% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 111 | 28.5% |
| NOT_COMPARABLE_NO_HISTORY | 23 | 5.9% |
| NOT_COMPARABLE_MISSING_ML | 10 | 2.6% |
| NOT_COMPARABLE_MISSING_SCP | 4 | 1.0% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **89** (22.9% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 89 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 389 | 207 | 53.2% |
| M2 | 389 | 221 | 56.8% |
| M3 | 389 | 222 | 57.1% |
| M4 | 389 | 225 | 57.8% |
| M5 | 389 | 235 | 60.4% |
| M6 | 389 | 236 | 60.7% |
| RECENT_3M | 389 | 224 | 57.6% |
| OLDER_3M | 389 | 239 | 61.4% |
| 6M | 389 | 241 | 62.0% |

---

## 3. Semestre completo (6M)

WAPE SCP=10.6%, WAPE ML=10.4%, mejora relativa ponderada=+2.3%, reduccion absoluta de error=105.244, series comparables=241, historico total=43.821.612.

Frecuencia de victoria: ML gana 142 (58.9%), SCP gana 99 (41.1%), empate 0 (0.0%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=10.8%, WAPE ML=10.1%, mejora relativa ponderada=+5.9%, reduccion absoluta de error=135.454, series comparables=224, historico total=21.419.116.

Frecuencia de victoria: ML gana 114 (50.9%), SCP gana 109 (48.7%), empate 1 (0.4%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=9.7%, WAPE ML=10.6%, mejora relativa ponderada=-9.7%, reduccion absoluta de error=-211.128, series comparables=239, historico total=22.402.496.

Frecuencia de victoria: ML gana 146 (61.1%), SCP gana 92 (38.5%), empate 1 (0.4%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +5.9%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): -9.7%. La mejora cambia de signo entre trimestres.

% victorias ML: 50.9% (primer trimestre) vs 61.1% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 207 | 11.2% | 8.5% | +23.5% | 58.5% | 40.6% | 1.0% |
| M2 | 221 | 7.0% | 6.2% | +11.5% | 49.3% | 50.2% | 0.5% |
| M3 | 222 | 5.0% | 6.7% | -33.7% | 44.6% | 55.4% | 0.0% |
| M4 | 225 | 8.0% | 11.1% | -38.9% | 43.6% | 55.6% | 0.9% |
| M5 | 235 | 11.1% | 10.6% | +4.3% | 66.8% | 33.2% | 0.0% |
| M6 | 236 | 9.7% | 9.2% | +5.1% | 58.5% | 40.7% | 0.8% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +23.5% vs +5.1%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 142 (58.9%), SCP gana 99 (41.1%), empate 0 (0.0%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **105.244** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| AutoETS | 90 | 67.8% | 8.4% | 9.3% | -10.9% | +8.6% | no |
| AutoARIMA | 60 | 58.3% | 10.9% | 9.2% | +15.3% | +7.8% | no |
| HistoricAverage | 41 | 46.3% | 20.2% | 17.0% | +15.9% | -16.8% | no |
| MovingAverage3M | 18 | 55.6% | 12.9% | 11.9% | +7.9% | +0.5% | no |
| AutoTheta | 17 | 47.1% | 10.4% | 16.7% | -59.5% | -3.2% | no |
| MovingAverage12M | 8 | 50.0% | 8.7% | 7.5% | +13.9% | -4.1% | si |
| SeasonalNaive | 5 | 60.0% | 5.0% | 4.8% | +2.8% | +34.6% | si |
| (sin clasificar) | 1 | 100.0% | 113.4% | 100.0% | +11.8% | +11.8% | si |
| TSB | 1 | 100.0% | 287.2% | 77.3% | +73.1% | +73.1% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 lineal | 122 | 61.5% | 10.1% | 10.4% | -2.9% | +8.6% | no |
| x11 seasonal | 73 | 58.9% | 7.9% | 7.9% | -0.1% | +3.6% | no |
| average | 26 | 19.2% | 8.9% | 12.5% | -39.5% | -29.5% | no |
| syntetos-boylan | 14 | 100.0% | 148.3% | 71.0% | +52.2% | +52.0% | no |
| seasonal discrete | 6 | 83.3% | 104.5% | 69.6% | +33.4% | +40.3% | si |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 189 | 60.8% | 9.3% | 9.5% | -2.1% | +8.0% | no |
| smooth_recentRelease | 21 | 19.0% | 7.2% | 9.1% | -26.4% | -29.2% | no |
| intermittent_newRelease | 13 | 100.0% | 148.3% | 71.0% | +52.1% | +52.0% | no |
| smooth_insuficient | 6 | 50.0% | 23.2% | 23.5% | -1.3% | -1.1% | si |
| smooth_newRelease | 4 | 25.0% | 27.5% | 47.6% | -73.4% | -138.3% | si |
| lumpy_insuficient | 3 | 100.0% | 380.5% | 101.1% | +73.4% | +73.3% | si |
| erratic_acceptable | 1 | 0.0% | 8.5% | 16.2% | -90.5% | -90.5% | si |
| intermittent_acceptable | 1 | 100.0% | 287.2% | 77.3% | +73.1% | +73.1% | si |
| erratic_recentRelease | 1 | 0.0% | 179.8% | 381.9% | -112.4% | -112.4% | si |
| intermittent_obsolete | 1 | 100.0% | 113.4% | 100.0% | +11.8% | +11.8% | si |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable_acceptable | 189 | 60.8% | 9.3% | 9.5% | -2.1% | +8.0% | no |
| smooth_recentRelease_recentRelease | 21 | 19.0% | 7.2% | 9.1% | -26.4% | -29.2% | no |
| intermittent_newRelease_newRelease | 13 | 100.0% | 148.3% | 71.0% | +52.1% | +52.0% | no |
| smooth_insuficient_insuficient | 6 | 50.0% | 23.2% | 23.5% | -1.3% | -1.1% | si |
| smooth_newRelease_newRelease | 4 | 25.0% | 27.5% | 47.6% | -73.4% | -138.3% | si |
| lumpy_insuficient_insuficient | 3 | 100.0% | 380.5% | 101.1% | +73.4% | +73.3% | si |
| erratic_acceptable_acceptable | 1 | 0.0% | 8.5% | 16.2% | -90.5% | -90.5% | si |
| intermittent_acceptable_acceptable | 1 | 100.0% | 287.2% | 77.3% | +73.1% | +73.1% | si |
| erratic_recentRelease_recentRelease | 1 | 0.0% | 179.8% | 381.9% | -112.4% | -112.4% | si |
| intermittent_obsolete_obsolete | 1 | 100.0% | 113.4% | 100.0% | +11.8% | +11.8% | si |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_acceptable | 189 | 60.8% | 9.3% | 9.5% | -2.1% | +8.0% | no |
| smooth_recentRelease | 21 | 19.0% | 7.2% | 9.1% | -26.4% | -29.2% | no |
| intermittent_newRelease | 13 | 100.0% | 148.3% | 71.0% | +52.1% | +52.0% | no |
| smooth_insuficient | 6 | 50.0% | 23.2% | 23.5% | -1.3% | -1.1% | si |
| smooth_newRelease | 4 | 25.0% | 27.5% | 47.6% | -73.4% | -138.3% | si |
| lumpy_insuficient | 3 | 100.0% | 380.5% | 101.1% | +73.4% | +73.3% | si |
| erratic_acceptable | 1 | 0.0% | 8.5% | 16.2% | -90.5% | -90.5% | si |
| intermittent_acceptable | 1 | 100.0% | 287.2% | 77.3% | +73.1% | +73.1% | si |
| erratic_recentRelease | 1 | 0.0% | 179.8% | 381.9% | -112.4% | -112.4% | si |
| intermittent_obsolete | 1 | 100.0% | 113.4% | 100.0% | +11.8% | +11.8% | si |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 lineal | 122 | 61.5% | 10.1% | 10.4% | -2.9% | +8.6% | no |
| x11 seasonal | 73 | 58.9% | 7.9% | 7.9% | -0.1% | +3.6% | no |
| average | 26 | 19.2% | 8.9% | 12.5% | -39.5% | -29.5% | no |
| syntetos-boylan | 14 | 100.0% | 148.3% | 71.0% | +52.2% | +52.0% | no |
| seasonal discrete | 6 | 83.3% | 104.5% | 69.6% | +33.4% | +40.3% | si |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 0 filas. `HAS_ML_EXCLUDED=1` (recuento real): 89 filas. La diferencia (89) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 268 | +87.5% | 1600.0% | 200.0% | ML | syntetos-boylan | MovingAverage3M | lumpy_insuficient |
| 374 | +77.2% | 31.6% | 7.2% | ML | x11 lineal | AutoETS | smooth_acceptable |
| 351 | +73.3% | 375.0% | 100.0% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 194 | +73.1% | 287.2% | 77.3% | ML | seasonal discrete | TSB | intermittent_acceptable |
| 179 | +72.5% | 45.5% | 12.5% | ML | x11 seasonal | AutoETS | smooth_acceptable |
| 389 | +72.2% | 6.5% | 1.8% | ML | x11 seasonal | AutoARIMA | smooth_acceptable |
| 333 | +68.8% | 320.8% | 100.0% | ML | seasonal discrete | MovingAverage3M | lumpy_insuficient |
| 295 | +67.4% | 9.0% | 2.9% | ML | x11 lineal | AutoETS | smooth_acceptable |
| 319 | +64.7% | 79.1% | 27.9% | ML | average | HistoricAverage | smooth_newRelease |
| 225 | +62.8% | 5.1% | 1.9% | ML | x11 seasonal | AutoTheta | smooth_acceptable |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 180 | -262.8% | 15.4% | 55.9% | SCP | average | HistoricAverage | smooth_newRelease |
| 173 | -239.5% | 28.6% | 97.0% | SCP | x11 lineal | AutoTheta | smooth_acceptable |
| 133 | -230.2% | 2.6% | 8.4% | SCP | x11 seasonal | AutoETS | smooth_acceptable |
| 64 | -197.9% | 29.2% | 87.1% | SCP | x11 lineal | AutoETS | smooth_acceptable |
| 213 | -197.5% | 1.5% | 4.5% | SCP | x11 seasonal | AutoETS | smooth_acceptable |
| 212 | -180.3% | 6.5% | 18.2% | SCP | x11 lineal | AutoARIMA | smooth_acceptable |
| 317 | -170.9% | 2.7% | 7.4% | SCP | x11 lineal | AutoETS | smooth_acceptable |
| 303 | -163.0% | 18.3% | 48.1% | SCP | average | HistoricAverage | smooth_newRelease |
| 328 | -132.8% | 24.3% | 56.6% | SCP | x11 lineal | AutoETS | smooth_acceptable |
| 42 | -122.3% | 3.0% | 6.7% | SCP | x11 seasonal | AutoETS | smooth_acceptable |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- 6 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+2.3%). A nivel de serie individual, la mediana de mejora es +7.0% y ML gana en el 58.9% de las series comparables (62.0% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
