# FOV SCP vs ML Analysis

Pipeline reproducible que compara, de forma retrospectiva, la precision y
cobertura de dos flujos de forecast:

- **SCP**: flujo automatico de forecast actualmente utilizado.
- **ML**: pipeline Optimizer/ML de clasificacion, seleccion y routing de
  modelos (el termino "ML" identifica el pipeline de seleccion/routing, no
  implica que todos los modelos seleccionados sean algoritmos de machine
  learning).

El objetivo es producir evidencia clara, auditable e interpretable sobre
donde ML mejora frente a SCP y donde SCP sigue siendo superior, tanto por
cliente como en una comparativa global entre clientes.

La especificacion funcional completa esta en
[`docs/analysis_requirements.md`](docs/analysis_requirements.md).

## Instalacion

Requiere Python 3.11+ (probado con 3.13).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No requiere conexion a bases de datos ni a servicios externos.

## Ejecucion

```powershell
python analysis_fov_scp_ml.py
```

El script:

1. Descubre automaticamente todos los `*.csv` de `data/` (nunca hardcodea la
   lista de clientes).
2. Valida cada CSV de forma aislada: un fichero invalido no bloquea a los
   demas.
3. Ejecuta el nucleo de analisis (cobertura, comparabilidad especifica por
   periodo, WAPE global ponderado, mejora relativa, ganadores).
4. Genera el Excel, el informe Markdown, los graficos y el log de cada
   cliente valido en `outputs/<CLIENTE>/`.
5. Calcula la comparativa global entre todos los clientes con fichero valido
   y genera el Excel, el informe Markdown y los graficos globales en
   `outputs/global/`.
6. Genera `outputs/execution_summary.md` y `outputs/execution_summary.xlsx`
   (una fila por CSV descubierto, valido o no).

No modifica nunca los CSV originales de `data/`.

### Tests

```powershell
python -m pytest
```

Los tests usan datos sinteticos (`tests/factories.py`); ninguno depende de
los CSV reales de `data/`.

## Estructura de `data/`

Un CSV por cliente, con el prefijo `TA_FOV_SCP_ML_` seguido del `ID_CLIENT`
y una etiqueta legible, por ejemplo:

```text
data/
  TA_FOV_SCP_ML_10204_SKLUM.csv
  TA_FOV_SCP_ML_10461_Garcia_Millan.csv
  ...
```

El cliente se identifica siempre desde el contenido (`ID_CLIENT`), nunca
solo desde el nombre del fichero; si no coinciden, se registra un WARNING.

### Defecto de formato conocido

Algunos CSV de origen tienen cada linea fisica (cabecera y filas) envuelta
en una capa extra de comillas CSV (comillas dobladas). `src/input_loader.py`
lo detecta de forma defensiva (comprobando que la cabecera sigue el patron
antes de reparar) y lo normaliza en memoria sin modificar el fichero
original. Queda registrado como `WRAPPED_CSV_NORMALIZED` (WARNING) en los
chequeos de calidad de cada cliente.

## Estructura de `outputs/`

```text
outputs/
  <CLIENTE>/                                  # p.ej. 10204_SKLUM
    fov_scp_ml_summary_<CLIENTE>.xlsx         # Excel individual, 14 pestanas
    fov_scp_ml_report_<CLIENTE>.md            # Informe individual, 18 secciones
    processing_log_<CLIENTE>.txt              # Log de procesamiento
    charts/
      coverage/  semester/  quarters/  monthly/
      models/  classifications/  impact_and_risk/

  global/
    fov_scp_ml_global_summary.xlsx            # Excel global, 16 pestanas
    fov_scp_ml_global_report.md               # Informe global, 21 secciones
    charts/
      coverage/  semester/  quarters/  monthly/
      clients/  models/  classifications/  impact_and_risk/

  execution_summary.md
  execution_summary.xlsx
```

Un cliente sin ninguna serie comparable (p.ej. `COMPARISON_STATUS =
NOT_COMPARABLE_MISSING_VALIDATION` en todas sus filas) genera igualmente su
carpeta y sus outputs: es un caso valido de cobertura, no un error, y sus
secciones de performance quedan vacias por diseno en vez de contener
metricas inventadas. Este cliente:

- SI se incluye en cobertura (universo `HAS_BASE_CANDIDATE = 1`).
- SI se incluye en los chequeos de calidad.
- SI aparece en las tablas por cliente (individuales y globales).
- SI aparece siempre en `execution_summary`.
- NO participa en las medias, medianas ni frecuencia de victoria de mejora
  por cliente o por serie (perspectivas 2 y 3): aporta `NaN` (no 0), y su
  exclusion se refleja siempre como `N_CLIENTES_SIN_PERFORMANCE` (denominador
  explicito), nunca de forma silenciosa.
- NO aporta fila a las tablas de reduccion ni deterioro de la perspectiva 4
  (impacto absoluto y concentracion), al no tener `ABS_ERROR_REDUCTION`
  calculable.
- SI aporta al WAPE global ponderado (perspectiva 1) de forma neutra: al no
  tener historico ni error en ninguna fila comparable, su contribucion a
  `SUM(historico)` y `SUM(error_absoluto)` es 0 (no-op), sin distorsionar el
  ratio.

No queda excluido de las cuatro perspectivas globales como bloque: solo
queda fuera del calculo en las que exigen performance por serie o por
cliente (2, 3 y 4).

## Convencion temporal

Identificadores tecnicos (se usan siempre en codigo, columnas y
validaciones): `M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `RECENT_3M`, `OLDER_3M`,
`6M`.

- `M1` es el mes cerrado mas reciente; `M6` es el mas antiguo de la ventana.
- `RECENT_3M` = `M1 + M2 + M3`.
- `OLDER_3M` = `M4 + M5 + M6`.
- `6M` = `M1 + ... + M6`.

Etiquetas visibles (solo en informes, titulos y graficos; nunca en codigo):

| Tecnico     | Visible                                |
| ----------- | --------------------------------------- |
| `RECENT_3M` | Primer trimestre del semestre (M1-M3)  |
| `OLDER_3M`  | Segundo trimestre del semestre (M4-M6) |
| `6M`        | Semestre completo (M1-M6)              |

No se usan en textos visibles expresiones como "trimestre reciente",
"trimestre anterior", "Q1" o "Q2": los dos trimestres son bloques internos
del semestre retrospectivo, no trimestres naturales del calendario.

## Formulas principales

```text
WAPE_GLOBAL = SUM(error_absoluto_total) / SUM(historico_total)
```

Ponderado por volumen; **nunca** se calcula como promedio simple de los WAPE
por serie (ver "Principios metodologicos" mas abajo).

```text
ML_IMPROVEMENT_VS_SCP_PCT = (SCP_WAPE - ML_WAPE) / SCP_WAPE * 100
ABS_ERROR_REDUCTION       = SCP_TOTAL_ABS_ERROR - ML_TOTAL_ABS_ERROR
```

`ML_IMPROVEMENT_VS_SCP_PCT` no se calcula cuando `SCP_WAPE` es
computacionalmente cero (tolerancia `1e-9`, para evitar que ruido de punto
flotante dispare porcentajes absurdos al dividir por un denominador casi
nulo); ver `src/metrics.py`.

## Reglas de comparabilidad

- Universo de cobertura: todas las filas con `HAS_BASE_CANDIDATE = 1`.
- Universo de performance: mascara **especifica de cada periodo** (no se
  reutiliza la misma mascara para todos los periodos ni se usa unicamente
  `COMPARISON_STATUS = 'COMPARABLE'`). Una fila es comparable en un periodo
  cuando pertenece al universo candidato, tiene historico > 0 en ese periodo,
  y dispone de forecast/error/WAPE validos para SCP y para ML en ese
  periodo. Los trimestres y el semestre usan directamente las columnas
  agregadas `TOTAL_*` ya materializadas en el CSV.
- `WINNER_METHOD_*` (columna original del CSV) es siempre la fuente de
  verdad del ganador. La formula exacta de `relativeDiff` usada para
  generarla (regla de negocio: TIE cuando `relativeDiff < 0.0001`, salvo
  ambos WAPE=0 que siempre es TIE) no esta documentada en este repositorio:
  no se reconstruye ni se inventa ese umbral. Solo se audita el caso
  totalmente especificado de ambos WAPE=0.

## Principios metodologicos

Se distinguen siempre, sin mezclarlas:

- cobertura;
- impacto global ponderado (perspectiva 1: `SUM(abs_error) / SUM(historico)`);
- mejora media y mediana **por cliente** (perspectiva 2: cada cliente pesa
  igual, no se pondera por numero de series);
- mejora media y mediana **por serie** (perspectiva 3: recalculada desde las
  filas comparables originales, no reconstruida desde medianas por cliente);
- frecuencia de victoria (% de series que gana cada metodo);
- reduccion absoluta de error y concentracion por cliente (perspectiva 4).

No se afirma que ML mejora de forma generalizada basandose unicamente en el
WAPE global ponderado: es posible (y ocurre en los datos reales de este
repositorio) que el WAPE global empeore por la concentracion de volumen en
un unico cliente, mientras la mayoria de clientes y series mejoran. El
informe global distingue explicitamente estas lecturas.

## Chequeos de calidad

Tres niveles: `OK`, `WARNING`, `ERROR`. Un `ERROR` de fichero invalida al
cliente completo (no se calcula ningun periodo); un `ERROR` o `WARNING` de
periodo/fila queda localizado a ese periodo o esas filas, y **nunca**
invalida el cliente completo por si solo. Incluyen, entre otros:
legibilidad del CSV, columnas obligatorias, cliente unico por CSV,
coincidencia nombre-vs-`ID_CLIENT`, duplicados de clave logica,
reconstruccion de `SIGNED_ERROR`/`ABS_ERROR`/`SQUARED_ERROR`/MAE/RMSE/Bias,
historico negativo, WAPE y mejora extremos, heterogeneidad de `ID_BATCH`
entre clientes, y posible mojibake en columnas de texto. El detalle completo
esta en `src/quality_checks.py` y en la pestana `13_data_quality_checks` /
`15_data_quality_checks` de cada Excel.

## Arquitectura del codigo

```text
analysis_fov_scp_ml.py      # orquestador: descubrimiento -> analisis -> outputs
src/
  input_loader.py            # descubrimiento y lectura defensiva de CSV
  periods.py                 # mapeo centralizado periodo -> columnas
  metrics.py                 # WAPE ponderado, mejora relativa, reduccion absoluta
  quality_checks.py          # modelo de severidad y chequeos estructurales/numericos
  client_analysis.py         # nucleo de analisis por cliente y periodo
  models.py                  # analisis de modelos, clasificaciones y rankings
  excel_writer.py            # Excel individual (14 pestanas)
  report_writer.py           # Markdown individual (18 secciones)
  charts.py                  # graficos individuales (7 subcarpetas)
  logging_utils.py           # log de procesamiento por cliente
  global_analysis.py         # comparativa global (4 perspectivas)
  global_excel_writer.py     # Excel global (16 pestanas)
  global_report_writer.py    # Markdown global (21 secciones)
  global_charts.py           # graficos globales (8 subcarpetas)
  execution_summary.py       # execution_summary.md / .xlsx
tests/                        # tests unitarios con datos sinteticos
```

## Restricciones del proyecto

- No se conecta a bases de datos ni a APIs/servicios externos.
- No usa rutas absolutas dentro del codigo (siempre `pathlib`, relativo a
  `Path(__file__).resolve().parent`).
- Compatible con Windows y PowerShell.
- Evita bucles fila a fila cuando pandas permite vectorizacion.
- Cierra siempre todas las figuras de matplotlib.
