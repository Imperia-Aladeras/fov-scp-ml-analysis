"""
Modelo de severidad y chequeos de calidad estructurales/numericos.

Niveles:
    OK       - el chequeo se ha ejecutado y no ha encontrado problemas.
    WARNING  - problema que no invalida el cliente/periodo pero debe quedar
               documentado en log, Excel, informe y resumen de ejecucion.
    ERROR    - problema que invalida el cliente o el periodo afectado.

Las tolerancias numericas usadas para comparar totales agregados con sumas
reconstruidas son:

    NUMERIC_ABS_TOLERANCE = 1e-6   (tolerancia absoluta)
    NUMERIC_REL_TOLERANCE = 1e-4   (tolerancia relativa, 0.01%)

Se considera "igual dentro de tolerancia" cuando:
    abs(a - b) <= NUMERIC_ABS_TOLERANCE + NUMERIC_REL_TOLERANCE * abs(b)

Estas tolerancias son deliberadamente laxas para no generar ruido por
redondeo de coma flotante, pero suficientemente estrictas para detectar
inconsistencias reales entre columnas agregadas y columnas mensuales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from src.periods import PeriodColumns, is_aggregate, is_monthly, months_of
from src.metrics import both_wape_zero_mask

NUMERIC_ABS_TOLERANCE = 1e-6
NUMERIC_REL_TOLERANCE = 1e-4

EXTREME_WAPE_THRESHOLD = 5.0  # 500% - por encima se marca WARNING, no ERROR
EXTREME_IMPROVEMENT_THRESHOLD_PCT = 300.0  # |mejora relativa| > 300%


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class QualityIssue:
    severity: Severity
    code: str
    message: str
    scope: str  # "file" | "client" | "period"
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.code}: {self.message}"


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)

    def add(self, issue: QualityIssue | None) -> None:
        if issue is not None:
            self.issues.append(issue)

    def extend(self, issues: list[QualityIssue]) -> None:
        self.issues.extend(i for i in issues if i is not None)

    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def errors(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def warnings(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def summary_counts(self) -> dict[str, int]:
        counts = {Severity.OK.value: 0, Severity.WARNING.value: 0, Severity.ERROR.value: 0}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts


class StructuralInputError(RuntimeError):
    """
    Error estructural que invalida el CSV fisico completo: cuando se lanza,
    no se crea ningun ClientSource. `code` es uno de los codigos ya usados
    como QualityIssue de severidad ERROR y ambito "file" (CSV_NOT_READABLE,
    MISSING_REQUIRED_COLUMNS, DUPLICATE_LOGICAL_KEY), mas los codigos nuevos
    de Fase 2 (INVALID_ID_CLIENT, INVALID_EXECUTION_SCOPE,
    INVALID_ID_CONFIGURATION, INVALID_RUN_START_DATE,
    AMBIGUOUS_CLIENT_EXECUTION, INCONSISTENT_CLIENT_RUN_START_DATE,
    INCOMPATIBLE_RUN_START_DATE). Misma
    forma que InputIntegrityError (src/input_inventory.py): permite que
    run_pipeline traduzca exc.code directamente a failure.error_type sin
    ningun cambio en ese mecanismo ya existente.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def values_close(a: pd.Series, b: pd.Series) -> pd.Series:
    """
    Compara con tolerancia absoluta + relativa (ver docstring del modulo).
    Coerciona explicitamente a numerico antes de comparar: una columna que
    haya llegado aqui con dtype `object` (p.ej. una serie construida a mano
    en tests, o completamente nula) no debe hacer fallar `np.isclose`.
    """
    a_num = pd.to_numeric(a, errors="coerce").astype(float)
    b_num = pd.to_numeric(b, errors="coerce").astype(float)
    return np.isclose(a_num, b_num, atol=NUMERIC_ABS_TOLERANCE, rtol=NUMERIC_REL_TOLERANCE, equal_nan=True)


# --------------------------------------------------------------------------
# Chequeos a nivel de fichero / carga (items 1-9 de la spec)
# --------------------------------------------------------------------------

def check_csv_readable(file_label: str, readable: bool, error_message: str | None) -> QualityIssue | None:
    if readable:
        return None
    return QualityIssue(
        Severity.ERROR, "CSV_NOT_READABLE",
        f"No se ha podido leer el CSV de forma valida: {error_message}",
        scope="file", details={"file": file_label},
    )


def check_required_columns(file_label: str, columns: list[str], required: list[str]) -> QualityIssue | None:
    missing = [c for c in required if c not in columns]
    if not missing:
        return None
    return QualityIssue(
        Severity.ERROR, "MISSING_REQUIRED_COLUMNS",
        f"Faltan {len(missing)} columnas obligatorias: {missing[:10]}"
        + (" ..." if len(missing) > 10 else ""),
        scope="file", details={"file": file_label, "missing": missing},
    )


def check_dtypes(file_label: str, df: pd.DataFrame, numeric_columns: list[str]) -> list[QualityIssue]:
    """WARNING por columna que deberia ser numerica y contiene valores no coercibles."""
    issues: list[QualityIssue] = []
    for col in numeric_columns:
        if col not in df.columns:
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            continue
        coerced = pd.to_numeric(series, errors="coerce")
        bad_mask = coerced.isna() & series.notna()
        n_bad = int(bad_mask.sum())
        if n_bad > 0:
            issues.append(QualityIssue(
                Severity.WARNING, "NON_NUMERIC_VALUES",
                f"Columna '{col}' esperada numerica tiene {n_bad} valores no coercibles.",
                scope="file", details={"file": file_label, "column": col, "n_bad": n_bad},
            ))
    return issues


def check_single_client(file_label: str, df: pd.DataFrame, id_column: str = "ID_CLIENT") -> tuple[list, QualityIssue | None]:
    unique_ids = sorted(df[id_column].dropna().unique().tolist()) if id_column in df.columns else []
    if len(unique_ids) <= 1:
        return unique_ids, None
    return unique_ids, QualityIssue(
        Severity.ERROR, "MULTIPLE_CLIENTS_IN_CSV",
        f"El CSV contiene mas de un ID_CLIENT: {unique_ids}. No se mezclan silenciosamente.",
        scope="file", details={"file": file_label, "ids": unique_ids},
    )


def check_filename_matches_id(file_label: str, id_from_name: int | None, id_from_content: int | None) -> QualityIssue | None:
    if id_from_name is None or id_from_content is None:
        return None
    if id_from_name == id_from_content:
        return None
    return QualityIssue(
        Severity.WARNING, "FILENAME_ID_MISMATCH",
        f"El ID del nombre de archivo ({id_from_name}) no coincide con ID_CLIENT interno ({id_from_content}).",
        scope="file", details={"file": file_label, "id_from_name": id_from_name, "id_from_content": id_from_content},
    )


def check_duplicate_key(file_label: str, df: pd.DataFrame, key_columns: list[str]) -> QualityIssue | None:
    present = [c for c in key_columns if c in df.columns]
    if len(present) != len(key_columns):
        return None
    n_dupes = int(df.duplicated(subset=key_columns).sum())
    if n_dupes == 0:
        return None
    return QualityIssue(
        Severity.ERROR, "DUPLICATE_LOGICAL_KEY",
        f"{n_dupes} filas duplicadas sobre la clave logica {key_columns}.",
        scope="file", details={"file": file_label, "n_duplicates": n_dupes},
    )


def check_duplicate_client_across_files(client_to_files: dict[int, list[str]]) -> list[QualityIssue]:
    """
    Chequeo global (no por fichero): mismo ID_CLIENT presente en mas de un CSV.
    No se fusionan los ficheros; se registra el conflicto y ambos se muestran.
    """
    issues: list[QualityIssue] = []
    for client_id, files in client_to_files.items():
        if len(files) > 1:
            issues.append(QualityIssue(
                Severity.ERROR, "DUPLICATE_CLIENT_ACROSS_FILES",
                f"El cliente {client_id} aparece en mas de un CSV: {files}. No se fusionan ni se duplica el analisis.",
                scope="file", details={"id_client": client_id, "files": files},
            ))
    return issues


# --------------------------------------------------------------------------
# Chequeos numericos por periodo (items 10-28 de la spec)
# --------------------------------------------------------------------------

def check_aggregate_vs_monthly_sum(
    file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns,
    monthly_field: str, aggregate_field_name: str,
) -> QualityIssue | None:
    """
    Compara una columna agregada (p.ej. TOTAL_HISTORY_RECENT_3M) con la suma
    de la columna mensual equivalente (HISTORY_M1+M2+M3) para el periodo dado.
    Solo aplica a periodos agregados (RECENT_3M, OLDER_3M, 6M).
    """
    if not is_aggregate(period):
        return None
    months = months_of(period)
    monthly_cols = [f"{monthly_field}_{m}" for m in months]
    if not all(c in df.columns for c in monthly_cols) or aggregate_field_name not in df.columns:
        return None
    reconstructed = df[monthly_cols].sum(axis=1, skipna=True)
    provided = df[aggregate_field_name]
    both_present = provided.notna()
    mismatch = both_present & ~values_close(reconstructed.where(both_present), provided.where(both_present))
    n_mismatch = int(mismatch.sum())
    if n_mismatch == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "AGGREGATE_VS_MONTHLY_SUM_MISMATCH",
        f"{n_mismatch} filas donde {aggregate_field_name} no coincide con la suma de {monthly_cols} "
        f"(tolerancia abs={NUMERIC_ABS_TOLERANCE}, rel={NUMERIC_REL_TOLERANCE}).",
        scope="period", details={
            "file": file_label, "period": period, "n_mismatch": n_mismatch,
            "aggregate_column": aggregate_field_name, "monthly_columns": monthly_cols,
        },
    )


def check_wape_reconstruction(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    """Reconstruye WAPE = abs_error/history por fila y lo compara con la columna provista."""
    issues: list[QualityIssue] = []
    for method, wape_col, abs_error_col in (
        ("SCP", pcols.scp_wape, pcols.scp_total_abs_error),
        ("ML", pcols.ml_wape, pcols.ml_total_abs_error),
    ):
        if wape_col not in df.columns or abs_error_col not in df.columns or pcols.total_history not in df.columns:
            continue
        history = df[pcols.total_history]
        provided = df[wape_col]
        with np.errstate(divide="ignore", invalid="ignore"):
            reconstructed = df[abs_error_col] / history
        reconstructed = reconstructed.where(history > 0)
        both_present = provided.notna() & reconstructed.notna()
        mismatch = both_present & ~values_close(reconstructed.where(both_present), provided.where(both_present))
        n_mismatch = int(mismatch.sum())
        if n_mismatch > 0:
            issues.append(QualityIssue(
                Severity.WARNING, "WAPE_RECONSTRUCTION_MISMATCH",
                f"{n_mismatch} filas donde {wape_col} no coincide con {abs_error_col}/{pcols.total_history} reconstruido.",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n_mismatch},
            ))
    return issues


def check_both_zero_wape_is_tie(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> QualityIssue | None:
    """
    Unica parte de la regla de negocio del winner totalmente especificada:
    "ambos WAPE iguales a cero -> TIE". Se valida solo este caso; el resto
    de la regla (empate cuando relativeDiff < 0.0001) no se reconstruye
    porque la formula exacta de relativeDiff no esta documentada en el
    repositorio (ver check_winner_formula_not_auditable).
    """
    if pcols.winner_method not in df.columns or pcols.scp_wape not in df.columns or pcols.ml_wape not in df.columns:
        return None
    both_zero = both_wape_zero_mask(df[pcols.scp_wape], df[pcols.ml_wape])
    provided = df[pcols.winner_method]
    bad = both_zero & provided.notna() & (provided != "TIE")
    n_bad = int(bad.sum())
    if n_bad == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "BOTH_ZERO_WAPE_NOT_TIE",
        f"{n_bad} filas con {pcols.scp_wape}=0 y {pcols.ml_wape}=0 pero {pcols.winner_method} != 'TIE' "
        f"(la regla de negocio establece que ambos WAPE=0 implica TIE).",
        scope="period", details={"file": file_label, "period": period, "n_bad": n_bad},
    )


def check_winner_formula_not_auditable(file_label: str) -> QualityIssue:
    """
    Limitacion metodologica (no un chequeo de fila): la regla de negocio real
    del winner es "TIE cuando relativeDiff < 0.0001, salvo ambos WAPE=0 que
    siempre es TIE". La formula exacta de `relativeDiff` usada por la
    generacion original de WINNER_METHOD_* no esta documentada en este
    repositorio ni en docs/analysis_requirements.md. No se inventa esa
    formula: WINNER_METHOD_*, WINNER_MODEL_*, FINALIST_METHOD_*,
    FINALIST_MODEL_* y WINNER_IMPROVEMENT_PCT_* se usan siempre como fuente
    de verdad. Unicamente se audita el caso de ambos WAPE=0 (completamente
    especificado, ver check_both_zero_wape_is_tie).
    """
    return QualityIssue(
        Severity.WARNING, "WINNER_FORMULA_NOT_AUDITABLE",
        "El criterio de empate relativo (relativeDiff < 0.0001) usado para generar WINNER_METHOD_* "
        "no esta documentado en el repositorio. WINNER_METHOD_* se usa como fuente de verdad sin "
        "reconstruccion; solo se audita el caso totalmente especificado de ambos WAPE=0.",
        scope="file", details={"file": file_label},
    )


def check_null_metrics_when_zero_history(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> QualityIssue | None:
    if pcols.total_history not in df.columns or pcols.scp_wape not in df.columns:
        return None
    zero_history = df[pcols.total_history] == 0
    has_wape = df[pcols.scp_wape].notna() | df.get(pcols.ml_wape, pd.Series(index=df.index)).notna()
    bad = zero_history & has_wape
    n_bad = int(bad.sum())
    if n_bad == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "METRIC_WITH_ZERO_HISTORY",
        f"{n_bad} filas con {pcols.total_history}=0 pero con WAPE calculado (deberia ser nulo/no aplicable).",
        scope="period", details={"file": file_label, "period": period, "n_bad": n_bad},
    )


def check_negative_history(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> QualityIssue | None:
    """
    Historico negativo: WARNING, no ERROR. Puede representar un ajuste o
    devolucion legitima, no necesariamente un error de datos. La fila queda
    excluida automaticamente del universo de performance de este periodo
    (period_comparable_mask exige historico > 0), pero no invalida el
    fichero, el cliente ni los demas periodos.
    """
    if pcols.total_history not in df.columns:
        return None
    negative_mask = df[pcols.total_history] < 0
    n_negative = int(negative_mask.sum())
    if n_negative == 0:
        return None
    id_col = "ID_CONFIGURATION"
    if id_col in df.columns:
        affected_rows = [
            {"id_configuration": row_id, "period": period, "value": value}
            for row_id, value in zip(df.loc[negative_mask, id_col], df.loc[negative_mask, pcols.total_history])
        ]
    else:
        affected_rows = []
    return QualityIssue(
        Severity.WARNING, "NEGATIVE_HISTORY",
        f"{n_negative} filas con {pcols.total_history} negativo (posible ajuste/devolucion). "
        f"Excluidas del universo de performance de {period}; no invalida otros periodos ni el cliente.",
        scope="period", details={
            "file": file_label, "period": period, "n_negative": n_negative, "affected_rows": affected_rows,
        },
    )


def check_negative_forecast(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for method, col in (("SCP", pcols.scp_total_forecast), ("ML", pcols.ml_total_forecast)):
        if col not in df.columns:
            continue
        n_negative = int((df[col] < 0).sum())
        if n_negative > 0:
            issues.append(QualityIssue(
                Severity.WARNING, "NEGATIVE_FORECAST",
                f"{n_negative} filas con {col} negativo (revisar si es un valor permitido).",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_negative": n_negative},
            ))
    return issues


def check_extreme_wape(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for method, col in (("SCP", pcols.scp_wape), ("ML", pcols.ml_wape)):
        if col not in df.columns:
            continue
        n_extreme = int((df[col] > EXTREME_WAPE_THRESHOLD).sum())
        if n_extreme > 0:
            issues.append(QualityIssue(
                Severity.WARNING, "EXTREME_WAPE",
                f"{n_extreme} filas con {col} > {EXTREME_WAPE_THRESHOLD * 100:.0f}% "
                f"(tipicamente series con historico muy pequeno).",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_extreme": n_extreme},
            ))
    return issues


def check_extreme_improvement(file_label: str, period: str, improvement_pct: pd.Series) -> QualityIssue | None:
    n_extreme = int((improvement_pct.abs() > EXTREME_IMPROVEMENT_THRESHOLD_PCT).sum())
    if n_extreme == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "EXTREME_IMPROVEMENT",
        f"{n_extreme} filas con mejora relativa |valor| > {EXTREME_IMPROVEMENT_THRESHOLD_PCT}%.",
        scope="period", details={"file": file_label, "period": period, "n_extreme": n_extreme},
    )


def check_comparison_status_vs_period_mask(
    file_label: str, period: str, comparison_status: pd.Series, period_mask: pd.Series,
) -> QualityIssue | None:
    """
    Compara COMPARISON_STATUS == 'COMPARABLE' con la mascara de comparabilidad
    especifica del periodo. Se documenta la discrepancia, no se oculta.
    """
    status_comparable = comparison_status == "COMPARABLE"
    discrepancy = status_comparable != period_mask
    n_discrepancy = int(discrepancy.sum())
    if n_discrepancy == 0:
        return None
    only_status = int((status_comparable & ~period_mask).sum())
    only_mask = int((~status_comparable & period_mask).sum())
    return QualityIssue(
        Severity.WARNING, "COMPARISON_STATUS_VS_PERIOD_MASK_DISCREPANCY",
        f"{n_discrepancy} filas difieren entre COMPARISON_STATUS='COMPARABLE' y la mascara de "
        f"comparabilidad especifica de {period} ({only_status} solo en status, {only_mask} solo en mascara).",
        scope="period", details={
            "file": file_label, "period": period, "n_discrepancy": n_discrepancy,
            "only_in_comparison_status": only_status, "only_in_period_mask": only_mask,
        },
    )


def check_comparable_missing_wape_inputs(
    file_label: str, period: str, comparable_mask: pd.Series, df: pd.DataFrame, pcols: PeriodColumns,
) -> QualityIssue | None:
    """
    Filas COMPARABLE (poblacion canonica del periodo) con TOTAL_HISTORY,
    SCP_TOTAL_ABS_ERROR o ML_TOTAL_ABS_ERROR incompleto. La fila permanece
    en la poblacion (no se redefine comparabilidad), pero el WAPE global
    afectado queda no evaluable (NaN) en vez de calcularse ignorando la
    fila en silencio (ver metrics.period_wape_global).
    """
    missing = comparable_mask & (
        df[pcols.total_history].isna() | df[pcols.scp_total_abs_error].isna() | df[pcols.ml_total_abs_error].isna()
    )
    n_missing = int(missing.sum())
    if n_missing == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "COMPARABLE_MISSING_WAPE_INPUTS",
        f"{n_missing} filas comparables en {period} con {pcols.total_history}/{pcols.scp_total_abs_error}/"
        f"{pcols.ml_total_abs_error} incompleto: el WAPE global afectado queda no evaluable (NaN) en vez de "
        f"calcularse ignorando estas filas.",
        scope="period", details={"file": file_label, "period": period, "n_missing": n_missing},
    )


def check_comparable_without_winner(file_label: str, period: str, comparable_mask: pd.Series, winner: pd.Series) -> QualityIssue | None:
    bad = comparable_mask & winner.isna()
    n_bad = int(bad.sum())
    if n_bad == 0:
        return None
    return QualityIssue(
        Severity.ERROR, "COMPARABLE_WITHOUT_WINNER",
        f"{n_bad} filas comparables en {period} sin winner asignado.",
        scope="period", details={"file": file_label, "period": period, "n_bad": n_bad},
    )


def check_comparable_without_forecasts(
    file_label: str, period: str, comparable_mask: pd.Series, scp_forecast: pd.Series, ml_forecast: pd.Series,
) -> QualityIssue | None:
    bad = comparable_mask & (scp_forecast.isna() | ml_forecast.isna())
    n_bad = int(bad.sum())
    if n_bad == 0:
        return None
    return QualityIssue(
        Severity.ERROR, "COMPARABLE_WITHOUT_FORECASTS",
        f"{n_bad} filas comparables en {period} sin forecast SCP y/o ML.",
        scope="period", details={"file": file_label, "period": period, "n_bad": n_bad},
    )


def check_ml_exclusion_reason_present(file_label: str, df: pd.DataFrame) -> QualityIssue | None:
    if "HAS_ML_EXCLUDED" not in df.columns or "ML_EXCLUSION_REASON" not in df.columns:
        return None
    bad = (df["HAS_ML_EXCLUDED"] == 1) & df["ML_EXCLUSION_REASON"].isna()
    n_bad = int(bad.sum())
    if n_bad == 0:
        return None
    return QualityIssue(
        Severity.WARNING, "ML_EXCLUSION_WITHOUT_REASON",
        f"{n_bad} filas con HAS_ML_EXCLUDED=1 sin ML_EXCLUSION_REASON.",
        scope="file", details={"file": file_label, "n_bad": n_bad},
    )


def check_forecast_null_when_flag_absent(file_label: str, df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    checks = (
        ("HAS_SCP_CALCULATED", [f"SCP_FORECAST_M{i}" for i in range(1, 7)], "SCP"),
        ("HAS_ML_CALCULATED", [f"ML_FORECAST_M{i}" for i in range(1, 7)], "ML"),
    )
    for flag_col, forecast_cols, method in checks:
        present_cols = [c for c in forecast_cols if c in df.columns]
        if flag_col not in df.columns or not present_cols:
            continue
        flag_absent = df[flag_col] == 0
        has_any_forecast = df[present_cols].notna().any(axis=1)
        bad = flag_absent & has_any_forecast
        n_bad = int(bad.sum())
        if n_bad > 0:
            issues.append(QualityIssue(
                Severity.WARNING, "FORECAST_PRESENT_WITH_FLAG_ABSENT",
                f"{n_bad} filas con {flag_col}=0 pero con algun forecast {method} mensual no nulo.",
                scope="file", details={"file": file_label, "flag": flag_col, "n_bad": n_bad},
            ))
    return issues


# --------------------------------------------------------------------------
# Reconstruccion de la cadena de errores mensual (item 8): SIGNED_ERROR,
# ABS_ERROR y SQUARED_ERROR se derivan de FORECAST e HISTORY segun las
# formulas documentadas en docs/analysis_requirements.md (secciones 11-13):
#
#   SIGNED_ERROR   = FORECAST - HISTORY
#   ABS_ERROR      = ABS(SIGNED_ERROR)
#   SQUARED_ERROR  = SIGNED_ERROR ^ 2
#
# Estas formulas estan definidas a grano mensual. Para periodos agregados,
# la coherencia se valida con check_aggregate_vs_monthly_sum (suma de meses),
# no re-derivando desde FORECAST-HISTORY agregado.
# --------------------------------------------------------------------------

def check_error_chain_reconstruction(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    if not is_monthly(period) or pcols.total_history not in df.columns:
        return []
    issues: list[QualityIssue] = []
    history = df[pcols.total_history]
    for method, forecast_col, signed_col, abs_col, squared_col in (
        ("SCP", pcols.scp_total_forecast, pcols.scp_total_signed_error, pcols.scp_total_abs_error, pcols.scp_total_squared_error),
        ("ML", pcols.ml_total_forecast, pcols.ml_total_signed_error, pcols.ml_total_abs_error, pcols.ml_total_squared_error),
    ):
        if forecast_col not in df.columns:
            continue
        reconstructed_signed = df[forecast_col] - history

        if signed_col in df.columns:
            provided = df[signed_col]
            both = provided.notna() & reconstructed_signed.notna()
            mismatch = both & ~values_close(reconstructed_signed.where(both), provided.where(both))
            n = int(mismatch.sum())
            if n:
                issues.append(QualityIssue(
                    Severity.WARNING, "SIGNED_ERROR_RECONSTRUCTION_MISMATCH",
                    f"{n} filas donde {signed_col} no coincide con {forecast_col}-{pcols.total_history} reconstruido.",
                    scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
                ))

        if abs_col in df.columns:
            reconstructed_abs = reconstructed_signed.abs()
            provided = df[abs_col]
            both = provided.notna() & reconstructed_abs.notna()
            mismatch = both & ~values_close(reconstructed_abs.where(both), provided.where(both))
            n = int(mismatch.sum())
            if n:
                issues.append(QualityIssue(
                    Severity.WARNING, "ABS_ERROR_RECONSTRUCTION_MISMATCH",
                    f"{n} filas donde {abs_col} no coincide con ABS({forecast_col}-{pcols.total_history}) reconstruido.",
                    scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
                ))

        if squared_col in df.columns:
            reconstructed_squared = reconstructed_signed ** 2
            provided = df[squared_col]
            both = provided.notna() & reconstructed_squared.notna()
            mismatch = both & ~values_close(reconstructed_squared.where(both), provided.where(both))
            n = int(mismatch.sum())
            if n:
                issues.append(QualityIssue(
                    Severity.WARNING, "SQUARED_ERROR_RECONSTRUCTION_MISMATCH",
                    f"{n} filas donde {squared_col} no coincide con ({forecast_col}-{pcols.total_history})^2 reconstruido.",
                    scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
                ))
    return issues


# --------------------------------------------------------------------------
# Validacion de MAE, RMSE y Bias (formulas de docs/analysis_requirements.md
# seccion 17). Validas tanto para periodos mensuales como agregados, porque
# PeriodColumns normaliza el acceso igual para ambos casos.
#
#   MAE  = TOTAL_ABS_ERROR / POSITIVE_HISTORY_MONTH_COUNT
#   RMSE = SQRT(TOTAL_SQUARED_ERROR / POSITIVE_HISTORY_MONTH_COUNT)
#   BIAS = TOTAL_SIGNED_ERROR / TOTAL_HISTORY
# --------------------------------------------------------------------------

def check_mae_reconstruction(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    if pcols.positive_history_month_count not in df.columns:
        return []
    count = df[pcols.positive_history_month_count]
    issues: list[QualityIssue] = []
    for method, abs_col, mae_col in (
        ("SCP", pcols.scp_total_abs_error, pcols.scp_mae), ("ML", pcols.ml_total_abs_error, pcols.ml_mae),
    ):
        if abs_col not in df.columns or mae_col not in df.columns:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            reconstructed = df[abs_col] / count
        reconstructed = reconstructed.where(count > 0)
        provided = df[mae_col]
        both = provided.notna() & reconstructed.notna()
        mismatch = both & ~values_close(reconstructed.where(both), provided.where(both))
        n = int(mismatch.sum())
        if n:
            issues.append(QualityIssue(
                Severity.WARNING, "MAE_RECONSTRUCTION_MISMATCH",
                f"{n} filas donde {mae_col} no coincide con {abs_col}/{pcols.positive_history_month_count} reconstruido.",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
            ))
    return issues


def check_rmse_reconstruction(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    if pcols.positive_history_month_count not in df.columns:
        return []
    count = df[pcols.positive_history_month_count]
    issues: list[QualityIssue] = []
    for method, squared_col, rmse_col in (
        ("SCP", pcols.scp_total_squared_error, pcols.scp_rmse), ("ML", pcols.ml_total_squared_error, pcols.ml_rmse),
    ):
        if squared_col not in df.columns or rmse_col not in df.columns:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            reconstructed = np.sqrt(df[squared_col] / count)
        reconstructed = reconstructed.where(count > 0)
        provided = df[rmse_col]
        both = provided.notna() & reconstructed.notna()
        mismatch = both & ~values_close(reconstructed.where(both), provided.where(both))
        n = int(mismatch.sum())
        if n:
            issues.append(QualityIssue(
                Severity.WARNING, "RMSE_RECONSTRUCTION_MISMATCH",
                f"{n} filas donde {rmse_col} no coincide con SQRT({squared_col}/{pcols.positive_history_month_count}) reconstruido.",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
            ))
    return issues


def check_bias_reconstruction(file_label: str, df: pd.DataFrame, period: str, pcols: PeriodColumns) -> list[QualityIssue]:
    if pcols.total_history not in df.columns:
        return []
    history = df[pcols.total_history]
    issues: list[QualityIssue] = []
    for method, signed_col, bias_col in (
        ("SCP", pcols.scp_total_signed_error, pcols.scp_bias), ("ML", pcols.ml_total_signed_error, pcols.ml_bias),
    ):
        if signed_col not in df.columns or bias_col not in df.columns:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            reconstructed = df[signed_col] / history
        reconstructed = reconstructed.where(history > 0)
        provided = df[bias_col]
        both = provided.notna() & reconstructed.notna()
        mismatch = both & ~values_close(reconstructed.where(both), provided.where(both))
        n = int(mismatch.sum())
        if n:
            issues.append(QualityIssue(
                Severity.WARNING, "BIAS_RECONSTRUCTION_MISMATCH",
                f"{n} filas donde {bias_col} no coincide con {signed_col}/{pcols.total_history} reconstruido.",
                scope="period", details={"file": file_label, "period": period, "method": method, "n_mismatch": n},
            ))
    return issues


# --------------------------------------------------------------------------
# Item 4: normalizacion de CSV envueltos en comillas dobladas.
# --------------------------------------------------------------------------

def check_wrapped_csv_normalized(
    file_label: str, reject_reason: str, columns_before: int | None, columns_after: int,
    n_rows_recovered: int,
) -> QualityIssue:
    """
    Se emite siempre que se ha usado la lectura reparada (comillas dobladas)
    en lugar de la lectura estandar. WARNING, no ERROR: el fichero se ha
    podido recuperar integramente en memoria sin modificar el original.
    """
    return QualityIssue(
        Severity.WARNING, "WRAPPED_CSV_NORMALIZED",
        f"El CSV no se pudo leer con el parser estandar ({reject_reason}); se ha aplicado la "
        f"normalizacion de comillas dobladas en memoria. Columnas antes={columns_before}, "
        f"despues={columns_after}. Filas recuperadas={n_rows_recovered}.",
        scope="file", details={
            "file": file_label, "reject_reason": reject_reason,
            "columns_before": columns_before, "columns_after": columns_after,
            "n_rows_recovered": n_rows_recovered,
        },
    )


# --------------------------------------------------------------------------
# Item 10: heterogeneidad de ID_BATCH entre clientes y mojibake en texto.
# --------------------------------------------------------------------------

def check_batch_heterogeneity(client_batches: dict[int, list]) -> QualityIssue | None:
    """
    Chequeo global (no por fichero): detecta si los CSV cargados proceden de
    mas de un ID_BATCH. No implica que el analisis sea invalido, pero debe
    quedar explicito que los clientes pueden no proceder de la misma
    ejecucion/batch.
    """
    all_batches: set = set()
    for batches in client_batches.values():
        all_batches.update(batches)
    if len(all_batches) <= 1:
        return None
    affected = {str(client_id): batches for client_id, batches in client_batches.items()}
    return QualityIssue(
        Severity.WARNING, "BATCH_HETEROGENEITY_ACROSS_CLIENTS",
        f"Se han detectado {len(all_batches)} valores distintos de ID_BATCH entre los clientes "
        f"cargados: {sorted(all_batches)}. Los clientes no proceden necesariamente de la misma "
        f"ejecucion/batch.",
        scope="file", details={"clients_and_batches": affected},
    )


_MOJIBAKE_PATTERN = r"�|[ÃÂ][^\x00-\x7F]"


def check_mojibake_in_value_levels(file_label: str, df: pd.DataFrame) -> QualityIssue | None:
    """
    Deteccion heuristica (best-effort) de artefactos de codificacion en las
    columnas VALUE_LEVEL_*: caracter de sustitucion Unicode (U+FFFD) o el
    patron tipico de doble codificacion UTF-8/Latin-1 ("Ã"/"Â" seguido de un
    caracter no ASCII). No se corrige ni se infiere el texto original.
    """
    value_level_cols = [c for c in df.columns if c.startswith("VALUE_LEVEL_")]
    if not value_level_cols:
        return None
    counts: dict[str, int] = {}
    examples: dict[str, list] = {}
    for col in value_level_cols:
        series = df[col].dropna().astype(str)
        if series.empty:
            continue
        mask = series.str.contains(_MOJIBAKE_PATTERN, regex=True, na=False)
        n = int(mask.sum())
        if n:
            counts[col] = n
            examples[col] = series[mask].unique()[:3].tolist()
    if not counts:
        return None
    total = sum(counts.values())
    return QualityIssue(
        Severity.WARNING, "POSSIBLE_MOJIBAKE_IN_TEXT",
        f"{total} valores en columnas VALUE_LEVEL_* con posibles artefactos de codificacion "
        f"(caracter de sustitucion o doble codificacion UTF-8): {counts}. No se corrige ni se "
        f"infiere el texto original.",
        scope="file", details={"file": file_label, "counts_by_column": counts, "examples": examples},
    )
