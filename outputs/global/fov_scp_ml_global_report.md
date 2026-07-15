# Comparativa global SCP vs ML — todos los clientes

**Fecha del analisis:** 15/07/2026
**Clientes incluidos:** 9

---

## 1. Resumen ejecutivo

Sobre 9 clientes cargados y 7.881 series comparables en el semestre completo, ML **no mejora** el WAPE global ponderado frente a SCP (-11.9%). ML mejora en **6 de 7 clientes con performance calculable** en 6M (85.7%; mediana de mejora por cliente: +3.5%), y otros 2 clientes no tienen series comparables en 6M. A nivel de serie, gana en el 53.8% de las series comparables. Estas cifras no deben confundirse entre si: se detallan por separado en las secciones siguientes.

---

## 2. Clientes analizados

| ID_CLIENT | Etiqueta | CSV | Estado |
|---|---|---|---|
| 10204 | 10204_SKLUM | TA_FOV_SCP_ML_10204_SKLUM.csv | SUCCESS_WITH_WARNINGS |
| 10461 | 10461_Garcia_Millan | TA_FOV_SCP_ML_10461_Garcia_Millan.csv | SUCCESS_WITH_WARNINGS |
| 10467 | 10467_Embutidos_Martinez | TA_FOV_SCP_ML_10467_Embutidos_Martinez.csv | SUCCESS_WITH_WARNINGS |
| 10592 | 10592_Plasfesa | TA_FOV_SCP_ML_10592_Plasfesa.csv | SUCCESS_WITH_WARNINGS |
| 10620 | 10620_Frutas_Bollo | TA_FOV_SCP_ML_10620_Frutas_Bollo.csv | SUCCESS_WITH_WARNINGS |
| 10629 | 10629_Platanomelon | TA_FOV_SCP_ML_10629_Platanomelon.csv | SUCCESS_WITH_WARNINGS |
| 10664 | 10664_DV_Flora | TA_FOV_SCP_ML_10664_DV_Flora.csv | SUCCESS_WITH_WARNINGS |
| 10666 | 10666_Grupo_Alacant | TA_FOV_SCP_ML_10666_Grupo_Alacant.csv | SUCCESS_WITH_WARNINGS |
| 10699 | 10699_SIGMA | TA_FOV_SCP_ML_10699_SIGMA.csv | SUCCESS_WITH_WARNINGS |

---

## 3. Calidad y cobertura de los inputs

Series candidatas totales: **20.539**. Series comparables en 6M: **7.881** (38.4%). La cobertura varia sensiblemente entre clientes (ver 02_client_coverage en el Excel global).

Clientes cuyo CSV requirio normalizacion en memoria (comillas dobladas): 9 de 9.

---

## 4. Resultado del semestre completo

WAPE SCP=56.4%, WAPE ML=63.1%, mejora global ponderada=-11.9%, reduccion absoluta=-19.668.844, series comparables=7.881 de 20.539 candidatas (38.4%).

---

## 5. Resultado del Primer trimestre del semestre (M1-M3)

WAPE SCP=47.1%, WAPE ML=51.8%, mejora global ponderada=-10.0%, reduccion absoluta=-7.174.454, series comparables=7.459 de 20.539 candidatas (36.3%).

---

## 6. Resultado del Segundo trimestre del semestre (M4-M6)

WAPE SCP=61.4%, WAPE ML=66.9%, mejora global ponderada=-8.9%, reduccion absoluta=-7.749.043, series comparables=7.565 de 20.539 candidatas (36.8%).

---

## 7. Comparacion entre trimestres

Mejora ponderada: -10.0% (primer trimestre) vs -8.9% (segundo trimestre). La mejora global mantiene el mismo signo en ambos trimestres.

% de clientes que mejoran: 85.7% vs 42.9%.

---

## 8. Evolucion mensual

| Mes | Comparables | WAPE SCP | WAPE ML | Mejora ponderada | % clientes mejoran | % series gana ML |
|---|---|---|---|---|---|---|
| M1 | 6.858 | 34.9% | 31.8% | +9.0% | 85.7% | 48.1% |
| M2 | 6.962 | 43.4% | 43.5% | -0.2% | 71.4% | 50.8% |
| M3 | 7.049 | 52.7% | 52.8% | -0.3% | 57.1% | 49.5% |
| M4 | 7.090 | 53.9% | 56.0% | -3.9% | 42.9% | 46.0% |
| M5 | 6.982 | 58.9% | 59.1% | -0.3% | 57.1% | 48.0% |
| M6 | 7.027 | 59.4% | 59.0% | +0.7% | 85.7% | 47.7% |

No se concluye que ML mejora de forma estable solo porque gane mas series en algun mes: comparar siempre con la mejora ponderada y el % de clientes que mejoran de la misma fila.

---

## 9. WAPE global ponderado

Perspectiva 1 (impacto ponderado por volumen) para cada periodo:

| Periodo | WAPE SCP | WAPE ML | Mejora global ponderada |
|---|---|---|---|
| M1 | 34.9% | 31.8% | +9.0% |
| M2 | 43.4% | 43.5% | -0.2% |
| M3 | 52.7% | 52.8% | -0.3% |
| M4 | 53.9% | 56.0% | -3.9% |
| M5 | 58.9% | 59.1% | -0.3% |
| M6 | 59.4% | 59.0% | +0.7% |
| RECENT_3M | 47.1% | 51.8% | -10.0% |
| OLDER_3M | 61.4% | 66.9% | -8.9% |
| 6M | 56.4% | 63.1% | -11.9% |

---

## 10. Media de mejora por cliente

Perspectiva 2 (cada cliente pesa igual, no se pondera por numero de series). La media, la desviacion y el resto de estadisticos de esta seccion se calculan **unicamente sobre los clientes evaluables** (con mejora calculable en ese periodo); `N_SIN_PERFORMANCE` indica cuantos clientes del total no entran en el calculo por no tener ninguna serie comparable en ese periodo:

| Periodo | N total | N evaluables | N sin performance | Media entre clientes | Desviacion |
|---|---|---|---|---|---|
| M1 | 9 | 7 | 2 | +6.7% | 8.9% |
| M2 | 9 | 7 | 2 | +15.4% | 29.9% |
| M3 | 9 | 7 | 2 | +8.0% | 34.4% |
| M4 | 9 | 7 | 2 | -6.9% | 17.0% |
| M5 | 9 | 7 | 2 | +1.7% | 6.8% |
| M6 | 9 | 7 | 2 | +0.4% | 10.0% |
| RECENT_3M | 9 | 7 | 2 | +9.4% | 27.0% |
| OLDER_3M | 9 | 7 | 2 | -3.1% | 5.6% |
| 6M | 9 | 7 | 2 | +4.4% | 15.9% |

---

## 11. Mediana de mejora por cliente

La mediana es la referencia principal cuando hay clientes outlier. Mismo denominador que la seccion 10 (unicamente clientes evaluables, columna N evaluables):

| Periodo | N evaluables | Mediana entre clientes | P25 | P75 |
|---|---|---|---|---|
| M1 | 7 | +3.6% | +1.7% | +9.9% |
| M2 | 7 | +11.5% | +4.8% | +19.5% |
| M3 | 7 | +5.2% | -11.6% | +16.7% |
| M4 | 7 | -0.8% | -12.4% | +2.8% |
| M5 | 7 | +1.8% | -2.3% | +3.3% |
| M6 | 7 | +3.1% | +1.0% | +4.2% |
| RECENT_3M | 7 | +5.9% | +1.9% | +14.4% |
| OLDER_3M | 7 | -3.0% | -6.9% | +1.2% |
| 6M | 7 | +3.5% | +1.4% | +8.3% |

---

## 12. Media y mediana por serie

Perspectiva 3: estadistica de la mejora relativa de cada serie individual de todos los clientes juntos (no reconstruida desde las medianas por cliente).

| Periodo | Media por serie | Mediana por serie | P25 | P75 |
|---|---|---|---|---|
| M1 | -182.6% | +0.0% | -87.5% | +47.6% |
| M2 | -48537.1% | +4.2% | -65.9% | +51.0% |
| M3 | -103673.4% | +1.1% | -68.2% | +51.0% |
| M4 | -178659.7% | +0.0% | -63.6% | +42.9% |
| M5 | -177979.0% | +0.0% | -58.2% | +45.4% |
| M6 | -136526.4% | +0.0% | -60.9% | +49.0% |
| RECENT_3M | -37.5% | +3.2% | -36.2% | +34.9% |
| OLDER_3M | -186279.7% | +0.0% | -31.1% | +27.4% |
| 6M | -24.2% | +3.5% | -24.9% | +25.8% |

La media por serie puede ser extremadamente negativa o positiva (ordenes de magnitud mayor que la mediana): esto ocurre cuando una o pocas series tienen un SCP_WAPE casi nulo pero no exactamente cero, lo que dispara el porcentaje de mejora individual a valores muy grandes al dividir por un denominador casi nulo. No se recorta ni se oculta ese valor (ver seccion 20), pero la mediana es la referencia principal para interpretar el comportamiento tipico de una serie.

---

## 13. Clientes donde mejora ML

ML mejora en **6 de 7 clientes con performance calculable** en 6M. Otros 2 clientes no tienen series comparables en 6M y no entran en este recuento.

| Cliente | Mejora ponderada 6M |
|---|---|
| 10592_Plasfesa | +30.7% |
| 10666_Grupo_Alacant | +12.4% |
| 10664_DV_Flora | +4.2% |
| 10629_Platanomelon | +3.5% |
| 10467_Embutidos_Martinez | +2.3% |
| 10204_SKLUM | +0.5% |

---

## 14. Clientes donde empeora

1 de 7 clientes con performance calculable no mejoran (empeoran o quedan iguales) en 6M. Otros 2 clientes no tienen series comparables en 6M y no entran en este recuento.

| Cliente | Mejora ponderada 6M |
|---|---|
| 10620_Frutas_Bollo | -22.7% |

---

## 15. Concentracion de la mejora

**REDUCCION_POSITIVA_TOTAL** (suma de clientes que reducen error): 7.369.649. **DETERIORO_TOTAL_ABSOLUTO** (suma, en valor absoluto, de clientes que aumentan error): 27.038.493. **REDUCCION_NETA**: -19.668.844.

No se calcula ni se presenta un porcentaje de contribucion sobre la reduccion neta (puede ser cero o negativa y da lugar a porcentajes fuera de 0-100% dificiles de interpretar): cada cliente se compara solo dentro de su propio grupo (reduce error / aumenta error).

El cliente que **mas reduce error** en 6M es **10592_Plasfesa** (54.5% de la reduccion positiva total).

Clientes que reducen error:

| Cliente | Reduccion absoluta | % de la reduccion positiva |
|---|---|---|
| 10592_Plasfesa | 4.017.152 | 54.5% |
| 10666_Grupo_Alacant | 3.144.034 | 42.7% |
| 10467_Embutidos_Martinez | 105.244 | 1.4% |
| 10664_DV_Flora | 89.393 | 1.2% |
| 10204_SKLUM | 7.588 | 0.1% |
| 10629_Platanomelon | 6.239 | 0.1% |

El cliente que **mas aumenta error** en 6M es **10620_Frutas_Bollo** (100.0% del deterioro total absoluto). Este cliente NO es un contribuidor positivo a la reduccion: aporta deterioro, no mejora.

Clientes que aumentan error:

| Cliente | Reduccion absoluta (negativa) | % del deterioro total |
|---|---|---|
| 10620_Frutas_Bollo | -27.038.493 | 100.0% |

---

## 16. Modelos que mas aportan

Modelos ML por frecuencia y tasa de victoria en Semestre completo (M1-M6) (todos los clientes):

| Categoria | N series | N clientes | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora |
|---|---|---|---|---|---|---|---|
| MovingAverage3M | 1.711 | 7 | 52.3% | 92.1% | 116.6% | -26.5% | +2.1% |
| SeasonalNaive | 1.581 | 7 | 45.4% | 47.2% | 50.5% | -7.0% | -2.7% |
| AutoTheta | 1.226 | 7 | 64.0% | 53.9% | 46.5% | +13.8% | +12.1% |
| HistoricAverage | 1.123 | 7 | 59.8% | 77.0% | 65.2% | +15.4% | +7.9% |
| AutoARIMA | 775 | 6 | 48.4% | 51.7% | 56.4% | -9.1% | -0.8% |
| AutoETS | 734 | 6 | 52.6% | 32.9% | 30.0% | +8.9% | +1.7% |
| MovingAverage12M | 502 | 7 | 60.2% | 64.4% | 81.9% | -27.2% | +9.9% |
| TSB | 105 | 7 | 51.4% | 88.3% | 121.0% | -37.1% | +2.4% |
| ADIDA | 59 | 6 | 44.1% | 101.5% | 202.0% | -98.9% | +0.0% |
| CrostonSBA | 31 | 5 | 41.9% | 167.1% | 299.1% | -79.0% | -12.3% |

La frecuencia de seleccion no implica mayor aportacion de valor: comparar tasa de victoria y mejora agregada.

---

## 17. Clasificaciones donde funciona mejor ML

Tipologias (SERIES_CLASSIFICATION) con mayor tasa de victoria ML (muestra >= 10 series):

| Categoria | N series | N clientes | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora |
|---|---|---|---|---|---|---|---|
| intermittent_newRelease | 14 | 2 | 92.9% | 148.3% | 71.0% | +52.1% | +52.0% |
| smooth_insuficient | 2.326 | 7 | 63.8% | 42.9% | 31.1% | +27.4% | +11.8% |
| lumpy_acceptable | 96 | 5 | 62.5% | 95.4% | 101.0% | -5.9% | +13.8% |
| smooth_acceptable | 2.163 | 6 | 51.9% | 15.6% | 14.1% | +9.9% | +1.4% |
| intermittent_acceptable | 86 | 6 | 51.2% | 63.0% | 109.6% | -73.9% | +1.8% |

---

## 18. Tipologias donde SCP sigue siendo mejor

Tipologias (SERIES_CLASSIFICATION) con menor tasa de victoria ML (muestra >= 10 series):

| Categoria | N series | N clientes | Tasa victoria ML | WAPE SCP | WAPE ML | Mejora agregada | Mediana mejora |
|---|---|---|---|---|---|---|---|
| erratic_recentRelease | 68 | 4 | 27.9% | 107.5% | 123.2% | -14.6% | -12.5% |
| intermittent_recentRelease | 102 | 6 | 43.1% | 96.1% | 98.1% | -2.1% | -3.9% |
| intermittent_insuficient | 481 | 7 | 46.2% | 74.2% | 113.2% | -52.4% | +0.0% |
| lumpy_recentRelease | 30 | 4 | 46.7% | 115.2% | 111.4% | +3.3% | -3.7% |
| smooth_recentRelease | 566 | 5 | 47.2% | 18.2% | 20.1% | -10.7% | -2.1% |

---

## 19. Cobertura y exclusiones

Del universo candidato total (20.539 series), 61.6% queda fuera de comparacion en 6M. Exclusiones ML reales (HAS_ML_EXCLUDED=1) en todos los clientes: 9.007.

---

## 20. Riesgos y limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo no esta documentado y no se reconstruye (ver informes individuales).
- Los clientes no proceden necesariamente del mismo ID_BATCH ni de la misma ejecucion (ver 15_data_quality_checks).
- Modelos y clasificaciones globales se muestran unicamente para el semestre completo (6M).
- Los clientes sin ninguna serie comparable en un periodo SI se incluyen en cobertura, en calidad y en las tablas por cliente de ese periodo; unicamente quedan fuera del CALCULO de medias, medianas, WAPE, winners o mejoras de ese periodo por no tener performance calculable (ver seccion 1 y N_CLIENTES_SIN_PERFORMANCE en el Excel global). Se documentan tambien en su informe individual.
- Este analisis es retrospectivo (backtesting) y no garantiza comportamiento futuro.

---

## 21. Conclusion final

ML **no mejora** el WAPE global ponderado un -11.9% sobre el volumen total analizado en 6M. Mejora en **6 de 7 clientes con performance calculable** (mediana de mejora por cliente +3.5%), mientras que otros 2 clientes no tienen series comparables en 6M, y gana en el 53.8% de las series comparables (mediana de mejora por serie +3.5%). La cobertura efectiva es del 38.4% del universo candidato.

La reduccion neta de error absoluto es -19.668.844 (reduccion positiva total 7.369.649 frente a deterioro total absoluto 27.038.493), explicada principalmente por el deterioro concentrado en **10620_Frutas_Bollo** (ver seccion 15). Esto es coherente con que el WAPE global ponderado empeore aunque la mayoria de clientes y series mejoren: el impacto ponderado por volumen y la mejora tipica por cliente/serie responden preguntas distintas.

Estas cifras (impacto ponderado, mejora por cliente, mejora por serie, frecuencia de victoria, cobertura y concentracion) se han mantenido deliberadamente separadas a lo largo de este informe: una lectura favorable en una de ellas no implica que las demas lo sean en la misma medida.
