"""
Nucleo analitico de Fase 8 (diagnostico por modelo, clasificacion y volumen +
Bias). Este modulo contiene unicamente funciones/dataclasses puras -- operan
sobre `DataFrame`/`pd.Series`/`PeriodColumns`, nunca importan
`ClientAnalysisResult` ni `GlobalAnalysisResult` (evita import circular con
`client_analysis.py`/`global_analysis.py`, ver plan tecnico 8B seccion L).
Las funciones que necesitan conocer `ClientAnalysisResult` (agregacion
global multi-cliente) viven en `src/global_analysis.py`, no aqui.

VOLUME_BUCKET: terciles relativos por cliente sobre TOTAL_HISTORY_6M de la
poblacion COMPARABLE de ese cliente (nunca sobre HAS_BASE_CANDIDATE ni sobre
filas no comparables -- eso lo decide el llamador, no esta funcion). Los
valores nunca son comparables en magnitud absoluta entre clientes distintos.

El cruce SERIES_CLASSIFICATION x VOLUME_BUCKET (`classification_volume_cross_table`)
y los diagnosticos completos (`Phase8ClientDiagnostics`/`Phase8GlobalDiagnostics`)
son unicamente para el semestre completo (6M) y solo el diagnostico
individual se calcula por cliente; el cruce clasificacion x volumen es
exclusivamente global (8D) -- no existe una version individual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.metrics import BiasAggregateResult, bias_aggregate
from src.models import category_performance_table
from src.periods import PeriodColumns

RELATIVE_LOW = "RELATIVE_LOW"
RELATIVE_MEDIUM = "RELATIVE_MEDIUM"
RELATIVE_HIGH = "RELATIVE_HIGH"
NOT_ASSIGNABLE = "NOT_ASSIGNABLE"

REASON_NON_EVALUABLE_HISTORY_VALUES = "NON_EVALUABLE_HISTORY_VALUES"
REASON_N_LT_3 = "N_LT_3"
REASON_DISTINCT_VALUES_LT_3 = "DISTINCT_VALUES_LT_3"
REASON_COLLAPSE_AFTER_TIE_GROUPING = "COLLAPSE_AFTER_TIE_GROUPING"

_GROUP_LABELS = {0: RELATIVE_LOW, 1: RELATIVE_MEDIUM, 2: RELATIVE_HIGH}

# Mismo literal que usa category_performance_table internamente (models.py:56)
# para normalizar categorias nulas. No se importa desde models.py (D4: no se
# toca ese archivo en 8B); la alineacion se garantiza por test canario
# (tests/test_phase8.py), no por una constante compartida en tiempo de
# ejecucion.
MISSING_CATEGORY_LABEL = "(sin clasificar)"

VOLUME_BUCKET_COLUMN = "VOLUME_BUCKET"
MODEL_CATEGORY_COLUMNS = ("ML_BEST_MODEL", "SCP_BEST_MODEL")
CLASSIFICATION_CATEGORY_COLUMNS = ("ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION", "SCP_CLASSIFICATION")


@dataclass
class VolumeBucketResult:
    status: str  # "OK" | "NOT_ASSIGNABLE"
    buckets: pd.Series  # label por fila, alineada al indice de `total_history`
    n_distinct_values: int
    bucket_counts: dict
    reason: str | None  # codigo machine-readable; None si status=="OK"


def _not_assignable(total_history: pd.Series, reason: str, n_distinct_values: int = 0) -> VolumeBucketResult:
    n = len(total_history)
    return VolumeBucketResult(
        status=NOT_ASSIGNABLE,
        buckets=pd.Series(NOT_ASSIGNABLE, index=total_history.index),
        n_distinct_values=n_distinct_values,
        bucket_counts={NOT_ASSIGNABLE: n},
        reason=reason,
    )


def compute_volume_buckets(total_history: pd.Series) -> VolumeBucketResult:
    """
    Terciles relativos de `total_history` (se espera TOTAL_HISTORY_6M de la
    poblacion COMPARABLE de UN cliente), respetando siempre los empates: un
    mismo valor nunca se reparte entre dos buckets. Funcion pura y
    determinista -- nunca modifica `total_history`.

    Devuelve VolumeBucketResult con status="OK" y exactamente 3 buckets no
    vacios (RELATIVE_LOW/RELATIVE_MEDIUM/RELATIVE_HIGH), o status=
    "NOT_ASSIGNABLE" (con `reason` machine-readable) cuando la distribucion
    no permite construir esos 3 grupos sin dividir un empate. NOT_ASSIGNABLE
    nunca degrada silenciosamente a 2 buckets: es un resultado explicito
    para el cliente completo.
    """
    n = len(total_history)

    # Coercion a numerico primero (mismo motivo que metrics._sum_or_not_evaluable):
    # una columna dtype `object` (p.ej. enteros sin castear, strings numericos,
    # o una mezcla con texto no numerico) no debe hacer fallar np.isinf con un
    # TypeError. `errors="coerce"` no muta `total_history` (crea una Series
    # nueva con el mismo indice); un valor realmente no convertible se
    # convierte en NaN, que ya cae bajo el guard 0 de abajo -- nunca
    # desaparece silenciosamente, siempre produce NOT_ASSIGNABLE.
    total_history = pd.to_numeric(total_history, errors="coerce")

    # Guard 0: cualquier valor no evaluable (NaN o +/-inf) invalida la
    # segmentacion completa ANTES de cualquier operacion de pandas
    # (value_counts/unique/nunique tienen comportamientos default que
    # ignoran NaN; este guard hace ese comportamiento irrelevante aqui).
    if total_history.isna().any() or np.isinf(total_history).any():
        return _not_assignable(total_history, REASON_NON_EVALUABLE_HISTORY_VALUES, n_distinct_values=0)

    if n < 3:
        return _not_assignable(total_history, REASON_N_LT_3, n_distinct_values=int(total_history.nunique()))

    distinct_values = sorted(total_history.unique())
    if len(distinct_values) < 3:
        return _not_assignable(total_history, REASON_DISTINCT_VALUES_LT_3, n_distinct_values=len(distinct_values))

    # Regla de construccion: agrupar por VALOR ascendente, nunca dividir un
    # empate -- cada valor distinto se procesa una unica vez, entero.
    value_counts = total_history.value_counts().sort_index()  # unicos, orden ascendente (seguro: sin NaN/inf)
    target = n / 3
    group_of_value: dict = {}
    current_group = 0  # 0=RELATIVE_LOW, 1=RELATIVE_MEDIUM, 2=RELATIVE_HIGH
    cumulative = 0

    for value, count in value_counts.items():
        group_of_value[value] = current_group  # se asigna ANTES de avanzar
        cumulative += count
        while current_group < 2 and cumulative >= target * (current_group + 1):
            current_group += 1  # puede avanzar mas de un grupo de golpe

    buckets = total_history.map(group_of_value).map(_GROUP_LABELS)

    # Post-condicion de seguridad: nunca degradar a <3 grupos en silencio.
    # El detalle exacto del bucle de avance es secundario mientras sea
    # determinista -- esta comprobacion es el contrato real.
    if buckets.nunique() < 3:
        return _not_assignable(total_history, REASON_COLLAPSE_AFTER_TIE_GROUPING, n_distinct_values=len(distinct_values))

    return VolumeBucketResult(
        status="OK",
        buckets=buckets,
        n_distinct_values=len(distinct_values),
        bucket_counts=buckets.value_counts().to_dict(),
        reason=None,
    )


def category_performance_table_with_bias(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series, category_col: str,
) -> pd.DataFrame:
    """
    Compone `models.category_performance_table` (sin modificarla) con Bias
    agregado por grupo. Reutiliza literalmente la tabla base -- WAPE,
    winner, improvement, ABS_ERROR_REDUCTION, pct_of_history_volume y
    small_sample no se recalculan aqui, solo se le anaden columnas.

    Normaliza `category_col` con MISSING_CATEGORY_LABEL (mismo literal que
    `category_performance_table` usa internamente) antes de su propio
    `groupby` de Bias, y une por la columna "category" ya normalizada en
    ambos lados -- nunca por posicion, para que una categoria nula termine
    usando exactamente la misma identidad logica en la tabla heredada y en
    el Bias anadido.
    """
    base = category_performance_table(df, pcols, comparable_mask, category_col)
    if base.empty:
        return base

    sub = df.loc[comparable_mask].copy()
    sub[category_col] = sub[category_col].fillna(MISSING_CATEGORY_LABEL)

    bias_rows = []
    for value, group in sub.groupby(category_col, dropna=False, observed=True):
        result = bias_aggregate(group, pcols)
        bias_rows.append({
            "category": value,
            "scp_bias_agg": result.scp_bias_agg, "ml_bias_agg": result.ml_bias_agg,
            "scp_direction": result.scp_direction, "ml_direction": result.ml_direction,
        })

    return base.merge(pd.DataFrame(bias_rows), on="category", how="left")


def classification_volume_cross_table(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series,
) -> pd.DataFrame:
    """
    Cruce SERIES_CLASSIFICATION x VOLUME_BUCKET -- unico cruce de Fase 8,
    exclusivamente global (no existe version individual). Clave estructurada
    de tupla `(clasificacion, bucket)`, nunca serializada como string: la
    igualdad de grupo es igualdad de tupla, collision-free por construccion,
    no por verificar que un separador textual no aparezca en los datos.

    `df` debe llegar con VOLUME_BUCKET ya presente como columna (adjuntada
    por el llamador desde los `VolumeBucketResult.buckets` ya calculados por
    cliente); nunca es NaN por construccion -- siempre uno de los 4 valores
    explicitos (RELATIVE_LOW/MEDIUM/HIGH o NOT_ASSIGNABLE).
    """
    sub = df.loc[comparable_mask].copy()
    sub["SERIES_CLASSIFICATION"] = sub["SERIES_CLASSIFICATION"].fillna(MISSING_CATEGORY_LABEL)
    sub["_CLASSIFICATION_VOLUME_KEY"] = list(zip(sub["SERIES_CLASSIFICATION"], sub[VOLUME_BUCKET_COLUMN]))
    mask_all_true = pd.Series(True, index=sub.index)

    table = category_performance_table_with_bias(sub, pcols, mask_all_true, "_CLASSIFICATION_VOLUME_KEY")
    if table.empty:
        return table

    table[["SERIES_CLASSIFICATION", "VOLUME_BUCKET"]] = pd.DataFrame(table["category"].tolist(), index=table.index)
    n_clients_map = sub.groupby("_CLASSIFICATION_VOLUME_KEY")["ID_CLIENT"].nunique()
    table["n_clients"] = table["category"].map(n_clients_map)
    return table.drop(columns=["category"])


@dataclass
class Phase8ClientDiagnostics:
    bias_total: BiasAggregateResult
    volume: VolumeBucketResult
    model_tables: dict
    classification_tables: dict
    volume_table: pd.DataFrame


def build_phase8_client_diagnostics(
    df: pd.DataFrame, pcols: PeriodColumns, comparable_mask: pd.Series,
) -> Phase8ClientDiagnostics:
    """
    Diagnostico Fase 8 completo de un cliente, unicamente para la poblacion
    comparable de 6M (el llamador -- `client_analysis._analyze_period` --
    decide cuando invocar esto; aqui no se valida el periodo). Firma pura,
    sin `ClientAnalysisResult`.
    """
    comparable_df = df.loc[comparable_mask]
    bias_total = bias_aggregate(comparable_df, pcols)
    volume_result = compute_volume_buckets(comparable_df[pcols.total_history])

    df_with_bucket = comparable_df.copy()
    df_with_bucket[VOLUME_BUCKET_COLUMN] = volume_result.buckets  # nunca toca `df`/`comparable_df` originales

    model_tables = {
        col: category_performance_table_with_bias(df, pcols, comparable_mask, col)
        for col in MODEL_CATEGORY_COLUMNS
    }
    classification_tables = {
        col: category_performance_table_with_bias(df, pcols, comparable_mask, col)
        for col in CLASSIFICATION_CATEGORY_COLUMNS
    }
    volume_table = category_performance_table_with_bias(
        df_with_bucket, pcols, pd.Series(True, index=df_with_bucket.index), VOLUME_BUCKET_COLUMN,
    )

    return Phase8ClientDiagnostics(
        bias_total=bias_total, volume=volume_result,
        model_tables=model_tables, classification_tables=classification_tables, volume_table=volume_table,
    )


@dataclass
class Phase8GlobalDiagnostics:
    """Contenedor puro -- ninguna referencia a ClientAnalysisResult. Se ensambla en src/global_analysis.py."""
    bias_total: BiasAggregateResult
    model_tables: dict
    classification_tables: dict
    volume_table: pd.DataFrame
    classification_volume_cross: pd.DataFrame
    n_clients_with_not_assignable_volume: int
