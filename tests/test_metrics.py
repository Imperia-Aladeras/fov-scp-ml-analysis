import math

import numpy as np
import pandas as pd

from src.metrics import (
    CASE_BOTH_ZERO,
    CASE_MISSING_WAPE,
    CASE_ML_ZERO_SCP_POSITIVE,
    CASE_NORMAL,
    CASE_SCP_ZERO_ML_POSITIVE,
    absolute_error_reduction_row,
    absolute_error_reduction_total,
    both_wape_zero_mask,
    client_contribution_to_total_reduction,
    cross_entity_stats,
    descriptive_stats,
    period_wape_global,
    relative_improvement_row,
    safe_divide,
    winner_distribution,
)
from src.periods import period_columns


def test_safe_divide_returns_nan_for_zero_or_negative_denominator():
    numerator = pd.Series([10.0, 20.0, 30.0])
    denominator = pd.Series([2.0, 0.0, -5.0])
    result = safe_divide(numerator, denominator)
    assert result.iloc[0] == 5.0
    assert math.isnan(result.iloc[1])
    assert math.isnan(result.iloc[2])


def _wape_frame():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [1000.0, 10.0],
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, 5.0],
    })
    return df, pcols


def test_wape_global_is_weighted_not_a_simple_average_of_series_wape():
    df, pcols = _wape_frame()
    result = period_wape_global(df, pcols)

    naive_avg_scp_wape = ((100.0 / 1000.0) + (5.0 / 10.0)) / 2
    expected_weighted_scp_wape = (100.0 + 5.0) / (1000.0 + 10.0)

    assert math.isclose(result["scp_wape_global"], expected_weighted_scp_wape, rel_tol=1e-9)
    assert not math.isclose(result["scp_wape_global"], naive_avg_scp_wape, rel_tol=1e-3)


def test_wape_global_nan_when_history_sum_is_zero():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [0.0, 0.0],
        pcols.scp_total_abs_error: [0.0, 0.0],
        pcols.ml_total_abs_error: [0.0, 0.0],
    })
    result = period_wape_global(df, pcols)
    assert math.isnan(result["scp_wape_global"])
    assert math.isnan(result["ml_wape_global"])


def test_absolute_error_reduction_row_and_total():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, 8.0],
    })
    row = absolute_error_reduction_row(df, pcols)
    assert row.tolist() == [50.0, -3.0]
    assert absolute_error_reduction_total(df, pcols) == 47.0


def test_relative_improvement_row_normal_case():
    scp = pd.Series([0.2])
    ml = pd.Series([0.1])
    values, cases = relative_improvement_row(scp, ml)
    assert math.isclose(values.iloc[0], 50.0)
    assert cases.iloc[0] == CASE_NORMAL


def test_relative_improvement_row_both_zero():
    scp = pd.Series([0.0])
    ml = pd.Series([0.0])
    values, cases = relative_improvement_row(scp, ml)
    assert math.isnan(values.iloc[0])
    assert cases.iloc[0] == CASE_BOTH_ZERO


def test_relative_improvement_row_scp_zero_ml_positive():
    scp = pd.Series([0.0])
    ml = pd.Series([0.1])
    values, cases = relative_improvement_row(scp, ml)
    assert math.isnan(values.iloc[0])
    assert cases.iloc[0] == CASE_SCP_ZERO_ML_POSITIVE


def test_relative_improvement_row_scp_near_zero_floating_point_noise_is_treated_as_zero():
    """
    Regresion: SCP_WAPE=2e-16 (ruido de punto flotante, no 0.0 exacto) usado
    como denominador producia mejoras de billones de por ciento (caso real
    detectado en el cliente 10204, ID_CONFIGURATION 8590, M1). Debe tratarse
    como SCP_ZERO_ML_POSITIVE (NaN), no como NORMAL.
    """
    scp = pd.Series([2e-16])
    ml = pd.Series([0.171875])
    values, cases = relative_improvement_row(scp, ml)
    assert math.isnan(values.iloc[0])
    assert cases.iloc[0] == CASE_SCP_ZERO_ML_POSITIVE


def test_relative_improvement_row_object_dtype_with_none_does_not_crash():
    scp = pd.Series([None, 0.2], dtype=object)
    ml = pd.Series([None, 0.1], dtype=object)
    values, cases = relative_improvement_row(scp, ml)
    assert cases.tolist() == [CASE_MISSING_WAPE, CASE_NORMAL]
    assert math.isclose(values.iloc[1], 50.0)


def test_both_wape_zero_mask_treats_floating_point_noise_as_zero():
    scp = pd.Series([2e-16, 0.0])
    ml = pd.Series([3e-17, 0.0])
    mask = both_wape_zero_mask(scp, ml)
    assert mask.tolist() == [True, True]


def test_relative_improvement_row_ml_zero_scp_positive_is_defined_as_100pct():
    scp = pd.Series([0.4])
    ml = pd.Series([0.0])
    values, cases = relative_improvement_row(scp, ml)
    assert math.isclose(values.iloc[0], 100.0)
    assert cases.iloc[0] == CASE_ML_ZERO_SCP_POSITIVE


def test_relative_improvement_row_missing_wape():
    scp = pd.Series([0.3, None])
    ml = pd.Series([None, 0.1])
    values, cases = relative_improvement_row(scp, ml)
    assert values.isna().all()
    assert (cases == CASE_MISSING_WAPE).all()


def test_descriptive_stats_extremes_and_percentiles():
    series = pd.Series([-150.0, -50.0, 0.0, 50.0, 90.0, 150.0])
    stats = descriptive_stats(series)
    assert stats["count"] == 6
    assert stats["n_below_-100"] == 1
    assert stats["n_above_100"] == 1
    assert math.isclose(stats["pct_below_-100"], 100 / 6)
    assert stats["min"] == -150.0
    assert stats["max"] == 150.0
    assert math.isclose(stats["median"], 25.0)


def test_descriptive_stats_empty_series():
    stats = descriptive_stats(pd.Series(dtype=float))
    assert stats["count"] == 0
    assert math.isnan(stats["mean"])


def test_winner_distribution_counts_and_percentages():
    winner = pd.Series(["ML", "ML", "SCP", "TIE", None])
    dist = winner_distribution(winner)
    assert dist["_total"] == 4
    assert dist["ML"]["n"] == 2
    assert math.isclose(dist["ML"]["pct"], 50.0)
    assert dist["SCP"]["n"] == 1
    assert dist["TIE"]["n"] == 1


def test_both_wape_zero_mask_only_flags_fully_specified_case():
    scp = pd.Series([0.0, 0.0, 0.2, None])
    ml = pd.Series([0.0, 0.1, 0.1, 0.0])
    mask = both_wape_zero_mask(scp, ml)
    # fila 0: ambos 0 -> True. fila 1: ml!=0 -> False. fila 2: scp!=0 -> False.
    # fila 3: scp nulo -> False (no se puede afirmar nada sin dato).
    assert mask.tolist() == [True, False, False, False]


def test_client_contribution_to_total_reduction():
    reductions = pd.Series([50.0, 30.0, 20.0])
    contribution = client_contribution_to_total_reduction(reductions)
    assert contribution.tolist() == [50.0, 30.0, 20.0]


def test_client_contribution_to_total_reduction_zero_total_is_nan():
    reductions = pd.Series([10.0, -10.0])
    contribution = client_contribution_to_total_reduction(reductions)
    assert contribution.isna().all()


def test_cross_entity_stats_equal_weight_mean_median_and_improved_worse_tie():
    values = pd.Series([10.0, -5.0, 0.0, 20.0, -10.0])
    stats = cross_entity_stats(values, tie_epsilon=0.0)
    assert math.isclose(stats["mean"], np.mean([10.0, -5.0, 0.0, 20.0, -10.0]))
    assert math.isclose(stats["median"], 0.0)
    assert stats["n_improved"] == 2
    assert stats["n_worse"] == 2
    assert stats["n_tie"] == 1
