"""
Analisis de modelos y clasificaciones, y rankings por serie.

Todo el analisis de este modulo opera sobre el universo comparable de un
periodo concreto (nunca sobre el universo de cobertura completo), y siempre
distingue frecuencia de seleccion, frecuencia de victoria, tasa de victoria
y contribucion absoluta a la reduccion de error, tal como exige
docs/analysis_requirements.md ("no interpretes automaticamente el modelo mas
frecuente como el modelo que mas valor aporta").

"Veces seleccionado" se interpreta aqui como el numero de filas comparables
del periodo en las que esa categoria aparece (no el total de filas candidatas,
que incluiria series sin WAPE valido para ninguno de los dos metodos). Se
documenta explicitamente esta convencion en el 00_readme del Excel.
"""

from __future__ import annotations

import pandas as pd

from src.metrics import (
    absolute_error_reduction_row,
    absolute_error_reduction_total,
    period_wape_global,
    relative_improvement_row,
)
from src.periods import PeriodColumns

MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION = 10

RANKING_LEVEL_COLUMNS = ["VALUE_LEVEL_1", "VALUE_LEVEL_2", "VALUE_LEVEL_3", "VALUE_LEVEL_4", "VALUE_LEVEL_5"]


def category_performance_table(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series, category_col: str,
) -> pd.DataFrame:
    """
    Tabla de rendimiento por categoria (modelo o clasificacion) sobre el
    universo comparable del periodo. Sirve tanto para ML_BEST_MODEL /
    SCP_BEST_MODEL como para ML_CLASSIFICATION / ML_TYPE /
    SERIES_CLASSIFICATION / SCP_CLASSIFICATION.

    Columnas: n_comparable (frecuencia de seleccion dentro del universo
    comparable), n_win_ml, n_win_scp, n_tie, win_rate_ml_pct, scp_wape_agg,
    ml_wape_agg, improvement_agg_pct, median_improvement_pct,
    abs_error_reduction, pct_of_history_volume, small_sample.
    """
    if category_col not in df.columns:
        return pd.DataFrame()
    sub = df.loc[comparable_mask]
    if sub.empty:
        return pd.DataFrame()

    sub = sub.copy()
    sub[category_col] = sub[category_col].fillna("(sin clasificar)")
    total_history = sub[pcols.total_history].sum()

    rows = []
    for value, group in sub.groupby(category_col, dropna=False, observed=True):
        n = len(group)
        winner = group[pcols.winner_method]
        n_ml = int((winner == "ML").sum())
        n_scp = int((winner == "SCP").sum())
        n_tie = int((winner == "TIE").sum())
        wape = period_wape_global(group, pcols)
        imp_values, _cases = relative_improvement_row(group[pcols.scp_wape], group[pcols.ml_wape])
        abs_reduction = absolute_error_reduction_total(group, pcols)
        hist_sum = group[pcols.total_history].sum()
        rows.append({
            "category": value,
            "n_comparable": n,
            "n_win_ml": n_ml,
            "n_win_scp": n_scp,
            "n_tie": n_tie,
            "win_rate_ml_pct": (n_ml / n * 100) if n else float("nan"),
            "scp_wape_agg": wape["scp_wape_global"],
            "ml_wape_agg": wape["ml_wape_global"],
            "improvement_agg_pct": wape["improvement_pct"],
            "median_improvement_pct": imp_values.median() if not imp_values.dropna().empty else float("nan"),
            "abs_error_reduction": abs_reduction,
            "pct_of_history_volume": (hist_sum / total_history * 100) if total_history else float("nan"),
            "small_sample": n < MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION,
        })
    result = pd.DataFrame(rows).sort_values("n_comparable", ascending=False).reset_index(drop=True)
    return result


def _ranking_columns(pcols: PeriodColumns) -> list[str]:
    return [
        "ID_CLIENT", "ID_CONFIGURATION", *RANKING_LEVEL_COLUMNS,
        pcols.total_history, pcols.scp_total_abs_error, pcols.ml_total_abs_error,
        pcols.scp_wape, pcols.ml_wape, pcols.winner_method,
        "SCP_BEST_MODEL", "ML_BEST_MODEL", "SERIES_CLASSIFICATION",
    ]


def top_absolute_impact(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series, n: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ranking de impacto absoluto (item separado del cambio porcentual, nunca
    mezclados): top reduccion absoluta de error y top aumento absoluto.
    """
    sub = df.loc[comparable_mask]
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame()
    sub = sub.copy()
    sub["ABS_ERROR_REDUCTION"] = absolute_error_reduction_row(sub, pcols)
    cols = [c for c in _ranking_columns(pcols) if c in sub.columns]
    ordered = ["ABS_ERROR_REDUCTION", *cols]
    top_reduction = sub.sort_values("ABS_ERROR_REDUCTION", ascending=False).head(n)[ordered]
    top_increase = sub.sort_values("ABS_ERROR_REDUCTION", ascending=True).head(n)[ordered]
    return top_reduction.reset_index(drop=True), top_increase.reset_index(drop=True)


def top_percentage_changes(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series, n: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ranking de cambio porcentual: top mejora relativa y top deterioro relativo."""
    sub = df.loc[comparable_mask]
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame()
    sub = sub.copy()
    values, _cases = relative_improvement_row(sub[pcols.scp_wape], sub[pcols.ml_wape])
    sub["ML_IMPROVEMENT_VS_SCP_PCT"] = values
    sub = sub.dropna(subset=["ML_IMPROVEMENT_VS_SCP_PCT"])
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame()
    cols = [c for c in _ranking_columns(pcols) if c in sub.columns]
    ordered = ["ML_IMPROVEMENT_VS_SCP_PCT", *cols]
    top_improve = sub.sort_values("ML_IMPROVEMENT_VS_SCP_PCT", ascending=False).head(n)[ordered]
    top_worsen = sub.sort_values("ML_IMPROVEMENT_VS_SCP_PCT", ascending=True).head(n)[ordered]
    return top_improve.reset_index(drop=True), top_worsen.reset_index(drop=True)
