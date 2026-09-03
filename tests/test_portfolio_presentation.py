"""Phase 10C.1: pure presentation contract for Phase 10B portfolio results."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    CLASSIFICATION_FAMILY_TABLE_COLUMNS,
    CLASSIFICATION_MODEL_TABLE_COLUMNS,
    COVERAGE_COLUMNS,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    FAMILY_TABLE_COLUMNS,
    FAMILY_UNMAPPED,
    MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS,
    MODEL_TABLE_COLUMNS,
    OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
    PORTFOLIO_REQUIRED_COLUMNS,
    STABILITY_PERFORMANCE_COLUMNS,
    STABILITY_STATE_CHANGED,
    STABILITY_STATE_NOT_EVALUABLE,
    STABILITY_STATE_STABLE,
    STABILITY_SUMMARY_COLUMNS,
    TRANSITION_COLUMNS,
)
from src.portfolio_presentation import (
    BLOCK_LABELS,
    CANONICAL_EVENT_COLUMNS,
    COLUMN_PRESENTATIONS,
    ENGINE_LABELS,
    FAMILY_LABELS,
    PORTFOLIO_CONDITIONED_PERFORMANCE_NOTE,
    PORTFOLIO_SMALL_SAMPLE_NOTE,
    PORTFOLIO_TABLE_SCHEMAS,
    PORTFOLIO_UNAVAILABLE_NOTE,
    SCHEMA_CANONICAL_EVENTS,
    SCHEMA_CLASSIFICATION_COVERAGE,
    SCHEMA_CLASSIFICATION_FAMILY,
    SCHEMA_CLASSIFICATION_MODEL,
    SCHEMA_CLASSIFICATION_STABILITY,
    SCHEMA_CLASSIFICATION_TRANSITIONS,
    SCHEMA_COVERAGE,
    SCHEMA_FAMILIES,
    SCHEMA_MODEL_STABILITY_SUMMARY,
    SCHEMA_MODEL_TRANSITIONS,
    SCHEMA_MODELS,
    SCHEMA_PERFORMANCE_BY_STABILITY,
    SCHEMA_STABILITY_BY_OLDER_MODEL,
    PortfolioPresentationContractError,
    PortfolioPresentationState,
    PortfolioSampleState,
    PortfolioValueKind,
    block_label,
    family_label,
    format_portfolio_value,
    performance_sample_presentation,
    portfolio_presentation_availability,
    prepare_portfolio_presentation,
    prepare_portfolio_table,
    stability_state_label,
    visible_column_label,
)
from tests.factories import build_synthetic_client_dataframe
from tests.test_portfolio import _client_result, _portfolio_dataframe
from tests.test_portfolio_models import _conditioned_events
from tests.test_portfolio_optimizer import _optimizer_dataframe
from tests.test_portfolio_stability import _state_dataframe


def _available_portfolio():
    return _client_result(_state_dataframe()).portfolio


def _portfolio_source_tables(portfolio) -> dict[str, pd.DataFrame]:
    return {
        SCHEMA_COVERAGE: portfolio.coverage.by_engine_block,
        SCHEMA_MODELS: portfolio.model_tables.by_engine_block_model,
        SCHEMA_FAMILIES: portfolio.optimizer.family_tables,
        SCHEMA_CLASSIFICATION_COVERAGE: portfolio.optimizer.classification_coverage.by_block,
        SCHEMA_CLASSIFICATION_MODEL: portfolio.optimizer.classification_model_tables,
        SCHEMA_CLASSIFICATION_FAMILY: portfolio.optimizer.classification_family_tables,
        SCHEMA_MODEL_STABILITY_SUMMARY: portfolio.stability.model_summary,
        SCHEMA_STABILITY_BY_OLDER_MODEL: portfolio.stability.model_by_older_model,
        SCHEMA_MODEL_TRANSITIONS: portfolio.stability.model_transitions,
        SCHEMA_CLASSIFICATION_STABILITY: portfolio.stability.classification_summary,
        SCHEMA_CLASSIFICATION_TRANSITIONS: portfolio.stability.classification_transitions,
        SCHEMA_PERFORMANCE_BY_STABILITY: portfolio.stability.performance_by_stability,
        SCHEMA_CANONICAL_EVENTS: portfolio.events.dataframe,
    }


def test_engine_and_block_labels_use_the_approved_unambiguous_copy():
    assert ENGINE_LABELS == {
        ENGINE_SCP_AUTO: "SCP Classic Auto",
        ENGINE_OPTIMIZER: "SCP Classic Optimizer",
    }
    assert block_label(BLOCK_OLDER_3M) == "3 meses anteriores (M6–M4)"
    assert block_label(BLOCK_RECENT_3M) == "3 meses recientes (M3–M1)"

    all_block_copy = " ".join(BLOCK_LABELS.values()).lower()
    assert "primer trimestre del semestre" not in all_block_copy
    assert "segundo trimestre del semestre" not in all_block_copy
    assert "m6–m4" in all_block_copy
    assert "m3–m1" in all_block_copy


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("selection_assignment_rate", 0.5, "50,0 %"),
        ("selection_share_of_assignable", 0.5, "50,0 %"),
        ("volume_share", 0.5, "50,0 %"),
        ("selected_engine_win_rate", 0.5, "50,0 %"),
        ("classification_assignment_rate", 0.5, "50,0 %"),
        ("pair_assignment_rate", 0.5, "50,0 %"),
        ("stability_rate", 0.5, "50,0 %"),
        ("transition_share_of_evaluable", 0.5, "50,0 %"),
        ("scp_wape", 0.125, "12,5 %"),
        ("optimizer_wape", 0.25, "25,0 %"),
        ("scp_bias", 0.125, "+12,5 %"),
        ("optimizer_bias", -0.125, "-12,5 %"),
        ("optimizer_improvement_vs_scp", 25.0, "+25,0 %"),
        ("optimizer_improvement_vs_scp", -10.0, "-10,0 %"),
        ("optimizer_median_improvement_vs_scp", 25.0, "+25,0 %"),
        ("optimizer_abs_error_reduction_vs_scp", -80.0, "-80"),
        ("historical_volume", 1234.5, "1.234,5"),
        ("n_performance", 1234, "1.234"),
        ("selection_count", 10, "10"),
        ("scp_wape", float("nan"), "N/D"),
        ("optimizer_bias", float("inf"), "N/D"),
    ],
)
def test_explicit_portfolio_formats_preserve_scale_and_sign(column, value, expected):
    assert format_portfolio_value(column, value) == expected


def test_column_types_are_explicit_and_do_not_use_suffix_heuristics():
    assert COLUMN_PRESENTATIONS["selected_engine_win_rate"].value_kind == PortfolioValueKind.RATIO_PERCENT
    assert COLUMN_PRESENTATIONS["scp_wape"].value_kind == PortfolioValueKind.RATIO_PERCENT
    assert COLUMN_PRESENTATIONS["scp_bias"].value_kind == PortfolioValueKind.SIGNED_RATIO_PERCENT
    assert (
        COLUMN_PRESENTATIONS["optimizer_improvement_vs_scp"].value_kind
        == PortfolioValueKind.SIGNED_SCALED_PERCENT
    )
    assert (
        COLUMN_PRESENTATIONS["optimizer_abs_error_reduction_vs_scp"].value_kind
        == PortfolioValueKind.ABSOLUTE_NUMBER
    )
    assert COLUMN_PRESENTATIONS["n_performance"].value_kind == PortfolioValueKind.INTEGER


def test_fixed_optimizer_vs_auto_direction_and_analyzed_engine_win_rate_labels():
    fixed_columns = (
        "optimizer_improvement_vs_scp",
        "optimizer_median_improvement_vs_scp",
        "optimizer_abs_error_reduction_vs_scp",
    )
    for column in fixed_columns:
        label = visible_column_label(column)
        assert "Optimizer vs Auto" in label

    generic = visible_column_label("selected_engine_win_rate")
    assert generic == "Tasa de victoria del motor analizado"
    assert "motor seleccionado" not in generic.lower()
    assert visible_column_label(
        "selected_engine_win_rate", engine=ENGINE_SCP_AUTO,
    ) == "Tasa de victoria — SCP Classic Auto"
    assert visible_column_label(
        "selected_engine_win_rate", engine=ENGINE_OPTIMIZER,
    ) == "Tasa de victoria — SCP Classic Optimizer"


def test_stability_and_unmapped_labels_preserve_distinct_meanings():
    assert stability_state_label(STABILITY_STATE_STABLE) == "Estable"
    assert stability_state_label(STABILITY_STATE_CHANGED) == "Cambió"
    assert stability_state_label(STABILITY_STATE_NOT_EVALUABLE) == "No evaluable"
    assert family_label(FAMILY_UNMAPPED) == "Sin familia mapeada"

    presentation = prepare_portfolio_presentation(
        _client_result(_state_dataframe()).portfolio
    )
    events = presentation.tables[SCHEMA_CANONICAL_EVENTS].dataframe
    optimizer_older = events[
        (events["engine"] == ENGINE_LABELS[ENGINE_OPTIMIZER])
        & (events["block"] == BLOCK_LABELS[BLOCK_OLDER_3M])
    ]
    unmapped = optimizer_older[optimizer_older["model_name"].notna()].iloc[0]
    missing = optimizer_older[optimizer_older["model_name"].isna()].iloc[0]

    assert unmapped["family"] == FAMILY_LABELS[FAMILY_UNMAPPED]
    assert unmapped["family_mapping_status"] == "Modelo presente sin familia mapeada"
    assert missing["model_metadata_status"] == "Metadata ausente"
    assert pd.isna(missing["family"])
    assert missing["family_mapping_status"] == "Modelo ausente; familia no evaluable"


def test_optimizer_classification_values_are_not_recoded_or_grouped():
    presentation = prepare_portfolio_presentation(
        _client_result(_optimizer_dataframe()).portfolio
    )
    events = presentation.tables[SCHEMA_CANONICAL_EVENTS].dataframe
    values = set(events["optimizer_classification"].dropna())
    assert values == {"smooth_acceptable", "erratic_acceptable"}


def test_availability_distinguishes_unavailable_empty_and_content():
    historical = _client_result(build_synthetic_client_dataframe()).portfolio
    unavailable = portfolio_presentation_availability(historical)
    assert unavailable.state == PortfolioPresentationState.UNAVAILABLE
    assert unavailable.available is False
    assert unavailable.has_assignments is False
    assert unavailable.message == PORTFOLIO_UNAVAILABLE_NOTE
    assert unavailable.missing_required_columns == PORTFOLIO_REQUIRED_COLUMNS
    assert "no implica un error del pipeline" in unavailable.message

    empty_df = _portfolio_dataframe()
    for column in (
        "SCP_MODEL_OLDER_3M",
        "SCP_MODEL_RECENT_3M",
        "ML_BEST_MODEL_OLDER_3M",
        "ML_BEST_MODEL_RECENT_3M",
    ):
        empty_df[column] = None
    empty = portfolio_presentation_availability(_client_result(empty_df).portfolio)
    assert empty.state == PortfolioPresentationState.AVAILABLE_EMPTY
    assert empty.available is True
    assert empty.has_assignments is False
    assert "no se observaron asignaciones" in empty.message

    normal = portfolio_presentation_availability(_available_portfolio())
    assert normal.state == PortfolioPresentationState.AVAILABLE_WITH_CONTENT
    assert normal.available is True
    assert normal.has_assignments is True


def test_unavailable_preparation_exposes_audit_columns_and_no_partial_tables():
    historical = _client_result(build_synthetic_client_dataframe()).portfolio
    presentation = prepare_portfolio_presentation(historical)

    assert presentation.availability.missing_required_columns == PORTFOLIO_REQUIRED_COLUMNS
    assert presentation.tables == {}
    assert presentation.methodology_note == PORTFOLIO_CONDITIONED_PERFORMANCE_NOTE


@pytest.mark.parametrize(
    ("n_performance", "small_sample", "state", "label", "warning"),
    [
        (0, True, PortfolioSampleState.NO_PERFORMANCE, "Sin performance evaluable", False),
        (9, True, PortfolioSampleState.SMALL_SAMPLE, "Muestra reducida", True),
        (10, False, PortfolioSampleState.NO_WARNING, None, False),
    ],
)
def test_small_sample_presentation_contract(
    n_performance, small_sample, state, label, warning,
):
    outcome = performance_sample_presentation(n_performance, small_sample)
    assert outcome.state == state
    assert outcome.label == label
    assert outcome.warning is warning
    assert "no invalida automáticamente" in PORTFOLIO_SMALL_SAMPLE_NOTE


@pytest.mark.parametrize(
    ("n_performance", "small_sample"),
    [(0, False), (9, False), (10, True)],
)
def test_small_sample_inconsistency_is_rejected_without_replacing_core_value(
    n_performance, small_sample,
):
    with pytest.raises(PortfolioPresentationContractError, match="inconsistent"):
        performance_sample_presentation(n_performance, small_sample)


def test_every_10b_table_has_an_exact_presentation_schema():
    expected = {
        SCHEMA_COVERAGE: COVERAGE_COLUMNS,
        SCHEMA_MODELS: MODEL_TABLE_COLUMNS,
        SCHEMA_FAMILIES: FAMILY_TABLE_COLUMNS,
        SCHEMA_CLASSIFICATION_COVERAGE: OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
        SCHEMA_CLASSIFICATION_MODEL: CLASSIFICATION_MODEL_TABLE_COLUMNS,
        SCHEMA_CLASSIFICATION_FAMILY: CLASSIFICATION_FAMILY_TABLE_COLUMNS,
        SCHEMA_MODEL_STABILITY_SUMMARY: STABILITY_SUMMARY_COLUMNS,
        SCHEMA_STABILITY_BY_OLDER_MODEL: MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS,
        SCHEMA_MODEL_TRANSITIONS: TRANSITION_COLUMNS,
        SCHEMA_CLASSIFICATION_STABILITY: STABILITY_SUMMARY_COLUMNS,
        SCHEMA_CLASSIFICATION_TRANSITIONS: TRANSITION_COLUMNS,
        SCHEMA_PERFORMANCE_BY_STABILITY: STABILITY_PERFORMANCE_COLUMNS,
        SCHEMA_CANONICAL_EVENTS: CANONICAL_EVENT_COLUMNS,
    }
    assert set(PORTFOLIO_TABLE_SCHEMAS) == set(expected)
    for key, columns in expected.items():
        assert PORTFOLIO_TABLE_SCHEMAS[key].columns == columns
        assert all(column in COLUMN_PRESENTATIONS for column in columns)
    assert PORTFOLIO_TABLE_SCHEMAS[SCHEMA_CANONICAL_EVENTS].technical_audit_surface is True


def test_complete_table_preparation_is_deterministic_and_keeps_10b_semantic_order():
    raw = _available_portfolio().model_tables.by_engine_block_model
    shuffled = raw.sample(frac=1, random_state=73).reset_index(drop=True)

    from_core = prepare_portfolio_table(raw, SCHEMA_MODELS).dataframe
    from_shuffled = prepare_portfolio_table(shuffled, SCHEMA_MODELS).dataframe
    assert_frame_equal(from_core, from_shuffled)

    expected_prefix = [
        (ENGINE_LABELS[ENGINE_SCP_AUTO], BLOCK_LABELS[BLOCK_OLDER_3M]),
        (ENGINE_LABELS[ENGINE_SCP_AUTO], BLOCK_LABELS[BLOCK_RECENT_3M]),
        (ENGINE_LABELS[ENGINE_SCP_AUTO], BLOCK_LABELS[BLOCK_RECENT_3M]),
    ]
    assert list(
        from_core[["engine", "block"]].head(3).itertuples(index=False, name=None)
    ) == expected_prefix


def test_n_performance_zero_row_is_preserved_by_table_preparation():
    from src.portfolio import build_portfolio_model_result

    table = build_portfolio_model_result(_conditioned_events()).by_engine_block_model
    prepared = prepare_portfolio_table(table, SCHEMA_MODELS).dataframe
    zero_rows = prepared[prepared["n_performance"] == 0]

    assert not zero_rows.empty
    assert zero_rows["small_sample"].all()


def test_preparation_does_not_mutate_portfolio_or_any_source_dataframe():
    portfolio = _available_portfolio()
    source_tables = _portfolio_source_tables(portfolio)
    snapshots = {key: table.copy(deep=True) for key, table in source_tables.items()}

    presentation = prepare_portfolio_presentation(portfolio)

    for key, source in source_tables.items():
        assert_frame_equal(source, snapshots[key])
        assert presentation.tables[key].dataframe is not source

    prepared_models = presentation.tables[SCHEMA_MODELS].dataframe
    if not prepared_models.empty:
        prepared_models.loc[0, "model_name"] = "presentation-only mutation"
        assert_frame_equal(source_tables[SCHEMA_MODELS], snapshots[SCHEMA_MODELS])


def test_visible_dataframe_is_a_copy_with_declared_user_labels():
    prepared = prepare_portfolio_presentation(_available_portfolio()).tables[SCHEMA_MODELS]
    visible = prepared.visible_dataframe()

    assert "Motor analizado" in visible.columns
    assert "Período" in visible.columns
    assert "Mejora de WAPE — Optimizer vs Auto" in visible.columns
    assert "Tasa de victoria del motor analizado" in visible.columns
    assert visible is not prepared.dataframe


def test_presentation_is_independent_from_all_forbidden_legacy_metadata():
    forbidden = {
        "SCP_BEST_MODEL",
        "ML_BEST_MODEL",
        "ML_CLASSIFICATION",
        "SCP_CLASSIFICATION",
        "SERIES_CLASSIFICATION",
        "ML_TYPE",
    }
    assert forbidden.isdisjoint(COLUMN_PRESENTATIONS)
    assert forbidden.isdisjoint({
        column
        for schema in PORTFOLIO_TABLE_SCHEMAS.values()
        for column in schema.columns
    })

    left_df = _state_dataframe()
    right_df = _state_dataframe()
    for index, column in enumerate(sorted(forbidden)):
        left_df[column] = f"legacy-left-{index}"
        right_df[column] = f"legacy-right-{index}"

    left = prepare_portfolio_presentation(_client_result(left_df).portfolio)
    right = prepare_portfolio_presentation(_client_result(right_df).portfolio)
    for key in PORTFOLIO_TABLE_SCHEMAS:
        assert_frame_equal(left.tables[key].dataframe, right.tables[key].dataframe)
