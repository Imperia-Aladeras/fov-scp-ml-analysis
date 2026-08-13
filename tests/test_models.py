import math

import pandas as pd

from src.models import category_performance_table, pareto_absolute_impact, top_absolute_impact, top_percentage_changes
from src.periods import period_columns
from tests.factories import build_no_comparable_dataframe, build_synthetic_client_dataframe


def test_category_performance_table_basic_correctness():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0  # excluye la fila 2 (historico 0)

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    assert set(table["category"]) == {"AutoETS", "AutoARIMA"}
    row_autoets = table[table["category"] == "AutoETS"].iloc[0]
    assert row_autoets["n_comparable"] == 1
    assert row_autoets["n_win_ml"] == 1
    assert math.isclose(row_autoets["win_rate_ml_pct"], 100.0)
    assert bool(row_autoets["small_sample"]) is True  # n=1 < 10


def test_category_performance_table_empty_when_no_comparable_rows():
    df = build_no_comparable_dataframe()
    pcols = period_columns("6M")
    empty_mask = pd.Series([False], index=df.index)
    table = category_performance_table(df, pcols, empty_mask, "ML_BEST_MODEL")
    assert table.empty


def test_category_performance_table_missing_column_returns_empty():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    mask = df["HAS_BASE_CANDIDATE"] == 1
    table = category_performance_table(df, pcols, mask, "NO_EXISTE")
    assert table.empty


def test_top_absolute_impact_orders_correctly():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    mask = (df["HAS_BASE_CANDIDATE"] == 1) & (df[pcols.total_history] > 0)
    top_reduction, top_increase = top_absolute_impact(df, pcols, mask, n=5)
    # fila 0: reduccion = 120-60=60 (positivo). fila 1: reduccion=60-180=-120 (negativo, aumento).
    assert top_reduction.iloc[0]["ID_CONFIGURATION"] == 1001
    assert top_increase.iloc[0]["ID_CONFIGURATION"] == 1002


def test_top_percentage_changes_orders_correctly():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    mask = (df["HAS_BASE_CANDIDATE"] == 1) & (df[pcols.total_history] > 0)
    top_improve, top_worsen = top_percentage_changes(df, pcols, mask, n=5)
    assert top_improve.iloc[0]["ID_CONFIGURATION"] == 1001  # ML mejora un 50%
    assert top_worsen.iloc[0]["ID_CONFIGURATION"] == 1002  # ML empeora frente a SCP


def test_top_rankings_empty_when_no_comparable_rows():
    df = build_no_comparable_dataframe()
    pcols = period_columns("6M")
    empty_mask = pd.Series([False], index=df.index)
    top_reduction, top_increase = top_absolute_impact(df, pcols, empty_mask)
    top_improve, top_worsen = top_percentage_changes(df, pcols, empty_mask)
    assert top_reduction.empty and top_increase.empty
    assert top_improve.empty and top_worsen.empty


def test_pareto_absolute_impact_top1_consistent_with_top_absolute_impact():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    mask = df["COMPARISON_STATUS"] == "COMPARABLE"
    top_reduction, top_increase = top_absolute_impact(df, pcols, mask, n=5)

    pareto = pareto_absolute_impact(df, pcols, mask)

    assert pareto.improvement.table.iloc[0]["ID_CONFIGURATION"] == top_reduction.iloc[0]["ID_CONFIGURATION"]
    assert math.isclose(
        pareto.improvement.table.iloc[0]["ABS_ERROR_REDUCTION"], top_reduction.iloc[0]["ABS_ERROR_REDUCTION"],
    )
    assert pareto.deterioration.table.iloc[0]["ID_CONFIGURATION"] == top_increase.iloc[0]["ID_CONFIGURATION"]
    assert math.isclose(
        pareto.deterioration.table.iloc[0]["ABS_ERROR_REDUCTION"], top_increase.iloc[0]["ABS_ERROR_REDUCTION"],
    )


def test_pareto_absolute_impact_nan_row_excluded_and_counted():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    df.loc[0, pcols.ml_total_abs_error] = None  # fila 0 (COMPARABLE, mejora) pierde su unico input de ML
    mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    pareto = pareto_absolute_impact(df, pcols, mask)

    assert pareto.n_no_evaluables == 1
    assert pareto.improvement.summary.n_total == 0  # ya no queda ninguna fila de mejora evaluable
    assert pareto.deterioration.summary.n_total == 1  # la fila 1 (deterioro) no se ve afectada


def _minimal_pareto_frame(comparison_status, ids, scp_abs_error, ml_abs_error):
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CLIENT": [1] * len(ids), "ID_CONFIGURATION": ids, "COMPARISON_STATUS": comparison_status,
    })
    df[pcols.scp_total_abs_error] = scp_abs_error
    df[pcols.ml_total_abs_error] = ml_abs_error
    return df, pcols


def test_pareto_absolute_impact_all_improvement_leaves_deterioration_group_empty():
    df, pcols = _minimal_pareto_frame(
        ["COMPARABLE", "COMPARABLE"], [10, 20], scp_abs_error=[50.0, 40.0], ml_abs_error=[10.0, 10.0],
    )
    mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    pareto = pareto_absolute_impact(df, pcols, mask)

    assert pareto.improvement.summary.n_total == 2
    assert pareto.deterioration.table.empty
    assert pareto.deterioration.summary.n_total == 0
    assert pareto.deterioration.summary.n_for_50 is None


def test_pareto_absolute_impact_all_deterioration_leaves_improvement_group_empty():
    df, pcols = _minimal_pareto_frame(
        ["COMPARABLE", "COMPARABLE"], [10, 20], scp_abs_error=[10.0, 10.0], ml_abs_error=[50.0, 40.0],
    )
    mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    pareto = pareto_absolute_impact(df, pcols, mask)

    assert pareto.deterioration.summary.n_total == 2
    assert pareto.improvement.table.empty
    assert pareto.improvement.summary.n_total == 0
    assert pareto.improvement.summary.n_for_50 is None
