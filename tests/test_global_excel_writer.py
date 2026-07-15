from pathlib import Path

import openpyxl

from src.global_excel_writer import build_global_workbook
from tests.factories import build_global_analysis_result

EXPECTED_SHEETS = [
    "00_readme", "01_executive_summary", "02_client_coverage", "03_semester_by_client",
    "04_first_quarter_by_client", "05_second_quarter_by_client", "06_monthly_by_client",
    "07_global_period_summary", "08_client_improvement_stats", "09_series_improvement_stats",
    "10_winner_distribution", "11_models_and_win_rates", "12_classifications",
    "13_absolute_impact", "14_exclusions", "15_data_quality_checks",
]


def test_build_global_workbook_creates_all_sheets(tmp_path: Path):
    result = build_global_analysis_result()
    out_path = tmp_path / "global_summary.xlsx"
    build_global_workbook(result, out_path)

    assert out_path.exists()
    wb = openpyxl.load_workbook(out_path)
    assert wb.sheetnames == EXPECTED_SHEETS


def test_global_period_summary_has_one_row_per_period(tmp_path: Path):
    result = build_global_analysis_result()
    out_path = tmp_path / "global_summary.xlsx"
    build_global_workbook(result, out_path)

    wb = openpyxl.load_workbook(out_path)
    ws = wb["07_global_period_summary"]
    # fila 1 = titulo del bloque, fila 2 = cabecera, filas 3+ = una por periodo
    period_cells = [r[0] for r in ws.iter_rows(min_row=3, values_only=True) if r[0]]
    assert len(period_cells) == 9
