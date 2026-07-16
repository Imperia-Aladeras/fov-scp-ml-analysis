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

## Ejecucion (Fase 5A: ejecuciones aisladas y reproducibles)

```powershell
python analysis_fov_scp_ml.py
```

Sin argumentos, el comando reproduce el comportamiento historico: lee de
`data/` y crea una ejecucion nueva con timestamp en
`outputs/runs/<YYYYMMDD_HHMMSS>/`. **Nunca** reutiliza ni sobrescribe
automaticamente la antigua carpeta `outputs/` (los resultados legacy en
`outputs/<CLIENTE>/` y `outputs/global/` no se tocan).

El pipeline es reutilizable sobre cualquier carpeta de CSV mediante
parametros de linea de comandos:

```powershell
python analysis_fov_scp_ml.py `
  --input-dir "C:\Datos\ValidacionSeptiembre" `
  --output-root "C:\Informes\FOV\runs" `
  --run-name "validacion_septiembre_2026"
```

### Parametros

| Parametro | Por defecto | Descripcion |
|-|-|-|
| `--input-dir` | `<repo>/data` | Carpeta con los CSV de entrada. |
| `--output-root` | `<repo>/outputs/runs` | Carpeta raiz donde se publican las ejecuciones. |
| `--run-name` | timestamp `YYYYMMDD_HHMMSS` | Nombre de la ejecucion. Se sanea (ver mas abajo). |
| `--overwrite` | desactivado | Permite sustituir una ejecucion existente con el mismo nombre. |
| `--copy-inputs` | desactivado | Copia los CSV originales dentro de la ejecucion (`inputs/`). |
| `--open-report` | desactivado | Abre `index.html` en el navegador por defecto tras publicar la ejecucion. Ver [Informe HTML](#informe-html-fase-5b). |
| `--rebuild-run-index` | desactivado | Modo separado (Fase 5C): reconstruye unicamente el catalogo de `--output-root`, sin analizar CSV. Ver [Catálogo de ejecuciones](#catálogo-de-ejecuciones-fase-5c). |

### Saneamiento de `--run-name`

- Caracteres benignos prohibidos en Windows (`<>:"|?*` y caracteres de
  control) se sustituyen por `_` de forma predecible.
- Se **rechaza** (codigo de salida `2`, sin procesar ningun CSV) cualquier
  patron peligroso: separador de directorios (`/` o `\`), drive de Windows
  (`C:`), o el propio `..` como nombre completo. Estos patrones no se
  sanean: un nombre de ejecucion nunca puede crear subcarpetas ni escapar de
  `--output-root`.
- Se limita la longitud a 100 caracteres y se evitan los nombres reservados
  de Windows (`CON`, `NUL`, `COM1`...).
- Si el resultado saneado queda vacio, se usa el timestamp actual.
- Se verifica ademas que el directorio temporal y el final de la ejecucion
  son siempre hijos directos de `--output-root` (defensa adicional, no
  deberia poder violarse por construccion).

### Estructura de una ejecucion

```text
<output-root>/
  <run-name>/
    manifest.json              # metadata completa y trazable de la ejecucion
    run_config.json            # configuracion efectiva de la ejecucion
    execution.log               # log global (fase, entrada, salida, duracion, warnings/errores)
    execution_summary.md
    execution_summary.xlsx

    index.html                  # informe HTML global (Fase 5B): ver seccion dedicada mas abajo
    assets/
      styles.css                 # unico CSS local, offline, compartido por todas las paginas

    global/
      fov_scp_ml_global_summary.xlsx   # 16 pestanas
      fov_scp_ml_global_report.md      # 21 secciones
      charts/

    clients/
      <CLIENTE>/
        index.html                          # ficha HTML del cliente (Fase 5B)
        fov_scp_ml_summary_<CLIENTE>.xlsx   # 14 pestanas
        fov_scp_ml_report_<CLIENTE>.md      # 18 secciones
        processing_log_<CLIENTE>.txt
        charts/

    inputs/
      ...                       # solo con --copy-inputs: copia exacta de los CSV originales
```

### Publicacion atomica

La ejecucion se escribe primero en un directorio temporal oculto
(`<output-root>/.<run-name>.tmp/`). Solo cuando el procesamiento termina
correctamente se renombra a `<output-root>/<run-name>/`. Una ejecucion
interrumpida (proceso matado, excepcion no controlada) nunca aparece como
publicada: el directorio final simplemente no existe, y el temporal se
conserva intacto para diagnostico (incluye `execution.log` con el
traceback completo y `manifest.json` con `status: "FAILED"`, la fase donde
ocurrio el fallo, el tipo y el mensaje de error).

### Comportamiento de `--overwrite`

- Sin `--overwrite`: si ya existe una ejecucion con el mismo nombre (el
  directorio final) o un directorio temporal de una ejecucion anterior
  interrumpida con el mismo nombre, el pipeline **falla antes de procesar
  ningun CSV** con codigo de salida `2`. Nada se elimina automaticamente.
- Con `--overwrite`: un directorio temporal huerfano se elimina
  explicitamente (se informa por consola). La ejecucion final anterior
  **no se borra de inmediato**: se conserva mediante un backup temporal
  hasta que la nueva ejecucion ha quedado publicada con exito. Si la
  publicacion final fallara, la ejecucion anterior se restaura
  automaticamente y no se pierde; la nueva ejecucion (fallida) queda
  intacta en su directorio temporal para diagnostico.

### `--copy-inputs`

Copia los CSV originales (bytes identicos, `shutil.copy2`) dentro de
`<run>/inputs/`. Sin este flag, los CSV de entrada no se duplican: la
trazabilidad se mantiene igualmente via SHA-256 en `manifest.json`.

### `manifest.json`

El inventario de CSV de entrada (nombre, ruta relativa, tamano, fecha de
modificacion, SHA-256) se construye **antes** de `load_client_sources`, se
conserva durante toda la ejecucion y es la unica fuente de hashes del
manifest: nunca se vuelve a descubrir ni a hashear al final. Con
`--copy-inputs`, la copia archivada se verifica byte a byte contra el
original inmediatamente despues de copiar, y `analyzed_source` vale `"copy"`
para cada CSV; sin `--copy-inputs`, se procesan los originales y, al
terminar, se vuelven a comprobar (tamano y SHA-256); si alguno cambio
durante la ejecucion, la ejecucion falla (`INPUT_CHANGED_DURING_RUN`), el
manifest queda `FAILED` y **no** se publica el resultado.

Contiene, entre otros campos: `run_name`, `status`
(`SUCCESS`/`SUCCESS_WITH_WARNINGS`/`FAILED`), `published` (booleano),
`started_at`/`finished_at` (ISO 8601 con zona horaria local),
`duration_seconds`, `pipeline_version`, `git_commit` y `git_worktree_dirty`
(ambos `null` si Git no esta disponible o el directorio no es un
repositorio; si el working tree tiene cambios sin commit la ejecucion no
falla, solo se registra el warning en `execution.log` y el campo queda en
`true` — nunca se almacena el diff, solo el booleano), `input_dir`,
`output_dir_final` (ruta final, real o prevista) y `output_dir_working`
(el directorio temporal mientras la ejecucion no este publicada, `null` en
cuanto lo esta), cifras agregadas (CSV descubiertos, clientes
totales/validos/evaluables en 6M/sin performance en 6M, batches detectados,
filas totales, series candidatas, series comparables en 6M,
warnings/errores totales), la lista de outputs generados, y una entrada
`csv_files` con **un elemento por cada CSV descubierto** (incluso si no
pudo convertirse en un cliente valido): nombre, ruta relativa, tamano en
bytes, fecha de modificacion, SHA-256 (todo calculado sobre los bytes
originales **antes** de cualquier intento de parseo), `analyzed_source`
(`"original"` o `"copy"`), mas `id_client`/etiqueta/filas/estado/
warnings/errores cuando el CSV pudo procesarse. `outputs_generated` incluye
tambien `index.html`, cada `clients/<CLIENTE>/index.html` y `assets/styles.css`
(ver [Informe HTML](#informe-html-fase-5b)). Si la ejecucion falla,
incluye un bloque `failure` con `phase`, `error_type` y `error_message`; el
manifest se actualiza inmediatamente antes o despues de la publicacion para
que `published`/`output_dir_working` reflejen el estado real final.

## Informe HTML (Fase 5B)

Cada ejecucion publica, ademas del Excel/Markdown/graficos/logs de Fase 5A,
un informe HTML estatico, navegable y **completamente offline**:
`<run>/index.html` (global) y una ficha `<run>/clients/<CLIENTE>/index.html`
por cada CSV que llego a producir un resultado de analisis (valido o
invalido). El HTML es una capa de presentacion sobre los resultados ya
calculados en memoria: nunca relee Excel, Markdown, logs ni `manifest.json`
de disco, y nunca recalcula WAPE, MAE, RMSE, Bias, ganadores, mejoras,
cobertura ni impactos absolutos.

### Funcionamiento offline

- No requiere conexion a internet, servidor local ni Python en ejecucion:
  se abre haciendo doble clic en `index.html`.
- Un unico CSS local (`assets/styles.css`), sin CDN, sin fuentes remotas, sin
  JavaScript de terceros. La navegacion principal y todas las secciones son
  utilizables con JavaScript desactivado (solo se usan elementos nativos:
  `<details>`, anclas, tablas).
- Los graficos referencian los PNG ya generados por `src/charts.py` /
  `src/global_charts.py` mediante rutas relativas; nunca se referencia un PNG
  que no exista, y nunca se convierten los graficos a base64 en bloque.
- Todos los `href`/`src` son rutas relativas con `/` (nunca rutas absolutas
  de Windows, `file:///...`, URLs `http(s)://`, ni esquemas `javascript:` o
  `data:`). Los segmentos con espacios o acentos se codifican con
  porcentaje (`%20`, `%C3%B1`...) sin romper el enlace.

### Portabilidad

La carpeta completa de una ejecucion publicada (`<run>/`, con `index.html`,
`assets/`, `global/`, `clients/`) se puede copiar, comprimir, descomprimir o
mover a otra ubicacion (otro equipo, otra unidad) sin que se rompa ningun
enlace interno: todas las rutas son relativas entre si, nunca absolutas ni
dependientes del equipo donde se genero. `src/html_report.py` incluye un
validador de enlaces (`validate_run_links`) que se ejecuta automaticamente
durante la generacion y que los tests reutilizan para comprobar los enlaces
tambien despues de mover una copia de una ejecucion.

### Pagina global (`index.html`)

Cabecera de ejecucion, resumen ejecutivo (con numerador y denominador
explicitos, p.ej. "6 de 7 clientes evaluables mejoran; 2 sin performance"),
perspectivas diferenciadas (impacto ponderado, mejora por cliente, mejora
por serie, frecuencia de victoria, impacto absoluto, cobertura — nunca
mezcladas en una unica conclusion), evolucion mensual, graficos globales,
tabla de clientes (con enlace a su ficha cuando existe) e inventario de
archivos de entrada (incluye los CSV que no llegaron a producir un cliente,
sin inventar metricas ni carpeta para ellos), metodologia y limitaciones, y
enlaces a los ficheros de la ejecucion (Excel/Markdown globales,
`execution_summary`, `manifest.json`, `execution.log`).

### Ficha de cliente (`clients/<CLIENTE>/index.html`)

Identificacion, conclusion, cobertura por periodo, semestre completo y los
dos trimestres usando siempre las etiquetas "Semestre completo (M1-M6)",
"Primer trimestre del semestre (M1-M3)" y "Segundo trimestre del semestre
(M4-M6)", evolucion mensual, modelos, clasificaciones, impacto absoluto y
casos destacados, exclusiones, limitaciones, graficos y enlaces al Excel,
Markdown y log de ese cliente. Navegacion cliente anterior/siguiente en
orden deterministico (por nombre de fichero).

- Un cliente **sin performance calculable** (cobertura sin ninguna serie
  comparable) muestra una explicacion textual, nunca WAPE o mejora en cero.
- Un cliente **invalido** (fichero no valido) muestra una pagina de
  diagnostico con sus errores de calidad, sin secciones estadisticas
  ficticias.

### `--open-report`

```powershell
python analysis_fov_scp_ml.py `
  --input-dir "C:\Datos\Validacion" `
  --output-root "C:\Informes\FOV\runs" `
  --run-name "validacion_septiembre_2026" `
  --open-report
```

Abre `<run_dir_final>/index.html` en el navegador por defecto (via
`webbrowser`), y **solo** despues de que la publicacion transaccional haya
terminado con exito (`.publish_complete` ya existe): nunca abre el HTML del
directorio temporal. Es una accion de conveniencia estrictamente posterior
a la publicacion: si el navegador no puede abrirse (excepcion o `False`),
se muestra un aviso por consola y, si es posible, se anade una linea al
`execution.log` ya publicado, pero la ejecucion sigue devolviendo el codigo
de salida `0`, `.publish_complete` no se borra y el manifiesto no cambia a
`FAILED`. El valor de `--open-report` queda registrado en `run_config.json`.

### Integracion con la publicacion transaccional

El HTML y sus assets se generan **dentro del directorio temporal**
(`<run_dir_temp>/`), como una fase mas del pipeline (`HTML_REPORT`, entre
`EXECUTION_SUMMARY` y `MANIFEST`), y se incluyen en `outputs_generated` /
`manifest.json` igual que el resto de ficheros. Si la generacion del HTML
falla (incluida la validacion de enlaces), es un fallo global: la ejecucion
no se publica, el directorio temporal se conserva integro para diagnostico
y nunca se entrega un `index.html` a medias.

### Jerarquia de consulta de los outputs

- **HTML** (`index.html`, `clients/<CLIENTE>/index.html`): consulta
  rutinaria y navegable, punto de entrada recomendado.
- **Excel** (`fov_scp_ml_*_summary*.xlsx`): analisis detallado, filtros y
  tablas dinamicas.
- **Markdown** (`fov_scp_ml_*_report*.md`): auditoria y versionado legible
  en diffs de texto.
- **Logs** (`processing_log_*.txt`, `execution.log`): diagnostico tecnico.
- **`manifest.json`**: trazabilidad y reproducibilidad (hashes, procedencia
  Git, estado de publicacion).

### Codigos de salida

- `0`: ejecucion completada, aunque existan warnings o clientes aislados.
- `1`: fallo global durante el procesamiento (incluye cero CSV
  descubiertos) o fallo al publicar la ejecucion.
- `2`: error de configuracion o argumentos (incluye `--run-name` peligroso,
  `--input-dir` inexistente, y colision de ejecucion sin `--overwrite`).

### Migracion respecto a la estructura legacy

Las carpetas `outputs/<CLIENTE>/`, `outputs/global/` y
`outputs/execution_summary.*` generadas en fases anteriores (Fase 1-4) se
mantienen tal cual, versionadas en git, como snapshot historico. El pipeline
ya no escribe ahi por defecto: toda ejecucion nueva (con o sin argumentos)
se publica en `outputs/runs/<run-name>/` con la estructura descrita arriba.
`outputs/runs/` esta excluido de git (`.gitignore`): cada ejecucion se traza
operativamente mediante su propio `manifest.json`, los SHA-256 de sus CSV de
entrada, `pipeline_version` y el commit de Git, no mediante el control de
versiones del working tree.

El pipeline:

1. Descubre automaticamente todos los `*.csv` de `--input-dir` (nunca
   hardcodea la lista de clientes).
2. Valida cada CSV de forma aislada: un fichero invalido no bloquea a los
   demas.
3. Ejecuta el nucleo de analisis (cobertura, comparabilidad especifica por
   periodo, WAPE global ponderado, mejora relativa, ganadores).
4. Genera el Excel, el informe Markdown, los graficos y el log de cada
   cliente valido en `<run>/clients/<CLIENTE>/`.
5. Calcula la comparativa global entre todos los clientes con fichero valido
   y genera el Excel, el informe Markdown y los graficos globales en
   `<run>/global/`.
6. Genera `<run>/execution_summary.md`, `<run>/execution_summary.xlsx`,
   `<run>/manifest.json`, `<run>/run_config.json` y `<run>/execution.log`.
7. Genera el informe HTML estatico y offline (`<run>/index.html` y
   `<run>/clients/<CLIENTE>/index.html`, ver
   [Informe HTML](#informe-html-fase-5b)).
8. Publica la ejecucion de forma atomica (ver arriba).
9. Tras publicar, reconstruye automaticamente el catalogo historico de
   `--output-root` (ver [Catálogo de ejecuciones](#catálogo-de-ejecuciones-fase-5c)).
   Un fallo en este paso no invalida la ejecucion ya publicada.

No modifica nunca los CSV originales de `--input-dir`.

## Catálogo de ejecuciones (Fase 5C)

Cada `--output-root` mantiene, ademas de sus ejecuciones, un catalogo
historico estatico y offline en `<output-root>/index.html`: un indice
operativo de todas las ejecuciones publicadas, pensado para encontrar
rapidamente la ultima validacion o comparar de un vistazo el estado de
varias ejecuciones, sin abrir cada una por separado.

El catalogo es una capa de presentacion sobre `manifest.json`: **nunca**
vuelve a leer CSV, **nunca** recalcula metricas, **nunca** abre Excel ni
Markdown, **nunca** analiza logs y **nunca** compara estadisticamente unas
ejecuciones con otras (eso queda fuera de alcance de la Fase 5C). Solo
utiliza, por cada carpeta directamente dentro de `--output-root`:
`manifest.json`, la presencia de `.publish_complete` y la existencia de
`index.html`.

### Estructura

```text
<output-root>/
  index.html              # catalogo: indice de ejecuciones publicadas
  run_index.log             # registro del ultimo escaneo (incluidos/ignorados/motivos)
  catalog_assets/
    styles.css               # CSS local propio del catalogo (no el de ningun run)

  <run_1>/
    index.html  manifest.json  .publish_complete  ...
  <run_2>/
    ...
```

Todos los enlaces del catalogo son relativos (`<run>/index.html`,
`catalog_assets/styles.css`): la carpeta completa de `--output-root` se
puede copiar, comprimir o mover sin romper ningun enlace.

### Criterio de ejecucion valida

Una carpeta hija directa de `--output-root` se incluye en el catalogo
**unicamente** cuando: no empieza por `.` (excluye `.<run>.tmp` y
`.<run>.backup`), no es `catalog_assets/`, contiene `.publish_complete`,
contiene un `manifest.json` valido (JSON parseable), `manifest["published"]
== true`, `manifest["status"] != "FAILED"`, y contiene `index.html`. Nunca
se confia unicamente en `manifest["published"]`: todas las condiciones
deben cumplirse a la vez. Si el nombre de la carpeta no coincide con
`manifest["run_name"]`, la ejecucion se incluye igualmente, con un warning
`CATALOG_RUN_NAME_MISMATCH`. Ninguna carpeta que no cumpla el criterio se
elimina ni se modifica: simplemente no aparece en la tabla, y el motivo
queda registrado en `run_index.log`.

### Compatibilidad con manifests historicos

El catalogo lee manifests generados por fases anteriores (Fase 5A, Fase
5B) sin fallar: si un manifest no tiene `catalog_summary` (el bloque que la
Fase 5C anadio a `manifest.json`), la ejecucion se incluye igualmente, con
un warning `CATALOG_FIELDS_MISSING`, y sus metricas 6M se muestran como
`N/D` (nunca inventadas ni convertidas en 0). No se vuelve a procesar
ningun CSV para completar los datos ausentes.

### `manifest_schema_version` y `catalog_summary`

Cada `manifest.json` nuevo incluye `manifest_schema_version` (version del
**esquema** del manifiesto; distinta de `pipeline_version`, que versiona el
propio pipeline de analisis) y un bloque `catalog_summary` estable, pensado
para que el catalogo nunca tenga que recalcular nada:

```json
{
  "manifest_schema_version": 2,
  "catalog_summary": {
    "clients_total": 9,
    "clients_evaluable_6m": 7,
    "clients_without_performance_6m": 2,
    "series_candidates_6m": 20539,
    "series_comparable_6m": 7881,
    "coverage_pct_6m": 38.37,
    "wape_scp_6m": 0.5642,
    "wape_ml_6m": 0.6310,
    "weighted_improvement_pct_6m": -11.9,
    "net_error_reduction_6m": -19668843.908,
    "warnings_total": 123,
    "errors_total": 0
  }
}
```

Todos los valores de `catalog_summary` provienen de campos **ya
calculados** por `GlobalAnalysisResult`/`ExecutionRecord` (ver
`src/manifest.py`): `manifest.py` no repite ningun calculo estadistico. Un
valor ausente se serializa como `null` (nunca como `0`). No es necesario
ni se recomienda modificar retroactivamente manifests ya publicados.

### Orden y "Ultima ejecucion completada"

Las ejecuciones se ordenan por `finished_at` descendente; si falta, por
`started_at` descendente; como desempate deterministico, por nombre de
ejecucion. Los timestamps se parsean respetando su zona horaria (ISO 8601
con offset). Una ejecucion con timestamp invalido o ausente **no se
excluye**: se coloca al final, se muestra como `N/D` y se registra un
warning `CATALOG_INVALID_TIMESTAMP`. La seccion "Ultima ejecucion
completada" reutiliza la primera fila de ese mismo orden: nunca se calcula
por separado ni con un criterio distinto.

### Incidencias del escaneo

`run_index.log` registra, en cada reconstruccion: timestamp, numero de
directorios inspeccionados, ejecuciones incluidas e ignoradas (con motivo),
warnings de compatibilidad y de timestamp invalido. La pagina del catalogo
incluye un resumen (totales) y un detalle desplegable; nunca muestra
tracebacks completos (esos quedan solo en `run_index.log`).

### `--rebuild-run-index`

```powershell
python analysis_fov_scp_ml.py `
  --rebuild-run-index `
  --output-root "C:\Informes\FOV\runs"
```

Modo separado que **no** descubre CSV, **no** calcula clientes, **no** crea
ningun run ni directorio temporal de run, y **no** modifica ningun
`manifest.json` ni `.publish_complete` existente: solo reconstruye
`index.html` y `run_index.log` a partir de las ejecuciones ya publicadas.
En este modo **solo** se admite `--output-root`; `--input-dir`,
`--run-name`, `--overwrite`, `--copy-inputs` y `--open-report` son
incompatibles (el parser de este modo ni siquiera los reconoce, por lo que
usarlos junto a `--rebuild-run-index` termina en un error de "argumento no
reconocido"). Codigos de salida: `0` catalogo reconstruido; `1` fallo de
reconstruccion; `2` argumentos incompatibles.

### Reconstruccion automatica tras publicar

Tras cada `publish_run()` con exito, el pipeline intenta reconstruir el
catalogo de `--output-root` automaticamente, **antes** de procesar
`--open-report`. Es una operacion derivada, fuera del directorio del run:
nunca se anade al `manifest.json` del run ni a su `outputs_generated`. Si
falla (p.ej. un problema de disco al escribir el catalogo), el run **ya
publicado sigue siendo valido**: no se revierte, `.publish_complete` no se
borra, el manifest no cambia a `FAILED`, y el codigo de salida del analisis
sigue siendo `0`. Se muestra un aviso claro por consola (con el comando
`--rebuild-run-index` exacto para reintentarlo) y, de forma best-effort, se
anade una linea al `execution.log` ya publicado del run.

### Generacion atomica

`index.html`/`run_index.log` se escriben primero como `.tmp` en el mismo
`--output-root`; solo se sustituyen los ficheros definitivos (`os.replace`,
`index.html` en ultimo lugar) si la generacion **y** la validacion de
enlaces del catalogo terminan con exito. Si algo falla en cualquier punto,
el catalogo anterior (si existia) queda completamente intacto y no se toca
ningun run. La validacion de enlaces del catalogo comprueba unicamente el
HTML que se esta generando (nunca vuelve a recorrer ni revalidar el
contenido de cada run historico, que ya se valido cuando ese run se
publico, ver [Informe HTML](#informe-html-fase-5b)).

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

## Guías operativas

### Ejecutar una nueva validación

```powershell
python analysis_fov_scp_ml.py `
  --input-dir "C:\Datos\Validacion" `
  --output-root "C:\Informes\FOV\runs" `
  --run-name "validacion_septiembre_2026"
```

Publica una ejecución nueva, aislada y versionada en
`<output-root>\validacion_septiembre_2026\`, y actualiza automáticamente el
catálogo de `<output-root>\index.html`.

### Consultar una ejecución

- Abre `<run>\index.html` (doble clic): punto de entrada recomendado,
  navegable y offline.
- Usa el **Excel** (`fov_scp_ml_*_summary*.xlsx`) para análisis detallado,
  filtros y tablas dinámicas.
- Usa el **Markdown** (`fov_scp_ml_*_report*.md`) para auditoría y
  versionado legible en diffs de texto.
- Usa los **logs** (`processing_log_*.txt`, `execution.log`) para
  diagnóstico técnico.
- Usa `manifest.json` para trazabilidad (hashes de los CSV de entrada,
  commit de Git, estado de publicación).

### Consultar el histórico

Abre `<output-root>\index.html`: incluye la sección "Última ejecución
completada", la tabla completa ordenada por fecha de finalización
descendente, y una sección de incidencias del escaneo. `N/D` significa que
esa métrica no existe para esa ejecución (nunca que valga cero); es
especialmente frecuente en ejecuciones publicadas antes de la Fase 5C (ver
[Catálogo de ejecuciones](#catálogo-de-ejecuciones-fase-5c)).

### Reconstruir el catálogo

```powershell
python analysis_fov_scp_ml.py `
  --rebuild-run-index `
  --output-root "C:\Informes\FOV\runs"
```

Útil si el catálogo no se actualizó automáticamente (por ejemplo, tras un
fallo puntual de disco), o tras mover/restaurar manualmente ejecuciones
dentro de `--output-root`. No analiza ningún CSV ni crea ninguna ejecución
nueva.

### Repetir una ejecución

Vuelve a ejecutar el mismo comando con un `--run-name` distinto (o sin
`--run-name`, para usar el timestamp automático): cada ejecución queda
aislada, y ambas aparecen por separado en el catálogo.

### Sobrescribir una ejecución

Añade `--overwrite` para sustituir una ejecución existente con el mismo
`--run-name`. La ejecución anterior se conserva en un backup temporal hasta
que la nueva termina de publicarse con éxito (ver la sección
"Comportamiento de `--overwrite`" más arriba); el catálogo, tras la
reconstrucción automática, muestra una única fila con los datos del
manifiesto más reciente.

### Archivar inputs

Añade `--copy-inputs` para copiar los CSV originales dentro de
`<run>\inputs\` (verificados byte a byte tras la copia). Sin este flag, la
trazabilidad de los CSV de entrada se mantiene igualmente vía SHA-256 en
`manifest.json`; el catálogo nunca depende de la carpeta `inputs\`.

### Diagnosticar errores

- Código de salida `1`: revisa `execution.log` dentro del directorio
  temporal indicado en consola (`<output-root>\.<run-name>.tmp\`); incluye
  la fase donde falló y el traceback completo.
- Código de salida `2`: error de configuración detectado antes de tocar
  disco (revisa el mensaje de consola: `--run-name` peligroso,
  `--input-dir` inexistente, colisión sin `--overwrite`, o argumento
  incompatible con `--rebuild-run-index`).
- Si el catálogo no se actualizó tras una ejecución publicada con éxito
  (código `0` pero sin aviso de "Catálogo actualizado"), revisa el aviso
  por consola y el `execution.log` **ya publicado** de ese run, y
  reconstruye manualmente con `--rebuild-run-index`.

### Mover o compartir resultados

Tanto `<run>\` como `<output-root>\` completo se pueden copiar, comprimir o
mover a otra ubicación sin romper ningún enlace: todas las rutas dentro del
HTML (informe por ejecución y catálogo) son relativas. No es necesario
mover ni conservar `inputs\`, `manifest.json` ni ningún otro fichero
concreto por separado: basta con la carpeta completa.

### Outputs legacy

`data/` y las carpetas `outputs/<CLIENTE>/`, `outputs/global/`,
`outputs/execution_summary.md`, `outputs/execution_summary.xlsx`
(generadas en las Fases 1-4, antes de las ejecuciones versionadas) **no**
forman parte del catálogo ni de ninguna estructura de ejecución
reproducible:

- No tienen `manifest.json` ni `.publish_complete`, por lo que
  `scan_output_root()` nunca podría registrarlas como una ejecución válida
  aunque estuvieran dentro de `--output-root` (no lo están: viven en
  `outputs/`, no en `outputs/runs/`).
- No pueden convertirse retroactivamente en una ejecución versionada: no
  existe forma de reconstruir su `manifest.json` (hashes de los CSV
  originales en el momento exacto de esa ejecución, commit de Git, etc.)
  sin volver a ejecutar el pipeline sobre los CSV correspondientes.
- Para obtener un equivalente versionado y catalogable, genera una
  ejecución nueva sobre los CSV actuales de `data/` (ver
  [Ejecutar una nueva validación](#ejecutar-una-nueva-validación) más
  arriba, sin `--input-dir` para usar `data/` por defecto).
- **No se implementa ninguna migración automática ni destructiva**: este
  proyecto nunca borra ni mueve `data/` ni `outputs/<CLIENTE>/` /
  `outputs/global/` por sí mismo.
- Qué puede eliminarse manualmente: una vez verificada una nueva ejecución
  versionada equivalente (mismos CSV, resultados revisados), las carpetas
  legacy en `outputs/` pueden eliminarse manualmente si ya no se necesitan
  como referencia inmediata.
- Qué conviene conservar por auditoría: si esos outputs legacy fueron la
  base de una decisión o entrega ya comunicada, consérvalos (están
  versionados en git como snapshot histórico) aunque exista una ejecución
  nueva equivalente; el historial de git ya documenta cuándo y por qué se
  generaron.
- `outputs/runs/` (excluida de git, ver `.gitignore`) es la estructura
  operativa vigente: toda ejecución nueva, con o sin argumentos, se publica
  ahí, con su propio `manifest.json` como fuente de trazabilidad.

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
  input_inventory.py         # inventario inmutable de CSV (tamano, mtime, SHA-256)
  manifest.py                 # manifest.json + procedencia Git
  run_config.py               # RunConfig, CLI y saneamiento de --run-name
  run_publish.py              # publicacion atomica y reconciliacion tras interrupcion
  html_formatters.py          # formatters centralizados para el informe HTML (N/D, %, es-ES)
  html_view_models.py         # traduce ClientAnalysisResult/GlobalAnalysisResult/ExecutionRecord a datos para las plantillas
  html_report.py              # orquestacion del HTML (Fase 5B): paginas, assets, validacion de enlaces
  run_catalog_models.py       # traduce manifest.json (nunca ClientAnalysisResult/GlobalAnalysisResult) a filas del catalogo
  run_catalog.py               # catalogo historico (Fase 5C): descubrimiento, orden, reconstruccion atomica
templates/                    # plantillas Jinja2 (autoescape) del informe HTML y del catalogo
  base.html  global_report.html  client_report.html  components/  run_catalog.html
report_assets/
  styles.css                  # CSS local unico del informe HTML por ejecucion
  catalog_styles.css           # CSS local unico del catalogo (independiente de cada run)
tests/                        # tests unitarios con datos sinteticos
```

## Restricciones del proyecto

- No se conecta a bases de datos ni a APIs/servicios externos.
- No usa rutas absolutas dentro del codigo (siempre `pathlib`, relativo a
  `Path(__file__).resolve().parent`).
- Compatible con Windows y PowerShell.
- Evita bucles fila a fila cuando pandas permite vectorizacion.
- Cierra siempre todas las figuras de matplotlib.
