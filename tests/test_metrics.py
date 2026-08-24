import math

import numpy as np
import pandas as pd

from src.metrics import (
    BIAS_DIRECTION_NEGATIVE,
    BIAS_DIRECTION_NOT_EVALUABLE,
    BIAS_DIRECTION_POSITIVE,
    BIAS_DIRECTION_ZERO,
    CASE_BOTH_ZERO,
    CASE_MISSING_WAPE,
    CASE_ML_ZERO_SCP_POSITIVE,
    CASE_NORMAL,
    CASE_SCP_ZERO_ML_POSITIVE,
    absolute_error_reduction_row,
    absolute_error_reduction_total,
    bias_aggregate,
    both_wape_zero_mask,
    client_contribution_to_total_reduction,
    cross_entity_stats,
    descriptive_stats,
    direction_label,
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


# --------------------------------------------------------------------------
# Fase 4: evaluabilidad por metrica dentro de la poblacion COMPARABLE de 6M
# (sin redefinir poblacion). period_wape_global/absolute_error_reduction_total
# no deben calcular un agregado parcial ignorando filas con nulos en
# silencio (pandas.Series.sum() ignora NaN por defecto).
# --------------------------------------------------------------------------

def test_wape_global_nan_when_history_has_a_null_row():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [1000.0, None],
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, 5.0],
    })
    result = period_wape_global(df, pcols)
    assert math.isnan(result["history_sum"])
    assert math.isnan(result["scp_wape_global"])
    assert math.isnan(result["ml_wape_global"])
    assert math.isnan(result["improvement_pct"])


def test_wape_global_nan_only_for_affected_method_when_one_abs_error_has_a_null_row():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [1000.0, 10.0],
        pcols.scp_total_abs_error: [100.0, None],
        pcols.ml_total_abs_error: [50.0, 5.0],
    })
    result = period_wape_global(df, pcols)
    assert math.isnan(result["scp_abs_error_sum"])
    assert not math.isnan(result["ml_abs_error_sum"])
    assert math.isnan(result["scp_wape_global"])
    assert not math.isnan(result["ml_wape_global"])
    assert math.isclose(result["ml_wape_global"], 55.0 / 1010.0, rel_tol=1e-9)
    # La mejora depende de ambos WAPE: no evaluable si scp_wape_global es NaN.
    assert math.isnan(result["improvement_pct"])


def test_wape_global_unaffected_by_scp_wape_or_ml_wape_columns():
    """
    SCP_WAPE/ML_WAPE (columna distinta) no son input de period_wape_global:
    su ausencia no debe invalidar el WAPE global mientras TOTAL_HISTORY y
    los TOTAL_ABS_ERROR necesarios esten completos.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [1000.0, 10.0],
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, 5.0],
        pcols.scp_wape: [None, None],
        pcols.ml_wape: [None, None],
    })
    result = period_wape_global(df, pcols)
    assert math.isclose(result["scp_wape_global"], 105.0 / 1010.0, rel_tol=1e-9)
    assert math.isclose(result["ml_wape_global"], 55.0 / 1010.0, rel_tol=1e-9)
    assert not math.isnan(result["improvement_pct"])


def test_wape_global_no_nulls_matches_previous_behavior():
    """Regresion: sin nulos, el resultado no cambia respecto al comportamiento previo."""
    df, pcols = _wape_frame()
    result = period_wape_global(df, pcols)
    expected_weighted_scp_wape = (100.0 + 5.0) / (1000.0 + 10.0)
    assert math.isclose(result["scp_wape_global"], expected_weighted_scp_wape, rel_tol=1e-9)


def test_absolute_error_reduction_total_nan_when_scp_abs_error_has_a_null_row():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_total_abs_error: [100.0, None],
        pcols.ml_total_abs_error: [50.0, 8.0],
    })
    assert math.isnan(absolute_error_reduction_total(df, pcols))


def test_absolute_error_reduction_total_nan_when_ml_abs_error_has_a_null_row():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, None],
    })
    assert math.isnan(absolute_error_reduction_total(df, pcols))


def test_absolute_error_reduction_total_no_nulls_matches_previous_behavior():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_total_abs_error: [100.0, 5.0],
        pcols.ml_total_abs_error: [50.0, 8.0],
    })
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


# --------------------------------------------------------------------------
# Fase 8B (K.2): bias_aggregate / BiasAggregateResult / direction_label.
# --------------------------------------------------------------------------

def _bias_frame(total_history, scp_signed, ml_signed):
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: total_history,
        pcols.scp_total_signed_error: scp_signed,
        pcols.ml_total_signed_error: ml_signed,
    })
    return df, pcols


def test_bias_aggregate_positive_direction():
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, 5.0], [-50.0, -5.0])
    result = bias_aggregate(df, pcols)
    assert math.isclose(result.scp_bias_agg, 105.0 / 1010.0, rel_tol=1e-9)
    assert result.scp_direction == BIAS_DIRECTION_POSITIVE
    assert math.isclose(result.ml_bias_agg, -55.0 / 1010.0, rel_tol=1e-9)
    assert result.ml_direction == BIAS_DIRECTION_NEGATIVE


def test_bias_aggregate_zero_direction_is_exact_zero_not_tolerance():
    df, pcols = _bias_frame([1000.0, 10.0], [50.0, -50.0], [0.0, 0.0])
    result = bias_aggregate(df, pcols)
    assert result.scp_bias_agg == 0.0
    assert result.scp_direction == BIAS_DIRECTION_ZERO
    assert result.ml_bias_agg == 0.0
    assert result.ml_direction == BIAS_DIRECTION_ZERO


def test_bias_aggregate_sum_over_sum_differs_from_simple_mean_of_per_row_ratio():
    """
    BIAS_AGG = SUM(signed)/SUM(history) nunca debe coincidir, en general, con
    la media simple de (signed/history) fila a fila -- mismo principio que
    WAPE_GLOBAL frente a la media simple de WAPE por serie (CLAUDE.md).
    """
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, -5.0], [0.0, 0.0])
    result = bias_aggregate(df, pcols)
    expected_sum_over_sum = (100.0 + -5.0) / (1000.0 + 10.0)
    naive_mean_per_row = ((100.0 / 1000.0) + (-5.0 / 10.0)) / 2
    assert math.isclose(result.scp_bias_agg, expected_sum_over_sum, rel_tol=1e-9)
    assert not math.isclose(result.scp_bias_agg, naive_mean_per_row, rel_tol=1e-3)


def test_bias_aggregate_history_sum_non_positive_makes_both_not_evaluable():
    df, pcols = _bias_frame([0.0, 0.0], [10.0, 5.0], [10.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.scp_bias_agg)
    assert math.isnan(result.ml_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE


def test_bias_aggregate_history_nan_makes_both_not_evaluable():
    df, pcols = _bias_frame([1000.0, None], [10.0, 5.0], [10.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.history_sum)
    assert math.isnan(result.scp_bias_agg)
    assert math.isnan(result.ml_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE


def test_bias_aggregate_history_inf_makes_both_not_evaluable():
    df, pcols = _bias_frame([1000.0, np.inf], [10.0, 5.0], [10.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.scp_bias_agg)
    assert math.isnan(result.ml_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE


def test_bias_aggregate_history_negative_inf_makes_both_not_evaluable():
    df, pcols = _bias_frame([1000.0, -np.inf], [10.0, 5.0], [10.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.scp_bias_agg)
    assert math.isnan(result.ml_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE


def test_bias_aggregate_scp_signed_error_nan_does_not_affect_ml():
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, None], [50.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.scp_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert not math.isnan(result.ml_bias_agg)
    assert math.isclose(result.ml_bias_agg, 55.0 / 1010.0, rel_tol=1e-9)
    assert result.ml_direction == BIAS_DIRECTION_POSITIVE


def test_bias_aggregate_scp_signed_error_inf_does_not_affect_ml():
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, np.inf], [50.0, 5.0])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.scp_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert not math.isnan(result.ml_bias_agg)
    assert result.ml_direction == BIAS_DIRECTION_POSITIVE


def test_bias_aggregate_ml_signed_error_nan_does_not_affect_scp():
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, 5.0], [50.0, None])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.ml_bias_agg)
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert not math.isnan(result.scp_bias_agg)
    assert math.isclose(result.scp_bias_agg, 105.0 / 1010.0, rel_tol=1e-9)
    assert result.scp_direction == BIAS_DIRECTION_POSITIVE


def test_bias_aggregate_ml_signed_error_negative_inf_does_not_affect_scp():
    df, pcols = _bias_frame([1000.0, 10.0], [100.0, 5.0], [50.0, -np.inf])
    result = bias_aggregate(df, pcols)
    assert math.isnan(result.ml_bias_agg)
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert not math.isnan(result.scp_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_POSITIVE


def test_bias_aggregate_both_methods_valid_and_independent():
    df, pcols = _bias_frame([500.0, 500.0], [50.0, -25.0], [-10.0, 30.0])
    result = bias_aggregate(df, pcols)
    assert math.isclose(result.scp_bias_agg, 25.0 / 1000.0, rel_tol=1e-9)
    assert math.isclose(result.ml_bias_agg, 20.0 / 1000.0, rel_tol=1e-9)
    assert result.scp_direction == BIAS_DIRECTION_POSITIVE
    assert result.ml_direction == BIAS_DIRECTION_POSITIVE


def test_bias_aggregate_empty_group_is_not_evaluable():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: pd.Series(dtype=float),
        pcols.scp_total_signed_error: pd.Series(dtype=float),
        pcols.ml_total_signed_error: pd.Series(dtype=float),
    })
    result = bias_aggregate(df, pcols)
    assert result.history_sum == 0.0
    assert math.isnan(result.scp_bias_agg)
    assert math.isnan(result.ml_bias_agg)
    assert result.scp_direction == BIAS_DIRECTION_NOT_EVALUABLE
    assert result.ml_direction == BIAS_DIRECTION_NOT_EVALUABLE


def test_direction_label_never_labels_non_finite_values_positive_or_negative():
    assert direction_label(np.inf) == BIAS_DIRECTION_NOT_EVALUABLE
    assert direction_label(-np.inf) == BIAS_DIRECTION_NOT_EVALUABLE
    assert direction_label(np.nan) == BIAS_DIRECTION_NOT_EVALUABLE
    assert direction_label(5.0) == BIAS_DIRECTION_POSITIVE
    assert direction_label(-5.0) == BIAS_DIRECTION_NEGATIVE
    assert direction_label(0.0) == BIAS_DIRECTION_ZERO
