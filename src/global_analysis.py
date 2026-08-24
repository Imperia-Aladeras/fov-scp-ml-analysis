"""
Comparativa global entre clientes (Fase 4).

Implementa las 4 perspectivas de docs/analysis_requirements.md
("Analisis global entre clientes"), siempre por separado, sin mezclarlas:

    1. Impacto global ponderado: SCP_WAPE_GLOBAL = SUM(abs_error) / SUM(historico)
       sobre TODAS las series comparables de TODOS los clientes.
    2. Mejora por cliente: cada cliente pesa igual (no se pondera por numero
       de series). Se calcula primero CLIENT_IMPROVEMENT_PCT por cliente y
       periodo, y despues estadistica descriptiva entre clientes.
    3. Mejora por serie: estadistica descriptiva de la mejora relativa de
       CADA serie individual de TODOS los clientes juntos (no se puede
       reconstruir desde medianas/percentiles por cliente: se recalcula
       desde las filas comparables originales de cada cliente).
    4. Impacto absoluto: reduccion absoluta total y contribucion de cada
       cliente a esa reduccion.

Solo participan en la comparativa global los clientes con fichero valido
(`ClientAnalysisResult.file_valid`); los invalidos se excluyen aqui pero
siguen apareciendo en el resumen de ejecucion (execution_summary).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.client_analysis import ClientAnalysisResult
from src.metrics import (
    BIAS_DIRECTION_NOT_EVALUABLE,
    BiasAggregateResult,
    absolute_error_reduction_row,
    client_contribution_to_total_reduction,
    cross_entity_stats,
    descriptive_stats,
    direction_label,
    relative_improvement_row,
)
from src.models import _ranking_columns, category_performance_table
from src.pareto import ParetoAnalysis, build_pareto_analysis
from src.periods import ALL_PERIODS, period_columns, visible_label
from src.phase8 import (
    MISSING_CATEGORY_LABEL,
    VOLUME_BUCKET_COLUMN,
    Phase8GlobalDiagnostics,
    category_performance_table_with_bias,
    classification_volume_cross_table,
)


@dataclass
class GlobalPeriodResult:
    period: str
    label: str
    n_clients: int
    n_candidates_total: int
    n_comparable_total: int
    pct_comparable_global: float
    history_sum: float
    scp_abs_error_sum: float
    ml_abs_error_sum: float
    scp_wape_global: float
    ml_wape_global: float
    global_improvement_pct: float
    abs_error_reduction_total: float
    winner_counts: dict
    # Perspectiva 2: cross_entity_stats ya incluye, con el denominador correcto
    # en cada caso: n_total (todos los clientes), n_evaluable/count (con
    # mejora calculable), n_missing (sin performance), n_improved, n_worse,
    # n_tie y sus pct_* (siempre sobre n_evaluable, nunca sobre n_total).
    client_improvement_stats: dict
    series_improvement_stats: dict  # Perspectiva 3 (descriptive_stats)
    # Perspectiva 4: dos tablas separadas (nunca un % sobre la reduccion neta,
    # que puede ser cero o negativa) + los tres totales.
    client_reduction_table: pd.DataFrame  # clientes con ABS_ERROR_REDUCTION > 0
    client_deterioration_table: pd.DataFrame  # clientes con ABS_ERROR_REDUCTION < 0
    reduction_totals: dict  # REDUCCION_POSITIVA_TOTAL, DETERIORO_TOTAL_ABSOLUTO, REDUCCION_NETA
    # Pareto de impacto absoluto (integracion global): SOLO se calculan para
    # 6M, estructuras nuevas y separadas de client_reduction_table/
    # client_deterioration_table (que no se modifican). None para el resto
    # de periodos.
    pareto_series: ParetoAnalysis | None = None
    pareto_clients: ParetoAnalysis | None = None
    # Diagnostico Fase 8 global: SOLO 6M, y unicamente si TODOS los clientes
    # participantes tienen PeriodResult.phase8 no nulo para 6M (contrato de
    # compatibilidad, ver _build_phase8_global_if_all_clients_ready). None
    # sin excepcion ni agregacion parcial cuando falta en algun cliente.
    phase8: Phase8GlobalDiagnostics | None = None


@dataclass
class GlobalAnalysisResult:
    client_results: list  # ClientAnalysisResult validos, usados en la comparativa
    invalid_results: list  # ClientAnalysisResult no validos (informativos)
    periods: dict = field(default_factory=dict)  # period -> GlobalPeriodResult
    client_period_tables: dict = field(default_factory=dict)  # period -> DataFrame (fila por cliente)


def _period_history_sum(r: ClientAnalysisResult, period: str) -> float:
    pr = r.periods.get(period)
    return (pr.wape.get("history_sum") or 0.0) if pr else 0.0


def _client_improvement_series(client_results: list[ClientAnalysisResult], period: str) -> pd.Series:
    """
    Indexado por ID_CLIENT, no por file_label: desde que un unico CSV fisico
    puede particionarse en varios clientes (Fase 3), varios ClientAnalysisResult
    comparten el mismo file_label (derivado del nombre de fichero fisico, no
    del cliente), lo que colapsaria silenciosamente entradas distintas bajo
    la misma clave de dict. id_client es unico por construccion (un CSV
    invalido con clientes duplicados no llega a producir ClientAnalysisResult
    validos duplicados). Solo se usan los VALORES aqui (cross_entity_stats no
    depende de las etiquetas del indice).
    """
    values = {}
    for r in client_results:
        pr = r.periods.get(period)
        values[r.source.id_client] = pr.wape.get("improvement_pct") if pr else float("nan")
    return pd.Series(values, dtype=float)


def _global_series_improvement_values(client_results: list[ClientAnalysisResult], period: str) -> pd.Series:
    pcols = period_columns(period)
    parts = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None or pr.n_comparable == 0 or pr.comparable_mask is None or r.source.dataframe is None:
            continue
        sub = r.source.dataframe.loc[pr.comparable_mask]
        values, _cases = relative_improvement_row(sub[pcols.scp_wape], sub[pcols.ml_wape])
        parts.append(values)
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, ignore_index=True)


def _sum_winner_counts(client_results: list[ClientAnalysisResult], period: str) -> dict:
    totals = {"ML": 0, "SCP": 0, "TIE": 0}
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None:
            continue
        for method in totals:
            totals[method] += pr.winner_counts.get(method, {}).get("n", 0)
    total_n = sum(totals.values())
    result = {
        method: {"n": n, "pct": (n / total_n * 100) if total_n else float("nan")}
        for method, n in totals.items()
    }
    result["_total"] = total_n
    return result


def _client_reduction_and_deterioration_tables(
    client_results: list[ClientAnalysisResult], period: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Separa los clientes en dos tablas segun el signo de ABS_ERROR_REDUCTION
    (positivo = ML reduce error; negativo = ML lo aumenta) y calcula el
    porcentaje de contribucion DENTRO de cada grupo por separado:

        PCT_OF_POSITIVE_REDUCTION  = CLIENT_ABS_ERROR_REDUCTION / REDUCCION_POSITIVA_TOTAL * 100
        PCT_OF_TOTAL_DETERIORATION = ABS(CLIENT_ABS_ERROR_REDUCTION) / DETERIORO_TOTAL_ABSOLUTO * 100

    Nunca se calcula un porcentaje sobre REDUCCION_NETA (la suma de todos los
    valores, positivos y negativos): cuando la reduccion neta es cero o
    negativa, ese porcentaje deja de estar acotado entre 0 y 100% y se vuelve
    dificil de interpretar (p.ej. un cliente puede "aportar" mas del 100% de
    un total neto pequeno o negativo). Los clientes con ABS_ERROR_REDUCTION
    exactamente 0 no aparecen en ninguna de las dos tablas (no reducen ni
    aumentan error).
    """
    rows = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None:
            continue
        rows.append({
            "ID_CLIENT": r.source.id_client, "ETIQUETA": r.source.file_label,
            "DISPLAY_NAME": r.source.display_name,
            "ABS_ERROR_REDUCTION": pr.abs_error_reduction_total,
        })
    base = pd.DataFrame(rows)

    totals = {"REDUCCION_POSITIVA_TOTAL": 0.0, "DETERIORO_TOTAL_ABSOLUTO": 0.0, "REDUCCION_NETA": 0.0}
    if base.empty:
        return base, base.copy(), totals

    positive_mask = base["ABS_ERROR_REDUCTION"] > 0
    negative_mask = base["ABS_ERROR_REDUCTION"] < 0

    if base["ABS_ERROR_REDUCTION"].isna().any():
        # Al menos un cliente no es evaluable para reduccion absoluta (p.ej.
        # una fila COMPARABLE de 6M con SCP/ML_TOTAL_ABS_ERROR incompleto):
        # no puede saberse si contribuiria al grupo positivo o al de
        # deterioro, asi que ningun total se calcula ignorandolo (pandas
        # Series.sum() ignora NaN por defecto, lo que lo recuperaria en
        # silencio solo con los clientes evaluables).
        totals["REDUCCION_POSITIVA_TOTAL"] = float("nan")
        totals["DETERIORO_TOTAL_ABSOLUTO"] = float("nan")
        totals["REDUCCION_NETA"] = float("nan")
    else:
        totals["REDUCCION_POSITIVA_TOTAL"] = float(base.loc[positive_mask, "ABS_ERROR_REDUCTION"].sum())
        totals["DETERIORO_TOTAL_ABSOLUTO"] = float(base.loc[negative_mask, "ABS_ERROR_REDUCTION"].abs().sum())
        totals["REDUCCION_NETA"] = float(base["ABS_ERROR_REDUCTION"].sum())

    reducers = base.loc[positive_mask].copy()
    if not reducers.empty:
        reducers["PCT_OF_POSITIVE_REDUCTION"] = client_contribution_to_total_reduction(reducers["ABS_ERROR_REDUCTION"])
    reducers = reducers.sort_values("ABS_ERROR_REDUCTION", ascending=False).reset_index(drop=True)

    worseners = base.loc[negative_mask].copy()
    if not worseners.empty:
        worseners["PCT_OF_TOTAL_DETERIORATION"] = client_contribution_to_total_reduction(worseners["ABS_ERROR_REDUCTION"].abs())
    worseners = worseners.sort_values("ABS_ERROR_REDUCTION", ascending=True).reset_index(drop=True)

    return reducers, worseners, totals


def global_pareto_series(client_results: list[ClientAnalysisResult], period: str) -> ParetoAnalysis:
    """
    Pareto global de series: mismo patron de reconstruccion que
    `_global_series_improvement_values`/`global_category_performance_table`
    (concatena las filas comparables de TODOS los clientes conservando
    ID_CLIENT, ya presente en cada dataframe), calculando ABS_ERROR_REDUCTION
    con la misma formula que el nivel individual (`absolute_error_reduction_row`,
    no se redefine). Identidad global = ID_CLIENT + ID_CONFIGURATION (nunca
    se asume ID_CONFIGURATION unico entre clientes distintos): por eso el
    desempate es magnitud DESC, ID_CLIENT ASC, ID_CONFIGURATION ASC.
    DISPLAY_NAME se anade solo como columna de presentacion (nunca identidad
    ni desempate). Reutiliza `_ranking_columns` de src.models (mismo set de
    columnas de contexto que ya usa el Pareto individual) en vez de
    duplicarlo.
    """
    pcols = period_columns(period)
    id_cols_wanted = ["DISPLAY_NAME", *_ranking_columns(pcols)]
    frames = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None or pr.n_comparable == 0 or pr.comparable_mask is None or r.source.dataframe is None:
            continue
        sub = r.source.dataframe.loc[pr.comparable_mask].copy()
        sub["ABS_ERROR_REDUCTION"] = absolute_error_reduction_row(sub, pcols)
        sub["DISPLAY_NAME"] = r.source.display_name
        frames.append(sub)

    concatenated = (
        pd.concat(frames, ignore_index=True) if frames
        else pd.DataFrame(columns=["ABS_ERROR_REDUCTION", *id_cols_wanted])
    )
    # Sin filtrado silencioso: si a algun cliente le falta una columna
    # declarada en id_cols_wanted, build_pareto_analysis debe fallar
    # (fail-fast), no descartarla en silencio.
    return build_pareto_analysis(
        concatenated, "ABS_ERROR_REDUCTION", id_cols=id_cols_wanted, tie_break_cols=["ID_CLIENT", "ID_CONFIGURATION"],
    )


def global_pareto_clients(client_results: list[ClientAnalysisResult], period: str) -> ParetoAnalysis:
    """
    Pareto global de clientes: reutiliza `pr.abs_error_reduction_total` ya
    calculado por client_analysis.py -- NUNCA se recalcula desde las series.
    Misma base de columnas de identidad que `_client_reduction_and_deterioration_tables`
    (ID_CLIENT, ETIQUETA, DISPLAY_NAME solo como presentacion), pero en una
    estructura Pareto nueva y separada: esta funcion no llama ni modifica
    `_client_reduction_and_deterioration_tables`, `client_reduction_table` ni
    `client_deterioration_table`. Identidad = ID_CLIENT; desempate magnitud
    DESC, ID_CLIENT ASC. Hereda el mismo comportamiento NaN que ya tiene
    `pr.abs_error_reduction_total` (un input ausente en cualquier serie del
    cliente invalida el total de ESE cliente, ver metrics.absolute_error_reduction_total).
    """
    rows = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None:
            continue
        rows.append({
            "ID_CLIENT": r.source.id_client, "ETIQUETA": r.source.file_label,
            "DISPLAY_NAME": r.source.display_name,
            "ABS_ERROR_REDUCTION": pr.abs_error_reduction_total,
        })
    base = pd.DataFrame(rows, columns=["ID_CLIENT", "ETIQUETA", "DISPLAY_NAME", "ABS_ERROR_REDUCTION"])
    return build_pareto_analysis(
        base, "ABS_ERROR_REDUCTION", id_cols=["ID_CLIENT", "ETIQUETA", "DISPLAY_NAME"], tie_break_cols=["ID_CLIENT"],
    )


def global_category_performance_table_with_bias(
    client_results: list[ClientAnalysisResult], period: str, category_col: str,
) -> pd.DataFrame:
    """
    Version global de phase8.category_performance_table_with_bias: concatena
    las filas comparables de TODOS los clientes (conservando ID_CLIENT, ya
    presente en cada dataframe), igual patron que category_performance_table
    (linea 354 de este modulo). `category_col` se normaliza UNA UNICA VEZ,
    antes de cualquier groupby, con el mismo MISSING_CATEGORY_LABEL que usa
    la tabla analitica -- y esa misma columna ya normalizada se reutiliza
    tanto para la tabla como para `n_clients`, de modo que la fila
    "(sin clasificar)" nunca queda desalineada entre metricas/Bias/n_clients.
    """
    pcols = period_columns(period)
    frames = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None or pr.comparable_mask is None or r.source.dataframe is None or pr.n_comparable == 0:
            continue
        sub = r.source.dataframe.loc[pr.comparable_mask]
        if not sub.empty:
            frames.append(sub)
    if not frames:
        return pd.DataFrame()

    concatenated = pd.concat(frames, ignore_index=True)
    if category_col not in concatenated.columns:
        return pd.DataFrame()

    concatenated = concatenated.copy()
    concatenated[category_col] = concatenated[category_col].fillna(MISSING_CATEGORY_LABEL)

    mask_all_true = pd.Series(True, index=concatenated.index)
    table = category_performance_table_with_bias(concatenated, pcols, mask_all_true, category_col)
    if table.empty:
        return table

    n_clients_map = concatenated.groupby(category_col, observed=True)["ID_CLIENT"].nunique()
    table["n_clients"] = table["category"].map(n_clients_map)
    return table


def _combine_bias_sums(values: list[float]) -> float:
    """NaN si algun valor de `values` no es finito; si no, la suma. Mismo criterio que metrics._sum_or_not_evaluable."""
    if any(not np.isfinite(v) for v in values):
        return np.nan
    return float(sum(values))


def _global_bias_total(client_results: list[ClientAnalysisResult], period: str) -> BiasAggregateResult:
    """
    Bias global: reutiliza las sumas YA calculadas por cliente
    (PeriodResult.phase8.bias_total), nunca recalculadas desde las filas --
    mismo patron que build_global_period_result ya usa para scp_err/ml_err/
    history_sum. Misma evaluabilidad independiente SCP/ML que bias_aggregate:
    history invalido invalida ambos; un signed error no finito de un metodo
    no invalida al otro.
    """
    bias_results = [r.periods[period].phase8.bias_total for r in client_results]
    history_sum = _combine_bias_sums([b.history_sum for b in bias_results])
    scp_signed_sum = _combine_bias_sums([b.scp_signed_error_sum for b in bias_results])
    ml_signed_sum = _combine_bias_sums([b.ml_signed_error_sum for b in bias_results])

    history_valid = np.isfinite(history_sum) and history_sum > 0
    if not history_valid:
        return BiasAggregateResult(
            history_sum=history_sum, scp_signed_error_sum=scp_signed_sum, ml_signed_error_sum=ml_signed_sum,
            scp_bias_agg=np.nan, ml_bias_agg=np.nan,
            scp_direction=BIAS_DIRECTION_NOT_EVALUABLE, ml_direction=BIAS_DIRECTION_NOT_EVALUABLE,
        )

    scp_bias_agg = (scp_signed_sum / history_sum) if np.isfinite(scp_signed_sum) else np.nan
    ml_bias_agg = (ml_signed_sum / history_sum) if np.isfinite(ml_signed_sum) else np.nan
    return BiasAggregateResult(
        history_sum=history_sum, scp_signed_error_sum=scp_signed_sum, ml_signed_error_sum=ml_signed_sum,
        scp_bias_agg=scp_bias_agg, ml_bias_agg=ml_bias_agg,
        scp_direction=direction_label(scp_bias_agg), ml_direction=direction_label(ml_bias_agg),
    )


def _global_volume_frames_and_not_assignable_count(
    client_results: list[ClientAnalysisResult], period: str,
) -> tuple[list[pd.DataFrame], int]:
    """
    Concatena, por cliente, las filas comparables junto con el VOLUME_BUCKET
    YA CALCULADO en el paso individual (PeriodResult.phase8.volume.buckets,
    alineado por indice sobre la misma df.loc[comparable_mask] -- nunca se
    recalculan terciles sobre el pool global). Los clientes NOT_ASSIGNABLE
    permanecen, con sus filas etiquetadas como tal, nunca excluidas.
    """
    frames = []
    n_not_assignable = 0
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None or pr.comparable_mask is None or r.source.dataframe is None or pr.n_comparable == 0:
            continue
        sub = r.source.dataframe.loc[pr.comparable_mask].copy()
        sub[VOLUME_BUCKET_COLUMN] = pr.phase8.volume.buckets
        frames.append(sub)
        if pr.phase8.volume.status == "NOT_ASSIGNABLE":
            n_not_assignable += 1
    return frames, n_not_assignable


def build_phase8_global_diagnostics(client_results: list[ClientAnalysisResult], period: str) -> Phase8GlobalDiagnostics:
    """
    Diagnostico Fase 8 global (8D), solo 6M. El llamador
    (_build_phase8_global_if_all_clients_ready) ya garantiza que todos los
    PeriodResult.phase8 estan presentes -- esta funcion no vuelve a
    comprobarlo.
    """
    pcols = period_columns(period)

    bias_total = _global_bias_total(client_results, period)

    model_tables = {
        col: global_category_performance_table_with_bias(client_results, period, col)
        for col in ("ML_BEST_MODEL", "SCP_BEST_MODEL")
    }
    classification_tables = {
        col: global_category_performance_table_with_bias(client_results, period, col)
        for col in ("ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION", "SCP_CLASSIFICATION")
    }

    volume_frames, n_not_assignable = _global_volume_frames_and_not_assignable_count(client_results, period)
    if volume_frames:
        concatenated_with_bucket = pd.concat(volume_frames, ignore_index=True)
        mask_all_true = pd.Series(True, index=concatenated_with_bucket.index)
        volume_table = category_performance_table_with_bias(
            concatenated_with_bucket, pcols, mask_all_true, VOLUME_BUCKET_COLUMN,
        )
        classification_volume_cross = classification_volume_cross_table(concatenated_with_bucket, pcols, mask_all_true)
    else:
        volume_table = pd.DataFrame()
        classification_volume_cross = pd.DataFrame()

    return Phase8GlobalDiagnostics(
        bias_total=bias_total, model_tables=model_tables, classification_tables=classification_tables,
        volume_table=volume_table, classification_volume_cross=classification_volume_cross,
        n_clients_with_not_assignable_volume=n_not_assignable,
    )


def _build_phase8_global_if_all_clients_ready(
    client_results: list[ClientAnalysisResult], period: str,
) -> Phase8GlobalDiagnostics | None:
    """
    GlobalPeriodResult.phase8 solo se construye cuando period=="6M" Y TODOS
    los clientes participantes tienen PeriodResult.phase8 no nulo para 6M.
    Si falta en algun cliente: None, sin excepcion, sin agregacion parcial,
    sin excluir a ese cliente de ninguna otra perspectiva global. Una lista
    vacia satisface vacuamente "todos tienen phase8" (consistente con
    global_pareto_series/global_pareto_clients, que ya toleran listas
    vacias devolviendo estructuras vacias en vez de None).
    """
    if period != "6M":
        return None
    all_ready = all(
        (pr := r.periods.get(period)) is not None and pr.phase8 is not None
        for r in client_results
    )
    if not all_ready:
        return None
    return build_phase8_global_diagnostics(client_results, period)


def build_global_period_result(client_results: list[ClientAnalysisResult], period: str) -> GlobalPeriodResult:
    history_sum = sum(_period_history_sum(r, period) for r in client_results)
    scp_err = sum((r.periods[period].wape.get("scp_abs_error_sum") or 0.0) for r in client_results if period in r.periods)
    ml_err = sum((r.periods[period].wape.get("ml_abs_error_sum") or 0.0) for r in client_results if period in r.periods)

    if history_sum > 0:
        scp_wape_global = scp_err / history_sum
        ml_wape_global = ml_err / history_sum
        global_improvement_pct = (scp_wape_global - ml_wape_global) / scp_wape_global * 100 if scp_wape_global else float("nan")
    else:
        scp_wape_global = ml_wape_global = global_improvement_pct = float("nan")

    n_candidates_total = sum(r.periods[period].n_candidates for r in client_results if period in r.periods)
    n_comparable_total = sum(r.periods[period].n_comparable for r in client_results if period in r.periods)
    pct_comparable_global = (n_comparable_total / n_candidates_total * 100) if n_candidates_total else float("nan")

    reduction_table, deterioration_table, reduction_totals = _client_reduction_and_deterioration_tables(client_results, period)

    # Pareto de impacto absoluto: solo 6M, igual que el criterio ya usado
    # para PeriodResult.pareto en client_analysis.py.
    pareto_series = global_pareto_series(client_results, period) if period == "6M" else None
    pareto_clients = global_pareto_clients(client_results, period) if period == "6M" else None
    phase8 = _build_phase8_global_if_all_clients_ready(client_results, period)

    return GlobalPeriodResult(
        period=period, label=visible_label(period), n_clients=len(client_results),
        n_candidates_total=n_candidates_total, n_comparable_total=n_comparable_total,
        pct_comparable_global=pct_comparable_global,
        history_sum=history_sum, scp_abs_error_sum=scp_err, ml_abs_error_sum=ml_err,
        scp_wape_global=scp_wape_global, ml_wape_global=ml_wape_global,
        global_improvement_pct=global_improvement_pct, abs_error_reduction_total=scp_err - ml_err,
        winner_counts=_sum_winner_counts(client_results, period),
        client_improvement_stats=cross_entity_stats(_client_improvement_series(client_results, period)),
        series_improvement_stats=descriptive_stats(_global_series_improvement_values(client_results, period)),
        client_reduction_table=reduction_table, client_deterioration_table=deterioration_table,
        reduction_totals=reduction_totals,
        pareto_series=pareto_series, pareto_clients=pareto_clients,
        phase8=phase8,
    )


def build_client_period_table(client_results: list[ClientAnalysisResult], period: str) -> pd.DataFrame:
    """
    Perspectiva "tabla global por cliente": una fila por cliente para el
    periodo dado (docs/analysis_requirements.md, seccion "Tabla global por
    cliente").
    """
    rows = []
    for r in client_results:
        pr = r.periods.get(period)
        source = r.source
        counts = r.quality.summary_counts()
        row = {
            "ID_CLIENT": source.id_client, "ETIQUETA": source.file_label,
            "DISPLAY_NAME": source.display_name, "CSV": source.file_name,
            "ID_BATCH": source.id_batch, "ID_RUN_STAGING": source.id_run_staging,
        }
        if pr is None:
            rows.append(row)
            continue
        row.update({
            "SERIES_CANDIDATAS": pr.n_candidates, "SERIES_COMPARABLES": pr.n_comparable,
            "PCT_COMPARABLE": pr.pct_comparable,
            "HISTORICO_TOTAL": pr.wape.get("history_sum"),
            "ERROR_ABSOLUTO_SCP": pr.wape.get("scp_abs_error_sum"),
            "ERROR_ABSOLUTO_ML": pr.wape.get("ml_abs_error_sum"),
            "REDUCCION_ABSOLUTA": pr.abs_error_reduction_total,
            "WAPE_SCP": pr.wape.get("scp_wape_global"), "WAPE_ML": pr.wape.get("ml_wape_global"),
            "MEJORA_RELATIVA_PCT": pr.wape.get("improvement_pct"),
            "PCT_GANA_ML": pr.winner_counts.get("ML", {}).get("pct"),
            "PCT_GANA_SCP": pr.winner_counts.get("SCP", {}).get("pct"),
            "PCT_EMPATE": pr.winner_counts.get("TIE", {}).get("pct"),
            "MEDIA_MEJORA_POR_SERIE_PCT": pr.improvement_stats_all.get("mean"),
            "MEDIANA_MEJORA_POR_SERIE_PCT": pr.improvement_stats_all.get("median"),
            "N_EXCLUSIONES_ML": pr.n_ml_excluded, "PCT_EXCLUSIONES_ML": pr.pct_ml_excluded,
            "WARNINGS": counts.get("WARNING", 0), "ERRORS": counts.get("ERROR", 0),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def global_category_performance_table(
    client_results: list[ClientAnalysisResult], period: str, category_col: str,
) -> pd.DataFrame:
    """
    Version global de models.category_performance_table: concatena las filas
    comparables de TODOS los clientes (conservando ID_CLIENT) y anade cuantos
    clientes distintos aportan cada categoria.
    """
    pcols = period_columns(period)
    frames = []
    for r in client_results:
        pr = r.periods.get(period)
        if pr is None or pr.comparable_mask is None or r.source.dataframe is None or pr.n_comparable == 0:
            continue
        sub = r.source.dataframe.loc[pr.comparable_mask]
        if not sub.empty:
            frames.append(sub)
    if not frames:
        return pd.DataFrame()

    concatenated = pd.concat(frames, ignore_index=True)
    if category_col not in concatenated.columns:
        return pd.DataFrame()

    mask_all = pd.Series(True, index=concatenated.index)
    table = category_performance_table(concatenated, pcols, mask_all, category_col)
    if table.empty:
        return table

    concatenated = concatenated.copy()
    concatenated[category_col] = concatenated[category_col].fillna("(sin clasificar)")
    n_clients_map = concatenated.groupby(category_col, observed=True)["ID_CLIENT"].nunique()
    table["n_clients"] = table["category"].map(n_clients_map)
    return table


def analyze_global(all_results: list[ClientAnalysisResult]) -> GlobalAnalysisResult:
    """
    Orquesta la comparativa global sobre todos los clientes con fichero
    valido. Los invalidos se conservan aparte (informativos, para el
    resumen de ejecucion) pero no participan en las perspectivas globales.
    """
    valid_results = [r for r in all_results if r.file_valid and r.source.dataframe is not None]
    invalid_results = [r for r in all_results if not (r.file_valid and r.source.dataframe is not None)]

    periods = {period: build_global_period_result(valid_results, period) for period in ALL_PERIODS}
    client_period_tables = {period: build_client_period_table(valid_results, period) for period in ALL_PERIODS}

    return GlobalAnalysisResult(
        client_results=valid_results, invalid_results=invalid_results,
        periods=periods, client_period_tables=client_period_tables,
    )
