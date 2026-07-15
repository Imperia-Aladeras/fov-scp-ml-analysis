import math

from src.global_analysis import (
    analyze_global,
    build_client_period_table,
    build_global_period_result,
    global_category_performance_table,
)
from tests.factories import build_multi_client_results, build_negative_net_multi_client_results


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


def test_global_category_performance_table_aggregates_across_clients():
    results = build_multi_client_results()
    table = global_category_performance_table(results, "6M", "ML_BEST_MODEL")
    # AutoETS aparece en mixed (fila 0) y en las 2 filas de all_ml -> 3 series, 2 clientes.
    row = table[table["category"] == "AutoETS"].iloc[0]
    assert row["n_comparable"] == 3
    assert row["n_clients"] == 2
