from pathlib import Path

import openpyxl

from src.excel_writer import (
    EXEC_SUMMARY_PERIODS,
    _column_number_format,
    _dict_to_df,
    build_client_workbook,
    executive_summary_table,
    pareto_absolute_impact_blocks,
)
from tests.factories import build_synthetic_client_result

EXPECTED_SHEETS = [
    "00_readme", "01_executive_summary", "02_coverage_status", "03_semester", "04_first_quarter",
    "05_second_quarter", "06_monthly_summary", "07_monthly_winners", "08_models_and_win_rates",
    "09_classifications", "10_exclusions", "11_top_absolute_impact", "12_top_percentage_changes",
    "13_data_quality_checks", "14_pareto_absolute_impact",
]


def test_dict_to_df_sorted_descending():
    df = _dict_to_df({"a": 1, "b": 5, "c": 3}, "K", "V")
    assert df["K"].tolist() == ["b", "c", "a"]


def test_dict_to_df_empty():
    df = _dict_to_df({}, "K", "V")
    assert df.empty


def test_column_number_format_hints():
    assert _column_number_format("WAPE_SCP") == "0.0%"
    assert _column_number_format("MEJORA_RELATIVA_PCT") == '0.0"%"'
    assert _column_number_format("HISTORICO_TOTAL") == "#,##0"
    assert _column_number_format("ID_CONFIGURATION") is None


def test_executive_summary_table_has_one_row_per_period():
    result = build_synthetic_client_result(with_data=True)
    table = executive_summary_table(result)
    assert table["PERIODO"].tolist() == EXEC_SUMMARY_PERIODS
    row_6m = table[table["PERIODO"] == "6M"].iloc[0]
    assert row_6m["SERIES_COMPARABLES"] == 2


def test_build_client_workbook_creates_all_sheets(tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)
    out_path = tmp_path / "summary.xlsx"
    build_client_workbook(result, out_path)

    assert out_path.exists()
    wb = openpyxl.load_workbook(out_path)
    assert wb.sheetnames == EXPECTED_SHEETS


def test_build_client_workbook_no_comparable_series_does_not_crash(tmp_path: Path):
    """
    Item explicito de la Fase 3: un cliente sin series comparables sigue
    siendo un caso valido; el Excel se genera igualmente sin inventar datos.
    """
    result = build_synthetic_client_result(with_data=False)
    out_path = tmp_path / "summary_empty.xlsx"
    build_client_workbook(result, out_path)

    assert out_path.exists()
    wb = openpyxl.load_workbook(out_path)
    assert wb.sheetnames == EXPECTED_SHEETS

    ws = wb["01_executive_summary"]
    row_values = [cell.value for cell in ws[3]]  # primera fila de datos (6M)
    assert row_values[3] == 0  # SERIES_COMPARABLES = 0


# --------------------------------------------------------------------------
# 14_pareto_absolute_impact
# --------------------------------------------------------------------------

def test_pareto_absolute_impact_blocks_basic_content():
    result = build_synthetic_client_result(with_data=True)
    blocks = pareto_absolute_impact_blocks(result)
    titles = [t for t, _ in blocks]
    assert any("mejora" in t for t in titles)
    assert any("deterioro" in t for t in titles)
    assert any("Resumen de concentracion" in t for t in titles)

    improvement_table = next(df for t, df in blocks if "mejora" in t)
    deterioration_table = next(df for t, df in blocks if "deterioro" in t)
    assert improvement_table["ID_CONFIGURATION"].tolist() == [1001]
    assert deterioration_table["ID_CONFIGURATION"].tolist() == [1002]

    summary_table = next(df for t, df in blocks if "Resumen de concentracion" in t)
    assert summary_table["N_TOTAL"].tolist() == [1, 1]
    assert summary_table["N_NO_EVALUABLES"].tolist() == [0, 0]


def test_pareto_absolute_impact_blocks_reads_precomputed_pareto_without_recomputing():
    """
    La hoja 14 nunca debe volver a llamar a pareto_absolute_impact ni a
    build_pareto_analysis: las tablas devueltas deben ser exactamente los
    mismos objetos DataFrame ya almacenados en PeriodResult.pareto (una
    recomputacion produciria un DataFrame distinto, aunque tuviera el mismo
    contenido).
    """
    result = build_synthetic_client_result(with_data=True)
    pr = result.periods["6M"]
    blocks = {title: df for title, df in pareto_absolute_impact_blocks(result)}

    improvement_title = next(t for t in blocks if "mejora" in t)
    deterioration_title = next(t for t in blocks if "deterioro" in t)
    assert blocks[improvement_title] is pr.pareto.improvement.table
    assert blocks[deterioration_title] is pr.pareto.deterioration.table


def test_pareto_absolute_impact_blocks_all_improvement_client_notes_empty_deterioration(tmp_path: Path):
    from tests.factories import build_multi_client_results

    all_ml_result = build_multi_client_results()[2]  # 77777_AllMlWins: ambas filas ganan ML en 6M
    blocks = pareto_absolute_impact_blocks(all_ml_result)

    deterioration_table = next(df for t, df in blocks if "deterioro" in t)
    assert deterioration_table.empty
    note_texts = [v for t, df in blocks if t == "Nota" for v in df[""].tolist()]
    assert any("Sin series con deterioro" in n for n in note_texts)

    out_path = tmp_path / "all_ml.xlsx"
    build_client_workbook(all_ml_result, out_path)
    assert out_path.exists()
    wb = openpyxl.load_workbook(out_path)
    assert wb.sheetnames == EXPECTED_SHEETS
