import pandas as pd

from src.periods import period_columns
from src.quality_checks import (
    Severity,
    StructuralInputError,
    check_aggregate_vs_monthly_sum,
    check_bias_reconstruction,
    check_batch_heterogeneity,
    check_block_ml_metadata_pairing,
    check_block_model_metadata_missing_for_pure_forecast,
    check_both_zero_wape_is_tie,
    check_comparable_missing_wape_inputs,
    check_comparable_without_forecasts,
    check_comparable_without_winner,
    check_comparison_status_vs_period_mask,
    check_error_chain_reconstruction,
    check_extreme_wape,
    check_infinite_backend_metrics,
    check_invalid_binary_flag_value,
    check_invalid_winner_method_value,
    check_mae_reconstruction,
    check_mojibake_in_value_levels,
    check_negative_history,
    check_negative_nonnegative_metrics,
    check_rmse_reconstruction,
    check_unknown_comparison_status_value,
    check_wape_reconstruction,
    check_winner_formula_not_auditable,
    check_wrapped_csv_normalized,
    _INFINITE_CHECK_ATTRS,
    _NEGATIVE_DOMAIN_FIELDS,
)


def test_block_model_metadata_missing_detects_scp_and_ml_independently():
    pcols = period_columns("OLDER_3M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [101, 202],
        pcols.scp_total_forecast: [30.0, None],
        pcols.ml_total_forecast: [None, 25.0],
        "SCP_MODEL_OLDER_3M": [None, None],
        "ML_BEST_MODEL_OLDER_3M": [None, None],
    })

    issues = check_block_model_metadata_missing_for_pure_forecast("f.csv", df, "OLDER_3M", pcols)

    assert {issue.details["method"] for issue in issues} == {"SCP", "ML"}
    assert all(issue.severity == Severity.ERROR for issue in issues)
    assert all(issue.code == "BLOCK_MODEL_METADATA_MISSING_FOR_PURE_FORECAST" for issue in issues)
    assert {issue.details["sample_ids"][0] for issue in issues} == {101, 202}


def test_block_model_metadata_missing_does_not_make_historical_columns_mandatory():
    pcols = period_columns("RECENT_3M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [101],
        pcols.scp_total_forecast: [30.0],
        pcols.ml_total_forecast: [25.0],
    })

    assert check_block_model_metadata_missing_for_pure_forecast("f.csv", df, "RECENT_3M", pcols) == []


def test_block_model_metadata_missing_never_reconstructs_from_legacy_6m_columns():
    pcols = period_columns("RECENT_3M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [101],
        pcols.scp_total_forecast: [30.0],
        pcols.ml_total_forecast: [25.0],
        "SCP_MODEL_RECENT_3M": [None],
        "ML_BEST_MODEL_RECENT_3M": [None],
        "SCP_BEST_MODEL": ["LegacySCP"],
        "ML_BEST_MODEL": ["LegacyML"],
    })

    issues = check_block_model_metadata_missing_for_pure_forecast("f.csv", df, "RECENT_3M", pcols)
    assert {issue.details["method"] for issue in issues} == {"SCP", "ML"}


def test_block_ml_metadata_pairing_covers_both_mismatch_directions_and_valid_pairs():
    df = pd.DataFrame({
        "ID_CONFIGURATION": [101, 202, 303, 404],
        "ML_BEST_MODEL_OLDER_3M": ["AutoETS", None, "AutoARIMA", None],
        "ML_CLASSIFICATION_OLDER_3M": [None, "smooth", "erratic", None],
    })

    issue = check_block_ml_metadata_pairing("f.csv", df, "OLDER_3M")

    assert issue is not None
    assert issue.severity == Severity.ERROR
    assert issue.code == "BLOCK_ML_METADATA_PAIRING_MISMATCH"
    assert issue.details["n_bad"] == 2
    assert issue.details["sample_ids"] == [101, 202]


def test_block_ml_metadata_pairing_missing_physical_column_is_backward_compatible():
    only_model = pd.DataFrame({"ML_BEST_MODEL_RECENT_3M": ["AutoETS"]})
    only_classification = pd.DataFrame({"ML_CLASSIFICATION_RECENT_3M": ["smooth"]})

    assert check_block_ml_metadata_pairing("f.csv", only_model, "RECENT_3M") is None
    assert check_block_ml_metadata_pairing("f.csv", only_classification, "RECENT_3M") is None


def test_structural_input_error_exposes_code_and_message():
    exc = StructuralInputError("INVALID_ID_CLIENT", "3 fila(s) con ID_CLIENT invalido.")
    assert exc.code == "INVALID_ID_CLIENT"
    assert str(exc) == "3 fila(s) con ID_CLIENT invalido."


def test_structural_input_error_is_raisable_and_catchable_by_code():
    try:
        raise StructuralInputError("AMBIGUOUS_CLIENT_EXECUTION", "cliente 10338 con 2 scopes")
    except StructuralInputError as exc:
        assert exc.code == "AMBIGUOUS_CLIENT_EXECUTION"
    else:
        raise AssertionError("StructuralInputError no fue lanzada")


def test_check_aggregate_vs_monthly_sum_detects_mismatch():
    pcols = period_columns("RECENT_3M")
    df = pd.DataFrame({
        "HISTORY_M1": [10.0], "HISTORY_M2": [10.0], "HISTORY_M3": [10.0],
        pcols.total_history: [999.0],  # deberia ser 30.0
    })
    issue = check_aggregate_vs_monthly_sum("f.csv", df, "RECENT_3M", pcols, "HISTORY", pcols.total_history)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "AGGREGATE_VS_MONTHLY_SUM_MISMATCH"


def test_check_aggregate_vs_monthly_sum_passes_when_consistent():
    pcols = period_columns("RECENT_3M")
    df = pd.DataFrame({
        "HISTORY_M1": [10.0], "HISTORY_M2": [10.0], "HISTORY_M3": [10.0],
        pcols.total_history: [30.0],
    })
    issue = check_aggregate_vs_monthly_sum("f.csv", df, "RECENT_3M", pcols, "HISTORY", pcols.total_history)
    assert issue is None


def test_check_wape_reconstruction_detects_mismatch():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0],
        pcols.scp_total_abs_error: [20.0],
        pcols.scp_wape: [0.5],  # deberia ser 0.2
        pcols.ml_total_abs_error: [10.0],
        pcols.ml_wape: [0.1],
    })
    issues = check_wape_reconstruction("f.csv", df, "6M", pcols)
    codes = [i.code for i in issues]
    assert "WAPE_RECONSTRUCTION_MISMATCH" in codes
    assert len(issues) == 1  # solo SCP falla, ML es consistente


# --------------------------------------------------------------------------
# Item 2: la unica parte de la regla de winner totalmente especificada es
# "ambos WAPE=0 -> TIE". El resto (empate cuando relativeDiff < 0.0001) no
# se reconstruye porque la formula real no esta documentada; se confia en
# WINNER_METHOD_* como fuente de verdad y se deja constancia de la
# limitacion metodologica.
# --------------------------------------------------------------------------

def test_check_both_zero_wape_is_tie_detects_inconsistency():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_wape: [0.0],
        pcols.ml_wape: [0.0],
        pcols.winner_method: ["ML"],  # incorrecto: ambos WAPE=0 deberia ser TIE
    })
    issue = check_both_zero_wape_is_tie("f.csv", df, "6M", pcols)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "BOTH_ZERO_WAPE_NOT_TIE"


def test_check_both_zero_wape_is_tie_passes_when_tie():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_wape: [0.0],
        pcols.ml_wape: [0.0],
        pcols.winner_method: ["TIE"],
    })
    issue = check_both_zero_wape_is_tie("f.csv", df, "6M", pcols)
    assert issue is None


def test_check_both_zero_wape_is_tie_does_not_touch_relative_tie_case():
    """
    Empate relativo (WAPEs distintos de cero pero muy proximos, WINNER_METHOD
    dice TIE): no se debe generar ninguna incidencia, porque no conocemos la
    formula real de relativeDiff y no se audita ese caso.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_wape: [0.20001],
        pcols.ml_wape: [0.2],
        pcols.winner_method: ["TIE"],
    })
    issue = check_both_zero_wape_is_tie("f.csv", df, "6M", pcols)
    assert issue is None


def test_check_both_zero_wape_is_tie_does_not_flag_ml_winner():
    """ML gana (WAPE menor, no ambos cero): no debe generar incidencia."""
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_wape: [0.3],
        pcols.ml_wape: [0.1],
        pcols.winner_method: ["ML"],
    })
    assert check_both_zero_wape_is_tie("f.csv", df, "6M", pcols) is None


def test_check_both_zero_wape_is_tie_does_not_flag_scp_winner():
    """SCP gana (WAPE menor, no ambos cero): no debe generar incidencia."""
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.scp_wape: [0.1],
        pcols.ml_wape: [0.3],
        pcols.winner_method: ["SCP"],
    })
    assert check_both_zero_wape_is_tie("f.csv", df, "6M", pcols) is None


def test_check_winner_formula_not_auditable_is_a_documented_limitation():
    issue = check_winner_formula_not_auditable("f.csv")
    assert issue.severity == Severity.WARNING
    assert issue.code == "WINNER_FORMULA_NOT_AUDITABLE"
    assert "relativeDiff" in issue.message


# --------------------------------------------------------------------------
# Item 3: historico negativo es WARNING (no ERROR) y conserva detalle de fila.
# --------------------------------------------------------------------------

def test_check_negative_history_is_warning_with_row_detail():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [4468, 999],
        pcols.total_history: [-5.0, 10.0],
    })
    issue = check_negative_history("f.csv", df, "6M", pcols)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.details["n_negative"] == 1
    assert issue.details["affected_rows"] == [{"id_configuration": 4468, "period": "6M", "value": -5.0}]


def test_check_extreme_wape_is_warning():
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_wape: [10.0], pcols.ml_wape: [0.2]})
    issues = check_extreme_wape("f.csv", df, "6M", pcols)
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert issues[0].details["method"] == "SCP"


def test_check_comparable_without_winner_is_error():
    winner = pd.Series([None, "ML"])
    comparable_mask = pd.Series([True, True])
    issue = check_comparable_without_winner("f.csv", "6M", comparable_mask, winner)
    assert issue is not None
    assert issue.severity == Severity.ERROR
    assert issue.details["n_bad"] == 1


def test_check_comparable_without_forecasts_is_error():
    scp = pd.Series([100.0, None])
    ml = pd.Series([90.0, 80.0])
    comparable_mask = pd.Series([True, True])
    issue = check_comparable_without_forecasts("f.csv", "6M", comparable_mask, scp, ml)
    assert issue is not None
    assert issue.details["n_bad"] == 1


# --------------------------------------------------------------------------
# Fase 4: COMPARISON_STATUS es la fuente de verdad de 6M/global; la mascara
# local (period_comparable_mask) pasa a ser solo auditoria/reconciliacion
# frente a ella. La firma/logica de check_comparison_status_vs_period_mask
# no cambia (compara dos mascaras booleanas cualquiera); lo que cambia es
# que el llamador (client_analysis._analyze_period) ahora le pasa la
# mascara LOCAL como segundo argumento, no la mascara backend (ver
# tests/test_client_analysis.py).
# --------------------------------------------------------------------------

def test_check_comparison_status_vs_period_mask_no_discrepancy():
    comparison_status = pd.Series(["COMPARABLE", "NOT_COMPARABLE_NO_HISTORY"])
    local_mask = pd.Series([True, False])
    issue = check_comparison_status_vs_period_mask("f.csv", "6M", comparison_status, local_mask)
    assert issue is None


def test_check_comparison_status_vs_period_mask_flags_discrepancy_in_either_direction():
    comparison_status = pd.Series(["COMPARABLE", "NOT_COMPARABLE_MISSING_SCP", None])
    local_mask = pd.Series([False, True, False])
    issue = check_comparison_status_vs_period_mask("f.csv", "6M", comparison_status, local_mask)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "COMPARISON_STATUS_VS_PERIOD_MASK_DISCREPANCY"
    assert issue.details["n_discrepancy"] == 2
    assert issue.details["only_in_comparison_status"] == 1
    assert issue.details["only_in_period_mask"] == 1


def test_check_comparable_missing_wape_inputs_flags_incomplete_required_columns():
    """
    Fila COMPARABLE (poblacion canonica) con SCP_TOTAL_ABS_ERROR_6M nulo:
    debe generar el issue, sin importar que SCP_WAPE_6M (columna distinta,
    no input de esta formula) este completo o no.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0, 200.0],
        pcols.scp_total_abs_error: [None, 40.0],
        pcols.ml_total_abs_error: [10.0, 20.0],
    })
    comparable_mask = pd.Series([True, True])
    issue = check_comparable_missing_wape_inputs("f.csv", "6M", comparable_mask, df, pcols)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "COMPARABLE_MISSING_WAPE_INPUTS"
    assert issue.details["n_missing"] == 1


def test_check_comparable_missing_wape_inputs_ignores_non_comparable_rows():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0, 200.0],
        pcols.scp_total_abs_error: [None, 40.0],
        pcols.ml_total_abs_error: [10.0, 20.0],
    })
    comparable_mask = pd.Series([False, True])
    issue = check_comparable_missing_wape_inputs("f.csv", "6M", comparable_mask, df, pcols)
    assert issue is None


def test_check_comparable_missing_wape_inputs_no_discrepancy_when_all_complete():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0, 200.0],
        pcols.scp_total_abs_error: [20.0, 40.0],
        pcols.ml_total_abs_error: [10.0, 20.0],
    })
    comparable_mask = pd.Series([True, True])
    issue = check_comparable_missing_wape_inputs("f.csv", "6M", comparable_mask, df, pcols)
    assert issue is None


# --------------------------------------------------------------------------
# Item 8: reconstruccion de la cadena de errores y de MAE/RMSE/Bias.
# --------------------------------------------------------------------------

def test_check_error_chain_reconstruction_detects_abs_and_squared_mismatch():
    pcols = period_columns("M1")
    df = pd.DataFrame({
        pcols.total_history: [100.0],
        pcols.scp_total_forecast: [120.0],
        pcols.scp_total_signed_error: [20.0],   # correcto: 120-100
        pcols.scp_total_abs_error: [999.0],     # incorrecto: deberia ser 20.0
        pcols.scp_total_squared_error: [400.0], # correcto: 20^2
    })
    issues = check_error_chain_reconstruction("f.csv", df, "M1", pcols)
    codes = [i.code for i in issues]
    assert "ABS_ERROR_RECONSTRUCTION_MISMATCH" in codes
    assert "SIGNED_ERROR_RECONSTRUCTION_MISMATCH" not in codes
    assert "SQUARED_ERROR_RECONSTRUCTION_MISMATCH" not in codes


def test_check_error_chain_reconstruction_only_applies_to_monthly_periods():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0],
        pcols.scp_total_forecast: [120.0],
        pcols.scp_total_abs_error: [999.0],
    })
    assert check_error_chain_reconstruction("f.csv", df, "6M", pcols) == []


def test_check_mae_reconstruction_detects_mismatch():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.positive_history_month_count: [4],
        pcols.scp_total_abs_error: [40.0],
        pcols.scp_mae: [999.0],  # deberia ser 10.0
    })
    issues = check_mae_reconstruction("f.csv", df, "6M", pcols)
    assert len(issues) == 1
    assert issues[0].code == "MAE_RECONSTRUCTION_MISMATCH"


def test_check_rmse_reconstruction_detects_mismatch():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.positive_history_month_count: [4],
        pcols.scp_total_squared_error: [400.0],
        pcols.scp_rmse: [999.0],  # deberia ser sqrt(100)=10.0
    })
    issues = check_rmse_reconstruction("f.csv", df, "6M", pcols)
    assert len(issues) == 1
    assert issues[0].code == "RMSE_RECONSTRUCTION_MISMATCH"


def test_check_bias_reconstruction_detects_mismatch():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [100.0],
        pcols.scp_total_signed_error: [10.0],
        pcols.scp_bias: [999.0],  # deberia ser 0.1
    })
    issues = check_bias_reconstruction("f.csv", df, "6M", pcols)
    assert len(issues) == 1
    assert issues[0].code == "BIAS_RECONSTRUCTION_MISMATCH"


# --------------------------------------------------------------------------
# Item 4: warning de normalizacion de CSV envuelto en comillas dobladas.
# --------------------------------------------------------------------------

def test_check_wrapped_csv_normalized_is_warning_with_detail():
    issue = check_wrapped_csv_normalized("f.csv", "columnas insuficientes", 1, 234, 500)
    assert issue.severity == Severity.WARNING
    assert issue.code == "WRAPPED_CSV_NORMALIZED"
    assert issue.details["columns_before"] == 1
    assert issue.details["columns_after"] == 234
    assert issue.details["n_rows_recovered"] == 500


# --------------------------------------------------------------------------
# Item 10: heterogeneidad de batch y mojibake.
# --------------------------------------------------------------------------

def test_check_batch_heterogeneity_detects_multiple_batches():
    issue = check_batch_heterogeneity({10204: [63], 10620: [62]})
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "BATCH_HETEROGENEITY_ACROSS_CLIENTS"


def test_check_batch_heterogeneity_passes_when_single_batch():
    issue = check_batch_heterogeneity({10204: [63], 10467: [63]})
    assert issue is None


def test_check_mojibake_detects_replacement_character_and_double_encoding():
    df = pd.DataFrame({"VALUE_LEVEL_1": ["Graneles Helader�as", "DECORACIÃ“N", "Normal"]})
    issue = check_mojibake_in_value_levels("f.csv", df)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.details["counts_by_column"]["VALUE_LEVEL_1"] == 2


def test_check_mojibake_passes_on_clean_text():
    df = pd.DataFrame({"VALUE_LEVEL_1": ["Heladerías", "Decoración", "Muebles"]})
    assert check_mojibake_in_value_levels("f.csv", df) is None


# --------------------------------------------------------------------------
# Fase 9B: METRIC_001-005 (auditoria de dominio matematico y de valores
# backend inesperados). Todos WARNING; ninguno reconstruye ni cambia
# comparabilidad/winner/Bias/WAPE (ver plan aprobado en Fase 9A).
# --------------------------------------------------------------------------

def test_negative_domain_fields_scope_is_10_columns_per_period():
    """Guarda de regresion sobre el alcance aprobado en 9A: 5 metricas x 2 metodos."""
    assert len(_NEGATIVE_DOMAIN_FIELDS) == 10


def test_infinite_check_attrs_scope_is_18_columns_per_period():
    """Guarda de regresion sobre el alcance aprobado en 9A: 18 columnas por periodo."""
    assert len(_INFINITE_CHECK_ATTRS) == 18


def test_check_negative_nonnegative_metrics_detects_negative_wape():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [1, 2],
        pcols.scp_wape: [-0.1, 0.2],  # WAPE es dominio matematico >=0
    })
    issues = check_negative_nonnegative_metrics("f.csv", df, "6M", pcols)
    codes = [i.code for i in issues]
    assert codes == ["NEGATIVE_NONNEGATIVE_METRIC_VALUE"]
    assert issues[0].details["method"] == "SCP"
    assert issues[0].details["metric"] == "WAPE"
    assert issues[0].details["n_violations"] == 1
    assert issues[0].details["sample_ids"] == [1]


def test_check_negative_nonnegative_metrics_nan_does_not_trigger():
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_wape: [None, 0.2]})
    assert check_negative_nonnegative_metrics("f.csv", df, "6M", pcols) == []


def test_check_negative_nonnegative_metrics_infinite_does_not_trigger():
    """Un +-inf no dispara METRIC_001 (np.isfinite lo descarta); lo cubre METRIC_002."""
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_wape: [float("inf"), float("-inf"), 0.2]})
    assert check_negative_nonnegative_metrics("f.csv", df, "6M", pcols) == []


def test_check_negative_nonnegative_metrics_ignores_signed_error_bias_history_forecast():
    """
    SIGNED_ERROR, BIAS, HISTORY y FORECAST pueden ser negativos legitimamente:
    no forman parte del dominio auditado por este check.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.total_history: [-5.0],
        pcols.scp_total_forecast: [-1.0],
        pcols.scp_total_signed_error: [-3.0],
        pcols.scp_bias: [-0.5],
    })
    assert check_negative_nonnegative_metrics("f.csv", df, "6M", pcols) == []


def test_check_infinite_backend_metrics_detects_inf_in_history():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        "ID_CONFIGURATION": [1, 2],
        pcols.total_history: [float("inf"), 100.0],
    })
    issues = check_infinite_backend_metrics("f.csv", df, "6M", pcols)
    codes = [i.code for i in issues]
    assert codes == ["INFINITE_METRIC_VALUE"]
    assert issues[0].details["column"] == pcols.total_history
    assert issues[0].details["n_violations"] == 1
    assert issues[0].details["sample_ids"] == [1]


def test_check_infinite_backend_metrics_detects_negative_inf_in_bias():
    """BIAS puede ser negativo, pero -inf no es un valor finito valido: METRIC_002 si lo audita."""
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_bias: [float("-inf"), -0.2]})
    issues = check_infinite_backend_metrics("f.csv", df, "6M", pcols)
    assert [i.code for i in issues] == ["INFINITE_METRIC_VALUE"]
    assert issues[0].details["column"] == pcols.scp_bias


def test_check_infinite_backend_metrics_nan_does_not_trigger():
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.total_history: [None, 100.0]})
    assert check_infinite_backend_metrics("f.csv", df, "6M", pcols) == []


def test_check_infinite_backend_metrics_ignores_categorical_and_count_columns():
    pcols = period_columns("6M")
    df = pd.DataFrame({
        pcols.winner_method: ["ML"],
        pcols.winner_model: ["AutoETS"],
        pcols.positive_history_month_count: [6],
    })
    assert check_infinite_backend_metrics("f.csv", df, "6M", pcols) == []


def test_check_invalid_winner_method_value_detects_unexpected_literal():
    pcols = period_columns("6M")
    winner = pd.Series(["ML", "DRAW", "SCP"], name=pcols.winner_method)
    comparable_mask = pd.Series([True, True, True])
    issue = check_invalid_winner_method_value("f.csv", "6M", comparable_mask, winner)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "INVALID_WINNER_METHOD_VALUE"
    assert issue.details["unexpected_values"] == {"DRAW": 1}
    assert issue.details["n_rows"] == 1


def test_check_invalid_winner_method_value_does_not_duplicate_null_winner():
    """Winner nulo en fila comparable ya es ERROR via check_comparable_without_winner; no se duplica aqui."""
    pcols = period_columns("6M")
    winner = pd.Series([None, "ML"], name=pcols.winner_method)
    comparable_mask = pd.Series([True, True])
    assert check_invalid_winner_method_value("f.csv", "6M", comparable_mask, winner) is None


def test_check_invalid_winner_method_value_ignores_non_comparable_rows():
    pcols = period_columns("6M")
    winner = pd.Series(["DRAW", "ML"], name=pcols.winner_method)
    comparable_mask = pd.Series([False, True])
    assert check_invalid_winner_method_value("f.csv", "6M", comparable_mask, winner) is None


def test_check_invalid_winner_method_value_accepts_full_valid_domain():
    pcols = period_columns("6M")
    winner = pd.Series(["ML", "SCP", "TIE"], name=pcols.winner_method)
    comparable_mask = pd.Series([True, True, True])
    assert check_invalid_winner_method_value("f.csv", "6M", comparable_mask, winner) is None


def test_check_unknown_comparison_status_value_accepts_full_known_domain():
    """Dominio confirmado por grep dirigido en Fase 9B (docs/backend-validation-flow.md, 8 estados)."""
    df = pd.DataFrame({"COMPARISON_STATUS": [
        "COMPARABLE", "NOT_COMPARABLE_NO_HISTORY", "NOT_COMPARABLE_MISSING_SCP",
        "NOT_COMPARABLE_MISSING_ML", "NOT_COMPARABLE_MISSING_SCP_AND_ML",
        "NOT_COMPARABLE_ML_EXCLUDED", "NOT_COMPARABLE_MISSING_VALIDATION",
        "NOT_COMPARABLE_RUN_FAILED",
    ]})
    assert check_unknown_comparison_status_value("f.csv", df) is None


def test_check_unknown_comparison_status_value_detects_unexpected_literal():
    df = pd.DataFrame({"COMPARISON_STATUS": ["COMPARABLE", "NOT_COMPARABLE_NEW_REASON"]})
    issue = check_unknown_comparison_status_value("f.csv", df)
    assert issue is not None
    assert issue.severity == Severity.WARNING
    assert issue.code == "UNKNOWN_COMPARISON_STATUS_VALUE"
    assert issue.details["unexpected_values"] == {"NOT_COMPARABLE_NEW_REASON": 1}


def test_check_unknown_comparison_status_value_null_is_not_unknown():
    df = pd.DataFrame({"COMPARISON_STATUS": ["COMPARABLE", None]})
    assert check_unknown_comparison_status_value("f.csv", df) is None


def test_check_invalid_binary_flag_value_detects_out_of_domain():
    df = pd.DataFrame({"HAS_ML_EXCLUDED": [0, 1, 2]})
    issues = check_invalid_binary_flag_value("f.csv", df)
    assert len(issues) == 1
    assert issues[0].code == "INVALID_BINARY_FLAG_VALUE"
    assert issues[0].details["column"] == "HAS_ML_EXCLUDED"
    assert issues[0].details["n_rows"] == 1


def test_check_invalid_binary_flag_value_nan_does_not_trigger():
    df = pd.DataFrame({"HAS_SCP_CALCULATED": [0, 1, None]})
    assert check_invalid_binary_flag_value("f.csv", df) == []


def test_check_invalid_binary_flag_value_accepts_zero_and_one():
    df = pd.DataFrame({
        "HAS_BASE_CANDIDATE": [1, 0], "HAS_SCP_CALCULATED": [1, 1],
        "HAS_ML_CALCULATED": [0, 1], "HAS_ML_EXCLUDED": [0, 0],
    })
    assert check_invalid_binary_flag_value("f.csv", df) == []


# --------------------------------------------------------------------------
# Auditoria de Fase 9B: robustez dtype object/string, no-duplicacion con
# counts explicitos, y confirmacion de que METRIC_003 nunca usa la mascara
# backend de 6M para periodos mensuales/trimestrales.
# --------------------------------------------------------------------------

def test_check_negative_nonnegative_metrics_object_dtype_does_not_raise_and_coerces_correctly():
    """
    Robustez dtype object/string: aunque el contrato de carga real
    (input_loader.coerce_numeric_columns) ya garantiza dtype numerico para
    estas columnas antes de que lleguen a analyze_client (WAPE/MAE/RMSE/
    ABS_ERROR/SQUARED_ERROR no estan en _CATEGORICAL_COLUMNS ni matchean
    _CATEGORICAL_SUFFIXES), el propio check es defensivo por si mismo
    (_coerce_numeric) y no debe lanzar TypeError si recibe una Series object
    con strings no numericos -- p.ej. un DataFrame construido a mano en tests.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_wape: pd.Series(["no-numerico", "-0.1", None, 0.2], dtype=object)})
    issues = check_negative_nonnegative_metrics("f.csv", df, "6M", pcols)
    assert [i.code for i in issues] == ["NEGATIVE_NONNEGATIVE_METRIC_VALUE"]
    assert issues[0].details["n_violations"] == 1  # solo "-0.1" coerciona a negativo; "no-numerico" coerciona a NaN


def test_check_infinite_backend_metrics_object_dtype_does_not_raise_and_coerces_correctly():
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.total_history: pd.Series(["no-numerico", float("inf"), None, 100.0], dtype=object)})
    issues = check_infinite_backend_metrics("f.csv", df, "6M", pcols)
    assert [i.code for i in issues] == ["INFINITE_METRIC_VALUE"]
    assert issues[0].details["n_violations"] == 1


def test_check_invalid_binary_flag_value_object_dtype_does_not_raise_and_coerces_correctly():
    df = pd.DataFrame({"HAS_ML_EXCLUDED": pd.Series(["no-numerico", "1", None, 2.0], dtype=object)})
    issues = check_invalid_binary_flag_value("f.csv", df)
    assert len(issues) == 1
    # "1" (string) coerciona a 1.0 (valido, no dispara); "no-numerico" coerciona a NaN (no dispara); solo 2.0 dispara.
    assert issues[0].details["n_rows"] == 1


def test_negative_infinite_wape_triggers_metric_002_but_not_metric_001():
    """
    Punto 9 del brief de auditoria: un -inf en una metrica del dominio
    COMPARTIDO por ambos checks (WAPE) debe disparar METRIC_002
    (INFINITE_METRIC_VALUE) pero explicitamente NO METRIC_001
    (NEGATIVE_NONNEGATIVE_METRIC_VALUE) -- np.isfinite descarta el valor
    infinito de la condicion "negativo" en METRIC_001.
    """
    pcols = period_columns("6M")
    df = pd.DataFrame({pcols.scp_wape: [float("-inf"), 0.2]})

    negative_issues = check_negative_nonnegative_metrics("f.csv", df, "6M", pcols)
    infinite_issues = check_infinite_backend_metrics("f.csv", df, "6M", pcols)

    assert negative_issues == []
    assert [i.code for i in infinite_issues] == ["INFINITE_METRIC_VALUE"]
    assert infinite_issues[0].details["n_violations"] == 1


def test_check_invalid_binary_flag_value_one_issue_per_affected_column_not_per_row():
    """
    Contrato de METRIC_005: un issue POR COLUMNA afectada (no un issue global
    combinando varias columnas, ni un issue por fila).
    """
    df = pd.DataFrame({
        "HAS_SCP_CALCULATED": [2, 0], "HAS_ML_CALCULATED": [0, 3], "HAS_BASE_CANDIDATE": [1, 0],
    })
    issues = check_invalid_binary_flag_value("f.csv", df)
    columns = {i.details["column"] for i in issues}
    assert columns == {"HAS_SCP_CALCULATED", "HAS_ML_CALCULATED"}  # HAS_BASE_CANDIDATE (valida) no genera issue
    assert len(issues) == 2


def test_null_winner_triggers_comparable_without_winner_but_not_metric_003():
    """
    Winner nulo en fila comparable: dispara COMPARABLE_WITHOUT_WINNER (ERROR,
    check preexistente) pero NUNCA METRIC_003 (INVALID_WINNER_METHOD_VALUE) --
    METRIC_003 excluye explicitamente los nulos de su condicion para no
    duplicar la incidencia ya cubierta.
    """
    pcols = period_columns("6M")
    winner = pd.Series([None, "ML"], name=pcols.winner_method)
    comparable_mask = pd.Series([True, True])

    metric_003_issue = check_invalid_winner_method_value("f.csv", "6M", comparable_mask, winner)
    without_winner_issue = check_comparable_without_winner("f.csv", "6M", comparable_mask, winner)

    assert metric_003_issue is None
    assert without_winner_issue is not None
    assert without_winner_issue.severity == Severity.ERROR
    assert without_winner_issue.details["n_bad"] == 1
