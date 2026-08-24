import math

import numpy as np
import pandas as pd

from src.metrics import BIAS_DIRECTION_NEGATIVE, BIAS_DIRECTION_POSITIVE
from src.models import category_performance_table
from src.periods import period_columns
from src.phase8 import (
    MISSING_CATEGORY_LABEL,
    NOT_ASSIGNABLE,
    REASON_COLLAPSE_AFTER_TIE_GROUPING,
    REASON_DISTINCT_VALUES_LT_3,
    REASON_N_LT_3,
    REASON_NON_EVALUABLE_HISTORY_VALUES,
    RELATIVE_HIGH,
    RELATIVE_LOW,
    RELATIVE_MEDIUM,
    Phase8ClientDiagnostics,
    build_phase8_client_diagnostics,
    category_performance_table_with_bias,
    classification_volume_cross_table,
    compute_volume_buckets,
)
from tests.factories import build_no_comparable_dataframe, build_synthetic_client_dataframe

# --------------------------------------------------------------------------
# Fase 8B (K.3): compute_volume_buckets / VolumeBucketResult.
# Ninguna fixture de este archivo depende del CSV real: son series sinteticas
# pequenas que reproducen los patrones estructurales detectados en 8A
# (empate en frontera, concentracion extrema, escalas muy distintas).
# --------------------------------------------------------------------------


def test_nine_distinct_values_produce_balanced_3_3_3():
    total_history = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    assert result.reason is None
    assert result.bucket_counts == {RELATIVE_LOW: 3, RELATIVE_MEDIUM: 3, RELATIVE_HIGH: 3}
    assert list(result.buckets) == [
        RELATIVE_LOW, RELATIVE_LOW, RELATIVE_LOW,
        RELATIVE_MEDIUM, RELATIVE_MEDIUM, RELATIVE_MEDIUM,
        RELATIVE_HIGH, RELATIVE_HIGH, RELATIVE_HIGH,
    ]


def test_tie_at_boundary_is_never_split_and_still_produces_three_groups():
    """
    Analogo reducido al patron real de 10249 (empate de valor '60.0'
    compartido por varias filas a ambos lados del corte por rango): el valor
    10 (4 filas) nunca se reparte entre LOW y MEDIUM, cae entero en LOW.
    """
    total_history = pd.Series([10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 30.0, 30.0, 30.0])
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    assert result.bucket_counts == {RELATIVE_LOW: 4, RELATIVE_MEDIUM: 2, RELATIVE_HIGH: 3}
    # Las 4 filas de valor 10.0 estan TODAS en el mismo bucket (nunca partidas).
    value_10_buckets = result.buckets[total_history == 10.0]
    assert value_10_buckets.nunique() == 1
    assert value_10_buckets.iloc[0] == RELATIVE_LOW


def test_several_scattered_repeated_values_are_grouped_without_splitting():
    total_history = pd.Series([1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 5.0, 5.0, 6.0])
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    for value in total_history.unique():
        assert result.buckets[total_history == value].nunique() == 1
    assert sum(result.bucket_counts.values()) == len(total_history)


def test_n_equals_2_is_not_assignable_with_n_lt_3():
    total_history = pd.Series([5.0, 10.0])
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_N_LT_3
    assert result.bucket_counts == {NOT_ASSIGNABLE: 2}
    assert (result.buckets == NOT_ASSIGNABLE).all()


def test_n_equals_3_with_three_distinct_values_gives_one_per_bucket():
    total_history = pd.Series([10.0, 20.0, 30.0])
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    assert result.bucket_counts == {RELATIVE_LOW: 1, RELATIVE_MEDIUM: 1, RELATIVE_HIGH: 1}


def test_all_values_equal_is_not_assignable_with_distinct_values_lt_3():
    total_history = pd.Series([7.0] * 20)
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_DISTINCT_VALUES_LT_3
    assert result.n_distinct_values == 1


def test_extreme_concentration_collapses_middle_bucket_and_is_not_assignable():
    """
    Un unico valor concentra >2/3 de las filas: agrupar el empate completo en
    un lado dejaria RELATIVE_MEDIUM vacio -- la post-condicion lo detecta y
    devuelve NOT_ASSIGNABLE en vez de degradar silenciosamente a 2 buckets.
    """
    total_history = pd.Series([1.0] * 70 + [2.0, 3.0])
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_COLLAPSE_AFTER_TIE_GROUPING
    assert result.n_distinct_values == 3


def test_nan_in_input_makes_whole_client_not_assignable():
    total_history = pd.Series([1.0, 2.0, 3.0, 4.0, None, 6.0, 7.0, 8.0, 9.0])
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_NON_EVALUABLE_HISTORY_VALUES
    assert result.n_distinct_values == 0
    assert (result.buckets == NOT_ASSIGNABLE).all()


def test_positive_inf_in_input_makes_whole_client_not_assignable():
    total_history = pd.Series([1.0, 2.0, 3.0, 4.0, np.inf, 6.0, 7.0, 8.0, 9.0])
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_NON_EVALUABLE_HISTORY_VALUES


def test_negative_inf_in_input_makes_whole_client_not_assignable():
    total_history = pd.Series([1.0, 2.0, 3.0, 4.0, -np.inf, 6.0, 7.0, 8.0, 9.0])
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_NON_EVALUABLE_HISTORY_VALUES


def test_deterministic_same_input_produces_identical_result():
    total_history = pd.Series([10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 30.0, 30.0, 30.0])
    result_a = compute_volume_buckets(total_history)
    result_b = compute_volume_buckets(total_history.copy())
    assert result_a.status == result_b.status
    assert result_a.reason == result_b.reason
    assert result_a.bucket_counts == result_b.bucket_counts
    pd.testing.assert_series_equal(result_a.buckets, result_b.buckets)


def test_input_series_is_never_mutated():
    total_history = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    original = total_history.copy()
    compute_volume_buckets(total_history)
    pd.testing.assert_series_equal(total_history, original)


def test_two_clients_with_radically_different_scales_are_bucketed_independently():
    client_small_scale = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    client_large_scale = pd.Series([1_000_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0, 5_000_000.0,
                                     6_000_000.0, 7_000_000.0, 8_000_000.0, 9_000_000.0])
    result_small = compute_volume_buckets(client_small_scale)
    result_large = compute_volume_buckets(client_large_scale)

    assert result_small.status == "OK"
    assert result_large.status == "OK"
    assert result_small.bucket_counts == {RELATIVE_LOW: 3, RELATIVE_MEDIUM: 3, RELATIVE_HIGH: 3}
    assert result_large.bucket_counts == {RELATIVE_LOW: 3, RELATIVE_MEDIUM: 3, RELATIVE_HIGH: 3}

    # RELATIVE_LOW del cliente grande (>=1,000,000) es, en magnitud absoluta,
    # muchisimo mayor que RELATIVE_HIGH del cliente pequeno (<=9): los buckets
    # son relativos a cada cliente, nunca comparables en absoluto entre ellos.
    small_high_max = client_small_scale[result_small.buckets == RELATIVE_HIGH].max()
    large_low_min = client_large_scale[result_large.buckets == RELATIVE_LOW].min()
    assert large_low_min > small_high_max


# --------------------------------------------------------------------------
# Auditoria final 8B (punto 2): compute_volume_buckets con dtype=object.
# np.isinf lanza TypeError sobre dtype object; la coercion a numerico
# (pd.to_numeric(errors="coerce")) evita el TypeError y trata cualquier
# valor no convertible como no evaluable (nunca desaparece en silencio).
# --------------------------------------------------------------------------

def test_compute_volume_buckets_empty_object_dtype_does_not_raise():
    total_history = pd.Series([], dtype=object)
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_N_LT_3


def test_compute_volume_buckets_object_dtype_python_ints_treated_as_numeric():
    total_history = pd.Series([1, 2, 3], dtype=object)
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    assert result.bucket_counts == {RELATIVE_LOW: 1, RELATIVE_MEDIUM: 1, RELATIVE_HIGH: 1}


def test_compute_volume_buckets_object_dtype_numeric_strings_coerced():
    total_history = pd.Series(["1", "2", "3"], dtype=object)
    result = compute_volume_buckets(total_history)
    assert result.status == "OK"
    assert result.bucket_counts == {RELATIVE_LOW: 1, RELATIVE_MEDIUM: 1, RELATIVE_HIGH: 1}


def test_compute_volume_buckets_object_dtype_non_numeric_value_is_not_assignable():
    """Un valor realmente no convertible ('invalid') nunca desaparece en silencio: NOT_ASSIGNABLE para el cliente completo."""
    total_history = pd.Series(["1", "invalid", "3"], dtype=object)
    result = compute_volume_buckets(total_history)
    assert result.status == NOT_ASSIGNABLE
    assert result.reason == REASON_NON_EVALUABLE_HISTORY_VALUES
    assert len(result.buckets) == 3  # las 3 filas siguen presentes, ninguna se pierde


def test_compute_volume_buckets_object_dtype_input_not_mutated():
    total_history = pd.Series(["1", "2", "3"], dtype=object)
    original = total_history.copy()
    compute_volume_buckets(total_history)
    pd.testing.assert_series_equal(total_history, original)
    assert total_history.dtype == object  # el dtype original no cambia para el llamador


# --------------------------------------------------------------------------
# Fase 8B (K.4): category_performance_table_with_bias.
# --------------------------------------------------------------------------

def _category_with_bias_frame():
    """3 filas comparables de un cliente, con signed error propio (distinto de ABS_ERROR/WAPE)."""
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CLIENT": [1, 1, 1],
        pcols.total_history: [100.0, 100.0, 100.0],
        pcols.scp_total_forecast: [120.0, 110.0, 130.0],
        pcols.scp_total_abs_error: [20.0, 10.0, 30.0],
        pcols.scp_wape: [0.2, 0.1, 0.3],
        pcols.ml_total_forecast: [110.0, 130.0, 90.0],
        pcols.ml_total_abs_error: [10.0, 30.0, 10.0],
        pcols.ml_wape: [0.1, 0.3, 0.1],
        pcols.winner_method: ["ML", "SCP", "ML"],
        pcols.scp_total_signed_error: [20.0, 10.0, 30.0],
        pcols.ml_total_signed_error: [10.0, 30.0, -10.0],
        "CATEGORY_COL": ["A", None, "A"],
    })
    comparable_mask = pd.Series([True, True, True])
    return df, pcols, comparable_mask


def test_category_performance_table_with_bias_preserves_base_columns_unchanged():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0

    base = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    augmented = category_performance_table_with_bias(df, pcols, comparable_mask, "ML_BEST_MODEL")

    base_columns = list(base.columns)
    pd.testing.assert_frame_equal(augmented[base_columns], base)


def test_category_performance_table_with_bias_adds_only_bias_columns_no_duplicates():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0

    base = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    augmented = category_performance_table_with_bias(df, pcols, comparable_mask, "ML_BEST_MODEL")

    new_columns = set(augmented.columns) - set(base.columns)
    assert new_columns == {"scp_bias_agg", "ml_bias_agg", "scp_direction", "ml_direction"}


def test_category_performance_table_with_bias_empty_when_no_comparable_rows():
    df = build_no_comparable_dataframe()
    pcols = period_columns("6M")
    empty_mask = pd.Series([False], index=df.index)
    table = category_performance_table_with_bias(df, pcols, empty_mask, "ML_BEST_MODEL")
    assert table.empty


def test_category_performance_table_with_bias_null_category_aligned_with_sin_clasificar():
    df, pcols, mask = _category_with_bias_frame()
    table = category_performance_table_with_bias(df, pcols, mask, "CATEGORY_COL")

    null_row = table[table["category"] == MISSING_CATEGORY_LABEL].iloc[0]
    assert null_row["n_comparable"] == 1
    # Fila del medio (indice 1): scp_signed=10.0, ml_signed=30.0, history=100.0.
    assert math.isclose(null_row["scp_bias_agg"], 10.0 / 100.0)
    assert math.isclose(null_row["ml_bias_agg"], 30.0 / 100.0)
    assert null_row["scp_direction"] == BIAS_DIRECTION_POSITIVE
    assert null_row["ml_direction"] == BIAS_DIRECTION_POSITIVE

    a_row = table[table["category"] == "A"].iloc[0]
    assert a_row["n_comparable"] == 2
    # Filas 0 y 2: scp_signed=[20,30] sum=50, history sum=200 -> 0.25; ml_signed=[10,-10] sum=0, history sum=200 -> 0.0.
    assert math.isclose(a_row["scp_bias_agg"], 50.0 / 200.0)
    assert math.isclose(a_row["ml_bias_agg"], 0.0)
    assert a_row["ml_direction"] == "ZERO"


def test_category_performance_table_with_bias_works_for_volume_bucket_dimension():
    df, pcols, mask = _category_with_bias_frame()
    df["VOLUME_BUCKET"] = [RELATIVE_LOW, RELATIVE_LOW, RELATIVE_HIGH]
    table = category_performance_table_with_bias(df, pcols, mask, "VOLUME_BUCKET")

    assert set(table["category"]) == {RELATIVE_LOW, RELATIVE_HIGH}
    low_row = table[table["category"] == RELATIVE_LOW].iloc[0]
    assert low_row["n_comparable"] == 2


def test_category_performance_table_with_bias_small_sample_matches_base():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0

    base = category_performance_table(df, pcols, comparable_mask, "ML_BEST_MODEL")
    augmented = category_performance_table_with_bias(df, pcols, comparable_mask, "ML_BEST_MODEL")
    assert augmented.set_index("category")["small_sample"].equals(base.set_index("category")["small_sample"])


# --------------------------------------------------------------------------
# Fase 8B (K.5, funcion pura): build_phase8_client_diagnostics.
# --------------------------------------------------------------------------

def test_build_phase8_client_diagnostics_does_not_mutate_source_dataframe():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0
    original = df.copy(deep=True)

    build_phase8_client_diagnostics(df, pcols, comparable_mask)

    pd.testing.assert_frame_equal(df, original)  # ninguna columna nueva ni valor existente alterado
    assert "VOLUME_BUCKET" not in df.columns


def test_build_phase8_client_diagnostics_returns_all_expected_tables():
    df = build_synthetic_client_dataframe()
    pcols = period_columns("6M")
    comparable_mask = df["HAS_BASE_CANDIDATE"] == 1
    comparable_mask &= df[pcols.total_history] > 0

    diagnostics = build_phase8_client_diagnostics(df, pcols, comparable_mask)

    assert isinstance(diagnostics, Phase8ClientDiagnostics)
    assert set(diagnostics.model_tables) == {"ML_BEST_MODEL", "SCP_BEST_MODEL"}
    assert set(diagnostics.classification_tables) == {
        "ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION", "SCP_CLASSIFICATION",
    }
    assert not math.isnan(diagnostics.bias_total.scp_bias_agg)
    assert diagnostics.volume.status in ("OK", NOT_ASSIGNABLE)


def test_build_phase8_client_diagnostics_has_no_cross_attribute():
    """No existe cruce individual: Phase8ClientDiagnostics no expone ningun campo de cruce."""
    field_names = {f for f in Phase8ClientDiagnostics.__dataclass_fields__}
    assert not any("cross" in f for f in field_names)


# --------------------------------------------------------------------------
# Fase 8B (K.7): classification_volume_cross_table.
# --------------------------------------------------------------------------

def _cross_frame():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CLIENT": [1, 1, 2, 2],
        pcols.total_history: [100.0, 100.0, 200.0, 200.0],
        pcols.scp_total_forecast: [120.0, 110.0, 240.0, 220.0],
        pcols.scp_total_abs_error: [20.0, 10.0, 40.0, 20.0],
        pcols.scp_wape: [0.2, 0.1, 0.2, 0.1],
        pcols.ml_total_forecast: [110.0, 130.0, 220.0, 260.0],
        pcols.ml_total_abs_error: [10.0, 30.0, 20.0, 60.0],
        pcols.ml_wape: [0.1, 0.3, 0.1, 0.3],
        pcols.winner_method: ["ML", "SCP", "ML", "SCP"],
        pcols.scp_total_signed_error: [20.0, 10.0, 40.0, 20.0],
        pcols.ml_total_signed_error: [10.0, 30.0, 20.0, 60.0],
        "SERIES_CLASSIFICATION": ["smooth", None, "smooth", "erratic"],
        "VOLUME_BUCKET": [RELATIVE_LOW, RELATIVE_LOW, RELATIVE_HIGH, RELATIVE_HIGH],
    })
    comparable_mask = pd.Series([True, True, True, True])
    return df, pcols, comparable_mask


def test_classification_volume_cross_table_preserves_both_dimensions_structurally():
    df, pcols, mask = _cross_frame()
    table = classification_volume_cross_table(df, pcols, mask)

    assert "SERIES_CLASSIFICATION" in table.columns
    assert "VOLUME_BUCKET" in table.columns
    assert "category" not in table.columns  # la clave interna de tupla no se filtra al resultado

    smooth_low = table[(table["SERIES_CLASSIFICATION"] == "smooth") & (table["VOLUME_BUCKET"] == RELATIVE_LOW)]
    assert len(smooth_low) == 1
    assert smooth_low.iloc[0]["n_comparable"] == 1


def test_classification_volume_cross_table_null_classification_normalized():
    df, pcols, mask = _cross_frame()
    table = classification_volume_cross_table(df, pcols, mask)

    null_row = table[(table["SERIES_CLASSIFICATION"] == MISSING_CATEGORY_LABEL) & (table["VOLUME_BUCKET"] == RELATIVE_LOW)]
    assert len(null_row) == 1
    assert null_row.iloc[0]["n_comparable"] == 1


def test_classification_volume_cross_table_n_clients_across_two_clients():
    df, pcols, mask = _cross_frame()
    table = classification_volume_cross_table(df, pcols, mask)

    smooth_high = table[(table["SERIES_CLASSIFICATION"] == "smooth") & (table["VOLUME_BUCKET"] == RELATIVE_HIGH)]
    assert smooth_high.iloc[0]["n_clients"] == 1  # solo ID_CLIENT=2 aporta esta combinacion

    # "smooth" aparece en ambos clientes (1 en LOW, 2 en HIGH) pero en celdas DISTINTAS:
    # cada celda cuenta solo los clientes que aportan a ESA combinacion exacta.
    smooth_low = table[(table["SERIES_CLASSIFICATION"] == "smooth") & (table["VOLUME_BUCKET"] == RELATIVE_LOW)]
    assert smooth_low.iloc[0]["n_clients"] == 1


def test_classification_volume_cross_table_small_sample_threshold():
    df, pcols, mask = _cross_frame()
    table = classification_volume_cross_table(df, pcols, mask)
    assert (table["n_comparable"] < 10).all()
    assert table["small_sample"].all()


def test_classification_volume_cross_table_bias_columns_present():
    df, pcols, mask = _cross_frame()
    table = classification_volume_cross_table(df, pcols, mask)
    for col in ("scp_bias_agg", "ml_bias_agg", "scp_direction", "ml_direction"):
        assert col in table.columns
    erratic_high = table[(table["SERIES_CLASSIFICATION"] == "erratic") & (table["VOLUME_BUCKET"] == RELATIVE_HIGH)]
    assert erratic_high.iloc[0]["scp_direction"] == BIAS_DIRECTION_POSITIVE


def test_classification_volume_cross_table_no_collision_between_similar_looking_categories():
    """
    Documenta por que se descarto el diseno de string+separador (8A correccion 2):
    con clave de tupla, dos categorias cuyo string concatenado colisionaria
    (p.ej. "A|B" + "C" vs "A" + "B|C" si el separador fuese "|") no colisionan
    porque la identidad es la tupla completa, nunca un string reconstruido.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CLIENT": [1, 1],
        pcols.total_history: [100.0, 100.0],
        pcols.scp_total_forecast: [120.0, 120.0],
        pcols.scp_total_abs_error: [20.0, 20.0],
        pcols.scp_wape: [0.2, 0.2],
        pcols.ml_total_forecast: [110.0, 110.0],
        pcols.ml_total_abs_error: [10.0, 10.0],
        pcols.ml_wape: [0.1, 0.1],
        pcols.winner_method: ["ML", "ML"],
        pcols.scp_total_signed_error: [20.0, 20.0],
        pcols.ml_total_signed_error: [10.0, 10.0],
        # Dos combinaciones distintas que, concatenadas con un separador ingenuo
        # "__x__", producirian el MISMO string si una categoria ya contuviera
        # el separador: aqui simulamos el caso limite con valores que
        # comparten prefijo/sufijo tras una concatenacion textual hipotetica.
        "SERIES_CLASSIFICATION": ["A__x__RELATIVE_LOW", "A"],
        "VOLUME_BUCKET": [RELATIVE_HIGH, "__x__RELATIVE_LOW__x__RELATIVE_HIGH"],
    })
    mask = pd.Series([True, True])
    table = classification_volume_cross_table(df, pcols, mask)

    # Con clave de tupla, cada fila da lugar a una celda propia (2 grupos
    # distintos, nunca colisionados en uno solo por coincidencia textual).
    assert len(table) == 2
    assert table["n_comparable"].sum() == 2
