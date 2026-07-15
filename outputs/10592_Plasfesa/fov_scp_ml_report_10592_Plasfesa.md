# Informe individual SCP vs ML — 10592_Plasfesa

**Fecha del analisis:** 15/07/2026
**Cliente:** ID_CLIENT=10592 | Fichero: `TA_FOV_SCP_ML_10592_Plasfesa.csv`
**Batch/Run:** ID_BATCH=[66] | ID_RUN_STAGING=[66] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Sobre **784 series candidatas**, **321 (40.9%)** son comparables en el semestre completo (6M). WAPE SCP=72.8%, WAPE ML=50.4%, mejora relativa ponderada=+30.7%, reduccion absoluta de error=4.017.152, series comparables=321, historico total=17.954.102.

Frecuencia de victoria en 6M: ML gana 249 (77.6%), SCP gana 69 (21.5%), empate 3 (0.9%).

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **784**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| COMPARABLE | 321 | 40.9% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 310 | 39.5% |
| NOT_COMPARABLE_ML_EXCLUDED | 120 | 15.3% |
| NOT_COMPARABLE_MISSING_SCP | 33 | 4.2% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **430** (54.8% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 348 |
| ShortSeries | 82 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 784 | 272 | 34.7% |
| M2 | 784 | 266 | 33.9% |
| M3 | 784 | 269 | 34.3% |
| M4 | 784 | 278 | 35.5% |
| M5 | 784 | 275 | 35.1% |
| M6 | 784 | 264 | 33.7% |
| RECENT_3M | 784 | 321 | 40.9% |
| OLDER_3M | 784 | 314 | 40.1% |
| 6M | 784 | 321 | 40.9% |

---

## 3. Semestre completo (6M)

WAPE SCP=72.8%, WAPE ML=50.4%, mejora relativa ponderada=+30.7%, reduccion absoluta de error=4.017.152, series comparables=321, historico total=17.954.102.

Frecuencia de victoria: ML gana 249 (77.6%), SCP gana 69 (21.5%), empate 3 (0.9%).

---

## 4. Primer trimestre del semestre (M1-M3)

WAPE SCP=75.9%, WAPE ML=31.0%, mejora relativa ponderada=+59.2%, reduccion absoluta de error=3.877.443, series comparables=321, historico total=8.626.853.

Frecuencia de victoria: ML gana 238 (74.1%), SCP gana 71 (22.1%), empate 12 (3.7%).

---

## 5. Segundo trimestre del semestre (M4-M6)

WAPE SCP=69.9%, WAPE ML=68.3%, mejora relativa ponderada=+2.2%, reduccion absoluta de error=141.513, series comparables=314, historico total=9.327.249.

Frecuencia de victoria: ML gana 128 (40.8%), SCP gana 161 (51.3%), empate 25 (8.0%).

---

## 6. Comparacion entre trimestres

Mejora ponderada en Primer trimestre del semestre (M1-M3): +59.2%. Mejora ponderada en Segundo trimestre del semestre (M4-M6): +2.2%. La mejora mantiene el mismo signo en ambos trimestres.

% victorias ML: 74.1% (primer trimestre) vs 40.8% (segundo trimestre).

---

## 7. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora relativa | % ML | % SCP | % Empate |
|---|---|---|---|---|---|---|---|
| M1 | 272 | 33.5% | 33.5% | +0.1% | 49.3% | 42.6% | 8.1% |
| M2 | 266 | 94.9% | 25.3% | +73.4% | 80.1% | 9.4% | 10.5% |
| M3 | 269 | 96.3% | 24.9% | +74.1% | 84.0% | 8.9% | 7.1% |
| M4 | 278 | 31.7% | 31.4% | +0.9% | 39.6% | 52.9% | 7.6% |
| M5 | 275 | 91.9% | 89.7% | +2.4% | 5.1% | 4.7% | 90.2% |
| M6 | 264 | 93.1% | 91.6% | +1.6% | 6.4% | 3.0% | 90.5% |

M1 (mas reciente) vs M6 (mas antiguo): mejora +0.1% vs +1.6%. No se concluye estabilidad ni tendencia solo a partir de dos puntos; ver la tabla completa para el patron mes a mes.

---

## 8. Frecuencia de victoria

Semestre completo: ML gana 249 (77.6%), SCP gana 69 (21.5%), empate 3 (0.9%).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Reduccion absoluta de error en 6M: **4.017.152** unidades de historico (positivo = ML reduce error total frente a SCP).

---

## 10. Modelos ML

Modelos seleccionados por ML en Semestre completo (M1-M6) (top 10 por frecuencia):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| SeasonalNaive | 86 | 82.6% | 68.8% | 45.5% | +33.9% | +24.9% | no |
| HistoricAverage | 62 | 80.6% | 74.7% | 44.9% | +40.0% | +26.4% | no |
| MovingAverage3M | 51 | 76.5% | 72.8% | 52.0% | +28.6% | +19.9% | no |
| AutoTheta | 44 | 90.9% | 75.4% | 54.6% | +27.6% | +27.2% | no |
| MovingAverage12M | 38 | 78.9% | 77.8% | 58.8% | +24.5% | +31.3% | no |
| TSB | 18 | 50.0% | 78.4% | 84.3% | -7.5% | +2.2% | no |
| CrostonSBA | 9 | 33.3% | 116.2% | 127.3% | -9.6% | -39.5% | si |
| ADIDA | 8 | 37.5% | 88.6% | 90.9% | -2.7% | -4.8% | si |
| CrostonClassic | 5 | 80.0% | 106.1% | 92.4% | +12.9% | +16.9% | si |

La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de victoria y la mejora agregada, no solo el conteo.

---

## 11. Modelos SCP

Modelos SCP en Semestre completo (M1-M6) (top 10 por frecuencia), incluye contra que compite ML:

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 129 | 90.7% | 77.2% | 53.1% | +31.2% | +28.2% | no |
| seasonal discrete | 77 | 58.4% | 93.0% | 88.0% | +5.4% | +8.2% | no |
| x11 lineal | 68 | 88.2% | 66.9% | 43.1% | +35.5% | +32.2% | no |
| syntetos-boylan | 34 | 52.9% | 97.7% | 106.8% | -9.3% | +7.0% | no |
| preserve current forecast | 13 | 69.2% | 93.4% | 99.9% | -7.0% | +8.0% | no |

---

## 12. Clasificaciones

**ML_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient | 218 | 85.3% | 72.6% | 49.1% | +32.4% | +27.9% | no |
| intermittent_insuficient | 80 | 57.5% | 101.0% | 102.1% | -1.1% | +8.1% | no |
| smooth_recentRelease | 11 | 72.7% | 60.2% | 50.7% | +15.8% | +15.7% | no |
| lumpy_insuficient | 7 | 85.7% | 87.5% | 81.2% | +7.1% | +13.7% | si |
| intermittent_recentRelease | 3 | 33.3% | 75.4% | 67.0% | +11.3% | -0.6% | si |
| erratic_insuficient | 2 | 100.0% | 36.9% | 25.4% | +31.1% | +36.5% | si |

**ML_TYPE** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient_insuficient | 218 | 85.3% | 72.6% | 49.1% | +32.4% | +27.9% | no |
| intermittent_insuficient_insuficient | 80 | 57.5% | 101.0% | 102.1% | -1.1% | +8.1% | no |
| smooth_recentRelease_recentRelease | 11 | 72.7% | 60.2% | 50.7% | +15.8% | +15.7% | no |
| lumpy_insuficient_insuficient | 7 | 85.7% | 87.5% | 81.2% | +7.1% | +13.7% | si |
| intermittent_recentRelease_recentRelease | 3 | 33.3% | 75.4% | 67.0% | +11.3% | -0.6% | si |
| erratic_insuficient_insuficient | 2 | 100.0% | 36.9% | 25.4% | +31.1% | +36.5% | si |

**SERIES_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| smooth_insuficient | 218 | 85.3% | 72.6% | 49.1% | +32.4% | +27.9% | no |
| intermittent_insuficient | 80 | 57.5% | 101.0% | 102.1% | -1.1% | +8.1% | no |
| smooth_recentRelease | 11 | 72.7% | 60.2% | 50.7% | +15.8% | +15.7% | no |
| lumpy_insuficient | 7 | 85.7% | 87.5% | 81.2% | +7.1% | +13.7% | si |
| intermittent_recentRelease | 3 | 33.3% | 75.4% | 67.0% | +11.3% | -0.6% | si |
| erratic_insuficient | 2 | 100.0% | 36.9% | 25.4% | +31.1% | +36.5% | si |

**SCP_CLASSIFICATION** (top 10):

| Categoria | N | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora | % muestra pequena |
|---|---|---|---|---|---|---|---|
| x11 seasonal | 129 | 90.7% | 77.2% | 53.1% | +31.2% | +28.2% | no |
| seasonal discrete | 77 | 58.4% | 93.0% | 88.0% | +5.4% | +8.2% | no |
| x11 lineal | 68 | 88.2% | 66.9% | 43.1% | +35.5% | +32.2% | no |
| syntetos-boylan | 34 | 52.9% | 97.7% | 106.8% | -9.3% | +7.0% | no |
| preserve current forecast | 13 | 69.2% | 93.4% | 99.9% | -7.0% | +8.0% | no |

Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se deben extraer conclusiones fuertes de ellas.

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 120 filas. `HAS_ML_EXCLUDED=1` (recuento real): 430 filas. La diferencia (310) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Top series con mayor mejora porcentual en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 1765 | +90.5% | 84.6% | 8.0% | ML | x11 seasonal | HistoricAverage | smooth_insuficient |
| 1402 | +73.6% | 84.5% | 22.3% | ML | syntetos-boylan | SeasonalNaive | intermittent_insuficient |
| 404 | +70.2% | 166.7% | 49.7% | ML | syntetos-boylan | HistoricAverage | intermittent_insuficient |
| 114 | +69.3% | 150.0% | 46.0% | ML | syntetos-boylan | HistoricAverage | intermittent_insuficient |
| 992 | +68.3% | 69.0% | 21.9% | ML | seasonal discrete | SeasonalNaive | lumpy_insuficient |
| 792 | +66.4% | 150.0% | 50.4% | ML | syntetos-boylan | ADIDA | intermittent_insuficient |
| 1762 | +56.6% | 86.3% | 37.5% | ML | x11 seasonal | SeasonalNaive | smooth_insuficient |
| 930 | +54.3% | 54.7% | 25.0% | ML | seasonal discrete | SeasonalNaive | smooth_insuficient |
| 684 | +52.1% | 150.0% | 71.9% | ML | syntetos-boylan | ADIDA | intermittent_insuficient |
| 163 | +52.0% | 71.2% | 34.2% | ML | x11 seasonal | AutoTheta | smooth_insuficient |

---

## 15. Casos de mayor deterioro

Top series donde ML peor se comporta frente a SCP en Semestre completo (M1-M6):

| ID_CONFIGURATION | ML_IMPROVEMENT_VS_SCP_PCT | WAPE SCP | WAPE ML | Winner | Modelo SCP | Modelo ML | Clasificacion |
|---|---|---|---|---|---|---|---|
| 1184 | -142.5% | 66.7% | 161.7% | SCP | syntetos-boylan | CrostonSBA | intermittent_insuficient |
| 1576 | -92.9% | 61.5% | 118.6% | SCP | x11 seasonal | SeasonalNaive | smooth_insuficient |
| 765 | -92.0% | 74.9% | 143.9% | SCP | preserve current forecast | CrostonSBA | intermittent_insuficient |
| 545 | -73.7% | 60.0% | 104.2% | SCP | seasonal discrete | AutoTheta | smooth_insuficient |
| 1162 | -72.3% | 84.6% | 145.8% | SCP | x11 lineal | MovingAverage3M | smooth_insuficient |
| 954 | -71.8% | 84.9% | 145.9% | SCP | syntetos-boylan | TSB | intermittent_insuficient |
| 817 | -71.0% | 80.1% | 137.0% | SCP | syntetos-boylan | CrostonSBA | intermittent_insuficient |
| 1465 | -68.4% | 58.4% | 98.3% | SCP | seasonal discrete | MovingAverage12M | intermittent_insuficient |
| 1470 | -66.7% | 77.2% | 128.6% | SCP | seasonal discrete | SeasonalNaive | intermittent_insuficient |
| 204 | -65.4% | 82.5% | 136.4% | SCP | seasonal discrete | TSB | intermittent_insuficient |

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.
- Hay series con historico mensual negativo (posible ajuste/devolucion) que siguen siendo comparables en 6M.
- 12 observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 18. Conclusion

En el semestre completo, ML **mejora** el WAPE global ponderado frente a SCP (+30.7%). A nivel de serie individual, la mediana de mejora es +22.6% y ML gana en el 77.6% de las series comparables (40.9% del universo candidato). Estas cuatro cifras (impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida.
