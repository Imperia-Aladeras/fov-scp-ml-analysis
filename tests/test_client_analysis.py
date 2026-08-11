import math
from dataclasses import fields
from pathlib import Path

import pandas as pd

from src.client_analysis import (
    COMPARISON_STATUS_NULL_BUCKET,
    PeriodResult,
    _value_counts_dict_with_null_bucket,
    analyze_client,
    backend_comparable_mask_6m,
    period_comparable_mask,
)
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


# --------------------------------------------------------------------------
# Fase 4: poblacion canonica 6M/global = COMPARISON_STATUS=="COMPARABLE" en
# solitario (sin HAS_BASE_CANDIDATE ni mascara local de completitud). La
# mascara local queda solo como auditoria/reconciliacion.
# --------------------------------------------------------------------------

def test_backend_comparable_mask_6m_is_only_comparison_status():
    df = pd.DataFrame({
        "COMPARISON_STATUS": ["COMPARABLE", "NOT_COMPARABLE_NO_HISTORY", None, "COMPARABLE"],
    })
    mask = backend_comparable_mask_6m(df)
    assert mask.tolist() == [True, False, False, True]


def test_6m_comparable_mask_ignores_local_column_completeness():
    """
    Fila COMPARABLE segun el backend pero con SCP_TOTAL_ABS_ERROR_6M nulo
    (lo que la excluiria de la mascara local `period_comparable_mask`):
    debe permanecer en la poblacion canonica de 6M.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1],
        "ID_CONFIGURATION": [1],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0], scp_forecast=[120.0], scp_abs_error=[20.0], scp_wape=[0.2],
            ml_forecast=[110.0], ml_abs_error=[10.0], ml_wape=[0.1], winner_method=["ML"],
        )
    pcols_6m = period_columns("6M")
    df[pcols_6m.scp_total_abs_error] = [None]

    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99995_Synthetic.csv"), file_label="99995_Synthetic", id_from_filename=99995,
        dataframe=df, read_repaired=False, id_client=99995, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99995_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    # Poblacion 6M: la fila sigue comparable pese a faltar un input de WAPE.
    assert period_6m.comparable_mask.tolist() == [True]
    assert period_6m.n_comparable == 1

    # Evaluabilidad por metrica: SCP_WAPE_GLOBAL/mejora quedan no evaluables,
    # ML_WAPE_GLOBAL no se ve afectado (input distinto, completo).
    assert math.isnan(period_6m.wape["scp_wape_global"])
    assert math.isnan(period_6m.wape["improvement_pct"])
    assert not math.isnan(period_6m.wape["ml_wape_global"])
    assert math.isclose(period_6m.wape["ml_wape_global"], 10 / 100, rel_tol=1e-9)

    # Se documenta explicitamente, no se calcula en silencio ignorando la fila.
    assert "COMPARABLE_MISSING_WAPE_INPUTS" in [i.code for i in period_6m.quality.issues]


def test_6m_comparable_row_with_missing_row_wape_keeps_global_wape_evaluable():
    """
    Fila COMPARABLE con SCP_WAPE_6M/ML_WAPE_6M nulos pero
    TOTAL_HISTORY_6M/*_TOTAL_ABS_ERROR_6M completos: esas columnas no son
    input de period_wape_global, asi que el WAPE global sigue siendo
    evaluable; solo la mejora por serie (no la agregada) se ve afectada por
    filas concretas sin WAPE (comportamiento ya existente de
    relative_improvement_row, sin cambios).
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1],
        "ID_CONFIGURATION": [1],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0], scp_forecast=[120.0], scp_abs_error=[20.0], scp_wape=[0.2],
            ml_forecast=[110.0], ml_abs_error=[10.0], ml_wape=[0.1], winner_method=["ML"],
        )
    pcols_6m = period_columns("6M")
    df[pcols_6m.scp_wape] = [None]
    df[pcols_6m.ml_wape] = [None]

    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99994_Synthetic.csv"), file_label="99994_Synthetic", id_from_filename=99994,
        dataframe=df, read_repaired=False, id_client=99994, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99994_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.comparable_mask.tolist() == [True]
    assert period_6m.n_comparable == 1
    assert math.isclose(period_6m.wape["scp_wape_global"], 20 / 100, rel_tol=1e-9)
    assert math.isclose(period_6m.wape["ml_wape_global"], 10 / 100, rel_tol=1e-9)
    assert math.isclose(period_6m.wape["improvement_pct"], (0.2 - 0.1) / 0.2 * 100, rel_tol=1e-9)
    assert "COMPARABLE_MISSING_WAPE_INPUTS" not in [i.code for i in period_6m.quality.issues]


def test_6m_not_comparable_breakdown_does_not_filter_by_has_base_candidate():
    """
    Test defensivo (decision cerrada Fase 4): HAS_BASE_CANDIDATE no debe
    filtrar la poblacion 6M ni su breakdown de motivos por la puerta de
    atras. Fila con HAS_BASE_CANDIDATE=0 y
    COMPARISON_STATUS="NOT_COMPARABLE_RUN_FAILED": no pertenece a
    comparable_mask (correcto, su status no es COMPARABLE) pero SI debe
    aparecer en el breakdown de motivos de 6M.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 0],
        "ID_CONFIGURATION": [1, 2],
        "COMPARISON_STATUS": ["COMPARABLE", "NOT_COMPARABLE_RUN_FAILED"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0, 100.0],
            scp_forecast=[120.0, 120.0], scp_abs_error=[20.0, 20.0], scp_wape=[0.2, 0.2],
            ml_forecast=[110.0, 110.0], ml_abs_error=[10.0, 10.0], ml_wape=[0.1, 0.1],
            winner_method=["ML", "ML"],
        )
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99993_Synthetic.csv"), file_label="99993_Synthetic", id_from_filename=99993,
        dataframe=df, read_repaired=False, id_client=99993, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99993_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.comparable_mask.tolist() == [True, False]
    assert period_6m.n_comparable == 1
    assert period_6m.comparison_status_counts_not_comparable == {"NOT_COMPARABLE_RUN_FAILED": 1}


def test_6m_null_comparison_status_excluded_and_counted_in_diagnostic_bucket():
    """
    COMPARISON_STATUS nulo: no pertenece a la poblacion 6M/global y se
    contabiliza en un bucket diagnostico propio de reporting, distinto de
    los strings oficiales NOT_COMPARABLE_* del backend.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1],
        "ID_CONFIGURATION": [1, 2],
        "COMPARISON_STATUS": ["COMPARABLE", None],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0, 100.0],
            scp_forecast=[120.0, 120.0], scp_abs_error=[20.0, 20.0], scp_wape=[0.2, 0.2],
            ml_forecast=[110.0, 110.0], ml_abs_error=[10.0, 10.0], ml_wape=[0.1, 0.1],
            winner_method=["ML", "ML"],
        )
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99992_Synthetic.csv"), file_label="99992_Synthetic", id_from_filename=99992,
        dataframe=df, read_repaired=False, id_client=99992, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99992_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.comparable_mask.tolist() == [True, False]
    assert period_6m.n_comparable == 1
    assert period_6m.comparison_status_counts_not_comparable == {"SIN_COMPARISON_STATUS": 1}


def test_partial_periods_unaffected_by_backend_6m_mask():
    """
    Regresion: M1..M6, RECENT_3M, OLDER_3M siguen usando exclusivamente
    `period_comparable_mask` (columnas propias del periodo), nunca
    COMPARISON_STATUS. Fila con COMPARISON_STATUS="COMPARABLE" pero sin
    forecast ML en M1: debe seguir excluida de M1 (mascara local), aunque
    permanezca en la poblacion de 6M.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1],
        "ID_CONFIGURATION": [1],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0], scp_forecast=[120.0], scp_abs_error=[20.0], scp_wape=[0.2],
            ml_forecast=[110.0], ml_abs_error=[10.0], ml_wape=[0.1], winner_method=["ML"],
        )
    pcols_m1 = period_columns("M1")
    df[pcols_m1.ml_total_forecast] = [None]
    df[pcols_m1.ml_total_abs_error] = [None]
    df[pcols_m1.ml_wape] = [None]

    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99991_Synthetic.csv"), file_label="99991_Synthetic", id_from_filename=99991,
        dataframe=df, read_repaired=False, id_client=99991, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99991_Synthetic",
    )
    result = analyze_client(source)

    assert result.periods["M1"].comparable_mask.tolist() == [False]
    assert result.periods["M1"].n_comparable == 0
    for period in ("M2", "M3", "M4", "M5", "M6", "RECENT_3M", "OLDER_3M"):
        assert result.periods[period].comparable_mask.tolist() == [True]
    assert result.periods["6M"].comparable_mask.tolist() == [True]


def test_6m_counters_use_canonical_universe_not_has_base_candidate_run_failed():
    """
    Test defensivo A (decision Fase 4): el universo canonico de 6M es el
    mismo sobre el que se aplica COMPARISON_STATUS, no HAS_BASE_CANDIDATE.
    Fila HAS_BASE_CANDIDATE=0, COMPARISON_STATUS="NOT_COMPARABLE_RUN_FAILED":
    forma parte del universo 6M pese a no ser candidata.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [0],
        "ID_CONFIGURATION": [1],
        "COMPARISON_STATUS": ["NOT_COMPARABLE_RUN_FAILED"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0], scp_forecast=[120.0], scp_abs_error=[20.0], scp_wape=[0.2],
            ml_forecast=[110.0], ml_abs_error=[10.0], ml_wape=[0.1], winner_method=["ML"],
        )
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99990_Synthetic.csv"), file_label="99990_Synthetic", id_from_filename=99990,
        dataframe=df, read_repaired=False, id_client=99990, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99990_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.n_candidates == 1  # universo canonico 6M (len(df)), no HAS_BASE_CANDIDATE
    assert period_6m.n_comparable == 0
    assert period_6m.n_not_comparable == 1
    assert period_6m.pct_comparable == 0.0
    assert period_6m.comparison_status_counts_not_comparable == {"NOT_COMPARABLE_RUN_FAILED": 1}

    # Periodos parciales mantienen su semantica actual basada en candidate_mask.
    assert result.periods["M1"].n_candidates == 0


def test_6m_counters_use_canonical_universe_not_has_base_candidate_comparable():
    """Test defensivo B (decision Fase 4): simetrico al anterior, con status COMPARABLE."""
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [0],
        "ID_CONFIGURATION": [1],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0], scp_forecast=[120.0], scp_abs_error=[20.0], scp_wape=[0.2],
            ml_forecast=[110.0], ml_abs_error=[10.0], ml_wape=[0.1], winner_method=["ML"],
        )
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99989_Synthetic.csv"), file_label="99989_Synthetic", id_from_filename=99989,
        dataframe=df, read_repaired=False, id_client=99989, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99989_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.n_candidates == 1
    assert period_6m.n_comparable == 1
    assert period_6m.n_not_comparable == 0
    assert period_6m.pct_comparable == 100.0

    assert result.periods["M1"].n_candidates == 0


def test_value_counts_dict_with_null_bucket_treats_none_nan_empty_and_whitespace_as_blank():
    series = pd.Series(["COMPARABLE", None, "", "   ", "NOT_COMPARABLE_NO_HISTORY"])
    counts = _value_counts_dict_with_null_bucket(series)
    assert counts == {
        "COMPARABLE": 1,
        "NOT_COMPARABLE_NO_HISTORY": 1,
        COMPARISON_STATUS_NULL_BUCKET: 3,
    }


def test_6m_blank_and_whitespace_comparison_status_counted_in_diagnostic_bucket():
    """
    COMPARISON_STATUS vacio ("") o formado unicamente por espacios se trata
    igual que nulo: no pertenece a la poblacion 6M y se contabiliza en el
    mismo bucket diagnostico SIN_COMPARISON_STATUS, sin normalizar ni
    renombrar ningun otro valor.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1, 1],
        "ID_CONFIGURATION": [1, 2, 3],
        "COMPARISON_STATUS": ["COMPARABLE", "", "   "],
    })
    for period in ALL_PERIODS:
        _set_period(
            df, period,
            total_history=[100.0, 100.0, 100.0],
            scp_forecast=[120.0, 120.0, 120.0], scp_abs_error=[20.0, 20.0, 20.0], scp_wape=[0.2, 0.2, 0.2],
            ml_forecast=[110.0, 110.0, 110.0], ml_abs_error=[10.0, 10.0, 10.0], ml_wape=[0.1, 0.1, 0.1],
            winner_method=["ML", "ML", "ML"],
        )
    source = ClientSource(
        csv_path=Path("TA_FOV_SCP_ML_99988_Synthetic.csv"), file_label="99988_Synthetic", id_from_filename=99988,
        dataframe=df, read_repaired=False, id_client=99988, id_batch=[1], id_run_staging=[1],
        source_run_id=[1], n_rows=len(df), is_valid=True, folder_name="99988_Synthetic",
    )
    result = analyze_client(source)
    period_6m = result.periods["6M"]

    assert period_6m.comparable_mask.tolist() == [True, False, False]
    assert period_6m.n_comparable == 1
    assert period_6m.comparison_status_counts_not_comparable == {"SIN_COMPARISON_STATUS": 2}


def test_period_result_has_no_new_field_for_6m_local_audit_mask():
    """
    Fase 4 (decision cerrada): sin campos nuevos en PeriodResult salvo
    necesidad demostrada. La mascara local de 6M vive como variable local
    dentro de _analyze_period, no se persiste.
    """
    field_names = {f.name for f in fields(PeriodResult)}
    assert "comparable_mask_local_audit" not in field_names
    assert "local_mask" not in field_names
