"""Phase 10B.6: cross-cutting invariants for the complete portfolio contract."""

from __future__ import annotations

import pandas as pd
import pytest

from src.global_analysis import analyze_global
from src.periods import period_columns
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    FAMILY_MAPPING_NOT_EVALUABLE,
    FAMILY_UNMAPPED,
    PORTFOLIO_REQUIRED_COLUMNS,
    build_portfolio_analysis,
)
from tests.test_portfolio import _client_result, _portfolio_dataframe


def _table_row(table: pd.DataFrame, **values) -> pd.Series:
    selected = table
    for column, value in values.items():
        selected = selected[selected[column] == value]
    assert len(selected) == 1
    return selected.iloc[0]


def _set_block_metrics(
    df: pd.DataFrame,
    block: str,
    *,
    history: list[float],
    scp_abs_error: list[float],
    optimizer_abs_error: list[float],
    scp_signed_error: list[float],
    optimizer_signed_error: list[float],
    winner_method: list[str],
) -> None:
    pcols = period_columns(block)
    index = df.index[:len(history)]
    df.loc[index, pcols.total_history] = history
    df.loc[index, pcols.scp_total_abs_error] = scp_abs_error
    df.loc[index, pcols.ml_total_abs_error] = optimizer_abs_error
    df.loc[index, pcols.scp_total_signed_error] = scp_signed_error
    df.loc[index, pcols.ml_total_signed_error] = optimizer_signed_error
    df.loc[index, pcols.scp_wape] = [error / volume for error, volume in zip(scp_abs_error, history)]
    df.loc[index, pcols.ml_wape] = [
        error / volume for error, volume in zip(optimizer_abs_error, history)
    ]
    df.loc[index, pcols.scp_bias] = [
        error / volume for error, volume in zip(scp_signed_error, history)
    ]
    df.loc[index, pcols.ml_bias] = [
        error / volume for error, volume in zip(optimizer_signed_error, history)
    ]
    df.loc[index, pcols.winner_method] = winner_method


def test_each_missing_required_column_makes_the_entire_portfolio_unavailable():
    for missing_column in PORTFOLIO_REQUIRED_COLUMNS:
        result = _client_result(_portfolio_dataframe().drop(columns=[missing_column]))

        assert result.file_valid is True
        assert result.periods["6M"].n_comparable == 2
        assert result.portfolio.availability.available is False
        assert result.portfolio.availability.missing_required_columns == (missing_column,)
        assert result.portfolio.events is None
        assert result.portfolio.coverage is None
        assert result.portfolio.model_tables is None
        assert result.portfolio.optimizer is None
        assert result.portfolio.stability is None


def test_canonical_identity_uses_every_source_series_key_component():
    base = _portfolio_dataframe().iloc[[0]].copy()
    rows = [base.copy() for _ in range(6)]
    rows[1]["ID_BATCH"] = 2
    rows[2]["ID_RUN_STAGING"] = 11
    rows[3]["ID_CLIENT"] = 100000
    rows[4]["SOURCE_RUN_ID"] = 101
    rows[5]["ID_CONFIGURATION"] = 2001
    source = pd.concat(rows, ignore_index=True)
    candidate_mask = pd.Series(True, index=source.index)
    block_masks = {
        BLOCK_OLDER_3M: pd.Series(True, index=source.index),
        BLOCK_RECENT_3M: pd.Series(True, index=source.index),
    }

    portfolio = build_portfolio_analysis(source, candidate_mask, block_masks)
    events = portfolio.events.dataframe

    assert portfolio.availability.available is True
    assert len(events) == 4 * len(source) == 24
    assert events["source_series_key"].nunique() == 6
    assert not events.duplicated(
        subset=["source_series_key", "engine", "block"]
    ).any()
    assert events.groupby("source_series_key", observed=True).size().eq(4).all()


def test_older_and_recent_metadata_and_metrics_are_fully_isolated():
    df = _portfolio_dataframe()
    df["ML_BEST_MODEL_OLDER_3M"] = "OlderModel"
    df["ML_BEST_MODEL_RECENT_3M"] = "RecentModel"
    df["ML_CLASSIFICATION_OLDER_3M"] = "OlderClass"
    df["ML_CLASSIFICATION_RECENT_3M"] = "RecentClass"
    _set_block_metrics(
        df,
        BLOCK_OLDER_3M,
        history=[100.0, 900.0],
        scp_abs_error=[20.0, 90.0],
        optimizer_abs_error=[10.0, 180.0],
        scp_signed_error=[20.0, -90.0],
        optimizer_signed_error=[10.0, 180.0],
        winner_method=["SCP", "TIE"],
    )
    _set_block_metrics(
        df,
        BLOCK_RECENT_3M,
        history=[400.0, 600.0],
        scp_abs_error=[40.0, 180.0],
        optimizer_abs_error=[80.0, 60.0],
        scp_signed_error=[40.0, 180.0],
        optimizer_signed_error=[-80.0, 60.0],
        winner_method=["ML", "SCP"],
    )
    result = _client_result(df)
    model_table = result.portfolio.model_tables.by_engine_block_model
    older = _table_row(
        model_table,
        engine=ENGINE_OPTIMIZER,
        block=BLOCK_OLDER_3M,
        model_name="OlderModel",
    )
    recent = _table_row(
        model_table,
        engine=ENGINE_OPTIMIZER,
        block=BLOCK_RECENT_3M,
        model_name="RecentModel",
    )

    assert older["historical_volume"] == 1000.0
    assert older["scp_wape"] == pytest.approx(0.11)
    assert older["optimizer_wape"] == pytest.approx(0.19)
    assert older["scp_bias"] == pytest.approx(-0.07)
    assert older["optimizer_bias"] == pytest.approx(0.19)
    assert older["selected_engine_win_count"] == 0
    assert older["tie_count"] == 1

    assert recent["historical_volume"] == 1000.0
    assert recent["scp_wape"] == pytest.approx(0.22)
    assert recent["optimizer_wape"] == pytest.approx(0.14)
    assert recent["scp_bias"] == pytest.approx(0.22)
    assert recent["optimizer_bias"] == pytest.approx(-0.02)
    assert recent["selected_engine_win_count"] == 1
    assert recent["tie_count"] == 0

    events = result.portfolio.events.dataframe
    older_events = events[
        (events["engine"] == ENGINE_OPTIMIZER)
        & (events["block"] == BLOCK_OLDER_3M)
    ]
    recent_events = events[
        (events["engine"] == ENGINE_OPTIMIZER)
        & (events["block"] == BLOCK_RECENT_3M)
    ]
    assert set(older_events["optimizer_classification"]) == {"OlderClass"}
    assert set(recent_events["optimizer_classification"]) == {"RecentClass"}


def test_pair_assignable_crosses_use_only_complete_pairs_and_keep_unmapped():
    df = _portfolio_dataframe()
    extra = df.iloc[[0]].copy()
    extra["ID_CONFIGURATION"] = 1004
    df = pd.concat([df, extra], ignore_index=True)
    df["ML_BEST_MODEL_OLDER_3M"] = ["AutoETS", "Chronos", None, "Naive"]
    df["ML_CLASSIFICATION_OLDER_3M"] = ["known", "known", "known", None]
    result = _client_result(df)
    optimizer = result.portfolio.optimizer
    coverage = _table_row(
        optimizer.classification_coverage.by_block,
        block=BLOCK_OLDER_3M,
    )
    model_cross = optimizer.classification_model_tables.query(
        "block == @BLOCK_OLDER_3M"
    )
    family_cross = optimizer.classification_family_tables.query(
        "block == @BLOCK_OLDER_3M"
    )

    assert coverage["n_optimizer_events"] == 4
    assert coverage["n_model_present"] == 3
    assert coverage["n_classification_present"] == 3
    assert coverage["n_pair_assignable"] == 2
    assert model_cross["selection_assignable_count"].eq(2).all()
    assert model_cross["selection_count"].sum() == 2
    assert model_cross["selection_share_of_assignable"].sum() == pytest.approx(1.0)
    assert set(model_cross["model_name"]) == {"AutoETS", "Chronos"}
    assert family_cross["selection_assignable_count"].eq(2).all()
    assert family_cross["selection_count"].sum() == 2
    assert family_cross["selection_share_of_assignable"].sum() == pytest.approx(1.0)
    assert set(family_cross["family"]) == {"classical", FAMILY_UNMAPPED}

    general_family = optimizer.family_tables.query("block == @BLOCK_OLDER_3M")
    assert general_family["selection_count"].sum() == 3
    chronos = _table_row(
        result.portfolio.model_tables.by_engine_block_model,
        engine=ENGINE_OPTIMIZER,
        block=BLOCK_OLDER_3M,
        model_name="Chronos",
    )
    assert chronos["selection_count"] == 1
    assert chronos["n_performance"] == 1
    null_event = result.portfolio.events.dataframe.query(
        "engine == @ENGINE_OPTIMIZER and block == @BLOCK_OLDER_3M "
        "and ID_CONFIGURATION == 1003"
    ).iloc[0]
    assert pd.isna(null_event["family"])
    assert null_event["family_mapping_status"] == FAMILY_MAPPING_NOT_EVALUABLE


def test_older_model_cohort_is_not_inflated_by_incoming_transition():
    df = _portfolio_dataframe()
    extras = []
    for configuration in (1004, 1005):
        row = df.iloc[[0]].copy()
        row["ID_CONFIGURATION"] = configuration
        extras.append(row)
    df = pd.concat([df, *extras], ignore_index=True)
    df["ML_BEST_MODEL_OLDER_3M"] = ["A", "A", "A", "D", "E"]
    df["ML_BEST_MODEL_RECENT_3M"] = ["A", "B", "C", "D", "A"]
    stability = _client_result(df).portfolio.stability
    cohort_a = _table_row(
        stability.model_by_older_model,
        engine=ENGINE_OPTIMIZER,
        model_name="A",
    )

    assert cohort_a["n_evaluable"] == 3
    assert cohort_a["stable_count"] == 1
    assert cohort_a["changed_count"] == 2
    assert cohort_a["stability_rate"] == pytest.approx(1 / 3)
    assert _table_row(
        stability.model_by_older_model,
        engine=ENGINE_OPTIMIZER,
        model_name="E",
    )["changed_count"] == 1
    transitions = stability.model_transitions.query("engine == @ENGINE_OPTIMIZER")
    assert ((transitions["older_value"] == "E") & (transitions["recent_value"] == "A")).any()
    assert transitions["transition_count"].sum() == 5
    assert transitions["transition_share_of_evaluable"].sum() == pytest.approx(1.0)


def test_cross_result_cardinality_and_denominator_invariants_hold_together():
    df = _portfolio_dataframe()
    df.loc[2, "ML_BEST_MODEL_OLDER_3M"] = None
    df.loc[1, "ML_CLASSIFICATION_RECENT_3M"] = None
    result = _client_result(df)
    portfolio = result.portfolio
    events = portfolio.events.dataframe

    assert len(events) == 4 * len(df)
    for coverage in portfolio.coverage.by_engine_block.itertuples(index=False):
        event_scope = events[
            (events["engine"] == coverage.engine)
            & (events["block"] == coverage.block)
        ]
        model_scope = portfolio.model_tables.by_engine_block_model[
            (portfolio.model_tables.by_engine_block_model["engine"] == coverage.engine)
            & (portfolio.model_tables.by_engine_block_model["block"] == coverage.block)
        ]
        assert coverage.n_model_present + coverage.n_model_missing == coverage.n_structural_events
        assert coverage.n_performance_evaluable <= coverage.n_model_present
        assert coverage.n_model_present <= coverage.n_structural_events
        assert coverage.n_structural_events == len(event_scope)
        assert model_scope["selection_count"].sum() == coverage.n_model_present
        if coverage.n_model_present:
            assert model_scope["selection_share_of_assignable"].sum() == pytest.approx(1.0)

    optimizer_coverage = portfolio.coverage.by_engine_block.query(
        "engine == @ENGINE_OPTIMIZER"
    )
    for coverage in optimizer_coverage.itertuples(index=False):
        family_scope = portfolio.optimizer.family_tables.query("block == @coverage.block")
        assert family_scope["selection_count"].sum() == coverage.n_model_present
        if coverage.n_model_present:
            assert family_scope["selection_share_of_assignable"].sum() == pytest.approx(1.0)

    for summary in portfolio.stability.model_summary.itertuples(index=False):
        pair_count = events.loc[
            events["engine"] == summary.engine,
            "source_series_key",
        ].nunique()
        transitions = portfolio.stability.model_transitions.query(
            "engine == @summary.engine"
        )
        assert summary.stable_count + summary.changed_count + summary.not_evaluable_count == pair_count
        assert transitions["transition_count"].sum() == summary.stable_count + summary.changed_count
        if summary.n_evaluable:
            assert transitions["transition_share_of_evaluable"].sum() == pytest.approx(1.0)

    classification_summary = _table_row(
        portfolio.stability.classification_summary,
        engine=ENGINE_OPTIMIZER,
    )
    classification_transitions = portfolio.stability.classification_transitions
    assert (
        classification_summary["stable_count"]
        + classification_summary["changed_count"]
        + classification_summary["not_evaluable_count"]
        == df.shape[0]
    )
    assert classification_transitions["transition_count"].sum() == (
        classification_summary["stable_count"] + classification_summary["changed_count"]
    )


def test_global_portfolio_recalculates_weighted_metrics_counts_and_rates_from_events():
    client_a_df = _portfolio_dataframe(97001).iloc[[0]].copy()
    client_b_df = _portfolio_dataframe(97002).iloc[:2].copy()
    client_a_df["ML_BEST_MODEL_OLDER_3M"] = ["Naive"]
    client_a_df["ML_BEST_MODEL_RECENT_3M"] = ["Naive"]
    client_b_df["ML_BEST_MODEL_OLDER_3M"] = ["Naive", "AutoETS"]
    client_b_df["ML_BEST_MODEL_RECENT_3M"] = ["AutoARIMA", "AutoARIMA"]
    _set_block_metrics(
        client_a_df,
        BLOCK_OLDER_3M,
        history=[100.0],
        scp_abs_error=[50.0],
        optimizer_abs_error=[25.0],
        scp_signed_error=[50.0],
        optimizer_signed_error=[25.0],
        winner_method=["ML"],
    )
    _set_block_metrics(
        client_b_df,
        BLOCK_OLDER_3M,
        history=[1000.0, 1000.0],
        scp_abs_error=[100.0, 100.0],
        optimizer_abs_error=[200.0, 200.0],
        scp_signed_error=[-100.0, -100.0],
        optimizer_signed_error=[200.0, 200.0],
        winner_method=["SCP", "SCP"],
    )
    client_a = _client_result(client_a_df, 97001)
    client_b = _client_result(client_b_df, 97002)
    global_result = analyze_global([client_a, client_b])
    global_model = global_result.portfolio.model_tables.by_engine_block_model
    global_naive = _table_row(
        global_model,
        engine=ENGINE_OPTIMIZER,
        block=BLOCK_OLDER_3M,
        model_name="Naive",
    )

    assert global_naive["selection_count"] == 2
    assert global_naive["selection_assignable_count"] == 3
    assert global_naive["selection_share_of_assignable"] == pytest.approx(2 / 3)
    assert global_naive["n_performance"] == 2
    assert global_naive["n_clients"] == 2
    assert global_naive["scp_wape"] == pytest.approx((50 + 100) / (100 + 1000))
    assert global_naive["optimizer_wape"] == pytest.approx((25 + 200) / (100 + 1000))
    assert global_naive["scp_bias"] == pytest.approx((50 - 100) / (100 + 1000))
    assert global_naive["scp_wape"] != pytest.approx((0.5 + 0.1) / 2)
    assert global_naive["scp_bias"] != pytest.approx((0.5 - 0.1) / 2)

    global_family = _table_row(
        global_result.portfolio.optimizer.family_tables,
        block=BLOCK_OLDER_3M,
        family="baselines",
    )
    assert global_family["selection_count"] == 2
    assert global_family["selection_share_of_assignable"] == pytest.approx(2 / 3)
    assert global_family["scp_wape"] == global_naive["scp_wape"]

    client_rate_a = _table_row(
        client_a.portfolio.stability.model_summary,
        engine=ENGINE_OPTIMIZER,
    )["stability_rate"]
    client_rate_b = _table_row(
        client_b.portfolio.stability.model_summary,
        engine=ENGINE_OPTIMIZER,
    )["stability_rate"]
    global_summary = _table_row(
        global_result.portfolio.stability.model_summary,
        engine=ENGINE_OPTIMIZER,
    )
    assert client_rate_a == 1.0
    assert client_rate_b == 0.0
    assert global_summary["stability_rate"] == pytest.approx(1 / 3)
    assert global_summary["stability_rate"] != pytest.approx(
        (client_rate_a + client_rate_b) / 2
    )
    transitions = global_result.portfolio.stability.model_transitions.query(
        "engine == @ENGINE_OPTIMIZER"
    )
    assert transitions["transition_count"].sum() == 3
    assert transitions["transition_share_of_evaluable"].sum() == pytest.approx(1.0)
    assert transitions["transition_share_of_evaluable"].tolist() == pytest.approx([1 / 3] * 3)
