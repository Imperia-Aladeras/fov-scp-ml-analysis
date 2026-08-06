# Plan técnico: adaptación del reporting al CSV completo multi-cliente de `TA_FOV_SCP_ML_SERIES_COMPARISON`

> Este documento es un plan. No describe un comportamiento ya implementado.
> Ninguna de las secciones siguientes ha sido codificada; el pipeline actual
> (`analysis_fov_scp_ml.py`, `src/*`) sigue operando exactamente como se
> describe en [`docs/reporting-flow.md`](reporting-flow.md) y
> [`docs/backend-validation-flow.md`](backend-validation-flow.md), documentos
> que son la base factual de este plan.

## 5.1 Resumen ejecutivo

**Limitación actual.** El reporting solo acepta un CSV por cliente
(`analysis_fov_scp_ml.py` → `src/input_loader.py`). Si un CSV contiene más de
un `ID_CLIENT`, `quality_checks.check_single_client` lo marca
`MULTIPLE_CLIENTS_IN_CSV` (ERROR de fichero) y el fichero completo queda
inválido: no se calcula ningún periodo, no se genera Excel/Markdown/PNG, y el
cliente no participa en absoluto en la comparativa global. El flujo real y
definitivo de backend a reporting (ver
[`docs/backend-validation-flow.md`](backend-validation-flow.md), sección
"Frontera de entrega al proyecto de reporting") entrega, en cambio, **un único
CSV** con la exportación completa de `TA_FOV_SCP_ML_SERIES_COMPARISON`, que
por construcción puede — y normalmente va a — contener varios `ID_CLIENT`
(porque `start-multi` admite hasta 10 clientes por solicitud y una campaña
puede requerir varias llamadas).

**Comportamiento objetivo.** El pipeline debe aceptar ese único CSV completo,
cargarlo una única vez, particionarlo internamente por `ID_CLIENT`, y producir
exactamente los mismos artefactos que hoy (Excel/Markdown/PNG/HTML por
cliente, comparativa global, manifest, catálogo de runs), sin que el usuario
tenga que dividir manualmente el fichero.

**Decisiones ya cerradas** (no se replantean en este documento; ver también
la sección 5.18 "Preguntas abiertas", que confirma que ninguna decisión aquí
cerrada queda pendiente de resolución):

- No hay conexión SQL, API de transferencia, ETL compartido ni integración
  automática entre `scp-backend` y este repositorio. El único intercambio es
  el CSV completo copiado manualmente en `data/`.
- La identidad canónica del cliente es `ID_CLIENT`; el nombre descriptivo
  (`config/client-catalog.json`, ver sección 5.7) es solo una etiqueta de
  presentación, nunca una clave de agrupación.
- Varios `ID_BATCH` en el mismo CSV son válidos cuando corresponden a
  clientes diferentes, pero para un mismo `ID_CLIENT` debe existir siempre
  una única combinación `(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID)`; más de
  una combinación es siempre un conflicto estructural que detiene el run
  completo, sin excepciones ni heurísticas de selección (sección 5.6).
- Para 6M, la población comparable se filtra realmente con
  `COMPARISON_STATUS == 'COMPARABLE'` (referencia canónica del backend); la
  máscara propia de `client_analysis.period_comparable_mask` pasa a ser una
  auditoría de discrepancias, no el universo analítico (sección 5.10).
- `WINNER_IMPROVEMENT_PCT_*` (ganador vs. finalista, backend) y la mejora
  ML‑vs‑SCP recalculada por reporting (`src/metrics.relative_improvement_row`)
  son dos métricas distintas que deben coexistir con nombres inequívocos, sin
  recalcular nunca `WINNER_IMPROVEMENT_PCT` (sección 5.11).
- El contrato actual de 234 columnas no permite verificar la ventana
  calendario M1-M6 entre ejecuciones. Se ha decidido solicitar al backend
  que añada `RUN_START_DATE` a `TA_FOV_SCP_ML_SERIES_COMPARISON` y a la
  exportación CSV como prerrequisito (Fase 0, sección 5.16); `COPIED_AT` no
  se usa como aproximación bajo ninguna circunstancia (sección 5.6).
- Las reglas de descubrimiento de CSV (cuántos ficheros directos se admiten y
  bajo qué condiciones) están cerradas y no requieren un flag de CLI nuevo
  (sección 5.4).
- `config/client-catalog.json` es el catálogo definitivo (228 entradas,
  depurado manualmente); no está pendiente de limpieza ni de sustitución
  (sección 5.7).
- La estructura de publicación (`outputs/runs/<run-name>/`, publicación
  transaccional, HTML global + por cliente, Excel, Markdown, PNG, manifest,
  logs, catálogo de runs, funcionamiento 100% offline) se mantiene tal cual.

**Resultado esperado.** Un `--input-dir` con un único CSV multi-cliente
produce el mismo tipo de run publicado que hoy produce un `--input-dir` con
varios CSV de un cliente cada uno: una página HTML global, una página HTML por
`ID_CLIENT`, Excel/Markdown/PNG por cliente, comparativa global sobre todos
los clientes válidos, manifest con trazabilidad completa (incluida la del
catálogo de nombres) y catálogo de runs sin cambios de contrato.

**Fuera de alcance.** Selección automática de "el batch más reciente",
conexión a staging o a otras tablas del backend, división manual del CSV,
consumo del catálogo de clientes en tiempo real vía HTTP, resolución
automática de conflictos de ejecución lógica duplicada (deben detener el run
explícitamente, no resolverse por heurística), y cualquier cambio a la
fórmula de empate/mejora del backend (solo se documenta la reconciliación,
no se reimplementa la fórmula).

## 5.2 Estado actual confirmado

Todas las afirmaciones de esta sección fueron verificadas sobre la rama
`feature/per-client-multi-period-analysis`, tomando como referencia el
estado del repositorio en el commit `260d427`. Coinciden con lo ya
documentado en `docs/reporting-flow.md`.

**Descubrimiento de CSV.** `src/input_loader.discover_csv_files(data_dir)`
(línea 111) ejecuta `sorted(data_dir.glob("*.csv"))`: únicamente hijos
directos de `data_dir`, nunca recursivo, sin nombre fijo ni prioridad. El
default de `--input-dir` es `<repo>/data` (`src/run_config.build_arg_parser`,
línea ~100).

**Carga.** `src/input_loader.read_csv_defensive(path)` (línea 225) intenta una
lectura estándar (`utf-8-sig`, delimitador coma) y, si falla, repara CSV
envueltos en comillas dobladas en memoria (`unwrap_double_quoted_line`, línea
145), sin tocar nunca el fichero original. `_load_single_source(path)` (línea
332) construye un único `ClientSource` por fichero: valida columnas
(`quality_checks.check_required_columns` contra
`periods.all_required_columns()`, 234 columnas), coacciona tipos numéricos
(`coerce_numeric_columns`), y determina `id_client` a partir de los valores
únicos de `ID_CLIENT` en el DataFrame completo del fichero.

**Dónde se rechaza `MULTIPLE_CLIENTS_IN_CSV`.**
`src/quality_checks.check_single_client(file_label, df, id_column="ID_CLIENT")`
(línea 149-157): si `df["ID_CLIENT"].dropna().unique()` tiene más de un valor,
devuelve un `QualityIssue(Severity.ERROR, "MULTIPLE_CLIENTS_IN_CSV", ...)`.
`_load_single_source` (línea 361-362) añade ese issue al `QualityReport` del
`ClientSource`; como es `ERROR`, `source.is_valid` queda `False` (línea 389) y
`client_analysis.analyze_client` (línea 354-357) devuelve inmediatamente
`ClientAnalysisResult(file_valid=False, status="ERROR", periods={})` sin
calcular ningún periodo.

**Cómo se crea `ClientSource`.** Dataclass en `src/input_loader.py` (línea
311-329): `csv_path`, `file_label` (derivado del **nombre de fichero**, no de
una columna), `id_from_filename`, `dataframe`, `read_repaired`, `id_client`,
`id_batch`/`id_run_staging`/`source_run_id` (listas de valores únicos vistos
en el fichero), `n_rows`, `quality`, `is_valid`, `folder_name`. La relación
actual es **1 fichero físico → 1 `ClientSource` → 1 cliente**.

**Cómo se obtiene el nombre del cliente hoy.**
`extract_label_from_filename(path)` (línea 116-126) quita el prefijo
`TA_FOV_SCP_ML_` y la extensión `.csv` del **nombre de fichero**:
`TA_FOV_SCP_ML_10204_SKLUM.csv` → `10204_SKLUM`. No existe ninguna columna de
nombre de cliente en el contrato de 234 columnas
(`periods.STATIC_REQUIRED_COLUMNS`); el nombre nunca sale del contenido del
CSV. `folder_name = normalize_folder_name(file_label)` (línea 138-142)
sustituye caracteres prohibidos en Windows.

**Cómo se construye el análisis global.**
`src/global_analysis.analyze_global(all_results)` (línea 285-300) filtra
`r.file_valid and r.source.dataframe is not None` para obtener
`valid_results`, y sobre esa lista construye las 4 perspectivas
(`build_global_period_result` por periodo, línea 177-207) y
`client_period_tables` (una tabla por periodo con una fila por cliente,
`build_client_period_table`, línea 210-246). El único filtro es la validez
del fichero; no hay selección por batch/run.

**Cómo se construyen los análisis por cliente.**
`src/client_analysis.analyze_client(source)` (línea 341-395) recibe **un**
`ClientSource` y devuelve **un** `ClientAnalysisResult` con 9 `PeriodResult`
(`_analyze_period`, línea 196-297): `candidate_mask = df["HAS_BASE_CANDIDATE"]
== 1`, luego `period_comparable_mask` (línea 136-155, máscara propia por
periodo) para cada uno de `periods.ALL_PERIODS`.

**Cómo se publican los outputs.**
`analysis_fov_scp_ml._generate_client_outputs` (línea 113-145) escribe en
`clients_dir / source.folder_name /`: Excel (`excel_writer.build_client_workbook`),
Markdown (`report_writer.build_client_report`), PNG
(`charts.generate_client_charts`), log
(`logging_utils.build_processing_log`). `_generate_global_outputs` (línea
148-162) escribe en `global_dir /`. Todo ocurre dentro de
`run_config.run_dir_temp`; `src/run_publish.publish_run` (línea 176-219) hace
el rename atómico a `run_dir_final` solo cuando todo el pipeline ha terminado
con éxito.

**Cómo se generan manifest y logs.**
`src/manifest.build_manifest` (línea 123-210) construye
`by_filename = {r.source.file_name: r for r in results}` (línea 139) — **una
entrada de `csv_files` por cada fichero físico del inventario**, correlacionada
1:1 con, como mucho, un `ClientAnalysisResult`. `execution_summary.build_execution_records`
(línea 50-109) hace exactamente la misma correlación 1:1 por
`record.name` (nombre de fichero). Esta correlación **1 fichero → 1 resultado**
es la pieza que más cambia con un CSV multi-cliente (ver sección 5.5).

**Cómo se determina la comparabilidad.**
`period_comparable_mask(df, pcols, candidate_mask)` (client_analysis.py:136)
NO usa `COMPARISON_STATUS`: exige `candidate_mask` (`HAS_BASE_CANDIDATE==1`),
histórico del periodo > 0, y forecast/error-absoluto/WAPE no nulos para SCP y
ML en ese periodo. Solo para `6M`, `check_comparison_status_vs_period_mask`
(client_analysis.py:279-280, quality_checks.py:400-422) **audita** — no
sustituye — la discrepancia frente a `COMPARISON_STATUS=='COMPARABLE'`. Este
comportamiento cambia de forma funcional en el diseño objetivo (sección
5.10): para 6M, `COMPARISON_STATUS=='COMPARABLE'` pasará a ser el filtro real.

**Cómo se calcula la mejora.**
`src/metrics.relative_improvement_row(scp_wape, ml_wape)` (línea 114-146)
calcula `(SCP_WAPE - ML_WAPE) / SCP_WAPE * 100` fila a fila, con casos
especiales documentados (`CASE_BOTH_ZERO`, `CASE_SCP_ZERO_ML_POSITIVE`,
`CASE_ML_ZERO_SCP_POSITIVE`). `period_wape_global` (línea 31-61) calcula la
misma fórmula sobre agregados (`SUM(abs_error)/SUM(historico)`), nunca sobre
un `WINNER_IMPROVEMENT_PCT_*` del CSV, que se coacciona a numérico pero no se
usa analíticamente (ver `docs/reporting-flow.md`, tabla de la sección 21.2).

**Cómo se gestionan batches y runs actualmente.**
`ClientSource.id_batch` / `id_run_staging` / `source_run_id` (input_loader.py,
`_load_single_source`, línea 376-379) solo **recolectan** los valores únicos
vistos en el fichero de ese cliente; no filtran ni seleccionan filas.
`check_batch_heterogeneity` (quality_checks.py:673-692) es un chequeo
**global entre ficheros distintos** (clientes distintos con `ID_BATCH`
distintos): un WARNING informativo, nunca bloqueante. No existe ningún
chequeo hoy que detecte dos ejecuciones lógicas **del mismo cliente** dentro
del mismo fichero (ver sección 5.6): con un único CSV por cliente eso nunca
podía ocurrir dentro de un fichero, así que el caso nunca se implementó.

## 5.3 Diseño objetivo

```text
data/<full-export>.csv (o CSV legacy admitidos, ver sección 5.4)
  -> inventario y hash (src/input_inventory.build_input_inventory, sin cambios: sigue operando por fichero físico)
  -> clasificación del escenario de entrada (nueva: 0/1/N CSV, full-export vs. legacy, ver sección 5.4)
  -> carga física única por CSV admitido (nueva: input_loader debe leer cada CSV completo UNA vez)
  -> validación del esquema (sin cambios de mecanismo: quality_checks.check_required_columns, aplicado al DataFrame completo de cada CSV)
  -> validación de ejecución lógica por ID_CLIENT (nueva, ver sección 5.6; la comprobación de ventana temporal queda bloqueada hasta Fase 0 / RUN_START_DATE)
  -> agrupación lógica por ID_CLIENT (nueva: groupby en memoria, sin releer el CSV)
  -> resolución opcional del nombre (nueva: config/client-catalog.json, ver sección 5.7)
  -> análisis por cliente (sin cambios de fondo: client_analysis.analyze_client sigue operando sobre un DataFrame de un único cliente; cambia el universo comparable de 6M, ver sección 5.10)
  -> análisis global (sin cambios de fondo: global_analysis.analyze_global sigue operando sobre client_results validos)
  -> publicación transaccional (sin cambios: run_publish.publish_run es agnóstico al número de clientes; un error estructural de scope/esquema/ventana detiene el run ANTES de llegar aquí, ver sección 5.8)
```

Distinción explícita de conceptos, porque hoy están implícitamente fusionados
en `ClientSource` (1 fichero = 1 cliente) y deben separarse:

| Concepto | Hoy | Objetivo |
|---|---|---|
| Archivo físico de entrada | 1 CSV = 1 cliente | 1 CSV completo = N clientes, o varios CSV legacy admitidos bajo las condiciones de la sección 5.4; sigue habiendo 1 `InputFileRecord` por fichero |
| Dataset global | Concatenación implícita de N ficheros | Un único DataFrame en memoria por CSV completo, particionado lógicamente |
| Partición lógica por cliente | `ClientSource` = fichero | `ClientSource`-equivalente = subconjunto de filas del DataFrame único, filtrado por `ID_CLIENT` |
| Metadata del cliente | `id_client`, `file_label` (del nombre de fichero) | `id_client` (del contenido, como hoy) + nombre resuelto vía catálogo opcional |
| Metadata del batch/run | Recolectada sin validar (listas) | Recolectada y **validada** por cliente: exactamente una combinación batch/run/source-run, sin excepciones (sección 5.6) |
| Resultados globales | `GlobalAnalysisResult` sobre `client_results` | Sin cambio de forma; cambia solo el origen de `client_results` |
| Resultados por cliente | `ClientAnalysisResult` por fichero | `ClientAnalysisResult` por partición lógica (misma forma) |

## 5.4 Descubrimiento del CSV

Reglas definitivas (cerradas; no quedan opciones a evaluar):

| Escenario | Comportamiento objetivo |
|---|---|
| `data/` sin CSV directos | Error. Igual que hoy: `run_pipeline` falla con `ERROR: no se ha encontrado ningún CSV`, manifest `FAILED`, código de salida `1` (`analysis_fov_scp_ml.py`, línea 472-487). Sin cambios. |
| Exactamente **1** CSV directo en `data/` | Es la operación estándar prevista. Se procesa siempre como carga física única y partición interna por `ID_CLIENT`: el CSV puede contener uno o varios `ID_CLIENT`, y ambos casos se tratan con el mismo camino de código (una partición con un único grupo es indistinguible, en resultado, del modo histórico actual). |
| **Varios** CSV directos en `data/` | Solo se admite temporalmente como **modo histórico** si se cumplen **las cuatro condiciones siguientes simultáneamente**: (1) cada CSV contiene exactamente un `ID_CLIENT`; (2) ningún `ID_CLIENT` se repite entre archivos; (3) todos los CSV comparten el mismo esquema de columnas; (4) todos comparten la misma ventana temporal. Si **cualquiera** de las cuatro condiciones no se cumple, es un error de configuración que detiene el run completo (ver sección 5.8). Esta clasificación es el diseño objetivo de Fase 2; su implementación está bloqueada por Fase 0, ver la nota siguiente. |
| Mezcla de un CSV multi-cliente (más de un `ID_CLIENT`) con cualquier otro CSV directo | Error. No se combinan formatos distintos en el mismo run. |
| Varios CSV directos, y más de uno de ellos contiene múltiples `ID_CLIENT` | Error. No se admiten dos (o más) CSV multi-cliente completos en la misma carpeta de entrada. |
| CSV históricos en subcarpetas (`data/exportacion_*/`) | Sin cambios: `discover_csv_files` sigue sin ser recursivo; no se descubren automáticamente. Coherente con el comportamiento actual documentado en `docs/reporting-flow.md` sección 7.1. |
| Ruta explícita por CLI | `--input-dir` ya existe y sigue funcionando igual: apunta a la carpeta cuyos CSV directos se evalúan con las reglas de esta tabla. |
| Archivo temporal / exportación antigua | Si convive con otros CSV directos en `data/`, se evalúa con las mismas reglas (número de `ID_CLIENT` por fichero, solapes, esquema, ventana); no se elige arbitrariamente. |

**No se selecciona ningún archivo arbitrariamente** en ningún escenario. **No
se añade por ahora ningún flag de CLI nuevo** para seleccionar modo: la
clasificación del escenario (full-export vs. legacy vs. error) se determina
únicamente a partir del número de CSV directos descubiertos y de su
contenido (`ID_CLIENT` por fichero, esquema, ventana), leído de todas formas
durante la carga.

**Fase 0 es un prerrequisito bloqueante para esta tabla.** El contrato
actual (234 columnas) no contiene ninguna columna de fecha calendario (ver
sección 5.6), por lo que la condición (4) —misma ventana temporal— no puede
verificarse de forma fiable hasta que Fase 0 entregue `RUN_START_DATE`
(sección 5.16). Esto no es una pregunta abierta: es una limitación temporal
ya resuelta por la existencia de Fase 0 como prerrequisito. En consecuencia:

- El comportamiento actual del pipeline (ver `docs/reporting-flow.md`) **no
  se modifica** hasta que comience la implementación por fases: un CSV con
  más de un `ID_CLIENT` sigue siendo rechazado por `MULTIPLE_CLIENTS_IN_CSV`,
  y el descubrimiento de varios CSV directos sigue procesándolos exactamente
  como hoy.
- **Fase 2 (sección 5.16), que implementa esta tabla, no comienza hasta que
  `RUN_START_DATE` esté disponible.** No se implementa ninguna versión
  previa que admita varios CSV directos en modo legacy verificando solo las
  condiciones (1)-(3) y dejando la (4) pendiente.
- Cuando se implemente esta clasificación (Fase 2), la igualdad de ventana
  será verificable y **obligatoria**: forma parte del mismo entregable que
  las condiciones (1)-(3), no una mejora posterior.
- **No se acepta un modo "parcialmente verificable"**: no existe, en ningún
  momento, un estado publicado del pipeline que admita varios CSV directos
  en modo legacy sin poder comprobar la condición (4). El caso ya soportado
  hoy — procesar los CSV históricos de uno en uno, o agruparlos en
  subcarpetas no descubiertas automáticamente — sigue funcionando sin
  cambios mientras tanto, porque no pasa por esta clasificación.

**Por qué se descarta añadir un flag de CLI.** Una opción evaluada
inicialmente era añadir un argumento explícito (p. ej. `--mode
{legacy,full-export}`) para forzar el escenario. Se descarta: la decisión
cerrada es no añadir superficie de CLI nueva por ahora, porque el criterio de
clasificación (número de CSV, `ID_CLIENT` por fichero, esquema, ventana) ya
es información que el loader necesita leer de todas formas antes de decidir
cómo particionar, así que no aporta seguridad adicional frente a la
autodetección por contenido, y sí añade una decisión más que el usuario
debe recordar.

## 5.5 Loader multi-cliente

La clasificación del escenario de entrada (sección 5.4: full-export único,
legacy admitido, o error) precede a todo lo descrito en esta sección. Lo que
sigue describe el camino "full-export" (1 CSV, N clientes); el camino legacy
(varios CSV, 1 cliente cada uno) reutiliza el loader actual sin cambios,
salvo la validación adicional de las cuatro condiciones de la sección 5.4.

- **Carga única.** `read_csv_defensive` se invoca una sola vez sobre el CSV
  completo (sigue siendo la misma función; no cambia su contrato).
- **Validación de columnas.** `quality_checks.check_required_columns` se
  aplica una vez sobre el DataFrame completo, antes de particionar: un CSV
  con columnas faltantes invalida el fichero entero (no se sabe todavía a
  qué clientes pertenecen las filas si falta `ID_CLIENT`).
- **Normalización de tipos.** `coerce_numeric_columns` se aplica una vez
  sobre el DataFrame completo (vectorizado; no hay motivo para repetirlo por
  cliente).
- **Conservación de nulos/ceros/negativos.** Sin cambios: la coacción
  numérica y las máscaras de comparabilidad siguen actuando fila a fila,
  independientemente de que las filas ahora convivan en un DataFrame de
  varios clientes.
- **`ID_CLIENT` nulo o no interpretable.** Es un error estructural que
  invalida el CSV completo (sección 5.8): si no puede determinarse
  inequívocamente a qué cliente pertenece una fila, no se descarta esa fila
  silenciosamente ni se procesa el resto asumiendo que está bien.
- **Agrupación por `ID_CLIENT`.** Tras validar el esquema completo y que
  `ID_CLIENT` es interpretable en todas las filas, se particiona con
  `df.groupby("ID_CLIENT")` (o una máscara booleana por `ID_CLIENT`
  reutilizando vistas, evitando copias innecesarias del DataFrame completo:
  usar `.loc[mask]` bajo demanda en vez de crear N copias eager si N es
  grande).
- **Estructura lógica por cliente.** Nuevo tipo, p. ej.
  `ClientPartition`, que sustituye la relación implícita "un `ClientSource`
  = un fichero" por "un `ClientSource` = una partición lógica del fichero
  único". Debe conservar la misma interfaz que `client_analysis.analyze_client`
  espera hoy (`dataframe`, `id_client`, `id_batch`, `id_run_staging`,
  `source_run_id`, `quality`, `is_valid`, `folder_name`, `file_label`) para
  minimizar el cambio en `analyze_client` y todo lo que consume
  `ClientAnalysisResult` aguas abajo (Excel/Markdown/PNG/HTML no deberían
  necesitar saber que ahora provienen de una partición en vez de un fichero).
- **Relación entre el inventario físico y varios resultados lógicos.**
  `input_inventory.InputFileRecord` sigue siendo 1 por fichero físico (no
  cambia: sigue habiendo un único CSV, un único hash SHA-256). Lo que cambia
  es la cardinalidad "fichero → resultados": pasa de como-mucho-1 a N. Todo
  código que hoy asume `by_filename = {r.source.file_name: r for r in
  results}` (un único resultado por nombre de fichero: `manifest.build_manifest`
  línea 139, `execution_summary.build_execution_records` línea 64) debe
  pasar a `by_filename: dict[str, list[ClientAnalysisResult]]`.
- **Compatibilidad con los hashes existentes.** El hash SHA-256 se sigue
  calculando una vez sobre el fichero físico completo
  (`input_inventory.build_input_inventory`, sin cambios). Cada
  `ClientAnalysisResult` de una partición lógica debe conservar una
  referencia al `InputFileRecord`/hash del fichero físico del que procede,
  para que el manifest pueda seguir vinculando "estos N clientes proceden de
  este fichero con este hash".
- **Impacto sobre `ClientSource`.** Se le añade (o se sustituye por un tipo
  que añada) una referencia al fichero físico de origen y, opcionalmente, el
  índice/posición dentro de ese fichero, sin romper el resto de sus campos
  actuales.
- **Impacto sobre logs y manifest.** `manifest.csv_files` deja de ser "un
  elemento por CSV con como mucho un cliente" y pasa a ser "un elemento por
  CSV con una lista de clientes resueltos" (ver sección 5.12 para el detalle
  exacto de forma JSON propuesta).
- **Observabilidad de tamaño y duración.** El loader debe registrar, por CSV
  cargado: tamaño en bytes (ya disponible vía `InputFileRecord.size_bytes`),
  número de filas, número de clientes resultantes de la partición, y
  duración de la fase de carga. Ver sección 5.12 (manifest) y el punto 8 del
  prompt de esta tarea: no se establece todavía ningún límite operativo de
  tamaño ni se decide el uso de *chunks*; esa decisión se toma después de
  observar campañas reales con estos datos ya registrados.

## 5.6 Validación de ejecución lógica

**Objetivo:** para un mismo `ID_CLIENT` dentro del CSV completo, debe existir
**exactamente una** ejecución lógica: una única combinación
`(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID)`. El algoritmo usa las columnas ya
presentes en el contrato de 234 columnas
(`ID_BATCH`, `ID_RUN_STAGING`, `SOURCE_RUN_ID`, `ID_CLIENT`,
`ID_CONFIGURATION`), sin inventar columnas nuevas.

**Fase 0 es un prerrequisito bloqueante para toda esta sección.** El
comportamiento actual del pipeline (`MULTIPLE_CLIENTS_IN_CSV` para cualquier
CSV con más de un `ID_CLIENT`, sin partición ni validación de scope, ver
`docs/reporting-flow.md`) no se modifica hasta que comience la
implementación por fases. La implementación de esta sección corresponde a
Fase 2 (sección 5.16), y **Fase 2 no comienza hasta que Fase 0 entregue
`RUN_START_DATE`** (sección 5.16), aunque el algoritmo de combinaciones
`(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID)` descrito a continuación no
dependa técnicamente de esa columna. La razón es evitar un estado
intermedio: no se implementa la validación de combinaciones batch/run/source-run
por un lado y la comprobación de ventana temporal por otro, en momentos
distintos; ambas se entregan juntas en Fase 2, de modo que cuando exista
partición multi-cliente, la igualdad de ventana ya sea verificable y
**obligatoria** desde el primer momento. No se acepta un modo "parcialmente
verificable" que admita varios CSV o particiones multi-cliente sin poder
comprobar `RUN_START_DATE`.

Algoritmo propuesto (`validate_client_scope`, nuevo, en un módulo por
determinar — candidato: `src/scope_validation.py` o dentro de
`src/input_loader.py` junto a la partición):

1. Para cada `ID_CLIENT`, calcular el conjunto de combinaciones distintas
   `(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID)` presentes en sus filas.
2. Si hay exactamente **una** combinación → ejecución lógica única, cliente
   válido.
3. Si hay **más de una** combinación → conflicto estructural, siempre,
   **sin excepciones**: no importa si las `ID_CONFIGURATION` de cada
   combinación son disjuntas o se solapan. No existe ningún caso en el que
   varias combinaciones para el mismo cliente se acepten o se concatenen.

**Regla de bloqueo:** más de una combinación para un mismo `ID_CLIENT` genera
un `QualityIssue` (`AMBIGUOUS_CLIENT_EXECUTION`, `Severity.ERROR`) que
muestra explícitamente todas las combinaciones conflictivas y sus
`ID_CONFIGURATION`. Este es un **error estructural** (sección 5.8): invalida
el CSV completo y detiene el run entero, no solo ese cliente. No se
concatenan configuraciones de distintas ejecuciones del mismo cliente, no se
selecciona automáticamente el `ID_BATCH` más alto, no se selecciona el
`SOURCE_RUN_ID` más reciente (no hay columna de fecha por la que "más
reciente" tenga significado defendible hasta Fase 0), y el conflicto no se
resuelve mediante ninguna heurística.

**Ejemplos:**

- **Cliente válido:** `ID_CLIENT=10338`, todas sus filas con
  `(ID_BATCH=91, ID_RUN_STAGING=45, SOURCE_RUN_ID=7)`. Una combinación → sin
  incidencia.
- **Cliente repetido en dos batches (bloqueado, detiene el run):**
  `ID_CLIENT=10470` tiene filas con
  `(ID_BATCH=91, ID_RUN_STAGING=45, SOURCE_RUN_ID=7)` para
  `ID_CONFIGURATION` 1-10, y también filas con
  `(ID_BATCH=97, ID_RUN_STAGING=50, SOURCE_RUN_ID=9)` para
  `ID_CONFIGURATION` 11-20 (**disjuntas**, sin ninguna configuración
  repetida). → `AMBIGUOUS_CLIENT_EXECUTION` de todas formas: dos
  combinaciones para el mismo cliente son siempre un conflicto estructural,
  independientemente de si las configuraciones se solapan o no. El CSV
  completo se invalida y el run se detiene, mostrando ambas combinaciones.
- **Cliente repetido en dos runs con configuraciones solapadas (bloqueado,
  detiene el run):** igual que el anterior, pero con `ID_CONFIGURATION`
  1-10 repetidas en ambas combinaciones. Mismo resultado
  (`AMBIGUOUS_CLIENT_EXECUTION`); el solape adicional no cambia la
  severidad ni el tratamiento, porque la regla ya bloquea con una sola
  combinación adicional.
- **Varios clientes repartidos entre varios batches (caso esperado, no
  bloqueado):** el CSV completo contiene `ID_BATCH=91` con los clientes
  10338, 10470, ..., 10203 (10 clientes) y `ID_BATCH=97` con otros 8
  clientes distintos. Cada cliente individual sigue teniendo una única
  combinación batch/run/source-run → sin incidencia a nivel de cliente; el
  WARNING global `BATCH_HETEROGENEITY_ACROSS_CLIENTS` (ya existente,
  quality_checks.py:673) sigue emitiéndose para dejar constancia de que el
  dataset combina varios batches.

### Ventana temporal (bloqueada hasta Fase 0)

**Estado actual de columnas.** El contrato de 234 columnas
(`periods.STATIC_REQUIRED_COLUMNS` + columnas por periodo) **no incluye
ninguna columna de fecha calendario** (ni `RUN_START_DATE`, ni fecha por
mes). `COPIED_AT` existe pero no se parsea hoy
(`docs/reporting-flow.md`, sección 9: "no se parsea `COPIED_AT`, no existe
`RUN_START_DATE` en el contrato"). El backend sí tiene esa fecha
internamente (`docs/backend-validation-flow.md`: "El mapeo M6 a M1 usa el
calendario de la ejecución: `M6 = RUN_START_DATE` y `M1 = RUN_START_DATE + 5
meses`"), pero **`RUN_START_DATE` no forma parte del contrato exportado a
`TA_FOV_SCP_ML_SERIES_COMPARISON`** según lo confirmado en
`docs/reporting-flow.md`.

**Decisión cerrada.** No se usa `COPIED_AT` como aproximación bajo ninguna
circunstancia (ni siquiera como *best-effort* con advertencia): es una fecha
de copia a staging, no la fecha real de cálculo, y una aproximación no
verificable no debe informar una decisión de bloqueo/no-bloqueo. En su
lugar, se solicita al backend que añada `RUN_START_DATE` a
`TA_FOV_SCP_ML_SERIES_COMPARISON` y a la exportación CSV (Fase 0, sección
5.16). Hasta que esa fase se complete, **Fase 2 no comienza**: no se
implementa ni la comprobación de ventana temporal ni el resto de la
validación de scope multi-cliente de esta sección, como variante parcial o
aproximada. El comportamiento actual del pipeline no se modifica mientras
tanto. No existe un modo "parcialmente verificable" que implemente unas
comprobaciones de scope sí y la de ventana no.

**Reglas del reporting a partir de Fase 2, una vez `RUN_START_DATE` exista**
(contrato objetivo de 235 columnas, salvo ajuste adicional que determine la
revisión real del backend). Estas reglas son parte obligatoria de la primera
implementación de Fase 2, no una mejora diferida:

- Todas las filas de un mismo `ID_CLIENT` deben compartir un único
  `RUN_START_DATE`.
- Todos los clientes incluidos en un mismo análisis global deben compartir
  el mismo `RUN_START_DATE`.
- Varias fechas distintas dentro de un cliente, o entre los clientes de un
  mismo dataset global, son un **error estructural** (sección 5.8): detiene
  el run completo, con el mismo tratamiento que `AMBIGUOUS_CLIENT_EXECUTION`.
- No se agregan ventanas diferentes bajo ninguna circunstancia.
- El conflicto nunca se degrada a WARNING: es siempre ERROR bloqueante.
- `COPIED_AT` no se usa para inferir la ventana, ni siquiera cuando
  `RUN_START_DATE` ya exista (deja de tener ningún papel en esta
  comprobación).

## 5.7 Catálogo de clientes

`config/client-catalog.json` es el **catálogo definitivo**: 228 entradas,
depurado y normalizado manualmente por el propietario del proyecto a partir
del catálogo provisional de 294 entradas generado inicialmente desde
`get-clients`. No está pendiente de limpieza ni de sustitución.

- **Carga opcional de `config/client-catalog.json`.** Nuevo módulo
  candidato: `src/client_catalog.py`, con una función
  `load_client_catalog(path: Path) -> dict[int, str]` que lee el JSON
  (`{"10338": "Grefusa", ...}`), convierte las claves a `int`, y devuelve un
  diccionario vacío (nunca lanza) si el fichero no existe.
- **Validaciones al cargar:** JSON parseable, es un objeto (no una lista),
  cada clave es convertible a entero, cada valor es una cadena. Un catálogo
  corrupto o ilegible degrada a "catálogo vacío" con un WARNING, nunca
  bloquea el análisis (ver "Reglas futuras" del prompt original: "la
  ausencia del catálogo no debe impedir el análisis").
- **`n_entries` calculado dinámicamente.** El número de entradas del
  catálogo (hoy 228) **nunca se hardcodea** en código ni en manifest: se
  calcula siempre como `len(catalog)` en el momento de la carga, para que
  una futura edición manual del JSON no requiera ningún cambio de código ni
  deje un número desactualizado en la documentación o en el manifest.
- **Fallback.** `resolve_client_name(id_client: int, catalog: dict[int,
  str]) -> str`: si `id_client in catalog`, devuelve el nombre del catálogo;
  si no, devuelve `f"Cliente {id_client}"` (fallback explícito, nunca una
  cadena vacía ni `None`).
- **Uso de `ID_CLIENT`.** El catálogo se consulta únicamente para
  presentación (títulos, HTML, Excel, Markdown), nunca para decidir qué
  clientes se procesan ni para agrupar filas.
- **Presentación del nombre.** Formato recomendado en el prompt original:
  `Grefusa — ClientId 10338` cuando el catálogo resuelve un nombre;
  `Cliente 10338` cuando no.
- **Sanitización.** El nombre resuelto se sanea únicamente al construir
  carpetas/filenames/slugs/URLs (reutilizando
  `input_loader.normalize_folder_name`, que ya sustituye
  `<>:"/\|?*` por `_`); el nombre original (con acentos, espacios,
  puntuación) se conserva sin modificar para títulos y contenido visible en
  HTML/Excel/Markdown.
- **Nombres duplicados.** El diseño debe seguir tolerando que dos
  `ID_CLIENT` distintos compartan nombre descriptivo, porque el catálogo es
  de mantenimiento manual y nada garantiza unicidad hacia el futuro. El
  catálogo depurado actual no contiene ya nombres estrictamente idénticos
  entre IDs distintos (p. ej. los antiguos duplicados `Faes GU` → 10226 y
  10446 quedaron reducidos a una única entrada, `10226`, tras la limpieza),
  pero sí conserva pares de IDs claramente relacionados que el propietario
  distinguió manualmente con un sufijo — p. ej. `10503` (`Fiorucci`) y
  `10537` (`Fiorucci 2`), o `10618` (`Viokox 2`) y `10724` (`Viokox`) — como
  evidencia de que el riesgo de colisión de nombres es real y debe seguir
  mitigándose estructuralmente. Por eso la carpeta de cliente debe
  incorporar `ID_CLIENT` para evitar colisión, p. ej. `10338-grefusa` en vez
  de solo `grefusa`, sustituyendo el `folder_name` actual (derivado del
  nombre de fichero) por uno derivado de `{id_client}-{slug(nombre_resuelto)}`.
- **IDs ausentes.** Un `ID_CLIENT` del CSV que no está en el catálogo usa el
  fallback `Cliente {id_client}`; no es un error ni un warning (es el
  comportamiento esperado y documentado del catálogo, que se mantiene
  manualmente y puede quedar desactualizado sin que eso invalide el
  reporting).
- **Impacto en navegación.** `html_view_models.build_client_page_vm` /
  `build_client_table_vm` (que hoy usan `source.file_label` como etiqueta,
  ver `src/html_view_models.py` líneas 223-265, 378-420) deben pasar a usar
  el nombre resuelto por el catálogo en vez de `file_label` derivado del
  nombre de fichero (que deja de tener sentido cuando el fichero es un CSV
  completo multi-cliente, no `TA_FOV_SCP_ML_<ID>_<ETIQUETA>.csv`).
- **Impacto en filenames.** `excel_writer` / `report_writer` /
  `logging_utils` construyen nombres como
  `fov_scp_ml_summary_{source.folder_name}.xlsx`
  (`analysis_fov_scp_ml.py`, línea 127): siguen funcionando igual una vez
  que `folder_name` se redefine como se indica arriba (`{id}-{slug}`).
- **Impacto en templates.** `templates/client_report.html`,
  `templates/global_report.html` y sus componentes deben mostrar el nombre
  resuelto (con el sufijo `ClientId <id>` o el fallback `Cliente <id>`) en
  vez de la etiqueta actual derivada de fichero.
- **Impacto en Excel, Markdown y HTML.** Cualquier cabecera/título que hoy
  use `source.file_label` (buscar todas las ocurrencias en
  `excel_writer.py`, `report_writer.py`, `global_excel_writer.py`,
  `global_report_writer.py`, `html_view_models.py`) debe migrar al nombre
  resuelto por el catálogo. `ETIQUETA` en `global_analysis.build_client_period_table`
  (línea 222) es un ejemplo concreto de columna que hoy expone
  `source.file_label` y pasaría a exponer el nombre resuelto.
- **Registro en manifest.** Ruta del catálogo, hash SHA-256, `n_entries`
  calculado dinámicamente (nunca hardcodeado), IDs sin nombre encontrados
  durante la ejecución, nombre finalmente mostrado por cliente (ver sección
  5.12).
- **Tests necesarios:** catálogo ausente (fallback total), catálogo vacío
  `{}`, catálogo con JSON inválido, catálogo con claves no numéricas,
  catálogo con un ID presente y otro ausente en el mismo run, nombre con
  espacios exteriores ya recortados (el catálogo en sí ya llega recortado,
  pero el loader no debe volver a hacer `strip()` de forma que oculte un
  problema real de origen), nombre con acentos/Unicode preservado en HTML
  pero saneado en el slug, colisión de slugs entre dos clientes con nombre
  parecido tras sanear (mitigado por incluir siempre `ID_CLIENT` en el
  `folder_name`), `n_entries` calculado a partir de un catálogo de tamaño
  arbitrario (no solo 228) para confirmar que nunca se asume un tamaño fijo.

## 5.8 Semántica de errores

Se distinguen siempre dos categorías, con tratamiento muy distinto:

**Errores estructurales — invalidan el CSV completo y detienen el run
entero.** No se publica un run "exitoso" excluyendo silenciosamente a los
clientes afectados: el pipeline falla igual que hoy falla ante "cero CSV
encontrados" (`analysis_fov_scp_ml.py`, línea 472-487) o
`INPUT_CHANGED_DURING_RUN` — manifest `FAILED`, directorio temporal
conservado íntegro para diagnóstico, código de salida `1`, sin publicación.
Pertenecen a esta categoría:

- Esquema inválido (columnas obligatorias ausentes en el CSV completo).
- `ID_CLIENT` nulo o no interpretable en cualquier fila.
- Un cliente con más de una combinación `(ID_BATCH, ID_RUN_STAGING,
  SOURCE_RUN_ID)` (`AMBIGUOUS_CLIENT_EXECUTION`, sección 5.6) — **no** se
  aísla solo ese cliente y se continúa con los demás; el CSV completo queda
  inválido.
- Duplicados de la clave lógica (`ID_BATCH, ID_RUN_STAGING, ID_CLIENT,
  SOURCE_RUN_ID, ID_CONFIGURATION`) dentro del CSV completo.
- Varias ventanas temporales (`RUN_START_DATE` distinto dentro de un
  cliente, o entre los clientes del análisis global) — disponible solo tras
  Fase 0, sección 5.6.
- Mezcla incompatible de CSV full-export y legacy, o cualquier combinación
  de CSV directos que no cumpla las reglas cerradas de la sección 5.4.

Este tratamiento es una diferencia deliberada frente al diseño anterior de
este mismo plan (que aislaba un cliente `AMBIGUOUS_CLIENT_EXECUTION` como si
fuera un fichero inválido más, dejando publicar el resto): con un único
fichero físico de entrada, un conflicto de scope en un cliente indica que el
propio full export puede no ser la exportación completa y coherente que se
espera recibir del backend (ver `docs/backend-validation-flow.md`, "No
seleccionar columnas manualmente ni reconstruir métricas durante la
exportación"), por lo que no hay una base fiable para publicar el resto de
clientes como si nada hubiera pasado.

**Situaciones analíticas normales — no invalidan el run.** Se procesan y
publican con normalidad, exactamente como hoy:

- Cliente sin comparables (cobertura sin ninguna serie comparable): sigue
  generando su carpeta, Excel, Markdown, log y página HTML, con performance
  como N/D.
- Cliente sin nombre en el catálogo: usa el fallback `Cliente {id}`.
- Cliente con métricas N/D por ausencia válida de población comparable en
  algún periodo concreto (p. ej. sin comparables en `M3` pero sí en 6M).
- Cualquier `QualityIssue` de severidad `WARNING` localizada a un
  periodo/fila que hoy ya no escala a `ERROR` de cliente
  (`client_analysis.analyze_client`, línea 389).

**Fallos aislados no estructurales.** El `try/except` por cliente de
`analysis_fov_scp_ml.run_pipeline` (línea 495-514) se mantiene para
excepciones inesperadas durante la generación de outputs de un cliente ya
validado (p. ej. un fallo puntual al construir un gráfico) — esto **no** es
lo mismo que un error estructural de scope: la validación de la sección 5.6
ocurre **antes** de empezar a generar outputs por cliente, así que un
conflicto de scope nunca llega a ese `try/except` aislado: detiene el run en
una fase anterior (`SCOPE_VALIDATION`, nueva fase de log).

## 5.9 Análisis por cliente

Cada cliente se genera desde una partición interna del CSV único
(`df.loc[df["ID_CLIENT"] == id_client]`, o el resultado de un `groupby`
previo), no desde un fichero separado. Elementos concretos:

- **Clave:** `ID_CLIENT` (entero), como ya lo es hoy internamente
  (`ClientSource.id_client`).
- **Etiqueta:** nombre resuelto por `config/client-catalog.json` (sección
  5.7), con fallback `Cliente {id}`. Sustituye a `file_label` derivado de
  nombre de fichero como etiqueta *de presentación* (pero `file_label`/el
  nombre físico del CSV de origen se sigue registrando en el manifest como
  procedencia, no se pierde esa trazabilidad).
- **Slug:** versión saneada del nombre resuelto (reutilizando
  `normalize_folder_name`).
- **Nombre de carpeta:** `{id_client}-{slug}` (p. ej. `10338-grefusa`), para
  evitar colisiones entre clientes con nombre igual o parecido y para que la
  carpeta sea estable aunque el catálogo cambie de nombre en una ejecución
  futura (cambia el slug, pero el prefijo numérico sigue identificando
  inequívocamente al cliente en los enlaces históricos del catálogo de
  runs).
- **Navegación:** el orden cliente anterior/siguiente
  (`html_view_models`, sección "Navegacion cliente anterior/siguiente en
  orden deterministico" del README) pasa de "por nombre de fichero" a "por
  `ID_CLIENT` numérico ascendente" (más estable y predecible que ordenar por
  un nombre de fichero que ya no existe por cliente).
- **Cliente sin nombre:** usa el fallback `Cliente {id}`; sigue siendo un
  cliente completamente válido y procesado (sección 5.8: no es un error
  estructural).
- **Cliente sin comparables:** sin cambios de comportamiento (sección 5.8):
  sigue generando su carpeta, Excel, Markdown, log y página HTML, con
  performance como N/D.
- **Fallo aislado:** ver sección 5.8 — el `try/except` por cliente sigue
  existiendo para excepciones no estructurales durante la generación de
  outputs de un cliente ya validado; un conflicto de scope (sección 5.6) no
  llega a este punto porque detiene el run antes.
- **Orden de clientes:** determinista por `ID_CLIENT` ascendente (ver
  navegación arriba), reemplazando el orden actual "por nombre de fichero".
- **Colisiones de nombres:** resueltas estructuralmente por incluir siempre
  `ID_CLIENT` en el `folder_name` (ver sección 5.7 para ejemplos concretos
  del catálogo depurado: `10503`/`10537` para "Fiorucci"/"Fiorucci 2",
  `10618`/`10724` para "Viokox 2"/"Viokox").

## 5.10 Comparabilidad

| Concepto | Comportamiento actual | Fuente backend | Comportamiento objetivo | Archivo afectado |
|---|---|---|---|---|
| `COMPARISON_STATUS` (6M) | Se audita solo en 6M contra la máscara propia (`check_comparison_status_vs_period_mask`); no filtra nunca | Precedencia documentada de 8 estados; `COMPARABLE` es la referencia canónica de 6M | **Cambio funcional:** `COMPARISON_STATUS == 'COMPARABLE'` pasa a ser el filtro real de la población comparable de 6M (numerador de cobertura de 6M y universo de las métricas 6M) | `src/client_analysis.py` (`_analyze_period`, `period_comparable_mask` para el caso `period == "6M"`) |
| Máscara comparable propia (6M) | `period_comparable_mask`: candidato + histórico>0 + SCP/ML válidos; hoy es el universo analítico de 6M | No existe como tal en backend | Deja de ser el universo analítico de 6M; se conserva únicamente como **auditoría**: desglosa por causa (`HAS_ML_EXCLUDED`, histórico no positivo, forecast/WAPE ausente) las discrepancias frente a `COMPARISON_STATUS == 'COMPARABLE'`, sin sustituirlo | `src/client_analysis.py`, `src/quality_checks.py` (nueva función de desglose) |
| Denominador de cobertura (todos los periodos, incluido 6M) | `n_candidates` = `HAS_BASE_CANDIDATE==1` | Cobertura usa universo `BASE/Candidate` como denominador (coincide) | Sin cambio: `HAS_BASE_CANDIDATE==1` sigue siendo el denominador de cobertura en todos los periodos, incluido 6M | `src/client_analysis.py` |
| `6M` — métricas (WAPE, mejora, ganadores, reducción absoluta) | Calculadas sobre la máscara propia | `COMPARABLE` | **Cambio funcional:** se recalculan únicamente sobre filas `COMPARISON_STATUS == 'COMPARABLE'` | `src/client_analysis.py`, `src/metrics.py` (sin cambio de fórmula, cambia el subconjunto de filas de entrada) |
| `OLDER_3M` / `RECENT_3M` | Máscara propia sobre columnas `TOTAL_*_OLDER_3M`/`TOTAL_*_RECENT_3M` | No hay equivalente trimestral en `COMPARISON_STATUS` (es un resumen de 6M) | **Sin cambio:** mantienen máscara específica según disponibilidad de datos del periodo, porque `COMPARISON_STATUS` no tiene granularidad trimestral | `src/client_analysis.py` |
| Meses individuales (`M1..M6`) | Máscara propia por mes | No hay equivalente mensual en `COMPARISON_STATUS` | **Sin cambio:** mantienen máscara específica según disponibilidad de datos del periodo | `src/client_analysis.py` |
| No comparables (6M) | Motivo derivado local (`NO_HISTORY_OR_ZERO`, `MISSING_SCP_AND_ML`, `MISSING_SCP`, `MISSING_ML`, `OTHER`) | 8 estados de precedencia (`NOT_COMPARABLE_RUN_FAILED`, ..., `NOT_COMPARABLE_NO_HISTORY`) | Para 6M, el motivo canónico pasa a ser directamente el valor de `COMPARISON_STATUS` cuando es distinto de `COMPARABLE`; el motivo derivado local se conserva como desglose de auditoría adicional, no como fuente primaria | `src/client_analysis.py` |
| Cobertura (6M) | `n_comparable/n_candidates*100` sobre máscara propia | Misma definición conceptual, con `COMPARABLE` como numerador | `n_comparable` de 6M pasa a ser el recuento de filas `COMPARISON_STATUS == 'COMPARABLE'` dentro del universo candidato | `src/client_analysis.py` |

**No se cambia la definición del backend ni se reconstruye
`COMPARISON_STATUS`**: el reporting consume el valor tal cual llega en el
CSV, exactamente como ya hace con `WINNER_METHOD_*`.

## 5.11 Métricas de mejora

| Métrica | Fórmula | Fuente | Uso | Nombre futuro |
|---|---|---|---|---|
| Ganador vs. finalista | `((FINALIST_WAPE - WINNER_WAPE) / FINALIST_WAPE) * 100`; `0` en empate | Backend, columna `WINNER_IMPROVEMENT_PCT_*` (requerida pero hoy solo coaccionada, no usada analíticamente) | Se expone tal cual la entrega el backend, como métrica de negocio "mejora del ganador frente al finalista". **No se recalcula bajo ninguna circunstancia**: es una columna de solo lectura desde el CSV | `WINNER_IMPROVEMENT_PCT` (mismo nombre que la columna origen, sin transformación) |
| ML frente a SCP | `(SCP_WAPE - ML_WAPE) / SCP_WAPE * 100` | Reporting, `src/metrics.relative_improvement_row` / `period_wape_global` | Mantener como está: es la métrica central de las 4 perspectivas del análisis (cliente, serie, global ponderado) | `ML_VS_SCP_IMPROVEMENT_PCT` (renombrar en outputs desde el actual `improvement_pct`/`MEJORA_RELATIVA_PCT`/`ML_IMPROVEMENT_VS_SCP_PCT`, unificando la nomenclatura dispersa hoy entre código, Excel y README) |
| Empate | `relativeDiff = ABS(SCP_WAPE-ML_WAPE)/NULLIF(MAX(SCP_WAPE,ML_WAPE),0)`; `TIE` si `<0.0001`, o si ambos WAPE=0 | Backend (ahora documentado en `docs/backend-validation-flow.md`) | Reporting solo audita el caso "ambos WAPE=0 ⇒ debe ser TIE" (`check_both_zero_wape_is_tie`); **no** reconstruye `relativeDiff` completo | Sin cambio de fórmula; cambia el mensaje de `check_winner_formula_not_auditable` (ver sección 5.16, Fase 4) |
| Denominador cero | `SCP_WAPE` computacionalmente cero (`NEAR_ZERO_WAPE_EPSILON=1e-9`) | Reporting | `ML_VS_SCP_IMPROVEMENT_PCT` = NaN (`CASE_SCP_ZERO_ML_POSITIVE`) o normal si además `ML_WAPE`~0 (`CASE_BOTH_ZERO` → NaN) | Sin cambio |
| Valores nulos | `SCP_WAPE`/`ML_WAPE` nulo | Reporting | `ML_VS_SCP_IMPROVEMENT_PCT` = NaN (`CASE_MISSING_WAPE`) | Sin cambio |
| Valores negativos | WAPE no debería ser negativo por definición (`abs_error/history`, ambos ≥0 tras excluir histórico≤0), pero no se valida el signo explícitamente | Reporting/backend | Añadir un chequeo de calidad nuevo (`check_negative_wape`, WARNING) que documente si algún `SCP_WAPE`/`ML_WAPE` llega negativo, en vez de asumir silenciosamente que nunca ocurre | `src/quality_checks.py` |

## 5.12 Outputs y publicación

Estructura de `outputs/runs/<run-name>/` **sin cambios de forma**; cambia el
contenido de algunos ficheros:

- **`index.html`** — la tabla de clientes pasa a mostrar el nombre resuelto
  por catálogo (`{nombre} — ClientId {id}` / `Cliente {id}`) en vez de
  `file_label`; el inventario de archivos de entrada pasa a mostrar, por
  cada CSV, cuántos clientes se resolvieron desde él (hoy asume 0 o 1).
- **`clients/<client-slug>/index.html`** — `<client-slug>` pasa de
  `folder_name` derivado de nombre de fichero a `{id}-{slug(nombre)}`
  (sección 5.9); el contenido interno (cobertura, WAPE, mejora, modelos,
  clasificaciones) no cambia de forma.
- **`manifest.json`** — cambios concretos propuestos:
  - `csv_files[i]` pasa de campos singulares (`id_client`, `etiqueta`,
    `filas`, `estado`, `warnings`, `errors`) a una lista `clients: [...]`
    con un elemento por cliente resuelto de ese fichero (manteniendo los
    campos singulares como `null` cuando `clients` está vacío, para no
    romper lectores que ya asumen la forma actual del catálogo — ver
    "Compatibilidad con manifests históricos" en README/`run_catalog.py`,
    que ya tolera campos ausentes con warnings `CATALOG_FIELDS_MISSING`).
  - Nuevo bloque `client_catalog`, con `n_entries` **calculado
    dinámicamente** al cargar el JSON (nunca hardcodeado en el código ni en
    el manifest; la documentación puede registrar el tamaño actual del catálogo
    como información descriptiva):

    ```json
    {
      "path": "config/client-catalog.json",
      "sha256": "...",
      "n_entries": "<len(catalog) en el momento de la carga>",
      "ids_without_name": ["..."],
      "resolved_names": {"10338": "Grefusa", "...": "..."}
    }
    ```

  - Nuevos campos de observabilidad de tamaño/duración (punto 8 del prompt
    de esta tarea, sin establecer todavía ningún límite operativo): por
    cada CSV cargado, tamaño en bytes (ya disponible vía `size_bytes`),
    número de filas, número de clientes resultantes; a nivel de run,
    duración de la fase de carga (`input_load_duration_seconds`, nuevo) y
    duración total del run (`duration_seconds`, ya existente). El límite de
    tamaño o el uso de *chunks* se decide después de observar campañas
    reales con estos datos ya registrados, no en este plan.
  - `manifest_schema_version` se incrementa (hoy en `2`,
    `src/manifest.MANIFEST_SCHEMA_VERSION`) porque cambia la forma de
    `csv_files`.
- **`execution.log`** — sin cambio de mecanismo; los mensajes de fase
  reflejan cuántos clientes se resolvieron del CSV único, e incluyen una
  nueva fase `SCOPE_VALIDATION` (sección 5.8) que, si falla, detiene el run
  antes de `CLIENT_PROCESSING`.
- **`run_config.json`** — sin cambio de forma; no se añade ningún argumento
  CLI nuevo para seleccionar modo de entrada (sección 5.4).
- **`execution_summary.*`** — cambia de "una fila por CSV" (hoy, 1:1 con
  `ExecutionRecord`) a "una fila por cliente resuelto, con el fichero de
  origen como columna adicional" (`ExecutionRecord.archivo` deja de ser
  clave única). Un CSV con `read_error` sigue generando una única fila
  `INPUT_NOT_ANALYZED`, sin clientes. Un CSV que falla por un error
  estructural de scope (sección 5.8) no llega a generar `execution_summary`
  en absoluto, porque el run entero se detiene antes de esa fase.
- **Catálogo de runs (`<output-root>/index.html`)** — no necesita cambios
  de contrato: sigue leyendo únicamente `catalog_summary` (agregados ya
  calculados) y `.publish_complete`; `catalog_summary` no depende de la
  cardinalidad "1 fichero = 1 cliente" (ya se calcula sobre `results`, que
  pasa a tener más elementos, sin cambiar su forma).

Se mantiene la publicación transaccional actual sin cambios
(`run_publish.publish_run`, `reconcile_interrupted_publication`): ambas
funciones operan sobre directorios, no sobre la cardinalidad de clientes, y
no requieren ningún cambio. Un error estructural (sección 5.8) nunca llega a
invocar `publish_run`: el run falla antes, exactamente como hoy falla
"cero CSV encontrados".

## 5.13 Compatibilidad hacia atrás

La convivencia de un modo "full-export" (1 CSV, N clientes) con un modo
"legacy" (varios CSV, 1 cliente cada uno) ya no es una recomendación: es una
regla cerrada (sección 5.4), con cuatro condiciones explícitas para que el
modo legacy siga admitiéndose. Esta sección documenta, para referencia
futura, las alternativas consideradas y por qué el diseño cerrado es el que
mejor equilibra riesgo y continuidad.

| Opción | Complejidad | Riesgo | Ambigüedad | Impacto en tests | Impacto en usuarios | Estado |
|---|---|---|---|---|---|---|
| 1. Sustituir completamente el modo CSV-por-cliente | Baja (elimina una rama de código) | Alto: rompe los 24 CSV históricos de `data/exportacion_*` usados como evidencia y cualquier test que dependa de un CSV de un solo cliente como *input* típico | Ninguna: un único comportamiento | Alto: hay que reescribir fixtures que asumen 1 CSV = 1 cliente (`tests/factories.py`) | Alto: cualquier flujo manual que siga copiando CSV por cliente deja de funcionar sin aviso | Descartada por ahora; posible destino final tras validar el modo nuevo (Fase 6, sección 5.16), no antes |
| 2. Mantener ambos modos permanentemente sin condiciones | Media (dos caminos de carga a mantener) | Medio: superficie de mantenimiento duplicada indefinidamente | Media: un usuario podría no saber cuál modo se activó | Medio: hay que testear ambos caminos para siempre | Bajo: no rompe nada existente | Descartada: el prompt original es explícito en que la única entrada analítica futura es el CSV completo; mantener ambos modos sin condiciones "por inercia" contradice esa instrucción |
| 3. Detectar automáticamente el modo por contenido, con el modo legacy admitido solo bajo las cuatro condiciones cerradas de la sección 5.4 | Baja-media: los criterios (número de `ID_CLIENT` por fichero, solapes, esquema, ventana) ya son información que el loader lee de todas formas | Bajo: el criterio es inequívoco y las cuatro condiciones eliminan la ambigüedad de "varios CSV directos" que antes quedaba como decisión abierta | Baja: la única limitación real es que la condición de ventana compartida no es verificable con certeza hasta Fase 0 (documentado explícitamente, no es una pregunta abierta) | Bajo: los tests existentes de "1 CSV = 1 cliente" siguen pasando sin cambios porque ese caso sigue siendo válido y usa el mismo camino de código internamente (una partición con 1 solo grupo) | Ninguno para el flujo histórico de un único CSV; el flujo con varios CSV legacy simultáneos pasa a validarse más estrictamente que hoy (nuevo) | **Cerrada y vigente.** Es la regla definitiva de la sección 5.4 |

**No se mantiene compatibilidad únicamente por inercia**: los 24 CSV
históricos de `data/exportacion_*` no se eliminan (son evidencia auditada,
versionada en Git, sección "Outputs legacy" del README). Procesados de uno
en uno (el patrón de uso histórico real, ver `docs/reporting-flow.md`), cada
CSV sigue siendo "1 CSV directo, 1 `ID_CLIENT`" y por tanto sigue
funcionando sin ningún cambio de comportamiento bajo la regla cerrada. Solo
si se cargaran **todos a la vez** en el mismo `--input-dir` entrarían en el
camino "varios CSV directos" y quedarían sujetos a las cuatro condiciones de
la sección 5.4 (incluida la de ventana temporal, no verificable hasta Fase
0) — un escenario que no corresponde al uso histórico documentado de este
repositorio.

## 5.14 Archivos y funciones afectados

| Archivo | Función o clase | Cambio futuro | Riesgo | Tests relacionados |
|---|---|---|---|---|
| `src/run_config.py` | `build_arg_parser`, `RunConfig` | Sin nuevo argumento de CLI (sección 5.4); el catálogo se carga desde `<repo>/config/client-catalog.json`. Si el fichero no existe o no puede cargarse, se utiliza el fallback Cliente <ID_CLIENT>. | Bajo: argumento opcional con default sensato | `tests/test_run_config.py` |
| `src/input_loader.py` | `discover_csv_files` | Sin cambio de firma; la clasificación del escenario "0/1/N CSV, full-export/legacy/error" (sección 5.4) se decide en el orquestador a partir de lo que esta función descubre | Bajo | `tests/test_input_loader.py` |
| `src/input_loader.py` | `_load_single_source`, `ClientSource`, `load_client_sources` | Nueva función `load_client_partitions(path) -> list[ClientSource-equivalente]` que reutiliza `read_csv_defensive`, `check_required_columns`, `coerce_numeric_columns` sobre el DataFrame completo, y luego particiona por `ID_CLIENT` aplicando la validación de scope (sección 5.6); nueva función de clasificación de escenario de entrada (sección 5.4) | Medio-alto: es el cambio central del plan | `tests/test_input_loader.py` (nuevos casos multi-cliente y de clasificación de escenario) |
| `src/quality_checks.py` | `check_single_client` | Se mantiene sin cambios para el modo legacy (1 CSV = 1 cliente); en modo full-export no se invoca por fichero, se sustituye conceptualmente por la partición explícita | Bajo | `tests/test_quality_checks.py` |
| `src/quality_checks.py` | `check_duplicate_client_across_files`, `check_batch_heterogeneity` | Revisar semántica: el primero se reutiliza para la condición (2) del modo legacy de la sección 5.4 (`ID_CLIENT` no repetido entre ficheros); el segundo sigue aplicando igual (heterogeneidad de batch entre clientes del mismo fichero o del mismo run) | Medio | `tests/test_quality_checks.py`, `tests/test_input_loader.py` |
| `src/quality_checks.py` | Nueva: `check_ambiguous_client_execution` | Implementa el algoritmo de la sección 5.6: más de una combinación `(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID)` por `ID_CLIENT` es siempre `Severity.ERROR`, sin excepción por configuraciones disjuntas. Es un error estructural que el orquestador debe propagar como fallo global del run (sección 5.8), no como aislamiento por cliente | Alto: lógica nueva de negocio con impacto en el flujo de fallo global | Nuevo `tests/test_scope_validation.py` |
| `src/quality_checks.py` | Nueva: `check_negative_wape` | WARNING si `SCP_WAPE`/`ML_WAPE` < 0 | Bajo | `tests/test_quality_checks.py` |
| `src/quality_checks.py` | `check_winner_formula_not_auditable` | Actualizar el mensaje: la fórmula de `relativeDiff` **ya está documentada** en `docs/backend-validation-flow.md`; el chequeo debe seguir sin reconstruirla (no se recalcula el winner), pero el mensaje no puede seguir diciendo "no está documentada" | Bajo (cambio de texto/severidad, no de lógica) | `tests/test_quality_checks.py`, `tests/test_client_analysis.py` |
| `src/quality_checks.py` | Nueva: `check_comparison_status_discrepancy_breakdown` | Desglosa por causa la discrepancia entre la máscara propia de 6M y `COMPARISON_STATUS=='COMPARABLE'` (sección 5.10), como auditoría — ya no como candidata a universo analítico | Medio | `tests/test_quality_checks.py` |
| `src/periods.py` | `STATIC_REQUIRED_COLUMNS`, `all_required_columns` | **Depende de Fase 0** (sección 5.16): el contrato de 234 columnas no cambia hasta que el backend entregue `RUN_START_DATE` en una exportación real; cuando exista, se añade como columna estática obligatoria (contrato objetivo de 235 columnas) | Bajo hasta Fase 0; medio cuando se implemente (columna nueva obligatoria) | `tests/test_periods.py` (nuevo caso tras Fase 0) |
| `src/client_analysis.py` | `analyze_client`, `period_comparable_mask`, `_analyze_period` | **Cambio funcional para 6M** (sección 5.10): `period_comparable_mask` deja de ser el universo analítico de 6M; `_analyze_period` para `period == "6M"` filtra por `COMPARISON_STATUS == 'COMPARABLE'`. Sin cambio de firma. Documentar en el docstring que el DataFrame ahora puede ser una partición en memoria, no un fichero | Medio: cambia resultados numéricos de 6M, no solo documentación | `tests/test_client_analysis.py` |
| `src/global_analysis.py` | `analyze_global`, `build_client_period_table` | Sin cambio de firma; `ETIQUETA` pasa de `file_label` a nombre resuelto por catálogo; los agregados de 6M reflejan el nuevo universo `COMPARABLE` heredado de `client_analysis.py` | Bajo-medio | `tests/test_global_analysis.py` |
| `src/metrics.py` | Sin cambios de fórmula | Solo renombrado de salida (`ML_VS_SCP_IMPROVEMENT_PCT`), no de cálculo | Bajo | `tests/test_metrics.py` |
| `src/html_view_models.py` | `build_client_row_vm`, `build_client_table_vm`, `build_client_page_vm`, `build_inventory_row_vm` | Sustituir `source.file_label` por nombre resuelto por catálogo; navegación prev/next por `ID_CLIENT` | Medio | `tests/test_html_report.py` |
| `src/html_report.py` | `generate_html_report` | `folder_name` pasa a `{id}-{slug}`; sin cambio de mecanismo de generación/validación de enlaces | Medio | `tests/test_html_report.py` |
| `src/manifest.py` | `build_manifest`, `_build_csv_entry` | `csv_files[i]` pasa a lista `clients`; nuevo bloque `client_catalog` con `n_entries` calculado dinámicamente; nuevos campos de observabilidad de tamaño/duración (sección 5.12); incrementar `MANIFEST_SCHEMA_VERSION` | Medio-alto: cambia forma pública consumida por `run_catalog.py` y por consumidores externos del manifest | `tests/test_manifest.py`, `tests/test_run_catalog.py` |
| `src/execution_summary.py` | `build_execution_records`, `ExecutionRecord` | `archivo` deja de ser 1:1 con cliente; una fila por cliente resuelto + columna de fichero de origen | Medio | `tests/test_execution_summary.py` |
| `src/run_publish.py` | — | Sin cambios | Ninguno | `tests/test_run_publish.py` |
| `src/run_catalog.py`, `run_catalog_models.py` | `scan_output_root`, `rebuild_run_catalog` | Sin cambios de contrato (solo leen `catalog_summary`, agnóstico a cardinalidad de clientes); revisar que toleren `manifest_schema_version` incrementado con el mismo mecanismo `CATALOG_FIELDS_MISSING` ya existente | Bajo | `tests/test_run_catalog.py` |
| `src/input_inventory.py` | — | Sin cambios (opera sobre ficheros físicos, no sobre clientes) | Ninguno | `tests/test_input_inventory.py` |
| `analysis_fov_scp_ml.py` | `run_pipeline`, `_generate_client_outputs`, `_print_client_summary` | Bucle "por fichero" pasa a bucle "por partición lógica"; nueva fase `SCOPE_VALIDATION` (falla el run completo ante un error estructural, sección 5.8) y `CLIENT_CATALOG_LOAD` en el log de fases | Alto: es el orquestador central | `tests/test_pipeline_runs.py` |
| Nuevo: `src/client_catalog.py` | `load_client_catalog`, `resolve_client_name` | Módulo nuevo (sección 5.7) | Bajo (módulo aislado, sin dependencias de otros módulos de dominio) | Nuevo `tests/test_client_catalog.py` |

## 5.15 Plan de tests

### Input

- Un CSV multi-cliente válido (varios `ID_CLIENT`, cada uno con una única
  combinación batch/run/source-run).
- CSV vacío (0 filas, cabecera válida).
- Cero CSV en `data/` → error, sin cambios respecto a hoy.
- Exactamente un CSV directo con un único `ID_CLIENT` → modo legacy trivial,
  sin cambios de resultado respecto a hoy.
- Exactamente un CSV directo con varios `ID_CLIENT` → modo full-export,
  particionado interno.
- Varios CSV directos que cumplen las cuatro condiciones de la sección 5.4
  (un `ID_CLIENT` cada uno, sin solape, mismo esquema, misma ventana) → modo
  legacy admitido.
- Varios CSV directos con un `ID_CLIENT` repetido entre archivos → error,
  detiene el run completo.
- Varios CSV directos donde alguno contiene más de un `ID_CLIENT` → error.
- Dos CSV directos, ambos multi-cliente → error.
- Varios CSV directos con esquemas distintos entre sí → error.
- Columnas ausentes → sigue invalidando el CSV completo, sin cambios.
- `ID_CLIENT` nulo en alguna fila → error estructural, detiene el run
  completo (nuevo respecto al comportamiento actual, donde solo invalidaba
  ese fichero).
- Tipos inválidos (sigue generando `NON_NUMERIC_VALUES`, sin cambios).
- Nulos, ceros, negativos (sin cambios de semántica; test de que la
  partición por cliente no altera el resultado fila a fila respecto al modo
  legacy con el mismo contenido).

### Clientes

- Un cliente (equivalente al modo legacy; debe producir un resultado
  bit-a-bit comparable, salvo el nombre de carpeta).
- Varios clientes.
- ID ausente del catálogo (fallback `Cliente {id}`).
- Nombre con espacios exteriores en la fuente (verificar que el catálogo ya
  llega recortado y que el loader no depende de un segundo `strip()`).
- Nombre con acentos (p. ej. "Aldelís", "Compañía Alfaro" del catálogo real
  depurado).
- Nombre con `/`, `\`, `:`, comillas u otros caracteres (ninguno en el
  catálogo real actual, pero sintético en tests: verificar que el slug los
  sustituye y el nombre visible los conserva).
- Colisión de slugs (dos nombres que normalizan igual, verificar que el
  prefijo `{id}-` los distingue; usar como referencia real los pares
  `10503`/`10537` y `10618`/`10724` del catálogo depurado).
- `n_entries` del catálogo calculado dinámicamente para catálogos de tamaño
  distinto de 228 (para confirmar que no hay ningún tamaño hardcodeado).

### Scope

- Varios batches válidos con clientes diferentes (caso esperado, sin
  incidencia por cliente, WARNING global de heterogeneidad).
- Un cliente con más de una combinación batch/run/source-run y
  `ID_CONFIGURATION` **disjuntas** entre combinaciones → **bloqueado**
  (`AMBIGUOUS_CLIENT_EXECUTION`, detiene el run completo). Caso
  explícitamente cambiado respecto a una versión anterior de este plan, que
  lo admitía con un WARNING: ya no existe esa excepción.
- Un cliente con más de una combinación batch/run/source-run y
  `ID_CONFIGURATION` **solapadas** → bloqueado, mismo tratamiento.
- Un cliente repetido en dos runs (`ID_RUN_STAGING` distinto) → bloqueado.
- Configuraciones duplicadas dentro de la misma combinación batch/run/source-run
  (ya cubierto por `check_duplicate_key` existente, verificar que sigue
  aplicando tras particionar, y que también es un error estructural que
  detiene el run completo, no solo ese cliente).
- Ventana temporal: tests solo ejecutables tras Fase 0 (con `RUN_START_DATE`
  disponible): mismo `ID_CLIENT` con dos `RUN_START_DATE` → error
  estructural; dos clientes del mismo análisis global con `RUN_START_DATE`
  distinto → error estructural. Hasta entonces, no hay test posible más allá
  de confirmar que la comprobación está deliberadamente ausente/bloqueada.

### Métricas

- 6M filtrado por `COMPARISON_STATUS == 'COMPARABLE'` como universo real
  (nuevo comportamiento, sección 5.10) — reemplaza el test anterior de "la
  máscara propia es el universo y `COMPARISON_STATUS` solo se audita".
- Desglose de discrepancia máscara-propia-vs-`COMPARISON_STATUS` como
  auditoría (nueva función `check_comparison_status_discrepancy_breakdown`).
- Máscara por periodos (mensual, trimestral) sin cambios de fondo.
- Empate (`both_wape_zero_mask`, sin cambios).
- Winner improvement (`WINNER_IMPROVEMENT_PCT_*` del backend, nuevo: test de
  que se expone tal cual, sin recalcular bajo ninguna circunstancia).
- ML vs. SCP improvement (renombrado de salida, mismo cálculo).
- Denominador cero (`CASE_SCP_ZERO_ML_POSITIVE`, sin cambios).
- Nulos (`CASE_MISSING_WAPE`, sin cambios).
- Negativos (nuevo `check_negative_wape`).

### Outputs

- HTML global con varios clientes resueltos desde un único CSV.
- HTML por cliente con `folder_name = {id}-{slug}`.
- Navegación anterior/siguiente por `ID_CLIENT` ascendente.
- Carpeta con `ID_CLIENT` en el nombre (verificar que dos clientes con
  nombre similar no colisionan, usando los pares reales del catálogo
  depurado).
- Manifest: bloque `clients` en `csv_files[i]`, bloque `client_catalog` con
  `n_entries` dinámico, campos de observabilidad de tamaño/duración,
  `manifest_schema_version` incrementado.
- Hash del CSV único (sigue calculándose una vez, verificar que se referencia
  desde N clientes).
- Hash del catálogo (`client_catalog.sha256` en manifest).
- Publicación transaccional (reutiliza los tests existentes de
  `test_run_publish.py`, sin necesidad de casos nuevos porque el mecanismo
  no cambia).
- **Run fallido por error estructural:** un cliente `AMBIGUOUS_CLIENT_EXECUTION`,
  un esquema inválido, o una mezcla incompatible de CSV (sección 5.4) hacen
  fallar el **run completo** (código de salida `1`, manifest `FAILED`, sin
  publicación, directorio temporal conservado con las combinaciones
  conflictivas documentadas) — **no** se publican los demás clientes válidos
  del mismo CSV. Este test reemplaza al de una versión anterior de este plan
  que esperaba aislamiento por cliente para este caso.
- Run con un fallo aislado no estructural en un cliente (p. ej. excepción
  inesperada al generar un gráfico de un cliente ya validado): el resto de
  clientes sí se publican, como hoy.

## 5.16 Fases de implementación

### Fase 0 — Completar contrato del backend

- **Objetivo:** obtener `RUN_START_DATE` en `TA_FOV_SCP_ML_SERIES_COMPARISON`
  y en la exportación CSV, prerrequisito de la validación de ventana
  temporal (sección 5.6). Esta fase ocurre mayoritariamente **fuera de este
  repositorio**, en `scp-backend`.
- **Archivos:** en `scp-backend` (fuera de alcance de este repositorio):
  tabla `TA_FOV_SCP_ML_SERIES_COMPARISON` y su construcción
  (`ForecastOptimizerValidationStagingCopyService.RefreshSeriesComparisonAsync`,
  ver `docs/backend-validation-flow.md`), y el procedimiento de exportación
  a CSV. En este repositorio: `docs/backend-validation-flow.md` (una vez el
  backend confirme el cambio, documentar el nuevo campo y su semántica,
  análogo a como ya se documentó `COMPARISON_STATUS`).
- **Cambios:**
  - Añadir `RUN_START_DATE` a la tabla `TA_FOV_SCP_ML_SERIES_COMPARISON` en
    el backend.
  - Rellenarla desde la ejecución real (el backend ya calcula
    internamente `M6 = RUN_START_DATE`, `M1 = RUN_START_DATE + 5 meses`; solo
    falta persistirla en la tabla de comparación).
  - Incluirla en la tabla de comparación y en la exportación CSV completa.
  - Actualizar `docs/backend-validation-flow.md` con la evidencia del
    cambio (sección de columnas, convención mensual).
  - Generar un CSV real de prueba exportado desde
    `TA_FOV_SCP_ML_SERIES_COMPARISON` con `RUN_START_DATE` ya poblado, para
    validar el contrato objetivo antes de implementar el consumo en
    reporting.
  - **En este repositorio, diferido a cuando se implemente el consumo**
    (Fase 2, no en esta fase): actualizar `periods.STATIC_REQUIRED_COLUMNS`
    y las fixtures sintéticas de `tests/factories.py` para incluir
    `RUN_START_DATE` como columna obligatoria (contrato objetivo de 235
    columnas, salvo que la revisión real del backend determine otro ajuste
    adicional).
- **Riesgos:** depende de un equipo/repositorio externo
  (`imperia-scm/scp-backend`); sin fecha de entrega controlable desde este
  plan. Mientras no se complete, **Fase 2 no puede comenzar** (sección 5.6,
  sección 5.16): ni la validación de ventana temporal ni el resto de la
  clasificación/validación de scope multi-cliente se implementan, y el modo
  legacy con varios CSV directos sigue sin poder verificar su condición (4)
  con certeza (sección 5.4). El pipeline actual permanece sin cambios
  mientras tanto.
- **Tests:** ninguno en este repositorio durante la fase (el CSV de prueba
  real se usa para validar Fase 2 una vez esta fase concluya).
- **Criterio de aceptación:** existe un CSV real exportado desde
  `TA_FOV_SCP_ML_SERIES_COMPARISON` con `RUN_START_DATE` poblado para al
  menos un batch de prueba, y `docs/backend-validation-flow.md` documenta el
  cambio con el mismo nivel de evidencia que el resto del documento
  (confirmado por código/evidencia manual, no solo declarado).
- **Commit atómico propuesto:** ninguno de código en este repositorio; si
  procede, `docs(backend): document RUN_START_DATE addition to
  TA_FOV_SCP_ML_SERIES_COMPARISON` una vez el backend confirme el cambio y
  se actualice `docs/backend-validation-flow.md`.

### Fase 1 — Catálogo y modelo de identidad

- **Objetivo:** disponer de `config/client-catalog.json` (catálogo
  definitivo de 228 entradas, ya depurado) consumible por código, sin tocar
  el pipeline analítico.
- **Archivos:** nuevo `src/client_catalog.py`.
- **Cambios:** `load_client_catalog`, `resolve_client_name`, saneamiento de
  slug reutilizando `input_loader.normalize_folder_name`; `n_entries`
  siempre calculado como `len(catalog)`, nunca hardcodeado.
- **Riesgos:** bajo; módulo aislado sin dependencias de dominio.
- **Pruebas:** `tests/test_client_catalog.py` (catálogo ausente, vacío,
  corrupto, con IDs numéricos como string, con catálogos de tamaño
  arbitrario para confirmar que `n_entries` nunca se hardcodea).
- **Criterio de aceptación:** `resolve_client_name` nunca lanza, siempre
  devuelve una cadena no vacía, y el catálogo definitivo real
  (`config/client-catalog.json`, 228 entradas) se carga sin warnings.
- **Commit atómico propuesto:** `feat(catalog): load client-catalog.json with id-based fallback`.

### Fase 2 — Loader multi-cliente y validación de scope

- **Prerrequisito bloqueante:** esta fase **no comienza hasta que Fase 0
  entregue `RUN_START_DATE`** (sección 5.16, sección 5.6). No existe una
  versión previa de esta fase que implemente la clasificación de escenarios
  (sección 5.4) o la validación de combinaciones batch/run/source-run
  (sección 5.6) sin poder implementar, a la vez, la comprobación de igualdad
  de ventana temporal: se entregan juntas para que esa comprobación sea
  obligatoria desde el primer momento, sin ningún estado intermedio
  "parcialmente verificable". Hasta que este prerrequisito se cumpla, el
  pipeline sigue comportándose exactamente como hoy (`docs/reporting-flow.md`).
- **Objetivo:** clasificar el escenario de entrada (sección 5.4), cargar un
  CSV completo una vez y particionarlo por `ID_CLIENT`, con la validación de
  ejecución lógica única y de ventana temporal de la sección 5.6.
- **Archivos:** `src/input_loader.py` (clasificación de escenario, nueva
  función de partición), `src/quality_checks.py`
  (`check_ambiguous_client_execution`, ajuste de
  `check_duplicate_client_across_files`/`check_batch_heterogeneity`),
  `src/periods.py` (`RUN_START_DATE` como columna obligatoria, ver Fase 0).
- **Cambios:** ver secciones 5.4, 5.5 y 5.6 completas, incluida la
  comprobación de ventana temporal como parte obligatoria del entregable
  (no diferida a una fase posterior).
- **Riesgos:** alto (es el núcleo del cambio); mitigado con tests
  exhaustivos de scope antes de tocar el orquestador.
- **Pruebas:** `tests/test_input_loader.py` (casos multi-cliente y de
  clasificación de escenario), `tests/test_scope_validation.py` (nuevo,
  incluidos casos de `RUN_START_DATE` distinto dentro de un cliente y entre
  clientes del análisis global).
- **Criterio de aceptación:** un CSV sintético de 3 clientes con
  combinaciones batch/run limpias y el mismo `RUN_START_DATE` produce 3
  particiones válidas bit-a-bit-equivalentes a 3 CSV separados procesados en
  modo legacy (mismos totales de candidatas/comparables/WAPE por periodo);
  un cliente con más de una combinación batch/run/source-run (disjunta o
  solapada) produce `AMBIGUOUS_CLIENT_EXECUTION` y detiene la clasificación
  antes de generar ningún output; un dataset con `RUN_START_DATE` distinto
  entre clientes detiene el run completo como error estructural.
- **Commit atómico propuesto:** `feat(loader): partition multi-client CSV by ID_CLIENT with scope and window validation`.

### Fase 3 — Orquestación global y por cliente

- **Objetivo:** adaptar `analysis_fov_scp_ml.run_pipeline` para consumir la
  lista de particiones en vez de la lista de ficheros, deteniendo el run
  completo ante un error estructural (sección 5.8) y aislando solo los
  fallos no estructurales por cliente.
- **Archivos:** `analysis_fov_scp_ml.py`, `src/global_analysis.py` (sin
  cambio de firma, solo de origen de datos).
- **Cambios:** bucle de procesamiento por partición; nueva fase de log
  `SCOPE_VALIDATION` que, si falla, detiene el run antes de
  `CLIENT_PROCESSING` (análoga a la fase `INVENTORY` actual cuando no hay
  CSV); clasificación del escenario de entrada según la sección 5.4.
- **Riesgos:** alto (orquestador central; cualquier regresión afecta a
  todos los outputs).
- **Pruebas:** `tests/test_pipeline_runs.py` (nuevos casos end-to-end con
  CSV sintético multi-cliente, incluidos los de fallo estructural completo).
- **Criterio de aceptación:** ejecución completa sobre un CSV sintético
  multi-cliente válido termina con código de salida 0 y publica un run; una
  ejecución sobre un CSV con un conflicto de scope termina con código de
  salida 1, sin publicar nada; el modo legacy (1 CSV = 1 cliente procesado
  de uno en uno, incluidos los 24 CSV reales de `data/exportacion_*`) sigue
  produciendo exactamente los mismos resultados que antes de esta fase
  (regresión cero). Nota: cargar los 24 CSV históricos **todos a la vez** en
  el mismo `--input-dir` no es el patrón de uso documentado y quedaría sujeto
  a las cuatro condiciones de la sección 5.4 como cualquier otro conjunto de
  varios CSV directos.
- **Commit atómico propuesto:** `feat(pipeline): orchestrate multi-client CSV with structural-error run abort`.

### Fase 4 — Reconciliación metodológica

- **Objetivo:** cambiar el universo analítico de 6M a
  `COMPARISON_STATUS == 'COMPARABLE'` (sección 5.10), exponer
  `WINNER_IMPROVEMENT_PCT` del backend sin recalcularlo, y alinear nombres y
  mensajes con las decisiones de las secciones 5.10 y 5.11, todo ello con
  cambios funcionales reales (no solo documentación).
- **Archivos:** `src/client_analysis.py` (`_analyze_period` para 6M),
  `src/quality_checks.py` (`check_winner_formula_not_auditable`, nueva
  `check_comparison_status_discrepancy_breakdown`, nueva
  `check_negative_wape`), `src/metrics.py` (renombrado de salida a
  `ML_VS_SCP_IMPROVEMENT_PCT`), exposición de `WINNER_IMPROVEMENT_PCT_*` del
  backend como métrica adicional en Excel/Markdown/HTML.
- **Cambios:** ver secciones 5.10 y 5.11 completas.
- **Riesgos:** medio-alto: cambia resultados numéricos de 6M (universo
  comparable) además de nombres de columnas visibles en Excel/Markdown; hay
  que revisar con cuidado que el cambio de universo no rompa tests que
  asuman la máscara propia como fuente de verdad de 6M.
- **Pruebas:** `tests/test_metrics.py`, `tests/test_quality_checks.py`,
  `tests/test_client_analysis.py`, `tests/test_excel_writer.py`,
  `tests/test_report_writer.py`.
- **Criterio de aceptación:** las métricas de 6M (cobertura, WAPE, mejora,
  ganadores) se calculan sobre `COMPARISON_STATUS == 'COMPARABLE'`, con la
  máscara propia expuesta únicamente como desglose de auditoría; ningún test
  compara `WINNER_METHOD_*` / `WINNER_MODEL_*` recalculado (siguen siendo
  fuente de verdad sin reconstrucción); `check_winner_formula_not_auditable`
  deja de afirmar que la fórmula "no está documentada" y pasa a explicar que
  está documentada en el backend pero no se reconstruye por decisión de
  diseño (fuente de verdad = columna original).
- **Commit atómico propuesto:** `feat(metrics): distinguish backend winner improvement from ML vs SCP improvement`.

### Fase 5 — Outputs, manifest y navegación

- **Objetivo:** propagar nombre/slug/carpeta basados en catálogo a
  Excel/Markdown/HTML/manifest, e incorporar los nuevos campos de
  observabilidad de tamaño/duración.
- **Archivos:** `src/html_view_models.py`, `src/html_report.py`,
  `src/manifest.py`, `src/execution_summary.py`,
  `src/global_analysis.py` (columna `ETIQUETA`), `src/excel_writer.py`,
  `src/report_writer.py`, `src/global_excel_writer.py`,
  `src/global_report_writer.py`.
- **Cambios:** ver secciones 5.7, 5.9 y 5.12 completas (incluidos los nuevos
  campos `n_entries` dinámico, tamaño en bytes/filas/clientes por CSV, y
  duración de carga).
- **Riesgos:** medio-alto: toca prácticamente todos los generadores de
  salida; alto valor de regresión visual (recomendado revisar manualmente
  un HTML generado antes de dar la fase por cerrada, coherente con la
  sección "Forma de trabajo" de `CLAUDE.md`).
- **Pruebas:** `tests/test_html_report.py`, `tests/test_manifest.py`,
  `tests/test_execution_summary.py`, `tests/test_global_analysis.py`,
  `tests/test_excel_writer.py`, `tests/test_report_writer.py`,
  `tests/test_run_catalog.py` (verificar que sigue tolerando
  `manifest_schema_version` incrementado).
- **Criterio de aceptación:** un run publicado con un CSV multi-cliente
  sintético produce HTML navegable offline (validado con
  `html_report.validate_run_links`), con carpetas `{id}-{slug}` sin
  colisiones, y el manifest incluye el bloque `client_catalog` completo con
  `n_entries` calculado dinámicamente y los nuevos campos de tamaño/duración.
- **Commit atómico propuesto:** `feat(outputs): resolve client display names and folders via client-catalog.json`.

### Fase 6 — Validación end-to-end

- **Objetivo:** confirmar el comportamiento sobre un dataset representativo
  antes de considerar el modo multi-cliente listo para uso operativo.
- **Archivos:** ninguno de producción; solo ejecución y revisión.
- **Cambios:** ninguno de código (fase de validación pura).
- **Distinción obligatoria entre tipos de CSV usados en esta fase:**
  - **CSV sintético:** válido únicamente para los tests unitarios y de
    integración de las Fases 1-5 (`tests/test_input_loader.py`,
    `tests/test_scope_validation.py`, `tests/test_pipeline_runs.py`, etc.).
    No es válido para la aceptación end-to-end de esta fase.
  - **CSV real exportado desde `TA_FOV_SCP_ML_SERIES_COMPARISON`, con
    `RUN_START_DATE` poblado:** **obligatorio** para la aceptación
    end-to-end operativa de esta fase. No se sustituye por un CSV sintético
    ni siquiera de forma provisional: si el CSV real de prueba de Fase 0 no
    está disponible, esta fase permanece **bloqueada y pendiente**, no se
    da por completada con un dataset sintético como aproximación.
- **Riesgos:** bajo en código, alto en confianza operativa si se acepta esta
  fase sin el CSV real, o si se sustituye por uno sintético.
- **Pruebas:** ejecución real del pipeline sobre el CSV real de prueba
  exportado desde `TA_FOV_SCP_ML_SERIES_COMPARISON` generado en Fase 0 (con
  `RUN_START_DATE` ya poblado); comparación de los agregados globales (WAPE
  ponderado, mejora por cliente/serie) frente al baseline conocido de
  ejecutar los CSV históricos equivalentes en modo legacy; revisión visual
  manual del HTML publicado; registro y revisión de los nuevos campos de
  observabilidad de tamaño/duración del manifest para informar, en el
  futuro, la decisión de un límite operativo o el uso de *chunks*.
- **Criterio de aceptación:** los agregados globales del modo multi-cliente
  sobre el CSV real de prueba (con `RUN_START_DATE`) coinciden, dentro de
  las tolerancias numéricas ya definidas (`NUMERIC_ABS_TOLERANCE=1e-6`,
  `NUMERIC_REL_TOLERANCE=1e-4`), con los agregados del modo legacy sobre los
  mismos datos. Esta fase no se considera completada si la comparación se
  realizó solo sobre un CSV sintético.
- **Commit atómico propuesto:** ninguno de código; documentar el resultado
  de la validación en el PR/commit final de la Fase 5, o en un commit de
  solo documentación si se detectan hallazgos.

## 5.17 Criterios de aceptación globales

- Un único CSV multi-cliente se procesa sin dividirlo manualmente.
- Cada `ID_CLIENT` válido produce un informe individual (Excel, Markdown,
  PNG, HTML, log).
- El informe global usa todos los clientes válidos del CSV único.
- Varios batches con clientes diferentes son aceptados sin incidencia por
  cliente (solo WARNING informativo de heterogeneidad).
- Un cliente con más de una combinación `(ID_BATCH, ID_RUN_STAGING,
  SOURCE_RUN_ID)` — con o sin solape de `ID_CONFIGURATION` — nunca se mezcla:
  detiene el **run completo** con `AMBIGUOUS_CLIENT_EXECUTION`, mostrando
  todas las combinaciones conflictivas; no se publica un run que excluya
  silenciosamente a ese cliente y publique el resto.
- Varios CSV directos solo se admiten como modo legacy si cumplen las cuatro
  condiciones cerradas de la sección 5.4; cualquier incumplimiento detiene
  el run completo.
- Las ventanas temporales incompatibles (una vez `RUN_START_DATE` exista,
  Fase 0) nunca se agregan silenciosamente: son siempre un error estructural
  que detiene el run completo, nunca un WARNING.
- El nombre de cliente procede de `config/client-catalog.json` cuando el
  `ID_CLIENT` existe en el catálogo definitivo (228 entradas).
- Un `ID_CLIENT` desconocido en el catálogo usa el fallback `Cliente {id}`,
  sin error.
- El catálogo nunca filtra qué clientes se procesan: la pertenencia al CSV
  es la única condición de procesamiento.
- `n_entries` del catálogo se calcula siempre dinámicamente; no queda hardcodeado
  en código ni en el manifest; el valor 228 indicado en este documento describe
  únicamente el estado actual del catálogo.
- No hay llamadas HTTP en ningún punto del pipeline de reporting.
- No hay acceso SQL en ningún punto del pipeline de reporting.
- Para 6M, `COMPARISON_STATUS == 'COMPARABLE'` es el filtro real de la
  población comparable (numerador y métricas); la máscara propia queda
  únicamente como auditoría de discrepancias.
- `WINNER_IMPROVEMENT_PCT` (backend, ganador vs. finalista) y
  `ML_VS_SCP_IMPROVEMENT_PCT` (reporting, ML vs. SCP) están diferenciadas
  por nombre en todos los outputs; `WINNER_IMPROVEMENT_PCT` nunca se
  recalcula.
- El manifest registra tamaño en bytes, número de filas, número de clientes,
  duración de carga y duración total del run, sin que este plan establezca
  todavía un límite operativo de tamaño.
- Outputs y publicación transaccional permanecen exactamente como hoy
  (`outputs/runs/<run-name>/`, `.tmp`/`.backup`/`.publish_complete`).
- Los HTML siguen funcionando offline como carpeta completa, validados por
  `html_report.validate_run_links`.

## 5.18 Preguntas abiertas

Solo se listarían aquí decisiones que el código o los documentos disponibles
(`docs/backend-validation-flow.md`, `docs/reporting-flow.md`) no permitan
resolver por sí mismos, y que no contradigan ninguna decisión ya cerrada en
este documento (secciones 5.1 a 5.17). Las cuatro preguntas de una versión
anterior de este plan (ventana temporal sin `RUN_START_DATE`, umbral para
particiones disjuntas, umbral de tamaño/memoria, y alcance de limpieza del
catálogo) han quedado resueltas por las decisiones cerradas en esta
revisión: Fase 0 (sección 5.16) resuelve la primera; la eliminación completa
de la excepción de particiones disjuntas (sección 5.6) resuelve la segunda;
el registro de observabilidad sin límite rígido todavía (secciones 5.12 y
5.17) resuelve la tercera; y el catálogo definitivo de 228 entradas (sección
5.7) resuelve la cuarta.

No quedan preguntas abiertas para iniciar la implementación por fases.
