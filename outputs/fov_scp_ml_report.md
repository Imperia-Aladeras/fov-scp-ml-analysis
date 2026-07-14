# Comparativa de forecast SCP vs ML — Informe ejecutivo

**Fecha del analisis:** 13/07/2026
**Clientes analizados:** 10204, 10467, 10664, 10666
**Ventana evaluada:** ultimos 6 meses cerrados (M1 = mes mas reciente, M6 = mas antiguo)
**Fuente de datos:** archivo local `TA_FOV_SCP_ML_SERIES_COMPARISON_batch_62.csv` (sin conexion a base de datos, sin cambios sobre datos productivos)

---

## Resumen ejecutivo

Sobre los cuatro clientes analizados se han evaluado **12.603 series** de forecast. De ellas, **6.277 (49.8%)** tienen histórico y forecast suficientes en ambos métodos para poder compararse de forma fiable; el resto (**6.326**) queda fuera de la comparación por distintos motivos que se detallan más abajo (series nuevas, sin histórico suficiente, exclusiones del propio modelo ML, etc.).

En conjunto, **ML mejora el forecast frente a SCP**: el error ponderado (WAPE) global baja de **26.8%** con SCP a **24.1%** con ML, una mejora relativa del **9.9%**.

A nivel de series individuales, ML gana en **3.396 de 6.277 series comparables (54.1%)**, SCP gana en **2.828 (45.1%)** y hay empate técnico en **53 (0.8%)**. Es decir, la mejora de ML no es uniforme: en una parte relevante de las series SCP sigue siendo el método más preciso, y esos casos se documentan en detalle en este informe y en la pestaña `08_scp_wins_analysis` del Excel.

**Lectura para negocio:** el dato que mejor resume el valor de ML es la mejora de WAPE global ponderada por volumen de histórico (arriba), porque no se deja arrastrar por series pequeñas con errores porcentuales extremos. El recuento de series ganadas (ML vs SCP) es complementario: indica en cuántos casos concretos habría que intervenir/confiar en cada método, no cuánto pesa cada caso en el negocio.

---

## Clientes analizados y cobertura

La cobertura (qué proporción de series se puede comparar) varía por cliente. Una cobertura baja no es necesariamente un problema de ML: puede deberse a series demasiado cortas, sin histórico, o directamente fuera del alcance de ambos métodos.

| Cliente | Series candidatas | Series comparables | % comparables | No comparables | Exclusiones ML (HAS_ML_EXCLUDED=1) |
|---|---:|---:|---:|---:|---:|
| TOTAL | 12.603 | 6.277 | 49.8% | 6.326 | 5.360 (42.5%) |
| 10204 | 10.210 | 5.027 | 49.2% | 5.183 | 4.475 (43.8%) |
| 10467 | 389 | 241 | 62.0% | 148 | 89 (22.9%) |
| 10664 | 365 | 221 | 60.5% | 144 | 101 (27.7%) |
| 10666 | 1.639 | 788 | 48.1% | 851 | 695 (42.4%) |

Detalle de motivos de no comparabilidad (`COMPARISON_STATUS`), global sobre las series candidatas:

| Estado | N series | % sobre candidatas |
|---|---:|---:|
| COMPARABLE | 6.277 | 49.8% |
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 3.409 | 27.0% |
| NOT_COMPARABLE_ML_EXCLUDED | 2.205 | 17.5% |
| NOT_COMPARABLE_NO_HISTORY | 583 | 4.6% |
| NOT_COMPARABLE_MISSING_SCP | 114 | 0.9% |
| NOT_COMPARABLE_MISSING_ML | 15 | 0.1% |

**Cómo leer esta tabla:** `COMPARABLE` es la única categoría que entra en el análisis de performance. El resto son series que, por distintos motivos operativos (falta de histórico, series nuevas, exclusión explícita del motor ML, fallo del cálculo, etc.), no permiten una comparación justa entre SCP y ML y por tanto no deben usarse para argumentar a favor ni en contra de ningún método.

---

## ¿ML mejora el forecast frente a SCP?

### Impacto agregado en precisión (WAPE global ponderado)

El WAPE (error absoluto ponderado por histórico) es la métrica principal de comparación. Se calcula sumando todo el error absoluto y todo el histórico de las series comparables, para que las series con más volumen pesen más que las series pequeñas.

| Cliente | Series comparables | WAPE SCP | WAPE ML | Mejora ML vs SCP |
|---|---:|---:|---:|---:|
| TOTAL | 6.277 | 26.8% | 24.1% | 9.9% |
| 10204 | 5.027 | 35.7% | 35.5% | 0.5% |
| 10467 | 241 | 10.6% | 10.4% | 2.3% |
| 10664 | 221 | 18.0% | 17.2% | 4.2% |
| 10666 | 788 | 38.4% | 33.7% | 12.4% |

Un valor positivo en la última columna indica que ML reduce el error frente a SCP en ese cliente; un valor negativo indica que, en conjunto, ML tiene más error que SCP para ese cliente.

### Reparto de victorias por serie

| Método | N series | % sobre comparables |
|---|---:|---:|
| ML | 3.396 | 54.1% |
| SCP | 2.828 | 45.1% |
| Empate (TIE) | 53 | 0.8% |

### Magnitud de la mejora cuando ML gana

En las **3.396 series donde ML gana**, la mejora porcentual de WAPE frente a SCP tiene una **mediana de 23.1%** (media 27.2%; rango intercuartílico entre 11.2% y 39.7%). Se usa la mediana como referencia principal porque la media puede distorsionarse por series con muy poco histórico, donde pequeñas diferencias absolutas generan porcentajes de mejora muy grandes.

### Magnitud de la pérdida cuando gana SCP

En las **2.828 series donde gana SCP**, la diferencia `ML_IMPROVEMENT_VS_SCP_6M` (negativa por definición en estos casos) tiene una **mediana de -27.6%**, es decir, ML tiene un WAPE típicamente 27.6% peor que SCP en esas series. El detalle fila a fila está en la pestaña `11_top_ml_underperformance` del Excel.

---

## ¿Con qué modelos mejora ML?

Cuando ML gana, estos son los modelos que con más frecuencia resultan ganadores (`WINNER_MODEL_6M`):

| Modelo ganador | N series | % sobre victorias ML |
|---|---:|---:|
| AutoTheta | 701 | 20.6% |
| MovingAverage3M | 679 | 20.0% |
| HistoricAverage | 566 | 16.7% |
| SeasonalNaive | 523 | 15.4% |
| AutoETS | 339 | 10.0% |

El detalle completo de modelos, clasificaciones ML (`ML_CLASSIFICATION`, `ML_TYPE`) y tipología de serie (`SERIES_CLASSIFICATION`) tanto en victorias como en derrotas de ML está disponible en las pestañas `07_ml_winning_models` y `08_scp_wins_analysis` del Excel, con desglose por cliente cuando la muestra lo permite.

---

## Series que quedan fuera de la comparación

Del total de **12.603** series candidatas de los cuatro clientes, **6.326 (50.2%)** no se han podido comparar. Los motivos principales, ordenados por frecuencia, son:

| Estado (`COMPARISON_STATUS`) | N series | % sobre candidatas | Significado |
|---|---:|---:|---|
| NOT_COMPARABLE_MISSING_SCP_AND_ML | 3.409 | 27.0% | Faltan ambos forecasts (SCP y ML). |
| NOT_COMPARABLE_ML_EXCLUDED | 2.205 | 17.5% | ML excluyó explícitamente la serie (ver más abajo). |
| NOT_COMPARABLE_NO_HISTORY | 583 | 4.6% | No hay histórico útil para evaluar la serie. |
| NOT_COMPARABLE_MISSING_SCP | 114 | 0.9% | Falta el forecast de SCP. |
| NOT_COMPARABLE_MISSING_ML | 15 | 0.1% | Falta el forecast de ML. |

### Exclusiones ML en detalle

Contando el `COMPARISON_STATUS = 'NOT_COMPARABLE_ML_EXCLUDED'` hay **2.205** series marcadas como excluidas por ML. Sin embargo, ese estado sigue una **precedencia**: si una serie excluida por ML también cumple otra condición de no comparabilidad (por ejemplo, falta también el forecast de SCP), el estado principal que se le asigna puede ser otro distinto. Por eso, el recuento **real** de exclusiones ML usa el flag `HAS_ML_EXCLUDED = 1`, que asciende a **5.360 series (42.5% sobre el total de candidatas)**. La diferencia entre ambos conteos (**3.155** series) corresponde a exclusiones ML que quedan "tapadas" por otro estado con mayor precedencia, típicamente `NOT_COMPARABLE_MISSING_SCP_AND_ML`.

Motivos de exclusión ML (`ML_EXCLUSION_REASON`), sobre las filas con `HAS_ML_EXCLUDED = 1`:

| Motivo | N series | % sobre exclusiones ML |
|---|---:|---:|
| ShortSeries | 2.946 | 55.0% |
| MissingHistory | 2.249 | 42.0% |
| NewRelease | 165 | 3.1% |

**Nota:** estas exclusiones no son un fallo de ML frente a SCP — son series que el propio motor ML descarta de antemano por no cumplir los requisitos mínimos (histórico insuficiente, serie demasiado corta o de reciente creación), y por tanto no deben interpretarse como series donde "ML pierde", sino como series donde ML no llega a competir.

---

## Principales conclusiones

- ML reduce el error de forecast global un **9.9%** frente a SCP (WAPE ponderado) sobre las series comparables de los cuatro clientes analizados.
- ML gana a nivel de serie individual en el 54.1% de los casos comparables, frente al 45.1% donde gana SCP y 0.8% de empates.
- Solo el 49.8% de las series candidatas de estos cuatro clientes es comparable; cualquier conclusión sobre ML vs SCP aplica a ese subconjunto, no al universo completo.
- El modelo ganador más frecuente cuando ML gana es **AutoTheta** (701 series, 20.6%).
- Las exclusiones reales de ML (5.360 series, 42.5%) se concentran en series con histórico corto o insuficiente, no en fallos del modelo sobre series evaluables.

---

## Limitaciones del análisis

- Este análisis cubre únicamente los clientes 10204, 10467, 10664, 10666 y el batch de validación `batch_62`; no es representativo de otros clientes ni de otros periodos.
- Solo el 49.8% de las series candidatas es comparable. Las conclusiones sobre la mejora de ML no se pueden extrapolar automáticamente a las series no comparables.
- Algunas series individuales presentan WAPE extremos (cientos o miles por ciento) por tener históricos muy pequeños; se ha usado la mediana como referencia principal y se recomienda no interpretar los valores máximos sin revisar el caso concreto.
- El análisis es retrospectivo (backtesting sobre los últimos 6 meses cerrados) y no garantiza el comportamiento futuro de ML frente a SCP.
- No se dispone de contexto de negocio adicional (roturas de stock, promociones, eventos puntuales) que pueda explicar picos de error en series concretas.

- Todos los chequeos de calidad de datos aplicados sobre el subconjunto analizado han pasado sin incidencias.

---

## Anexos

- Detalle completo, desgloses por cliente y tablas de apoyo: `outputs/fov_scp_ml_summary.xlsx`.
- Gráficos de apoyo: carpeta `outputs/charts/`.
- Script de generación (reproducible): `analysis_fov_scp_ml.py`.
