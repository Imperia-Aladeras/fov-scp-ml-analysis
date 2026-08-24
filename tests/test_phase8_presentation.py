import pandas as pd

from src.metrics import (
    BIAS_DIRECTION_NEGATIVE,
    BIAS_DIRECTION_NOT_EVALUABLE,
    BIAS_DIRECTION_POSITIVE,
    BIAS_DIRECTION_ZERO,
)
from src.phase8 import NOT_ASSIGNABLE, REASON_N_LT_3, RELATIVE_HIGH, RELATIVE_LOW, RELATIVE_MEDIUM
from src.phase8_presentation import (
    VOLUME_METHODOLOGY_NOTE,
    VOLUME_METHODOLOGY_NOTE_GLOBAL,
    direction_label_es,
    has_bias_columns,
    sort_volume_table,
    volume_bucket_label_es,
    volume_not_assignable_reason_es,
)


def test_direction_label_es_translates_all_four_machine_values():
    assert direction_label_es(BIAS_DIRECTION_POSITIVE) == "Sobreprevisión"
    assert direction_label_es(BIAS_DIRECTION_NEGATIVE) == "Infraprevisión"
    assert direction_label_es(BIAS_DIRECTION_ZERO) == "Sin sesgo agregado"
    assert direction_label_es(BIAS_DIRECTION_NOT_EVALUABLE) == "No evaluable"


def test_direction_label_es_none_is_not_evaluable():
    assert direction_label_es(None) == "No evaluable"


def test_volume_bucket_label_es_translates_all_four_machine_values():
    assert volume_bucket_label_es(RELATIVE_LOW) == "Bajo relativo"
    assert volume_bucket_label_es(RELATIVE_MEDIUM) == "Medio relativo"
    assert volume_bucket_label_es(RELATIVE_HIGH) == "Alto relativo"
    assert volume_bucket_label_es(NOT_ASSIGNABLE) == "No asignable"


def test_volume_not_assignable_reason_es_known_reason_translated():
    text = volume_not_assignable_reason_es(REASON_N_LT_3)
    assert "3" in text
    assert text != REASON_N_LT_3


def test_sort_volume_table_orders_low_medium_high_not_assignable():
    table = pd.DataFrame({
        "category": [RELATIVE_HIGH, RELATIVE_LOW, NOT_ASSIGNABLE, RELATIVE_MEDIUM],
        "n_comparable": [1, 1, 1, 1],
    })
    sorted_table = sort_volume_table(table)
    assert sorted_table["category"].tolist() == [RELATIVE_LOW, RELATIVE_MEDIUM, RELATIVE_HIGH, NOT_ASSIGNABLE]


def test_sort_volume_table_never_mutates_input():
    table = pd.DataFrame({"category": [RELATIVE_HIGH, RELATIVE_LOW], "n_comparable": [1, 1]})
    original = table.copy()
    sort_volume_table(table)
    pd.testing.assert_frame_equal(table, original)


def test_sort_volume_table_empty_returns_empty():
    table = pd.DataFrame({"category": [], "n_comparable": []})
    result = sort_volume_table(table)
    assert result.empty


def test_has_bias_columns_true_when_all_four_present():
    table = pd.DataFrame({
        "category": ["A"], "scp_bias_agg": [0.1], "ml_bias_agg": [0.1],
        "scp_direction": ["POSITIVE"], "ml_direction": ["POSITIVE"],
    })
    assert has_bias_columns(table) is True


def test_has_bias_columns_false_when_missing_or_empty():
    assert has_bias_columns(pd.DataFrame({"category": ["A"]})) is False
    assert has_bias_columns(pd.DataFrame()) is False
    assert has_bias_columns(None) is False


def test_volume_methodology_note_global_is_distinct_from_individual_note():
    assert VOLUME_METHODOLOGY_NOTE_GLOBAL != VOLUME_METHODOLOGY_NOTE
    assert "de este cliente" in VOLUME_METHODOLOGY_NOTE
    assert "de este cliente" not in VOLUME_METHODOLOGY_NOTE_GLOBAL


def test_volume_methodology_note_global_explains_per_client_aggregation():
    text = VOLUME_METHODOLOGY_NOTE_GLOBAL.lower()
    assert "propio cliente" in text
    assert "no se recalculan terciles" in text
    assert "global" in text
