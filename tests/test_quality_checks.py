import pandas as pd

from src.periods import period_columns
from src.quality_checks import (
    Severity,
    StructuralInputError,
    check_aggregate_vs_monthly_sum,
    check_bias_reconstruction,
    check_batch_heterogeneity,
    check_both_zero_wape_is_tie,
    check_comparable_missing_wape_inputs,
    check_comparable_without_forecasts,
    check_comparable_without_winner,
    check_comparison_status_vs_period_mask,
    check_error_chain_reconstruction,
    check_extreme_wape,
    check_mae_reconstruction,
    check_mojibake_in_value_levels,
    check_negative_history,
    check_rmse_reconstruction,
    check_wape_reconstruction,
    check_winner_formula_not_auditable,
    check_wrapped_csv_normalized,
)


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
