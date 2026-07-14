"""Datos sinteticos compartidos entre tests (no depende de los CSV reales)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.input_loader import ClientSource
from src.periods import period_columns


def set_period(df: pd.DataFrame, period: str, total_history, scp_forecast, scp_abs_error, scp_wape,
                ml_forecast, ml_abs_error, ml_wape, winner_method) -> None:
    pcols = period_columns(period)
    df[pcols.total_history] = total_history
    df[pcols.scp_total_forecast] = scp_forecast
    df[pcols.scp_total_abs_error] = scp_abs_error
    df[pcols.scp_wape] = scp_wape
    df[pcols.ml_total_forecast] = ml_forecast
    df[pcols.ml_total_abs_error] = ml_abs_error
    df[pcols.ml_wape] = ml_wape
    df[pcols.winner_method] = winner_method


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


def make_client_source(df: pd.DataFrame, id_client: int, label: str) -> ClientSource:
    return ClientSource(
        csv_path=Path(f"TA_FOV_SCP_ML_{id_client}_{label}.csv"), file_label=f"{id_client}_{label}",
        id_from_filename=id_client, dataframe=df, read_repaired=False, id_client=id_client,
        id_batch=[1], id_run_staging=[1], source_run_id=[1], n_rows=len(df), is_valid=True,
        folder_name=f"{id_client}_{label}",
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
