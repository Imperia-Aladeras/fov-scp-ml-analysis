from pathlib import Path

import openpyxl

from src.execution_summary import (
    build_execution_records,
    build_execution_summary_markdown,
    build_execution_summary_workbook,
    execution_summary_table,
)
from tests.factories import build_multi_client_results


def test_build_execution_records_one_per_client():
    results = build_multi_client_results()
    outputs_by_file = {r.source.file_name: [] for r in results}
    durations_by_file = {r.source.file_name: 0.42 for r in results}
    records = build_execution_records(results, outputs_by_file, durations_by_file)

    assert len(records) == 3
    assert {rec.id_client for rec in records} == {99999, 88888, 77777}
    assert all(rec.duracion_segundos == 0.42 for rec in records)


def test_execution_summary_table_columns():
    results = build_multi_client_results()
    outputs = {r.source.file_name: [f"outputs/{r.source.folder_name}/x.xlsx", f"outputs/{r.source.folder_name}/x.md",
                                     "c.png", "c.png"] for r in results}
    durations = {r.source.file_name: 1.0 for r in results}
    records = build_execution_records(results, outputs, durations)
    table = execution_summary_table(records)

    assert list(table.columns) == [
        "ARCHIVO", "CARPETA_SALIDA", "ID_CLIENT", "ETIQUETA", "ID_BATCH", "ID_RUN_STAGING",
        "FILAS", "CANDIDATAS", "COMPARABLES_6M", "ESTADO", "WARNINGS", "ERRORS",
        "DURACION_SEGUNDOS", "INFORME_GENERADO", "EXCEL_GENERADO", "GRAFICOS_GENERADOS",
    ]
    assert (table["GRAFICOS_GENERADOS"] == 2).all()
    assert table["INFORME_GENERADO"].all()
    assert table["EXCEL_GENERADO"].all()


def test_build_execution_summary_workbook_creates_file(tmp_path: Path):
    results = build_multi_client_results()
    records = build_execution_records(results, {}, {})
    out_path = tmp_path / "execution_summary.xlsx"
    build_execution_summary_workbook(records, out_path)

    assert out_path.exists()
    wb = openpyxl.load_workbook(out_path)
    assert wb.sheetnames == ["execution_summary"]
    ws = wb["execution_summary"]
    assert ws.max_row == 4  # cabecera + 3 clientes


def test_build_execution_summary_markdown_mentions_all_clients():
    results = build_multi_client_results()
    records = build_execution_records(results, {}, {})
    markdown = build_execution_summary_markdown(records)
    for name in ("TA_FOV_SCP_ML_99999_Synthetic.csv", "TA_FOV_SCP_ML_88888_NoComparable.csv", "TA_FOV_SCP_ML_77777_AllMlWins.csv"):
        assert name in markdown
