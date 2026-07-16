"""
Tests de orquestacion de extremo a extremo (Fase 5A): CLI -> RunConfig ->
run_pipeline -> publicacion. Usan tmp_path y datos sinteticos; nunca los CSV
reales de data/.
"""

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pytest

import analysis_fov_scp_ml as pipeline
from src.periods import ALL_PERIODS, period_columns

SIMPLE_HEADER = "ID,ID_BATCH,ID_RUN_STAGING,ID_CLIENT,SOURCE_RUN_ID,ID_CONFIGURATION,VALUE_LEVEL_1"


def _write_invalid_csv(path: Path, id_client: int) -> None:
    """CSV parseable pero sin el esquema completo: queda ERROR (columnas obligatorias faltantes)."""
    path.write_text(SIMPLE_HEADER + "\n" + f"1,63,63,{id_client},1,23,LABEL\n", encoding="utf-8")


def _write_full_valid_csv(path: Path, id_client: int) -> None:
    """
    CSV con el esquema completo (todas las columnas de periods.all_required_columns()),
    una unica fila comparable en todos los periodos, con agregados consistentes
    (RECENT_3M/OLDER_3M = 3 meses, 6M = 6 meses) para no disparar warnings de
    coherencia agregada.
    """
    month_history, month_scp_err, month_ml_err = 100.0, 20.0, 10.0
    row = {
        "ID": 1, "ID_BATCH": 63, "ID_RUN_STAGING": 60, "ID_CLIENT": id_client, "SOURCE_RUN_ID": 1,
        "ID_CONFIGURATION": 1,
        "VALUE_LEVEL_1": "Cat", "VALUE_LEVEL_2": None, "VALUE_LEVEL_3": None,
        "VALUE_LEVEL_4": None, "VALUE_LEVEL_5": None,
        "ML_BEST_MODEL": "AutoETS", "ML_CLASSIFICATION": "smooth", "ML_TYPE": "smooth_ok", "ML_STATUS": "OK",
        "SCP_BEST_MODEL": "x11 seasonal", "SCP_CLASSIFICATION": "smooth", "SCP_STATUS": "OK",
        "SERIES_CLASSIFICATION": "smooth",
        "COMPARISON_STATUS": "COMPARABLE",
        "HAS_BASE_CANDIDATE": 1, "HAS_SCP_CALCULATED": 1, "HAS_ML_CALCULATED": 1,
        "HAS_ML_EXCLUDED": 0, "ML_EXCLUSION_REASON": None, "SCP_NO_OUTPUT_REASON": None,
        "COPIED_AT": "2026-01-01",
    }
    for period in ALL_PERIODS:
        pcols = period_columns(period)
        n_months = 1 if period.startswith("M") else (3 if period in ("RECENT_3M", "OLDER_3M") else 6)
        history = month_history * n_months
        scp_err = month_scp_err * n_months
        ml_err = month_ml_err * n_months
        scp_wape = scp_err / history
        ml_wape = ml_err / history
        row[pcols.total_history] = history
        row[pcols.scp_total_forecast] = history + scp_err
        row[pcols.ml_total_forecast] = history + ml_err
        row[pcols.scp_total_signed_error] = scp_err
        row[pcols.ml_total_signed_error] = ml_err
        row[pcols.scp_total_abs_error] = scp_err
        row[pcols.ml_total_abs_error] = ml_err
        row[pcols.scp_total_squared_error] = scp_err ** 2
        row[pcols.ml_total_squared_error] = ml_err ** 2
        row[pcols.positive_history_month_count] = n_months
        # MAE = TOTAL_ABS_ERROR / POSITIVE_HISTORY_MONTH_COUNT
        # RMSE = SQRT(TOTAL_SQUARED_ERROR / POSITIVE_HISTORY_MONTH_COUNT)
        # BIAS = TOTAL_SIGNED_ERROR / TOTAL_HISTORY
        # (formulas de src/quality_checks.py: deben coincidir exactamente para
        # no disparar *_RECONSTRUCTION_MISMATCH en un fixture que se quiere limpio)
        row[pcols.scp_mae] = scp_err / n_months
        row[pcols.ml_mae] = ml_err / n_months
        row[pcols.scp_rmse] = math.sqrt((scp_err ** 2) / n_months)
        row[pcols.ml_rmse] = math.sqrt((ml_err ** 2) / n_months)
        row[pcols.scp_wape] = scp_wape
        row[pcols.ml_wape] = ml_wape
        row[pcols.scp_bias] = scp_err / history
        row[pcols.ml_bias] = ml_err / history
        row[pcols.winner_method] = "ML"
        row[pcols.winner_model] = "AutoETS"
        row[pcols.finalist_method] = "SCP"
        row[pcols.finalist_model] = "x11 seasonal"
        row[pcols.winner_improvement_pct] = (scp_wape - ml_wape) / scp_wape * 100
    pd.DataFrame([row]).to_csv(path, index=False)


def test_main_with_zero_csv_returns_1_and_does_not_publish(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "empty_run",
    ])

    assert exit_code == 1
    assert not (output_root / "empty_run").exists()
    temp_dir = output_root / ".empty_run.tmp"
    assert temp_dir.exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["failure"]["phase"] == "INVENTORY"
    assert manifest["published"] is False
    assert manifest["output_dir_working"] == str(temp_dir)
    assert manifest["output_dir_final"] == str(output_root / "empty_run")


def test_main_creates_run_structure_and_never_touches_legacy_outputs(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_full_valid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    (data_dir / "TA_FOV_SCP_ML_99999_Broken.csv").write_bytes(b"\xff\xfe not a csv")
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "mixed_run",
    ])

    assert exit_code == 0
    run_dir = output_root / "mixed_run"
    assert run_dir.exists()
    assert not (output_root / ".mixed_run.tmp").exists()

    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "run_config.json").exists()
    assert (run_dir / "execution.log").exists()
    assert (run_dir / "execution_summary.md").exists()
    assert (run_dir / "execution_summary.xlsx").exists()
    assert (run_dir / "global" / "fov_scp_ml_global_summary.xlsx").exists()
    assert (run_dir / "global" / "fov_scp_ml_global_report.md").exists()

    valid_client_dir = run_dir / "clients" / "10204_SKLUM"
    assert (valid_client_dir / "fov_scp_ml_summary_10204_SKLUM.xlsx").exists()
    assert (valid_client_dir / "fov_scp_ml_report_10204_SKLUM.md").exists()
    assert (valid_client_dir / "processing_log_10204_SKLUM.txt").exists()

    broken_client_dir = run_dir / "clients" / "99999_Broken"
    assert (broken_client_dir / "processing_log_99999_Broken.txt").exists()
    assert not (broken_client_dir / "fov_scp_ml_summary_99999_Broken.xlsx").exists()

    # nunca en las rutas legacy
    assert not (tmp_path / "outputs" / "10204_SKLUM").exists()
    assert not (tmp_path / "outputs" / "global").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "SUCCESS_WITH_WARNINGS"
    assert manifest["n_csv_discovered"] == 2
    assert manifest["n_clients_valid"] == 1
    assert manifest["published"] is True
    assert manifest["output_dir_working"] is None
    assert manifest["output_dir_final"] == str(run_dir)
    csv_by_name = {e["name"]: e for e in manifest["csv_files"]}
    assert csv_by_name["TA_FOV_SCP_ML_10204_SKLUM.csv"]["sha256"] is not None
    assert csv_by_name["TA_FOV_SCP_ML_10204_SKLUM.csv"]["id_client"] == 10204
    assert csv_by_name["TA_FOV_SCP_ML_10204_SKLUM.csv"]["analyzed_source"] == "original"
    assert csv_by_name["TA_FOV_SCP_ML_99999_Broken.csv"]["sha256"] is not None
    assert csv_by_name["TA_FOV_SCP_ML_99999_Broken.csv"]["id_client"] is None

    run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["run_name_effective"] == "mixed_run"


def test_main_fails_with_exit_code_2_on_collision_without_overwrite(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    first = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "dup_run"])
    assert first == 0

    second = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "dup_run"])
    assert second == 2
    # la primera ejecucion no se toca
    assert (output_root / "dup_run" / "manifest.json").exists()


def test_main_succeeds_with_overwrite_after_collision(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    first = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "dup_run"])
    assert first == 0

    second = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "dup_run", "--overwrite",
    ])
    assert second == 0
    assert (output_root / "dup_run").exists()
    assert not (output_root / ".dup_run.tmp").exists()
    assert not (output_root / ".dup_run.backup").exists()


def test_main_fails_with_exit_code_2_when_orphan_temp_exists_without_overwrite(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"
    orphan_temp = output_root / ".orphan_run.tmp"
    orphan_temp.mkdir(parents=True)
    (orphan_temp / "marker.txt").write_text("from an interrupted run", encoding="utf-8")

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "orphan_run",
    ])
    assert exit_code == 2
    # el temporal huerfano NO se elimina silenciosamente
    assert (orphan_temp / "marker.txt").exists()


def test_main_removes_orphan_temp_explicitly_with_overwrite(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"
    orphan_temp = output_root / ".orphan_run.tmp"
    orphan_temp.mkdir(parents=True)
    (orphan_temp / "marker.txt").write_text("from an interrupted run", encoding="utf-8")

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "orphan_run", "--overwrite",
    ])
    assert exit_code == 0
    assert (output_root / "orphan_run").exists()
    assert not orphan_temp.exists()


def test_main_rejects_run_name_with_path_traversal_with_exit_code_2(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "../escape",
    ])
    assert exit_code == 2
    assert not output_root.exists()


def test_main_rejects_missing_input_dir_with_exit_code_2(tmp_path: Path):
    output_root = tmp_path / "runs"
    exit_code = pipeline.main([
        "--input-dir", str(tmp_path / "no_existe"), "--output-root", str(output_root), "--run-name", "whatever",
    ])
    assert exit_code == 2


def test_main_with_copy_inputs_copies_original_csv_bytes(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_invalid_csv(csv_path, id_client=10204)
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "with_inputs", "--copy-inputs",
    ])
    assert exit_code == 0
    run_dir = output_root / "with_inputs"
    copied = run_dir / "inputs" / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    assert copied.exists()
    original_bytes = csv_path.read_bytes()
    assert copied.read_bytes() == original_bytes

    # el manifest registra que la fuente analizada fue la copia archivada, y su
    # hash coincide exactamente con los bytes de esa copia (los bytes usados por el analisis)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["csv_files"][0]
    assert entry["analyzed_source"] == "copy"
    assert entry["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert entry["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()


def test_main_without_copy_inputs_does_not_create_inputs_dir(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "no_inputs",
    ])
    assert exit_code == 0
    assert not (output_root / "no_inputs" / "inputs").exists()


def test_main_runs_on_paths_with_spaces_and_accents(tmp_path: Path):
    weird_dir = tmp_path / "Carpeta con espacios y ñ"
    data_dir = weird_dir / "data"
    data_dir.mkdir(parents=True)
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = weird_dir / "outputs" / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "acentos_run",
    ])
    assert exit_code == 0
    assert (output_root / "acentos_run" / "clients" / "10204_SKLUM").exists()


def test_default_command_with_no_args_uses_repo_data_and_creates_timestamped_run(tmp_path: Path, monkeypatch):
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "data").mkdir(parents=True)
    _write_invalid_csv(fake_repo / "data" / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    monkeypatch.setattr(pipeline, "BASE_DIR", fake_repo)

    exit_code = pipeline.main([])
    assert exit_code == 0
    output_root = fake_repo / "outputs" / "runs"
    # output_root tambien contiene, desde la Fase 5C, el catalogo historico
    # (index.html, run_index.log, catalog_assets/) generado automaticamente
    # tras la publicacion: se filtran los directorios de run (excluyendo
    # catalog_assets/, que es propio del catalogo, no un run).
    run_dirs = [p for p in output_root.iterdir() if p.is_dir() and p.name != "catalog_assets"]
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "clients" / "10204_SKLUM").exists()
    assert (output_root / "index.html").exists()
    assert (output_root / "run_index.log").exists()


# --------------------------------------------------------------------------
# Correccion Fase 5A (punto 2): inputs modificados durante la ejecucion.
# --------------------------------------------------------------------------

def test_main_fails_when_input_csv_changes_during_run_without_copy_inputs(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_invalid_csv(csv_path, id_client=10204)
    output_root = tmp_path / "runs"

    from src.client_analysis import analyze_client as real_analyze_client

    def tampering_analyze_client(source):
        result = real_analyze_client(source)
        # simula que el CSV de origen se sobrescribe a mitad de la ejecucion
        csv_path.write_text(SIMPLE_HEADER + "\n" + "1,63,63,99999,1,23,TAMPERED\n", encoding="utf-8")
        return result

    monkeypatch.setattr(pipeline, "analyze_client", tampering_analyze_client)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "tampered_run",
    ])

    assert exit_code == 1
    assert not (output_root / "tampered_run").exists()
    temp_dir = output_root / ".tampered_run.tmp"
    assert temp_dir.exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["output_dir_working"] == str(temp_dir)
    assert manifest["failure"]["phase"] == "VERIFY_INPUTS_UNCHANGED"
    assert manifest["failure"]["error_type"] == "INPUT_CHANGED_DURING_RUN"
    assert "TA_FOV_SCP_ML_10204_SKLUM.csv" in manifest["failure"]["error_message"]


def test_main_fails_when_copy_does_not_match_original(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_invalid_csv(csv_path, id_client=10204)
    output_root = tmp_path / "runs"

    def corrupting_copy2(src, dst):
        Path(dst).write_bytes(b"CORRUPTED DURING COPY")

    monkeypatch.setattr(pipeline.shutil, "copy2", corrupting_copy2)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "corrupt_copy",
        "--copy-inputs",
    ])

    assert exit_code == 1
    assert not (output_root / "corrupt_copy").exists()
    temp_dir = output_root / ".corrupt_copy.tmp"
    assert temp_dir.exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["failure"]["phase"] == "COPY_INPUTS"
    assert manifest["failure"]["error_type"] == "INPUT_COPY_MISMATCH"


# --------------------------------------------------------------------------
# Correccion Fase 5A (punto 4): control de fallos durante la preparacion
# del directorio de ejecucion (setup).
# --------------------------------------------------------------------------

def test_prepare_run_directories_propagates_filesystem_failure(tmp_path: Path, monkeypatch):
    parser_cfg = pipeline.build_run_config(
        pipeline.build_arg_parser(tmp_path).parse_args([
            "--input-dir", str(tmp_path / "data"), "--output-root", str(tmp_path / "runs"), "--run-name", "run1",
        ]),
        tmp_path,
    )
    original_write_text = Path.write_text

    def failing_write_text(self, *a, **k):
        if self.name == "run_config.json":
            raise OSError("disco lleno (simulado)")
        return original_write_text(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    with pytest.raises(OSError):
        pipeline._prepare_run_directories(parser_cfg)


def test_main_handles_setup_failure_when_preparing_directories(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    def raiser(run_config):
        # simula que el temporal SI llego a crearse parcialmente antes del fallo
        run_config.clients_dir.mkdir(parents=True, exist_ok=True)
        raise OSError("fallo simulado creando subdirectorios")

    monkeypatch.setattr(pipeline, "_prepare_run_directories", raiser)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "setup_fail",
    ])
    assert exit_code == 1
    temp_dir = output_root / ".setup_fail.tmp"
    assert temp_dir.exists()
    assert not (output_root / "setup_fail").exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["failure"]["phase"] == "PREPARE_DIRECTORIES"
    assert (temp_dir / "execution.log").exists()
    log_text = (temp_dir / "execution.log").read_text(encoding="utf-8")
    assert "Traceback" in log_text


def test_main_handles_setup_failure_when_writing_run_config_json(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    original_write_text = Path.write_text

    def failing_write_text(self, *a, **k):
        if self.name == "run_config.json":
            raise OSError("fallo simulado escribiendo run_config.json")
        return original_write_text(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "cfg_fail",
    ])
    assert exit_code == 1
    temp_dir = output_root / ".cfg_fail.tmp"
    assert temp_dir.exists()
    assert not (output_root / "cfg_fail").exists()
    # el manifest tambien usa write_text: se documenta el fallo con el mecanismo best-effort disponible
    manifest_path = temp_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "FAILED"
        assert manifest["failure"]["phase"] == "PREPARE_DIRECTORIES"


def test_main_handles_setup_failure_when_removing_orphan_temp_with_overwrite(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"
    orphan_temp = output_root / ".dup_run.tmp"
    orphan_temp.mkdir(parents=True)
    (orphan_temp / "marker.txt").write_text("orphan", encoding="utf-8")

    def failing_rmtree(path, *a, **k):
        raise OSError("fallo simulado eliminando temporal")

    monkeypatch.setattr(pipeline.shutil, "rmtree", failing_rmtree)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "dup_run", "--overwrite",
    ])
    assert exit_code == 1
    assert orphan_temp.exists()  # no se elimino (fallo simulado): se conserva integro
    assert (orphan_temp / "marker.txt").exists()
    manifest = json.loads((orphan_temp / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["failure"]["phase"] == "REMOVE_ORPHAN_TEMP"


def test_main_handles_setup_failure_when_reconciling_orphan_backup(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    def raiser(run_config):
        raise OSError("fallo simulado reconciliando backup")

    monkeypatch.setattr(pipeline, "reconcile_interrupted_publication", raiser)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "backup_fail",
    ])
    # el fallo ocurre antes de crear el temporal: no hay nada donde escribir
    # manifest/log, pero main() no debe propagar una excepcion sin controlar
    assert exit_code == 1
    assert not (output_root / "backup_fail").exists()


# --------------------------------------------------------------------------
# Correccion (punto 1): finalizacion transaccional de la publicacion, a
# nivel de orquestacion completa (main()). Nunca debe devolverse exit code 0
# cuando la finalizacion (manifest/log tras el rename) queda incompleta.
# --------------------------------------------------------------------------

def test_main_returns_1_and_repairs_manifest_when_manifest_patch_fails_after_rename(tmp_path: Path, monkeypatch):
    import src.run_publish as run_publish_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    def failing_patch(run_config):
        raise OSError("fallo simulado escribiendo manifest.json")

    monkeypatch.setattr(run_publish_module, "_patch_manifest_published", failing_patch)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "finalize_fail",
    ])

    assert exit_code == 1
    assert not (output_root / "finalize_fail").exists()
    temp_dir = output_root / ".finalize_fail.tmp"
    assert temp_dir.exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["output_dir_working"] == str(temp_dir)
    assert manifest["failure"]["phase"] == "PUBLISH"


def test_main_returns_1_and_repairs_manifest_when_final_log_append_fails(tmp_path: Path, monkeypatch):
    """
    El patch de manifest.json (published=true) tiene exito antes de que
    falle el registro final del log: la publicacion se deshace igualmente, y
    el manejador de main() corrige el manifest de vuelta a published=false.
    """
    import src.run_publish as run_publish_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    def failing_log(run_config):
        raise OSError("fallo simulado escribiendo execution.log")

    monkeypatch.setattr(run_publish_module, "_append_final_publish_log_line", failing_log)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "logfail",
    ])

    assert exit_code == 1
    assert not (output_root / "logfail").exists()
    temp_dir = output_root / ".logfail.tmp"
    assert temp_dir.exists()
    manifest = json.loads((temp_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["published"] is False
    assert manifest["output_dir_working"] == str(temp_dir)


def test_main_restores_previous_run_when_publish_finalization_fails_with_overwrite(tmp_path: Path, monkeypatch):
    import src.run_publish as run_publish_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_invalid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    output_root = tmp_path / "runs"

    first = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "restore_test",
    ])
    assert first == 0
    first_manifest = json.loads((output_root / "restore_test" / "manifest.json").read_text(encoding="utf-8"))

    def failing_patch(run_config):
        raise OSError("fallo simulado")

    monkeypatch.setattr(run_publish_module, "_patch_manifest_published", failing_patch)

    second = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "restore_test", "--overwrite",
    ])
    assert second == 1
    # la ejecucion anterior sigue publicada e intacta
    assert (output_root / "restore_test").exists()
    restored_manifest = json.loads((output_root / "restore_test" / "manifest.json").read_text(encoding="utf-8"))
    assert restored_manifest["started_at"] == first_manifest["started_at"]
    assert restored_manifest["published"] is True
    # la nueva ejecucion (fallida) se conserva en el temporal
    assert (output_root / ".restore_test.tmp").exists()


# --------------------------------------------------------------------------
# Correccion (punto 2 + 3 + 4): procedencia individual por CSV bajo
# --copy-inputs cuando un fichero tiene read_error, y su fila en
# execution_summary.
# --------------------------------------------------------------------------

def test_main_with_copy_inputs_marks_read_error_csv_as_not_analyzed_end_to_end(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    good_path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_invalid_csv(good_path, id_client=10204)
    broken_path = data_dir / "TA_FOV_SCP_ML_66666_Broken.csv"
    broken_path.write_bytes(b"whatever bytes")
    output_root = tmp_path / "runs"

    import src.input_inventory as inv_module
    real_hash = inv_module.compute_sha256

    def failing_hash(p):
        if p.name == "TA_FOV_SCP_ML_66666_Broken.csv":
            raise OSError("permiso denegado (simulado)")
        return real_hash(p)

    monkeypatch.setattr(inv_module, "compute_sha256", failing_hash)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "readerr_copy",
        "--copy-inputs",
    ])
    assert exit_code == 0
    run_dir = output_root / "readerr_copy"

    # nunca se copia un fichero con read_error, ni siquiera con --copy-inputs
    assert not (run_dir / "inputs" / "TA_FOV_SCP_ML_66666_Broken.csv").exists()
    assert (run_dir / "inputs" / "TA_FOV_SCP_ML_10204_SKLUM.csv").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in manifest["csv_files"]}
    broken_entry = by_name["TA_FOV_SCP_ML_66666_Broken.csv"]
    assert broken_entry["analyzed_source"] == "not_analyzed"
    assert broken_entry["analysis_status"] == "INPUT_READ_ERROR"
    assert broken_entry["read_error"] is not None
    assert by_name["TA_FOV_SCP_ML_10204_SKLUM.csv"]["analyzed_source"] == "copy"

    # csv_copiados refleja el numero REAL de copias (1), no len(inventory) (2)
    log_text = (run_dir / "execution.log").read_text(encoding="utf-8")
    assert "csv_copiados=1" in log_text

    summary_md = (run_dir / "execution_summary.md").read_text(encoding="utf-8")
    assert "TA_FOV_SCP_ML_66666_Broken.csv" in summary_md
    assert "INPUT_NOT_ANALYZED" in summary_md

    import openpyxl
    wb = openpyxl.load_workbook(run_dir / "execution_summary.xlsx")
    ws = wb["execution_summary"]
    assert ws.max_row == 3  # cabecera + 2 CSV (uno analizado, uno no)


# --------------------------------------------------------------------------
# Correccion (punto 5): un cambio de SOLO metadata (mtime_ns) durante la
# ejecucion no invalida ni bloquea la ejecucion, pero el resultado nunca
# queda como SUCCESS puro.
# --------------------------------------------------------------------------

def test_main_marks_success_with_warnings_when_only_metadata_changes_and_clients_are_clean(tmp_path: Path, monkeypatch):
    import os as os_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_full_valid_csv(csv_path, id_client=10204)
    output_root = tmp_path / "runs"

    from src.client_analysis import analyze_client as real_analyze_client

    def touching_analyze_client(source):
        result = real_analyze_client(source)
        # cambia UNICAMENTE la fecha de modificacion, preservando exactamente
        # los mismos bytes (mismo tamano, mismo contenido, mismo SHA-256).
        stat_before = csv_path.stat()
        new_mtime = stat_before.st_mtime + 5.0
        os_module.utime(csv_path, (new_mtime, new_mtime))
        return result

    monkeypatch.setattr(pipeline, "analyze_client", touching_analyze_client)

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "metadata_only",
    ])

    assert exit_code == 0
    run_dir = output_root / "metadata_only"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    # el cliente esta limpio de problemas de calidad de datos: el unico
    # warning presente es WINNER_FORMULA_NOT_AUDITABLE, que
    # client_analysis.py anade de forma INCONDICIONAL a todo cliente valido
    # (no depende de los datos, es estructural) y por tanto no puede
    # eliminarse mediante un fixture "mas limpio". Ninguna de las
    # comprobaciones de reconstruccion (WAPE/MAE/RMSE/BIAS/error chain)
    # dispara advertencia: el fixture reproduce esas formulas exactamente.
    client_entry = manifest["csv_files"][0]
    assert client_entry["warnings"] == 1
    assert client_entry["errors"] == 0

    assert manifest["input_metadata_changed"] == ["TA_FOV_SCP_ML_10204_SKLUM.csv"]
    assert manifest["status"] == "SUCCESS_WITH_WARNINGS"
    assert manifest["published"] is True

    log_text = (run_dir / "execution.log").read_text(encoding="utf-8")
    assert "INPUT_METADATA_CHANGED" in log_text
    assert "TA_FOV_SCP_ML_10204_SKLUM.csv" in log_text


def test_apply_metadata_changed_status_escalates_pure_success_to_warnings():
    """
    Prueba aislada de la regla exacta pedida (punto 5): un cambio de solo
    metadata nunca deja el resultado en SUCCESS puro. Se prueba de forma
    aislada porque, en la practica, ningun cliente completamente analizado
    llega nunca a "SUCCESS" puro (WINNER_FORMULA_NOT_AUDITABLE es
    incondicional), asi que esta es la unica forma de verificar la regla en
    el caso limite que la motiva.
    """
    assert pipeline._apply_metadata_changed_status("SUCCESS", ["a.csv"]) == "SUCCESS_WITH_WARNINGS"


def test_apply_metadata_changed_status_leaves_already_escalated_status_unchanged():
    assert pipeline._apply_metadata_changed_status("SUCCESS_WITH_WARNINGS", ["a.csv"]) == "SUCCESS_WITH_WARNINGS"


def test_apply_metadata_changed_status_is_noop_without_metadata_changes():
    assert pipeline._apply_metadata_changed_status("SUCCESS", []) == "SUCCESS"
    assert pipeline._apply_metadata_changed_status("SUCCESS_WITH_WARNINGS", []) == "SUCCESS_WITH_WARNINGS"
