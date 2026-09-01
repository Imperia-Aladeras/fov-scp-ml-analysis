"""Phase 10B.2: availability, canonical block events and coverage."""

from __future__ import annotations

import pandas as pd
import pytest

from src.client_analysis import analyze_client, period_comparable_mask
from src.global_analysis import analyze_global
from src.periods import period_columns
from src.portfolio import (
    AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING,
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    CLASSIFICATION_MISSING,
    CLASSIFICATION_NOT_APPLICABLE,
    CLASSIFICATION_PRESENT,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    EVENT_KEY_COLUMNS,
    MODEL_METADATA_MISSING,
    MODEL_METADATA_PRESENT,
    PORTFOLIO_REQUIRED_COLUMNS,
    PortfolioContractError,
    build_portfolio_analysis,
)
from tests.factories import build_synthetic_client_dataframe, make_client_source


def _portfolio_dataframe(id_client: int = 99999) -> pd.DataFrame:
    df = build_synthetic_client_dataframe()
    df["ID_BATCH"] = 1
    df["ID_RUN_STAGING"] = 10
    df["ID_CLIENT"] = id_client
    df["SOURCE_RUN_ID"] = 100
    df["RUN_START_DATE"] = pd.Timestamp("2026-01-01")
    df["SCP_MODEL_OLDER_3M"] = ["Average", "X11_Seasonal", "SeasonalDiscrete"]
    df["SCP_MODEL_RECENT_3M"] = ["ExponentialSmoothing", "X11_Seasonal", "SeasonalDiscrete"]
    df["ML_BEST_MODEL_OLDER_3M"] = ["AutoETS", "AutoARIMA", "Naive"]
    df["ML_BEST_MODEL_RECENT_3M"] = ["AutoTheta", "AutoARIMA", "Naive"]
    df["ML_CLASSIFICATION_OLDER_3M"] = ["smooth_acceptable", "erratic_acceptable", "lumpy_ultraSparse"]
    df["ML_CLASSIFICATION_RECENT_3M"] = ["smooth_acceptable", "erratic_acceptable", "lumpy_ultraSparse"]
    return df


def _client_result(df: pd.DataFrame, id_client: int = 99999):
    return analyze_client(make_client_source(df, id_client, "Portfolio"))


def _event(result, engine: str, block: str, id_configuration: int):
    events = result.portfolio.events.dataframe
    rows = events[
        (events["engine"] == engine)
        & (events["block"] == block)
        & (events["ID_CONFIGURATION"] == id_configuration)
    ]
    assert len(rows) == 1
    return rows.iloc[0]


def test_complete_contract_builds_four_unique_structural_events_per_source_row():
    result = _client_result(_portfolio_dataframe())

    assert result.portfolio.availability.available is True
    assert result.portfolio.availability.reason is None
    assert result.portfolio.availability.missing_required_columns == ()

    events = result.portfolio.events.dataframe
    assert len(events) == 12
    assert not events.duplicated(subset=list(EVENT_KEY_COLUMNS)).any()
    assert set(events["engine"]) == {ENGINE_SCP_AUTO, ENGINE_OPTIMIZER}
    assert set(events["block"]) == {BLOCK_OLDER_3M, BLOCK_RECENT_3M}
    assert events.groupby("source_series_key").size().eq(4).all()
    assert events.iloc[0]["source_series_key"] == (1, 10, 99999, 100, 1001)
    assert events["RUN_START_DATE"].eq(pd.Timestamp("2026-01-01")).all()


def test_historical_and_partially_upgraded_inputs_are_unavailable_without_breaking_existing_analytics():
    historical = build_synthetic_client_dataframe()
    historical_result = _client_result(historical)

    assert historical_result.file_valid is True
    assert historical_result.periods["6M"].n_comparable == 2
    assert historical_result.portfolio.availability.available is False
    assert historical_result.portfolio.availability.reason == AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING
    assert historical_result.portfolio.availability.missing_required_columns == PORTFOLIO_REQUIRED_COLUMNS
    assert historical_result.portfolio.events is None
    assert historical_result.portfolio.coverage is None

    partial = _portfolio_dataframe().drop(columns=["ML_CLASSIFICATION_RECENT_3M"])
    partial_result = _client_result(partial)
    assert partial_result.file_valid is True
    assert partial_result.portfolio.availability.available is False
    assert partial_result.portfolio.availability.missing_required_columns == ("ML_CLASSIFICATION_RECENT_3M",)
    assert partial_result.portfolio.events is None


def test_events_keep_block_and_engine_metadata_separate_and_classification_optimizer_only():
    df = _portfolio_dataframe()
    recent = period_columns(BLOCK_RECENT_3M)
    df.loc[0, recent.total_history] = 400.0
    df.loc[0, recent.scp_total_abs_error] = 160.0
    df.loc[0, recent.ml_total_abs_error] = 120.0
    df.loc[0, recent.scp_total_signed_error] = 160.0
    df.loc[0, recent.ml_total_signed_error] = 120.0
    df.loc[0, recent.scp_wape] = 0.4
    df.loc[0, recent.ml_wape] = 0.3
    df.loc[0, recent.scp_bias] = 0.4
    df.loc[0, recent.ml_bias] = 0.3

    result = _client_result(df)
    scp_older = _event(result, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, 1001)
    scp_recent = _event(result, ENGINE_SCP_AUTO, BLOCK_RECENT_3M, 1001)
    optimizer_older = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1001)
    optimizer_recent = _event(result, ENGINE_OPTIMIZER, BLOCK_RECENT_3M, 1001)

    assert scp_older["model_name"] == "Average"
    assert scp_recent["model_name"] == "ExponentialSmoothing"
    assert optimizer_older["model_name"] == "AutoETS"
    assert optimizer_recent["model_name"] == "AutoTheta"
    assert pd.isna(scp_older["optimizer_classification"])
    assert scp_older["classification_metadata_status"] == CLASSIFICATION_NOT_APPLICABLE
    assert optimizer_older["optimizer_classification"] == "smooth_acceptable"
    assert optimizer_older["classification_metadata_status"] == CLASSIFICATION_PRESENT

    assert optimizer_older["total_history"] == 300.0
    assert optimizer_recent["total_history"] == 400.0
    assert optimizer_older["optimizer_abs_error_reduction_vs_scp"] == 30.0
    assert optimizer_recent["optimizer_abs_error_reduction_vs_scp"] == 40.0
    assert optimizer_older["optimizer_improvement_vs_scp"] == 50.0
    assert optimizer_recent["optimizer_improvement_vs_scp"] == pytest.approx(25.0)


def test_null_block_model_never_falls_back_to_legacy_metadata():
    df = _portfolio_dataframe()
    df.loc[0, "ML_BEST_MODEL_OLDER_3M"] = None
    df.loc[0, "ML_BEST_MODEL"] = "LegacyMustNotBeUsed"

    result = _client_result(df)
    event = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1001)

    assert pd.isna(event["model_name"])
    assert event["model_metadata_status"] == MODEL_METADATA_MISSING
    assert event["selection_evaluable"] == False
    assert event["block_metrics_evaluable"] == True
    assert event["performance_evaluable"] == False


def test_missing_optimizer_classification_does_not_change_model_evaluability():
    df = _portfolio_dataframe()
    df.loc[0, "ML_CLASSIFICATION_OLDER_3M"] = None

    result = _client_result(df)
    event = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1001)

    assert event["model_name"] == "AutoETS"
    assert event["model_metadata_status"] == MODEL_METADATA_PRESENT
    assert event["selection_evaluable"] == True
    assert event["performance_evaluable"] == True
    assert pd.isna(event["optimizer_classification"])
    assert event["classification_metadata_status"] == CLASSIFICATION_MISSING


def test_selection_and_performance_evaluability_are_independent():
    result = _client_result(_portfolio_dataframe())

    comparable = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1001)
    no_performance = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1003)

    assert comparable["model_metadata_status"] == MODEL_METADATA_PRESENT
    assert comparable["selection_evaluable"] == True
    assert comparable["block_metrics_evaluable"] == True
    assert comparable["performance_evaluable"] == True

    assert no_performance["model_metadata_status"] == MODEL_METADATA_PRESENT
    assert no_performance["selection_evaluable"] == True
    assert no_performance["block_metrics_evaluable"] == False
    assert no_performance["performance_evaluable"] == False


def test_coverage_is_available_even_when_every_model_is_missing():
    df = _portfolio_dataframe()
    for column in (
        "SCP_MODEL_OLDER_3M",
        "SCP_MODEL_RECENT_3M",
        "ML_BEST_MODEL_OLDER_3M",
        "ML_BEST_MODEL_RECENT_3M",
    ):
        df[column] = None

    result = _client_result(df)
    coverage = result.portfolio.coverage.by_engine_block

    assert result.portfolio.availability.available is True
    assert len(coverage) == 4
    assert coverage["n_base_series"].eq(3).all()
    assert coverage["n_structural_events"].eq(3).all()
    assert coverage["n_model_present"].eq(0).all()
    assert coverage["n_model_missing"].eq(3).all()
    assert coverage["selection_assignment_rate"].eq(0.0).all()
    assert coverage["n_performance_evaluable"].eq(0).all()
    assert result.portfolio.model_tables.by_engine_block_model.empty


def test_coverage_counts_selection_and_performance_by_engine_and_block():
    df = _portfolio_dataframe()
    df.loc[2, "ML_BEST_MODEL_OLDER_3M"] = None
    result = _client_result(df)
    coverage = result.portfolio.coverage.by_engine_block
    row = coverage[
        (coverage["engine"] == ENGINE_OPTIMIZER)
        & (coverage["block"] == BLOCK_OLDER_3M)
    ].iloc[0]

    assert row["n_base_series"] == 3
    assert row["n_structural_events"] == 3
    assert row["n_model_present"] == 2
    assert row["n_model_missing"] == 1
    assert row["selection_assignment_rate"] == pytest.approx(2 / 3)
    assert row["n_block_metrics_evaluable"] == 2
    assert row["n_performance_evaluable"] == 2


def test_duplicate_source_series_key_is_rejected_defensively():
    df = _portfolio_dataframe()
    df.loc[1, "ID_CONFIGURATION"] = df.loc[0, "ID_CONFIGURATION"]
    candidate_mask = df["HAS_BASE_CANDIDATE"] == 1
    masks = {
        block: period_comparable_mask(df, period_columns(block), candidate_mask)
        for block in (BLOCK_OLDER_3M, BLOCK_RECENT_3M)
    }

    with pytest.raises(PortfolioContractError, match="duplicate source_series_key"):
        build_portfolio_analysis(df, candidate_mask, masks)


def test_global_portfolio_combines_complete_clients_and_refuses_partial_coverage():
    df_a = _portfolio_dataframe(93001)
    df_b = _portfolio_dataframe(93002)
    result_a = _client_result(df_a, 93001)
    result_b = _client_result(df_b, 93002)

    global_result = analyze_global([result_a, result_b])
    assert global_result.portfolio.availability.available is True
    assert len(global_result.portfolio.events.dataframe) == 24
    assert global_result.portfolio.coverage.by_engine_block["n_base_series"].eq(6).all()

    historical_result = _client_result(build_synthetic_client_dataframe(), 94001)
    mixed_global = analyze_global([result_a, historical_result])
    assert mixed_global.portfolio.availability.available is False
    assert mixed_global.portfolio.availability.reason == AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING
    assert mixed_global.portfolio.events is None
    assert set(mixed_global.portfolio.availability.missing_required_columns) == set(PORTFOLIO_REQUIRED_COLUMNS)
