"""
Orquestacion del nucleo de analisis para un unico cliente, a traves de
todos los periodos (M1..M6, RECENT_3M, OLDER_3M, 6M).

Este modulo NO genera Excel, Markdown ni graficos (eso es Fase 3/4). Solo
calcula: universos, comparabilidad especifica por periodo, cobertura,
WAPE global ponderado, reduccion absoluta de error, estadistica de mejora
relativa, distribucion de ganadores y chequeos de calidad.

Modelo de estados (4 niveles, deliberadamente separados):

    1. Validez del fichero (`ClientSource.is_valid` / `ClientAnalysisResult.file_valid`):
       el CSV se ha podido leer, tiene el esquema completo requerido, un
       unico ID_CLIENT, sin duplicados de clave logica, etc. Si el fichero
       no es valido, no se calcula ningun periodo.
    2. Estado global del cliente (`ClientAnalysisResult.status`): SUCCESS,
       SUCCESS_WITH_WARNINGS o ERROR. Es ERROR unicamente cuando el fichero
       no es valido. Una incidencia localizada en un periodo o en filas
       concretas (p.ej. un historico negativo en un mes) NUNCA marca el
       cliente entero como ERROR: como mucho produce SUCCESS_WITH_WARNINGS.
    3. Estado de cada periodo (`PeriodResult.status`): OK, WARNING o ERROR,
       derivado unicamente de los chequeos de ese periodo. Un ERROR en M1
       no afecta al estado de M2, de los trimestres o de 6M salvo que sus
       propios chequeos tambien fallen.
    4. Incidencias de filas concretas: el detalle de las filas afectadas
       (p.ej. ID_CONFIGURATION + valor) se conserva en
       `QualityIssue.details["affected_rows"]` de los chequeos que lo
       admiten (p.ej. NEGATIVE_HISTORY), en lugar de colapsarlo en un
       simple contador.

Auditoria del winner: la regla de negocio real es "TIE cuando
relativeDiff < 0.0001, salvo ambos WAPE=0 que siempre es TIE". La formula
exacta de `relativeDiff` no esta documentada en este repositorio ni en
docs/analysis_requirements.md, por lo que NO se reconstruye ni se inventa un
umbral. WINNER_METHOD_* (y las columnas derivadas WINNER_MODEL_*,
FINALIST_METHOD_*, FINALIST_MODEL_*, WINNER_IMPROVEMENT_PCT_*) se usan
siempre como fuente de verdad. Unicamente se audita el caso totalmente
especificado de ambos WAPE=0 (ver quality_checks.check_both_zero_wape_is_tie)
y se deja constancia explicita de esta limitacion metodologica
(quality_checks.check_winner_formula_not_auditable).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.input_loader import ClientSource
from src.metrics import (
    absolute_error_reduction_total,
    descriptive_stats,
    period_wape_global,
    relative_improvement_row,
    winner_distribution,
)
from src.periods import ALL_PERIODS, MONTHLY_PERIODS, PeriodColumns, period_columns, visible_label
from src.quality_checks import (
    QualityReport,
    Severity,
    check_aggregate_vs_monthly_sum,
    check_bias_reconstruction,
    check_both_zero_wape_is_tie,
    check_comparable_missing_wape_inputs,
    check_comparable_without_forecasts,
    check_comparable_without_winner,
    check_comparison_status_vs_period_mask,
    check_error_chain_reconstruction,
    check_extreme_improvement,
    check_extreme_wape,
    check_forecast_null_when_flag_absent,
    check_mae_reconstruction,
    check_ml_exclusion_reason_present,
    check_negative_forecast,
    check_negative_history,
    check_null_metrics_when_zero_history,
    check_rmse_reconstruction,
    check_wape_reconstruction,
    check_winner_formula_not_auditable,
    QualityIssue,
)


@dataclass
class PeriodResult:
    period: str
    label: str
    status: str  # OK | WARNING | ERROR (deriva unicamente de los chequeos de este periodo)
    n_candidates: int  # universo de comparabilidad del periodo: HAS_BASE_CANDIDATE, salvo en 6M (len(df))
    n_comparable: int
    pct_comparable: float
    n_not_comparable: int
    not_comparable_reason_counts: dict
    comparison_status_counts_not_comparable: dict
    n_ml_excluded: int
    pct_ml_excluded: float
    ml_exclusion_reason_counts: dict
    n_missing_scp_forecast: int
    scp_no_output_reason_counts: dict
    n_missing_ml_forecast: int
    wape: dict
    abs_error_reduction_total: float
    winner_counts: dict
    improvement_stats_all: dict
    improvement_stats_ml_wins: dict
    improvement_stats_scp_wins: dict
    improvement_stats_tie: dict
    comparable_configuration_ids: frozenset = field(default_factory=frozenset)
    comparable_mask: pd.Series = None  # mascara booleana reutilizable (Fase 3: excel/report/charts)
    quality: QualityReport = field(default_factory=QualityReport)


@dataclass
class ClientAnalysisResult:
    source: ClientSource
    file_valid: bool  # validez del fichero (nivel 1)
    status: str  # SUCCESS | SUCCESS_WITH_WARNINGS | ERROR (nivel 2, estado global del cliente)
    n_candidates: int = 0
    comparison_status_distribution: dict = field(default_factory=dict)
    periods: dict = field(default_factory=dict)  # nivel 3: periods[period].status
    quality: QualityReport = field(default_factory=QualityReport)


def _history_valid(df: pd.DataFrame, pcols: PeriodColumns) -> pd.Series:
    history = df[pcols.total_history]
    return history.notna() & (history > 0)


def _method_valid(df: pd.DataFrame, forecast_col: str, abs_error_col: str, wape_col: str) -> pd.Series:
    cols = [c for c in (forecast_col, abs_error_col, wape_col) if c in df.columns]
    mask = pd.Series(True, index=df.index)
    for col in cols:
        mask &= df[col].notna()
    return mask


def period_comparable_mask(df: pd.DataFrame, pcols: PeriodColumns, candidate_mask: pd.Series) -> pd.Series:
    """
    Mascara de comparabilidad especifica del periodo (no se reutiliza la
    misma mascara para todos los periodos, ver docs/analysis_requirements.md).

    Una fila es comparable en el periodo cuando: pertenece al universo
    candidato, tiene historico valido (>0) para el periodo, y dispone de
    forecast/error/WAPE valido para SCP y para ML en ese periodo. Un
    historico negativo en el mes queda excluido automaticamente (no cumple
    > 0), sin necesidad de invalidar la fila en otros periodos.

    Para RECENT_3M/OLDER_3M se usa directamente el agregado trimestral ya
    materializado en el CSV (TOTAL_HISTORY_*, SCP/ML_TOTAL_ABS_ERROR_*, etc.),
    por lo que no se exige que cada uno de los tres meses sea comparable de
    forma aislada.
    """
    history_valid = _history_valid(df, pcols)
    scp_valid = _method_valid(df, pcols.scp_total_forecast, pcols.scp_total_abs_error, pcols.scp_wape)
    ml_valid = _method_valid(df, pcols.ml_total_forecast, pcols.ml_total_abs_error, pcols.ml_wape)
    return candidate_mask & history_valid & scp_valid & ml_valid


def backend_comparable_mask_6m(df: pd.DataFrame) -> pd.Series:
    """
    Poblacion canonica de 6M/global (Fase 4): exclusivamente
    COMPARISON_STATUS == "COMPARABLE", sin combinarla con HAS_BASE_CANDIDATE
    ni con ninguna mascara local de completitud de columnas. COMPARISON_STATUS
    nulo/vacio se trata como no comparable (la comparacion de string con NaN
    da False sin necesidad de manejo adicional). `period_comparable_mask`
    (local, especifica de columnas) sigue calculandose para 6M unicamente
    como mecanismo de auditoria/reconciliacion frente a esta mascara
    backend, nunca como poblacion.
    """
    return df["COMPARISON_STATUS"] == "COMPARABLE"


def _not_comparable_reason_counts(
    df: pd.DataFrame, pcols: PeriodColumns, candidate_mask: pd.Series, comparable_mask: pd.Series,
) -> dict:
    """
    Motivo DERIVADO de no comparabilidad, especifico del periodo. Se
    mantiene deliberadamente separado de COMPARISON_STATUS (ver
    `comparison_status_counts_not_comparable` en PeriodResult): no sustituye
    ni renombra las categorias originales del CSV (p.ej.
    NOT_COMPARABLE_MISSING_VALIDATION sigue visible tal cual en la
    distribucion de COMPARISON_STATUS).
    """
    not_comparable = candidate_mask & ~comparable_mask
    history_valid = _history_valid(df, pcols)
    scp_valid = _method_valid(df, pcols.scp_total_forecast, pcols.scp_total_abs_error, pcols.scp_wape)
    ml_valid = _method_valid(df, pcols.ml_total_forecast, pcols.ml_total_abs_error, pcols.ml_wape)

    reasons = pd.Series("OTHER", index=df.index, dtype=object)
    reasons = reasons.mask(not_comparable & ~history_valid, "NO_HISTORY_OR_ZERO")
    reasons = reasons.mask(not_comparable & history_valid & ~scp_valid & ~ml_valid, "MISSING_SCP_AND_ML")
    reasons = reasons.mask(not_comparable & history_valid & ~scp_valid & ml_valid, "MISSING_SCP")
    reasons = reasons.mask(not_comparable & history_valid & scp_valid & ~ml_valid, "MISSING_ML")

    counts = reasons[not_comparable].value_counts().to_dict()
    return {str(k): int(v) for k, v in counts.items()}


def _value_counts_dict(series: pd.Series) -> dict:
    return {str(k): int(v) for k, v in series.dropna().value_counts().to_dict().items()}


COMPARISON_STATUS_NULL_BUCKET = "SIN_COMPARISON_STATUS"


def _value_counts_dict_with_null_bucket(series: pd.Series, null_label: str = COMPARISON_STATUS_NULL_BUCKET) -> dict:
    """
    Como `_value_counts_dict`, pero sin perder los valores vacios: None,
    NaN, "" y strings formados unicamente por espacios se cuentan en un
    bucket diagnostico explicito y claramente derivado por reporting
    (`null_label`), distinguible de los strings oficiales NOT_COMPARABLE_*
    del backend (nunca se etiquetan como si fueran un estado backend real).
    No se normaliza ni se renombra ningun otro valor.
    """
    is_blank = series.isna() | (series.astype(str).str.strip() == "")
    counts = {str(k): int(v) for k, v in series[~is_blank].value_counts().to_dict().items()}
    n_blank = int(is_blank.sum())
    if n_blank:
        counts[null_label] = n_blank
    return counts


def _period_status(report: QualityReport) -> str:
    if report.has_errors():
        return "ERROR"
    if report.has_warnings():
        return "WARNING"
    return "OK"


def _analyze_period(df: pd.DataFrame, candidate_mask: pd.Series, period: str, file_label: str) -> PeriodResult:
    pcols = period_columns(period)
    quality = QualityReport()

    local_mask = period_comparable_mask(df, pcols, candidate_mask)
    is_backend_6m = period == "6M" and "COMPARISON_STATUS" in df.columns
    comparable_mask = backend_comparable_mask_6m(df) if is_backend_6m else local_mask

    n_candidates = int(candidate_mask.sum())
    n_comparable = int(comparable_mask.sum())
    if is_backend_6m:
        # Universo canonico 6M: todas las filas sobre las que se evalua
        # COMPARISON_STATUS (el mismo universo que comparable_mask y
        # comparison_status_not_comparable), no solo HAS_BASE_CANDIDATE.
        # `n_candidates` (HAS_BASE_CANDIDATE) sigue usandose mas abajo para
        # exclusiones ML y forecasts SCP/ML ausentes, sin mezclar ambos
        # conceptos (ClientAnalysisResult.n_candidates conserva su
        # contrato actual de cobertura HAS_BASE_CANDIDATE a nivel cliente).
        n_comparability_universe = len(df)
    else:
        n_comparability_universe = n_candidates
    n_not_comparable = n_comparability_universe - n_comparable
    pct_comparable = (n_comparable / n_comparability_universe * 100) if n_comparability_universe else float("nan")

    # `local_mask` es siempre la fuente de los motivos DERIVADOS
    # (NO_HISTORY_OR_ZERO/MISSING_SCP/MISSING_ML/...): en 6M queda como
    # mecanismo de auditoria/reconciliacion, nunca como el motivo mostrado.
    not_comparable_reasons = _not_comparable_reason_counts(df, pcols, candidate_mask, local_mask)
    if is_backend_6m:
        # Poblacion 6M/global = COMPARISON_STATUS=="COMPARABLE" en solitario
        # (sin HAS_BASE_CANDIDATE): el breakdown de motivos debe ser
        # coherente y calcularse sobre TODO el universo analizado, no solo
        # sobre `candidate_mask`, o reintroduciria HAS_BASE_CANDIDATE como
        # filtro de la poblacion 6M por la puerta de atras. Los nulos se
        # cuentan en un bucket diagnostico propio, no en un string
        # NOT_COMPARABLE_* del backend.
        comparison_status_not_comparable = _value_counts_dict_with_null_bucket(
            df.loc[~comparable_mask, "COMPARISON_STATUS"]
        )
    elif "COMPARISON_STATUS" in df.columns:
        comparison_status_not_comparable = _value_counts_dict(
            df.loc[candidate_mask & ~comparable_mask, "COMPARISON_STATUS"]
        )
    else:
        comparison_status_not_comparable = {}

    ml_excluded_mask = candidate_mask & (df.get("HAS_ML_EXCLUDED", pd.Series(0, index=df.index)) == 1)
    n_ml_excluded = int(ml_excluded_mask.sum())
    pct_ml_excluded = (n_ml_excluded / n_candidates * 100) if n_candidates else float("nan")
    ml_exclusion_reasons = _value_counts_dict(df.loc[ml_excluded_mask, "ML_EXCLUSION_REASON"]) if "ML_EXCLUSION_REASON" in df.columns else {}

    missing_scp_mask = candidate_mask & df[pcols.scp_total_forecast].isna()
    n_missing_scp = int(missing_scp_mask.sum())
    scp_no_output_reasons = _value_counts_dict(df.loc[missing_scp_mask, "SCP_NO_OUTPUT_REASON"]) if "SCP_NO_OUTPUT_REASON" in df.columns else {}

    missing_ml_mask = candidate_mask & df[pcols.ml_total_forecast].isna()
    n_missing_ml = int(missing_ml_mask.sum())

    comparable_df = df.loc[comparable_mask]
    if "ID_CONFIGURATION" in df.columns:
        comparable_configuration_ids = frozenset(comparable_df["ID_CONFIGURATION"].tolist())
    else:
        comparable_configuration_ids = frozenset()

    if n_comparable > 0:
        wape = period_wape_global(comparable_df, pcols)
        abs_reduction_total = absolute_error_reduction_total(comparable_df, pcols)
        winner_counts = winner_distribution(comparable_df[pcols.winner_method])

        improvement_values, _cases = relative_improvement_row(
            comparable_df[pcols.scp_wape], comparable_df[pcols.ml_wape]
        )
        winner = comparable_df[pcols.winner_method]
        stats_all = descriptive_stats(improvement_values)
        stats_ml = descriptive_stats(improvement_values[winner == "ML"])
        stats_scp = descriptive_stats(improvement_values[winner == "SCP"])
        stats_tie = descriptive_stats(improvement_values[winner == "TIE"])
    else:
        wape = period_wape_global(comparable_df, pcols)
        abs_reduction_total = 0.0
        winner_counts = winner_distribution(pd.Series(dtype=object))
        improvement_values = pd.Series(dtype=float)
        stats_all = descriptive_stats(pd.Series(dtype=float))
        stats_ml = descriptive_stats(pd.Series(dtype=float))
        stats_scp = descriptive_stats(pd.Series(dtype=float))
        stats_tie = descriptive_stats(pd.Series(dtype=float))

    # --- chequeos de calidad numericos del periodo ---
    for monthly_field, aggregate_col in (
        ("HISTORY", pcols.total_history),
        ("SCP_ABS_ERROR", pcols.scp_total_abs_error),
        ("ML_ABS_ERROR", pcols.ml_total_abs_error),
    ):
        quality.add(check_aggregate_vs_monthly_sum(file_label, df, period, pcols, monthly_field, aggregate_col))

    quality.extend(check_wape_reconstruction(file_label, df, period, pcols))
    quality.extend(check_error_chain_reconstruction(file_label, df, period, pcols))
    quality.extend(check_mae_reconstruction(file_label, df, period, pcols))
    quality.extend(check_rmse_reconstruction(file_label, df, period, pcols))
    quality.extend(check_bias_reconstruction(file_label, df, period, pcols))
    quality.add(check_both_zero_wape_is_tie(file_label, df, period, pcols))
    quality.add(check_null_metrics_when_zero_history(file_label, df, period, pcols))
    quality.add(check_negative_history(file_label, df, period, pcols))
    quality.extend(check_negative_forecast(file_label, df, period, pcols))
    quality.extend(check_extreme_wape(file_label, df, period, pcols))
    if n_comparable > 0:
        quality.add(check_extreme_improvement(file_label, period, improvement_values))
    quality.add(check_comparable_without_winner(file_label, period, comparable_mask, df[pcols.winner_method]))
    quality.add(check_comparable_without_forecasts(
        file_label, period, comparable_mask, df[pcols.scp_total_forecast], df[pcols.ml_total_forecast]
    ))
    if is_backend_6m:
        # `local_mask` (reconstruccion local) se compara contra
        # COMPARISON_STATUS (fuente de verdad backend, ya usada como
        # `comparable_mask`) para documentar discrepancias, nunca para
        # decidir la poblacion.
        quality.add(check_comparison_status_vs_period_mask(file_label, period, df["COMPARISON_STATUS"], local_mask))
        quality.add(check_comparable_missing_wape_inputs(file_label, period, comparable_mask, df, pcols))

    return PeriodResult(
        period=period, label=visible_label(period), status=_period_status(quality),
        n_candidates=n_comparability_universe, n_comparable=n_comparable, pct_comparable=pct_comparable,
        n_not_comparable=n_not_comparable, not_comparable_reason_counts=not_comparable_reasons,
        comparison_status_counts_not_comparable=comparison_status_not_comparable,
        n_ml_excluded=n_ml_excluded, pct_ml_excluded=pct_ml_excluded,
        ml_exclusion_reason_counts=ml_exclusion_reasons,
        n_missing_scp_forecast=n_missing_scp, scp_no_output_reason_counts=scp_no_output_reasons,
        n_missing_ml_forecast=n_missing_ml,
        wape=wape, abs_error_reduction_total=abs_reduction_total, winner_counts=winner_counts,
        improvement_stats_all=stats_all, improvement_stats_ml_wins=stats_ml,
        improvement_stats_scp_wins=stats_scp, improvement_stats_tie=stats_tie,
        comparable_configuration_ids=comparable_configuration_ids,
        comparable_mask=comparable_mask,
        quality=quality,
    )


def _negative_history_rows(period_result: PeriodResult) -> list[dict]:
    rows: list[dict] = []
    for issue in period_result.quality.issues:
        if issue.code == "NEGATIVE_HISTORY":
            rows.extend(issue.details.get("affected_rows", []))
    return rows


def _highlight_negative_history_still_comparable(
    file_label: str, periods: dict[str, PeriodResult],
) -> QualityIssue | None:
    """
    Cruza las filas con historico mensual negativo (cualquier mes) con el
    conjunto de series comparables en 6M: si el agregado semestral sigue
    siendo positivo, la fila puede seguir siendo comparable en 6M pese a
    tener un mes con historico negativo. Se destaca explicitamente en lugar
    de dejarlo implicito.
    """
    if "6M" not in periods:
        return None
    negative_rows: list[dict] = []
    for month in MONTHLY_PERIODS:
        if month in periods:
            negative_rows.extend(_negative_history_rows(periods[month]))
    if not negative_rows:
        return None

    comparable_ids_6m = periods["6M"].comparable_configuration_ids
    highlighted = [row for row in negative_rows if row["id_configuration"] in comparable_ids_6m]
    if not highlighted:
        return None

    ids = [row["id_configuration"] for row in highlighted]
    return QualityIssue(
        Severity.WARNING, "NEGATIVE_HISTORY_ROW_COMPARABLE_IN_6M",
        f"{len(highlighted)} serie(s) con historico mensual negativo en algun mes (ID_CONFIGURATION "
        f"{ids}) siguen siendo comparables en 6M porque el agregado semestral es positivo.",
        scope="client", details={"file": file_label, "rows": highlighted},
    )


def analyze_client(source: ClientSource) -> ClientAnalysisResult:
    """
    Ejecuta el nucleo de analisis para un cliente ya cargado. Si el fichero
    no es valido (CSV ilegible, esquema incompleto, multiples clientes en el
    CSV, etc.) el estado global del cliente es ERROR y no se calcula ningun
    periodo. Si el fichero es valido, el estado global NUNCA es ERROR por
    una incidencia localizada en un periodo o en filas concretas: como mucho
    es SUCCESS_WITH_WARNINGS (ver PeriodResult.status para el detalle por
    periodo).
    """
    quality = QualityReport()
    quality.extend(source.quality.issues)

    if not source.is_valid or source.dataframe is None:
        return ClientAnalysisResult(
            source=source, file_valid=False, status="ERROR", n_candidates=0, periods={}, quality=quality,
        )

    df = source.dataframe
    file_label = source.file_name

    if "HAS_BASE_CANDIDATE" not in df.columns:
        quality.add(check_ml_exclusion_reason_present(file_label, df))
        return ClientAnalysisResult(
            source=source, file_valid=False, status="ERROR", n_candidates=0, periods={}, quality=quality,
        )

    candidate_mask = df["HAS_BASE_CANDIDATE"] == 1
    n_candidates = int(candidate_mask.sum())
    comparison_status_distribution = (
        _value_counts_dict(df.loc[candidate_mask, "COMPARISON_STATUS"]) if "COMPARISON_STATUS" in df.columns else {}
    )

    quality.add(check_ml_exclusion_reason_present(file_label, df))
    quality.extend(check_forecast_null_when_flag_absent(file_label, df))
    quality.add(check_winner_formula_not_auditable(file_label))

    periods: dict[str, PeriodResult] = {}
    for period in ALL_PERIODS:
        result = _analyze_period(df, candidate_mask, period, file_label)
        periods[period] = result
        quality.extend(result.quality.issues)

    quality.add(_highlight_negative_history_still_comparable(file_label, periods))

    # Estado global del cliente: solo depende de la validez del fichero.
    # Las incidencias de periodo/fila quedan reflejadas en periods[*].status
    # y en el detalle de cada QualityIssue, nunca escalan a ERROR de cliente.
    status = "SUCCESS_WITH_WARNINGS" if (quality.has_errors() or quality.has_warnings()) else "SUCCESS"

    return ClientAnalysisResult(
        source=source, file_valid=True, status=status, n_candidates=n_candidates,
        comparison_status_distribution=comparison_status_distribution,
        periods=periods, quality=quality,
    )
