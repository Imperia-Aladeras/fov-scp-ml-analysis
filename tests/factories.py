"""Datos sinteticos compartidos entre tests (no depende de los CSV reales)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.input_loader import ClientSource
from src.periods import period_columns

# Fecha sintetica estable para tests que necesitan RUN_START_DATE (Fase 2).
# No depende de ser dia 1 del mes; centralizada aqui para no hardcodear una
# fecha en decenas de tests distintos.
DEFAULT_RUN_START_DATE = "2026-01-01"


def _derive_signed_error_and_bias(history_values, forecast_values):
    """
    SIGNED_ERROR = FORECAST - HISTORY; BIAS = SIGNED_ERROR / HISTORY (None si
    `history` no es > 0 o `forecast` es None) -- misma formula canonica que
    valida `quality_checks.check_error_chain_reconstruction`/
    `check_bias_reconstruction`, no un valor especifico de una fixture.
    """
    signed_error = []
    bias = []
    for history, forecast in zip(history_values, forecast_values):
        if forecast is None or history is None:
            signed_error.append(None)
            bias.append(None)
            continue
        signed = forecast - history
        signed_error.append(signed)
        bias.append(signed / history if history > 0 else None)
    return signed_error, bias


def set_period(df: pd.DataFrame, period: str, total_history, scp_forecast, scp_abs_error, scp_wape,
                ml_forecast, ml_abs_error, ml_wape, winner_method) -> None:
    """
    Ademas de las columnas historicas (Fases 0-7), deriva y rellena las
    columnas canonicas de signed error/Bias (Fase 8B) a partir de los mismos
    `total_history`/`*_forecast` ya recibidos -- ningun llamador existente
    necesita cambiar para seguir produciendo un DataFrame valido para
    `build_phase8_client_diagnostics`.

    Todas las columnas del periodo se insertan en una unica asignacion
    multi-columna y despues se consolida el DataFrame in-place. Esta funcion
    se llama 9 veces por fixture (una por periodo) sobre el mismo `df`;
    sin consolidar, cada tanda de columnas nuevas queda en un bloque interno
    separado y pandas termina emitiendo `PerformanceWarning: DataFrame is
    highly fragmented` (~100+ bloques para un DataFrame de este tamano).
    `_consolidate_inplace()` es el mecanismo que pandas usa internamente para
    fusionar esos bloques (el mismo que aplica `DataFrame.copy()`); no altera
    ningun valor ni columna, solo la representacion interna -- mismo
    contrato de mutacion in-place para el llamador, cero cambios de firma.
    """
    pcols = period_columns(period)
    scp_signed_error, scp_bias = _derive_signed_error_and_bias(total_history, scp_forecast)
    ml_signed_error, ml_bias = _derive_signed_error_and_bias(total_history, ml_forecast)

    new_columns = pd.DataFrame({
        pcols.total_history: total_history,
        pcols.scp_total_forecast: scp_forecast,
        pcols.scp_total_abs_error: scp_abs_error,
        pcols.scp_wape: scp_wape,
        pcols.ml_total_forecast: ml_forecast,
        pcols.ml_total_abs_error: ml_abs_error,
        pcols.ml_wape: ml_wape,
        pcols.winner_method: winner_method,
        pcols.scp_total_signed_error: scp_signed_error,
        pcols.scp_bias: scp_bias,
        pcols.ml_total_signed_error: ml_signed_error,
        pcols.ml_bias: ml_bias,
    }, index=df.index)
    df[new_columns.columns] = new_columns
    df._consolidate_inplace()


def build_synthetic_client_dataframe() -> pd.DataFrame:
    """
    3 filas candidatas:
      fila 0: ML gana en todos los periodos (SCP_WAPE=0.2, ML_WAPE=0.1).
      fila 1: SCP gana en todos los periodos (SCP_WAPE=0.1, ML_WAPE=0.3).
      fila 2: historico cero en todos los periodos -> no comparable.
    Incluye columnas de identificacion y clasificacion minimas para poder
    ejercitar modelos/clasificaciones/rankings (Fase 3).
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1, 1],
        "ID_CLIENT": [99999, 99999, 99999],
        "ID_CONFIGURATION": [1001, 1002, 1003],
        "VALUE_LEVEL_1": ["Cat A", "Cat B", "Cat C"],
        "VALUE_LEVEL_2": [None, None, None],
        "VALUE_LEVEL_3": [None, None, None],
        "VALUE_LEVEL_4": [None, None, None],
        "VALUE_LEVEL_5": [None, None, None],
        "ML_BEST_MODEL": ["AutoETS", "AutoARIMA", None],
        "SCP_BEST_MODEL": ["x11 seasonal", "SeasonalNaive", None],
        "ML_CLASSIFICATION": ["smooth", "erratic", None],
        "ML_TYPE": ["smooth_ok", "erratic_ok", None],
        "SERIES_CLASSIFICATION": ["smooth", "erratic", None],
        "SCP_CLASSIFICATION": ["smooth", "erratic", None],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE", "NOT_COMPARABLE_NO_HISTORY"],
    })

    for month in [f"M{i}" for i in range(1, 7)]:
        set_period(
            df, month,
            total_history=[100.0, 100.0, 0.0],
            scp_forecast=[120.0, 110.0, None], scp_abs_error=[20.0, 10.0, None], scp_wape=[0.2, 0.1, None],
            ml_forecast=[110.0, 130.0, None], ml_abs_error=[10.0, 30.0, None], ml_wape=[0.1, 0.3, None],
            winner_method=["ML", "SCP", None],
        )

    for period in ("RECENT_3M", "OLDER_3M"):
        set_period(
            df, period,
            total_history=[300.0, 300.0, 0.0],
            scp_forecast=[360.0, 330.0, None], scp_abs_error=[60.0, 30.0, None], scp_wape=[0.2, 0.1, None],
            ml_forecast=[330.0, 390.0, None], ml_abs_error=[30.0, 90.0, None], ml_wape=[0.1, 0.3, None],
            winner_method=["ML", "SCP", None],
        )
    set_period(
        df, "6M",
        total_history=[600.0, 600.0, 0.0],
        scp_forecast=[720.0, 660.0, None], scp_abs_error=[120.0, 60.0, None], scp_wape=[0.2, 0.1, None],
        ml_forecast=[660.0, 780.0, None], ml_abs_error=[60.0, 180.0, None], ml_wape=[0.1, 0.3, None],
        winner_method=["ML", "SCP", None],
    )
    return df


def build_no_comparable_dataframe() -> pd.DataFrame:
    """1 fila candidata, sin ninguna serie comparable en ningun periodo."""
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1],
        "ID_CLIENT": [88888],
        "ID_CONFIGURATION": [1],
        "VALUE_LEVEL_1": ["Cat"],
        "VALUE_LEVEL_2": [None], "VALUE_LEVEL_3": [None], "VALUE_LEVEL_4": [None], "VALUE_LEVEL_5": [None],
        "ML_BEST_MODEL": [None], "SCP_BEST_MODEL": [None],
        "ML_CLASSIFICATION": [None], "ML_TYPE": [None],
        "SERIES_CLASSIFICATION": [None], "SCP_CLASSIFICATION": [None],
        "COMPARISON_STATUS": ["NOT_COMPARABLE_MISSING_VALIDATION"],
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M", "6M"]:
        set_period(
            df, period, total_history=[0.0],
            scp_forecast=[None], scp_abs_error=[None], scp_wape=[None],
            ml_forecast=[None], ml_abs_error=[None], ml_wape=[None],
            winner_method=[None],
        )
    return df


def make_client_source(df: pd.DataFrame, id_client: int, label: str, display_name: str | None = None) -> ClientSource:
    """
    display_name simula el resultado de resolver el catalogo (Fase 5), que
    en produccion ocurre en la orquestacion, nunca en el loader (por eso
    ClientSource no lo resuelve por si mismo). Por defecto usa `label` para
    que las factories existentes sigan produciendo un display_name legible
    sin tener que tocar cada llamada.
    """
    resolved_display_name = display_name if display_name is not None else label
    return ClientSource(
        csv_path=Path(f"TA_FOV_SCP_ML_{id_client}_{label}.csv"), file_label=f"{id_client}_{label}",
        id_from_filename=id_client, dataframe=df, read_repaired=False, id_client=id_client,
        id_batch=[1], id_run_staging=[1], source_run_id=[1], n_rows=len(df), is_valid=True,
        folder_name=f"{id_client}_{label}", display_name=resolved_display_name,
    )


def build_synthetic_client_result(with_data: bool = True):
    from src.client_analysis import analyze_client

    if with_data:
        df = build_synthetic_client_dataframe()
        source = make_client_source(df, 99999, "Synthetic")
    else:
        df = build_no_comparable_dataframe()
        source = make_client_source(df, 88888, "NoComparable")
    return analyze_client(source)


def build_multi_client_results() -> list:
    """
    3 clientes sinteticos para ejercitar la comparativa global:
      - 99999_Synthetic: mixto (1 fila ML gana, 1 fila SCP gana).
      - 88888_NoComparable: sin ninguna serie comparable (excluido de las
        4 perspectivas globales, pero presente en execution_summary).
      - 77777_AllMlWins: todas las filas gana ML (para ver un cliente
        homogeneo distinto del mixto).
    """
    from src.client_analysis import analyze_client

    mixed = analyze_client(make_client_source(build_synthetic_client_dataframe(), 99999, "Synthetic"))
    no_comparable = analyze_client(make_client_source(build_no_comparable_dataframe(), 88888, "NoComparable"))

    all_ml_df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1],
        "ID_CLIENT": [77777, 77777],
        "ID_CONFIGURATION": [2001, 2002],
        "VALUE_LEVEL_1": ["Cat A", "Cat B"],
        "VALUE_LEVEL_2": [None, None], "VALUE_LEVEL_3": [None, None],
        "VALUE_LEVEL_4": [None, None], "VALUE_LEVEL_5": [None, None],
        "ML_BEST_MODEL": ["AutoETS", "AutoETS"], "SCP_BEST_MODEL": ["x11 seasonal", "x11 seasonal"],
        "ML_CLASSIFICATION": ["smooth", "smooth"], "ML_TYPE": ["smooth_ok", "smooth_ok"],
        "SERIES_CLASSIFICATION": ["smooth", "smooth"], "SCP_CLASSIFICATION": ["smooth", "smooth"],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE"],
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M", "6M"]:
        multiplier = 1.0 if period in ("RECENT_3M", "OLDER_3M") else (2.0 if period == "6M" else 1.0 / 3)
        set_period(
            all_ml_df, period,
            total_history=[300.0 * multiplier, 300.0 * multiplier],
            scp_forecast=[360.0 * multiplier, 360.0 * multiplier],
            scp_abs_error=[60.0 * multiplier, 60.0 * multiplier], scp_wape=[0.2, 0.2],
            ml_forecast=[330.0 * multiplier, 330.0 * multiplier],
            ml_abs_error=[30.0 * multiplier, 30.0 * multiplier], ml_wape=[0.1, 0.1],
            winner_method=["ML", "ML"],
        )
    all_ml = analyze_client(make_client_source(all_ml_df, 77777, "AllMlWins"))

    return [mixed, no_comparable, all_ml]


def build_global_analysis_result():
    from src.global_analysis import analyze_global

    return analyze_global(build_multi_client_results())


def _build_single_row_client_dataframe(history: float, scp_abs_error: float, ml_abs_error: float, winner: str) -> pd.DataFrame:
    scp_forecast = history + scp_abs_error
    ml_forecast = history + ml_abs_error
    scp_wape = scp_abs_error / history
    ml_wape = ml_abs_error / history
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1], "ID_CLIENT": [0], "ID_CONFIGURATION": [1],
        "VALUE_LEVEL_1": ["Cat"], "VALUE_LEVEL_2": [None], "VALUE_LEVEL_3": [None],
        "VALUE_LEVEL_4": [None], "VALUE_LEVEL_5": [None],
        "ML_BEST_MODEL": ["AutoETS"], "SCP_BEST_MODEL": ["x11 seasonal"],
        "ML_CLASSIFICATION": ["smooth"], "ML_TYPE": ["smooth_ok"],
        "SERIES_CLASSIFICATION": ["smooth"], "SCP_CLASSIFICATION": ["smooth"],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M", "6M"]:
        set_period(
            df, period,
            total_history=[history], scp_forecast=[scp_forecast], scp_abs_error=[scp_abs_error], scp_wape=[scp_wape],
            ml_forecast=[ml_forecast], ml_abs_error=[ml_abs_error], ml_wape=[ml_wape], winner_method=[winner],
        )
    return df


def build_negative_net_multi_client_results() -> list:
    """
    2 clientes disenados para que la reduccion NETA total sea negativa:
      - 55501_PositiveClient: reduccion = +10 (ML mejor, historico pequeno).
      - 55502_NegativeClient: reduccion = -1000 (ML mucho peor, historico grande).
    Neto = 10 - 1000 = -990. Sirve para verificar que el cliente negativo
    nunca se describe como el principal contribuidor a la reduccion, que no
    se usa REDUCCION_NETA como denominador de ningun porcentaje, y que los
    porcentajes de cada grupo (reduce / aumenta) suman 100% dentro de si
    mismos.
    """
    from src.client_analysis import analyze_client

    positive_df = _build_single_row_client_dataframe(history=100.0, scp_abs_error=20.0, ml_abs_error=10.0, winner="ML")
    positive = analyze_client(make_client_source(positive_df, 55501, "PositiveClient"))

    negative_df = _build_single_row_client_dataframe(history=2000.0, scp_abs_error=100.0, ml_abs_error=1100.0, winner="SCP")
    negative = analyze_client(make_client_source(negative_df, 55502, "NegativeClient"))

    return [positive, negative]
