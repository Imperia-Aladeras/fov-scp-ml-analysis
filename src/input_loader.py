"""
Descubrimiento y carga de los CSV de entrada (uno por cliente, en data/).

No se modifican nunca los ficheros originales: toda reparacion de formato
ocurre en memoria, sobre el contenido leido.

Defecto de formato conocido (ver Fase 1): los CSV de origen tienen cada
linea fisica (cabecera y filas) envuelta en una capa extra de comillas CSV
(la linea completa entre comillas, con las comillas internas dobladas). Un
`pandas.read_csv` estandar no puede parsear esto correctamente.

Tres niveles de validacion, deliberadamente separados (no se usa un numero
arbitrario de columnas como criterio principal):

    1. Parseable como CSV: pandas ha podido tokenizar el fichero en mas de
       una columna. Si colapsa en una unica columna (el modo de fallo real
       observado en estos CSV), NO es parseable, independientemente de
       cuantas columnas "deberia" tener el esquema real.
    2. Columnas de identificacion minimas: contiene al menos ID_CLIENT e
       ID_CONFIGURATION, suficientes para identificar cliente y grano.
    3. Esquema completo requerido para el analisis: se valida aparte, en
       quality_checks.check_required_columns, sobre la lista completa de
       periods.all_required_columns().

`read_csv_defensive` intenta primero una lectura estandar. Si no supera los
niveles 1+2, comprueba defensivamente si el fichero sigue el patron de
envoltorio de comillas dobladas esperado (cabecera + una proporcion alta de
lineas de datos) ANTES de aplicar la reparacion: no se repara cualquier CSV
cuya lectura estandar falle, solo los que coinciden con el patron conocido.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.periods import all_required_columns
from src.quality_checks import (
    QualityReport,
    StructuralInputError,
    check_batch_heterogeneity,
    check_csv_readable,
    check_dtypes,
    check_duplicate_client_across_files,
    check_duplicate_key,
    check_filename_matches_id,
    check_mojibake_in_value_levels,
    check_required_columns,
    check_single_client,
    check_wrapped_csv_normalized,
    QualityIssue,
    Severity,
)

FILENAME_PREFIX = "TA_FOV_SCP_ML_"
KEY_COLUMNS = ["ID_BATCH", "ID_RUN_STAGING", "ID_CLIENT", "SOURCE_RUN_ID", "ID_CONFIGURATION"]
# Columnas que definen la ejecucion logica de un ID_CLIENT (Fase 2): para
# cada cliente debe existir exactamente una combinacion de estas tres.
SCOPE_COLUMNS = ["ID_BATCH", "ID_RUN_STAGING", "SOURCE_RUN_ID"]

# Nivel 2: columnas minimas para identificar cliente y grano de la fila.
# Deliberadamente NO es "> 50 columnas": ese umbral era un numero arbitrario
# ligado al tamano del esquema real (234 columnas) y fallaba con CSV validos
# mas pequenos (p.ej. los usados en tests sinteticos). Aqui solo se exige lo
# minimo para poder identificar la fila; el esquema completo se valida por
# separado con check_required_columns (nivel 3).
MINIMAL_IDENTIFICATION_COLUMNS = ["ID_CLIENT", "ID_CONFIGURATION"]

# Deteccion defensiva del envoltorio de comillas dobladas (item 5): la
# condicion necesaria y suficiente para que la lectura estandar colapse en
# una unica columna es que la CABECERA este envuelta (es la primera linea
# que pandas tokeniza para fijar el numero de columnas). Se comprueba
# explicitamente antes de reparar. La proporcion de lineas de datos
# envueltas es variable entre ficheros reales observados:
#   - en algunos, todas las lineas (cabecera y filas) estan envueltas;
#   - en otros, solo la cabecera lo esta y las filas de datos ya son CSV
#     plano estandar.
# Por eso el ratio de lineas envueltas se calcula y se reporta (en
# WRAPPED_CSV_NORMALIZED) como informacion de auditoria, pero NO se usa como
# unico criterio para decidir si reparar: la cabecera envuelta es la senal
# fiable, y el resultado de la reparacion se valida de nuevo (nivel 1+2)
# antes de aceptarlo, lo que evita aplicar la reparacion a un CSV realmente
# distinto que por casualidad tenga una cabecera que empiece y acabe en
# comillas por una unica columna citada de forma legitima.
WRAP_PATTERN_SAMPLE_SIZE = 200

# Subconjunto numerico de las columnas requeridas, usado para el chequeo de
# tipos de datos y la conversion explicita (se excluyen columnas categoricas
# como WINNER_METHOD_*, WINNER_MODEL_*, FINALIST_METHOD_*, FINALIST_MODEL_*,
# ML_BEST_MODEL, etc.).
_CATEGORICAL_SUFFIXES = ("WINNER_METHOD", "WINNER_MODEL", "FINALIST_METHOD", "FINALIST_MODEL")
_CATEGORICAL_COLUMNS = {
    "ID_CONFIGURATION", "VALUE_LEVEL_1", "VALUE_LEVEL_2", "VALUE_LEVEL_3", "VALUE_LEVEL_4", "VALUE_LEVEL_5",
    "ML_BEST_MODEL", "ML_CLASSIFICATION", "ML_TYPE", "ML_STATUS",
    "SCP_BEST_MODEL", "SCP_CLASSIFICATION", "SCP_STATUS", "SERIES_CLASSIFICATION",
    "COMPARISON_STATUS", "ML_EXCLUSION_REASON", "SCP_NO_OUTPUT_REASON", "COPIED_AT",
}


def numeric_required_columns() -> list[str]:
    cols = []
    for col in all_required_columns():
        if col in _CATEGORICAL_COLUMNS:
            continue
        if any(col.startswith(prefix) for prefix in _CATEGORICAL_SUFFIXES):
            continue
        cols.append(col)
    return cols


def discover_csv_files(data_dir: Path) -> list[Path]:
    """Descubre automaticamente todos los *.csv de data/, sin lista hardcodeada."""
    return sorted(data_dir.glob("*.csv"))


def extract_label_from_filename(path: Path) -> str:
    """
    `TA_FOV_SCP_ML_10204_SKLUM.csv` -> `10204_SKLUM`.
    Elimina el prefijo TA_FOV_SCP_ML_ y la extension .csv.
    """
    name = path.name
    if name.startswith(FILENAME_PREFIX):
        name = name[len(FILENAME_PREFIX):]
    if name.lower().endswith(".csv"):
        name = name[:-4]
    return name


def extract_id_from_label(label: str) -> int | None:
    """Extrae el ID numerico inicial de la etiqueta (p.ej. '10204_SKLUM' -> 10204)."""
    match = re.match(r"^(\d+)", label)
    return int(match.group(1)) if match else None


_WINDOWS_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')


def normalize_folder_name(label: str) -> str:
    """Normaliza caracteres incompatibles con rutas de Windows, conservando guiones bajos."""
    normalized = _WINDOWS_FORBIDDEN_CHARS.sub("_", label)
    normalized = normalized.strip().strip(".")
    return normalized or "UNKNOWN_CLIENT"


def unwrap_double_quoted_line(line: str) -> str:
    """
    Repara una linea fisica envuelta en una capa extra de comillas CSV:
    quita la comilla envolvente y des-escapa las comillas dobladas ("" -> ").
    Si la linea no esta envuelta en comillas, se devuelve sin cambios.
    """
    stripped = line.rstrip("\r\n")
    if _line_is_wrapped(stripped):
        return stripped[1:-1].replace('""', '"')
    return stripped


def _line_is_wrapped(stripped_line: str) -> bool:
    return len(stripped_line) >= 2 and stripped_line.startswith('"') and stripped_line.endswith('"')


def _header_is_wrapped(physical_lines: list[str]) -> bool:
    if not physical_lines:
        return False
    return _line_is_wrapped(physical_lines[0].rstrip("\r\n"))


def _wrap_pattern_ratio(physical_lines: list[str]) -> float:
    if not physical_lines:
        return 0.0
    sample = physical_lines[:WRAP_PATTERN_SAMPLE_SIZE]
    matches = sum(1 for line in sample if _line_is_wrapped(line.rstrip("\r\n")))
    return matches / len(sample)


def is_parseable_as_csv(df: pd.DataFrame | None) -> bool:
    """Nivel 1: pandas ha tokenizado el fichero en mas de una columna (no ha colapsado en un unico campo)."""
    return df is not None and len(df.columns) > 1


def has_identification_columns(df: pd.DataFrame | None) -> bool:
    """Nivel 2: contiene las columnas minimas para identificar cliente y grano."""
    if df is None:
        return False
    return all(c in df.columns for c in MINIMAL_IDENTIFICATION_COLUMNS)


def _is_usable(df: pd.DataFrame | None) -> bool:
    return is_parseable_as_csv(df) and has_identification_columns(df)


def _attempt_read_path(path: Path) -> tuple[pd.DataFrame | None, int | None, str | None]:
    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    except Exception as exc:
        return None, None, str(exc)
    return df, len(df.columns), None


def _attempt_read_text(text: str) -> tuple[pd.DataFrame | None, int | None, str | None]:
    try:
        df = pd.read_csv(io.StringIO(text), low_memory=False)
    except Exception as exc:
        return None, None, str(exc)
    return df, len(df.columns), None


def _decode_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_bytes().decode("utf-8-sig"), None
    except UnicodeDecodeError as exc:
        return None, f"Error de decodificacion UTF-8: {exc}"


@dataclass
class CsvLoadResult:
    dataframe: pd.DataFrame | None
    repaired: bool
    standard_columns_count: int | None
    standard_reject_reason: str | None
    repaired_columns_count: int | None
    n_rows_recovered: int | None
    error: str | None


def read_csv_defensive(path: Path) -> CsvLoadResult:
    """
    Intenta primero una lectura estandar (nivel 1+2). Si no es usable,
    comprueba defensivamente si el fichero sigue el patron de envoltorio de
    comillas dobladas antes de aplicar la reparacion. Nunca modifica el
    fichero original.
    """
    df_std, cols_std, err_std = _attempt_read_path(path)
    if _is_usable(df_std):
        return CsvLoadResult(
            dataframe=df_std, repaired=False, standard_columns_count=cols_std,
            standard_reject_reason=None, repaired_columns_count=None,
            n_rows_recovered=len(df_std), error=None,
        )

    if not is_parseable_as_csv(df_std):
        reject_reason = err_std or (
            f"La lectura estandar no genero una tokenizacion CSV valida "
            f"(columnas obtenidas: {cols_std if cols_std is not None else 0})."
        )
    else:
        reject_reason = (
            f"La lectura estandar produjo {cols_std} columnas pero sin las columnas de "
            f"identificacion minimas {MINIMAL_IDENTIFICATION_COLUMNS}."
        )

    text, decode_error = _decode_text(path)
    if text is None:
        return CsvLoadResult(
            dataframe=None, repaired=False, standard_columns_count=cols_std,
            standard_reject_reason=reject_reason, repaired_columns_count=None,
            n_rows_recovered=None, error=decode_error,
        )

    physical_lines = [line for line in text.split("\n") if line.strip() != ""]
    if not _header_is_wrapped(physical_lines):
        return CsvLoadResult(
            dataframe=None, repaired=False, standard_columns_count=cols_std,
            standard_reject_reason=reject_reason, repaired_columns_count=None,
            n_rows_recovered=None,
            error=(
                f"{reject_reason} La cabecera tampoco sigue el patron de comillas dobladas esperado "
                f"(no empieza y termina en comilla); no se aplica ninguna reparacion."
            ),
        )

    # La cabecera confirma el patron conocido. La reparacion linea a linea es
    # un no-op para cualquier linea que no siga el patron (unwrap_double_quoted_line
    # las devuelve sin cambios), por lo que es segura de aplicar aunque solo
    # una parte de las filas de datos esten realmente envueltas.
    wrap_ratio = _wrap_pattern_ratio(physical_lines)
    repaired_text = "\n".join(unwrap_double_quoted_line(line) for line in physical_lines)
    df_rep, cols_rep, err_rep = _attempt_read_text(repaired_text)
    if not _is_usable(df_rep):
        return CsvLoadResult(
            dataframe=None, repaired=False, standard_columns_count=cols_std,
            standard_reject_reason=reject_reason, repaired_columns_count=cols_rep,
            n_rows_recovered=None,
            error=(
                (err_rep or "La reparacion de comillas dobladas no recupero un esquema identificable.")
                + f" (cabecera envuelta, {wrap_ratio * 100:.0f}% de la muestra de lineas envuelta)."
            ),
        )

    return CsvLoadResult(
        dataframe=df_rep, repaired=True, standard_columns_count=cols_std,
        standard_reject_reason=f"{reject_reason} (cabecera envuelta; {wrap_ratio * 100:.0f}% de la muestra de lineas envuelta)",
        repaired_columns_count=cols_rep,
        n_rows_recovered=len(df_rep), error=None,
    )


def coerce_numeric_columns(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    """
    Conversion explicita a numerico (item 7): tras validar tipos con
    check_dtypes (que registra los valores no convertibles como WARNING),
    se convierten las columnas numericas requeridas con pd.to_numeric,
    conservando NaN para nulos y para valores no convertibles. Evita que el
    resto del analisis opere accidentalmente sobre strings numericos.
    """
    for col in numeric_columns:
        if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@dataclass
class ClientSource:
    csv_path: Path
    file_label: str
    id_from_filename: int | None
    dataframe: pd.DataFrame | None
    read_repaired: bool
    id_client: int | None = None
    id_batch: list = field(default_factory=list)
    id_run_staging: list = field(default_factory=list)
    source_run_id: list = field(default_factory=list)
    n_rows: int = 0
    quality: QualityReport = field(default_factory=QualityReport)
    is_valid: bool = False
    folder_name: str = ""

    @property
    def file_name(self) -> str:
        return self.csv_path.name


def _load_single_source(path: Path) -> ClientSource:
    file_label = extract_label_from_filename(path)
    id_from_filename = extract_id_from_label(file_label)

    result = read_csv_defensive(path)
    df = result.dataframe
    source = ClientSource(
        csv_path=path, file_label=file_label, id_from_filename=id_from_filename,
        dataframe=df, read_repaired=result.repaired, folder_name=normalize_folder_name(file_label),
    )
    source.quality.add(check_csv_readable(path.name, df is not None, result.error))
    if df is None:
        source.is_valid = False
        return source

    if result.repaired:
        source.quality.add(check_wrapped_csv_normalized(
            path.name, result.standard_reject_reason or "motivo no determinado",
            result.standard_columns_count, result.repaired_columns_count or len(df.columns),
            result.n_rows_recovered or len(df),
        ))

    source.n_rows = len(df)

    source.quality.add(check_required_columns(path.name, list(df.columns), all_required_columns()))
    source.quality.extend(check_dtypes(path.name, df, numeric_required_columns()))
    df = coerce_numeric_columns(df, numeric_required_columns())
    source.dataframe = df

    unique_clients, multi_client_issue = check_single_client(path.name, df)
    source.quality.add(multi_client_issue)
    if len(unique_clients) == 1:
        source.id_client = int(unique_clients[0])
    elif len(unique_clients) == 0:
        source.quality.add(QualityIssue(
            Severity.ERROR, "MISSING_ID_CLIENT",
            "No se ha podido determinar ID_CLIENT (columna vacia o ausente).",
            scope="file", details={"file": path.name},
        ))

    source.quality.add(check_filename_matches_id(path.name, id_from_filename, source.id_client))
    source.quality.add(check_duplicate_key(path.name, df, KEY_COLUMNS))
    source.quality.add(check_mojibake_in_value_levels(path.name, df))

    for col, bucket in (("ID_BATCH", source.id_batch), ("ID_RUN_STAGING", source.id_run_staging),
                        ("SOURCE_RUN_ID", source.source_run_id)):
        if col in df.columns:
            bucket.extend(sorted(df[col].dropna().unique().tolist()))

    for label, values in (("ID_BATCH", source.id_batch), ("ID_RUN_STAGING", source.id_run_staging)):
        if len(values) > 1:
            source.quality.add(QualityIssue(
                Severity.WARNING, "MULTIPLE_VALUES_FOR_SINGLE_CLIENT",
                f"El CSV de un unico cliente contiene mas de un valor de {label}: {values}.",
                scope="file", details={"file": path.name, "column": label, "values": values},
            ))

    source.is_valid = not source.quality.has_errors()
    return source


def load_client_sources(data_dir: Path) -> list[ClientSource]:
    """
    Descubre y carga todos los CSV de data_dir. Aisla errores por fichero:
    un CSV invalido no impide procesar los demas. Detecta ademas clientes
    duplicados entre ficheros y heterogeneidad de ID_BATCH entre clientes.
    """
    paths = discover_csv_files(data_dir)
    sources = [_load_single_source(path) for path in paths]

    client_to_files: dict[int, list[str]] = {}
    client_to_batches: dict[int, list] = {}
    for source in sources:
        if source.id_client is not None:
            client_to_files.setdefault(source.id_client, []).append(source.file_name)
            client_to_batches[source.id_client] = source.id_batch

    duplicate_issues = check_duplicate_client_across_files(client_to_files)
    if duplicate_issues:
        by_client = {issue.details["id_client"]: issue for issue in duplicate_issues}
        for source in sources:
            issue = by_client.get(source.id_client)
            if issue is not None:
                source.quality.add(issue)
                source.is_valid = False

    batch_issue = check_batch_heterogeneity(client_to_batches)
    if batch_issue is not None:
        for source in sources:
            if source.id_client is not None:
                source.quality.add(batch_issue)

    return sources


# ==============================================================================
# Fase 2 (EN PARALELO al loader legacy de arriba, todavia sin integrar en
# run_pipeline): un unico CSV fisico completo, una unica lectura, particion
# por ID_CLIENT. N=1 (un unico ID_CLIENT) no es un caso especial: recorre
# exactamente el mismo camino que N>1, es simplemente una particion.
#
# RUN_START_DATE es obligatoria SOLO para load_client_sources_from_csv
# durante esta fase: se exige explicitamente aqui (all_required_columns() +
# "RUN_START_DATE"), sin anadirla todavia a periods.STATIC_REQUIRED_COLUMNS,
# para no alterar el contrato del loader legacy (load_client_sources) antes
# de que run_pipeline migre a este loader nuevo en una fase posterior.
# ==============================================================================

def _numeric_and_integral_mask(series: pd.Series) -> pd.Series:
    """
    True donde el valor NO es un entero finito interpretable: nulo, no
    numerico (coaccionado a NaN por pd.to_numeric), infinito, o decimal no
    entero (p.ej. 63.5). Acepta enteros y floats sin parte fraccionaria
    (63, 63.0). Compartido por todos los identificadores estructurales del
    CSV (ID_CLIENT, ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID,
    ID_CONFIGURATION), que proceden de BIGINT en el backend. No valida
    rango de negocio: no rechaza 0 ni negativos unicamente por su valor.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    non_finite = ~np.isfinite(numeric)  # cubre nulo, no numerico e infinito
    non_integral = np.isfinite(numeric) & (numeric % 1 != 0)
    return non_finite | non_integral


def _validate_id_client_strict(df: pd.DataFrame) -> None:
    """
    Valida ID_CLIENT sobre los valores originales, ANTES de
    coerce_numeric_columns: un ID_CLIENT nulo o no numerico no debe
    convertirse primero en NaN (silenciosamente, via coercion general) y
    perderse despues en la deteccion.
    """
    invalid_mask = _numeric_and_integral_mask(df["ID_CLIENT"])
    if invalid_mask.any():
        n_bad = int(invalid_mask.sum())
        raise StructuralInputError(
            "INVALID_ID_CLIENT",
            f"{n_bad} fila(s) con ID_CLIENT nulo, no numerico, infinito o no entero. "
            f"ID_CLIENT debe ser inequivocamente convertible a un entero finito.",
        )


def _validate_execution_scope_fields(df: pd.DataFrame) -> None:
    """
    Tras la coercion numerica general, cada fila debe disponer de valores
    ID_BATCH, ID_RUN_STAGING y SOURCE_RUN_ID interpretables como entero
    finito (proceden de BIGINT en el backend). No basta con comprobar
    isna(): un decimal no entero (63.5) o un infinito ya coaccionado por
    coerce_numeric_columns no es NaN y pasaria desapercibido si solo se
    comprobara nulidad. No se inventan validaciones de rango/signo.
    """
    invalid_mask = pd.Series(False, index=df.index)
    for col in SCOPE_COLUMNS:
        invalid_mask |= _numeric_and_integral_mask(df[col])
    if invalid_mask.any():
        n_bad = int(invalid_mask.sum())
        raise StructuralInputError(
            "INVALID_EXECUTION_SCOPE",
            f"{n_bad} fila(s) con ID_BATCH, ID_RUN_STAGING o SOURCE_RUN_ID nulo, no numerico, "
            f"infinito o no entero.",
        )


def _validate_id_configuration_strict(df: pd.DataFrame) -> None:
    """
    ID_CONFIGURATION no participa en el scope de ejecucion
    (_check_ambiguous_client_scope), pero si forma parte de la clave
    logica canonica (KEY_COLUMNS) y procede de BIGINT en el backend. No
    esta incluida en numeric_required_columns() (es categorica para el
    resto del pipeline), asi que coerce_numeric_columns nunca la toca: se
    valida aqui, sobre los valores originales, para impedir que una
    configuracion con ID estructuralmente invalido llegue a
    check_duplicate_key o al analisis posterior sin ser detectada.
    """
    invalid_mask = _numeric_and_integral_mask(df["ID_CONFIGURATION"])
    if invalid_mask.any():
        n_bad = int(invalid_mask.sum())
        raise StructuralInputError(
            "INVALID_ID_CONFIGURATION",
            f"{n_bad} fila(s) con ID_CONFIGURATION nulo, no numerico, infinito o no entero.",
        )


def _parse_run_start_date_strict(df: pd.DataFrame) -> pd.Series:
    """
    Parsea RUN_START_DATE con pd.to_datetime(errors="coerce",
    format="mixed"). La exportacion manual de una columna SQL DATETIME2
    puede mezclar precision textual entre filas (con/sin fraccion de
    segundo, con/sin componente de hora): sin format="mixed", pandas (2.3.3,
    version verificada en este entorno) infiere el formato de la PRIMERA
    fila y convierte a NaT cualquier fila valida posterior con distinta
    precision -- comprobado explicitamente: la Serie
    ["2026-01-01", "2026-01-01 00:00:00.001"] produce NaT en la segunda
    fila sin format="mixed", y la parsea correctamente (preservando los
    milisegundos) con el. NULL, cadena vacia y texto realmente no
    interpretable siguen colapsando a NaT de forma identica con
    format="mixed" (tambien verificado). Devuelve la Serie parseada
    COMPLETA (con hora/fraccion), sin normalizar: la normalizacion a fecha
    se aplica unicamente, y por separado, para comparar igualdad logica de
    ventana (ver _logical_run_start_dates). No se usa COPIED_AT.
    """
    parsed = pd.to_datetime(df["RUN_START_DATE"], errors="coerce", format="mixed")
    if parsed.isna().any():
        n_bad = int(parsed.isna().sum())
        raise StructuralInputError(
            "INVALID_RUN_START_DATE",
            f"{n_bad} fila(s) con RUN_START_DATE nulo, vacio o no interpretable como fecha.",
        )
    return parsed


def _logical_run_start_dates(parsed_run_start_date: pd.Series) -> pd.Series:
    """
    Fecha logica usada UNICAMENTE para comparar igualdad de ventana (nunca
    se almacena en el DataFrame): normaliza a medianoche para no comparar
    diferencias de precision sub-diaria que la exportacion manual pudiera
    introducir. La ventana se identifica por el dia de inicio, no por la
    hora exacta. No se valida ni se exige que sea el primer dia del mes.
    """
    return parsed_run_start_date.dt.normalize()


def _check_ambiguous_client_scope(df: pd.DataFrame) -> None:
    """
    Para cada ID_CLIENT debe existir exactamente una combinacion real
    (por fila, no listas de valores unicos por columna) de SCOPE_COLUMNS.
    ID_CONFIGURATION no participa en esta decision: mas de una combinacion
    para el mismo cliente es siempre un error, tanto si las configuraciones
    son disjuntas como si se solapan.
    """
    ambiguous: dict[int, int] = {}
    for id_client, group in df.groupby("ID_CLIENT"):
        n_combos = len(group[SCOPE_COLUMNS].drop_duplicates())
        if n_combos > 1:
            ambiguous[int(id_client)] = n_combos
    if ambiguous:
        raise StructuralInputError(
            "AMBIGUOUS_CLIENT_EXECUTION",
            f"{len(ambiguous)} cliente(s) con mas de una combinacion de "
            f"(ID_BATCH, ID_RUN_STAGING, SOURCE_RUN_ID): {ambiguous} "
            f"(ID_CLIENT -> numero de combinaciones distintas). ID_CONFIGURATION no afecta a "
            f"esta decision; no se selecciona ninguna combinacion de forma arbitraria.",
        )


def _check_client_run_start_date_consistency(df: pd.DataFrame, logical_dates: pd.Series) -> dict[int, pd.Timestamp]:
    """
    Para cada ID_CLIENT, todas sus filas deben compartir una unica fecha
    logica de RUN_START_DATE. Devuelve {id_client: fecha} (una entrada por
    cliente, ya validada) para que la validacion global no tenga que volver
    a agrupar el DataFrame.
    """
    client_dates: dict[int, pd.Timestamp] = {}
    inconsistent: dict[int, list] = {}
    for id_client, dates in logical_dates.groupby(df["ID_CLIENT"]):
        unique_dates = dates.unique()
        if len(unique_dates) > 1:
            inconsistent[int(id_client)] = sorted(unique_dates)
        else:
            client_dates[int(id_client)] = unique_dates[0]
    if inconsistent:
        raise StructuralInputError(
            "INCONSISTENT_CLIENT_RUN_START_DATE",
            f"{len(inconsistent)} cliente(s) con mas de una fecha logica de RUN_START_DATE "
            f"dentro de sus propias filas: {inconsistent}.",
        )
    return client_dates


def _check_global_run_start_date(client_dates: dict[int, pd.Timestamp]) -> None:
    """
    Todos los ID_CLIENT del CSV deben compartir la misma fecha logica de
    RUN_START_DATE, con independencia de que tengan ID_BATCH,
    ID_RUN_STAGING o SOURCE_RUN_ID distintos: no se agrupa unicamente por
    ID_BATCH.
    """
    by_date: dict[pd.Timestamp, list[int]] = {}
    for id_client, date in client_dates.items():
        by_date.setdefault(date, []).append(id_client)
    if len(by_date) > 1:
        raise StructuralInputError(
            "INCOMPATIBLE_RUN_START_DATE",
            f"Los clientes del CSV no comparten la misma fecha logica de RUN_START_DATE: "
            f"{ {str(date.date()): ids for date, ids in by_date.items()} }.",
        )


def _build_client_sources(
    df: pd.DataFrame, csv_path: Path, read_repaired: bool, physical_warnings: list[QualityIssue],
) -> list[ClientSource]:
    """
    DataFrame ya validado -> list[ClientSource]. Sin I/O: testable de forma
    aislada pasando un DataFrame construido en memoria.

    csv_path/file_label/id_from_filename/read_repaired son metadata fisica
    compartida por todas las particiones (el mismo fichero de origen). El
    resto de campos de ClientSource es exclusivo de cada particion. No se
    llama a check_filename_matches_id: en un full export, el nombre del
    fichero no representa la identidad de ningun cliente concreto.
    folder_name se deja vacio deliberadamente (metadata de presentacion,
    fuera de alcance de esta fase).
    """
    file_label = extract_label_from_filename(csv_path)
    id_from_filename = extract_id_from_label(file_label)

    sources: list[ClientSource] = []
    for id_client, group in df.groupby("ID_CLIENT", sort=True):
        partition = group.copy()
        quality = QualityReport()
        quality.extend(physical_warnings)
        quality.add(check_mojibake_in_value_levels(csv_path.name, partition))

        source = ClientSource(
            csv_path=csv_path, file_label=file_label, id_from_filename=id_from_filename,
            dataframe=partition, read_repaired=read_repaired, id_client=int(id_client),
            id_batch=sorted(partition["ID_BATCH"].dropna().unique().tolist()),
            id_run_staging=sorted(partition["ID_RUN_STAGING"].dropna().unique().tolist()),
            source_run_id=sorted(partition["SOURCE_RUN_ID"].dropna().unique().tolist()),
            n_rows=len(partition), quality=quality,
            is_valid=not quality.has_errors(), folder_name="",
        )
        sources.append(source)
    return sources


def load_client_sources_from_csv(path: Path) -> list[ClientSource]:
    """
    Fase 2. Carga UN CSV fisico completo (`path`, ya resuelto por quien
    llama) y lo particiona por ID_CLIENT. No descubre directorios, no
    cuenta CSV, no accede al manifest ni publica outputs. Lanza
    StructuralInputError ante cualquier problema estructural: en ese caso
    no se crea ningun ClientSource.

    Orden de validacion (deliberado, ver src/quality_checks.StructuralInputError):
    lectura fisica -> columnas obligatorias (incluye RUN_START_DATE, solo
    para este loader) -> diagnostico de dtype (warning) -> ID_CLIENT
    estricto sobre valores originales -> coercion numerica general ->
    parseo de RUN_START_DATE -> scope basico por fila -> ID_CONFIGURATION
    estricto -> clave logica duplicada -> ejecucion logica ambigua por
    cliente -> RUN_START_DATE intra-cliente -> RUN_START_DATE global ->
    particion.
    """
    result = read_csv_defensive(path)
    csv_readable_issue = check_csv_readable(path.name, result.dataframe is not None, result.error)
    if csv_readable_issue is not None:
        raise StructuralInputError("CSV_NOT_READABLE", csv_readable_issue.message)
    df = result.dataframe

    required_columns = [*all_required_columns(), "RUN_START_DATE"]
    missing_issue = check_required_columns(path.name, list(df.columns), required_columns)
    if missing_issue is not None:
        raise StructuralInputError("MISSING_REQUIRED_COLUMNS", missing_issue.message)

    physical_warnings: list[QualityIssue] = []
    if result.repaired:
        physical_warnings.append(check_wrapped_csv_normalized(
            path.name, result.standard_reject_reason or "motivo no determinado",
            result.standard_columns_count, result.repaired_columns_count or len(df.columns),
            result.n_rows_recovered or len(df),
        ))
    physical_warnings.extend(check_dtypes(path.name, df, numeric_required_columns()))

    _validate_id_client_strict(df)
    df = coerce_numeric_columns(df, numeric_required_columns())

    parsed_run_start_date = _parse_run_start_date_strict(df)
    df["RUN_START_DATE"] = parsed_run_start_date  # se preserva el timestamp completo, sin normalizar

    _validate_execution_scope_fields(df)
    _validate_id_configuration_strict(df)

    dup_issue = check_duplicate_key(path.name, df, KEY_COLUMNS)
    if dup_issue is not None:
        raise StructuralInputError("DUPLICATE_LOGICAL_KEY", dup_issue.message)

    _check_ambiguous_client_scope(df)

    logical_dates = _logical_run_start_dates(df["RUN_START_DATE"])
    client_dates = _check_client_run_start_date_consistency(df, logical_dates)
    _check_global_run_start_date(client_dates)

    sources = _build_client_sources(df, path, result.repaired, physical_warnings)

    client_to_batches = {source.id_client: source.id_batch for source in sources}
    batch_issue = check_batch_heterogeneity(client_to_batches)
    if batch_issue is not None:
        for source in sources:
            source.quality.add(batch_issue)
            source.is_valid = not source.quality.has_errors()

    return sources
