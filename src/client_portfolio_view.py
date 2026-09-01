"""Compact client-facing view of the already-calculated portfolio result.

The HTML and Markdown surfaces share this adapter.  It only selects rows and
formats values from :mod:`src.portfolio_presentation`; it never recalculates
portfolio analytics and never reads legacy six-month metadata.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.portfolio_presentation import (
    SCHEMA_CLASSIFICATION_COVERAGE,
    SCHEMA_CLASSIFICATION_STABILITY,
    SCHEMA_CLASSIFICATION_TRANSITIONS,
    SCHEMA_COVERAGE,
    SCHEMA_FAMILIES,
    SCHEMA_MODEL_STABILITY_SUMMARY,
    SCHEMA_MODEL_TRANSITIONS,
    SCHEMA_MODELS,
    SCHEMA_PERFORMANCE_BY_STABILITY,
    PortfolioPresentationResult,
    format_portfolio_value,
    performance_sample_presentation,
    prepare_portfolio_presentation,
)

PORTFOLIO_STABILITY_DESCRIPTIVE_NOTE = (
    "La estabilidad compara asignaciones observadas entre ambos períodos. Las diferencias de "
    "performance entre grupos estables y cambiantes son descriptivas y no demuestran causalidad."
)

_MODEL_COLUMNS = (
    "model_name", "selection_count", "selection_share_of_assignable", "n_performance",
    "historical_volume", "scp_wape", "optimizer_wape", "scp_bias", "optimizer_bias",
    "selected_engine_win_rate", "optimizer_improvement_vs_scp",
    "optimizer_abs_error_reduction_vs_scp",
)
_FAMILY_COLUMNS = (
    "block", "family", "selection_count", "selection_share_of_assignable", "n_performance",
    "scp_wape", "optimizer_wape", "optimizer_bias", "selected_engine_win_rate",
    "optimizer_improvement_vs_scp",
)
_COVERAGE_COLUMNS = (
    "engine", "block", "n_base_series", "n_structural_events", "n_model_present",
    "n_model_missing", "selection_assignment_rate", "n_performance_evaluable",
)
_CLASSIFICATION_COVERAGE_COLUMNS = (
    "block", "n_classification_present", "n_classification_missing",
    "classification_assignment_rate", "n_pair_assignable", "pair_assignment_rate",
)
_STABILITY_COLUMNS = (
    "engine", "n_evaluable", "stable_count", "changed_count", "not_evaluable_count",
    "stability_rate",
)
_TRANSITION_COLUMNS = ("engine", "older_value", "recent_value", "transition_count")
_PERFORMANCE_COLUMNS = (
    "stability_type", "engine", "block", "stability_state", "n_performance",
    "scp_wape", "optimizer_wape", "optimizer_bias", "selected_engine_win_rate",
    "optimizer_improvement_vs_scp", "optimizer_abs_error_reduction_vs_scp",
)


def _formatted_rows(dataframe: pd.DataFrame, columns: Iterable[str]) -> list[dict[str, str]]:
    return [
        {column: format_portfolio_value(column, row[column]) for column in columns}
        for _, row in dataframe.iterrows()
    ]


def _sample_label(row: pd.Series) -> str:
    sample = performance_sample_presentation(int(row["n_performance"]), bool(row["small_sample"]))
    return sample.label or ""


def _compact_models(dataframe: pd.DataFrame, limit: int) -> list[dict]:
    groups: list[dict] = []
    if dataframe.empty:
        return groups
    for (engine, block), group in dataframe.groupby(["engine", "block"], sort=False, dropna=False):
        ordered = group.sort_values(
            ["selection_count", "model_name"], ascending=[False, True], kind="stable",
        )
        shown = ordered.head(limit)
        rows = _formatted_rows(shown, _MODEL_COLUMNS)
        for payload, (_, source_row) in zip(rows, shown.iterrows()):
            payload["sample_note"] = _sample_label(source_row)
        groups.append({
            "engine": str(engine),
            "block": str(block),
            "rows": rows,
            "total_rows": len(ordered),
            "truncated": len(ordered) > len(shown),
        })
    return groups


def _compact_transitions(dataframe: pd.DataFrame, limit: int) -> dict:
    shown_groups = []
    for _, group in dataframe.groupby("engine", sort=False, dropna=False):
        ordered_group = group.sort_values(
            ["transition_count", "older_value", "recent_value"],
            ascending=[False, True, True],
            kind="stable",
        )
        shown_groups.append(ordered_group.head(limit))
    shown = pd.concat(shown_groups, ignore_index=True) if shown_groups else dataframe.head(0)
    return {
        "rows": _formatted_rows(shown, _TRANSITION_COLUMNS),
        "total_rows": len(dataframe),
        "truncated": len(dataframe) > len(shown),
        "limit_per_engine": limit,
    }


def build_client_portfolio_view(portfolio, *, compact_limit: int = 8) -> dict:
    """Return a formatted, template-safe summary sourced only from ``portfolio``."""
    presentation: PortfolioPresentationResult = prepare_portfolio_presentation(portfolio)
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
        "model_stability": [],
        "model_transitions": {"rows": [], "total_rows": 0, "truncated": False, "limit_per_engine": compact_limit},
        "classification_stability": [],
        "classification_transitions": {"rows": [], "total_rows": 0, "truncated": False, "limit_per_engine": compact_limit},
        "performance_by_stability": [],
    }
    if not availability.available:
        return view

    tables = presentation.tables
    view["coverage"] = _formatted_rows(tables[SCHEMA_COVERAGE].dataframe, _COVERAGE_COLUMNS)
    view["models"] = _compact_models(tables[SCHEMA_MODELS].dataframe, compact_limit)

    families = tables[SCHEMA_FAMILIES].dataframe
    view["families"] = _formatted_rows(families, _FAMILY_COLUMNS)
    for payload, (_, source_row) in zip(view["families"], families.iterrows()):
        payload["sample_note"] = _sample_label(source_row)

    view["classification_coverage"] = _formatted_rows(
        tables[SCHEMA_CLASSIFICATION_COVERAGE].dataframe,
        _CLASSIFICATION_COVERAGE_COLUMNS,
    )
    view["model_stability"] = _formatted_rows(
        tables[SCHEMA_MODEL_STABILITY_SUMMARY].dataframe, _STABILITY_COLUMNS,
    )
    view["model_transitions"] = _compact_transitions(
        tables[SCHEMA_MODEL_TRANSITIONS].dataframe, compact_limit,
    )
    view["classification_stability"] = _formatted_rows(
        tables[SCHEMA_CLASSIFICATION_STABILITY].dataframe, _STABILITY_COLUMNS,
    )
    view["classification_transitions"] = _compact_transitions(
        tables[SCHEMA_CLASSIFICATION_TRANSITIONS].dataframe, compact_limit,
    )

    performance = tables[SCHEMA_PERFORMANCE_BY_STABILITY].dataframe
    view["performance_by_stability"] = _formatted_rows(performance, _PERFORMANCE_COLUMNS)
    for payload, (_, source_row) in zip(view["performance_by_stability"], performance.iterrows()):
        payload["sample_note"] = _sample_label(source_row)
    return view
