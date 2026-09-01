"""Phase 10B.4: Optimizer families and block-specific classification views."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.global_analysis import analyze_global
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    CLASSIFICATION_FAMILY_TABLE_COLUMNS,
    CLASSIFICATION_MODEL_TABLE_COLUMNS,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    FAMILY_MAPPING_MAPPED,
    FAMILY_MAPPING_NOT_APPLICABLE,
    FAMILY_MAPPING_NOT_EVALUABLE,
    FAMILY_MAPPING_UNMAPPED,
    FAMILY_TABLE_COLUMNS,
    FAMILY_UNMAPPED,
    OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
    OPTIMIZER_MODEL_FAMILY,
    optimizer_family_enrichment,
)
from tests.factories import build_synthetic_client_dataframe
from tests.test_portfolio import _client_result, _event, _portfolio_dataframe


def _optimizer_dataframe(id_client: int = 99999) -> pd.DataFrame:
    df = _portfolio_dataframe(id_client)
    df["ML_BEST_MODEL_OLDER_3M"] = ["AutoETS", "Prophet", "Chronos"]
    df["ML_CLASSIFICATION_OLDER_3M"] = ["smooth_acceptable", "erratic_acceptable", None]
    df["ML_BEST_MODEL_RECENT_3M"] = ["AutoETS", "FutureModel", "LGBMRegressor"]
    df["ML_CLASSIFICATION_RECENT_3M"] = [
        "smooth_acceptable",
        "erratic_acceptable",
        "erratic_acceptable",
    ]
    return df


def _family_row(table: pd.DataFrame, block: str, family: str) -> pd.Series:
    selected = table[(table["block"] == block) & (table["family"] == family)]
    assert len(selected) == 1
    return selected.iloc[0]


@pytest.mark.parametrize(
    ("model_name", "family"),
    [
        ("Naive", "baselines"),
        ("AutoETS", "classical"),
        ("CrostonSBA", "intermittent"),
        ("LGBMRegressor", "ml"),
    ],
)
def test_registry_derived_mapping_covers_each_explicit_nonempty_family(model_name, family):
    outcome = optimizer_family_enrichment(model_name)

    assert outcome.family == family
    assert outcome.family_mapping_status == FAMILY_MAPPING_MAPPED


def test_mapping_is_explicit_and_chronos_or_unknown_models_are_unmapped():
    assert "Chronos" not in OPTIMIZER_MODEL_FAMILY
    assert set(OPTIMIZER_MODEL_FAMILY.values()) == {
        "baselines", "classical", "intermittent", "ml",
    }

    chronos = optimizer_family_enrichment("Chronos")
    unknown = optimizer_family_enrichment("FutureModel")
    assert chronos.family == unknown.family == FAMILY_UNMAPPED
    assert chronos.family_mapping_status == unknown.family_mapping_status == FAMILY_MAPPING_UNMAPPED


def test_null_model_is_not_evaluable_and_never_becomes_unmapped():
    outcome = optimizer_family_enrichment(None)

    assert outcome.family is None
    assert outcome.family_mapping_status == FAMILY_MAPPING_NOT_EVALUABLE


def test_canonical_events_enrich_optimizer_only_and_preserve_unknown_model_name():
    result = _client_result(_optimizer_dataframe())
    optimizer_unknown = _event(result, ENGINE_OPTIMIZER, BLOCK_RECENT_3M, 1002)
    scp_event = _event(result, ENGINE_SCP_AUTO, BLOCK_RECENT_3M, 1002)

    assert optimizer_unknown["model_name"] == "FutureModel"
    assert optimizer_unknown["family"] == FAMILY_UNMAPPED
    assert optimizer_unknown["family_mapping_status"] == FAMILY_MAPPING_UNMAPPED
    assert pd.isna(scp_event["family"])
    assert scp_event["family_mapping_status"] == FAMILY_MAPPING_NOT_APPLICABLE


def test_family_table_uses_model_assignable_denominator_and_conditioned_math():
    result = _client_result(_optimizer_dataframe())
    table = result.portfolio.optimizer.family_tables
    older_classical = _family_row(table, BLOCK_OLDER_3M, "classical")
    older_unmapped = _family_row(table, BLOCK_OLDER_3M, FAMILY_UNMAPPED)

    assert tuple(table.columns) == FAMILY_TABLE_COLUMNS
    assert older_classical["selection_count"] == 2
    assert older_unmapped["selection_count"] == 1
    assert older_classical["selection_assignable_count"] == 3
    assert older_classical["selection_share_of_assignable"] == pytest.approx(2 / 3)
    assert older_unmapped["selection_share_of_assignable"] == pytest.approx(1 / 3)
    assert table.groupby("block", observed=True)["selection_share_of_assignable"].sum().eq(1.0).all()

    # The third selection has no evaluable block performance; it remains in
    # selection but not in the ratio-of-sums performance population.
    assert older_classical["n_performance"] == 2
    assert older_unmapped["n_performance"] == 0
    assert older_classical["historical_volume"] == 600.0
    assert older_classical["volume_share"] == 1.0
    assert older_classical["scp_wape"] == pytest.approx((60 + 30) / 600)
    assert older_classical["optimizer_wape"] == pytest.approx((30 + 90) / 600)
    assert older_classical["scp_bias"] == pytest.approx((60 + 30) / 600)
    assert older_classical["optimizer_bias"] == pytest.approx((30 + 90) / 600)
    assert older_classical["selected_engine_win_count"] == 1
    assert older_classical["tie_count"] == 0
    assert older_classical["selected_engine_win_rate"] == 0.5
    assert older_classical["optimizer_improvement_vs_scp"] == pytest.approx(-100 / 3)
    assert older_classical["optimizer_median_improvement_vs_scp"] == pytest.approx(-75.0)
    assert older_classical["optimizer_abs_error_reduction_vs_scp"] == -30.0
    assert bool(older_classical["small_sample"]) is True
    assert math.isnan(older_unmapped["scp_wape"])

    recent_unmapped = _family_row(table, BLOCK_RECENT_3M, FAMILY_UNMAPPED)
    assert recent_unmapped["selection_count"] == 1
    assert recent_unmapped["n_performance"] == 1


def test_classification_coverage_and_pair_assignable_denominators_are_explicit():
    result = _client_result(_optimizer_dataframe())
    optimizer = result.portfolio.optimizer
    coverage = optimizer.classification_coverage.by_block
    older = coverage[coverage["block"] == BLOCK_OLDER_3M].iloc[0]
    recent = coverage[coverage["block"] == BLOCK_RECENT_3M].iloc[0]

    assert tuple(coverage.columns) == OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS
    assert older["n_optimizer_events"] == 3
    assert older["n_model_present"] == 3
    assert older["n_model_missing"] == 0
    assert older["n_classification_present"] == 2
    assert older["n_classification_missing"] == 1
    assert older["classification_assignment_rate"] == pytest.approx(2 / 3)
    assert older["n_pair_assignable"] == 2
    assert older["pair_assignment_rate"] == pytest.approx(2 / 3)
    assert recent["n_pair_assignable"] == 3

    model_cross = optimizer.classification_model_tables
    family_cross = optimizer.classification_family_tables
    assert tuple(model_cross.columns) == CLASSIFICATION_MODEL_TABLE_COLUMNS
    assert tuple(family_cross.columns) == CLASSIFICATION_FAMILY_TABLE_COLUMNS
    assert "Chronos" not in set(model_cross["model_name"])
    assert set(model_cross.loc[model_cross["block"] == BLOCK_OLDER_3M, "model_name"]) == {
        "AutoETS", "Prophet",
    }
    assert FAMILY_UNMAPPED in set(
        family_cross.loc[family_cross["block"] == BLOCK_RECENT_3M, "family"]
    )
    assert model_cross.groupby("block", observed=True)["selection_share_of_assignable"].sum().eq(1.0).all()
    assert family_cross.groupby("block", observed=True)["selection_share_of_assignable"].sum().eq(1.0).all()
    assert model_cross.groupby("block", observed=True)["selection_assignable_count"].first().to_dict() == {
        BLOCK_OLDER_3M: 2,
        BLOCK_RECENT_3M: 3,
    }


def test_classification_missing_does_not_change_general_model_or_family_selection():
    result = _client_result(_optimizer_dataframe())
    model_table = result.portfolio.model_tables.by_engine_block_model
    family_table = result.portfolio.optimizer.family_tables

    chronos = model_table[
        (model_table["engine"] == ENGINE_OPTIMIZER)
        & (model_table["block"] == BLOCK_OLDER_3M)
        & (model_table["model_name"] == "Chronos")
    ]
    assert len(chronos) == 1
    assert _family_row(family_table, BLOCK_OLDER_3M, FAMILY_UNMAPPED)["selection_count"] == 1


def test_null_model_has_no_family_category_and_pair_requires_both_values():
    df = _optimizer_dataframe()
    df.loc[0, "ML_BEST_MODEL_OLDER_3M"] = None
    df.loc[0, "ML_CLASSIFICATION_OLDER_3M"] = "smooth_acceptable"
    result = _client_result(df)
    event = _event(result, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, 1001)
    optimizer = result.portfolio.optimizer
    older_coverage = optimizer.classification_coverage.by_block.query(
        "block == @BLOCK_OLDER_3M"
    ).iloc[0]

    assert pd.isna(event["family"])
    assert event["family_mapping_status"] == FAMILY_MAPPING_NOT_EVALUABLE
    assert optimizer.family_tables["family"].notna().all()
    assert optimizer.family_tables.query("block == @BLOCK_OLDER_3M")[
        "selection_assignable_count"
    ].eq(2).all()
    assert older_coverage["n_classification_present"] == 2
    assert older_coverage["n_pair_assignable"] == 1
    assert "smooth_acceptable" not in set(
        optimizer.classification_model_tables.query("block == @BLOCK_OLDER_3M")[
            "optimizer_classification"
        ]
    )


def test_only_block_specific_classification_is_used_and_blocks_remain_separate():
    df = _optimizer_dataframe()
    df["ML_CLASSIFICATION"] = "LegacyMustNotBeUsed"
    df["ML_TYPE"] = "LegacyTypeMustNotBeUsed"
    df["SERIES_CLASSIFICATION"] = "LegacySeriesMustNotBeUsed"
    df["SCP_CLASSIFICATION"] = "LegacyScpMustNotBeUsed"
    df["ML_CLASSIFICATION_OLDER_3M"] = None
    result = _client_result(df)
    optimizer = result.portfolio.optimizer

    assert optimizer.classification_model_tables.query("block == @BLOCK_OLDER_3M").empty
    assert optimizer.classification_family_tables.query("block == @BLOCK_OLDER_3M").empty
    assert not optimizer.classification_model_tables.query("block == @BLOCK_RECENT_3M").empty
    observed = set(optimizer.classification_model_tables["optimizer_classification"])
    assert not observed.intersection({
        "LegacyMustNotBeUsed", "LegacyTypeMustNotBeUsed",
        "LegacySeriesMustNotBeUsed", "LegacyScpMustNotBeUsed",
    })
    # General 10B.3/10B.4 selection remains available despite missing classification.
    assert len(result.portfolio.model_tables.by_engine_block_model.query(
        "engine == @ENGINE_OPTIMIZER and block == @BLOCK_OLDER_3M"
    )) == 3
    assert not optimizer.family_tables.query("block == @BLOCK_OLDER_3M").empty


def test_optimizer_results_are_client_global_coherent_and_global_counts_clients_from_events():
    client_a = _client_result(_optimizer_dataframe(97001), 97001)
    client_b = _client_result(_optimizer_dataframe(97002), 97002)
    global_result = analyze_global([client_a, client_b])

    client_classical = _family_row(
        client_a.portfolio.optimizer.family_tables,
        BLOCK_OLDER_3M,
        "classical",
    )
    global_classical = _family_row(
        global_result.portfolio.optimizer.family_tables,
        BLOCK_OLDER_3M,
        "classical",
    )
    assert global_classical["selection_count"] == 2 * client_classical["selection_count"]
    assert global_classical["n_performance"] == 2 * client_classical["n_performance"]
    assert global_classical["n_clients"] == 2
    assert global_classical["scp_wape"] == client_classical["scp_wape"]
    assert global_classical["optimizer_wape"] == client_classical["optimizer_wape"]

    ordered_model = global_result.portfolio.optimizer.classification_model_tables[
        ["block", "optimizer_classification", "model_name"]
    ]
    assert list(ordered_model.itertuples(index=False, name=None)) == sorted(
        ordered_model.itertuples(index=False, name=None),
        key=lambda row: (
            0 if row[0] == BLOCK_OLDER_3M else 1,
            row[1],
            row[2],
        ),
    )


def test_unavailable_portfolio_has_no_partial_optimizer_result_client_or_global():
    historical = _client_result(build_synthetic_client_dataframe(), 98001)
    available = _client_result(_optimizer_dataframe(98002), 98002)

    assert historical.portfolio.availability.available is False
    assert historical.portfolio.optimizer is None
    combined = analyze_global([available, historical]).portfolio
    assert combined.availability.available is False
    assert combined.model_tables is None
    assert combined.optimizer is None
