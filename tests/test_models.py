import math

import pandas as pd

from src.models import category_performance_table, top_absolute_impact, top_percentage_changes
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
