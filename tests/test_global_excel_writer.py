from pathlib import Path

import openpyxl

from src.client_analysis import analyze_client
from src.global_analysis import GlobalAnalysisResult
from src.global_excel_writer import build_global_workbook, data_quality_checks_blocks, readme_blocks
from src.quality_checks import QualityIssue, Severity
from tests.factories import build_global_analysis_result, build_synthetic_client_dataframe, make_client_source

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


def test_readme_client_lists_show_id_client_alongside_display_name():
    """
    El listado de clientes del README global (00_readme) no debe mostrar
    unicamente el nombre de catalogo: el catalogo no garantiza nombres unicos
    entre ID_CLIENT distintos.
    """
    result = build_global_analysis_result()
    blocks = readme_blocks(result)
    lines = "\n".join(blocks[0][1][""].astype(str))

    assert "Synthetic (99999)" in lines
    assert "NoComparable (88888)" in lines
    assert "AllMlWins (77777)" in lines


def test_data_quality_checks_counts_affected_clients_by_id_not_by_shared_file_label(tmp_path: Path):
    """
    Fase 5, bug corregido: dos ClientAnalysisResult que comparten el mismo
    file_label (porque proceden del mismo CSV fisico multi-cliente, Fase 3)
    deben contarse como 2 clientes afectados, no colapsar en 1 por compartir
    file_label/display_name como clave de identidad.
    """
    df_a = build_synthetic_client_dataframe()
    source_a = make_client_source(df_a, 10001, "SharedLabel")
    result_a = analyze_client(source_a)

    df_b = build_synthetic_client_dataframe()
    df_b["ID_CLIENT"] = 10002
    source_b = make_client_source(df_b, 10002, "SharedLabel")
    # mismo CSV fisico: mismo file_label y display_name que source_a, pero ID_CLIENT distinto
    source_b.file_label = source_a.file_label
    source_b.display_name = source_a.display_name
    result_b = analyze_client(source_b)

    same_issue = QualityIssue(
        Severity.WARNING, "SHARED_TEST_ISSUE", "incidencia sintetica compartida", scope="file",
    )
    result_a.quality.add(same_issue)
    result_b.quality.add(same_issue)

    global_result = GlobalAnalysisResult(client_results=[result_a, result_b], invalid_results=[])
    blocks = data_quality_checks_blocks(global_result)
    summary_df = blocks[0][1]

    row = summary_df[summary_df["CODIGO"] == "SHARED_TEST_ISSUE"].iloc[0]
    assert row["N_OCURRENCIAS"] == 2
    assert row["N_CLIENTES_AFECTADOS"] == 2

    # El detalle fila a fila (misma hoja) tambien debe llevar ID_CLIENT: el
    # resumen ya deduplicaba bien, pero el detalle solo mostraba CLIENTE
    # (display_name), y ambos clientes sinteticos comparten display_name.
    detail_df = blocks[1][1]
    shared_detail = detail_df[detail_df["CODIGO"] == "SHARED_TEST_ISSUE"]
    assert set(shared_detail["ID_CLIENT"]) == {10001, 10002}
    assert list(shared_detail.columns[:2]) == ["ID_CLIENT", "CLIENTE"]
