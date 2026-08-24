"""
Fase 8C -- auditoria: comprueba que el mismo valor de nucleo (PeriodResult.phase8)
llega SIN DIVERGENCIA de contenido (solo diferencias de formato/representacion)
a Excel, Markdown y HTML, para una tabla de VOLUME_BUCKET y una tabla de modelo.
No recalcula nada: toma como referencia phase8.volume_table/model_tables ya
calculados por el nucleo (build_synthetic_client_result / build_volume_bucket_client_result
en tests/factories.py) y compara contra lo que produce cada writer.
"""

from pathlib import Path

import openpyxl
import pytest

from src import html_view_models as vm
from src.excel_writer import build_client_workbook
from src.phase8_presentation import direction_label_es, sort_volume_table
from src.report_writer import (
    _fmt_num,
    _fmt_pct_fraction,
    _fmt_pct_scaled,
    _fmt_signed_pct_fraction,
    _fmt_signed_pct_scaled,
    build_client_report,
)
from tests.factories import build_volume_bucket_client_result

CHECK_COLUMNS = (
    "n_comparable", "win_rate_ml_pct", "scp_wape_agg", "ml_wape_agg", "improvement_agg_pct",
    "abs_error_reduction", "pct_of_history_volume", "scp_bias_agg", "ml_bias_agg",
    "scp_direction", "ml_direction", "small_sample",
)


def _md_table_row(markdown: str, section_marker: str, next_marker: str, row_label: str) -> dict:
    """Extrae una fila de una tabla markdown (pipe table) como dict {header: valor}."""
    section = markdown.split(section_marker)[1].split(next_marker)[0]
    lines = [ln for ln in section.splitlines() if ln.strip().startswith("|")]
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    for line in lines[2:]:  # linea 0 = headers, linea 1 = separador ---
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == row_label:
            return dict(zip(headers, cells))
    raise AssertionError(f"fila '{row_label}' no encontrada en la seccion '{section_marker}'")


def _xlsx_block_rows(path: Path, sheet: str, header_marker: str) -> list[dict]:
    """
    Lee UN bloque de `write_blocks` (src/excel_writer.py): localiza la fila de
    encabezados cuya primera celda es exactamente `header_marker` (p.ej.
    "VOLUME_BUCKET" o "category" -- el nombre de columna real del DataFrame
    de origen, nunca inventado aqui) y devuelve las filas de datos que le
    siguen hasta la primera fila vacia/siguiente bloque.
    """
    wb = openpyxl.load_workbook(path)
    ws = wb[sheet]
    rows_iter = list(ws.iter_rows(values_only=True))
    header_idx = next(i for i, row in enumerate(rows_iter) if row and row[0] == header_marker)
    headers = rows_iter[header_idx]
    result = []
    for row in rows_iter[header_idx + 1:]:
        if row[0] is None:
            break
        result.append({h: v for h, v in zip(headers, row) if h is not None})
    return result


def test_volume_bucket_low_group_consistent_across_excel_markdown_html(tmp_path: Path):
    result = build_volume_bucket_client_result()
    pr = result.periods["6M"]
    core_table = sort_volume_table(pr.phase8.volume_table)
    core_row = core_table[core_table["category"] == "RELATIVE_LOW"].iloc[0]

    # --- Excel: valores NUMERICOS crudos (mismo valor, sin reescalar) ---
    xlsx_path = tmp_path / "client.xlsx"
    build_client_workbook(result, xlsx_path)
    xlsx_rows = _xlsx_block_rows(xlsx_path, "15_phase8_bias_volume", "VOLUME_BUCKET")
    xlsx_row = next(r for r in xlsx_rows if r.get("VOLUME_BUCKET") == "Bajo relativo")
    assert xlsx_row["n_comparable"] == core_row["n_comparable"]
    assert xlsx_row["win_rate_ml_pct"] == pytest.approx(core_row["win_rate_ml_pct"])
    assert xlsx_row["scp_wape_agg"] == pytest.approx(core_row["scp_wape_agg"])
    assert xlsx_row["ml_wape_agg"] == pytest.approx(core_row["ml_wape_agg"])
    assert xlsx_row["improvement_agg_pct"] == pytest.approx(core_row["improvement_agg_pct"])
    assert xlsx_row["abs_error_reduction"] == pytest.approx(core_row["abs_error_reduction"])
    assert xlsx_row["pct_of_history_volume"] == pytest.approx(core_row["pct_of_history_volume"])
    assert xlsx_row["scp_bias_agg"] == pytest.approx(core_row["scp_bias_agg"])
    assert xlsx_row["ml_bias_agg"] == pytest.approx(core_row["ml_bias_agg"])
    assert xlsx_row["scp_direction"] == direction_label_es(core_row["scp_direction"])
    assert xlsx_row["ml_direction"] == direction_label_es(core_row["ml_direction"])
    assert bool(xlsx_row["small_sample"]) == bool(core_row["small_sample"])

    # --- Markdown: valores FORMATEADOS, comparados contra el mismo formatter ---
    report = build_client_report(result)
    md_row = _md_table_row(report, "## 18. Diagnóstico Fase 8", "## 19.", "Bajo relativo")
    assert md_row["N"] == _fmt_num(core_row["n_comparable"])
    assert md_row["Tasa victoria ML"] == _fmt_pct_scaled(core_row["win_rate_ml_pct"])
    assert md_row["WAPE SCP"] == _fmt_pct_fraction(core_row["scp_wape_agg"])
    assert md_row["WAPE ML"] == _fmt_pct_fraction(core_row["ml_wape_agg"])
    assert md_row["Mejora agregada"] == _fmt_signed_pct_scaled(core_row["improvement_agg_pct"])
    assert md_row["Reduccion absoluta"] == _fmt_num(core_row["abs_error_reduction"])
    assert md_row["% volumen historico"] == _fmt_pct_scaled(core_row["pct_of_history_volume"])
    assert md_row["Bias SCP"] == _fmt_signed_pct_fraction(core_row["scp_bias_agg"])
    assert md_row["Bias ML"] == _fmt_signed_pct_fraction(core_row["ml_bias_agg"])
    assert md_row["Direccion SCP"] == direction_label_es(core_row["scp_direction"])
    assert md_row["Direccion ML"] == direction_label_es(core_row["ml_direction"])
    assert md_row["Muestra pequena"] == ("si" if core_row["small_sample"] else "no")

    # --- HTML view-model: mismos formatters que Markdown (fmt_* == _fmt_* en valor) ---
    page_vm = vm.build_client_page_vm(result)
    html_row = next(r for r in page_vm["phase8"]["volume"]["rows"] if r["bucket"] == "Bajo relativo")
    assert html_row["n"] == _fmt_num(core_row["n_comparable"])
    assert html_row["tasa_victoria_ml"] == _fmt_pct_scaled(core_row["win_rate_ml_pct"])
    assert html_row["wape_scp"] == _fmt_pct_fraction(core_row["scp_wape_agg"])
    assert html_row["wape_ml"] == _fmt_pct_fraction(core_row["ml_wape_agg"])
    assert html_row["mejora_agregada"] == _fmt_signed_pct_scaled(core_row["improvement_agg_pct"])
    assert html_row["abs_error_reduction"] == _fmt_num(core_row["abs_error_reduction"])
    assert html_row["pct_of_history_volume"] == _fmt_pct_scaled(core_row["pct_of_history_volume"])
    assert html_row["scp_bias"] == _fmt_signed_pct_fraction(core_row["scp_bias_agg"])
    assert html_row["ml_bias"] == _fmt_signed_pct_fraction(core_row["ml_bias_agg"])
    assert html_row["scp_direction"] == direction_label_es(core_row["scp_direction"])
    assert html_row["ml_direction"] == direction_label_es(core_row["ml_direction"])
    assert html_row["muestra_pequena"] == bool(core_row["small_sample"])


def test_model_table_autoets_group_consistent_across_excel_markdown_html(tmp_path: Path):
    result = build_volume_bucket_client_result()
    pr = result.periods["6M"]
    core_row = pr.phase8.model_tables["ML_BEST_MODEL"]
    core_row = core_row[core_row["category"] == "AutoETS"].iloc[0]

    xlsx_path = tmp_path / "client.xlsx"
    build_client_workbook(result, xlsx_path)
    xlsx_rows = _xlsx_block_rows(xlsx_path, "08_models_and_win_rates", "category")
    xlsx_row = next(r for r in xlsx_rows if r.get("category") == "AutoETS")
    assert xlsx_row["n_comparable"] == core_row["n_comparable"]
    assert xlsx_row["scp_wape_agg"] == pytest.approx(core_row["scp_wape_agg"])
    assert xlsx_row["ml_wape_agg"] == pytest.approx(core_row["ml_wape_agg"])
    assert xlsx_row["abs_error_reduction"] == pytest.approx(core_row["abs_error_reduction"])
    assert xlsx_row["pct_of_history_volume"] == pytest.approx(core_row["pct_of_history_volume"])
    assert xlsx_row["scp_bias_agg"] == pytest.approx(core_row["scp_bias_agg"])
    assert xlsx_row["ml_bias_agg"] == pytest.approx(core_row["ml_bias_agg"])
    assert xlsx_row["scp_direction"] == direction_label_es(core_row["scp_direction"])

    report = build_client_report(result)
    md_row = _md_table_row(report, "## 10. Modelos ML", "## 11.", "AutoETS")
    assert md_row["N"] == _fmt_num(core_row["n_comparable"])
    assert md_row["WAPE SCP"] == _fmt_pct_fraction(core_row["scp_wape_agg"])
    assert md_row["WAPE ML"] == _fmt_pct_fraction(core_row["ml_wape_agg"])
    assert md_row["Reduccion absoluta"] == _fmt_num(core_row["abs_error_reduction"])
    assert md_row["% volumen historico"] == _fmt_pct_scaled(core_row["pct_of_history_volume"])
    assert md_row["Bias SCP"] == _fmt_signed_pct_fraction(core_row["scp_bias_agg"])
    assert md_row["Direccion SCP"] == direction_label_es(core_row["scp_direction"])

    page_vm = vm.build_client_page_vm(result)
    html_row = next(r for r in page_vm["ml_models"] if r["categoria"] == "AutoETS")
    assert html_row["n"] == _fmt_num(core_row["n_comparable"])
    assert html_row["wape_scp"] == _fmt_pct_fraction(core_row["scp_wape_agg"])
    assert html_row["wape_ml"] == _fmt_pct_fraction(core_row["ml_wape_agg"])
    assert html_row["abs_error_reduction"] == _fmt_num(core_row["abs_error_reduction"])
    assert html_row["pct_of_history_volume"] == _fmt_pct_scaled(core_row["pct_of_history_volume"])
    assert html_row["scp_bias"] == _fmt_signed_pct_fraction(core_row["scp_bias_agg"])
    assert html_row["scp_direction"] == direction_label_es(core_row["scp_direction"])
