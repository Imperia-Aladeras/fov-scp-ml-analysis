"""
Motor generico de Pareto de impacto absoluto: agnostico de si las filas de
entrada representan series o clientes (ver docs/analysis_requirements.md,
seccion "Rankings por cliente" / "Perspectiva 4: impacto absoluto", y el
plan de diseno acordado para esta mejora analitica).

Separa siempre mejora (ABS_ERROR_REDUCTION > 0) de deterioro
(ABS_ERROR_REDUCTION < 0, trabajando con magnitud absoluta) en dos grupos
independientes, cada uno con su propio denominador de contribucion (nunca se
mezclan signos en un mismo porcentaje, igual que ya hace
src.metrics.client_contribution_to_total_reduction en
src.global_analysis._client_reduction_and_deterioration_tables). Filas con
ABS_ERROR_REDUCTION == 0 no pertenecen a ningun grupo. Filas con
ABS_ERROR_REDUCTION NaN pertenecen conceptualmente a la poblacion pero no
participan en ordenacion/contribucion/acumulado: se cuentan en
n_no_evaluables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.metrics import client_contribution_to_total_reduction

PARETO_THRESHOLDS: tuple[float, ...] = (50.0, 80.0, 90.0)


@dataclass
class ParetoGroupSummary:
    n_total: int
    n_for_50: int | None
    n_for_80: int | None
    n_for_90: int | None
    total_impact: float


@dataclass
class ParetoGroup:
    table: pd.DataFrame
    summary: ParetoGroupSummary


@dataclass
class ParetoAnalysis:
    improvement: ParetoGroup
    deterioration: ParetoGroup
    n_no_evaluables: int


def _validate_columns(df: pd.DataFrame, value_col: str, id_cols: list[str], tie_break_cols: list[str]) -> None:
    """
    Fail-fast: `value_col`, cada `id_cols` y cada `tie_break_cols` deben
    existir literalmente en `df`. En particular, a nivel global ID_CLIENT +
    ID_CONFIGURATION son parte del contrato de identidad (nunca se asume
    ID_CONFIGURATION unico globalmente): una columna de identidad ausente no
    se descarta en silencio, invalida la llamada.
    """
    missing = [c for c in (value_col, *id_cols, *tie_break_cols) if c not in df.columns]
    if missing:
        raise ValueError(
            f"build_pareto_analysis: columnas declaradas ausentes del DataFrame de entrada: {missing}. "
            "value_col, id_cols y tie_break_cols deben existir todas en df; no se descartan silenciosamente."
        )


def _n_for_thresholds(cumulative_pct: pd.Series) -> dict[float, int | None]:
    """
    Primer RANK (1-indexado) cuyo CUMULATIVE_PCT alcanza cada umbral fijo de
    PARETO_THRESHOLDS. Una tolerancia pequena absorbe el redondeo de punto
    flotante del cumsum (el ultimo valor puede quedar en 99.999999999... en
    vez de 100.0 exacto).
    """
    values = cumulative_pct.to_numpy()
    result: dict[float, int | None] = {}
    for threshold in PARETO_THRESHOLDS:
        hits = np.flatnonzero(values >= threshold - 1e-9)
        result[threshold] = int(hits[0]) + 1 if hits.size else None
    return result


def _build_group(
    sub: pd.DataFrame,
    value_col: str,
    id_cols: list[str],
    tie_break_cols: list[str],
    magnitude: pd.Series,
) -> ParetoGroup:
    ordered_cols = ["RANK", *id_cols, value_col, "PCT_OF_GROUP", "CUMULATIVE_PCT"]

    if sub.empty:
        table = pd.DataFrame(columns=ordered_cols)
        summary = ParetoGroupSummary(n_total=0, n_for_50=None, n_for_80=None, n_for_90=None, total_impact=0.0)
        return ParetoGroup(table=table, summary=summary)

    work = sub.copy()
    work["_MAGNITUDE"] = magnitude
    sort_cols = ["_MAGNITUDE", *tie_break_cols]
    ascending = [False, *([True] * len(tie_break_cols))]
    work = work.sort_values(sort_cols, ascending=ascending, kind="mergesort").reset_index(drop=True)

    total_impact = float(work["_MAGNITUDE"].sum())
    work["PCT_OF_GROUP"] = client_contribution_to_total_reduction(work["_MAGNITUDE"])
    work["CUMULATIVE_PCT"] = work["PCT_OF_GROUP"].cumsum()
    work["RANK"] = np.arange(1, len(work) + 1)

    n_for = _n_for_thresholds(work["CUMULATIVE_PCT"])

    summary = ParetoGroupSummary(
        n_total=len(work),
        n_for_50=n_for.get(50.0),
        n_for_80=n_for.get(80.0),
        n_for_90=n_for.get(90.0),
        total_impact=total_impact,
    )
    return ParetoGroup(table=work[ordered_cols], summary=summary)


def build_pareto_analysis(
    df: pd.DataFrame,
    value_col: str,
    id_cols: list[str],
    tie_break_cols: list[str],
) -> ParetoAnalysis:
    """
    `df` debe llegar ya filtrado a la poblacion comparable correcta (esto lo
    decide el llamador, no esta funcion). `value_col` es ABS_ERROR_REDUCTION
    (con signo, puede tener NaN). `id_cols` son las columnas de identidad y
    contexto a conservar en la tabla resultado. `tie_break_cols` es el orden
    de desempate ASC aplicado tras ordenar por magnitud DESC. Los umbrales de
    concentracion son fijos (PARETO_THRESHOLDS, 50/80/90) y no configurables:
    ParetoGroupSummary modela exactamente esos tres campos, asi que no se
    expone un parametro que aparente soportar otros umbrales.

    Lanza ValueError (fail-fast, sin fallback silencioso) si `value_col`,
    cualquier `id_cols` o cualquier `tie_break_cols` no existe en `df`.
    """
    _validate_columns(df, value_col, id_cols, tie_break_cols)

    values = df[value_col]
    not_evaluable = values.isna()
    n_no_evaluables = int(not_evaluable.sum())

    evaluable = df.loc[~not_evaluable]
    evaluable_values = values.loc[~not_evaluable]
    positive_mask = evaluable_values > 0
    negative_mask = evaluable_values < 0

    improvement = _build_group(
        evaluable.loc[positive_mask], value_col, id_cols, tie_break_cols,
        magnitude=evaluable_values.loc[positive_mask],
    )
    deterioration = _build_group(
        evaluable.loc[negative_mask], value_col, id_cols, tie_break_cols,
        magnitude=evaluable_values.loc[negative_mask].abs(),
    )

    return ParetoAnalysis(improvement=improvement, deterioration=deterioration, n_no_evaluables=n_no_evaluables)
