"""
Capa de presentacion de Fase 8 (8C): helpers PUROS de traduccion/formato,
compartidos por excel_writer.py, report_writer.py, html_view_models.py y
charts.py para que las cuatro salidas usen exactamente el mismo copy en
castellano y el mismo orden de presentacion.

Este modulo NUNCA recalcula Bias, volume buckets ni ninguna tabla de
src/phase8.py: unicamente traduce las etiquetas machine-readable ya
calculadas en el nucleo (BIAS_DIRECTION_*, VOLUME_BUCKET_*, reason codes de
VolumeBucketResult) y reordena/renombra columnas ya calculadas sobre una
COPIA del DataFrame de entrada (nunca en sitio, nunca sobre el DataFrame del
llamador).
"""

from __future__ import annotations

import pandas as pd

from src.metrics import (
    BIAS_DIRECTION_NEGATIVE,
    BIAS_DIRECTION_NOT_EVALUABLE,
    BIAS_DIRECTION_POSITIVE,
    BIAS_DIRECTION_ZERO,
)
from src.phase8 import (
    NOT_ASSIGNABLE,
    REASON_COLLAPSE_AFTER_TIE_GROUPING,
    REASON_DISTINCT_VALUES_LT_3,
    REASON_N_LT_3,
    REASON_NON_EVALUABLE_HISTORY_VALUES,
    RELATIVE_HIGH,
    RELATIVE_LOW,
    RELATIVE_MEDIUM,
)

DIRECTION_LABELS_ES = {
    BIAS_DIRECTION_POSITIVE: "Sobreprevisión",
    BIAS_DIRECTION_NEGATIVE: "Infraprevisión",
    BIAS_DIRECTION_ZERO: "Sin sesgo agregado",
    BIAS_DIRECTION_NOT_EVALUABLE: "No evaluable",
}

VOLUME_BUCKET_LABELS_ES = {
    RELATIVE_LOW: "Bajo relativo",
    RELATIVE_MEDIUM: "Medio relativo",
    RELATIVE_HIGH: "Alto relativo",
    NOT_ASSIGNABLE: "No asignable",
}

# Orden de negocio (LOW -> MEDIUM -> HIGH -> NOT_ASSIGNABLE), no el orden por
# n_comparable que produce category_performance_table_with_bias.
VOLUME_BUCKET_ORDER = [RELATIVE_LOW, RELATIVE_MEDIUM, RELATIVE_HIGH, NOT_ASSIGNABLE]

VOLUME_NOT_ASSIGNABLE_REASON_LABELS_ES = {
    REASON_NON_EVALUABLE_HISTORY_VALUES: (
        "Historico no evaluable (NaN o infinito) en alguna fila comparable: no se puede segmentar por volumen."
    ),
    REASON_N_LT_3: "Menos de 3 series comparables en 6M: no hay suficiente poblacion para 3 terciles.",
    REASON_DISTINCT_VALUES_LT_3: (
        "Menos de 3 valores distintos de historico total: todas las series tienen practicamente el mismo volumen."
    ),
    REASON_COLLAPSE_AFTER_TIE_GROUPING: (
        "Un unico valor de historico concentra demasiadas series: agrupar ese empate dejaria algun bucket vacio."
    ),
}

BIAS_METHODOLOGY_NOTE = (
    "Bias agregado = SUM(TOTAL_SIGNED_ERROR) / SUM(TOTAL_HISTORY). Positivo indica sobreprevision, "
    "negativo indica infraprevision. Magnitud y direccion complementan al WAPE (que solo mide magnitud "
    "del error), nunca lo sustituyen."
)

VOLUME_METHODOLOGY_NOTE = (
    "Los buckets de volumen (bajo/medio/alto relativo) son terciles de TOTAL_HISTORY_6M calculados "
    "UNICAMENTE dentro de la poblacion comparable de este cliente: no son umbrales absolutos y no son "
    "comparables en magnitud con los buckets de otro cliente."
)

# Copy especifico para reporting GLOBAL (8D): a diferencia de VOLUME_METHODOLOGY_NOTE
# (individual, "de este cliente"), este texto deja explicito que el reporting global
# unicamente AGREGA etiquetas VOLUME_BUCKET ya asignadas por cliente -- nunca recalcula
# terciles sobre el pool global de series. No reemplaza ni cambia el significado de
# VOLUME_METHODOLOGY_NOTE, que sigue siendo el copy correcto para el reporting individual.
VOLUME_METHODOLOGY_NOTE_GLOBAL = (
    "Cada VOLUME_BUCKET se asigno dentro de la poblacion comparable de su propio cliente; este "
    "reporting global unicamente agrega despues esas etiquetas ya calculadas. No se recalculan "
    "terciles sobre el conjunto global de series: los buckets no son umbrales absolutos comunes "
    "entre clientes ni son comparables en magnitud entre si."
)

PHASE8_ONLY_6M_NOTE = "Este diagnostico (Bias y volumen relativo) se calcula unicamente para el semestre completo (6M)."

PHASE8_SMALL_SAMPLE_NOTE = "Los grupos con menos de 10 series comparables se marcan como muestra pequena (small_sample): no se deben extraer conclusiones fuertes de ellos."

PHASE8_NO_ROUTING_NOTE = (
    "Estas cifras son diagnostico retrospectivo, no una recomendacion de modelo ni una regla de routing: "
    "no implican causalidad ni deben usarse para decidir automaticamente que metodo o modelo usar."
)


def direction_label_es(direction: str | None) -> str:
    """Traduce POSITIVE/NEGATIVE/ZERO/NOT_EVALUABLE (o None) a copy en castellano."""
    if direction is None:
        return DIRECTION_LABELS_ES[BIAS_DIRECTION_NOT_EVALUABLE]
    return DIRECTION_LABELS_ES.get(direction, DIRECTION_LABELS_ES[BIAS_DIRECTION_NOT_EVALUABLE])


def volume_bucket_label_es(bucket: str | None) -> str:
    """Traduce RELATIVE_LOW/MEDIUM/HIGH/NOT_ASSIGNABLE (o None) a copy en castellano."""
    if bucket is None:
        return VOLUME_BUCKET_LABELS_ES[NOT_ASSIGNABLE]
    return VOLUME_BUCKET_LABELS_ES.get(bucket, str(bucket))


def volume_not_assignable_reason_es(reason: str | None) -> str:
    if reason is None:
        return "Motivo no disponible."
    return VOLUME_NOT_ASSIGNABLE_REASON_LABELS_ES.get(reason, reason)


def sort_volume_table(volume_table: pd.DataFrame) -> pd.DataFrame:
    """
    Reordena (SOLO presentacion, no recalculo) `phase8.volume_table` en orden
    de negocio LOW/MEDIUM/HIGH/NOT_ASSIGNABLE en vez del orden por
    n_comparable que devuelve category_performance_table_with_bias. Devuelve
    una copia; nunca muta `volume_table`.
    """
    if volume_table is None or volume_table.empty:
        return volume_table
    order = {value: idx for idx, value in enumerate(VOLUME_BUCKET_ORDER)}
    return (
        volume_table.assign(_order=volume_table["category"].map(order).fillna(len(order)))
        .sort_values("_order", kind="stable")
        .drop(columns="_order")
        .reset_index(drop=True)
    )


BIAS_COLUMNS = ("scp_bias_agg", "ml_bias_agg", "scp_direction", "ml_direction")


def has_bias_columns(table: pd.DataFrame) -> bool:
    return table is not None and not table.empty and all(c in table.columns for c in BIAS_COLUMNS)
