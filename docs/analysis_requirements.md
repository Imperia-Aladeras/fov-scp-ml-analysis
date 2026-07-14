Quiero evolucionar el proyecto de análisis exploratorio SCP vs ML que se
encuentra en:

C:\Projects\AdhocReports\fov_scp_ml_analysis

El objetivo es convertir el análisis actual en un pipeline reproducible que:

1. Descubra automáticamente todos los CSV disponibles en `data/`.
2. Ejecute un análisis independiente para cada cliente.
3. Genere todos los resultados de cada cliente en una subcarpeta propia.
4. Analice resultados mensuales, trimestrales y semestrales.
5. Genere además una comparativa global entre clientes.
6. Construya argumentos rigurosos, claros e interpretables sobre la mejora
   de ML frente a SCP.
7. Preserve la trazabilidad de las métricas y las limitaciones del análisis.

No quiero un informe promocional. Quiero un análisis favorable a ML cuando
los datos lo respalden, pero técnicamente defendible ante Producto,
Operaciones y R&D.

# Forma de trabajo obligatoria

Trabaja por fases y no intentes implementar todo de una sola vez.

## Fase 1: inspección y diseño

En esta primera ejecución:

1. Ejecuta:
   - `git status`
   - `git branch --show-current`
   - `git rev-parse --show-toplevel`
   - `git remote -v`

2. Verifica que el repositorio es:
   `C:\Projects\AdhocReports\fov_scp_ml_analysis`

3. Verifica que estamos en la rama:
   `feature/per-client-multi-period-analysis`

4. Si no estamos en esa rama:
   - no cambies de rama automáticamente;
   - detente;
   - indícame la rama actual y el comando que debería ejecutar.

5. Inspecciona completamente:
   - `analysis_fov_scp_ml.py`
   - `descripcion.md.txt`
   - `.gitignore`
   - la estructura de `data/`
   - los nombres y columnas de todos los CSV
   - los outputs existentes
   - cualquier README, requirement o test existente

6. No modifiques ningún archivo todavía.

7. Presenta:
   - inventario de CSV;
   - cliente o clientes encontrados en cada CSV;
   - batches y runs encontrados;
   - número de filas por CSV;
   - columnas disponibles para M1...M6, RECENT_3M, OLDER_3M y 6M;
   - columnas obligatorias que falten;
   - arquitectura actual;
   - limitaciones del script actual;
   - propuesta concreta de refactor;
   - módulos o archivos que propones crear;
   - fases de implementación;
   - riesgos metodológicos detectados.

8. Detente al terminar la Fase 1 y espera mi confirmación.

No implementes las fases siguientes hasta que yo te lo indique.

## Fase 2: núcleo de carga, validación y métricas

Cuando autorice esta fase:

- implementar descubrimiento de CSV;
- validación de inputs;
- modelo de periodos;
- comparabilidad específica por periodo;
- métricas comunes;
- chequeos de calidad;
- tests unitarios del núcleo;
- sin generar todavía todos los informes finales.

Detente y muestra resultados antes de continuar.

## Fase 3: resultados individuales por cliente

Cuando autorice esta fase:

- generar Excel por cliente;
- generar Markdown por cliente;
- generar gráficos por cliente;
- organizar outputs en carpetas independientes;
- ejecutar el pipeline sobre todos los CSV;
- revisar calidad y legibilidad.

Detente y muestra resultados antes de continuar.

## Fase 4: comparativa global y acabado final

Cuando autorice esta fase:

- generar comparativa global;
- generar Excel global;
- generar Markdown global;
- generar gráficos globales;
- generar resumen de ejecución;
- actualizar README y requirements;
- ejecutar todos los tests;
- ejecutar el pipeline completo;
- proponer commits.

# Restricciones generales

- No hagas commit automáticamente.
- No hagas push.
- No cambies de rama automáticamente.
- No modifiques los CSV originales.
- No conectes con ninguna base de datos.
- No llames a APIs ni servicios externos.
- No uses rutas absolutas dentro del código.
- Trabaja únicamente dentro de este repositorio.
- Mantén compatibilidad con Windows y PowerShell.
- Usa `pathlib`.
- El punto de entrada principal debe seguir siendo:

  python analysis_fov_scp_ml.py

- Los errores de un CSV no deben impedir procesar otros CSV válidos.
- No elimines funcionalidad actual que siga siendo útil sin justificarlo.
- Reutiliza código existente cuando sea correcto, pero no mantengas una
  arquitectura monolítica únicamente por compatibilidad.

# Contexto funcional

El proyecto compara retrospectivamente dos flujos de forecast:

- SCP:
  flujo automático de forecast actualmente utilizado.

- ML:
  nuevo pipeline Optimizer/ML, que clasifica las series y selecciona entre
  diferentes modelos, incluidos baselines y modelos estadísticos.

El término ML identifica el pipeline de selección y routing. No implica que
todos los modelos seleccionados sean algoritmos de machine learning.

Cada fila del CSV representa una serie o configuración de forecast.

La métrica principal de comparación es WAPE.

Las métricas complementarias de auditoría son:

- MAE
- RMSE
- Bias
- error absoluto
- error firmado
- error cuadrático
- reducción absoluta de error

Debe distinguirse siempre entre:

- cobertura;
- precisión;
- frecuencia de victoria;
- impacto ponderado por volumen;
- mejora típica por cliente;
- mejora típica por serie.

# Inputs

La carpeta de entrada es:

data/

Actualmente existe un CSV independiente por cliente o esa es la estructura
esperada.

Ejemplos de nombres:

- `TA_FOV_SCP_ML_10204_SKLUM.csv`
- `TA_FOV_SCP_ML_10461_Garcia_Millan.csv`
- `TA_FOV_SCP_ML_10467_Embutidos_Martinez.csv`
- `TA_FOV_SCP_ML_10620_Frutas_Bollo.csv`
- `TA_FOV_SCP_ML_10664_DV_Flora.csv`
- `TA_FOV_SCP_ML_10666_Grupo_Alacant.csv`
- `TA_FOV_SCP_ML_10699_SIGMA.csv`

No hardcodes esta lista. Descubre automáticamente todos los `*.csv` de
`data/`.

Algunos clientes pueden proceder de runs fallidos, incompletos o no
comparables. No asumas que todos los CSV son válidos para un análisis de
performance.

# Identificación y validación de clientes

No dependas únicamente del nombre del archivo para identificar el cliente.

Para cada CSV:

1. Lee `ID_CLIENT` desde el contenido.
2. Comprueba cuántos clientes diferentes contiene.
3. El escenario esperado es un único `ID_CLIENT` por CSV.
4. Si contiene más de un cliente:
   - registra un ERROR;
   - muestra los IDs encontrados;
   - no mezcles los clientes silenciosamente;
   - no generes un informe como si fuera un único cliente;
   - continúa con los demás CSV cuando sea posible.

5. Extrae la etiqueta visible desde el nombre del archivo eliminando:
   - el prefijo `TA_FOV_SCP_ML_`;
   - la extensión `.csv`.

Ejemplo:

`TA_FOV_SCP_ML_10204_SKLUM.csv`
→ `10204_SKLUM`

6. Valida que el ID del nombre coincida con el `ID_CLIENT` interno.

7. Si no coinciden:
   - registra un ERROR o WARNING explícito;
   - muestra ambos valores;
   - no reasignes ni mezcles silenciosamente el archivo.

8. Si existen dos CSV para el mismo cliente:
   - no los unas silenciosamente;
   - registra el conflicto;
   - muestra los archivos implicados;
   - no dupliques el análisis.

9. Obtén del contenido:
   - `ID_BATCH`;
   - `ID_RUN_STAGING`;
   - `SOURCE_RUN_ID`;
   - cualquier información de run disponible.

No dependas del nombre del CSV para identificar batch o run.

# Granularidad y universo

El grano lógico esperado es:

ID_BATCH
+ ID_RUN_STAGING
+ ID_CLIENT
+ SOURCE_RUN_ID
+ ID_CONFIGURATION

Comprueba duplicados sobre esta clave.

El universo de cobertura debe partir de las filas candidatas base:

HAS_BASE_CANDIDATE = 1

Debe diferenciarse:

## Universo de cobertura

Todas las filas candidatas del cliente.

Se utiliza para:

- número total de series;
- porcentaje de cobertura;
- exclusiones;
- motivos de no comparabilidad;
- ausencia de forecast;
- limitaciones del pipeline.

## Universo de performance

Solo las series válidas para comparar SCP y ML en un periodo concreto.

No uses automáticamente la misma máscara para todos los periodos.

# Periodos analizados

El análisis debe realizarse para:

- `6M`
- `RECENT_3M`
- `OLDER_3M`
- `M1`
- `M2`
- `M3`
- `M4`
- `M5`
- `M6`

La convención funcional es:

- M1: primer mes evaluado dentro del cálculo retrospectivo.
- M2: segundo mes.
- M3: tercer mes.
- M4: cuarto mes.
- M5: quinto mes.
- M6: sexto mes.

Los periodos agregados son:

- `RECENT_3M` = M1 + M2 + M3
- `OLDER_3M` = M4 + M5 + M6
- `6M` = M1 + M2 + M3 + M4 + M5 + M6

# Nomenclatura visible

Mantén los nombres técnicos en:

- código;
- variables;
- estructuras internas;
- nombres de columnas;
- validaciones;
- fórmulas.

Nombres técnicos:

- RECENT_3M
- OLDER_3M
- 6M

En informes, textos, títulos y gráficos usa:

- `RECENT_3M`
  → `Primer trimestre del semestre (M1–M3)`

- `OLDER_3M`
  → `Segundo trimestre del semestre (M4–M6)`

- `6M`
  → `Semestre completo (M1–M6)`

Cuando el contexto sea evidente pueden abreviarse como:

- Primer trimestre
- Segundo trimestre
- Semestre completo

No utilices en los textos visibles:

- trimestre reciente;
- trimestre anterior;
- Q1;
- Q2;
- primer trimestre del año;
- segundo trimestre del año.

Los dos trimestres son bloques internos del semestre retrospectivo, no
trimestres naturales del calendario.

# Descubrimiento de columnas temporales

Antes de implementar, inspecciona las columnas reales del CSV.

Es probable que existan familias como:

- `HISTORY_M1...M6`
- `SCP_FORECAST_M1...M6`
- `ML_FORECAST_M1...M6`
- `SCP_ABS_ERROR_M1...M6`
- `ML_ABS_ERROR_M1...M6`
- `SCP_WAPE_M1...M6`
- `ML_WAPE_M1...M6`
- `WINNER_METHOD_M1...M6`
- `WINNER_MODEL_M1...M6`

Y agregados como:

- `TOTAL_HISTORY_6M`
- `SCP_TOTAL_ABS_ERROR_6M`
- `ML_TOTAL_ABS_ERROR_6M`
- `SCP_WAPE_6M`
- `ML_WAPE_6M`
- `WINNER_METHOD_6M`

Con equivalentes para:

- `RECENT_3M`
- `OLDER_3M`

No inventes nombres de columnas.

Construye un mapeo explícito y centralizado de periodos a columnas.

Si existen columnas agregadas:

1. utilízalas;
2. reconstruye los valores desde los meses;
3. genera chequeos de consistencia.

Si no existen columnas agregadas, pero hay datos mensuales suficientes:

1. deriva los agregados;
2. documenta claramente que son métricas calculadas;
3. no simules que proceden directamente del CSV.

Si faltan datos imprescindibles para un periodo:

- registra ERROR o WARNING según gravedad;
- no inventes resultados;
- deja el periodo como no analizable cuando corresponda.

# Comparabilidad específica por periodo

No uses únicamente:

COMPARISON_STATUS = 'COMPARABLE'

para todos los periodos.

Debes crear una máscara específica de comparabilidad para cada periodo.

Una serie será comparable para un periodo cuando:

- pertenece al universo candidato;
- tiene histórico válido para el periodo;
- dispone de error o forecast SCP suficiente;
- dispone de error o forecast ML suficiente;
- se puede calcular WAPE para ambos métodos;
- el denominador histórico es mayor que cero;
- no faltan datos esenciales del periodo.

Para `6M`:

- compara esta máscara específica con `COMPARISON_STATUS`;
- genera un chequeo de consistencia;
- documenta las discrepancias.

Para cada mes:

- no consideres comparable una fila con histórico total del mes igual a cero;
- no crees WAPE artificial;
- no crees winner cuando no existe base válida de comparación.

Para los trimestres:

- calcula la comparabilidad sobre el agregado trimestral;
- no exijas necesariamente que cada uno de los tres meses sea comparable de
  forma aislada si el agregado dispone de histórico y errores válidos;
- documenta la regla utilizada.

# Métricas por periodo

Para cada cliente y para cada periodo calcula:

## Cobertura

- series candidatas;
- series comparables;
- porcentaje comparable;
- series no comparables;
- motivos de no comparabilidad;
- exclusiones ML;
- porcentaje de exclusiones ML;
- motivos de exclusión ML;
- ausencia de forecast SCP;
- motivos de no materialización SCP;
- ausencia de forecast ML.

## WAPE agregado ponderado

SCP_WAPE_GLOBAL_PERIODO =
SUM(SCP_TOTAL_ABS_ERROR_PERIODO)
/
SUM(TOTAL_HISTORY_PERIODO)

ML_WAPE_GLOBAL_PERIODO =
SUM(ML_TOTAL_ABS_ERROR_PERIODO)
/
SUM(TOTAL_HISTORY_PERIODO)

ML_IMPROVEMENT_VS_SCP_GLOBAL_PCT =
(
  SCP_WAPE_GLOBAL_PERIODO
  - ML_WAPE_GLOBAL_PERIODO
)
/
SCP_WAPE_GLOBAL_PERIODO
* 100

Usa únicamente series comparables para ese periodo.

No calcules el WAPE agregado como media simple de los WAPE por serie.

## Reducción absoluta de error

ABS_ERROR_REDUCTION_PERIODO =
SCP_TOTAL_ABS_ERROR_PERIODO
- ML_TOTAL_ABS_ERROR_PERIODO

Interpretación:

- positivo: ML reduce error absoluto;
- negativo: ML aumenta error absoluto;
- cero: mismo error absoluto.

Incluye también la reducción absoluta total agregada.

## Mejora relativa por serie

ML_IMPROVEMENT_VS_SCP_PERIODO =
(
  SCP_WAPE_PERIODO
  - ML_WAPE_PERIODO
)
/
SCP_WAPE_PERIODO
* 100

No la calcules cuando:

- SCP_WAPE es nulo;
- ML_WAPE es nulo;
- SCP_WAPE es cero y la fórmula no es matemáticamente válida.

Gestiona y documenta específicamente:

- ambos WAPE iguales a cero;
- SCP_WAPE igual a cero y ML_WAPE mayor que cero;
- ML_WAPE igual a cero y SCP_WAPE mayor que cero.

## Estadística descriptiva de mejora

Para cada periodo calcula:

- count;
- mean;
- median;
- std;
- p10;
- p25;
- p75;
- p90;
- min;
- max;
- número inferior a -100%;
- porcentaje inferior a -100%;
- número superior a 100%;
- porcentaje superior a 100%.

Separa:

- todas las series comparables;
- series donde gana ML;
- series donde gana SCP;
- empates.

La mediana debe utilizarse como referencia principal cuando existan outliers,
pero no ocultes la media.

## Ganadores

Para cada periodo:

- número de victorias ML;
- porcentaje de victorias ML;
- número de victorias SCP;
- porcentaje de victorias SCP;
- número de empates;
- porcentaje de empates;
- modelos ganadores;
- modelos finalistas;
- mejora mediana cuando gana ML;
- deterioro mediano cuando gana SCP.

Respeta las columnas `WINNER_METHOD_*` existentes cuando sean coherentes.

Si necesitas reconstruir un winner:

- usa WAPE;
- documenta el umbral de empate;
- contrasta el resultado con las columnas de winner disponibles;
- no redefinas silenciosamente las reglas.

# Análisis de modelos

No te limites a mostrar los modelos que aparecen más veces entre las victorias.

Para cada modelo seleccionado por ML calcula:

- veces seleccionado;
- victorias ML;
- derrotas frente a SCP;
- empates;
- tasa de victoria;
- WAPE SCP agregado;
- WAPE ML agregado;
- mejora relativa agregada;
- reducción absoluta de error;
- mediana de mejora por serie;
- número de clientes en los que aparece;
- porcentaje del volumen histórico asociado.

TASA_VICTORIA_MODELO =
VICTORIAS_DEL_MODELO
/
VECES_QUE_EL_MODELO_FUE_SELECCIONADO

Distingue:

- frecuencia de selección;
- frecuencia de victoria;
- tasa de victoria;
- contribución absoluta a la reducción de error.

No interpretes automáticamente el modelo más frecuente como el modelo que más
valor aporta.

Analiza también los modelos SCP cuando SCP gana.

# Análisis de clasificaciones

Para cada periodo analiza resultados por:

- `ML_CLASSIFICATION`
- `ML_TYPE`
- `SERIES_CLASSIFICATION`
- `SCP_CLASSIFICATION`, cuando sea informativa

Para cada categoría calcula:

- series comparables;
- victorias ML;
- victorias SCP;
- empates;
- tasa de victoria ML;
- WAPE SCP agregado;
- WAPE ML agregado;
- mejora agregada;
- mediana de mejora;
- reducción absoluta de error;
- cobertura;
- clientes representados.

No generes conclusiones fuertes sobre categorías con muestras muy pequeñas.

Indica siempre el tamaño de muestra.

# Rankings por cliente

Para cada periodo genera rankings separados de:

## Impacto absoluto

- top series con mayor reducción absoluta de error;
- top series con mayor aumento absoluto de error.

## Cambio porcentual

- top series con mayor mejora porcentual;
- top series con mayor deterioro porcentual.

Incluye como mínimo:

- ID_CLIENT;
- ID_CONFIGURATION;
- niveles jerárquicos;
- histórico total del periodo;
- error absoluto SCP;
- error absoluto ML;
- reducción absoluta;
- WAPE SCP;
- WAPE ML;
- mejora relativa;
- winner;
- modelo SCP;
- modelo ML;
- clasificación.

No mezcles impacto absoluto y mejora porcentual en un único ranking.

# Análisis temporal individual

Para cada cliente analiza:

1. Semestre completo.
2. Primer trimestre del semestre.
3. Segundo trimestre del semestre.
4. M1.
5. M2.
6. M3.
7. M4.
8. M5.
9. M6.

Debe mostrarse:

- WAPE SCP y ML por periodo;
- mejora relativa;
- reducción absoluta de error;
- cobertura;
- porcentaje de victorias;
- media y mediana de mejora por serie;
- series comparables;
- volumen histórico.

Compara específicamente:

- Primer trimestre frente a Segundo trimestre.
- M1 frente a M6.
- estabilidad mensual.
- cambios de signo de la mejora.
- divergencias entre WAPE agregado y porcentaje de victorias.

La evolución temporal debe diferenciar:

- mejora ponderada por volumen;
- número de series ganadas;
- mejora típica por serie.

No concluyas que ML mejora temporalmente únicamente porque gana más series.

# Análisis global entre clientes

Además del análisis independiente por cliente, genera una comparativa global.

El análisis global debe realizarse para:

- Semestre completo.
- Primer trimestre del semestre.
- Segundo trimestre del semestre.
- M1.
- M2.
- M3.
- M4.
- M5.
- M6.

Debe presentar diferentes perspectivas, sin mezclarlas.

## Perspectiva 1: impacto global ponderado

Para cada periodo:

SCP_WAPE_GLOBAL =
SUM(SCP_TOTAL_ABS_ERROR)
/
SUM(TOTAL_HISTORY)

ML_WAPE_GLOBAL =
SUM(ML_TOTAL_ABS_ERROR)
/
SUM(TOTAL_HISTORY)

GLOBAL_IMPROVEMENT_PCT =
(
  SCP_WAPE_GLOBAL
  - ML_WAPE_GLOBAL
)
/
SCP_WAPE_GLOBAL
* 100

Esta perspectiva responde:

¿Cuánto error total reduce ML sobre el volumen total analizado?

## Perspectiva 2: mejora por cliente

Primero calcula para cada cliente y periodo:

CLIENT_IMPROVEMENT_PCT =
(
  SCP_WAPE_CLIENT
  - ML_WAPE_CLIENT
)
/
SCP_WAPE_CLIENT
* 100

Después calcula entre clientes:

- media;
- mediana;
- desviación estándar;
- p25;
- p75;
- mínimo;
- máximo;
- número de clientes con mejora;
- porcentaje de clientes con mejora;
- número de clientes con deterioro;
- porcentaje de clientes con deterioro;
- número y porcentaje de empates.

Cada cliente debe tener el mismo peso en esta perspectiva.

No ponderes la media de clientes por número de series.

## Perspectiva 3: mejora por serie

Para cada periodo:

- media de mejora por serie;
- mediana de mejora por serie;
- p25;
- p75;
- porcentaje de series ganadas por ML;
- porcentaje de series ganadas por SCP;
- porcentaje de empates;
- distribución de mejoras;
- distribución de deterioros.

## Perspectiva 4: impacto absoluto

Para cada periodo:

- reducción absoluta total de error;
- contribución absoluta de cada cliente;
- porcentaje de la mejora total aportado por cada cliente;
- clientes que generan deterioro;
- concentración de la mejora.

Calcula, cuando sea matemáticamente válido:

CLIENT_CONTRIBUTION_TO_TOTAL_REDUCTION =
CLIENT_ABS_ERROR_REDUCTION
/
TOTAL_ABS_ERROR_REDUCTION
* 100

No ocultes cuando la mejora global depende principalmente de uno o pocos
clientes.

# Tabla global por cliente

Para cada periodo genera una tabla con una fila por cliente y, al menos:

- ID_CLIENT;
- etiqueta de cliente;
- CSV;
- batch;
- run;
- series candidatas;
- series comparables;
- cobertura;
- histórico total;
- error absoluto SCP;
- error absoluto ML;
- reducción absoluta;
- WAPE SCP;
- WAPE ML;
- mejora relativa;
- porcentaje de victorias ML;
- porcentaje de victorias SCP;
- porcentaje de empates;
- media de mejora por serie;
- mediana de mejora por serie;
- exclusiones ML;
- warnings de calidad.

# Objetivo interpretativo del informe global

El informe debe responder con claridad:

1. ¿Mejora ML el error total agregado?
2. ¿Mejora ML en la mayoría de clientes?
3. ¿Mejora el cliente mediano?
4. ¿Mejora ML en la mayoría de series?
5. ¿La mejora se mantiene en ambos trimestres?
6. ¿La mejora se mantiene mes a mes?
7. ¿Qué clientes explican la mejora?
8. ¿Qué modelos explican la mejora?
9. ¿Dónde sigue siendo superior SCP?
10. ¿Qué porcentaje del universo queda fuera de comparación?
11. ¿Qué limitaciones de cobertura tiene ML?
12. ¿La mejora está concentrada en pocos casos de gran volumen?

Distingue siempre:

- impacto global ponderado;
- mejora media por cliente;
- mejora mediana por cliente;
- comportamiento medio por serie;
- comportamiento mediano por serie;
- frecuencia de victoria;
- reducción absoluta;
- cobertura.

# Estructura de outputs

No dejes informes individuales o gráficos sueltos en la raíz de `outputs/`.

La estructura debe ser:

outputs/
  10204_SKLUM/
    fov_scp_ml_report_10204_SKLUM.md
    fov_scp_ml_summary_10204_SKLUM.xlsx
    processing_log_10204_SKLUM.txt
    charts/
      coverage/
      semester/
      quarters/
      monthly/
      models/
      classifications/
      impact_and_risk/

  10461_Garcia_Millan/
    ...

  10467_Embutidos_Martinez/
    ...

  global/
    fov_scp_ml_global_report.md
    fov_scp_ml_global_summary.xlsx
    charts/
      coverage/
      semester/
      quarters/
      monthly/
      clients/
      models/
      classifications/
      impact_and_risk/

  execution_summary.md
  execution_summary.xlsx

La carpeta individual debe derivarse del nombre del CSV una vez validado el
`ID_CLIENT`.

Normaliza caracteres incompatibles con rutas de Windows.

Conserva guiones bajos para mantener nombres estables.

# Excel individual por cliente

Cada cliente debe generar un Excel con al menos:

- `00_readme`
- `01_executive_summary`
- `02_coverage_status`
- `03_semester`
- `04_first_quarter`
- `05_second_quarter`
- `06_monthly_summary`
- `07_monthly_winners`
- `08_models_and_win_rates`
- `09_classifications`
- `10_exclusions`
- `11_top_absolute_impact`
- `12_top_percentage_changes`
- `13_data_quality_checks`

## 00_readme

Debe explicar:

- fuente;
- cliente;
- batch;
- run;
- fecha;
- granularidad;
- universos;
- periodos;
- nombres técnicos y visibles;
- fórmulas;
- reglas de comparabilidad;
- reglas de winner;
- limitaciones.

## 01_executive_summary

Debe contener una tabla compacta con una fila por periodo:

- Semestre completo.
- Primer trimestre.
- Segundo trimestre.
- M1.
- M2.
- M3.
- M4.
- M5.
- M6.

Columnas mínimas:

- series candidatas;
- series comparables;
- cobertura;
- histórico;
- WAPE SCP;
- WAPE ML;
- mejora relativa;
- reducción absoluta;
- porcentaje gana ML;
- porcentaje gana SCP;
- porcentaje empate;
- media de mejora por serie;
- mediana de mejora por serie.

# Excel global

Debe incluir al menos:

- `00_readme`
- `01_executive_summary`
- `02_client_coverage`
- `03_semester_by_client`
- `04_first_quarter_by_client`
- `05_second_quarter_by_client`
- `06_monthly_by_client`
- `07_global_period_summary`
- `08_client_improvement_stats`
- `09_series_improvement_stats`
- `10_winner_distribution`
- `11_models_and_win_rates`
- `12_classifications`
- `13_absolute_impact`
- `14_exclusions`
- `15_data_quality_checks`

En `07_global_period_summary` debe existir una fila por periodo y columnas
para:

- histórico total;
- error absoluto SCP;
- error absoluto ML;
- reducción absoluta;
- WAPE SCP;
- WAPE ML;
- mejora global ponderada;
- media de mejora por cliente;
- mediana de mejora por cliente;
- desviación entre clientes;
- media de mejora por serie;
- mediana de mejora por serie;
- porcentaje de clientes donde mejora ML;
- porcentaje de series donde gana ML;
- cobertura.

# Formato Excel

Aplica:

- filtros automáticos;
- freeze panes;
- porcentajes con formato coherente;
- números con separadores;
- anchos de columna razonables;
- encabezados legibles;
- títulos visibles;
- jerarquía visual sencilla;
- colores discretos;
- no crear hojas redundantes.

No conviertas el Excel en un dashboard excesivamente complejo.

Prioriza claridad y auditabilidad.

# Informe Markdown individual

Cada cliente debe incluir:

1. Resumen ejecutivo.
2. Cobertura.
3. Semestre completo.
4. Primer trimestre.
5. Segundo trimestre.
6. Comparación entre trimestres.
7. Evolución mensual.
8. Frecuencia de victoria.
9. Impacto absoluto.
10. Modelos ML.
11. Modelos SCP.
12. Clasificaciones.
13. Exclusiones.
14. Casos de mayor mejora.
15. Casos de mayor deterioro.
16. Riesgos.
17. Limitaciones.
18. Conclusión.

La conclusión debe diferenciar:

- mejora global ponderada;
- mejora típica por serie;
- frecuencia de victoria;
- cobertura.

# Informe Markdown global

Debe incluir:

1. Resumen ejecutivo.
2. Clientes analizados.
3. Calidad y cobertura de los inputs.
4. Resultado del semestre completo.
5. Resultado del primer trimestre.
6. Resultado del segundo trimestre.
7. Comparación entre trimestres.
8. Evolución mensual.
9. WAPE global ponderado.
10. Media de mejora por cliente.
11. Mediana de mejora por cliente.
12. Media y mediana por serie.
13. Clientes donde mejora ML.
14. Clientes donde empeora.
15. Concentración de la mejora.
16. Modelos que más aportan.
17. Clasificaciones donde funciona mejor ML.
18. Tipologías donde SCP sigue siendo mejor.
19. Cobertura y exclusiones.
20. Riesgos y limitaciones.
21. Conclusión final.

El informe global debe ser exhaustivo pero sencillo.

No repitas la misma conclusión en varias secciones.

No acumules métricas sin explicar qué pregunta responde cada una.

# Gráficos individuales

Para cada cliente genera como mínimo:

## Cobertura

- distribución de `COMPARISON_STATUS`;
- cobertura por periodo;
- motivos de exclusión ML;
- motivos de ausencia SCP.

## Semestre

- WAPE SCP vs ML;
- winner distribution;
- distribución de mejora por serie;
- reducción absoluta;
- modelos y tasa de victoria.

## Trimestres

- WAPE del Primer trimestre;
- WAPE del Segundo trimestre;
- mejora comparativa;
- ganadores comparados;
- reducción absoluta comparada.

## Mensual

- evolución WAPE SCP y ML M1...M6;
- evolución de mejora relativa;
- evolución de reducción absoluta;
- porcentaje de victorias ML/SCP/TIE;
- cobertura mensual.

## Impacto y riesgo

- top reducciones absolutas;
- top aumentos absolutos;
- top mejoras porcentuales;
- top deterioros porcentuales.

# Gráficos globales

Genera como mínimo:

- cobertura por cliente;
- WAPE semestral por cliente;
- mejora semestral por cliente;
- reducción absoluta por cliente;
- media y mediana de mejora por cliente;
- Primer trimestre vs Segundo trimestre;
- evolución mensual global;
- evolución mensual por cliente;
- porcentaje de clientes donde mejora ML por periodo;
- porcentaje de series donde gana ML por periodo;
- contribución de cada cliente a la reducción absoluta;
- modelos y tasa de victoria;
- clasificaciones;
- distribución global de mejora.

# Reglas de visualización

- ML: azul.
- SCP: rojo.
- Empate: gris.
- Mantén colores coherentes en todos los gráficos.
- No cortes títulos.
- Incluye tamaño de muestra.
- Incluye periodo.
- Incluye cliente cuando sea individual.
- Cierra todas las figuras.
- No acumules memoria.
- No recortes valores extremos silenciosamente.
- Si un histograma se limita a ±100%:
  - indícalo en el título o subtítulo;
  - muestra cuántos valores quedan por debajo;
  - muestra cuántos quedan por encima;
  - conserva las estadísticas sin recorte.

# Chequeos de calidad

Implementa chequeos con niveles:

- OK
- WARNING
- ERROR

Un ERROR invalida el cliente o periodo afectado.

Un WARNING permite continuar, pero debe aparecer en:

- log;
- Excel;
- informe;
- resumen de ejecución.

Incluye como mínimo:

1. CSV legible.
2. Columnas obligatorias.
3. Tipos de datos.
4. Un único cliente por CSV.
5. Coincidencia entre nombre de archivo e `ID_CLIENT`.
6. Duplicados por clave lógica.
7. Unicidad de cliente.
8. Batches detectados.
9. Runs detectados.
10. Coherencia de histórico 6M con M1...M6.
11. Coherencia de Primer trimestre con M1+M2+M3.
12. Coherencia de Segundo trimestre con M4+M5+M6.
13. Coherencia de errores absolutos agregados.
14. Reconstrucción de error absoluto desde forecast e histórico.
15. Reconstrucción de WAPE.
16. Winner coherente con el menor WAPE.
17. Empates coherentes con el umbral.
18. Métricas nulas cuando histórico es cero.
19. Forecasts nulos cuando flags indican ausencia.
20. Exclusiones ML con motivo.
21. Valores negativos de histórico.
22. Valores negativos de forecast, diferenciando si son permitidos.
23. WAPE extremo.
24. Mejora extrema.
25. `COMPARISON_STATUS` frente a comparabilidad específica 6M.
26. Series comparables sin winner.
27. Series comparables sin forecasts.
28. Totales agregados frente a sumas mensuales.

Usa tolerancias numéricas razonables.

Documenta las tolerancias.

No afirmes que la calidad de datos está validada únicamente porque han pasado
controles estructurales.

# Logging

Genera un log por cliente con:

- timestamp;
- archivo;
- cliente;
- batch;
- run;
- fase;
- periodo;
- filas;
- warnings;
- errores;
- duración;
- outputs generados.

El log general debe permitir entender qué ocurrió sin abrir el código.

# Resumen de ejecución

Genera:

- `outputs/execution_summary.md`
- `outputs/execution_summary.xlsx`

Debe contener una fila por CSV con:

- archivo;
- carpeta de salida;
- ID_CLIENT;
- etiqueta;
- batch;
- run;
- filas;
- candidatas;
- comparables 6M;
- estado;
- warnings;
- errores;
- duración;
- informe generado;
- Excel generado;
- gráficos generados.

Estados posibles:

- SUCCESS
- SUCCESS_WITH_WARNINGS
- SKIPPED
- ERROR

# Arquitectura del código

Refactoriza en funciones pequeñas.

Puedes crear módulos auxiliares si mejora la mantenibilidad.

Una estructura posible, no obligatoria, sería:

- `analysis_fov_scp_ml.py`
- `src/input_loader.py`
- `src/periods.py`
- `src/metrics.py`
- `src/quality_checks.py`
- `src/client_analysis.py`
- `src/global_analysis.py`
- `src/excel_writer.py`
- `src/report_writer.py`
- `src/charts.py`
- `src/models.py`
- `tests/`

No introduzcas una arquitectura compleja sin necesidad.

El script principal debe coordinar:

1. descubrimiento;
2. validación;
3. análisis por cliente;
4. outputs individuales;
5. agregación global;
6. outputs globales;
7. resumen de ejecución.

# Tests

Añade tests unitarios, como mínimo, para:

- descubrimiento de CSV;
- detección de múltiples clientes;
- validación de nombre vs ID;
- detección de cliente duplicado;
- mapeo de periodos;
- Primer trimestre = M1+M2+M3;
- Segundo trimestre = M4+M5+M6;
- Semestre = M1...M6;
- WAPE agregado;
- mejora relativa;
- reducción absoluta;
- comparabilidad mensual;
- comparabilidad trimestral;
- comparabilidad semestral;
- histórico cero;
- SCP_WAPE cero;
- winner;
- empate;
- agregación global;
- media por cliente;
- mediana por cliente;
- contribución absoluta por cliente.

Usa datos sintéticos pequeños en tests.

No dependas de los CSV reales para todos los tests unitarios.

# Reproducibilidad

Añade o actualiza:

- `README.md`
- `requirements.txt` o `pyproject.toml`
- instrucciones de instalación;
- instrucciones de ejecución;
- estructura de `data/`;
- estructura de `outputs/`;
- convenciones M1...M6;
- nombres técnicos y visibles;
- fórmulas;
- reglas de comparabilidad;
- chequeos;
- ejecución de tests.

Mantén la instalación sencilla.

# Rendimiento

El cliente 10204 puede contener un volumen considerable de filas.

Evita:

- bucles fila a fila innecesarios;
- copias completas repetidas;
- DataFrames duplicados sin necesidad;
- figuras abiertas;
- escritura redundante del mismo bloque.

Usa operaciones vectorizadas.

Procesa clientes secuencialmente para controlar memoria.

Libera objetos grandes cuando finalice cada cliente si es necesario.

# Criterios de interpretación

La redacción debe ser prudente y basada en datos.

No afirmes:

“ML mejora de forma generalizada”

solo porque mejora el WAPE global.

Comprueba también:

- cuántos clientes mejoran;
- mediana por cliente;
- cuántas series mejoran;
- mediana por serie;
- ambos trimestres;
- evolución mensual;
- concentración por volumen;
- cobertura.

Una conclusión favorable debería poder expresarse en términos como:

“ML reduce el error global ponderado, mejora en X de Y clientes y presenta una
mediana de mejora por cliente de Z%, aunque el beneficio está concentrado en
determinados clientes o tipologías.”

Cuando SCP sea mejor en una parte relevante de los casos, indícalo.

El objetivo es construir argumentos sólidos de mejora de ML frente a SCP,
pero no ocultar:

- heterogeneidad;
- pérdidas;
- exclusiones;
- falta de cobertura;
- concentración;
- outliers;
- limitaciones de muestra.

# Entrega final

Al terminar cada fase:

1. Resume los cambios.
2. Muestra archivos creados o modificados.
3. Muestra tests ejecutados.
4. Muestra el resultado de ejecución.
5. Muestra warnings y errores.
6. Muestra `git diff --stat`.
7. No hagas commit.
8. No hagas push.

Al terminar la Fase 4:

1. Ejecuta todos los tests.
2. Ejecuta:
   `python analysis_fov_scp_ml.py`
3. Procesa todos los CSV.
4. Verifica todos los outputs.
5. Resume:
   - clientes procesados;
   - clientes omitidos;
   - errores;
   - warnings;
   - resultados generados;
   - decisiones metodológicas;
   - limitaciones.
6. Propón una secuencia pequeña y lógica de commits.
7. No hagas los commits.
8. No hagas push.