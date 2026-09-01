import math

import pandas as pd
import pytest

from src.client_analysis import analyze_client
from src.global_analysis import (
    analyze_global,
    build_client_period_table,
    build_global_period_result,
    global_category_performance_table,
    global_pareto_clients,
    global_pareto_series,
)
from src.periods import ALL_PERIODS, period_columns
from tests.factories import (
    build_multi_client_results,
    build_negative_net_multi_client_results,
    build_synthetic_client_dataframe,
    make_client_source,
    set_period,
)


def test_analyze_global_includes_only_file_valid_clients():
    results = build_multi_client_results()
    global_result = analyze_global(results)
    labels = {r.source.file_label for r in global_result.client_results}
    assert labels == {"99999_Synthetic", "88888_NoComparable", "77777_AllMlWins"}
    assert global_result.invalid_results == []


def test_global_period_result_weighted_wape_is_not_a_simple_average():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")

    # mixed (99999): scp_err=180, ml_err=240, history=1200 (fila 0 gana ML, fila 1 gana SCP)
    # all_ml (77777): history=600*2=1200, scp_err=60*2*2=... construido para dar wape 0.2/0.1
    # no_comparable (88888): aporta 0 a las sumas.
    assert gp.n_clients == 3
    assert gp.history_sum > 0
    naive_avg = (0.2 + 0.1) / 2  # promedio simple de dos WAPE cualquiera, para contraste
    assert not math.isclose(gp.scp_wape_global, naive_avg, rel_tol=1e-2) or gp.scp_wape_global != naive_avg


def test_global_period_result_client_perspective_weights_each_client_equally():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    # Solo 2 de los 3 clientes tienen mejora calculable (el NoComparable aporta NaN, se excluye).
    assert gp.client_improvement_stats["count"] == 2


def test_client_improvement_stats_distinguishes_total_evaluable_and_missing():
    """
    Item 1: N_CLIENTES_TOTAL, N_CLIENTES_EVALUABLES y N_CLIENTES_SIN_PERFORMANCE
    deben ser distintos y coherentes cuando hay clientes sin ninguna serie
    comparable (88888_NoComparable en este fixture).
    """
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    stats = gp.client_improvement_stats

    assert stats["n_total"] == 3
    assert stats["n_evaluable"] == 2
    assert stats["n_missing"] == 1
    assert stats["n_total"] == stats["n_evaluable"] + stats["n_missing"]
    # mixed (99999) empeora a nivel de cliente (-33.3%), all_ml (77777) mejora (+50%)
    # -> 1 de los 2 evaluables mejora. El NoComparable (88888) no cuenta ni mejora ni empeora.
    assert stats["n_improved"] == 1
    assert stats["n_worse"] == 1
    # El porcentaje de clientes que mejoran debe calcularse sobre evaluables (2), no sobre el total (3).
    assert math.isclose(stats["pct_improved"], 50.0)
    assert not math.isclose(stats["pct_improved"], 1 / 3 * 100)


def test_client_improvement_stats_does_not_collapse_clients_sharing_the_same_file_label():
    """
    Fase 3: un unico CSV fisico puede particionarse en varios ID_CLIENT, y
    todos ellos comparten el mismo file_label (derivado del nombre del
    fichero fisico, no de cada cliente). _client_improvement_series debe
    indexar por ID_CLIENT, no por file_label: de lo contrario, dos clientes
    con el mismo file_label colapsarian silenciosamente en una unica entrada
    del diccionario y uno de los dos desaparaceria de las estadisticas por
    cliente (regresion real detectada al adaptar el pipeline a Fase 3).
    """
    df_a = build_synthetic_client_dataframe()
    df_a["ID_CLIENT"] = 10204
    source_a = make_client_source(df_a, 10204, "FullExport")

    df_b = build_synthetic_client_dataframe()
    df_b["ID_CLIENT"] = 10461
    source_b = make_client_source(df_b, 10461, "FullExport")

    # mismo CSV fisico: mismo file_label/csv_path, ID_CLIENT distinto
    source_b.file_label = source_a.file_label
    source_b.csv_path = source_a.csv_path

    result_a = analyze_client(source_a)
    result_b = analyze_client(source_b)
    assert result_a.source.file_label == result_b.source.file_label
    assert result_a.source.id_client != result_b.source.id_client
    # ambos evaluables: PeriodResult.wape.improvement_pct no es NaN para ninguno
    assert result_a.periods["6M"].wape.get("improvement_pct") is not None
    assert result_b.periods["6M"].wape.get("improvement_pct") is not None

    gp = build_global_period_result([result_a, result_b], "6M")
    stats = gp.client_improvement_stats

    # sin la colision de clave, ambos clientes deben contarse por separado
    assert stats["n_total"] == 2
    assert stats["n_evaluable"] == 2
    assert stats["count"] == 2


def test_global_period_result_series_perspective_uses_raw_rows_not_client_medians():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    # mixed aporta 2 filas comparables, all_ml aporta 2 filas comparables -> 4 series en total.
    assert gp.series_improvement_stats["count"] == 4


def test_global_period_result_winner_counts_sum_across_clients():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    # mixed: 1 ML + 1 SCP. all_ml: 2 ML. Total: 3 ML, 1 SCP.
    assert gp.winner_counts["ML"]["n"] == 3
    assert gp.winner_counts["SCP"]["n"] == 1


def test_reduction_and_deterioration_tables_percentages_sum_to_100_within_group():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    if not gp.client_reduction_table.empty:
        assert math.isclose(gp.client_reduction_table["PCT_OF_POSITIVE_REDUCTION"].sum(), 100.0, abs_tol=1e-6)
    if not gp.client_deterioration_table.empty:
        assert math.isclose(gp.client_deterioration_table["PCT_OF_TOTAL_DETERIORATION"].sum(), 100.0, abs_tol=1e-6)


def test_negative_net_result_client_is_in_deterioration_table_not_top_contributor():
    """
    Item 2 (regresion): con un resultado neto negativo (un cliente mejora
    poco, otro empeora mucho), el cliente que empeora:
      - aparece en la tabla de deterioro, no en la de reduccion;
      - no se identifica como principal contribuidor a la reduccion;
      - los porcentajes de reduccion positiva suman 100%;
      - los porcentajes de deterioro suman 100%;
      - nunca se calcula un porcentaje sobre la reduccion neta (que es negativa).
    """
    results = build_negative_net_multi_client_results()
    gp = build_global_period_result(results, "6M")

    assert gp.reduction_totals["REDUCCION_NETA"] < 0
    assert gp.reduction_totals["REDUCCION_POSITIVA_TOTAL"] == 10.0
    assert gp.reduction_totals["DETERIORO_TOTAL_ABSOLUTO"] == 1000.0

    reducers = gp.client_reduction_table
    worseners = gp.client_deterioration_table

    assert set(reducers["ETIQUETA"]) == {"55501_PositiveClient"}
    assert set(worseners["ETIQUETA"]) == {"55502_NegativeClient"}
    # DISPLAY_NAME (Fase 5) es aditivo: convive con ETIQUETA sin sustituirla.
    assert set(reducers["DISPLAY_NAME"]) == {"PositiveClient"}
    assert set(worseners["DISPLAY_NAME"]) == {"NegativeClient"}

    # El cliente negativo NUNCA aparece en la tabla de clientes que reducen error.
    assert "55502_NegativeClient" not in set(reducers["ETIQUETA"])

    # Los porcentajes de contribucion positiva suman 100% (solo hay un reductor: el 100% es suyo).
    assert math.isclose(reducers["PCT_OF_POSITIVE_REDUCTION"].sum(), 100.0, abs_tol=1e-6)
    # Los porcentajes de deterioro suman 100% (solo hay un cliente que empeora).
    assert math.isclose(worseners["PCT_OF_TOTAL_DETERIORATION"].sum(), 100.0, abs_tol=1e-6)

    # Ninguna columna de las tablas expone un porcentaje calculado sobre la reduccion neta.
    assert "PCT_OF_TOTAL_REDUCTION" not in reducers.columns
    assert "PCT_OF_TOTAL_REDUCTION" not in worseners.columns


def test_build_client_period_table_has_one_row_per_client():
    results = build_multi_client_results()
    table = build_client_period_table(results, "6M")
    assert len(table) == 3
    assert set(table["ID_CLIENT"]) == {99999, 88888, 77777}


def test_build_client_period_table_display_name_is_additive_alongside_etiqueta():
    """
    Fase 5: DISPLAY_NAME se anade en paralelo a ETIQUETA, que conserva su
    semantica original (derivada de file_label), sin sustituirla.
    """
    results = build_multi_client_results()
    table = build_client_period_table(results, "6M")
    assert "DISPLAY_NAME" in table.columns
    assert "ETIQUETA" in table.columns
    row = table[table["ID_CLIENT"] == 99999].iloc[0]
    assert row["DISPLAY_NAME"] == "Synthetic"
    assert row["ETIQUETA"] == "99999_Synthetic"


def test_global_category_performance_table_aggregates_across_clients():
    results = build_multi_client_results()
    table = global_category_performance_table(results, "6M", "ML_BEST_MODEL")
    # AutoETS aparece en mixed (fila 0) y en las 2 filas de all_ml -> 3 series, 2 clientes.
    row = table[table["category"] == "AutoETS"].iloc[0]
    assert row["n_comparable"] == 3
    assert row["n_clients"] == 2


# --------------------------------------------------------------------------
# Fase 4: propagacion de no-evaluabilidad por metrica al agregado global.
# Un cliente COMPARABLE (poblacion 6M no cambia) pero no evaluable para una
# metrica concreta no debe desaparecer en silencio de la agregacion global
# (Perspectiva 1: WAPE/mejora global; Perspectiva 4: reduccion absoluta).
# Distingue explicitamente "B ausente" de "B presente pero no evaluable".
# --------------------------------------------------------------------------

def _build_single_client_df(id_client: int, history: float, scp_abs_error: float, ml_abs_error: float, winner: str) -> pd.DataFrame:
    scp_forecast = history + scp_abs_error
    ml_forecast = history + ml_abs_error
    scp_wape = scp_abs_error / history
    ml_wape = ml_abs_error / history
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1], "ID_CLIENT": [id_client], "ID_CONFIGURATION": [1],
        "VALUE_LEVEL_1": ["Cat"], "VALUE_LEVEL_2": [None], "VALUE_LEVEL_3": [None],
        "VALUE_LEVEL_4": [None], "VALUE_LEVEL_5": [None],
        "ML_BEST_MODEL": ["AutoETS"], "SCP_BEST_MODEL": ["x11 seasonal"],
        "ML_CLASSIFICATION": ["smooth"], "ML_TYPE": ["smooth_ok"],
        "SERIES_CLASSIFICATION": ["smooth"], "SCP_CLASSIFICATION": ["smooth"],
        "COMPARISON_STATUS": ["COMPARABLE"],
    })
    for period in ALL_PERIODS:
        set_period(
            df, period,
            total_history=[history], scp_forecast=[scp_forecast], scp_abs_error=[scp_abs_error], scp_wape=[scp_wape],
            ml_forecast=[ml_forecast], ml_abs_error=[ml_abs_error], ml_wape=[ml_wape], winner_method=[winner],
        )
    return df


def test_multi_client_global_aggregate_a_alone_baseline():
    """(A) Solo el Cliente A: agregado valido calculado unicamente con A."""
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    gp = build_global_period_result([result_a], "6M")
    assert math.isclose(gp.scp_wape_global, 0.1, rel_tol=1e-9)
    assert math.isclose(gp.ml_wape_global, 0.05, rel_tol=1e-9)
    assert math.isclose(gp.reduction_totals["REDUCCION_NETA"], 50.0, rel_tol=1e-9)


def test_multi_client_global_aggregate_b_evaluable_contributes_distinctly():
    """
    (B) [A, B] con B completamente evaluable: el agregado es el calculo
    conjunto real A+B. NO se exige ni se espera que coincida con (A); al
    contrario, se verifica que B contribuye de verdad.
    """
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    df_b = _build_single_client_df(60002, history=500.0, scp_abs_error=80.0, ml_abs_error=60.0, winner="SCP")
    result_b = analyze_client(make_client_source(df_b, 60002, "ClientB"))

    gp = build_global_period_result([result_a, result_b], "6M")

    expected_scp_wape = (100.0 + 80.0) / (1000.0 + 500.0)
    expected_ml_wape = (50.0 + 60.0) / (1000.0 + 500.0)
    assert math.isclose(gp.scp_wape_global, expected_scp_wape, rel_tol=1e-9)
    assert math.isclose(gp.ml_wape_global, expected_ml_wape, rel_tol=1e-9)
    assert math.isclose(gp.reduction_totals["REDUCCION_NETA"], (100.0 - 50.0) + (80.0 - 60.0), rel_tol=1e-9)

    # Explicitamente distinto de "solo A" (prueba que B contribuye de verdad).
    assert not math.isclose(gp.scp_wape_global, 0.1, rel_tol=1e-6)
    assert not math.isclose(gp.reduction_totals["REDUCCION_NETA"], 50.0, rel_tol=1e-6)


def test_multi_client_global_wape_nan_when_b_comparable_missing_history_never_recovers_a_only_value():
    """
    (C) [A, B] con B COMPARABLE pero con TOTAL_HISTORY_6M no evaluable: el
    WAPE global (depende del historico) queda NaN, sin recuperar en
    silencio el valor de "solo A". La reduccion absoluta no depende del
    historico, asi que sigue siendo evaluable con B incluido.
    """
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    df_b = _build_single_client_df(60003, history=500.0, scp_abs_error=80.0, ml_abs_error=60.0, winner="SCP")
    pcols_6m = period_columns("6M")
    df_b[pcols_6m.total_history] = [None]
    result_b = analyze_client(make_client_source(df_b, 60003, "ClientBIncompleteHistory"))

    # El cliente B sigue siendo comparable en 6M (la poblacion no cambia).
    assert result_b.periods["6M"].n_comparable == 1
    assert math.isnan(result_b.periods["6M"].wape["scp_wape_global"])

    gp = build_global_period_result([result_a, result_b], "6M")

    assert math.isnan(gp.scp_wape_global)
    assert math.isnan(gp.ml_wape_global)
    assert math.isnan(gp.global_improvement_pct)
    assert gp.scp_wape_global != 0.1  # nunca coincide con "solo A"

    # La reduccion absoluta no depende del historico: sigue siendo evaluable.
    assert math.isclose(gp.reduction_totals["REDUCCION_NETA"], (100.0 - 50.0) + (80.0 - 60.0), rel_tol=1e-9)


def test_multi_client_reduction_totals_nan_when_b_comparable_missing_abs_error_never_recovers_a_only_value():
    """
    (C) [A, B] con B COMPARABLE pero con ML_TOTAL_ABS_ERROR_6M no evaluable:
    ML_WAPE_GLOBAL, la mejora global y los tres totales de reduccion
    absoluta quedan NaN (nunca calculados ignorando a B). B no se fuerza a
    positive_mask ni negative_mask, y sigue visible con su NaN en la tabla
    por cliente. SCP_WAPE_GLOBAL (no depende de ML_TOTAL_ABS_ERROR) sigue
    evaluable de forma independiente.
    """
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    df_b = _build_single_client_df(60004, history=500.0, scp_abs_error=80.0, ml_abs_error=60.0, winner="SCP")
    pcols_6m = period_columns("6M")
    df_b[pcols_6m.ml_total_abs_error] = [None]
    result_b = analyze_client(make_client_source(df_b, 60004, "ClientBIncompleteAbsError"))

    assert result_b.periods["6M"].n_comparable == 1
    assert math.isnan(result_b.periods["6M"].abs_error_reduction_total)

    gp = build_global_period_result([result_a, result_b], "6M")

    assert not math.isnan(gp.scp_wape_global)  # independiente, no afectado
    assert math.isnan(gp.ml_wape_global)
    assert math.isnan(gp.global_improvement_pct)
    assert math.isnan(gp.reduction_totals["REDUCCION_NETA"])
    assert math.isnan(gp.reduction_totals["REDUCCION_POSITIVA_TOTAL"])
    assert math.isnan(gp.reduction_totals["DETERIORO_TOTAL_ABSOLUTO"])
    assert gp.reduction_totals["REDUCCION_NETA"] != 50.0  # nunca coincide con "solo A"

    # B no se fuerza a positive_mask ni negative_mask.
    assert "ClientBIncompleteAbsError" not in set(gp.client_reduction_table["ETIQUETA"])
    assert "ClientBIncompleteAbsError" not in set(gp.client_deterioration_table["ETIQUETA"])

    # B sigue visible en la tabla por cliente, con su valor NaN.
    table = build_client_period_table([result_a, result_b], "6M")
    row_b = table[table["ID_CLIENT"] == 60004].iloc[0]
    assert math.isnan(row_b["REDUCCION_ABSOLUTA"])


def test_global_pareto_only_populated_for_6m():
    results = build_multi_client_results()
    for period in ALL_PERIODS:
        gp = build_global_period_result(results, period)
        if period == "6M":
            assert gp.pareto_series is not None
            assert gp.pareto_clients is not None
        else:
            assert gp.pareto_series is None
            assert gp.pareto_clients is None


def test_client_reduction_tables_unaffected_by_new_pareto_fields():
    """Regresion: _client_reduction_and_deterioration_tables sigue exactamente igual."""
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    assert "PCT_OF_GROUP" not in gp.client_reduction_table.columns
    assert "RANK" not in gp.client_reduction_table.columns
    assert "PCT_OF_POSITIVE_REDUCTION" in gp.client_reduction_table.columns
    assert "PCT_OF_TOTAL_DETERIORATION" in gp.client_deterioration_table.columns
    assert gp.pareto_clients is not None
    assert gp.pareto_series is not None


def test_global_pareto_series_no_collision_when_clients_share_id_configuration():
    """
    Dos clientes con el mismo ID_CONFIGURATION (=1, valor por defecto de
    _build_single_client_df) no deben colapsar en una unica fila: la
    identidad global es ID_CLIENT + ID_CONFIGURATION.
    """
    df_a = _build_single_client_df(70001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 70001, "ClientA"))

    df_b = _build_single_client_df(70002, history=500.0, scp_abs_error=60.0, ml_abs_error=80.0, winner="SCP")
    result_b = analyze_client(make_client_source(df_b, 70002, "ClientB"))

    pareto = global_pareto_series([result_a, result_b], "6M")

    assert pareto.improvement.summary.n_total == 1
    assert pareto.deterioration.summary.n_total == 1
    imp_row = pareto.improvement.table.iloc[0]
    det_row = pareto.deterioration.table.iloc[0]
    assert (imp_row["ID_CLIENT"], imp_row["ID_CONFIGURATION"]) == (70001, 1)
    assert (det_row["ID_CLIENT"], det_row["ID_CONFIGURATION"]) == (70002, 1)


def test_global_pareto_series_tie_break_by_id_client_then_id_configuration():
    """Misma magnitud de reduccion, mismo ID_CONFIGURATION: desempate por ID_CLIENT ASC."""
    df_high = _build_single_client_df(70102, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_high = analyze_client(make_client_source(df_high, 70102, "ClientHigh"))

    df_low = _build_single_client_df(70101, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_low = analyze_client(make_client_source(df_low, 70101, "ClientLow"))

    pareto = global_pareto_series([result_high, result_low], "6M")
    table = pareto.improvement.table
    assert list(table["ID_CLIENT"]) == [70101, 70102]


def test_global_pareto_series_display_name_is_presentation_only():
    df_a = _build_single_client_df(70001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 70001, "ClientA", display_name="Etiqueta visible A"))

    pareto = global_pareto_series([result_a], "6M")
    table = pareto.improvement.table
    assert table.iloc[0]["DISPLAY_NAME"] == "Etiqueta visible A"
    # la identidad sigue siendo ID_CLIENT + ID_CONFIGURATION, no DISPLAY_NAME
    assert list(table["ID_CLIENT"]) == [70001]


def test_global_pareto_series_does_not_require_legacy_classification_context():
    """
    SERIES_CLASSIFICATION ya no forma parte de _ranking_columns: retirarla no
    altera el Pareto ni su identidad, orden o valor numerico.
    """
    df = _build_single_client_df(70001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    df = df.drop(columns=["SERIES_CLASSIFICATION"])
    result = analyze_client(make_client_source(df, 70001, "ClientMissingColumn"))

    pareto = global_pareto_series([result], "6M")
    row = pareto.improvement.table.iloc[0]
    assert row["ID_CLIENT"] == 70001
    assert row["ID_CONFIGURATION"] == 1
    assert row["ABS_ERROR_REDUCTION"] == pytest.approx(50.0)
    assert "SERIES_CLASSIFICATION" not in pareto.improvement.table.columns


def test_global_pareto_clients_uses_precomputed_abs_error_reduction_total(monkeypatch):
    """global_pareto_clients NUNCA debe recalcular desde las series: solo lee pr.abs_error_reduction_total."""
    results = build_multi_client_results()  # analyze_client ya se ejecuto aqui, antes del parche

    def _boom(*args, **kwargs):
        raise AssertionError("global_pareto_clients no debe recalcular desde las series")

    monkeypatch.setattr("src.metrics.absolute_error_reduction_row", _boom)
    monkeypatch.setattr("src.metrics.absolute_error_reduction_total", _boom)

    pareto = global_pareto_clients(results, "6M")

    expected = {
        r.source.id_client: r.periods["6M"].abs_error_reduction_total
        for r in results if r.periods.get("6M") is not None
    }
    for _, row in pareto.improvement.table.iterrows():
        assert math.isclose(row["ABS_ERROR_REDUCTION"], expected[row["ID_CLIENT"]])
    for _, row in pareto.deterioration.table.iterrows():
        assert math.isclose(row["ABS_ERROR_REDUCTION"], expected[row["ID_CLIENT"]])


def test_global_pareto_clients_excludes_nan_client_and_counts_it():
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    df_b = _build_single_client_df(60004, history=500.0, scp_abs_error=80.0, ml_abs_error=60.0, winner="SCP")
    pcols_6m = period_columns("6M")
    df_b[pcols_6m.ml_total_abs_error] = [None]
    result_b = analyze_client(make_client_source(df_b, 60004, "ClientBIncompleteAbsError"))

    pareto = global_pareto_clients([result_a, result_b], "6M")

    assert pareto.n_no_evaluables == 1
    assert pareto.improvement.summary.n_total == 1
    assert "ClientBIncompleteAbsError" not in set(pareto.improvement.table["ETIQUETA"])
    assert "ClientBIncompleteAbsError" not in set(pareto.deterioration.table["ETIQUETA"])


def test_global_pareto_clients_percentages_never_mix_signs():
    results = build_negative_net_multi_client_results()
    pareto = global_pareto_clients(results, "6M")

    assert math.isclose(pareto.improvement.table["PCT_OF_GROUP"].sum(), 100.0, abs_tol=1e-6)
    assert math.isclose(pareto.deterioration.table["PCT_OF_GROUP"].sum(), 100.0, abs_tol=1e-6)
    assert "55502_NegativeClient" not in set(pareto.improvement.table["ETIQUETA"])
    assert "55501_PositiveClient" not in set(pareto.deterioration.table["ETIQUETA"])


def test_multi_client_partial_periods_unaffected_by_evaluability_guard():
    """Regresion: periodos parciales sin cambios en agregacion global."""
    df_a = _build_single_client_df(60001, history=1000.0, scp_abs_error=100.0, ml_abs_error=50.0, winner="ML")
    result_a = analyze_client(make_client_source(df_a, 60001, "ClientA"))

    df_b = _build_single_client_df(60005, history=500.0, scp_abs_error=80.0, ml_abs_error=60.0, winner="SCP")
    pcols_6m = period_columns("6M")
    df_b[pcols_6m.ml_total_abs_error] = [None]
    result_b = analyze_client(make_client_source(df_b, 60005, "ClientBIncompleteAbsError6MOnly"))

    for period in ("M1", "RECENT_3M", "OLDER_3M"):
        gp = build_global_period_result([result_a, result_b], period)
        assert not math.isnan(gp.ml_wape_global)
        assert not math.isnan(gp.reduction_totals["REDUCCION_NETA"])


# --------------------------------------------------------------------------
# Fase 8B (K.6/K.7): diagnostico global de Fase 8. Todos los periodos
# distintos de "6M" quedan trivialmente no comparables (history=0) para
# aislar el comportamiento de Fase 8, que solo actua sobre 6M.
# --------------------------------------------------------------------------

def _multi_row_client_df(id_client: int, histories, scp_forecasts, ml_forecasts, classifications, winner_methods) -> pd.DataFrame:
    n = len(histories)
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1] * n, "ID_CLIENT": [id_client] * n,
        "ID_CONFIGURATION": list(range(1, n + 1)),
        "VALUE_LEVEL_1": ["Cat"] * n, "VALUE_LEVEL_2": [None] * n, "VALUE_LEVEL_3": [None] * n,
        "VALUE_LEVEL_4": [None] * n, "VALUE_LEVEL_5": [None] * n,
        "ML_BEST_MODEL": ["AutoETS"] * n, "SCP_BEST_MODEL": ["x11 seasonal"] * n,
        "ML_CLASSIFICATION": classifications, "ML_TYPE": classifications,
        "SERIES_CLASSIFICATION": classifications, "SCP_CLASSIFICATION": classifications,
        "COMPARISON_STATUS": ["COMPARABLE"] * n,
    })
    for period in [f"M{i}" for i in range(1, 7)] + ["RECENT_3M", "OLDER_3M"]:
        set_period(
            df, period, total_history=[0.0] * n,
            scp_forecast=[None] * n, scp_abs_error=[None] * n, scp_wape=[None] * n,
            ml_forecast=[None] * n, ml_abs_error=[None] * n, ml_wape=[None] * n, winner_method=[None] * n,
        )
    scp_abs_error = [abs(f - h) for f, h in zip(scp_forecasts, histories)]
    ml_abs_error = [abs(f - h) for f, h in zip(ml_forecasts, histories)]
    scp_wape = [e / h for e, h in zip(scp_abs_error, histories)]
    ml_wape = [e / h for e, h in zip(ml_abs_error, histories)]
    set_period(
        df, "6M", total_history=histories,
        scp_forecast=scp_forecasts, scp_abs_error=scp_abs_error, scp_wape=scp_wape,
        ml_forecast=ml_forecasts, ml_abs_error=ml_abs_error, ml_wape=ml_wape, winner_method=winner_methods,
    )
    return df


def _phase8_client_result(id_client, histories, scp_forecasts, ml_forecasts, classifications, winner_methods):
    df = _multi_row_client_df(id_client, histories, scp_forecasts, ml_forecasts, classifications, winner_methods)
    return analyze_client(make_client_source(df, id_client, f"Client{id_client}"))


def test_global_phase8_bias_is_sum_over_sum_not_average_of_client_bias():
    # Cliente A: signed=[20,10] (suma 30), history=200 -> bias_A=0.15
    result_a = _phase8_client_result(
        70001, histories=[100.0, 100.0], scp_forecasts=[120.0, 110.0], ml_forecasts=[100.0, 100.0],
        classifications=["smooth", "smooth"], winner_methods=["SCP", "SCP"],
    )
    # Cliente B: signed=[300,300] (suma 600), history=2000 -> bias_B=0.3
    result_b = _phase8_client_result(
        70002, histories=[1000.0, 1000.0], scp_forecasts=[1300.0, 1300.0], ml_forecasts=[1000.0, 1000.0],
        classifications=["erratic", "erratic"], winner_methods=["SCP", "SCP"],
    )

    gp = build_global_period_result([result_a, result_b], "6M")

    naive_average_of_client_bias = (0.15 + 0.3) / 2
    expected_sum_over_sum = (30.0 + 600.0) / (200.0 + 2000.0)
    assert math.isclose(gp.phase8.bias_total.scp_bias_agg, expected_sum_over_sum, rel_tol=1e-9)
    assert not math.isclose(gp.phase8.bias_total.scp_bias_agg, naive_average_of_client_bias, rel_tol=1e-3)


def test_global_phase8_volume_reuses_per_client_buckets_not_recalculated_on_pool():
    """
    Cliente A (escala pequena) y Cliente B (escala 1e6 mayor): si el volumen
    global recalculase terciles sobre el pool concatenado, TODO A caeria en
    RELATIVE_LOW y TODO B en RELATIVE_HIGH (0 filas de A en HIGH). Reutilizando
    el bucket ya calculado POR CLIENTE, cada uno aporta a los 3 buckets.
    """
    histories_a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    histories_b = [1_000_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0, 5_000_000.0, 6_000_000.0]
    result_a = _phase8_client_result(
        70003, histories=histories_a, scp_forecasts=[h * 1.2 for h in histories_a], ml_forecasts=histories_a,
        classifications=["smooth"] * 6, winner_methods=["SCP"] * 6,
    )
    result_b = _phase8_client_result(
        70004, histories=histories_b, scp_forecasts=[h * 1.2 for h in histories_b], ml_forecasts=histories_b,
        classifications=["erratic"] * 6, winner_methods=["SCP"] * 6,
    )

    gp = build_global_period_result([result_a, result_b], "6M")
    counts = gp.phase8.volume_table.set_index("category")["n_comparable"].to_dict()
    assert counts == {"RELATIVE_LOW": 4, "RELATIVE_MEDIUM": 4, "RELATIVE_HIGH": 4}


def test_global_phase8_not_assignable_client_preserved_and_counted():
    histories_a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    result_a = _phase8_client_result(
        70005, histories=histories_a, scp_forecasts=[h * 1.2 for h in histories_a], ml_forecasts=histories_a,
        classifications=["smooth"] * 6, winner_methods=["SCP"] * 6,
    )
    # Cliente C: solo 2 series comparables -> NOT_ASSIGNABLE (N_LT_3).
    result_c = _phase8_client_result(
        70006, histories=[10.0, 20.0], scp_forecasts=[12.0, 22.0], ml_forecasts=[10.0, 20.0],
        classifications=["lumpy", "lumpy"], winner_methods=["SCP", "SCP"],
    )
    assert result_c.periods["6M"].phase8.volume.status == "NOT_ASSIGNABLE"

    gp = build_global_period_result([result_a, result_c], "6M")

    assert gp.phase8.n_clients_with_not_assignable_volume == 1
    not_assignable_row = gp.phase8.volume_table[gp.phase8.volume_table["category"] == "NOT_ASSIGNABLE"]
    assert len(not_assignable_row) == 1
    assert not_assignable_row.iloc[0]["n_comparable"] == 2  # las 2 filas del cliente C, nunca excluidas


def test_global_phase8_null_category_n_clients_and_bias_aligned():
    result_a = _phase8_client_result(
        70007, histories=[100.0], scp_forecasts=[120.0], ml_forecasts=[100.0],
        classifications=[None], winner_methods=["SCP"],
    )
    result_b = _phase8_client_result(
        70008, histories=[200.0], scp_forecasts=[260.0], ml_forecasts=[200.0],
        classifications=[None], winner_methods=["SCP"],
    )

    gp = build_global_period_result([result_a, result_b], "6M")
    table = gp.phase8.classification_tables["SERIES_CLASSIFICATION"]

    null_row = table[table["category"] == "(sin clasificar)"].iloc[0]
    assert null_row["n_comparable"] == 2
    assert null_row["n_clients"] == 2
    # signed=[20,60], history=[100,200] -> bias = 80/300
    assert math.isclose(null_row["scp_bias_agg"], 80.0 / 300.0, rel_tol=1e-9)


def test_global_phase8_none_when_all_clients_missing_phase8():
    results = build_multi_client_results()
    for r in results:
        pr = r.periods.get("6M")
        if pr is not None:
            pr.phase8 = None

    gp = build_global_period_result(results, "6M")
    assert gp.phase8 is None
    assert gp.n_clients == len(results)  # el resto del resultado global no se ve afectado


def test_global_phase8_present_when_all_clients_have_phase8():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    assert gp.phase8 is not None


def test_global_phase8_none_when_mixed_some_clients_missing_phase8():
    results = build_multi_client_results()
    results[0].periods["6M"].phase8 = None  # simula un ClientAnalysisResult legacy

    gp = build_global_period_result(results, "6M")
    assert gp.phase8 is None
    # el cliente sin phase8 no se excluye del resto del agregado global (winner_counts sigue sumando los 3).
    assert gp.n_clients == len(results)
    assert gp.winner_counts["_total"] > 0


def test_global_phase8_none_for_periods_other_than_6m():
    results = build_multi_client_results()
    for period in ("M1", "RECENT_3M", "OLDER_3M"):
        gp = build_global_period_result(results, period)
        assert gp.phase8 is None


def test_global_classification_volume_cross_present_with_n_clients_and_bias():
    histories_a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    histories_b = [1_000_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0, 5_000_000.0, 6_000_000.0]
    result_a = _phase8_client_result(
        70009, histories=histories_a, scp_forecasts=[h * 1.2 for h in histories_a], ml_forecasts=histories_a,
        classifications=["smooth"] * 6, winner_methods=["SCP"] * 6,
    )
    result_b = _phase8_client_result(
        70010, histories=histories_b, scp_forecasts=[h * 1.2 for h in histories_b], ml_forecasts=histories_b,
        classifications=["erratic"] * 6, winner_methods=["SCP"] * 6,
    )

    gp = build_global_period_result([result_a, result_b], "6M")
    cross = gp.phase8.classification_volume_cross

    for col in ("SERIES_CLASSIFICATION", "VOLUME_BUCKET", "n_comparable", "n_clients",
                "scp_bias_agg", "ml_bias_agg", "scp_direction", "ml_direction", "small_sample"):
        assert col in cross.columns

    smooth_low = cross[(cross["SERIES_CLASSIFICATION"] == "smooth") & (cross["VOLUME_BUCKET"] == "RELATIVE_LOW")]
    assert len(smooth_low) == 1
    assert smooth_low.iloc[0]["n_comparable"] == 2
    assert smooth_low.iloc[0]["n_clients"] == 1

    erratic_high = cross[(cross["SERIES_CLASSIFICATION"] == "erratic") & (cross["VOLUME_BUCKET"] == "RELATIVE_HIGH")]
    assert erratic_high.iloc[0]["n_clients"] == 1
    assert (cross["small_sample"]).all()  # todas las celdas tienen n_comparable=2 < 10


def test_global_phase8_has_no_individual_cross_attribute():
    """El diagnostico global expone classification_volume_cross; el individual (Phase8ClientDiagnostics) no expone ningun cruce."""
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    assert gp.phase8 is not None
    assert hasattr(gp.phase8, "classification_volume_cross")
    for r in results:
        pr = r.periods.get("6M")
        if pr is not None and pr.phase8 is not None:
            assert not hasattr(pr.phase8, "classification_volume_cross")
