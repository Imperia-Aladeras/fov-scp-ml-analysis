import math

import pandas as pd

from src.metrics import absolute_error_reduction_total
from src.models import category_performance_table, pareto_absolute_impact, top_absolute_impact, top_percentage_changes
from src.periods import period_columns
from tests.factories import build_no_comparable_dataframe, build_synthetic_client_dataframe, set_period


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


# --------------------------------------------------------------------------
# Fase 9B: invariantes test-only de category_performance_table (protegen
# calculos derivados del propio proyecto; NO son quality checks runtime -- si
# alguno falla es un bug de este modulo, no un problema de datos backend, ver
# plan aprobado en Fase 9A).
# --------------------------------------------------------------------------

def test_category_performance_table_winner_buckets_sum_to_n_comparable_when_domain_valid():
    """
    Invariante A: cuando WINNER_METHOD pertenece al dominio valido
    ({"ML","SCP","TIE"}, sin nulos en la poblacion comparable),
    n_win_ml+n_win_scp+n_tie debe coincidir exactamente con n_comparable por
    categoria. No hay categoria con n=0 representable via esta API (groupby
    nunca produce grupos vacios), por lo que ese edge case queda excluido sin
    forzar un escenario artificial.
    """
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")

    assert not table.empty
    bucket_sum = table["n_win_ml"] + table["n_win_scp"] + table["n_tie"]
    assert (bucket_sum == table["n_comparable"]).all()


def test_category_performance_table_winner_buckets_exclude_unexpected_values():
    """
    Contrapunto de la invariante A: un WINNER_METHOD fuera de {"ML","SCP","TIE"}
    en fila comparable NO se cuenta en ningun bucket, por lo que la suma queda
    por debajo de n_comparable. Documenta el comportamiento actual
    explicitamente en vez de asumirlo en silencio -- la deteccion de ese valor
    inesperado es responsabilidad de quality_checks.check_invalid_winner_method_value
    (METRIC_003), no de esta tabla.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({"ID_CLIENT": [1, 1, 1], "ID_CONFIGURATION": [1, 2, 3], "CATEGORY": ["A", "A", "A"]})
    set_period(
        df, "6M",
        total_history=[100.0, 100.0, 100.0],
        scp_forecast=[110.0, 110.0, 110.0], scp_abs_error=[10.0, 10.0, 10.0], scp_wape=[0.1, 0.1, 0.1],
        ml_forecast=[105.0, 105.0, 105.0], ml_abs_error=[5.0, 5.0, 5.0], ml_wape=[0.05, 0.05, 0.05],
        winner_method=["ML", "SCP", "DRAW"],
    )
    comparable_mask = pd.Series([True, True, True])

    table = category_performance_table(df, pcols, comparable_mask, "CATEGORY")

    row = table.iloc[0]
    assert row["n_comparable"] == 3
    assert row["n_win_ml"] + row["n_win_scp"] + row["n_tie"] == 2  # "DRAW" no cuenta en ningun bucket


def test_category_performance_table_win_rate_ml_pct_within_bounds():
    """Invariante B: win_rate_ml_pct debe estar en [0,100] cuando evaluable (n>0)."""
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")

    evaluable = table["win_rate_ml_pct"].dropna()
    assert not evaluable.empty
    assert (evaluable >= 0).all() and (evaluable <= 100).all()


def test_category_performance_table_pct_of_history_volume_within_bounds_when_evaluable():
    """Invariante C: pct_of_history_volume debe estar en [0,100] cuando evaluable."""
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")

    evaluable = table["pct_of_history_volume"].dropna()
    assert not evaluable.empty
    assert (evaluable >= 0).all() and (evaluable <= 100).all()


def test_category_performance_table_pct_of_history_volume_sums_to_100_for_full_partition():
    """Invariante D: para una particion completa y evaluable, la suma de pct_of_history_volume ~= 100%."""
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")

    assert math.isclose(table["pct_of_history_volume"].sum(), 100.0, abs_tol=0.01)


def test_category_performance_table_pct_of_history_volume_not_forced_to_100_when_total_history_zero():
    """Invariante D, caso borde: total_history global = 0 -> no evaluable, NO se fuerza a 100%."""
    pcols = period_columns("6M")
    df = pd.DataFrame({"ID_CLIENT": [1, 1], "ID_CONFIGURATION": [1, 2], "CATEGORY": ["A", "B"]})
    set_period(
        df, "6M",
        total_history=[0.0, 0.0],
        scp_forecast=[0.0, 0.0], scp_abs_error=[0.0, 0.0], scp_wape=[None, None],
        ml_forecast=[0.0, 0.0], ml_abs_error=[0.0, 0.0], ml_wape=[None, None],
        winner_method=["TIE", "TIE"],
    )
    comparable_mask = pd.Series([True, True])

    table = category_performance_table(df, pcols, comparable_mask, "CATEGORY")

    assert table["pct_of_history_volume"].isna().all()


def test_category_performance_table_abs_error_reduction_sums_to_client_total_same_population():
    """
    Invariante E (categoria -> cliente): dentro del MISMO periodo y la MISMA
    poblacion comparable, la suma de abs_error_reduction por categoria debe
    coincidir con el total calculado sobre toda esa poblacion
    (metrics.absolute_error_reduction_total). NO se prueba aditividad entre
    periodos distintos (p.ej. RECENT_3M+OLDER_3M vs 6M): serian poblaciones
    potencialmente distintas. La aditividad cliente -> global ya esta cubierta
    por tests/test_global_analysis.py (Fase 8: REDUCCION_NETA = suma de
    abs_error_reduction_total por cliente).
    """
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    client_total = absolute_error_reduction_total(df.loc[comparable_mask], pcols)

    assert math.isclose(table["abs_error_reduction"].sum(), client_total, rel_tol=1e-4, abs_tol=1e-6)


def test_category_performance_table_abs_error_reduction_nan_propagates_not_skipped():
    """
    Invariante E, caso borde: si una categoria tiene abs_error_reduction NaN
    (por un input faltante en alguna de sus filas), el total del cliente sobre
    la MISMA poblacion comparable tambien debe ser NaN -- el contrato de
    metrics.absolute_error_reduction_total exige que un NaN nunca desaparezca
    silenciosamente por un sum() con skipna. Una comparacion ingenua contra
    table["abs_error_reduction"].sum() (skipna=True por defecto en pandas) NO
    detectaria esta ausencia de propagacion; por eso el invariante se valida
    contra absolute_error_reduction_total explicitamente.
    """
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    df.loc[0, pcols.ml_total_abs_error] = None  # categoria "AutoETS" pierde su unico input de ML
    comparable_mask = df["COMPARISON_STATUS"] == "COMPARABLE"

    table = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    client_total = absolute_error_reduction_total(df.loc[comparable_mask], pcols)

    row_autoets = table[table["category"] == "AutoETS"].iloc[0]
    assert pd.isna(row_autoets["abs_error_reduction"])
    assert pd.isna(client_total)
    naive_sum = table["abs_error_reduction"].sum()  # skipna=True por defecto: NO detecta la ausencia de propagacion
    assert not pd.isna(naive_sum)


def test_category_performance_table_small_sample_boundary_n9_true_n10_false():
    """
    Invariante F: small_sample == (n_comparable < 10), estrictamente. n=0 no
    es representable como fila de esta tabla (groupby nunca produce grupos
    vacios; ver test_category_performance_table_empty_when_no_comparable_rows
    para el caso de poblacion comparable vacia), por lo que no se fuerza ese
    escenario artificialmente.
    """
    pcols = period_columns("6M")
    n9, n10 = 9, 10
    ids = list(range(1, n9 + n10 + 1))
    categories = ["GROUP9"] * n9 + ["GROUP10"] * n10
    df = pd.DataFrame({"ID_CLIENT": [1] * len(ids), "ID_CONFIGURATION": ids, "CATEGORY": categories})
    set_period(
        df, "6M",
        total_history=[100.0] * len(ids),
        scp_forecast=[110.0] * len(ids), scp_abs_error=[10.0] * len(ids), scp_wape=[0.1] * len(ids),
        ml_forecast=[105.0] * len(ids), ml_abs_error=[5.0] * len(ids), ml_wape=[0.05] * len(ids),
        winner_method=["ML"] * len(ids),
    )
    comparable_mask = pd.Series([True] * len(ids))

    table = category_performance_table(df, pcols, comparable_mask, "CATEGORY")

    row9 = table[table["category"] == "GROUP9"].iloc[0]
    row10 = table[table["category"] == "GROUP10"].iloc[0]
    assert row9["n_comparable"] == 9 and bool(row9["small_sample"]) is True
    assert row10["n_comparable"] == 10 and bool(row10["small_sample"]) is False
