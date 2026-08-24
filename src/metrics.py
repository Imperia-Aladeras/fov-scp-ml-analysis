"""
Metricas comunes: WAPE global ponderado, mejora relativa, reduccion absoluta
de error y estadistica descriptiva. Reutilizables tanto para el analisis por
cliente (Fase 3) como para la comparativa global entre clientes (Fase 4).

Principio metodologico (CLAUDE.md): el WAPE agregado NUNCA se calcula como
media simple de los WAPE por serie. Siempre es:

    WAPE_GLOBAL = SUM(error_absoluto_total) / SUM(historico_total)

sobre el universo de series comparables correspondiente.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.periods import PeriodColumns

EXTREME_LOWER_BOUND_PCT = -100.0
EXTREME_UPPER_BOUND_PCT = 100.0


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Division vectorizada que devuelve NaN donde el denominador es 0, nulo o negativo."""
    denom = denominator.where(denominator > 0)
    return numerator / denom


def period_wape_global(df: pd.DataFrame, pcols: PeriodColumns) -> dict:
    """
    WAPE global ponderado por volumen para SCP y ML sobre las filas de `df`
    (el llamador debe pasar ya el subconjunto comparable del periodo).

    Si TOTAL_HISTORY, SCP_TOTAL_ABS_ERROR o ML_TOTAL_ABS_ERROR tiene algun
    nulo dentro de `df`, la suma correspondiente queda NaN en vez de
    calcularse ignorando esa fila en silencio (pandas.Series.sum() ignora
    NaN por defecto). SCP_WAPE_GLOBAL y ML_WAPE_GLOBAL dependen de sumas
    distintas y pueden quedar evaluables de forma independiente; ninguno de
    los dos depende de SCP_WAPE/ML_WAPE (columnas distintas, no son input
    de esta formula).
    """
    history_sum = np.nan if df[pcols.total_history].isna().any() else float(df[pcols.total_history].sum())
    scp_abs_error_sum = (
        np.nan if df[pcols.scp_total_abs_error].isna().any() else float(df[pcols.scp_total_abs_error].sum())
    )
    ml_abs_error_sum = (
        np.nan if df[pcols.ml_total_abs_error].isna().any() else float(df[pcols.ml_total_abs_error].sum())
    )

    if not (history_sum > 0):
        return {
            "history_sum": history_sum,
            "scp_abs_error_sum": scp_abs_error_sum,
            "ml_abs_error_sum": ml_abs_error_sum,
            "scp_wape_global": np.nan,
            "ml_wape_global": np.nan,
            "improvement_pct": np.nan,
        }

    scp_wape = scp_abs_error_sum / history_sum
    ml_wape = ml_abs_error_sum / history_sum
    improvement = (scp_wape - ml_wape) / scp_wape * 100 if scp_wape > 0 else np.nan

    return {
        "history_sum": history_sum,
        "scp_abs_error_sum": scp_abs_error_sum,
        "ml_abs_error_sum": ml_abs_error_sum,
        "scp_wape_global": scp_wape,
        "ml_wape_global": ml_wape,
        "improvement_pct": improvement,
    }


def absolute_error_reduction_row(df: pd.DataFrame, pcols: PeriodColumns) -> pd.Series:
    """positivo = ML reduce error absoluto; negativo = ML lo aumenta."""
    return df[pcols.scp_total_abs_error] - df[pcols.ml_total_abs_error]


def absolute_error_reduction_total(df: pd.DataFrame, pcols: PeriodColumns) -> float:
    """
    positivo = ML reduce error absoluto; negativo = ML lo aumenta. NaN si
    SCP_TOTAL_ABS_ERROR o ML_TOTAL_ABS_ERROR tiene algun nulo en `df` (no se
    calcula ignorando esa fila en silencio, igual que period_wape_global).
    """
    if df[pcols.scp_total_abs_error].isna().any() or df[pcols.ml_total_abs_error].isna().any():
        return float("nan")
    return float(df[pcols.scp_total_abs_error].sum() - df[pcols.ml_total_abs_error].sum())


# Casos especiales documentados explicitamente por la spec de mejora relativa.
CASE_NORMAL = "NORMAL"
CASE_MISSING_WAPE = "MISSING_WAPE"
CASE_BOTH_ZERO = "BOTH_ZERO"
CASE_SCP_ZERO_ML_POSITIVE = "SCP_ZERO_ML_POSITIVE"
CASE_ML_ZERO_SCP_POSITIVE = "ML_ZERO_SCP_POSITIVE"

# Un WAPE "computacionalmente cero" (p.ej. 2e-16 en vez de 0.0 exacto, ruido
# de punto flotante heredado de la columna WAPE de origen) no se detecta con
# una comparacion == 0 estricta. Si ese valor casi-cero actua como denominador
# en ML_IMPROVEMENT_VS_SCP, el resultado explota a magnitudes absurdas
# (billones de por ciento) sin ser matematicamente "incorrecto", pero si
# inutil y enganoso. Por eso el cero se detecta con una tolerancia: muy por
# debajo de cualquier WAPE real plausible (0.01% = 1e-4 ya seria un WAPE muy
# bueno) y muy por encima del epsilon de double precision (~2.22e-16).
NEAR_ZERO_WAPE_EPSILON = 1e-9


def _as_numeric(series: pd.Series) -> pd.Series:
    """
    Coerciona a numerico antes de operar. Una columna que llegue aqui con
    dtype `object` (p.ej. una serie construida a mano en tests con valores
    `None`, o cualquier resto de texto) no debe hacer fallar `.abs()`.
    """
    return pd.to_numeric(series, errors="coerce")


def both_wape_zero_mask(scp_wape: pd.Series, ml_wape: pd.Series) -> pd.Series:
    """
    Unica parte de la regla de negocio del winner que esta completamente
    especificada y por tanto es segura de auditar sin conocer la formula
    original: "ambos WAPE iguales a cero -> TIE". Usa tolerancia, no
    igualdad exacta (ver NEAR_ZERO_WAPE_EPSILON).
    """
    scp_wape, ml_wape = _as_numeric(scp_wape), _as_numeric(ml_wape)
    return (
        scp_wape.notna() & ml_wape.notna()
        & (scp_wape.abs() <= NEAR_ZERO_WAPE_EPSILON) & (ml_wape.abs() <= NEAR_ZERO_WAPE_EPSILON)
    )


def relative_improvement_row(scp_wape: pd.Series, ml_wape: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    ML_IMPROVEMENT_VS_SCP_PERIODO = (SCP_WAPE - ML_WAPE) / SCP_WAPE * 100

    Devuelve (valores, casos) donde `casos` documenta explicitamente por que
    una fila no tiene un valor numerico valido:

    - MISSING_WAPE: SCP_WAPE o ML_WAPE es nulo -> no se calcula (NaN).
    - BOTH_ZERO: ambos WAPE son ~0 (tolerancia, ver NEAR_ZERO_WAPE_EPSILON) ->
      formula 0/0 no valida (NaN).
    - SCP_ZERO_ML_POSITIVE: SCP_WAPE~0 y ML_WAPE>0 -> division por un
      denominador computacionalmente cero, resultado no interpretable; no se
      inventa un valor (NaN) en vez de un porcentaje astronomico.
    - ML_ZERO_SCP_POSITIVE: ML_WAPE~0 y SCP_WAPE>0 -> matematicamente valido,
      da +100% (ML elimina todo el error). Se calcula con la formula normal.
    - NORMAL: formula estandar.
    """
    scp_wape, ml_wape = _as_numeric(scp_wape), _as_numeric(ml_wape)
    both_present = scp_wape.notna() & ml_wape.notna()
    scp_zero = scp_wape.abs() <= NEAR_ZERO_WAPE_EPSILON
    ml_zero = ml_wape.abs() <= NEAR_ZERO_WAPE_EPSILON

    case = pd.Series(CASE_MISSING_WAPE, index=scp_wape.index, dtype=object)
    case = case.where(~both_present, CASE_NORMAL)
    case = case.mask(both_present & scp_zero & ml_zero, CASE_BOTH_ZERO)
    case = case.mask(both_present & scp_zero & ~ml_zero, CASE_SCP_ZERO_ML_POSITIVE)
    case = case.mask(both_present & ml_zero & ~scp_zero, CASE_ML_ZERO_SCP_POSITIVE)

    with np.errstate(divide="ignore", invalid="ignore"):
        raw = (scp_wape - ml_wape) / scp_wape * 100

    values = raw.where(case.isin([CASE_NORMAL, CASE_ML_ZERO_SCP_POSITIVE]))
    return values, case


def descriptive_stats(series: pd.Series) -> dict:
    """
    Estadistica descriptiva completa de una serie de mejoras (%). La mediana
    debe usarse como referencia principal cuando existan outliers, pero la
    media siempre se incluye tambien.
    """
    clean = series.dropna()
    n = len(clean)
    if n == 0:
        return {
            "count": 0, "mean": np.nan, "median": np.nan, "std": np.nan,
            "p10": np.nan, "p25": np.nan, "p75": np.nan, "p90": np.nan,
            "min": np.nan, "max": np.nan,
            "n_below_-100": 0, "pct_below_-100": np.nan,
            "n_above_100": 0, "pct_above_100": np.nan,
        }
    n_below = int((clean < EXTREME_LOWER_BOUND_PCT).sum())
    n_above = int((clean > EXTREME_UPPER_BOUND_PCT).sum())
    return {
        "count": n,
        "mean": clean.mean(),
        "median": clean.median(),
        "std": clean.std(ddof=1) if n > 1 else 0.0,
        "p10": clean.quantile(0.10),
        "p25": clean.quantile(0.25),
        "p75": clean.quantile(0.75),
        "p90": clean.quantile(0.90),
        "min": clean.min(),
        "max": clean.max(),
        "n_below_-100": n_below,
        "pct_below_-100": n_below / n * 100,
        "n_above_100": n_above,
        "pct_above_100": n_above / n * 100,
    }


def winner_distribution(winner: pd.Series) -> dict:
    """Conteo y porcentaje de ML/SCP/TIE sobre una serie WINNER_METHOD_*."""
    valid = winner.dropna()
    total = len(valid)
    counts = valid.value_counts().to_dict()
    result = {}
    for method in ("ML", "SCP", "TIE"):
        n = int(counts.get(method, 0))
        result[method] = {"n": n, "pct": (n / total * 100) if total else np.nan}
    other_methods = set(counts) - {"ML", "SCP", "TIE"}
    if other_methods:
        result["OTHER"] = {
            "n": int(sum(counts[m] for m in other_methods)),
            "pct": (sum(counts[m] for m in other_methods) / total * 100) if total else np.nan,
            "values": sorted(other_methods),
        }
    result["_total"] = total
    return result


def client_contribution_to_total_reduction(client_reductions: pd.Series) -> pd.Series:
    """
    CLIENT_CONTRIBUTION_TO_TOTAL_REDUCTION = CLIENT_ABS_ERROR_REDUCTION / TOTAL_ABS_ERROR_REDUCTION * 100
    Devuelve NaN para todos si el total es 0 (formula no valida).
    """
    total = client_reductions.sum()
    if total == 0:
        return pd.Series(np.nan, index=client_reductions.index)
    return client_reductions / total * 100


def cross_entity_stats(values: pd.Series, tie_epsilon: float = 0.0) -> dict:
    """
    Estadistica de una metrica de mejora calculada una vez por entidad
    (p.ej. una fila por cliente). Cada entidad pesa igual: no se pondera
    por volumen ni por numero de series subyacentes.

    Se usa tanto para "mejora por cliente" (Perspectiva 2 del analisis
    global) como, de forma generica, para cualquier agregacion por entidad
    con el mismo peso.

    `values` debe incluir una entrada POR CADA entidad total (con NaN para
    las que no tienen mejora calculable, p.ej. un cliente sin series
    comparables), no solo las evaluables: asi `n_total` y `n_missing`
    reflejan el universo completo. La media, mediana, percentiles y
    porcentajes (`pct_improved`, etc.) SIEMPRE usan como denominador
    unicamente las entidades evaluables (`count` / `n_total - n_missing`),
    nunca el total.
    """
    stats = descriptive_stats(values)
    clean = values.dropna()
    n_total = len(values)
    n = len(clean)
    n_missing = n_total - n
    n_improved = int((clean > tie_epsilon).sum())
    n_worse = int((clean < -tie_epsilon).sum())
    n_tie = n - n_improved - n_worse
    stats.update({
        "n_total": n_total,
        "n_evaluable": n,
        "n_missing": n_missing,
        "n_improved": n_improved,
        "pct_improved": (n_improved / n * 100) if n else np.nan,
        "n_worse": n_worse,
        "pct_worse": (n_worse / n * 100) if n else np.nan,
        "n_tie": n_tie,
        "pct_tie": (n_tie / n * 100) if n else np.nan,
    })
    return stats


# --------------------------------------------------------------------------
# Bias agregado (Fase 8B). BIAS_AGREGADO = SUM(TOTAL_SIGNED_ERROR) / SUM(TOTAL_HISTORY),
# nunca media simple del Bias por serie (mismo principio que WAPE_GLOBAL: ver
# docstring del modulo). Direcciones machine-readable, sin copy de presentacion.
# --------------------------------------------------------------------------

BIAS_DIRECTION_POSITIVE = "POSITIVE"
BIAS_DIRECTION_NEGATIVE = "NEGATIVE"
BIAS_DIRECTION_ZERO = "ZERO"
BIAS_DIRECTION_NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass
class BiasAggregateResult:
    history_sum: float
    scp_signed_error_sum: float
    ml_signed_error_sum: float
    scp_bias_agg: float
    ml_bias_agg: float
    scp_direction: str
    ml_direction: str


def _sum_or_not_evaluable(series: pd.Series) -> float:
    """
    NaN si algun valor de `series` es NaN o +/-inf; si no, la suma. Coerciona
    a numerico primero (misma razon que `_as_numeric`): una columna dtype
    `object` (p.ej. una serie de solo `None`, como la de un cliente sin
    filas comparables) no debe hacer fallar `np.isinf`.
    """
    series = _as_numeric(series)
    if series.isna().any() or np.isinf(series).any():
        return np.nan
    return float(series.sum())


def direction_label(bias_value: float) -> str:
    """
    Etiqueta machine-readable de la direccion de un Bias agregado. Un valor no
    finito (NaN, +inf o -inf) nunca se etiqueta POSITIVE/NEGATIVE -- siempre
    NOT_EVALUABLE, incluso si llega no finito por una causa no anticipada
    (p.ej. desbordamiento) y no solo por un input crudo ya no finito.
    """
    if not np.isfinite(bias_value):
        return BIAS_DIRECTION_NOT_EVALUABLE
    if bias_value > 0:
        return BIAS_DIRECTION_POSITIVE
    if bias_value < 0:
        return BIAS_DIRECTION_NEGATIVE
    return BIAS_DIRECTION_ZERO


def bias_aggregate(df: pd.DataFrame, pcols: PeriodColumns) -> BiasAggregateResult:
    """
    Bias agregado SCP y ML sobre las filas de `df` (el llamador debe pasar ya
    el subconjunto comparable correspondiente): BIAS_AGG = SUM(TOTAL_SIGNED_ERROR)
    / SUM(TOTAL_HISTORY). Nunca se reconstruye SIGNED_ERROR = FORECAST - HISTORY
    aqui (eso es exclusivo de quality_checks.check_error_chain_reconstruction,
    una validacion, no una fuente de calculo) -- se usan directamente las
    columnas canonicas ya materializadas.

    History es el denominador comun: si no es finito o su suma no es > 0,
    ambos metodos quedan no evaluables. Con history valido, SCP y ML se
    evaluan de forma INDEPENDIENTE: un signed error no finito de un metodo
    no invalida al otro.
    """
    history_sum = _sum_or_not_evaluable(df[pcols.total_history])
    scp_signed_sum = _sum_or_not_evaluable(df[pcols.scp_total_signed_error])
    ml_signed_sum = _sum_or_not_evaluable(df[pcols.ml_total_signed_error])

    history_valid = np.isfinite(history_sum) and history_sum > 0

    if not history_valid:
        return BiasAggregateResult(
            history_sum=history_sum, scp_signed_error_sum=scp_signed_sum, ml_signed_error_sum=ml_signed_sum,
            scp_bias_agg=np.nan, ml_bias_agg=np.nan,
            scp_direction=BIAS_DIRECTION_NOT_EVALUABLE, ml_direction=BIAS_DIRECTION_NOT_EVALUABLE,
        )

    scp_bias_agg = (scp_signed_sum / history_sum) if np.isfinite(scp_signed_sum) else np.nan
    ml_bias_agg = (ml_signed_sum / history_sum) if np.isfinite(ml_signed_sum) else np.nan

    return BiasAggregateResult(
        history_sum=history_sum, scp_signed_error_sum=scp_signed_sum, ml_signed_error_sum=ml_signed_sum,
        scp_bias_agg=scp_bias_agg, ml_bias_agg=ml_bias_agg,
        scp_direction=direction_label(scp_bias_agg), ml_direction=direction_label(ml_bias_agg),
    )
