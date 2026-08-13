import math

import numpy as np
import pandas as pd
import pytest

from src.pareto import build_pareto_analysis


def _df(values, **extra_cols):
    data = {"ID_CLIENT": [f"C{i}" for i in range(len(values))], "ABS_ERROR_REDUCTION": values}
    data.update(extra_cols)
    return pd.DataFrame(data)


def _run(values, tie_break_cols=("ID_CLIENT",), id_cols=("ID_CLIENT",), **extra_cols):
    df = _df(values, **extra_cols)
    return build_pareto_analysis(
        df, "ABS_ERROR_REDUCTION", id_cols=list(id_cols), tie_break_cols=list(tie_break_cols),
    )


def test_deterministic_order_by_magnitude_desc_then_tie_break_asc():
    df = pd.DataFrame({
        "ID_CLIENT": ["B", "A", "C"],
        "ABS_ERROR_REDUCTION": [10.0, 10.0, 5.0],
    })
    result = build_pareto_analysis(df, "ABS_ERROR_REDUCTION", id_cols=["ID_CLIENT"], tie_break_cols=["ID_CLIENT"])
    table = result.improvement.table
    assert list(table["ID_CLIENT"]) == ["A", "B", "C"]
    assert list(table["RANK"]) == [1, 2, 3]


def test_two_level_tie_break_client_then_configuration():
    df = pd.DataFrame({
        "ID_CLIENT": ["X2", "X1", "X1"],
        "ID_CONFIGURATION": ["CFG2", "CFG2", "CFG1"],
        "ABS_ERROR_REDUCTION": [10.0, 10.0, 10.0],
    })
    result = build_pareto_analysis(
        df, "ABS_ERROR_REDUCTION",
        id_cols=["ID_CLIENT", "ID_CONFIGURATION"], tie_break_cols=["ID_CLIENT", "ID_CONFIGURATION"],
    )
    table = result.improvement.table
    assert list(zip(table["ID_CLIENT"], table["ID_CONFIGURATION"])) == [
        ("X1", "CFG1"), ("X1", "CFG2"), ("X2", "CFG2"),
    ]


def test_n_for_thresholds_exact_hit():
    # cumulative: 50, 100 -> N_FOR_50 hits exactly at rank 1, N_FOR_80/90 at rank 2
    result = _run([50.0, 50.0])
    summary = result.improvement.summary
    assert summary.n_for_50 == 1
    assert summary.n_for_80 == 2
    assert summary.n_for_90 == 2


def test_n_for_thresholds_jump_over_no_exact_hit():
    # sorted by magnitude desc: 34, 33, 33 -> cumulative 34, 67, 100:
    # no rank lands exactly on 50, 80 or 90.
    result = _run([34.0, 33.0, 33.0])
    summary = result.improvement.summary
    assert summary.n_for_50 == 2  # 34 -> 67, first >= 50
    assert summary.n_for_80 == 3  # 67 -> 100, first >= 80
    assert summary.n_for_90 == 3


def test_single_element_group():
    result = _run([42.0])
    summary = result.improvement.summary
    table = result.improvement.table
    assert summary.n_total == 1
    assert summary.n_for_50 == summary.n_for_80 == summary.n_for_90 == 1
    assert math.isclose(table["PCT_OF_GROUP"].iloc[0], 100.0)
    assert math.isclose(table["CUMULATIVE_PCT"].iloc[0], 100.0)


def test_empty_improvement_group_when_all_deterioration():
    result = _run([-10.0, -5.0])
    assert result.improvement.table.empty
    summary = result.improvement.summary
    assert summary.n_total == 0
    assert summary.total_impact == 0.0
    assert summary.n_for_50 is None
    assert summary.n_for_80 is None
    assert summary.n_for_90 is None


def test_empty_deterioration_group_when_all_improvement():
    result = _run([10.0, 5.0])
    assert result.deterioration.table.empty
    summary = result.deterioration.summary
    assert summary.n_total == 0
    assert summary.total_impact == 0.0


def test_both_groups_empty_when_all_values_zero_or_nan():
    result = _run([0.0, float("nan")])
    assert result.improvement.table.empty
    assert result.deterioration.table.empty
    assert result.n_no_evaluables == 1


def test_nan_rows_excluded_from_both_groups_and_counted():
    result = _run([10.0, float("nan"), -5.0, float("nan")])
    assert result.n_no_evaluables == 2
    assert result.improvement.summary.n_total == 1
    assert result.deterioration.summary.n_total == 1
    # los NaN no deben sesgar el total de magnitud de ningun grupo
    assert math.isclose(result.improvement.summary.total_impact, 10.0)
    assert math.isclose(result.deterioration.summary.total_impact, 5.0)


def test_zero_values_excluded_from_both_groups():
    result = _run([10.0, 0.0, -5.0, 0.0])
    assert result.improvement.summary.n_total == 1
    assert result.deterioration.summary.n_total == 1
    assert result.n_no_evaluables == 0


def test_pct_of_group_sums_to_100_within_non_empty_group():
    result = _run([30.0, 20.0, 10.0])
    total_pct = result.improvement.table["PCT_OF_GROUP"].sum()
    assert math.isclose(total_pct, 100.0, rel_tol=1e-9)
    assert math.isclose(result.improvement.table["CUMULATIVE_PCT"].iloc[-1], 100.0, rel_tol=1e-9)


def test_deterioration_group_uses_absolute_magnitude_for_pct_and_keeps_signed_value_column():
    result = _run([-30.0, -10.0])
    table = result.deterioration.table
    # ordenado por magnitud (abs) desc: -30 primero
    assert list(table["ABS_ERROR_REDUCTION"]) == [-30.0, -10.0]
    assert math.isclose(table["PCT_OF_GROUP"].iloc[0], 75.0)
    assert math.isclose(table["PCT_OF_GROUP"].iloc[1], 25.0)


def test_never_mixes_signs_in_same_denominator():
    result = _run([100.0, -1.0])
    # el 100% de mejora es del propio 100 (no diluido por el -1 de deterioro)
    assert math.isclose(result.improvement.table["PCT_OF_GROUP"].iloc[0], 100.0)
    assert math.isclose(result.deterioration.table["PCT_OF_GROUP"].iloc[0], 100.0)


def test_raises_when_value_col_missing():
    df = pd.DataFrame({"ID_CLIENT": ["C0", "C1"]})
    with pytest.raises(ValueError, match="ABS_ERROR_REDUCTION"):
        build_pareto_analysis(df, "ABS_ERROR_REDUCTION", id_cols=["ID_CLIENT"], tie_break_cols=["ID_CLIENT"])


def test_raises_when_required_id_col_missing():
    df = pd.DataFrame({"ID_CLIENT": ["C0", "C1"], "ABS_ERROR_REDUCTION": [10.0, -5.0]})
    with pytest.raises(ValueError, match="ID_CONFIGURATION"):
        build_pareto_analysis(
            df, "ABS_ERROR_REDUCTION",
            id_cols=["ID_CLIENT", "ID_CONFIGURATION"], tie_break_cols=["ID_CLIENT"],
        )


def test_raises_when_required_tie_break_col_missing():
    df = pd.DataFrame({"ID_CLIENT": ["C0", "C1"], "ABS_ERROR_REDUCTION": [10.0, -5.0]})
    with pytest.raises(ValueError, match="ID_CONFIGURATION"):
        build_pareto_analysis(
            df, "ABS_ERROR_REDUCTION",
            id_cols=["ID_CLIENT"], tie_break_cols=["ID_CLIENT", "ID_CONFIGURATION"],
        )
