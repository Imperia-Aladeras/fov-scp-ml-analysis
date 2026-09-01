"""Canonical block events for the Phase 10B portfolio analysis.

This module deliberately stops at the 10B.2 contract: availability,
long-form structural events and coverage.  It does not aggregate by model,
family or classification, and it never falls back to legacy 6M metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from src.input_loader import KEY_COLUMNS
from src.metrics import absolute_error_reduction_row, relative_improvement_row
from src.periods import PeriodColumns, period_columns


ENGINE_SCP_AUTO = "SCP_AUTO"
ENGINE_OPTIMIZER = "OPTIMIZER"
BLOCK_OLDER_3M = "OLDER_3M"
BLOCK_RECENT_3M = "RECENT_3M"

MODEL_METADATA_PRESENT = "PRESENT"
MODEL_METADATA_MISSING = "MISSING"
CLASSIFICATION_PRESENT = "PRESENT"
CLASSIFICATION_MISSING = "MISSING"
CLASSIFICATION_NOT_APPLICABLE = "NOT_APPLICABLE"

AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING = "BLOCK_METADATA_COLUMNS_MISSING"
AVAILABILITY_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
AVAILABILITY_NO_VALID_CLIENTS = "NO_VALID_CLIENTS"

PORTFOLIO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "SCP_MODEL_OLDER_3M",
    "SCP_MODEL_RECENT_3M",
    "ML_BEST_MODEL_OLDER_3M",
    "ML_BEST_MODEL_RECENT_3M",
    "ML_CLASSIFICATION_OLDER_3M",
    "ML_CLASSIFICATION_RECENT_3M",
)

EVENT_KEY_COLUMNS: tuple[str, ...] = (*KEY_COLUMNS, "engine", "block")

COVERAGE_COLUMNS: tuple[str, ...] = (
    "engine",
    "block",
    "n_base_series",
    "n_structural_events",
    "n_model_present",
    "n_model_missing",
    "selection_assignment_rate",
    "n_block_metrics_evaluable",
    "n_performance_evaluable",
)


class PortfolioContractError(ValueError):
    """Raised when the canonical event identity would not be unique."""


@dataclass(frozen=True)
class PortfolioAvailability:
    available: bool
    reason: str | None = None
    missing_required_columns: tuple[str, ...] = ()


@dataclass
class PortfolioBlockEvents:
    dataframe: pd.DataFrame

    def __len__(self) -> int:
        return len(self.dataframe)


@dataclass
class PortfolioCoverage:
    by_engine_block: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=COVERAGE_COLUMNS),
    )


@dataclass
class PortfolioAnalysisResult:
    availability: PortfolioAvailability
    events: PortfolioBlockEvents | None = None
    coverage: PortfolioCoverage | None = None

    @classmethod
    def unavailable(
        cls,
        reason: str,
        missing_required_columns: Iterable[str] = (),
    ) -> "PortfolioAnalysisResult":
        return cls(
            availability=PortfolioAvailability(
                available=False,
                reason=reason,
                missing_required_columns=tuple(missing_required_columns),
            ),
        )


@dataclass(frozen=True)
class _EventSpec:
    engine: str
    block: str
    model_column: str
    classification_column: str | None


_EVENT_SPECS: tuple[_EventSpec, ...] = (
    _EventSpec(ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "SCP_MODEL_OLDER_3M", None),
    _EventSpec(ENGINE_SCP_AUTO, BLOCK_RECENT_3M, "SCP_MODEL_RECENT_3M", None),
    _EventSpec(
        ENGINE_OPTIMIZER,
        BLOCK_OLDER_3M,
        "ML_BEST_MODEL_OLDER_3M",
        "ML_CLASSIFICATION_OLDER_3M",
    ),
    _EventSpec(
        ENGINE_OPTIMIZER,
        BLOCK_RECENT_3M,
        "ML_BEST_MODEL_RECENT_3M",
        "ML_CLASSIFICATION_RECENT_3M",
    ),
)


def missing_portfolio_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return missing 10B columns without changing the global CSV schema contract."""
    return tuple(column for column in PORTFOLIO_REQUIRED_COLUMNS if column not in df.columns)


def _validate_source_cardinality(source_df: pd.DataFrame) -> None:
    missing_keys = [column for column in KEY_COLUMNS if column not in source_df.columns]
    if missing_keys:
        raise PortfolioContractError(
            "Portfolio source is missing canonical key columns: " + ", ".join(missing_keys)
        )
    duplicated = source_df.duplicated(subset=KEY_COLUMNS, keep=False)
    if duplicated.any():
        raise PortfolioContractError(
            "Portfolio source contains duplicate source_series_key rows."
        )


def _event_metrics(source_df: pd.DataFrame, pcols: PeriodColumns) -> dict[str, pd.Series]:
    improvement, _ = relative_improvement_row(source_df[pcols.scp_wape], source_df[pcols.ml_wape])
    return {
        "total_history": source_df[pcols.total_history],
        "scp_total_abs_error": source_df[pcols.scp_total_abs_error],
        "optimizer_total_abs_error": source_df[pcols.ml_total_abs_error],
        "scp_total_signed_error": source_df[pcols.scp_total_signed_error],
        "optimizer_total_signed_error": source_df[pcols.ml_total_signed_error],
        "scp_wape": source_df[pcols.scp_wape],
        "optimizer_wape": source_df[pcols.ml_wape],
        "scp_bias": source_df[pcols.scp_bias],
        "optimizer_bias": source_df[pcols.ml_bias],
        "winner_method": source_df[pcols.winner_method],
        "optimizer_improvement_vs_scp": improvement,
        "optimizer_abs_error_reduction_vs_scp": absolute_error_reduction_row(source_df, pcols),
    }


def _build_event_frame(
    source_df: pd.DataFrame,
    source_keys: list[tuple],
    spec: _EventSpec,
    block_metrics_mask: pd.Series,
) -> pd.DataFrame:
    pcols = period_columns(spec.block)
    model = source_df[spec.model_column]
    selection_evaluable = model.notna()

    event = source_df[list(KEY_COLUMNS)].copy()
    event["source_series_key"] = source_keys
    event["RUN_START_DATE"] = (
        source_df["RUN_START_DATE"] if "RUN_START_DATE" in source_df.columns else pd.NaT
    )
    event["engine"] = spec.engine
    event["block"] = spec.block
    event["model_name"] = model
    event["model_metadata_status"] = np.where(
        selection_evaluable, MODEL_METADATA_PRESENT, MODEL_METADATA_MISSING,
    )

    if spec.classification_column is None:
        event["optimizer_classification"] = pd.NA
        event["classification_metadata_status"] = CLASSIFICATION_NOT_APPLICABLE
    else:
        classification = source_df[spec.classification_column]
        event["optimizer_classification"] = classification
        event["classification_metadata_status"] = np.where(
            classification.notna(), CLASSIFICATION_PRESENT, CLASSIFICATION_MISSING,
        )

    event["selection_evaluable"] = selection_evaluable.astype(bool)
    event["block_metrics_evaluable"] = block_metrics_mask.astype(bool)
    event["performance_evaluable"] = (
        event["selection_evaluable"] & event["block_metrics_evaluable"]
    )

    for column, values in _event_metrics(source_df, pcols).items():
        event[column] = values
    return event


def _validate_event_cardinality(events: pd.DataFrame) -> None:
    duplicated = events.duplicated(subset=list(EVENT_KEY_COLUMNS), keep=False)
    if duplicated.any():
        raise PortfolioContractError(
            "Portfolio events are not unique by source_series_key + engine + block."
        )


def build_portfolio_coverage(events: pd.DataFrame) -> PortfolioCoverage:
    """Build coverage only; model-missing remains diagnostic rather than a category."""
    rows: list[dict] = []
    for (engine, block), group in events.groupby(["engine", "block"], sort=False, observed=True):
        n_structural = len(group)
        n_present = int(group["selection_evaluable"].sum())
        rows.append({
            "engine": engine,
            "block": block,
            "n_base_series": int(group["source_series_key"].nunique()),
            "n_structural_events": n_structural,
            "n_model_present": n_present,
            "n_model_missing": n_structural - n_present,
            # Fraction in [0, 1], deliberately not a percentage.
            "selection_assignment_rate": (n_present / n_structural) if n_structural else np.nan,
            "n_block_metrics_evaluable": int(group["block_metrics_evaluable"].sum()),
            "n_performance_evaluable": int(group["performance_evaluable"].sum()),
        })
    return PortfolioCoverage(pd.DataFrame(rows, columns=COVERAGE_COLUMNS))


def build_portfolio_analysis(
    df: pd.DataFrame,
    candidate_mask: pd.Series,
    block_metrics_masks: Mapping[str, pd.Series],
) -> PortfolioAnalysisResult:
    """Build the complete 10B.2 result for one already-valid client source."""
    missing_columns = missing_portfolio_columns(df)
    if missing_columns:
        return PortfolioAnalysisResult.unavailable(
            AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING,
            missing_columns,
        )

    source_df = df.loc[candidate_mask].copy()
    _validate_source_cardinality(source_df)
    source_keys = list(source_df[list(KEY_COLUMNS)].itertuples(index=False, name=None))

    frames: list[pd.DataFrame] = []
    for spec in _EVENT_SPECS:
        if spec.block not in block_metrics_masks:
            raise PortfolioContractError(f"Missing comparable mask for portfolio block {spec.block}.")
        block_mask = block_metrics_masks[spec.block].reindex(source_df.index, fill_value=False)
        frames.append(_build_event_frame(source_df, source_keys, spec, block_mask))

    events_df = pd.concat(frames, ignore_index=True)
    _validate_event_cardinality(events_df)
    expected_events = len(source_df) * len(_EVENT_SPECS)
    if len(events_df) != expected_events:
        raise PortfolioContractError(
            f"Expected {expected_events} structural portfolio events, got {len(events_df)}."
        )

    events = PortfolioBlockEvents(events_df)
    return PortfolioAnalysisResult(
        availability=PortfolioAvailability(available=True),
        events=events,
        coverage=build_portfolio_coverage(events_df),
    )


def combine_portfolio_analyses(
    portfolios: Iterable[PortfolioAnalysisResult],
) -> PortfolioAnalysisResult:
    """Combine valid client portfolio results without silently creating a partial global result."""
    portfolios = list(portfolios)
    if not portfolios:
        return PortfolioAnalysisResult.unavailable(AVAILABILITY_NO_VALID_CLIENTS)

    unavailable = [result for result in portfolios if not result.availability.available]
    if unavailable:
        missing_set = {
            column
            for result in unavailable
            for column in result.availability.missing_required_columns
        }
        missing = tuple(column for column in PORTFOLIO_REQUIRED_COLUMNS if column in missing_set)
        reason = (
            AVAILABILITY_BLOCK_METADATA_COLUMNS_MISSING
            if missing
            else unavailable[0].availability.reason or AVAILABILITY_SOURCE_UNAVAILABLE
        )
        return PortfolioAnalysisResult.unavailable(reason, missing)

    frames = [
        result.events.dataframe
        for result in portfolios
        if result.events is not None
    ]
    events_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not events_df.empty:
        _validate_event_cardinality(events_df)
    events = PortfolioBlockEvents(events_df)
    return PortfolioAnalysisResult(
        availability=PortfolioAvailability(available=True),
        events=events,
        coverage=build_portfolio_coverage(events_df),
    )
