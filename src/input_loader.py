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

import pandas as pd

from src.periods import all_required_columns
from src.quality_checks import (
    QualityReport,
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
