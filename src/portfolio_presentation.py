"""Pure presentation contract for the block-specific Phase 10B portfolio.

This module is deliberately independent from Jinja, openpyxl, matplotlib and
the report writers.  It translates already-calculated values, declares the
exact presentation schema of every 10B table and prepares deterministic deep
copies for later output surfaces.  It never recalculates portfolio analytics
and never reads or falls back to legacy six-month model/classification fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from src.models import MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    CLASSIFICATION_FAMILY_TABLE_COLUMNS,
    CLASSIFICATION_MISSING,
    CLASSIFICATION_MODEL_TABLE_COLUMNS,
    CLASSIFICATION_NOT_APPLICABLE,
    CLASSIFICATION_PRESENT,
    COVERAGE_COLUMNS,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    FAMILY_MAPPING_MAPPED,
    FAMILY_MAPPING_NOT_APPLICABLE,
    FAMILY_MAPPING_NOT_EVALUABLE,
    FAMILY_MAPPING_UNMAPPED,
    FAMILY_TABLE_COLUMNS,
    FAMILY_UNMAPPED,
    MODEL_METADATA_MISSING,
    MODEL_METADATA_PRESENT,
    MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS,
    MODEL_TABLE_COLUMNS,
    OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
    STABILITY_PERFORMANCE_COLUMNS,
    STABILITY_STATE_CHANGED,
    STABILITY_STATE_NOT_EVALUABLE,
    STABILITY_STATE_STABLE,
    STABILITY_SUMMARY_COLUMNS,
    STABILITY_TYPE_CLASSIFICATION,
    STABILITY_TYPE_MODEL,
    TRANSITION_COLUMNS,
    PortfolioAnalysisResult,
)


NA_TEXT = "N/D"

ENGINE_LABELS: Mapping[str, str] = MappingProxyType({
    ENGINE_SCP_AUTO: "SCP Classic Auto",
    ENGINE_OPTIMIZER: "SCP Classic Optimizer",
})

BLOCK_LABELS: Mapping[str, str] = MappingProxyType({
    BLOCK_OLDER_3M: "3 meses anteriores (M6–M4)",
    BLOCK_RECENT_3M: "3 meses recientes (M3–M1)",
})

STABILITY_STATE_LABELS: Mapping[str, str] = MappingProxyType({
    STABILITY_STATE_STABLE: "Estable",
    STABILITY_STATE_CHANGED: "Cambió",
    STABILITY_STATE_NOT_EVALUABLE: "No evaluable",
})

STABILITY_TYPE_LABELS: Mapping[str, str] = MappingProxyType({
    STABILITY_TYPE_MODEL: "Modelo",
    STABILITY_TYPE_CLASSIFICATION: "Clasificación del Optimizer",
})

FAMILY_LABELS: Mapping[str, str] = MappingProxyType({
    "baselines": "Modelos base",
    "classical": "Modelos clásicos",
    "intermittent": "Demanda intermitente",
    "ml": "Aprendizaje automático",
    FAMILY_UNMAPPED: "Sin familia mapeada",
})

PORTFOLIO_CONDITIONED_PERFORMANCE_NOTE = (
    "Los resultados describen la performance observada en las series donde el modelo o familia "
    "fue seleccionado. No constituyen un ranking universal de modelos, una comparación causal "
    "sobre una población experimental común ni una recomendación de routing. La clasificación "
    "del Optimizer tampoco determina un «mejor modelo»."
)

PORTFOLIO_UNAVAILABLE_NOTE = (
    "Análisis de selección por bloques no disponible. Este dataset no contiene la metadata "
    "específica de modelo y clasificación para los períodos anterior y reciente requerida por "
    "este análisis. El resto del informe sigue siendo válido; esta situación no implica un error "
    "del pipeline."
)

PORTFOLIO_AVAILABLE_EMPTY_NOTE = (
    "El análisis de selección por bloques está disponible, pero no se observaron asignaciones de "
    "modelo en los períodos anterior o reciente."
)

PORTFOLIO_AVAILABLE_NOTE = "Análisis de selección por bloques disponible."

PORTFOLIO_SMALL_SAMPLE_NOTE = (
    "Una muestra reducida limita la fuerza de la lectura, pero no invalida automáticamente el "
    "resultado."
)


class PortfolioPresentationContractError(ValueError):
    """Raised when a 10B object contradicts the declared presentation contract."""


class PortfolioValueKind(str, Enum):
    """Explicit display semantics; no column-name heuristics are used."""

    TEXT = "TEXT"
    IDENTIFIER = "IDENTIFIER"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    ABSOLUTE_NUMBER = "ABSOLUTE_NUMBER"
    RATIO_PERCENT = "RATIO_PERCENT"
    SIGNED_RATIO_PERCENT = "SIGNED_RATIO_PERCENT"
    SIGNED_SCALED_PERCENT = "SIGNED_SCALED_PERCENT"


@dataclass(frozen=True)
class PortfolioColumnPresentation:
    visible_label: str
    value_kind: PortfolioValueKind


# Every column exposed by a 10B presentation schema has an explicit type and
# end-user label.  This intentionally does not infer semantics from suffixes
# such as _rate, _pct, n_* or *_count.
COLUMN_PRESENTATIONS: Mapping[str, PortfolioColumnPresentation] = MappingProxyType({
    "ID_BATCH": PortfolioColumnPresentation("ID batch", PortfolioValueKind.IDENTIFIER),
    "ID_RUN_STAGING": PortfolioColumnPresentation("ID run staging", PortfolioValueKind.IDENTIFIER),
    "ID_CLIENT": PortfolioColumnPresentation("ID cliente", PortfolioValueKind.IDENTIFIER),
    "SOURCE_RUN_ID": PortfolioColumnPresentation("ID ejecución de origen", PortfolioValueKind.IDENTIFIER),
    "ID_CONFIGURATION": PortfolioColumnPresentation("ID configuración", PortfolioValueKind.IDENTIFIER),
    "source_series_key": PortfolioColumnPresentation("Clave canónica de serie", PortfolioValueKind.IDENTIFIER),
    "RUN_START_DATE": PortfolioColumnPresentation("Fecha de inicio de ejecución", PortfolioValueKind.DATETIME),
    "engine": PortfolioColumnPresentation("Motor analizado", PortfolioValueKind.TEXT),
    "block": PortfolioColumnPresentation("Período", PortfolioValueKind.TEXT),
    "model_name": PortfolioColumnPresentation("Modelo observado", PortfolioValueKind.TEXT),
    "model_metadata_status": PortfolioColumnPresentation("Estado de metadata de modelo", PortfolioValueKind.TEXT),
    "optimizer_classification": PortfolioColumnPresentation("Clasificación del Optimizer", PortfolioValueKind.TEXT),
    "classification_metadata_status": PortfolioColumnPresentation(
        "Estado de metadata de clasificación del Optimizer", PortfolioValueKind.TEXT,
    ),
    "selection_evaluable": PortfolioColumnPresentation("Asignación de modelo evaluable", PortfolioValueKind.BOOLEAN),
    "block_metrics_evaluable": PortfolioColumnPresentation("Métricas del período evaluables", PortfolioValueKind.BOOLEAN),
    "performance_evaluable": PortfolioColumnPresentation("Performance evaluable", PortfolioValueKind.BOOLEAN),
    "total_history": PortfolioColumnPresentation("Volumen histórico", PortfolioValueKind.ABSOLUTE_NUMBER),
    "scp_total_abs_error": PortfolioColumnPresentation(
        "Error absoluto — SCP Classic Auto", PortfolioValueKind.ABSOLUTE_NUMBER,
    ),
    "optimizer_total_abs_error": PortfolioColumnPresentation(
        "Error absoluto — SCP Classic Optimizer", PortfolioValueKind.ABSOLUTE_NUMBER,
    ),
    "scp_total_signed_error": PortfolioColumnPresentation(
        "Error firmado — SCP Classic Auto", PortfolioValueKind.ABSOLUTE_NUMBER,
    ),
    "optimizer_total_signed_error": PortfolioColumnPresentation(
        "Error firmado — SCP Classic Optimizer", PortfolioValueKind.ABSOLUTE_NUMBER,
    ),
    "scp_wape": PortfolioColumnPresentation("WAPE — SCP Classic Auto", PortfolioValueKind.RATIO_PERCENT),
    "optimizer_wape": PortfolioColumnPresentation(
        "WAPE — SCP Classic Optimizer", PortfolioValueKind.RATIO_PERCENT,
    ),
    "scp_bias": PortfolioColumnPresentation("Bias — SCP Classic Auto", PortfolioValueKind.SIGNED_RATIO_PERCENT),
    "optimizer_bias": PortfolioColumnPresentation(
        "Bias — SCP Classic Optimizer", PortfolioValueKind.SIGNED_RATIO_PERCENT,
    ),
    "winner_method": PortfolioColumnPresentation("Motor ganador observado", PortfolioValueKind.TEXT),
    "optimizer_improvement_vs_scp": PortfolioColumnPresentation(
        "Mejora de WAPE — SCP Classic Optimizer frente a SCP Classic Auto",
        PortfolioValueKind.SIGNED_SCALED_PERCENT,
    ),
    "optimizer_abs_error_reduction_vs_scp": PortfolioColumnPresentation(
        "Reducción absoluta de error — SCP Classic Optimizer frente a SCP Classic Auto",
        PortfolioValueKind.ABSOLUTE_NUMBER,
    ),
    "family": PortfolioColumnPresentation("Familia del modelo Optimizer", PortfolioValueKind.TEXT),
    "family_mapping_status": PortfolioColumnPresentation("Estado del mapeo de familia", PortfolioValueKind.TEXT),
    "n_base_series": PortfolioColumnPresentation("Series base", PortfolioValueKind.INTEGER),
    "n_structural_events": PortfolioColumnPresentation("Eventos estructurales", PortfolioValueKind.INTEGER),
    "n_model_present": PortfolioColumnPresentation("Modelos informados", PortfolioValueKind.INTEGER),
    "n_model_missing": PortfolioColumnPresentation("Modelos con metadata ausente", PortfolioValueKind.INTEGER),
    "selection_assignment_rate": PortfolioColumnPresentation(
        "Cobertura de asignación de modelo", PortfolioValueKind.RATIO_PERCENT,
    ),
    "n_block_metrics_evaluable": PortfolioColumnPresentation(
        "Series con métricas del período evaluables", PortfolioValueKind.INTEGER,
    ),
    "n_performance_evaluable": PortfolioColumnPresentation(
        "Series con modelo y performance evaluables", PortfolioValueKind.INTEGER,
    ),
    "selection_count": PortfolioColumnPresentation("Selecciones observadas", PortfolioValueKind.INTEGER),
    "selection_assignable_count": PortfolioColumnPresentation(
        "Asignaciones de modelo posibles", PortfolioValueKind.INTEGER,
    ),
    "selection_share_of_assignable": PortfolioColumnPresentation(
        "Cuota de selección sobre asignaciones posibles", PortfolioValueKind.RATIO_PERCENT,
    ),
    "n_performance": PortfolioColumnPresentation("Series con performance evaluable", PortfolioValueKind.INTEGER),
    "n_clients": PortfolioColumnPresentation("Clientes con performance evaluable", PortfolioValueKind.INTEGER),
    "small_sample": PortfolioColumnPresentation("Muestra reducida", PortfolioValueKind.BOOLEAN),
    "historical_volume": PortfolioColumnPresentation("Volumen histórico", PortfolioValueKind.ABSOLUTE_NUMBER),
    "volume_share": PortfolioColumnPresentation(
        "Cuota de volumen histórico evaluable", PortfolioValueKind.RATIO_PERCENT,
    ),
    "selected_engine_win_count": PortfolioColumnPresentation(
        "Victorias del motor analizado", PortfolioValueKind.INTEGER,
    ),
    "tie_count": PortfolioColumnPresentation("Empates", PortfolioValueKind.INTEGER),
    "selected_engine_win_rate": PortfolioColumnPresentation(
        "Tasa de victoria del motor analizado", PortfolioValueKind.RATIO_PERCENT,
    ),
    "optimizer_median_improvement_vs_scp": PortfolioColumnPresentation(
        "Mejora mediana — SCP Classic Optimizer frente a SCP Classic Auto",
        PortfolioValueKind.SIGNED_SCALED_PERCENT,
    ),
    "n_optimizer_events": PortfolioColumnPresentation("Eventos SCP Classic Optimizer", PortfolioValueKind.INTEGER),
    "n_classification_present": PortfolioColumnPresentation(
        "Clasificaciones del Optimizer informadas", PortfolioValueKind.INTEGER,
    ),
    "n_classification_missing": PortfolioColumnPresentation(
        "Clasificaciones del Optimizer con metadata ausente", PortfolioValueKind.INTEGER,
    ),
    "classification_assignment_rate": PortfolioColumnPresentation(
        "Cobertura de clasificación del Optimizer", PortfolioValueKind.RATIO_PERCENT,
    ),
    "n_pair_assignable": PortfolioColumnPresentation(
        "Pares clasificación–modelo asignables", PortfolioValueKind.INTEGER,
    ),
    "pair_assignment_rate": PortfolioColumnPresentation(
        "Cobertura de pares clasificación–modelo", PortfolioValueKind.RATIO_PERCENT,
    ),
    "n_evaluable": PortfolioColumnPresentation("Parejas evaluables", PortfolioValueKind.INTEGER),
    "stable_count": PortfolioColumnPresentation("Parejas estables", PortfolioValueKind.INTEGER),
    "changed_count": PortfolioColumnPresentation("Parejas que cambiaron", PortfolioValueKind.INTEGER),
    "not_evaluable_count": PortfolioColumnPresentation("Parejas no evaluables", PortfolioValueKind.INTEGER),
    "stability_rate": PortfolioColumnPresentation("Tasa de estabilidad", PortfolioValueKind.RATIO_PERCENT),
    "older_value": PortfolioColumnPresentation("Valor en 3 meses anteriores (M6–M4)", PortfolioValueKind.TEXT),
    "recent_value": PortfolioColumnPresentation("Valor en 3 meses recientes (M3–M1)", PortfolioValueKind.TEXT),
    "transition_count": PortfolioColumnPresentation("Transiciones observadas", PortfolioValueKind.INTEGER),
    "transition_share_of_evaluable": PortfolioColumnPresentation(
        "Cuota sobre transiciones evaluables", PortfolioValueKind.RATIO_PERCENT,
    ),
    "stability_type": PortfolioColumnPresentation("Dimensión de estabilidad", PortfolioValueKind.TEXT),
    "stability_state": PortfolioColumnPresentation("Estado de estabilidad", PortfolioValueKind.TEXT),
})


CANONICAL_EVENT_COLUMNS: tuple[str, ...] = (
    "ID_BATCH",
    "ID_RUN_STAGING",
    "ID_CLIENT",
    "SOURCE_RUN_ID",
    "ID_CONFIGURATION",
    "source_series_key",
    "RUN_START_DATE",
    "engine",
    "block",
    "model_name",
    "model_metadata_status",
    "optimizer_classification",
    "classification_metadata_status",
    "selection_evaluable",
    "block_metrics_evaluable",
    "performance_evaluable",
    "total_history",
    "scp_total_abs_error",
    "optimizer_total_abs_error",
    "scp_total_signed_error",
    "optimizer_total_signed_error",
    "scp_wape",
    "optimizer_wape",
    "scp_bias",
    "optimizer_bias",
    "winner_method",
    "optimizer_improvement_vs_scp",
    "optimizer_abs_error_reduction_vs_scp",
    "family",
    "family_mapping_status",
)


@dataclass(frozen=True)
class PortfolioTableSchema:
    key: str
    visible_name: str
    columns: tuple[str, ...]
    sort_columns: tuple[str, ...]
    technical_audit_surface: bool = False

    def __post_init__(self) -> None:
        if len(self.columns) != len(set(self.columns)):
            raise PortfolioPresentationContractError(
                f"Portfolio presentation schema {self.key!r} contains duplicate columns."
            )
        missing_specs = [column for column in self.columns if column not in COLUMN_PRESENTATIONS]
        if missing_specs:
            raise PortfolioPresentationContractError(
                f"Portfolio presentation schema {self.key!r} has columns without display types: "
                + ", ".join(missing_specs)
            )
        invalid_sort = [column for column in self.sort_columns if column not in self.columns]
        if invalid_sort:
            raise PortfolioPresentationContractError(
                f"Portfolio presentation schema {self.key!r} sorts unknown columns: "
                + ", ".join(invalid_sort)
            )


SCHEMA_COVERAGE = "coverage"
SCHEMA_MODELS = "models"
SCHEMA_FAMILIES = "families"
SCHEMA_CLASSIFICATION_COVERAGE = "classification_coverage"
SCHEMA_CLASSIFICATION_MODEL = "classification_model"
SCHEMA_CLASSIFICATION_FAMILY = "classification_family"
SCHEMA_MODEL_STABILITY_SUMMARY = "model_stability_summary"
SCHEMA_STABILITY_BY_OLDER_MODEL = "stability_by_older_model"
SCHEMA_MODEL_TRANSITIONS = "model_transitions"
SCHEMA_CLASSIFICATION_STABILITY = "classification_stability"
SCHEMA_CLASSIFICATION_TRANSITIONS = "classification_transitions"
SCHEMA_PERFORMANCE_BY_STABILITY = "performance_by_stability"
SCHEMA_CANONICAL_EVENTS = "canonical_events"


PORTFOLIO_TABLE_SCHEMAS: Mapping[str, PortfolioTableSchema] = MappingProxyType({
    SCHEMA_COVERAGE: PortfolioTableSchema(
        SCHEMA_COVERAGE,
        "Cobertura de selección por motor y período",
        COVERAGE_COLUMNS,
        ("engine", "block"),
    ),
    SCHEMA_MODELS: PortfolioTableSchema(
        SCHEMA_MODELS,
        "Selección y performance observada por modelo",
        MODEL_TABLE_COLUMNS,
        ("engine", "block", "model_name"),
    ),
    SCHEMA_FAMILIES: PortfolioTableSchema(
        SCHEMA_FAMILIES,
        "Selección y performance observada por familia del Optimizer",
        FAMILY_TABLE_COLUMNS,
        ("block", "family"),
    ),
    SCHEMA_CLASSIFICATION_COVERAGE: PortfolioTableSchema(
        SCHEMA_CLASSIFICATION_COVERAGE,
        "Cobertura de clasificación del Optimizer",
        OPTIMIZER_CLASSIFICATION_COVERAGE_COLUMNS,
        ("block",),
    ),
    SCHEMA_CLASSIFICATION_MODEL: PortfolioTableSchema(
        SCHEMA_CLASSIFICATION_MODEL,
        "Clasificación del Optimizer × modelo observado",
        CLASSIFICATION_MODEL_TABLE_COLUMNS,
        ("block", "optimizer_classification", "model_name"),
    ),
    SCHEMA_CLASSIFICATION_FAMILY: PortfolioTableSchema(
        SCHEMA_CLASSIFICATION_FAMILY,
        "Clasificación del Optimizer × familia del modelo",
        CLASSIFICATION_FAMILY_TABLE_COLUMNS,
        ("block", "optimizer_classification", "family"),
    ),
    SCHEMA_MODEL_STABILITY_SUMMARY: PortfolioTableSchema(
        SCHEMA_MODEL_STABILITY_SUMMARY,
        "Estabilidad global de modelos",
        STABILITY_SUMMARY_COLUMNS,
        ("engine",),
    ),
    SCHEMA_STABILITY_BY_OLDER_MODEL: PortfolioTableSchema(
        SCHEMA_STABILITY_BY_OLDER_MODEL,
        "Estabilidad por modelo observado en los 3 meses anteriores",
        MODEL_STABILITY_BY_OLDER_MODEL_COLUMNS,
        ("engine", "model_name"),
    ),
    SCHEMA_MODEL_TRANSITIONS: PortfolioTableSchema(
        SCHEMA_MODEL_TRANSITIONS,
        "Transiciones de modelo",
        TRANSITION_COLUMNS,
        ("engine", "older_value", "recent_value"),
    ),
    SCHEMA_CLASSIFICATION_STABILITY: PortfolioTableSchema(
        SCHEMA_CLASSIFICATION_STABILITY,
        "Estabilidad de la clasificación del Optimizer",
        STABILITY_SUMMARY_COLUMNS,
        ("engine",),
    ),
    SCHEMA_CLASSIFICATION_TRANSITIONS: PortfolioTableSchema(
        SCHEMA_CLASSIFICATION_TRANSITIONS,
        "Transiciones de clasificación del Optimizer",
        TRANSITION_COLUMNS,
        ("engine", "older_value", "recent_value"),
    ),
    SCHEMA_PERFORMANCE_BY_STABILITY: PortfolioTableSchema(
        SCHEMA_PERFORMANCE_BY_STABILITY,
        "Performance descriptiva por estabilidad",
        STABILITY_PERFORMANCE_COLUMNS,
        ("stability_type", "engine", "block", "stability_state"),
    ),
    SCHEMA_CANONICAL_EVENTS: PortfolioTableSchema(
        SCHEMA_CANONICAL_EVENTS,
        "Eventos canónicos auditables de selección por bloques",
        CANONICAL_EVENT_COLUMNS,
        ("engine", "block", "source_series_key"),
        technical_audit_surface=True,
    ),
})


class PortfolioPresentationState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE_EMPTY = "AVAILABLE_EMPTY"
    AVAILABLE_WITH_CONTENT = "AVAILABLE_WITH_CONTENT"


@dataclass(frozen=True)
class PortfolioPresentationAvailability:
    state: PortfolioPresentationState
    available: bool
    has_assignments: bool
    message: str
    missing_required_columns: tuple[str, ...] = ()


class PortfolioSampleState(str, Enum):
    NO_PERFORMANCE = "NO_PERFORMANCE"
    SMALL_SAMPLE = "SMALL_SAMPLE"
    NO_WARNING = "NO_WARNING"


@dataclass(frozen=True)
class PortfolioSamplePresentation:
    state: PortfolioSampleState
    label: str | None
    warning: bool


@dataclass(frozen=True)
class PreparedPortfolioTable:
    schema: PortfolioTableSchema
    dataframe: pd.DataFrame

    def visible_dataframe(self) -> pd.DataFrame:
        """Return another copy with end-user column names and native values."""
        labels = {
            column: COLUMN_PRESENTATIONS[column].visible_label
            for column in self.schema.columns
        }
        return self.dataframe.rename(columns=labels).copy(deep=True)


@dataclass(frozen=True)
class PortfolioPresentationResult:
    availability: PortfolioPresentationAvailability
    tables: Mapping[str, PreparedPortfolioTable]
    methodology_note: str = PORTFOLIO_CONDITIONED_PERFORMANCE_NOTE
    small_sample_note: str = PORTFOLIO_SMALL_SAMPLE_NOTE


_MODEL_METADATA_LABELS = {
    MODEL_METADATA_PRESENT: "Metadata presente",
    MODEL_METADATA_MISSING: "Metadata ausente",
}

_CLASSIFICATION_METADATA_LABELS = {
    CLASSIFICATION_PRESENT: "Metadata presente",
    CLASSIFICATION_MISSING: "Metadata ausente",
    CLASSIFICATION_NOT_APPLICABLE: "No aplica",
}

_FAMILY_MAPPING_LABELS = {
    FAMILY_MAPPING_MAPPED: "Familia mapeada",
    FAMILY_MAPPING_UNMAPPED: "Modelo presente sin familia mapeada",
    FAMILY_MAPPING_NOT_EVALUABLE: "Modelo ausente; familia no evaluable",
    FAMILY_MAPPING_NOT_APPLICABLE: "No aplica",
}

_WINNER_LABELS = {
    "SCP": ENGINE_LABELS[ENGINE_SCP_AUTO],
    "ML": ENGINE_LABELS[ENGINE_OPTIMIZER],
    "TIE": "Empate",
}

_VALUE_LABELS_BY_COLUMN: Mapping[str, Mapping[object, str]] = MappingProxyType({
    "engine": ENGINE_LABELS,
    "block": BLOCK_LABELS,
    "stability_type": STABILITY_TYPE_LABELS,
    "stability_state": STABILITY_STATE_LABELS,
    "family": FAMILY_LABELS,
    "model_metadata_status": MappingProxyType(_MODEL_METADATA_LABELS),
    "classification_metadata_status": MappingProxyType(_CLASSIFICATION_METADATA_LABELS),
    "family_mapping_status": MappingProxyType(_FAMILY_MAPPING_LABELS),
    "winner_method": MappingProxyType(_WINNER_LABELS),
})

_FIXED_SORT_ORDERS: Mapping[str, Mapping[object, int]] = MappingProxyType({
    "engine": MappingProxyType({ENGINE_SCP_AUTO: 0, ENGINE_OPTIMIZER: 1}),
    "block": MappingProxyType({BLOCK_OLDER_3M: 0, BLOCK_RECENT_3M: 1}),
    "stability_type": MappingProxyType({
        STABILITY_TYPE_MODEL: 0,
        STABILITY_TYPE_CLASSIFICATION: 1,
    }),
    "stability_state": MappingProxyType({
        STABILITY_STATE_STABLE: 0,
        STABILITY_STATE_CHANGED: 1,
        STABILITY_STATE_NOT_EVALUABLE: 2,
    }),
})


def engine_label(engine: str) -> str:
    return ENGINE_LABELS.get(engine, str(engine))


def block_label(block: str) -> str:
    return BLOCK_LABELS.get(block, str(block))


def stability_state_label(state: str) -> str:
    return STABILITY_STATE_LABELS.get(state, str(state))


def family_label(family: object) -> object:
    if _is_missing(family):
        return family
    return FAMILY_LABELS.get(family, family)


def visible_column_label(column: str, *, engine: str | None = None) -> str:
    """Return the declared label, optionally specializing engine-dependent wins."""
    if column not in COLUMN_PRESENTATIONS:
        raise KeyError(f"Unknown portfolio presentation column: {column}")
    if engine is not None and column == "selected_engine_win_rate":
        return f"Tasa de victoria — {engine_label(engine)}"
    if engine is not None and column == "selected_engine_win_count":
        return f"Victorias — {engine_label(engine)}"
    return COLUMN_PRESENTATIONS[column].visible_label


def portfolio_presentation_availability(
    portfolio: PortfolioAnalysisResult,
) -> PortfolioPresentationAvailability:
    """Classify unavailable, available-empty and available-with-content states."""
    if not portfolio.availability.available:
        return PortfolioPresentationAvailability(
            state=PortfolioPresentationState.UNAVAILABLE,
            available=False,
            has_assignments=False,
            message=PORTFOLIO_UNAVAILABLE_NOTE,
            missing_required_columns=tuple(
                portfolio.availability.missing_required_columns
            ),
        )

    if portfolio.model_tables is None:
        raise PortfolioPresentationContractError(
            "An available portfolio must contain PortfolioModelResult."
        )
    has_assignments = not portfolio.model_tables.by_engine_block_model.empty
    if not has_assignments:
        return PortfolioPresentationAvailability(
            state=PortfolioPresentationState.AVAILABLE_EMPTY,
            available=True,
            has_assignments=False,
            message=PORTFOLIO_AVAILABLE_EMPTY_NOTE,
        )
    return PortfolioPresentationAvailability(
        state=PortfolioPresentationState.AVAILABLE_WITH_CONTENT,
        available=True,
        has_assignments=True,
        message=PORTFOLIO_AVAILABLE_NOTE,
    )


def performance_sample_presentation(
    n_performance: int,
    small_sample: bool,
) -> PortfolioSamplePresentation:
    """Validate the core boolean and expose only its approved display semantics."""
    if isinstance(n_performance, bool) or int(n_performance) != n_performance:
        raise PortfolioPresentationContractError("n_performance must be an integer count.")
    n_performance = int(n_performance)
    if n_performance < 0:
        raise PortfolioPresentationContractError("n_performance cannot be negative.")
    if not isinstance(small_sample, (bool, type(pd.NA))) and small_sample not in (0, 1):
        raise PortfolioPresentationContractError("small_sample must be boolean.")
    if small_sample is pd.NA:
        raise PortfolioPresentationContractError("small_sample cannot be missing.")
    small_sample = bool(small_sample)
    expected = n_performance < MIN_SAMPLE_SIZE_FOR_STRONG_CONCLUSION
    if small_sample != expected:
        raise PortfolioPresentationContractError(
            "small_sample is inconsistent with the already-calculated n_performance contract."
        )
    if n_performance == 0:
        return PortfolioSamplePresentation(
            PortfolioSampleState.NO_PERFORMANCE,
            "Sin performance evaluable",
            warning=False,
        )
    if small_sample:
        return PortfolioSamplePresentation(
            PortfolioSampleState.SMALL_SAMPLE,
            "Muestra reducida",
            warning=True,
        )
    return PortfolioSamplePresentation(
        PortfolioSampleState.NO_WARNING,
        None,
        warning=False,
    )


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, Real) and not math.isfinite(float(value)):
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, (bool, type(pd.NA))) else False


def _format_decimal_es(value: float, decimals: int, *, signed: bool = False) -> str:
    sign = "+" if signed else ""
    rendered = f"{float(value):{sign},.{decimals}f}"
    return rendered.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def _format_absolute_es(value: object) -> str:
    rendered = _format_decimal_es(float(value), 1)
    return rendered[:-2] if rendered.endswith(",0") else rendered


def visible_value(column: str, value: object) -> object:
    """Translate only values with an explicit portfolio presentation contract."""
    if _is_missing(value):
        return value
    labels = _VALUE_LABELS_BY_COLUMN.get(column)
    if labels is None:
        return value
    return labels.get(value, value)


def format_portfolio_value(column: str, value: object) -> str:
    """Format one value according to its explicit column declaration."""
    if column not in COLUMN_PRESENTATIONS:
        raise KeyError(f"Unknown portfolio presentation column: {column}")
    if _is_missing(value):
        return NA_TEXT

    value = visible_value(column, value)
    kind = COLUMN_PRESENTATIONS[column].value_kind
    if kind in (PortfolioValueKind.TEXT, PortfolioValueKind.IDENTIFIER):
        return str(value)
    if kind == PortfolioValueKind.DATETIME:
        return pd.Timestamp(value).strftime("%d/%m/%Y %H:%M:%S")
    if kind == PortfolioValueKind.BOOLEAN:
        return "Sí" if bool(value) else "No"
    if kind == PortfolioValueKind.INTEGER:
        numeric = float(value)
        if not numeric.is_integer():
            raise PortfolioPresentationContractError(
                f"Column {column!r} received a non-integer count: {value!r}."
            )
        return f"{int(numeric):,}".replace(",", ".")
    if kind == PortfolioValueKind.ABSOLUTE_NUMBER:
        return _format_absolute_es(value)
    if kind == PortfolioValueKind.RATIO_PERCENT:
        return f"{_format_decimal_es(float(value) * 100, 1)} %"
    if kind == PortfolioValueKind.SIGNED_RATIO_PERCENT:
        return f"{_format_decimal_es(float(value) * 100, 1, signed=True)} %"
    if kind == PortfolioValueKind.SIGNED_SCALED_PERCENT:
        return f"{_format_decimal_es(float(value), 1, signed=True)} %"
    raise PortfolioPresentationContractError(
        f"Unsupported presentation type {kind!r} for column {column!r}."
    )


def _sort_for_presentation(
    dataframe: pd.DataFrame,
    schema: PortfolioTableSchema,
) -> pd.DataFrame:
    if dataframe.empty or not schema.sort_columns:
        return dataframe.reset_index(drop=True)

    ordered = dataframe.copy(deep=True)
    helper_columns: list[str] = []
    for index, column in enumerate(schema.sort_columns):
        helper = f"_portfolio_presentation_sort_{index}"
        helper_columns.append(helper)
        fixed_order = _FIXED_SORT_ORDERS.get(column)
        if fixed_order is not None:
            ordered[helper] = ordered[column].map(fixed_order).fillna(len(fixed_order))
        else:
            ordered[helper] = ordered[column].map(
                lambda value: "" if _is_missing(value) else str(value)
            )
    return (
        ordered.sort_values(helper_columns, kind="stable")
        .drop(columns=helper_columns)
        .reset_index(drop=True)
    )


def prepare_portfolio_table(
    dataframe: pd.DataFrame,
    schema_key: str,
) -> PreparedPortfolioTable:
    """Validate, copy, order and translate one table without changing metrics."""
    try:
        schema = PORTFOLIO_TABLE_SCHEMAS[schema_key]
    except KeyError as exc:
        raise KeyError(f"Unknown portfolio presentation schema: {schema_key}") from exc

    missing_columns = [column for column in schema.columns if column not in dataframe.columns]
    if missing_columns:
        raise PortfolioPresentationContractError(
            f"Table {schema_key!r} is missing required columns: " + ", ".join(missing_columns)
        )

    prepared = _sort_for_presentation(
        dataframe.loc[:, list(schema.columns)].copy(deep=True),
        schema,
    )
    for column, labels in _VALUE_LABELS_BY_COLUMN.items():
        if column in prepared.columns:
            prepared[column] = prepared[column].map(
                lambda value, mapping=labels: (
                    value if _is_missing(value) else mapping.get(value, value)
                )
            )
    return PreparedPortfolioTable(schema=schema, dataframe=prepared)


def _available_source_tables(
    portfolio: PortfolioAnalysisResult,
) -> Mapping[str, pd.DataFrame]:
    required_objects = {
        "events": portfolio.events,
        "coverage": portfolio.coverage,
        "model_tables": portfolio.model_tables,
        "optimizer": portfolio.optimizer,
        "stability": portfolio.stability,
    }
    missing_objects = [name for name, value in required_objects.items() if value is None]
    if missing_objects:
        raise PortfolioPresentationContractError(
            "An available portfolio is missing required result objects: "
            + ", ".join(missing_objects)
        )

    assert portfolio.events is not None
    assert portfolio.coverage is not None
    assert portfolio.model_tables is not None
    assert portfolio.optimizer is not None
    assert portfolio.stability is not None
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


def prepare_portfolio_presentation(
    portfolio: PortfolioAnalysisResult,
) -> PortfolioPresentationResult:
    """Prepare every declared 10B surface solely from ``result.portfolio``."""
    availability = portfolio_presentation_availability(portfolio)
    if not availability.available:
        return PortfolioPresentationResult(
            availability=availability,
            tables=MappingProxyType({}),
        )

    tables = {
        schema_key: prepare_portfolio_table(table, schema_key)
        for schema_key, table in _available_source_tables(portfolio).items()
    }
    return PortfolioPresentationResult(
        availability=availability,
        tables=MappingProxyType(tables),
    )
