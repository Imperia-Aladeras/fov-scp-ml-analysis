"""Phase 10B.5: descriptive model/classification stability and transitions."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.global_analysis import analyze_global
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS,
    STABILITY_PERFORMANCE_COLUMNS,
    STABILITY_STATE_CHANGED,
    STABILITY_STATE_STABLE,
    STABILITY_SUMMARY_COLUMNS,
    STABILITY_TYPE_CLASSIFICATION,
    STABILITY_TYPE_MODEL,
    TRANSITION_COLUMNS,
    PortfolioContractError,
    build_portfolio_stability_analysis,
)
from tests.factories import build_synthetic_client_dataframe
from tests.test_portfolio import _client_result, _portfolio_dataframe


def _summary_row(table: pd.DataFrame, engine: str) -> pd.Series:
    selected = table[table["engine"] == engine]
    assert len(selected) == 1
    return selected.iloc[0]


def _cohort_row(table: pd.DataFrame, engine: str, model_name: str) -> pd.Series:
    selected = table[
        (table["engine"] == engine)
        & (table["model_name"] == model_name)
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def _performance_row(
    table: pd.DataFrame,
    stability_type: str,
    engine: str,
    block: str,
    state: str,
) -> pd.Series:
    selected = table[
        (table["stability_type"] == stability_type)
        & (table["engine"] == engine)
        & (table["block"] == block)
        & (table["stability_state"] == state)
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def _state_dataframe(id_client: int = 99999) -> pd.DataFrame:
    df = _portfolio_dataframe(id_client)
    df["SCP_MODEL_OLDER_3M"] = ["A", "A", None]
    df["SCP_MODEL_RECENT_3M"] = ["A", "B", "DestinationOnly"]
    df["ML_BEST_MODEL_OLDER_3M"] = ["A", "A", None]
    df["ML_BEST_MODEL_RECENT_3M"] = ["A", "B", "DestinationOnly"]
    df["ML_CLASSIFICATION_OLDER_3M"] = ["smooth", "smooth", None]
    df["ML_CLASSIFICATION_RECENT_3M"] = ["smooth", "erratic", "lumpy"]
    return df


def test_model_summary_states_and_denominator_cover_every_pair_for_both_engines():
    result = _client_result(_state_dataframe())
    summary = result.portfolio.stability.model_summary

    assert tuple(summary.columns) == STABILITY_SUMMARY_COLUMNS
    for engine in (ENGINE_SCP_AUTO, ENGINE_OPTIMIZER):
        row = _summary_row(summary, engine)
        assert row["stable_count"] == 1
        assert row["changed_count"] == 1
        assert row["not_evaluable_count"] == 1
        assert row["n_evaluable"] == row["stable_count"] + row["changed_count"] == 2
        assert row["stability_rate"] == 0.5

    events = result.portfolio.events.dataframe
    assert summary[["stable_count", "changed_count", "not_evaluable_count"]].sum(axis=1).eq(
        events.groupby("engine", observed=True)["source_series_key"].nunique().to_numpy()
    ).all()


def test_each_missing_pattern_is_not_evaluable_and_zero_denominator_is_nan():
    df = _portfolio_dataframe()
    df["ML_BEST_MODEL_OLDER_3M"] = [None, "OlderOnly", None]
    df["ML_BEST_MODEL_RECENT_3M"] = ["RecentOnly", None, None]
    result = _client_result(df)
    row = _summary_row(result.portfolio.stability.model_summary, ENGINE_OPTIMIZER)

    assert row["n_evaluable"] == 0
    assert row["stable_count"] == 0
    assert row["changed_count"] == 0
    assert row["not_evaluable_count"] == 3
    assert math.isnan(row["stability_rate"])
    assert result.portfolio.stability.model_transitions.query(
        "engine == @ENGINE_OPTIMIZER"
    ).empty
    assert result.portfolio.stability.model_by_older_model.query(
        "engine == @ENGINE_OPTIMIZER"
    ).empty


def test_comparison_is_exact_case_sensitive_without_aliases_or_normalization():
    df = _portfolio_dataframe()
    df["ML_BEST_MODEL_OLDER_3M"] = ["CaseModel", "CaseModel", " Alias "]
    df["ML_BEST_MODEL_RECENT_3M"] = ["casemodel", "CaseModel", "Alias"]
    result = _client_result(df)
    row = _summary_row(result.portfolio.stability.model_summary, ENGINE_OPTIMIZER)

    assert row["stable_count"] == 1
    assert row["changed_count"] == 2
    transitions = result.portfolio.stability.model_transitions.query(
        "engine == @ENGINE_OPTIMIZER"
    )
    assert ((transitions["older_value"] == "CaseModel") &
            (transitions["recent_value"] == "casemodel")).any()
    assert ((transitions["older_value"] == " Alias ") &
            (transitions["recent_value"] == "Alias")).any()


def test_model_stability_cohort_is_defined_only_by_older_model():
    result = _client_result(_state_dataframe())
    table = result.portfolio.stability.model_by_older_model

    assert tuple(table.columns) == MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS
    for engine in (ENGINE_SCP_AUTO, ENGINE_OPTIMIZER):
        cohort = _cohort_row(table, engine, "A")
        assert cohort["n_evaluable"] == 2
        assert cohort["stable_count"] == 1
        assert cohort["changed_count"] == 1
        assert cohort["stability_rate"] == 0.5
        assert not (
            (table["engine"] == engine)
            & table["model_name"].isin(["B", "DestinationOnly"])
        ).any()
    assert table["model_name"].notna().all()


def test_model_transitions_include_diagonal_and_cover_all_evaluable_pairs():
    result = _client_result(_state_dataframe())
    transitions = result.portfolio.stability.model_transitions

    assert tuple(transitions.columns) == TRANSITION_COLUMNS
    for engine in (ENGINE_SCP_AUTO, ENGINE_OPTIMIZER):
        scope = transitions[transitions["engine"] == engine]
        assert list(scope[["older_value", "recent_value"]].itertuples(index=False, name=None)) == [
            ("A", "A"),
            ("A", "B"),
        ]
        assert scope["transition_count"].sum() == 2
        assert scope["n_evaluable"].eq(2).all()
        assert scope["transition_share_of_evaluable"].sum() == pytest.approx(1.0)
        assert scope["older_value"].notna().all()
        assert scope["recent_value"].notna().all()


def test_pairing_uses_full_source_series_key_and_rejects_duplicate_block_event():
    result = _client_result(_portfolio_dataframe())
    events = result.portfolio.events.dataframe
    base = events[
        (events["engine"] == ENGINE_OPTIMIZER)
        & (events["ID_CONFIGURATION"] == 1001)
    ].copy()
    duplicate_identity = base.copy()
    duplicate_identity["ID_BATCH"] = 2
    duplicate_identity["source_series_key"] = duplicate_identity["source_series_key"].map(
        lambda key: (2, *key[1:])
    )
    two_full_keys = pd.concat([base, duplicate_identity], ignore_index=True)
    summary = build_portfolio_stability_analysis(two_full_keys).model_summary
    assert _summary_row(summary, ENGINE_OPTIMIZER)["n_evaluable"] == 2

    duplicate_block = pd.concat([base, base.iloc[[0]]], ignore_index=True)
    with pytest.raises(PortfolioContractError, match=r"source_series_key \+ engine \+ block"):
        build_portfolio_stability_analysis(duplicate_block)


def test_optimizer_classification_summary_and_transitions_use_block_values_only():
    df = _state_dataframe()
    df["ML_CLASSIFICATION"] = "LegacyMustNotBeUsed"
    df["ML_TYPE"] = "LegacyTypeMustNotBeUsed"
    df["SERIES_CLASSIFICATION"] = "LegacySeriesMustNotBeUsed"
    df["SCP_CLASSIFICATION"] = "LegacyScpMustNotBeUsed"
    result = _client_result(df)
    stability = result.portfolio.stability
    summary = stability.classification_summary
    transitions = stability.classification_transitions

    assert set(summary["engine"]) == {ENGINE_OPTIMIZER}
    row = _summary_row(summary, ENGINE_OPTIMIZER)
    assert row["stable_count"] == 1
    assert row["changed_count"] == 1
    assert row["not_evaluable_count"] == 1
    assert row["n_evaluable"] == 2
    assert row["stability_rate"] == 0.5
    assert set(transitions["engine"]) == {ENGINE_OPTIMIZER}
    assert set(transitions[["older_value", "recent_value"]].itertuples(index=False, name=None)) == {
        ("smooth", "smooth"),
        ("smooth", "erratic"),
    }
    assert transitions["transition_count"].sum() == 2
    assert transitions["transition_share_of_evaluable"].sum() == pytest.approx(1.0)
    assert not set(transitions["older_value"]).intersection({
        "LegacyMustNotBeUsed", "LegacyTypeMustNotBeUsed",
        "LegacySeriesMustNotBeUsed", "LegacyScpMustNotBeUsed",
    })


def test_all_missing_block_classification_never_falls_back_to_legacy():
    df = _portfolio_dataframe()
    df["ML_CLASSIFICATION_OLDER_3M"] = None
    df["ML_CLASSIFICATION_RECENT_3M"] = None
    df["ML_CLASSIFICATION"] = "LegacyMustNotBeUsed"
    result = _client_result(df)
    stability = result.portfolio.stability
    row = _summary_row(stability.classification_summary, ENGINE_OPTIMIZER)

    assert row["n_evaluable"] == 0
    assert row["not_evaluable_count"] == 3
    assert math.isnan(row["stability_rate"])
    assert stability.classification_transitions.empty
    assert _summary_row(stability.model_summary, ENGINE_OPTIMIZER)["n_evaluable"] == 3


def _performance_events() -> pd.DataFrame:
    result = _client_result(_portfolio_dataframe())
    events = result.portfolio.events.dataframe.copy()
    definitions = {
        1001: ("Stable", "Stable"),
        1002: ("ChangedA", "RecentA"),
        1003: ("ChangedB", "RecentB"),
    }
    events["performance_evaluable"] = False

    for configuration, (older_model, recent_model) in definitions.items():
        events.loc[
            (events["ID_CONFIGURATION"] == configuration)
            & (events["block"] == BLOCK_OLDER_3M),
            "model_name",
        ] = older_model
        events.loc[
            (events["ID_CONFIGURATION"] == configuration)
            & (events["block"] == BLOCK_RECENT_3M),
            "model_name",
        ] = recent_model

    metric_values = {
        1001: (200.0, 40.0, 20.0, 40.0, 20.0, 0.2, 0.1, "ML"),
        1002: (100.0, 20.0, 10.0, 20.0, 10.0, 0.2, 0.1, "SCP"),
        1003: (900.0, 90.0, 180.0, -90.0, 180.0, 0.1, 0.2, "ML"),
    }
    performance_keys = {
        (BLOCK_OLDER_3M, 1002),
        (BLOCK_OLDER_3M, 1003),
        (BLOCK_RECENT_3M, 1001),
        (BLOCK_RECENT_3M, 1003),
    }
    metric_columns = [
        "total_history",
        "scp_total_abs_error",
        "optimizer_total_abs_error",
        "scp_total_signed_error",
        "optimizer_total_signed_error",
        "scp_wape",
        "optimizer_wape",
        "winner_method",
    ]
    for block, configuration in performance_keys:
        mask = (
            events["block"].eq(block)
            & events["ID_CONFIGURATION"].eq(configuration)
        )
        events.loc[mask, "performance_evaluable"] = True
        events.loc[mask, metric_columns] = metric_values[configuration]
    return events


def test_performance_by_model_stability_is_block_specific_and_uses_ratio_of_sums():
    performance = build_portfolio_stability_analysis(
        _performance_events()
    ).performance_by_stability
    older_changed = _performance_row(
        performance,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        STABILITY_STATE_CHANGED,
    )
    recent_stable = _performance_row(
        performance,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_RECENT_3M,
        STABILITY_STATE_STABLE,
    )

    assert tuple(performance.columns) == STABILITY_PERFORMANCE_COLUMNS
    assert "volume_share" not in performance.columns
    assert older_changed["n_performance"] == 2
    assert older_changed["historical_volume"] == 1000.0
    assert older_changed["scp_wape"] == pytest.approx((20 + 90) / 1000)
    assert older_changed["optimizer_wape"] == pytest.approx((10 + 180) / 1000)
    assert older_changed["scp_bias"] == pytest.approx((20 - 90) / 1000)
    assert older_changed["optimizer_bias"] == pytest.approx((10 + 180) / 1000)
    assert older_changed["selected_engine_win_count"] == 1
    assert older_changed["tie_count"] == 0
    assert older_changed["selected_engine_win_rate"] == 0.5
    assert older_changed["optimizer_improvement_vs_scp"] == pytest.approx((0.11 - 0.19) / 0.11 * 100)
    assert older_changed["optimizer_median_improvement_vs_scp"] == pytest.approx(-25.0)
    assert older_changed["optimizer_abs_error_reduction_vs_scp"] == -80.0
    assert bool(older_changed["small_sample"]) is True

    # The stable pair has RECENT performance but no OLDER performance.
    assert recent_stable["n_performance"] == 1
    assert performance[
        (performance["stability_type"] == STABILITY_TYPE_MODEL)
        & (performance["engine"] == ENGINE_OPTIMIZER)
        & (performance["block"] == BLOCK_OLDER_3M)
        & (performance["stability_state"] == STABILITY_STATE_STABLE)
    ].empty


def test_performance_direction_is_fixed_but_selected_engine_win_rate_is_symmetric():
    performance = build_portfolio_stability_analysis(
        _performance_events()
    ).performance_by_stability
    scp = _performance_row(
        performance,
        STABILITY_TYPE_MODEL,
        ENGINE_SCP_AUTO,
        BLOCK_OLDER_3M,
        STABILITY_STATE_CHANGED,
    )
    optimizer = _performance_row(
        performance,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        STABILITY_STATE_CHANGED,
    )

    assert scp["selected_engine_win_count"] == optimizer["selected_engine_win_count"] == 1
    assert scp["selected_engine_win_rate"] == optimizer["selected_engine_win_rate"] == 0.5
    assert scp["optimizer_improvement_vs_scp"] == optimizer["optimizer_improvement_vs_scp"]
    assert (
        scp["optimizer_abs_error_reduction_vs_scp"]
        == optimizer["optimizer_abs_error_reduction_vs_scp"]
        == -80.0
    )


def test_classification_performance_exists_only_for_optimizer_and_evaluable_blocks():
    performance = _client_result(
        _state_dataframe()
    ).portfolio.stability.performance_by_stability
    classification = performance[
        performance["stability_type"] == STABILITY_TYPE_CLASSIFICATION
    ]

    assert set(classification["engine"]) == {ENGINE_OPTIMIZER}
    assert set(classification["stability_state"]) == {
        STABILITY_STATE_STABLE,
        STABILITY_STATE_CHANGED,
    }
    assert classification["n_performance"].gt(0).all()


def test_stability_performance_small_sample_uses_n_performance_boundary():
    events = _performance_events()
    base_pair = events[
        (events["engine"] == ENGINE_OPTIMIZER)
        & (events["ID_CONFIGURATION"] == 1002)
    ]
    replicated: list[pd.DataFrame] = []
    for index in range(10):
        pair = base_pair.copy()
        pair["ID_CLIENT"] = 99000 + index
        pair["source_series_key"] = pair["source_series_key"].map(
            lambda key, i=index: (key[0], key[1], 99000 + i, key[3], key[4])
        )
        replicated.append(pair)
    ten_pairs = pd.concat(replicated, ignore_index=True)

    nine = build_portfolio_stability_analysis(
        ten_pairs[ten_pairs["ID_CLIENT"] < 99009]
    ).performance_by_stability
    ten = build_portfolio_stability_analysis(ten_pairs).performance_by_stability
    nine_row = _performance_row(
        nine,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        STABILITY_STATE_CHANGED,
    )
    ten_row = _performance_row(
        ten,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        STABILITY_STATE_CHANGED,
    )

    assert nine_row["n_performance"] == 9
    assert bool(nine_row["small_sample"]) is True
    assert ten_row["n_performance"] == 10
    assert bool(ten_row["small_sample"]) is False


def test_global_recalculates_stability_from_pairs_instead_of_averaging_client_rates():
    df_a = _portfolio_dataframe(97001)
    df_a["ML_BEST_MODEL_OLDER_3M"] = ["A", "B", "C"]
    df_a["ML_BEST_MODEL_RECENT_3M"] = ["A", "B", "C"]
    df_b = _portfolio_dataframe(97002)
    df_b["ML_BEST_MODEL_OLDER_3M"] = ["A", "B", None]
    df_b["ML_BEST_MODEL_RECENT_3M"] = ["A", "C", "DestinationOnly"]
    client_a = _client_result(df_a, 97001)
    client_b = _client_result(df_b, 97002)
    global_result = analyze_global([client_a, client_b])

    rate_a = _summary_row(
        client_a.portfolio.stability.model_summary,
        ENGINE_OPTIMIZER,
    )["stability_rate"]
    rate_b = _summary_row(
        client_b.portfolio.stability.model_summary,
        ENGINE_OPTIMIZER,
    )["stability_rate"]
    global_row = _summary_row(
        global_result.portfolio.stability.model_summary,
        ENGINE_OPTIMIZER,
    )
    assert rate_a == 1.0
    assert rate_b == 0.5
    assert global_row["n_evaluable"] == 5
    assert global_row["stable_count"] == 4
    assert global_row["changed_count"] == 1
    assert global_row["not_evaluable_count"] == 1
    assert global_row["stability_rate"] == 0.8
    assert global_row["stability_rate"] != pytest.approx((rate_a + rate_b) / 2)

    global_stable = _performance_row(
        global_result.portfolio.stability.performance_by_stability,
        STABILITY_TYPE_MODEL,
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        STABILITY_STATE_STABLE,
    )
    assert global_stable["n_clients"] == 2


def test_unavailable_portfolio_has_no_partial_stability_and_prior_tables_remain_integrated():
    historical = _client_result(build_synthetic_client_dataframe(), 98001)
    available = _client_result(_state_dataframe(98002), 98002)

    assert historical.portfolio.availability.available is False
    assert historical.portfolio.stability is None
    combined = analyze_global([available, historical]).portfolio
    assert combined.availability.available is False
    assert combined.stability is None

    assert available.portfolio.model_tables is not None
    assert available.portfolio.optimizer is not None
    assert not available.portfolio.model_tables.by_engine_block_model.empty
    assert not available.portfolio.optimizer.family_tables.empty


def test_stability_result_has_no_family_dimension_or_six_month_model_field():
    stability = _client_result(_state_dataframe()).portfolio.stability
    tables = [
        stability.model_summary,
        stability.model_by_older_model,
        stability.model_transitions,
        stability.classification_summary,
        stability.classification_transitions,
        stability.performance_by_stability,
    ]

    assert set(vars(stability)) == {
        "model_summary",
        "model_by_older_model",
        "model_transitions",
        "classification_summary",
        "classification_transitions",
        "performance_by_stability",
    }
    assert all("family" not in column.lower() for table in tables for column in table.columns)
    assert all("6m" not in column.lower() for table in tables for column in table.columns)
