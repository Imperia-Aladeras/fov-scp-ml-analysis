"""Global HTML/Markdown view over a prepared pooled portfolio result.

This module receives the output of ``prepare_portfolio_presentation`` for
``GlobalAnalysisResult.portfolio``.  It only selects and formats rows for
presentation; it never combines client tables or recalculates analytics.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.client_portfolio_view import (
    PORTFOLIO_STABILITY_DESCRIPTIVE_NOTE,
    compact_portfolio_transitions,
    format_portfolio_rows,
    portfolio_sample_label,
)
from src.portfolio_presentation import (
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
    PortfolioPresentationResult,
)

_COVERAGE_COLUMNS = (
    "engine", "block", "n_base_series", "n_structural_events", "n_model_present",
    "n_model_missing", "selection_assignment_rate", "n_block_metrics_evaluable",
    "n_performance_evaluable",
)
_MODEL_COLUMNS = (
    "model_name", "selection_count", "selection_share_of_assignable", "n_performance",
    "n_clients", "historical_volume", "volume_share", "scp_wape", "optimizer_wape",
    "scp_bias", "optimizer_bias", "selected_engine_win_rate",
    "optimizer_improvement_vs_scp", "optimizer_abs_error_reduction_vs_scp",
)
_FAMILY_COLUMNS = (
    "family", "selection_count", "selection_share_of_assignable", "n_performance",
    "n_clients", "historical_volume", "volume_share", "scp_wape", "optimizer_wape",
    "scp_bias", "optimizer_bias", "selected_engine_win_rate",
    "optimizer_improvement_vs_scp", "optimizer_abs_error_reduction_vs_scp",
)
_CLASSIFICATION_COVERAGE_COLUMNS = (
    "block", "n_optimizer_events", "n_model_present", "n_model_missing",
    "n_classification_present", "n_classification_missing",
    "classification_assignment_rate", "n_pair_assignable", "pair_assignment_rate",
)
_CLASSIFICATION_MODEL_COLUMNS = (
    "optimizer_classification", "model_name", "selection_count",
    "selection_share_of_assignable", "n_performance", "n_clients",
    "selected_engine_win_rate", "optimizer_improvement_vs_scp",
)
_CLASSIFICATION_FAMILY_COLUMNS = (
    "optimizer_classification", "family", "selection_count",
    "selection_share_of_assignable", "n_performance", "n_clients",
    "selected_engine_win_rate", "optimizer_improvement_vs_scp",
)
_STABILITY_COLUMNS = (
    "engine", "n_evaluable", "stable_count", "changed_count", "not_evaluable_count",
    "stability_rate",
)
_OLDER_MODEL_COLUMNS = (
    "model_name", "n_evaluable", "stable_count", "changed_count", "stability_rate",
)
_TRANSITION_COLUMNS = (
    "engine", "older_value", "recent_value", "transition_count", "n_evaluable",
    "transition_share_of_evaluable",
)
_PERFORMANCE_COLUMNS = (
    "stability_type", "engine", "block", "stability_state", "n_performance", "n_clients",
    "historical_volume", "scp_wape", "optimizer_wape", "scp_bias", "optimizer_bias",
    "selected_engine_win_rate", "optimizer_improvement_vs_scp",
    "optimizer_abs_error_reduction_vs_scp",
)


def _compact_groups(
    dataframe: pd.DataFrame,
    *,
    group_columns: tuple[str, ...],
    row_columns: Iterable[str],
    order_column: str,
    tie_columns: tuple[str, ...],
    limit: int,
) -> list[dict]:
    groups: list[dict] = []
    if dataframe.empty:
        return groups
    grouper = list(group_columns) if len(group_columns) > 1 else group_columns[0]
    for key, group in dataframe.groupby(grouper, sort=False, dropna=False):
        keys = key if isinstance(key, tuple) else (key,)
        ordered = group.sort_values(
            [order_column, *tie_columns],
            ascending=[False, *([True] * len(tie_columns))],
            kind="stable",
        )
        shown = ordered.head(limit)
        rows = format_portfolio_rows(shown, row_columns)
        if "n_performance" in shown.columns and "small_sample" in shown.columns:
            for payload, (_, source_row) in zip(rows, shown.iterrows()):
                payload["sample_note"] = portfolio_sample_label(source_row)
        groups.append({
            **{column: str(value) for column, value in zip(group_columns, keys)},
            "rows": rows,
            "total_rows": len(ordered),
            "truncated": len(ordered) > len(shown),
            "limit": limit,
        })
    return groups


def build_global_portfolio_view(
    presentation: PortfolioPresentationResult,
    *,
    selection_limit: int = 12,
    cohort_limit: int = 12,
    transition_limit: int = 12,
) -> dict:
    """Build the global presentation solely from an already-prepared result."""
    availability = presentation.availability
    view = {
        "state": availability.state.value,
        "available": availability.available,
        "has_assignments": availability.has_assignments,
        "message": availability.message,
        "missing_required_columns": list(availability.missing_required_columns),
        "methodology_note": presentation.methodology_note,
        "small_sample_note": presentation.small_sample_note,
        "stability_note": PORTFOLIO_STABILITY_DESCRIPTIVE_NOTE,
        "coverage": [],
        "models": [],
        "families": [],
        "classification_coverage": [],
        "classification_models": [],
        "classification_families": [],
        "model_stability": [],
        "older_model_cohorts": [],
        "model_transitions": {"rows": [], "total_rows": 0, "truncated": False},
        "classification_stability": [],
        "classification_transitions": {"rows": [], "total_rows": 0, "truncated": False},
        "performance_by_stability": [],
    }
    if not availability.available:
        return view

    tables = presentation.tables
    view["coverage"] = format_portfolio_rows(tables[SCHEMA_COVERAGE].dataframe, _COVERAGE_COLUMNS)
    view["models"] = _compact_groups(
        tables[SCHEMA_MODELS].dataframe,
        group_columns=("engine", "block"), row_columns=_MODEL_COLUMNS,
        order_column="selection_count", tie_columns=("model_name",), limit=selection_limit,
    )
    view["families"] = _compact_groups(
        tables[SCHEMA_FAMILIES].dataframe,
        group_columns=("block",), row_columns=_FAMILY_COLUMNS,
        order_column="selection_count", tie_columns=("family",), limit=selection_limit,
    )
    view["classification_coverage"] = format_portfolio_rows(
        tables[SCHEMA_CLASSIFICATION_COVERAGE].dataframe, _CLASSIFICATION_COVERAGE_COLUMNS,
    )
    view["classification_models"] = _compact_groups(
        tables[SCHEMA_CLASSIFICATION_MODEL].dataframe,
        group_columns=("block",), row_columns=_CLASSIFICATION_MODEL_COLUMNS,
        order_column="selection_count", tie_columns=("optimizer_classification", "model_name"),
        limit=selection_limit,
    )
    view["classification_families"] = _compact_groups(
        tables[SCHEMA_CLASSIFICATION_FAMILY].dataframe,
        group_columns=("block",), row_columns=_CLASSIFICATION_FAMILY_COLUMNS,
        order_column="selection_count", tie_columns=("optimizer_classification", "family"),
        limit=selection_limit,
    )
    view["model_stability"] = format_portfolio_rows(
        tables[SCHEMA_MODEL_STABILITY_SUMMARY].dataframe, _STABILITY_COLUMNS,
    )
    view["older_model_cohorts"] = _compact_groups(
        tables[SCHEMA_STABILITY_BY_OLDER_MODEL].dataframe,
        group_columns=("engine",), row_columns=_OLDER_MODEL_COLUMNS,
        order_column="n_evaluable", tie_columns=("model_name",), limit=cohort_limit,
    )
    view["model_transitions"] = compact_portfolio_transitions(
        tables[SCHEMA_MODEL_TRANSITIONS].dataframe,
        transition_limit,
        columns=_TRANSITION_COLUMNS,
    )
    view["classification_stability"] = format_portfolio_rows(
        tables[SCHEMA_CLASSIFICATION_STABILITY].dataframe, _STABILITY_COLUMNS,
    )
    view["classification_transitions"] = compact_portfolio_transitions(
        tables[SCHEMA_CLASSIFICATION_TRANSITIONS].dataframe,
        transition_limit,
        columns=_TRANSITION_COLUMNS,
    )
    performance = tables[SCHEMA_PERFORMANCE_BY_STABILITY].dataframe
    view["performance_by_stability"] = format_portfolio_rows(performance, _PERFORMANCE_COLUMNS)
    for payload, (_, source_row) in zip(view["performance_by_stability"], performance.iterrows()):
        payload["sample_note"] = portfolio_sample_label(source_row)
    return view
