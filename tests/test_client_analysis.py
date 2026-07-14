import math
from pathlib import Path

import pandas as pd

from src.client_analysis import analyze_client, period_comparable_mask
from src.input_loader import ClientSource
from src.periods import ALL_PERIODS, period_columns


def _minimal_period_frame(period: str, history, scp_forecast, scp_abs_error, scp_wape,
                           ml_forecast, ml_abs_error, ml_wape) -> tuple[pd.DataFrame, object]:
    pcols = period_columns(period)
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1] * len(history),
        pcols.total_history: history,
        pcols.scp_total_forecast: scp_forecast,
        pcols.scp_total_abs_error: scp_abs_error,
        pcols.scp_wape: scp_wape,
        pcols.ml_total_forecast: ml_forecast,
        pcols.ml_total_abs_error: ml_abs_error,
        pcols.ml_wape: ml_wape,
    })
    return df, pcols


def test_period_comparable_mask_monthly_excludes_zero_history():
    df, pcols = _minimal_period_frame(
        "M1",
        history=[100.0, 0.0],
        scp_forecast=[120.0, None], scp_abs_error=[20.0, None], scp_wape=[0.2, None],
        ml_forecast=[110.0, None], ml_abs_error=[10.0, None], ml_wape=[0.1, None],
    )
    mask = period_comparable_mask(df, pcols, df["HAS_BASE_CANDIDATE"] == 1)
    assert mask.tolist() == [True, False]


def test_period_comparable_mask_quarterly_uses_aggregate_columns_directly():
    df, pcols = _minimal_period_frame(
        "RECENT_3M",
        history=[300.0, 0.0],
        scp_forecast=[360.0, None], scp_abs_error=[60.0, None], scp_wape=[0.2, None],
        ml_forecast=[330.0, None], ml_abs_error=[30.0, None], ml_wape=[0.1, None],
    )
    mask = period_comparable_mask(df, pcols, df["HAS_BASE_CANDIDATE"] == 1)
    assert mask.tolist() == [True, False]


def test_period_comparable_mask_semester_excludes_missing_ml():
    df, pcols = _minimal_period_frame(
        "6M",
        history=[600.0, 600.0],
        scp_forecast=[720.0, 720.0], scp_abs_error=[120.0, 120.0], scp_wape=[0.2, 0.2],
        ml_forecast=[660.0, None], ml_abs_error=[60.0, None], ml_wape=[0.1, None],
    )
    mask = period_comparable_mask(df, pcols, df["HAS_BASE_CANDIDATE"] == 1)
    assert mask.tolist() == [True, False]


def _set_period(df: pd.DataFrame, period: str, total_history, scp_forecast, scp_abs_error, scp_wape,
                 ml_forecast, ml_abs_error, ml_wape, winner_method):
    pcols = period_columns(period)
    df[pcols.total_history] = total_history
    df[pcols.scp_total_forecast] = scp_forecast
    df[pcols.scp_total_abs_error] = scp_abs_error
    df[pcols.scp_wape] = scp_wape
    df[pcols.ml_total_forecast] = ml_forecast
    df[pcols.ml_total_abs_error] = ml_abs_error
    df[pcols.ml_wape] = ml_wape
    df[pcols.winner_method] = winner_method


def _build_synthetic_client_dataframe() -> pd.DataFrame:
    """
    3 filas candidatas:
      fila 0: ML gana en todos los periodos (SCP_WAPE=0.2, ML_WAPE=0.1).
      fila 1: SCP gana en todos los periodos (SCP_WAPE=0.1, ML_WAPE=0.3).
      fila 2: historico cero en todos los periodos -> no comparable.
    Los valores mensuales y agregados son coherentes entre si (agregado =
    suma de los tres/seis meses) para no generar warnings de reconciliacion.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1, 1],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE", "NOT_COMPARABLE_NO_HISTORY"],
    })

    for month in [f"M{i}" for i in range(1, 7)]:
        _set_period(
            df, month,
            total_history=[100.0, 100.0, 0.0],
            scp_forecast=[120.0, 110.0, None], scp_abs_error=[20.0, 10.0, None], scp_wape=[0.2, 0.1, None],
            ml_forecast=[110.0, 130.0, None], ml_abs_error=[10.0, 30.0, None], ml_wape=[0.1, 0.3, None],
            winner_method=["ML", "SCP", None],
        )

    _set_period(
        df, "RECENT_3M",
        total_history=[300.0, 300.0, 0.0],
        scp_forecast=[360.0, 330.0, None], scp_abs_error=[60.0, 30.0, None], scp_wape=[0.2, 0.1, None],
        ml_forecast=[330.0, 390.0, None], ml_abs_error=[30.0, 90.0, None], ml_wape=[0.1, 0.3, None],
        winner_method=["ML", "SCP", None],
    )
    _set_period(
        df, "OLDER_3M",
        total_history=[300.0, 300.0, 0.0],
        scp_forecast=[360.0, 330.0, None], scp_abs_error=[60.0, 30.0, None], scp_wape=[0.2, 0.1, None],
        ml_forecast=[330.0, 390.0, None], ml_abs_error=[30.0, 90.0, None], ml_wape=[0.1, 0.3, None],
        winner_method=["ML", "SCP", None],
    )
    _set_period(
        df, "6M",
        total_history=[600.0, 600.0, 0.0],
        scp_forecast=[720.0, 660.0, None], scp_abs_error=[120.0, 60.0, None], scp_wape=[0.2, 0.1, None],
        ml_forecast=[660.0, 780.0, None], ml_abs_error=[60.0, 180.0, None], ml_wape=[0.1, 0.3, None],
        winner_method=["ML", "SCP", None],
    )
    return df


def test_analyze_client_end_to_end_synthetic():
    df = _build_synthetic_client_dataframe()
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99999_Synthetic.csv"), file_label="99999_Synthetic", id_from_filename=99999,
        dataframe=df, read_repaired=False, id_client=99999, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99999_Synthetic",
    )

    result = analyze_client(source)

    assert result.n_candidates == 3
    period_6m = result.periods["6M"]
    assert period_6m.n_comparable == 2
    assert period_6m.n_not_comparable == 1
    assert period_6m.not_comparable_reason_counts.get("NO_HISTORY_OR_ZERO") == 1

    # WAPE global ponderado (no promedio simple):
    # scp_abs_error_sum = 120 + 60 = 180 ; ml_abs_error_sum = 60 + 180 = 240 ; history_sum = 1200
    assert math.isclose(period_6m.wape["scp_wape_global"], 180 / 1200, rel_tol=1e-9)
    assert math.isclose(period_6m.wape["ml_wape_global"], 240 / 1200, rel_tol=1e-9)

    assert period_6m.winner_counts["ML"]["n"] == 1
    assert period_6m.winner_counts["SCP"]["n"] == 1

    # reduccion absoluta total = sum(scp_abs_error) - sum(ml_abs_error) sobre comparables
    assert math.isclose(period_6m.abs_error_reduction_total, 180 - 240)

    # Los periodos mensuales tambien deben haberse calculado.
    for month in ("M1", "M2", "M3", "M4", "M5", "M6"):
        assert result.periods[month].n_comparable == 2

    assert result.status in ("SUCCESS", "SUCCESS_WITH_WARNINGS")
    assert result.file_valid is True


# --------------------------------------------------------------------------
# Item 3: un historico negativo en un mes concreto no debe invalidar los
# demas periodos ni el cliente completo cuando sus propios agregados siguen
# siendo validos (reproduce el caso real: cliente 10666, ID_CONFIGURATION
# 4468, historico negativo en un mes pero comparable en 6M).
# --------------------------------------------------------------------------

def _build_negative_history_dataframe() -> pd.DataFrame:
    """
    2 filas candidatas:
      1001: HISTORY_M1 negativo (-5), pero M2..M6 positivos y los agregados
            trimestral/semestral siguen siendo positivos.
      2002: fila de control, totalmente limpia.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1],
        "ID_CONFIGURATION": [1001, 2002],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE"],
    })

    _set_period(
        df, "M1",
        total_history=[-5.0, 100.0],
        scp_forecast=[None, 120.0], scp_abs_error=[None, 20.0], scp_wape=[None, 0.2],
        ml_forecast=[None, 110.0], ml_abs_error=[None, 10.0], ml_wape=[None, 0.1],
        winner_method=[None, "ML"],
    )
    for month in ("M2", "M3", "M4", "M5", "M6"):
        _set_period(
            df, month,
            total_history=[100.0, 100.0],
            scp_forecast=[120.0, 120.0], scp_abs_error=[20.0, 20.0], scp_wape=[0.2, 0.2],
            ml_forecast=[110.0, 110.0], ml_abs_error=[10.0, 10.0], ml_wape=[0.1, 0.1],
            winner_method=["ML", "ML"],
        )
    _set_period(
        df, "RECENT_3M",
        total_history=[195.0, 300.0],  # -5+100+100 ; 100+100+100
        scp_forecast=[240.0, 360.0], scp_abs_error=[45.0, 60.0], scp_wape=[45 / 195, 0.2],
        ml_forecast=[220.0, 330.0], ml_abs_error=[25.0, 30.0], ml_wape=[25 / 195, 0.1],
        winner_method=["ML", "ML"],
    )
    _set_period(
        df, "OLDER_3M",
        total_history=[300.0, 300.0],
        scp_forecast=[360.0, 360.0], scp_abs_error=[60.0, 60.0], scp_wape=[0.2, 0.2],
        ml_forecast=[330.0, 330.0], ml_abs_error=[30.0, 30.0], ml_wape=[0.1, 0.1],
        winner_method=["ML", "ML"],
    )
    _set_period(
        df, "6M",
        total_history=[495.0, 600.0],
        scp_forecast=[600.0, 720.0], scp_abs_error=[105.0, 120.0], scp_wape=[105 / 495, 0.2],
        ml_forecast=[550.0, 660.0], ml_abs_error=[55.0, 60.0], ml_wape=[55 / 495, 0.1],
        winner_method=["ML", "ML"],
    )
    return df


def test_negative_history_in_m1_does_not_invalidate_other_periods_or_client():
    df = _build_negative_history_dataframe()
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_10666_Synthetic.csv"), file_label="10666_Synthetic", id_from_filename=10666,
        dataframe=df, read_repaired=False, id_client=10666, id_batch=[63], id_run_staging=[59],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="10666_Synthetic",
    )
    result = analyze_client(source)

    # M1: la fila 1001 queda excluida del universo de performance (historico negativo).
    assert result.periods["M1"].n_comparable == 1

    # M2..M6, ambos trimestres y 6M: las dos filas siguen siendo comparables,
    # el mes negativo NO se propaga a otros periodos.
    for period in ("M2", "M3", "M4", "M5", "M6", "RECENT_3M", "OLDER_3M", "6M"):
        assert result.periods[period].n_comparable == 2, f"{period} deberia tener 2 comparables"

    # El estado global del cliente nunca es ERROR por esto (fichero valido).
    assert result.file_valid is True
    assert result.status == "SUCCESS_WITH_WARNINGS"

    # El chequeo de historico negativo es WARNING, localizado en M1.
    assert result.periods["M1"].status == "WARNING"
    assert "NEGATIVE_HISTORY" in [i.code for i in result.periods["M1"].quality.issues]
    for period in ("M2", "M3", "M4", "M5", "M6", "RECENT_3M", "OLDER_3M", "6M"):
        assert "NEGATIVE_HISTORY" not in [i.code for i in result.periods[period].quality.issues]

    # Se destaca explicitamente que la fila 1001 sigue siendo comparable en 6M.
    highlights = [i for i in result.quality.issues if i.code == "NEGATIVE_HISTORY_ROW_COMPARABLE_IN_6M"]
    assert len(highlights) == 1
    assert highlights[0].details["rows"][0]["id_configuration"] == 1001


def test_analyze_client_invalid_file_is_error_status_with_no_periods():
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99997_Broken.csv"), file_label="99997_Broken", id_from_filename=99997,
        dataframe=None, read_repaired=False, is_valid=False, folder_name="99997_Broken",
    )
    result = analyze_client(source)
    assert result.file_valid is False
    assert result.status == "ERROR"
    assert result.periods == {}


# --------------------------------------------------------------------------
# Item 9: COMPARISON_STATUS original y motivo derivado por periodo se
# conservan por separado; no se sustituye NOT_COMPARABLE_MISSING_VALIDATION
# por una categoria generica como MISSING_SCP_AND_ML.
# --------------------------------------------------------------------------

def test_comparison_status_distribution_kept_separate_from_derived_reason():
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1],
        "ID_CONFIGURATION": [1, 2],
        "COMPARISON_STATUS": ["NOT_COMPARABLE_MISSING_VALIDATION", "NOT_COMPARABLE_MISSING_VALIDATION"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0, 100.0],
            scp_forecast=[None, None], scp_abs_error=[None, None], scp_wape=[None, None],
            ml_forecast=[None, None], ml_abs_error=[None, None], ml_wape=[None, None],
            winner_method=[None, None],
        )

    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99998_Synthetic.csv"), file_label="99998_Synthetic", id_from_filename=99998,
        dataframe=df, read_repaired=False, id_client=99998, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99998_Synthetic",
    )
    result = analyze_client(source)

    # La distribucion global conserva la categoria ORIGINAL del CSV tal cual,
    # sin renombrarla ni sustituirla.
    assert result.comparison_status_distribution == {"NOT_COMPARABLE_MISSING_VALIDATION": 2}

    # El motivo DERIVADO especifico del periodo (distinto, propio del nucleo)
    # convive con el anterior sin sustituirlo.
    period_6m = result.periods["6M"]
    assert period_6m.not_comparable_reason_counts == {"MISSING_SCP_AND_ML": 2}
    assert period_6m.comparison_status_counts_not_comparable == {"NOT_COMPARABLE_MISSING_VALIDATION": 2}
