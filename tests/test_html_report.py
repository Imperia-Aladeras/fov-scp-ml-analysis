"""
Tests del informe HTML estatico y offline (Fase 5B): generacion, formato,
seguridad, navegacion, portabilidad, integracion con la publicacion
transaccional y --open-report. Usan tmp_path y datos sinteticos (via
tests.factories y CSV construidos en memoria); nunca los CSV reales de
data/.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

import analysis_fov_scp_ml as pipeline
from src import html_formatters as fmt
from src import html_view_models as vm
from src.html_report import extract_local_links, generate_html_report, validate_run_links
from src.periods import ALL_PERIODS, period_columns
from tests.factories import build_global_analysis_result, build_synthetic_client_result

# --------------------------------------------------------------------------
# Fixtures de CSV (independientes de data/): un unico generador parametrizado
# con el esquema completo requerido, reutilizado por todos los tests que
# necesitan pasar por el pipeline real (pipeline.main()).
# --------------------------------------------------------------------------

_HEADER_STATIC = {
    "ID": 1, "ID_BATCH": 63, "ID_RUN_STAGING": 60, "SOURCE_RUN_ID": 1, "ID_CONFIGURATION": 1,
    "RUN_START_DATE": "2026-01-01",
    "VALUE_LEVEL_2": None, "VALUE_LEVEL_3": None, "VALUE_LEVEL_4": None, "VALUE_LEVEL_5": None,
    "ML_STATUS": "OK", "SCP_STATUS": "OK",
    "HAS_SCP_CALCULATED": 1, "HAS_ML_CALCULATED": 1,
    "HAS_ML_EXCLUDED": 0, "ML_EXCLUSION_REASON": None, "SCP_NO_OUTPUT_REASON": None,
    "COPIED_AT": "2026-01-01",
}


def _build_client_row(
    id_client: int, *,
    ml_best_model: str = "AutoETS", scp_best_model: str = "x11 seasonal",
    value_level_1: str = "Cat", comparable: bool = True,
    history: float = 100.0, scp_err: float = 20.0, ml_err: float = 10.0, winner: str = "ML",
    id_configuration: int = 1, id_batch: int = 63, id_run_staging: int = 60, source_run_id: int = 1,
) -> dict:
    row = dict(_HEADER_STATIC)
    row.update({
        "ID": id_configuration, "ID_CLIENT": id_client, "ID_CONFIGURATION": id_configuration,
        "ID_BATCH": id_batch, "ID_RUN_STAGING": id_run_staging, "SOURCE_RUN_ID": source_run_id,
        "VALUE_LEVEL_1": value_level_1,
        "ML_BEST_MODEL": ml_best_model, "ML_CLASSIFICATION": "smooth", "ML_TYPE": "smooth_ok",
        "SCP_BEST_MODEL": scp_best_model, "SCP_CLASSIFICATION": "smooth",
        "SERIES_CLASSIFICATION": "smooth",
        "COMPARISON_STATUS": "COMPARABLE" if comparable else "NOT_COMPARABLE_NO_HISTORY",
        "HAS_BASE_CANDIDATE": 1,
    })
    for period in ALL_PERIODS:
        pcols = period_columns(period)
        n_months = 1 if period.startswith("M") else (3 if period in ("RECENT_3M", "OLDER_3M") else 6)
        if comparable:
            h = history * n_months
            se = scp_err * n_months
            me = ml_err * n_months
            scp_wape = se / h
            ml_wape = me / h
        else:
            h = se = me = 0.0
            scp_wape = ml_wape = None
        row[pcols.total_history] = h
        row[pcols.scp_total_forecast] = h + se
        row[pcols.ml_total_forecast] = h + me
        row[pcols.scp_total_signed_error] = se if comparable else None
        row[pcols.ml_total_signed_error] = me if comparable else None
        row[pcols.scp_total_abs_error] = se if comparable else None
        row[pcols.ml_total_abs_error] = me if comparable else None
        row[pcols.scp_total_squared_error] = (se ** 2) if comparable else None
        row[pcols.ml_total_squared_error] = (me ** 2) if comparable else None
        row[pcols.positive_history_month_count] = n_months if comparable else 0
        row[pcols.scp_mae] = (se / n_months) if comparable else None
        row[pcols.ml_mae] = (me / n_months) if comparable else None
        row[pcols.scp_rmse] = math.sqrt((se ** 2) / n_months) if comparable else None
        row[pcols.ml_rmse] = math.sqrt((me ** 2) / n_months) if comparable else None
        row[pcols.scp_wape] = scp_wape
        row[pcols.ml_wape] = ml_wape
        row[pcols.scp_bias] = (se / h) if comparable else None
        row[pcols.ml_bias] = (me / h) if comparable else None
        row[pcols.winner_method] = winner if comparable else None
        row[pcols.winner_model] = ml_best_model if comparable else None
        row[pcols.finalist_method] = "SCP" if comparable else None
        row[pcols.finalist_model] = scp_best_model if comparable else None
        row[pcols.winner_improvement_pct] = (
            (scp_wape - ml_wape) / scp_wape * 100 if comparable and scp_wape else None
        )
    return row


def _write_client_csv(path: Path, id_client: int, **kwargs) -> None:
    pd.DataFrame([_build_client_row(id_client, **kwargs)]).to_csv(path, index=False)


def _write_multi_client_csv(path: Path, specs: list[dict]) -> None:
    """
    Un unico CSV fisico con una fila por cada spec (particion por ID_CLIENT).
    Cada spec es un dict de kwargs para _build_client_row (debe incluir
    id_client); si no fija id_batch/id_run_staging/source_run_id, cada
    cliente recibe un scope de ejecucion distinto por defecto (indice en la
    lista), para no chocar con AMBIGUOUS_CLIENT_EXECUTION.
    """
    rows = []
    for i, spec in enumerate(specs):
        spec = dict(spec)
        spec.setdefault("id_configuration", i + 1)
        spec.setdefault("id_batch", 63 + i)
        spec.setdefault("id_run_staging", 60 + i)
        spec.setdefault("source_run_id", 1 + i)
        rows.append(_build_client_row(**spec))
    pd.DataFrame(rows).to_csv(path, index=False)


# --------------------------------------------------------------------------
# Generacion (extremo a extremo via pipeline.main)
# --------------------------------------------------------------------------

def test_pipeline_generates_global_index_and_client_pages(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_multi_client_csv(data_dir / "TA_FOV_SCP_ML_full_export.csv", [
        dict(id_client=10204, winner="ML", scp_err=20.0, ml_err=10.0),
        dict(id_client=10461, comparable=False),
    ])
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "gen_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "gen_run"

    assert (run_dir / "index.html").exists()
    assert (run_dir / "assets" / "styles.css").exists()
    # Fase 5: folder_name = {id_client}-{slug(display_name)} resuelto contra
    # el config/client-catalog.json real (10204 -> SKLUM, 10461 -> "García Millán").
    assert (run_dir / "clients" / "10204-sklum" / "index.html").exists()
    assert (run_dir / "clients" / "10461-garcía-millán" / "index.html").exists()

    problems = validate_run_links(run_dir)
    assert problems == []


def test_global_index_labels_client_count_not_csv_count_for_single_csv_multiple_clients(tmp_path: Path):
    """
    Fase 3 (cierre de inconsistencia): 1 CSV fisico particionado en 2
    clientes NUNCA debe mostrarse en el HTML global como "CSV descubiertos: 2"
    (ExecutionRecord/ClientAnalysisResult son por cliente, no por fichero
    fisico). La cabecera debe decir "Clientes procesados: 2".
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_multi_client_csv(data_dir / "TA_FOV_SCP_ML_full_export.csv", [
        dict(id_client=10204, winner="ML", scp_err=20.0, ml_err=10.0),
        dict(id_client=10461, comparable=False),
    ])
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "label_run",
    ])
    assert exit_code == 0
    global_html = (output_root / "label_run" / "index.html").read_text(encoding="utf-8")

    assert "CSV descubiertos" not in global_html
    assert "CSV descubiertos: 2" not in global_html
    assert "Clientes procesados</th><td>2</td>" in global_html


def test_execution_summary_and_html_header_count_only_real_clients_not_physical_records(tmp_path: Path):
    """
    Fase 3 (cierre de inconsistencia, segunda vuelta): no todo ExecutionRecord
    representa un cliente. Un CSV con read_error (o que nunca llego a
    parsearse) genera un ExecutionRecord fisico con id_client=None y
    estado=INPUT_NOT_ANALYZED; ese registro NO debe contar como "cliente
    procesado".

    Este escenario (1 CSV fisico con read_error, 0 ClientAnalysisResult) NO
    es alcanzable end-to-end via pipeline.main(): con el contrato de Fase 3
    (exactamente 1 CSV fisico), un read_error en ese unico fichero impide
    copiarlo/leerlo y la ejecucion completa falla ANTES de la fase
    EXECUTION_SUMMARY/HTML_REPORT (ver test_pipeline_runs.py::
    test_main_with_copy_inputs_fails_when_the_only_csv_has_read_error). Por
    eso se ejercitan aqui directamente las funciones que construyen el
    resumen y el HTML global, con el ExecutionRecord fisico ya construido.
    """
    from datetime import datetime

    from src.execution_summary import ExecutionRecord, INPUT_NOT_ANALYZED, build_execution_summary_markdown
    from src.global_analysis import analyze_global

    record = ExecutionRecord(
        archivo="TA_FOV_SCP_ML_full_export.csv", carpeta_salida="", id_client=None, etiqueta=None,
        display_name=None,
        id_batch=[], id_run_staging=[], filas=None, candidatas=None, comparables_6m=None,
        estado=INPUT_NOT_ANALYZED, warnings=None, errors=None, duracion_segundos=0.0,
        informe_generado=False, excel_generado=False, graficos_generados=0, log_generado=False,
        size_bytes=10, sha256=None, analysis_error="permiso denegado (simulado)",
    )

    markdown = build_execution_summary_markdown([record])
    assert "**Clientes procesados:** 0" in markdown

    run_config = pipeline.build_run_config(
        pipeline.build_arg_parser(tmp_path).parse_args([
            "--input-dir", str(tmp_path / "data"), "--output-root", str(tmp_path / "runs"), "--run-name", "readerr_only",
        ]),
        tmp_path,
    )
    now = datetime.now().astimezone()
    generate_html_report(
        run_config=run_config, results=[], global_result=analyze_global([]),
        all_outputs={}, global_outputs=[], execution_records=[record],
        started_at=now, finished_at=now, status="FAILED",
        git_commit=None, git_worktree_dirty=None,
    )
    global_html = (run_config.run_dir_temp / "index.html").read_text(encoding="utf-8")
    assert "Clientes procesados</th><td>0</td>" in global_html


def test_client_with_improvement_page_shows_positive_verdict(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Mejora.csv", 10204, winner="ML", scp_err=20.0, ml_err=10.0)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "improve_run",
    ])
    assert exit_code == 0
    html = (output_root / "improve_run" / "clients" / "10204-sklum" / "index.html").read_text(encoding="utf-8")
    assert "ML mejora el WAPE global ponderado" in html
    assert "+50.0%" in html


def test_client_with_deterioration_page_shows_negative_verdict(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10620_Peor.csv", 10620, winner="SCP", scp_err=10.0, ml_err=30.0)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "worse_run",
    ])
    assert exit_code == 0
    html = (output_root / "worse_run" / "clients" / "10620-frutas-bollo" / "index.html").read_text(encoding="utf-8")
    assert "ML no mejora el WAPE global ponderado" in html


def test_client_without_performance_shows_nd_not_zero(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10461_NoPerf.csv", 10461, comparable=False)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "noperf_run",
    ])
    assert exit_code == 0
    html = (output_root / "noperf_run" / "clients" / "10461-garcía-millán" / "index.html").read_text(encoding="utf-8")
    assert "Sin performance calculable" in html
    assert "WAPE, mejora y winner no están disponibles (N/D), no son cero" in html
    # nunca un WAPE/mejora fabricado en cero para este caso
    assert "<td>0.0%</td></tr>\n      <tr><th scope=\"row\">WAPE SCP" not in html


def test_structurally_broken_csv_fails_pipeline_without_generating_html(tmp_path: Path):
    """
    Con el contrato de Fase 3 (exactamente 1 CSV fisico, particionado por
    ID_CLIENT), un CSV fisicamente ilegible ya no es un "cliente invalido"
    aislado: load_client_sources_from_csv lanza StructuralInputError antes
    de CLIENT_PROCESSING, la ejecucion completa falla y no se genera ningun
    HTML de cliente ni de indice.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_99999_Invalido.csv").write_bytes(b"\xff\xfe not a csv")
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "invalid_run",
    ])
    assert exit_code == 1
    assert not (output_root / "invalid_run").exists()
    temp_dir = output_root / ".invalid_run.tmp"
    assert temp_dir.exists()
    assert not (temp_dir / "index.html").exists()
    assert not (temp_dir / "clients").exists() or not any((temp_dir / "clients").iterdir())

    import json
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["failure"]["error_type"] == "CSV_NOT_READABLE"


def test_html_included_in_outputs_generated_and_manifest(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "manifest_run",
    ])
    assert exit_code == 0
    import json
    manifest = json.loads((output_root / "manifest_run" / "manifest.json").read_text(encoding="utf-8"))
    outs = manifest["outputs_generated"]
    assert "index.html" in outs
    assert "clients/10204-sklum/index.html" in outs
    assert "assets/styles.css" in outs


# --------------------------------------------------------------------------
# Formato (formatters centralizados)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf")])
def test_formatters_never_render_missing_values_raw(value):
    assert fmt.fmt_pct_fraction(value) == "N/D"
    assert fmt.fmt_pct_scaled(value) == "N/D"
    assert fmt.fmt_signed_pct(value) == "N/D"
    assert fmt.fmt_num(value) == "N/D"
    assert fmt.fmt_int(value) == "N/D"
    for out in (fmt.fmt_pct_fraction(value), fmt.fmt_pct_scaled(value), fmt.fmt_signed_pct(value), fmt.fmt_num(value)):
        assert "nan" not in out.lower()
        assert "none" not in out.lower()
        assert "inf" not in out.lower()


def test_fmt_fraction_of_always_shows_numerator_and_denominator():
    assert fmt.fmt_fraction_of(6, 7, "clientes evaluables") == "6 de 7 clientes evaluables"
    assert fmt.fmt_fraction_of(None, 7) == "N/D"


def test_fmt_num_uses_es_es_thousands_and_decimal_separators():
    assert fmt.fmt_num(1234567, 0) == "1.234.567"
    assert fmt.fmt_num(1234.5, 1) == "1.234,5"


def test_encode_url_path_encodes_segments_not_separator():
    assert fmt.encode_url_path("clients/10 SKLUM & Co/index.html") == "clients/10%20SKLUM%20%26%20Co/index.html"


def test_to_posix_normalizes_windows_separators():
    assert fmt.to_posix("clients\\10204_SKLUM\\index.html") == "clients/10204_SKLUM/index.html"


def test_client_page_uses_exact_temporal_labels(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "labels_run",
    ])
    assert exit_code == 0
    html = (output_root / "labels_run" / "clients" / "10204-sklum" / "index.html").read_text(encoding="utf-8")
    assert "Semestre completo (M1–M6)" in html
    assert "Primer trimestre del semestre (M1–M3)" in html
    assert "Segundo trimestre del semestre (M4–M6)" in html
    for forbidden in (
        "trimestre reciente", "trimestre anterior", "trimestre más nuevo", "trimestre más antiguo",
        "m1-m6", "m1-m3", "m4-m6",
    ):
        assert forbidden not in html.lower()


def test_global_page_shows_numerator_and_denominator_for_clients_that_improve(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_multi_client_csv(data_dir / "TA_FOV_SCP_ML_full_export.csv", [
        dict(id_client=10204, winner="ML", scp_err=20.0, ml_err=10.0),
        dict(id_client=10461, comparable=False),
    ])
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "fraction_run",
    ])
    assert exit_code == 0
    html = (output_root / "fraction_run" / "index.html").read_text(encoding="utf-8")
    assert "1 de 1 clientes evaluables" in html
    assert "no disponen de performance calculable" in html


# --------------------------------------------------------------------------
# Seguridad
# --------------------------------------------------------------------------

def test_malicious_model_name_is_escaped_not_executed(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(
        data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204,
        ml_best_model='<script>alert("x")</script>',
    )
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "xss_run",
    ])
    assert exit_code == 0
    html = (output_root / "xss_run" / "clients" / "10204-sklum" / "index.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in html or "&lt;script&gt;alert" in html


def test_ampersand_in_client_label_is_escaped_in_text_and_links(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_R&D.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "amp_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "amp_run"
    assert (run_dir / "clients" / "10204-sklum" / "index.html").exists()
    global_html = (run_dir / "index.html").read_text(encoding="utf-8")
    assert "10204_R&amp;D" in global_html
    assert "10204_R&D<" not in global_html  # nunca sin escapar seguido de una etiqueta
    problems = validate_run_links(run_dir)
    assert problems == []


def test_no_forbidden_link_schemes_anywhere_in_generated_html(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "scheme_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "scheme_run"
    for html_path in run_dir.rglob("*.html"):
        text = html_path.read_text(encoding="utf-8")
        for link in extract_local_links(text):
            lowered = link.lower()
            assert not lowered.startswith("javascript:")
            assert not lowered.startswith("data:")
            assert not lowered.startswith("http://")
            assert not lowered.startswith("https://")
            assert not lowered.startswith("//")
            assert "file:///" not in lowered
            assert ":\\" not in link  # ninguna ruta absoluta de Windows


def test_extract_local_links_ignores_pure_anchors():
    html = '<a href="#seccion">x</a><a href="clients/a/index.html">y</a>'
    assert extract_local_links(html) == ["clients/a/index.html"]


def test_validate_run_links_detects_broken_link(tmp_path: Path):
    (tmp_path / "index.html").write_text('<a href="clients/nope/index.html">x</a>', encoding="utf-8")
    problems = validate_run_links(tmp_path)
    assert len(problems) == 1
    assert "destino inexistente" in problems[0]


def test_validate_run_links_detects_escape_outside_run_dir(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (tmp_path / "outside.html").write_text("fuera", encoding="utf-8")
    (run_dir / "index.html").write_text('<a href="../outside.html">x</a>', encoding="utf-8")
    problems = validate_run_links(run_dir)
    assert len(problems) == 1
    assert "escapa" in problems[0]


def test_validate_run_links_rejects_external_scheme(tmp_path: Path):
    (tmp_path / "index.html").write_text('<a href="https://example.com">x</a>', encoding="utf-8")
    problems = validate_run_links(tmp_path)
    assert len(problems) == 1
    assert "externo" in problems[0]


# --------------------------------------------------------------------------
# Navegacion
# --------------------------------------------------------------------------

def test_prev_next_navigation_between_clients(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_multi_client_csv(data_dir / "TA_FOV_SCP_ML_full_export.csv", [
        dict(id_client=10204), dict(id_client=10461), dict(id_client=10620),
    ])
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "navrun",
    ])
    assert exit_code == 0
    run_dir = output_root / "navrun"

    # Fase 5: folder_name = {id_client}-{slug(display_name)} resuelto contra
    # el config/client-catalog.json real (10204 -> SKLUM, 10461 -> "García Millán", 10620 -> "Frutas Bollo").
    beta_html = (run_dir / "clients" / "10461-garcía-millán" / "index.html").read_text(encoding="utf-8")
    assert "../10204-sklum/index.html" in beta_html
    assert "../10620-frutas-bollo/index.html" in beta_html
    # El texto visible del enlace debe llevar display_name (ID_CLIENT): el
    # catalogo no garantiza nombres unicos entre ID_CLIENT distintos.
    assert "SKLUM (10204)" in beta_html
    assert "Frutas Bollo (10620)" in beta_html

    alfa_html = (run_dir / "clients" / "10204-sklum" / "index.html").read_text(encoding="utf-8")
    assert "<span></span>" in alfa_html  # sin cliente anterior: no se inventa un enlace

    gamma_html = (run_dir / "clients" / "10620-frutas-bollo" / "index.html").read_text(encoding="utf-8")
    # el nombre acentuado va percent-encoded en el href (fmt.encode_url_path),
    # aunque el nombre de carpeta en disco conserve el acento sin codificar.
    assert fmt.encode_url_path("../10461-garcía-millán/index.html") in gamma_html
    assert "García Millán (10461)" in gamma_html


def test_client_page_links_to_own_excel_markdown_log_and_they_exist(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "fileslink_run",
    ])
    assert exit_code == 0
    client_dir = output_root / "fileslink_run" / "clients" / "10204-sklum"
    html = (client_dir / "index.html").read_text(encoding="utf-8")
    assert "fov_scp_ml_summary_10204-sklum.xlsx" in html
    assert (client_dir / "fov_scp_ml_summary_10204-sklum.xlsx").exists()
    assert "fov_scp_ml_report_10204-sklum.md" in html
    assert (client_dir / "fov_scp_ml_report_10204-sklum.md").exists()
    assert "processing_log_10204-sklum.txt" in html
    assert (client_dir / "processing_log_10204-sklum.txt").exists()


def test_global_page_links_to_client_and_back(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "backlink_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "backlink_run"
    global_html = (run_dir / "index.html").read_text(encoding="utf-8")
    assert "clients/10204-sklum/index.html" in global_html
    client_html = (run_dir / "clients" / "10204-sklum" / "index.html").read_text(encoding="utf-8")
    assert "../../index.html" in client_html


# --------------------------------------------------------------------------
# Portabilidad
# --------------------------------------------------------------------------

def test_run_copy_moved_to_another_location_keeps_all_links_valid(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_multi_client_csv(data_dir / "TA_FOV_SCP_ML_full_export.csv", [
        dict(id_client=10204), dict(id_client=10461, comparable=False),
    ])
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "portable_run",
    ])
    assert exit_code == 0
    original = output_root / "portable_run"

    moved_root = tmp_path / "moved elsewhere ñ"
    moved_root.mkdir()
    moved = moved_root / "portable_run_copy"
    shutil.copytree(original, moved)

    problems = validate_run_links(moved)
    assert problems == []

    moved_html = (moved / "index.html").read_text(encoding="utf-8")
    assert str(tmp_path) not in moved_html
    assert str(original) not in moved_html
    assert "C:\\" not in moved_html


def test_run_with_spaces_and_accents_in_path_generates_valid_html(tmp_path: Path):
    weird_root = tmp_path / "Carpeta con espacios y ñ"
    data_dir = weird_root / "data"
    data_dir.mkdir(parents=True)
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = weird_root / "outputs" / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "acentos_html_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "acentos_html_run"
    assert (run_dir / "index.html").exists()
    assert validate_run_links(run_dir) == []


# --------------------------------------------------------------------------
# Publicacion
# --------------------------------------------------------------------------

def test_html_generation_failure_prevents_publication(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    def failing_generate_html_report(**kwargs):
        raise RuntimeError("fallo simulado generando el informe HTML")

    monkeypatch.setattr(pipeline, "generate_html_report", failing_generate_html_report)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "htmlfail_run",
    ])
    assert exit_code == 1
    assert not (output_root / "htmlfail_run").exists()
    temp_dir = output_root / ".htmlfail_run.tmp"
    assert temp_dir.exists()

    import json
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["failure"]["phase"] == "HTML_REPORT"


def test_html_link_validation_failure_prevents_publication(tmp_path: Path, monkeypatch):
    """
    validate_run_links() se invoca desde analysis_fov_scp_ml.py DESPUES de
    escribir manifest.json (fase HTML_LINK_VALIDATION): parcheamos la
    referencia importada en el propio modulo pipeline, no en src.html_report,
    porque `from src.html_report import validate_run_links` ya vincula el
    nombre en el namespace de analysis_fov_scp_ml.py en tiempo de import.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    monkeypatch.setattr(pipeline, "validate_run_links", lambda run_dir: ["problema simulado"])

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "linkfail_run",
    ])
    assert exit_code == 1
    assert not (output_root / "linkfail_run").exists()
    temp_dir = output_root / ".linkfail_run.tmp"
    assert (temp_dir / "index.html").exists()
    # manifest.json SI se llego a escribir (la fase MANIFEST completo antes
    # de la validacion de enlaces); el fallo posterior lo deja en FAILED.
    import json
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["failure"]["phase"] == "HTML_LINK_VALIDATION"


def test_published_run_contains_index_and_assets_and_publish_complete(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "publishok_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "publishok_run"
    assert (run_dir / ".publish_complete").exists()
    assert (run_dir / "index.html").exists()
    assert (run_dir / "assets" / "styles.css").exists()


def test_index_html_links_to_manifest_json(tmp_path: Path):
    """
    index.html se genera antes de que manifest.json exista en disco (fase
    HTML_REPORT, antes de MANIFEST). El enlace a manifest.json debe
    aparecer igualmente en el HTML publicado, y debe apuntar a un fichero
    que realmente existe en la ejecucion final.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "manifestlink_run",
    ])
    assert exit_code == 0
    run_dir = output_root / "manifestlink_run"
    html = (run_dir / "index.html").read_text(encoding="utf-8")
    assert 'href="manifest.json"' in html
    assert (run_dir / "manifest.json").exists()
    assert validate_run_links(run_dir) == []


def test_manifest_link_target_exists_before_publish_run_is_called(tmp_path: Path, monkeypatch):
    """
    La secuencia exigida es: generar HTML -> outputs_generated -> escribir
    manifest.json -> validar enlaces -> publicar. Se comprueba interceptando
    publish_run(): en el momento en que se llama, manifest.json ya debe
    existir en el directorio TEMPORAL y el enlace desde index.html ya debe
    resolver correctamente (la validacion de enlaces ya tuvo que pasar).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    calls = []
    real_publish_run = pipeline.publish_run

    def spying_publish_run(run_config):
        temp_dir = run_config.run_dir_temp
        assert (temp_dir / "manifest.json").exists()
        assert 'href="manifest.json"' in (temp_dir / "index.html").read_text(encoding="utf-8")
        assert validate_run_links(temp_dir) == []
        calls.append(True)
        return real_publish_run(run_config)

    monkeypatch.setattr(pipeline, "publish_run", spying_publish_run)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "prepublish_run",
    ])
    assert exit_code == 0
    assert calls == [True]


def test_manifest_link_still_works_after_moving_a_copy_of_the_run(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "manifestmove_run",
    ])
    assert exit_code == 0
    original = output_root / "manifestmove_run"

    moved_root = tmp_path / "otro lugar"
    moved_root.mkdir()
    moved = moved_root / "manifestmove_run_copy"
    shutil.copytree(original, moved)

    assert validate_run_links(moved) == []
    moved_html = (moved / "index.html").read_text(encoding="utf-8")
    assert 'href="manifest.json"' in moved_html
    assert (moved / "manifest.json").exists()


def test_failed_link_validation_still_prevents_publication_when_manifest_link_broken(tmp_path: Path, monkeypatch):
    """Variante centrada en el enlace a manifest.json: si se rompe deliberadamente, la ejecucion no se publica."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    import src.manifest as manifest_module
    real_write_manifest = manifest_module.write_manifest

    def write_manifest_without_creating_file(manifest, path):
        # simula un manifest.json que nunca llega a escribirse en disco,
        # aunque el resto de la fase MANIFEST continue con normalidad
        return None

    monkeypatch.setattr(pipeline, "write_manifest", write_manifest_without_creating_file)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "brokenmanifest_run",
    ])
    assert exit_code == 1
    assert not (output_root / "brokenmanifest_run").exists()
    temp_dir = output_root / ".brokenmanifest_run.tmp"
    assert temp_dir.exists()
    assert not (temp_dir / "manifest.json").exists()
    log_text = (temp_dir / "execution.log").read_text(encoding="utf-8")
    assert "manifest.json" in log_text


# --------------------------------------------------------------------------
# --open-report
# --------------------------------------------------------------------------

def test_open_report_not_called_by_default(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    calls = []
    monkeypatch.setattr(pipeline.webbrowser, "open", lambda uri: calls.append(uri) or True)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "nodefault_run",
    ])
    assert exit_code == 0
    assert calls == []


def test_open_report_called_with_final_index_html_after_publish_complete(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    calls = []

    def fake_open(uri):
        calls.append(uri)
        # en el momento de la llamada, la publicacion ya debe estar completa
        run_dir = output_root / "openreport_run"
        assert (run_dir / ".publish_complete").exists()
        return True

    monkeypatch.setattr(pipeline.webbrowser, "open", fake_open)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "openreport_run",
        "--open-report",
    ])
    assert exit_code == 0
    assert len(calls) == 1
    final_index = (output_root / "openreport_run" / "index.html").resolve()
    assert calls[0] == final_index.as_uri()
    assert ".tmp" not in calls[0]


def test_open_report_browser_exception_does_not_invalidate_run(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    def raising_open(uri):
        raise RuntimeError("no hay navegador disponible (simulado)")

    monkeypatch.setattr(pipeline.webbrowser, "open", raising_open)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "openexc_run",
        "--open-report",
    ])
    assert exit_code == 0
    run_dir = output_root / "openexc_run"
    assert (run_dir / ".publish_complete").exists()
    import json
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] != "FAILED"
    assert manifest["published"] is True


def test_open_report_false_return_does_not_invalidate_run(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    monkeypatch.setattr(pipeline.webbrowser, "open", lambda uri: False)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "openfalse_run",
        "--open-report",
    ])
    assert exit_code == 0
    run_dir = output_root / "openfalse_run"
    assert (run_dir / ".publish_complete").exists()
    import json
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["published"] is True


def test_open_report_recorded_in_run_config_json(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    monkeypatch.setattr(pipeline.webbrowser, "open", lambda uri: True)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "cfgflag_run",
        "--open-report",
    ])
    assert exit_code == 0
    import json
    run_config = json.loads((output_root / "cfgflag_run" / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["open_report"] is True


# --------------------------------------------------------------------------
# View models (unidad, sin pasar por el pipeline completo)
# --------------------------------------------------------------------------

def test_build_client_row_vm_flags_client_without_performance():
    result = build_synthetic_client_result(with_data=False)
    row = vm.build_client_row_vm(result)
    assert row["status_flag"] == "sin_performance"
    assert row["wape_scp"] == "N/D"
    assert row["wape_ml"] == "N/D"
    assert row["mejora"] == "N/D"


def test_build_client_row_vm_flags_evaluable_client():
    result = build_synthetic_client_result(with_data=True)
    row = vm.build_client_row_vm(result)
    assert row["status_flag"] in ("evaluable", "con_warnings", "con_errores")
    assert row["wape_scp"] != "N/D"


def test_build_executive_summary_vm_matches_numerator_denominator_wording():
    global_result = build_global_analysis_result()
    summary = vm.build_executive_summary_vm(global_result)
    assert "de" in summary["clientes_mejoran_fraction"]
    assert summary["n_clients_missing_performance"] != "0"


def test_build_inventory_row_vm_never_invents_client_link_for_unanalyzed_csv():
    from src.execution_summary import ExecutionRecord, INPUT_NOT_ANALYZED

    record = ExecutionRecord(
        archivo="TA_FOV_SCP_ML_00000_Roto.csv", carpeta_salida="", id_client=None, etiqueta=None,
        display_name=None,
        id_batch=[], id_run_staging=[], filas=None, candidatas=None, comparables_6m=None,
        estado=INPUT_NOT_ANALYZED, warnings=None, errors=None, duracion_segundos=0.0,
        informe_generado=False, excel_generado=False, graficos_generados=0, log_generado=False,
        size_bytes=10, sha256="abc", analysis_error="no se pudo leer",
    )
    row = vm.build_inventory_row_vm(record)
    assert row["has_client_page"] is False
    assert row["folder_name"] is None
