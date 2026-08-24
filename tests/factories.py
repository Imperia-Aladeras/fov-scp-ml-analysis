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


def build_volume_bucket_client_dataframe() -> pd.DataFrame:
    """
    9 filas comparables en 6M con TOTAL_HISTORY_6M = [10, 20, ..., 90]: 9
    valores distintos -> terciles limpios 3/3/3 (RELATIVE_LOW/MEDIUM/HIGH,
    ver src/phase8.compute_volume_buckets), a diferencia de
    build_synthetic_client_dataframe (solo 2 filas comparables, siempre
    NOT_ASSIGNABLE por REASON_N_LT_3). Bias con signo alternado
    (sobreprevision/infraprevision: forecast por encima/debajo del historico
    en filas pares/impares) y winner alternado ML/SCP para poder ejercitar
    Fase 8 (Bias + volumen) con variedad real, no un unico caso degenerado.
    Los mismos ratios (WAPE, signo de Bias) se mantienen en M1..M6/RECENT_3M/
    OLDER_3M -- solo escalados por el peso de cada periodo dentro de 6M --
    para que check_aggregate_vs_monthly_sum no genere warnings de reconciliacion.
    """
    n = 9
    history_6m = [float(10 * (i + 1)) for i in range(n)]  # 10.0 .. 90.0

    def _scaled(period_multiplier: float, scp_frac: float, ml_fracs: list[float]) -> dict:
        history = [h * period_multiplier for h in history_6m]
        scp_abs = [h * scp_frac for h in history]
        ml_abs = [h * f for h, f in zip(history, ml_fracs)]
        # Signo alternado (sobreprevision en filas pares, infraprevision en impares).
        scp_fc = [h + e if i % 2 == 0 else h - e for i, (h, e) in enumerate(zip(history, scp_abs))]
        ml_fc = [h + e if i % 2 == 0 else h - e for i, (h, e) in enumerate(zip(history, ml_abs))]
        scp_wape = [scp_frac] * n
        ml_wape = ml_fracs
        winner = ["ML" if f < scp_frac else "SCP" for f in ml_fracs]
        return dict(
            total_history=history, scp_forecast=scp_fc, scp_abs_error=scp_abs, scp_wape=scp_wape,
            ml_forecast=ml_fc, ml_abs_error=ml_abs, ml_wape=ml_wape, winner_method=winner,
        )

    scp_frac = 0.2
    ml_fracs = [0.1 if i % 2 == 0 else 0.3 for i in range(n)]  # ML gana en filas pares, SCP en impares

    models_ml = ["AutoETS", "AutoARIMA"]
    models_scp = ["x11 seasonal", "SeasonalNaive"]
    classifications = ["smooth", "erratic"]

    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1] * n,
        "ID_CLIENT": [66666] * n,
        "ID_CONFIGURATION": list(range(4001, 4001 + n)),
        "VALUE_LEVEL_1": [f"Cat {i}" for i in range(n)],
        "VALUE_LEVEL_2": [None] * n, "VALUE_LEVEL_3": [None] * n,
        "VALUE_LEVEL_4": [None] * n, "VALUE_LEVEL_5": [None] * n,
        "ML_BEST_MODEL": [models_ml[i % 2] for i in range(n)],
        "SCP_BEST_MODEL": [models_scp[i % 2] for i in range(n)],
        "ML_CLASSIFICATION": [classifications[i % 2] for i in range(n)],
        "ML_TYPE": [classifications[i % 2] for i in range(n)],
        "SERIES_CLASSIFICATION": [classifications[i % 2] for i in range(n)],
        "SCP_CLASSIFICATION": [classifications[i % 2] for i in range(n)],
        "COMPARISON_STATUS": ["COMPARABLE"] * n,
    })

    for month in [f"M{i}" for i in range(1, 7)]:
        set_period(df, month, **_scaled(1.0 / 6, scp_frac, ml_fracs))
    for quarter in ("RECENT_3M", "OLDER_3M"):
        set_period(df, quarter, **_scaled(0.5, scp_frac, ml_fracs))
    set_period(df, "6M", **_scaled(1.0, scp_frac, ml_fracs))
    return df


def build_volume_bucket_client_result():
    from src.client_analysis import analyze_client

    df = build_volume_bucket_client_dataframe()
    return analyze_client(make_client_source(df, 66666, "VolumeBuckets"))


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


def _build_phase8_not_assignable_dataframe(id_client: int, classification: str) -> pd.DataFrame:
    """
    2 filas comparables en 6M (COMPARISON_STATUS == COMPARABLE): menos de 3
    series comparables -> volumen NOT_ASSIGNABLE (REASON_N_LT_3, ver
    src.phase8.compute_volume_buckets), a diferencia de
    build_volume_bucket_client_dataframe (9 filas, terciles limpios). Usada
    por build_phase8_global_multi_client_results (Fase 8D) para forzar
    n_clients_with_not_assignable_volume >= 1 en el fixture global.
    """
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1],
        "ID_CLIENT": [id_client, id_client],
        "ID_CONFIGURATION": [5001, 5002],
        "VALUE_LEVEL_1": ["Cat A", "Cat B"],
        "VALUE_LEVEL_2": [None, None], "VALUE_LEVEL_3": [None, None],
        "VALUE_LEVEL_4": [None, None], "VALUE_LEVEL_5": [None, None],
        "ML_BEST_MODEL": ["AutoETS", "AutoARIMA"], "SCP_BEST_MODEL": ["x11 seasonal", "SeasonalNaive"],
        "ML_CLASSIFICATION": [classification, classification], "ML_TYPE": [classification, classification],
        "SERIES_CLASSIFICATION": [classification, classification], "SCP_CLASSIFICATION": [classification, classification],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE"],
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M", "6M"]:
        set_period(
            df, period,
            total_history=[100.0, 200.0], scp_forecast=[120.0, 180.0], scp_abs_error=[20.0, 20.0], scp_wape=[0.2, 0.1],
            ml_forecast=[110.0, 220.0], ml_abs_error=[10.0, 20.0], ml_wape=[0.1, 0.1],
            winner_method=["ML", "SCP"],
        )
    return df


def build_phase8_global_multi_client_results() -> list:
    """
    Fixture global de Fase 8D (reporting de GlobalAnalysisResult.periods["6M"].phase8):
    3 clientes disenados para ejercitar Phase8GlobalDiagnostics con variedad
    real, no un unico caso degenerado:
      - 91001_VolumeA: mismo patron que build_volume_bucket_client_dataframe
        (9 filas comparables, terciles limpios LOW/MEDIUM/HIGH por cliente,
        Bias con signo alternado dentro de cada bucket via forecast por
        encima/debajo del historico en filas pares/impares),
        SERIES_CLASSIFICATION smooth/erratic.
      - 91002_VolumeB: mismo patron de volumen (mismos TOTAL_HISTORY_6M,
        buckets propios de ESTE cliente -- nunca comparables en magnitud con
        los de VolumeA), pero SERIES_CLASSIFICATION smooth/intermittent: al
        agregar globalmente, cada VOLUME_BUCKET recibe series de mas de una
        clasificacion (classification_volume_cross con variedad real).
      - 91003_NotAssignable: solo 2 filas comparables en 6M -> volumen
        NOT_ASSIGNABLE para todo el cliente (REASON_N_LT_3), para que
        n_clients_with_not_assignable_volume >= 1 y aparezca una fila
        SERIES_CLASSIFICATION x NOT_ASSIGNABLE en el cruce global.
    Todos los grupos resultantes tienen pocas series (n_comparable < 10):
    small_sample=True es el caso tipico de este fixture, no la excepcion.
    """
    from src.client_analysis import analyze_client

    df_a = build_volume_bucket_client_dataframe().copy()
    df_a["ID_CLIENT"] = 91001
    client_a = analyze_client(make_client_source(df_a, 91001, "VolumeA"))

    df_b = build_volume_bucket_client_dataframe().copy()
    df_b["ID_CLIENT"] = 91002
    classifications_b = ["smooth", "intermittent"]
    n = len(df_b)
    for col in ("ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION", "SCP_CLASSIFICATION"):
        df_b[col] = [classifications_b[i % 2] for i in range(n)]
    client_b = analyze_client(make_client_source(df_b, 91002, "VolumeB"))

    df_c = _build_phase8_not_assignable_dataframe(id_client=91003, classification="lumpy")
    client_c = analyze_client(make_client_source(df_c, 91003, "NotAssignable"))

    return [client_a, client_b, client_c]


def build_phase8_global_multi_client_analysis_result():
    from src.global_analysis import analyze_global

    return analyze_global(build_phase8_global_multi_client_results())


def build_phase8_global_missing_client_results() -> list:
    """
    2 clientes para probar que basta con que UN cliente participante no
    tenga PeriodResult.phase8 (is_backend_6m False -- sin columna
    COMPARISON_STATUS en 6M) para que GlobalPeriodResult.phase8 sea None,
    independientemente del resto (ver
    src.global_analysis._build_phase8_global_if_all_clients_ready). Caso
    DISTINTO de una lista global vacia (que produce Phase8 PRESENTE pero
    vacio, no None, por la evaluacion vacua de `all(...)` sobre lista vacia):
    aqui SI hay clientes participantes, solo que uno de ellos no calculo
    Fase 8 individual.
    """
    from src.client_analysis import analyze_client

    with_backend = analyze_client(make_client_source(build_synthetic_client_dataframe(), 99999, "Synthetic"))

    df_no_backend = build_synthetic_client_dataframe().drop(columns=["COMPARISON_STATUS"])
    df_no_backend["ID_CLIENT"] = 77779
    without_backend = analyze_client(make_client_source(df_no_backend, 77779, "NoBackend"))

    return [with_backend, without_backend]


def build_phase8_global_null_classification_results() -> list:
    """
    1 cliente, 3 filas comparables en 6M, con SERIES_CLASSIFICATION (y
    ML_CLASSIFICATION/ML_TYPE/SCP_CLASSIFICATION) nula en 1 de las 3 filas.
    El nucleo (src.phase8.category_performance_table_with_bias /
    classification_volume_cross_table, via MISSING_CATEGORY_LABEL de
    src.models.category_performance_table) ya normaliza esa fila a la
    categoria "(sin clasificar)" -- NUNCA "nan"/"None", NUNCA una fila
    aparte por posicion, siempre agrupada bajo esa unica etiqueta. Este
    fixture existe para que el reporting GLOBAL (Markdown/Excel/HTML) tenga
    cobertura explicita de ese caso, sin tocar el nucleo.
    """
    from src.client_analysis import analyze_client

    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 1, 1],
        "ID_CLIENT": [92001, 92001, 92001],
        "ID_CONFIGURATION": [6001, 6002, 6003],
        "VALUE_LEVEL_1": ["Cat A", "Cat B", "Cat C"],
        "VALUE_LEVEL_2": [None, None, None], "VALUE_LEVEL_3": [None, None, None],
        "VALUE_LEVEL_4": [None, None, None], "VALUE_LEVEL_5": [None, None, None],
        "ML_BEST_MODEL": ["AutoETS", "AutoETS", "AutoETS"], "SCP_BEST_MODEL": ["x11 seasonal"] * 3,
        "ML_CLASSIFICATION": ["smooth", None, "smooth"], "ML_TYPE": ["smooth_ok", None, "smooth_ok"],
        "SERIES_CLASSIFICATION": ["smooth", None, "smooth"], "SCP_CLASSIFICATION": ["smooth", None, "smooth"],
        "COMPARISON_STATUS": ["COMPARABLE", "COMPARABLE", "COMPARABLE"],
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M", "6M"]:
        set_period(
            df, period,
            total_history=[100.0, 100.0, 100.0], scp_forecast=[120.0, 120.0, 120.0],
            scp_abs_error=[20.0, 20.0, 20.0], scp_wape=[0.2, 0.2, 0.2],
            ml_forecast=[110.0, 110.0, 110.0], ml_abs_error=[10.0, 10.0, 10.0], ml_wape=[0.1, 0.1, 0.1],
            winner_method=["ML", "ML", "ML"],
        )
    client = analyze_client(make_client_source(df, 92001, "NullClass"))
    return [client]


def build_phase8_global_null_classification_analysis_result():
    from src.global_analysis import analyze_global

    return analyze_global(build_phase8_global_null_classification_results())
