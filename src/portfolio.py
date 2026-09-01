"""Canonical block events and conditioned portfolio analysis for Phase 10B.

It contains the 10B.2 availability/event/coverage contract, the 10B.3
aggregation by selected model and the explicit Optimizer-only family and
classification adapters from 10B.4.  It does not implement stability or
transitions, and it never falls back to legacy 6M metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from src.input_loader import KEY_COLUMNS
from src.metrics import (
    absolute_error_reduction_row,
    absolute_error_reduction_total,
    bias_aggregate,
    period_wape_global,
    relative_improvement_row,
    winner_distribution,
)
from src.models import MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION
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
FAMILY_MAPPING_MAPPED = "MAPPED"
FAMILY_MAPPING_UNMAPPED = "UNMAPPED"
FAMILY_MAPPING_NOT_EVALUABLE = "NOT_EVALUABLE"
FAMILY_MAPPING_NOT_APPLICABLE = "NOT_APPLICABLE"
FAMILY_UNMAPPED = "UNMAPPED"

# Reporting-owned, explicit copy of the family metadata declared by the
# Optimizer registry/wrappers.  Unknown selected models remain analytically
# assignable as UNMAPPED; names are never parsed or normalized heuristically.
OPTIMIZER_MODEL_FAMILY: dict[str, str] = {
    "Naive": "baselines",
    "SeasonalNaive": "baselines",
    "HistoricAverage": "baselines",
    "SES": "baselines",
    "RandomWalkWithDrift": "baselines",
    "WindowAverage": "baselines",
    "SeasonalWindowAverage": "baselines",
    "MovingAverage3M": "baselines",
    "MovingAverage12M": "baselines",
    "AutoETS": "classical",
    "AutoARIMA": "classical",
    "AutoTheta": "classical",
    "AutoCES": "classical",
    "ARIMA": "classical",
    "Holt": "classical",
    "HoltWinters": "classical",
    "Prophet": "classical",
    "ADIDA": "intermittent",
    "CrostonClassic": "intermittent",
    "CrostonOptimized": "intermittent",
    "CrostonSBA": "intermittent",
    "IMAPA": "intermittent",
    "TSB": "intermittent",
    "LocalCrostonClassic": "intermittent",
    "LocalCrostonOptimized": "intermittent",
    "LocalTSB": "intermittent",
    "LGBMRegressor": "ml",
    "Lasso": "ml",
    "Ridge": "ml",
    "ElasticNet": "ml",
    "HuberRegressor": "ml",
    "PoissonRegressor": "ml",
    "XGBRegressor": "ml",
    "CatBoostRegressor": "ml",
    "RandomForestRegressor": "ml",
    "HistGBDTRegressor": "ml",
}

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

CONDITIONED_METRIC_COLUMNS: tuple[str, ...] = (
    "selection_count",
    "selection_assignable_count",
    "selection_share_of_assignable",
    "n_performance",
    "n_clients",
    "small_sample",
    "historical_volume",
    "volume_share",
    "scp_wape",
    "optimizer_wape",
    "scp_bias",
    "optimizer_bias",
    "selected_engine_win_count",
    "tie_count",
    "selected_engine_win_rate",
    "optimizer_improvement_vs_scp",
    "optimizer_median_improvement_vs_scp",
    "optimizer_abs_error_reduction_vs_scp",
)

MODEL_TABLE_COLUMNS: tuple[str, ...] = (
    "engine",
    "block",
    "model_name",
    *CONDITIONED_METRIC_COLUMNS,
)

FAMILY_TABLE_COLUMNS: tuple[str, ...] = (
    "block",
    "family",
    *CONDITIONED_METRIC_COLUMNS,
)

CLASSIFICATION_MODEL_TABLE_COLUMNS: tuple[str, ...] = (
    "block",
    "optimizer_classification",
    "model_name",
    *CONDITIONED_METRIC_COLUMNS,
)

CLASSIFICATION_FAMILY_TABLE_COLUMNS: tuple[str, ...] = (
    "block",
    "optimizer_classification",
    "family",
    *CONDITIONED_METRIC_COLUMNS,
)

OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS: tuple[str, ...] = (
    "block",
    "n_optimizer_events",
    "n_model_present",
    "n_model_missing",
    "n_classification_present",
    "n_classification_missing",
    "classification_assignment_rate",
    "n_pair_assignable",
    "pair_assignment_rate",
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
class PortfolioModelResult:
    """Observed performance conditioned on model selection, never a model ranking."""

    by_engine_block_model: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=MODEL_TABLE_COLUMNS),
    )


@dataclass(frozen=True)
class OptimizerFamilyEnrichment:
    """Auditable family outcome for one Optimizer selected-model value."""

    family: str | None
    family_mapping_status: str


@dataclass
class OptimizerClassificationCoverage:
    by_block: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
        ),
    )


@dataclass
class OptimizerPortfolioResult:
    """Optimizer-only descriptive views conditioned on observed selection."""

    family_tables: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=FAMILY_TABLE_COLUMNS),
    )
    classification_model_tables: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=CLASSIFICATION_MODEL_TABLE_COLUMNS),
    )
    classification_family_tables: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=CLASSIFICATION_FAMILY_TABLE_COLUMNS),
    )
    classification_coverage: OptimizerClassificationCoverage = field(
        default_factory=OptimizerClassificationCoverage,
    )


@dataclass
class PortfolioAnalysisResult:
    availability: PortfolioAvailability
    events: PortfolioBlockEvents | None = None
    coverage: PortfolioCoverage | None = None
    model_tables: PortfolioModelResult | None = None
    optimizer: OptimizerPortfolioResult | None = None

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


def optimizer_family_enrichment(model_name: object) -> OptimizerFamilyEnrichment:
    """Map one Optimizer model using only the explicit registry-derived table."""
    if pd.isna(model_name):
        return OptimizerFamilyEnrichment(None, FAMILY_MAPPING_NOT_EVALUABLE)
    family = OPTIMIZER_MODEL_FAMILY.get(model_name)
    if family is None:
        return OptimizerFamilyEnrichment(FAMILY_UNMAPPED, FAMILY_MAPPING_UNMAPPED)
    return OptimizerFamilyEnrichment(family, FAMILY_MAPPING_MAPPED)


def enrich_optimizer_family_events(events: pd.DataFrame) -> pd.DataFrame:
    """Add Optimizer family metadata without changing event cardinality or names."""
    enriched = events.copy()
    optimizer = enriched["engine"].eq(ENGINE_OPTIMIZER)
    model_present = enriched["model_name"].notna()
    mapped_family = enriched["model_name"].map(OPTIMIZER_MODEL_FAMILY)
    mapped = optimizer & model_present & mapped_family.notna()
    unmapped = optimizer & model_present & mapped_family.isna()

    enriched["family"] = pd.Series(pd.NA, index=enriched.index, dtype="object")
    enriched.loc[mapped, "family"] = mapped_family.loc[mapped]
    enriched.loc[unmapped, "family"] = FAMILY_UNMAPPED

    enriched["family_mapping_status"] = FAMILY_MAPPING_NOT_APPLICABLE
    enriched.loc[optimizer & ~model_present, "family_mapping_status"] = (
        FAMILY_MAPPING_NOT_EVALUABLE
    )
    enriched.loc[mapped, "family_mapping_status"] = FAMILY_MAPPING_MAPPED
    enriched.loc[unmapped, "family_mapping_status"] = FAMILY_MAPPING_UNMAPPED
    return enriched


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


def _period_metric_frame(events: pd.DataFrame, block: str) -> tuple[pd.DataFrame, PeriodColumns]:
    """Adapt normalized event metrics to the already-validated period math API."""
    pcols = period_columns(block)
    return pd.DataFrame({
        pcols.total_history: events["total_history"],
        pcols.scp_total_abs_error: events["scp_total_abs_error"],
        pcols.ml_total_abs_error: events["optimizer_total_abs_error"],
        pcols.scp_total_signed_error: events["scp_total_signed_error"],
        pcols.ml_total_signed_error: events["optimizer_total_signed_error"],
    }), pcols


def _performance_metrics(
    group: pd.DataFrame,
    engine: str,
    block: str,
    performance_history_denominator: float,
) -> dict:
    n_performance = len(group)
    if n_performance == 0:
        return {
            "n_performance": 0,
            "n_clients": 0,
            "small_sample": True,
            "historical_volume": 0.0,
            "volume_share": 0.0 if performance_history_denominator > 0 else np.nan,
            "scp_wape": np.nan,
            "optimizer_wape": np.nan,
            "scp_bias": np.nan,
            "optimizer_bias": np.nan,
            "selected_engine_win_count": 0,
            "tie_count": 0,
            "selected_engine_win_rate": np.nan,
            "optimizer_improvement_vs_scp": np.nan,
            "optimizer_median_improvement_vs_scp": np.nan,
            "optimizer_abs_error_reduction_vs_scp": np.nan,
        }

    metric_frame, pcols = _period_metric_frame(group, block)
    wape = period_wape_global(metric_frame, pcols)
    bias = bias_aggregate(metric_frame, pcols)
    winner = winner_distribution(group["winner_method"])
    selected_method = "SCP" if engine == ENGINE_SCP_AUTO else "ML"
    selected_wins = int(winner.get(selected_method, {}).get("n", 0))
    tie_count = int(winner.get("TIE", {}).get("n", 0))
    row_improvement, _ = relative_improvement_row(group["scp_wape"], group["optimizer_wape"])
    historical_volume = wape["history_sum"]

    return {
        "n_performance": n_performance,
        "n_clients": int(group["ID_CLIENT"].nunique()),
        "small_sample": n_performance < MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION,
        "historical_volume": historical_volume,
        "volume_share": (
            historical_volume / performance_history_denominator
            if performance_history_denominator > 0
            else np.nan
        ),
        "scp_wape": wape["scp_wape_global"],
        "optimizer_wape": wape["ml_wape_global"],
        "scp_bias": bias.scp_bias_agg,
        "optimizer_bias": bias.ml_bias_agg,
        "selected_engine_win_count": selected_wins,
        "tie_count": tie_count,
        # Ties and any quality-audited noncanonical winner remain in this denominator.
        "selected_engine_win_rate": selected_wins / n_performance,
        "optimizer_improvement_vs_scp": wape["improvement_pct"],
        "optimizer_median_improvement_vs_scp": (
            float(row_improvement.median()) if row_improvement.notna().any() else np.nan
        ),
        "optimizer_abs_error_reduction_vs_scp": absolute_error_reduction_total(metric_frame, pcols),
    }


def _deterministic_table_order(
    table: pd.DataFrame,
    output_columns: tuple[str, ...],
    sort_columns: tuple[str, ...],
) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=output_columns)

    ordered = table.copy()
    helper_columns: list[str] = []
    fixed_orders = {
        "engine": {ENGINE_SCP_AUTO: 0, ENGINE_OPTIMIZER: 1},
        "block": {BLOCK_OLDER_3M: 0, BLOCK_RECENT_3M: 1},
    }
    for index, column in enumerate(sort_columns):
        helper = f"_portfolio_sort_{index}"
        helper_columns.append(helper)
        mapping = fixed_orders.get(column)
        ordered[helper] = ordered[column].map(mapping) if mapping else ordered[column].map(str)
    ordered = ordered.sort_values(helper_columns, kind="stable")
    return ordered.drop(columns=helper_columns).reset_index(drop=True)[list(output_columns)]


def _conditioned_rows_for_scope(
    selection_scope: pd.DataFrame,
    *,
    engine: str,
    block: str,
    dimension_columns: tuple[str, ...],
) -> list[dict]:
    """Shared 10B math for an already-explicit, selection-assignable scope."""
    if selection_scope.empty:
        return []

    selection_assignable_count = len(selection_scope)
    performance_scope = selection_scope.loc[selection_scope["performance_evaluable"]]
    performance_history_denominator = (
        float(performance_scope["total_history"].sum())
        if not performance_scope["total_history"].isna().any()
        else np.nan
    )
    grouper: str | list[str] = (
        dimension_columns[0] if len(dimension_columns) == 1 else list(dimension_columns)
    )

    rows: list[dict] = []
    for keys, selected_group in selection_scope.groupby(
        grouper,
        sort=False,
        observed=True,
    ):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(dimension_columns, key_values))
        row.update({
            "selection_count": len(selected_group),
            "selection_assignable_count": selection_assignable_count,
            "selection_share_of_assignable": len(selected_group) / selection_assignable_count,
        })
        row.update(_performance_metrics(
            selected_group.loc[selected_group["performance_evaluable"]],
            engine,
            block,
            performance_history_denominator,
        ))
        rows.append(row)
    return rows


def build_portfolio_model_result(events: pd.DataFrame) -> PortfolioModelResult:
    """Aggregate only engine + block + selected model for Phase 10B.3.

    Selection counts use selection-assignable events. Performance metrics
    use only performance-evaluable events and therefore describe observed
    performance conditioned on selection, not intrinsic model quality.
    Shares and win rates are fractions in [0, 1]; improvement remains the
    existing signed percentage with fixed Optimizer-vs-SCP direction.
    """
    selection_events = events.loc[events["selection_evaluable"]].copy()
    if selection_events.empty:
        return PortfolioModelResult()

    rows: list[dict] = []
    for (engine, block), selection_scope in selection_events.groupby(
        ["engine", "block"], sort=False, observed=True,
    ):
        scope_rows = _conditioned_rows_for_scope(
            selection_scope,
            engine=engine,
            block=block,
            dimension_columns=("model_name",),
        )
        rows.extend({"engine": engine, "block": block, **row} for row in scope_rows)

    table = pd.DataFrame(rows, columns=MODEL_TABLE_COLUMNS)
    return PortfolioModelResult(_deterministic_table_order(
        table,
        MODEL_TABLE_COLUMNS,
        ("engine", "block", "model_name"),
    ))


def build_optimizer_classification_coverage(
    events: pd.DataFrame,
) -> OptimizerClassificationCoverage:
    """Report block-specific classification and pair assignment without categories."""
    optimizer_events = events.loc[events["engine"] == ENGINE_OPTIMIZER]
    rows: list[dict] = []
    for block, block_scope in optimizer_events.groupby("block", sort=False, observed=True):
        n_events = len(block_scope)
        model_present = block_scope["selection_evaluable"].astype(bool)
        classification_present = block_scope["optimizer_classification"].notna()
        pair_assignable = model_present & classification_present
        n_model_present = int(model_present.sum())
        n_classification_present = int(classification_present.sum())
        n_pair_assignable = int(pair_assignable.sum())
        rows.append({
            "block": block,
            "n_optimizer_events": n_events,
            "n_model_present": n_model_present,
            "n_model_missing": n_events - n_model_present,
            "n_classification_present": n_classification_present,
            "n_classification_missing": n_events - n_classification_present,
            "classification_assignment_rate": (
                n_classification_present / n_events if n_events else np.nan
            ),
            "n_pair_assignable": n_pair_assignable,
            "pair_assignment_rate": n_pair_assignable / n_events if n_events else np.nan,
        })
    table = pd.DataFrame(rows, columns=OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS)
    return OptimizerClassificationCoverage(_deterministic_table_order(
        table,
        OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
        ("block",),
    ))


def _build_optimizer_family_table(events: pd.DataFrame) -> pd.DataFrame:
    selection_events = events.loc[
        (events["engine"] == ENGINE_OPTIMIZER)
        & events["selection_evaluable"]
    ]
    rows: list[dict] = []
    for block, block_scope in selection_events.groupby("block", sort=False, observed=True):
        scope_rows = _conditioned_rows_for_scope(
            block_scope,
            engine=ENGINE_OPTIMIZER,
            block=block,
            dimension_columns=("family",),
        )
        rows.extend({"block": block, **row} for row in scope_rows)
    return _deterministic_table_order(
        pd.DataFrame(rows, columns=FAMILY_TABLE_COLUMNS),
        FAMILY_TABLE_COLUMNS,
        ("block", "family"),
    )


def _optimizer_pair_assignable_events(events: pd.DataFrame) -> pd.DataFrame:
    return events.loc[
        (events["engine"] == ENGINE_OPTIMIZER)
        & events["selection_evaluable"]
        & events["optimizer_classification"].notna()
    ]


def _build_optimizer_classification_model_table(events: pd.DataFrame) -> pd.DataFrame:
    pair_events = _optimizer_pair_assignable_events(events)
    rows: list[dict] = []
    for block, block_scope in pair_events.groupby("block", sort=False, observed=True):
        scope_rows = _conditioned_rows_for_scope(
            block_scope,
            engine=ENGINE_OPTIMIZER,
            block=block,
            dimension_columns=("optimizer_classification", "model_name"),
        )
        rows.extend({"block": block, **row} for row in scope_rows)
    return _deterministic_table_order(
        pd.DataFrame(rows, columns=CLASSIFICATION_MODEL_TABLE_COLUMNS),
        CLASSIFICATION_MODEL_TABLE_COLUMNS,
        ("block", "optimizer_classification", "model_name"),
    )


def _build_optimizer_classification_family_table(events: pd.DataFrame) -> pd.DataFrame:
    pair_events = _optimizer_pair_assignable_events(events)
    rows: list[dict] = []
    for block, block_scope in pair_events.groupby("block", sort=False, observed=True):
        scope_rows = _conditioned_rows_for_scope(
            block_scope,
            engine=ENGINE_OPTIMIZER,
            block=block,
            dimension_columns=("optimizer_classification", "family"),
        )
        rows.extend({"block": block, **row} for row in scope_rows)
    return _deterministic_table_order(
        pd.DataFrame(rows, columns=CLASSIFICATION_FAMILY_TABLE_COLUMNS),
        CLASSIFICATION_FAMILY_TABLE_COLUMNS,
        ("block", "optimizer_classification", "family"),
    )


def build_optimizer_portfolio_result(events: pd.DataFrame) -> OptimizerPortfolioResult:
    """Build the three explicit 10B.4 Optimizer views and classification coverage."""
    return OptimizerPortfolioResult(
        family_tables=_build_optimizer_family_table(events),
        classification_model_tables=_build_optimizer_classification_model_table(events),
        classification_family_tables=_build_optimizer_classification_family_table(events),
        classification_coverage=build_optimizer_classification_coverage(events),
    )


def build_portfolio_analysis(
    df: pd.DataFrame,
    candidate_mask: pd.Series,
    block_metrics_masks: Mapping[str, pd.Series],
) -> PortfolioAnalysisResult:
    """Build the available Phase 10B.2-10B.4 result for one valid client source."""
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

    events_df = enrich_optimizer_family_events(pd.concat(frames, ignore_index=True))
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
        model_tables=build_portfolio_model_result(events_df),
        optimizer=build_optimizer_portfolio_result(events_df),
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
        model_tables=build_portfolio_model_result(events_df),
        optimizer=build_optimizer_portfolio_result(events_df),
    )
