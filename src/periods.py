"""
Modelo de periodos y mapeo centralizado periodo -> columnas del CSV.

Convencion temporal (fuente de verdad: CLAUDE.md):
    M1..M6: meses cerrados de la ventana retrospectiva. M1 es el mes cerrado
    mas reciente; M6 es el mas antiguo dentro de la ventana de seis meses.

    RECENT_3M = M1 + M2 + M3  (Primer trimestre del semestre)
    OLDER_3M  = M4 + M5 + M6  (Segundo trimestre del semestre)
    6M        = M1 + M2 + M3 + M4 + M5 + M6 (Semestre completo)

Los nombres tecnicos (M1..M6, RECENT_3M, OLDER_3M, 6M) se usan siempre en
codigo, columnas y validaciones. Las etiquetas visibles (VISIBLE_LABELS) se
usan solo en informes, titulos y graficos.
"""

from __future__ import annotations

from dataclasses import dataclass

MONTHLY_PERIODS: list[str] = [f"M{i}" for i in range(1, 7)]
QUARTER_PERIODS: list[str] = ["RECENT_3M", "OLDER_3M"]
SEMESTER_PERIOD = "6M"
AGGREGATE_PERIODS: list[str] = [*QUARTER_PERIODS, SEMESTER_PERIOD]
ALL_PERIODS: list[str] = [*MONTHLY_PERIODS, *AGGREGATE_PERIODS]

QUARTER_MONTHS: dict[str, list[str]] = {
    "RECENT_3M": ["M1", "M2", "M3"],
    "OLDER_3M": ["M4", "M5", "M6"],
}
SEMESTER_MONTHS: list[str] = MONTHLY_PERIODS

VISIBLE_LABELS: dict[str, str] = {
    "RECENT_3M": "Primer trimestre del semestre (M1-M3)",
    "OLDER_3M": "Segundo trimestre del semestre (M4-M6)",
    "6M": "Semestre completo (M1-M6)",
    **{m: m for m in MONTHLY_PERIODS},
}


def visible_label(period: str) -> str:
    """Etiqueta visible para informes/graficos. Nunca usar en codigo/columnas."""
    if period not in VISIBLE_LABELS:
        raise ValueError(f"Periodo desconocido: {period!r}")
    return VISIBLE_LABELS[period]


def is_monthly(period: str) -> bool:
    return period in MONTHLY_PERIODS


def is_aggregate(period: str) -> bool:
    return period in AGGREGATE_PERIODS


def months_of(period: str) -> list[str]:
    """Meses que componen un periodo. Para un mes individual, devuelve [period]."""
    if is_monthly(period):
        return [period]
    if period in QUARTER_MONTHS:
        return QUARTER_MONTHS[period]
    if period == SEMESTER_PERIOD:
        return SEMESTER_MONTHS
    raise ValueError(f"Periodo desconocido: {period!r}")


@dataclass(frozen=True)
class PeriodColumns:
    """
    Nombres de columna normalizados para un periodo concreto.

    Para periodos mensuales (M1..M6) estos nombres corresponden a las
    columnas "de un solo mes" del CSV (p.ej. HISTORY_M1). Para periodos
    agregados (RECENT_3M, OLDER_3M, 6M) corresponden a las columnas
    "TOTAL_*_{periodo}" ya materializadas en el CSV.

    El mapeo es explicito: no se inventan nombres de columna, solo se
    normaliza el acceso para que el resto del codigo no tenga que
    ramificar segun el tipo de periodo.
    """

    period: str
    total_history: str
    scp_total_forecast: str
    ml_total_forecast: str
    scp_total_signed_error: str
    ml_total_signed_error: str
    scp_total_abs_error: str
    ml_total_abs_error: str
    scp_total_squared_error: str
    ml_total_squared_error: str
    positive_history_month_count: str
    scp_mae: str
    ml_mae: str
    scp_rmse: str
    ml_rmse: str
    scp_wape: str
    ml_wape: str
    scp_bias: str
    ml_bias: str
    winner_method: str
    winner_model: str
    finalist_method: str
    finalist_model: str
    winner_improvement_pct: str

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.total_history, self.scp_total_forecast, self.ml_total_forecast,
            self.scp_total_signed_error, self.ml_total_signed_error,
            self.scp_total_abs_error, self.ml_total_abs_error,
            self.scp_total_squared_error, self.ml_total_squared_error,
            self.positive_history_month_count,
            self.scp_mae, self.ml_mae, self.scp_rmse, self.ml_rmse,
            self.scp_wape, self.ml_wape, self.scp_bias, self.ml_bias,
            self.winner_method, self.winner_model,
            self.finalist_method, self.finalist_model,
            self.winner_improvement_pct,
        )


def _monthly_columns(month: str) -> PeriodColumns:
    return PeriodColumns(
        period=month,
        total_history=f"HISTORY_{month}",
        scp_total_forecast=f"SCP_FORECAST_{month}",
        ml_total_forecast=f"ML_FORECAST_{month}",
        scp_total_signed_error=f"SCP_SIGNED_ERROR_{month}",
        ml_total_signed_error=f"ML_SIGNED_ERROR_{month}",
        scp_total_abs_error=f"SCP_ABS_ERROR_{month}",
        ml_total_abs_error=f"ML_ABS_ERROR_{month}",
        scp_total_squared_error=f"SCP_SQUARED_ERROR_{month}",
        ml_total_squared_error=f"ML_SQUARED_ERROR_{month}",
        positive_history_month_count=f"POSITIVE_HISTORY_MONTH_COUNT_{month}",
        scp_mae=f"SCP_MAE_{month}",
        ml_mae=f"ML_MAE_{month}",
        scp_rmse=f"SCP_RMSE_{month}",
        ml_rmse=f"ML_RMSE_{month}",
        scp_wape=f"SCP_WAPE_{month}",
        ml_wape=f"ML_WAPE_{month}",
        scp_bias=f"SCP_BIAS_{month}",
        ml_bias=f"ML_BIAS_{month}",
        winner_method=f"WINNER_METHOD_{month}",
        winner_model=f"WINNER_MODEL_{month}",
        finalist_method=f"FINALIST_METHOD_{month}",
        finalist_model=f"FINALIST_MODEL_{month}",
        winner_improvement_pct=f"WINNER_IMPROVEMENT_PCT_{month}",
    )


def _aggregate_columns(period: str) -> PeriodColumns:
    return PeriodColumns(
        period=period,
        total_history=f"TOTAL_HISTORY_{period}",
        scp_total_forecast=f"SCP_TOTAL_FORECAST_{period}",
        ml_total_forecast=f"ML_TOTAL_FORECAST_{period}",
        scp_total_signed_error=f"SCP_TOTAL_SIGNED_ERROR_{period}",
        ml_total_signed_error=f"ML_TOTAL_SIGNED_ERROR_{period}",
        scp_total_abs_error=f"SCP_TOTAL_ABS_ERROR_{period}",
        ml_total_abs_error=f"ML_TOTAL_ABS_ERROR_{period}",
        scp_total_squared_error=f"SCP_TOTAL_SQUARED_ERROR_{period}",
        ml_total_squared_error=f"ML_TOTAL_SQUARED_ERROR_{period}",
        positive_history_month_count=f"POSITIVE_HISTORY_MONTH_COUNT_{period}",
        scp_mae=f"SCP_MAE_{period}",
        ml_mae=f"ML_MAE_{period}",
        scp_rmse=f"SCP_RMSE_{period}",
        ml_rmse=f"ML_RMSE_{period}",
        scp_wape=f"SCP_WAPE_{period}",
        ml_wape=f"ML_WAPE_{period}",
        scp_bias=f"SCP_BIAS_{period}",
        ml_bias=f"ML_BIAS_{period}",
        winner_method=f"WINNER_METHOD_{period}",
        winner_model=f"WINNER_MODEL_{period}",
        finalist_method=f"FINALIST_METHOD_{period}",
        finalist_model=f"FINALIST_MODEL_{period}",
        winner_improvement_pct=f"WINNER_IMPROVEMENT_PCT_{period}",
    )


def period_columns(period: str) -> PeriodColumns:
    """Mapeo explicito y centralizado periodo -> columnas del CSV."""
    if period in MONTHLY_PERIODS:
        return _monthly_columns(period)
    if period in AGGREGATE_PERIODS:
        return _aggregate_columns(period)
    raise ValueError(f"Periodo desconocido: {period!r}")


# Columnas de identificacion, universo y metadata que no dependen del periodo.
STATIC_REQUIRED_COLUMNS: list[str] = [
    "ID", "ID_BATCH", "ID_RUN_STAGING", "ID_CLIENT", "SOURCE_RUN_ID", "ID_CONFIGURATION",
    "VALUE_LEVEL_1", "VALUE_LEVEL_2", "VALUE_LEVEL_3", "VALUE_LEVEL_4", "VALUE_LEVEL_5",
    "ML_BEST_MODEL", "ML_CLASSIFICATION", "ML_TYPE", "ML_STATUS",
    "SCP_BEST_MODEL", "SCP_CLASSIFICATION", "SCP_STATUS",
    "SERIES_CLASSIFICATION",
    "COMPARISON_STATUS",
    "HAS_BASE_CANDIDATE", "HAS_SCP_CALCULATED", "HAS_ML_CALCULATED",
    "HAS_ML_EXCLUDED", "ML_EXCLUSION_REASON", "SCP_NO_OUTPUT_REASON",
    "COPIED_AT",
]


def all_required_columns() -> list[str]:
    """
    Lista completa y centralizada de columnas obligatorias: columnas
    estaticas + todas las columnas de todos los periodos (M1..M6,
    RECENT_3M, OLDER_3M, 6M). Se usa para el chequeo de "columnas
    obligatorias" del loader.
    """
    cols: list[str] = list(STATIC_REQUIRED_COLUMNS)
    seen = set(cols)
    for period in ALL_PERIODS:
        for col in period_columns(period).as_tuple():
            if col not in seen:
                cols.append(col)
                seen.add(col)
    return cols
