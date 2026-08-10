import hashlib
import json
from datetime import datetime
from pathlib import Path

from src.input_inventory import build_input_inventory
from src.manifest import build_manifest, compute_sha256, detect_git_commit, detect_git_worktree_dirty, write_manifest
from src.run_config import build_arg_parser, build_run_config
from tests.factories import build_multi_client_results


def _run_config(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args([
        "--input-dir", str(tmp_path / "data"),
        "--output-root", str(tmp_path / "runs"),
        "--run-name", "test_run",
    ])
    return build_run_config(args, tmp_path)


def _now():
    return datetime.now().astimezone()


def _git(args: list[str], cwd: Path):
    import os
    import subprocess
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.com",
    })
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def test_compute_sha256_matches_known_value(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert compute_sha256(path) == expected


def test_detect_git_commit_returns_none_outside_a_repo(tmp_path: Path):
    assert detect_git_commit(tmp_path) is None


def test_detect_git_worktree_dirty_returns_none_outside_a_repo(tmp_path: Path):
    assert detect_git_worktree_dirty(tmp_path) is None


def test_detect_git_worktree_dirty_returns_none_when_git_unavailable(tmp_path: Path, monkeypatch):
    import subprocess as sp
    def fake_run(*a, **k):
        raise FileNotFoundError("git no encontrado")
    monkeypatch.setattr(sp, "run", fake_run)
    assert detect_git_worktree_dirty(tmp_path) is None
    assert detect_git_commit(tmp_path) is None


def test_detect_git_worktree_dirty_false_on_clean_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["commit", "-m", "initial"], repo)

    assert detect_git_worktree_dirty(repo) is False
    assert detect_git_commit(repo) is not None


def test_detect_git_worktree_dirty_true_with_uncommitted_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["commit", "-m", "initial"], repo)

    (repo / "a.txt").write_text("y", encoding="utf-8")  # cambio sin commit
    assert detect_git_worktree_dirty(repo) is True


def test_build_manifest_includes_one_entry_per_discovered_csv_even_without_client_source(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_11111_Unparseable.csv").write_bytes(b"\xff\xfe not really csv")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="FAILED",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["n_csv_discovered"] == 1
    entry = manifest["csv_files"][0]
    assert entry["name"] == "TA_FOV_SCP_ML_11111_Unparseable.csv"
    # los bytes se pueden leer/hashear igualmente (no es un read_error): el
    # problema de parseo como CSV con esquema es un asunto de load_client_sources,
    # no del inventario. Sin resultado correlacionado (no se paso en `results`),
    # queda como no procesado.
    assert entry["sha256"] is not None
    assert entry["size_bytes"] is not None
    assert entry["mtime_ns"] is not None
    assert entry["id_client"] is None
    assert entry["analyzed_source"] == "not_analyzed"
    assert entry["analysis_status"] == "NOT_PROCESSED"


def test_build_manifest_marks_read_error_entries_as_not_analyzed_even_with_copy_inputs(tmp_path: Path, monkeypatch):
    """
    Un CSV con read_error nunca se copia ni se analiza, ni siquiera con
    --copy-inputs: no debe aparecer como analizado desde una copia.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_11111_X.csv"
    path.write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)

    import src.input_inventory as inv_module
    real_hash = inv_module.compute_sha256

    def failing_hash(p: Path) -> str:
        if p == path:
            raise OSError("simulado")
        return real_hash(p)
    monkeypatch.setattr(inv_module, "compute_sha256", failing_hash)

    inventory = build_input_inventory(cfg.input_dir)
    assert inventory[0].read_error is not None

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="FAILED",
        git_commit=None, git_worktree_dirty=None, copy_inputs=True, published=False,
    )
    entry = manifest["csv_files"][0]
    assert entry["analyzed_source"] == "not_analyzed"
    assert entry["analysis_status"] == "INPUT_READ_ERROR"
    assert entry["analysis_error"] is not None
    assert entry["sha256"] is None


def test_build_manifest_marks_analyzed_source_per_record_original(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = build_multi_client_results()
    for r in results:
        (data_dir / r.source.csv_path.name).write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    by_name = {e["name"]: e for e in manifest["csv_files"]}
    entry = by_name["TA_FOV_SCP_ML_99999_Synthetic.csv"]
    assert entry["analyzed_source"] == "original"
    assert entry["analysis_status"] == entry["estado"]


def test_build_manifest_marks_analyzed_source_per_record_copy(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = build_multi_client_results()
    for r in results:
        (data_dir / r.source.csv_path.name).write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=True, published=False,
    )
    by_name = {e["name"]: e for e in manifest["csv_files"]}
    assert by_name["TA_FOV_SCP_ML_99999_Synthetic.csv"]["analyzed_source"] == "copy"


def test_build_manifest_does_not_recompute_hashes_from_disk(tmp_path: Path, monkeypatch):
    """El inventario ya trae los hashes: build_manifest no debe volver a llamar a compute_sha256."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_11111_X.csv").write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    import src.manifest as manifest_module

    def _forbidden(*a, **k):
        raise AssertionError("build_manifest no debe recalcular hashes")
    monkeypatch.setattr(manifest_module, "compute_sha256", _forbidden)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["csv_files"][0]["sha256"] is not None


def test_build_manifest_correlates_csv_entries_with_client_results(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = build_multi_client_results()
    for r in results:
        (data_dir / r.source.csv_path.name).write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["n_csv_discovered"] == 3
    by_name = {e["name"]: e for e in manifest["csv_files"]}
    assert by_name["TA_FOV_SCP_ML_99999_Synthetic.csv"]["id_client"] == 99999
    assert manifest["n_clients_total"] == 3


# --------------------------------------------------------------------------
# Fase 3: agregacion de csv_files cuando un unico CSV fisico produce varios
# ClientAnalysisResult (particion por ID_CLIENT).
# --------------------------------------------------------------------------

def _results_sharing_one_physical_file(results: list, shared_name: str = "TA_FOV_SCP_ML_full_export.csv") -> list:
    """Fuerza a que todos los resultados compartan el mismo csv_path fisico, como produce load_client_sources_from_csv."""
    for r in results:
        r.source.csv_path = Path(shared_name)
    return results


def test_build_manifest_aggregates_multi_client_csv_into_a_single_entry(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = _results_sharing_one_physical_file(build_multi_client_results())
    (data_dir / "TA_FOV_SCP_ML_full_export.csv").write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["n_csv_discovered"] == 1
    assert len(manifest["csv_files"]) == 1
    entry = manifest["csv_files"][0]
    # con N>1 clientes en el mismo CSV fisico, id_client/etiqueta no representan
    # a ninguno de ellos en particular
    assert entry["id_client"] is None
    assert entry["etiqueta"] is None
    assert entry["filas"] == sum(r.source.n_rows for r in results)
    assert entry["warnings"] == sum(r.quality.summary_counts().get("WARNING", 0) for r in results)
    assert entry["errors"] == sum(r.quality.summary_counts().get("ERROR", 0) for r in results)


def test_build_manifest_status_precedence_error_dominates(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = _results_sharing_one_physical_file(build_multi_client_results())
    results[0].status = "SUCCESS"
    results[1].status = "SUCCESS_WITH_WARNINGS"
    results[2].status = "ERROR"
    (data_dir / "TA_FOV_SCP_ML_full_export.csv").write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["csv_files"][0]["estado"] == "ERROR"


def test_build_manifest_status_precedence_warnings_dominate_over_success(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = _results_sharing_one_physical_file(build_multi_client_results())
    results[0].status = "SUCCESS"
    results[1].status = "SUCCESS_WITH_WARNINGS"
    results[2].status = "SUCCESS"
    (data_dir / "TA_FOV_SCP_ML_full_export.csv").write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["csv_files"][0]["estado"] == "SUCCESS_WITH_WARNINGS"


def test_build_manifest_single_client_csv_retains_id_client_and_etiqueta(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    results = build_multi_client_results()[:1]  # un unico cliente para este CSV fisico
    (data_dir / results[0].source.csv_path.name).write_text("dummy", encoding="utf-8")
    cfg = _run_config(tmp_path)
    inventory = build_input_inventory(cfg.input_dir)

    now = _now()
    manifest = build_manifest(
        cfg, inventory, results=results, global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS_WITH_WARNINGS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    entry = manifest["csv_files"][0]
    assert entry["id_client"] == results[0].source.id_client
    assert entry["etiqueta"] == results[0].source.file_label


def test_build_manifest_includes_failure_block_when_provided(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="FAILED",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
        failure={"phase": "DISCOVER", "error_type": "NoCsvFoundError", "error_message": "no csv"},
    )
    assert manifest["status"] == "FAILED"
    assert manifest["failure"]["phase"] == "DISCOVER"


def test_build_manifest_omits_failure_block_when_not_provided(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert "failure" not in manifest


def test_build_manifest_reflects_git_fields(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit="abc123", git_worktree_dirty=True, copy_inputs=False, published=False,
    )
    assert manifest["git_commit"] == "abc123"
    assert manifest["git_worktree_dirty"] is True


def test_build_manifest_defaults_input_metadata_changed_to_empty_list(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["input_metadata_changed"] == []


def test_build_manifest_reflects_input_metadata_changed(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
        input_metadata_changed=["TA_FOV_SCP_ML_10204_SKLUM.csv"],
    )
    assert manifest["input_metadata_changed"] == ["TA_FOV_SCP_ML_10204_SKLUM.csv"]


def test_build_manifest_unpublished_run_has_working_dir_and_intended_final(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    assert manifest["published"] is False
    assert manifest["output_dir_working"] == str(cfg.run_dir_temp)
    assert manifest["output_dir_final"] == str(cfg.run_dir_final)


def test_build_manifest_published_run_has_no_working_dir(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=[],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=True,
    )
    assert manifest["published"] is True
    assert manifest["output_dir_working"] is None
    assert manifest["output_dir_final"] == str(cfg.run_dir_final)


def test_write_manifest_produces_valid_json(tmp_path: Path):
    cfg = _run_config(tmp_path)
    now = _now()
    manifest = build_manifest(
        cfg, inventory=[], results=[], global_result=None, outputs_generated=["a.xlsx"],
        started_at=now, finished_at=now, status="SUCCESS",
        git_commit=None, git_worktree_dirty=None, copy_inputs=False, published=False,
    )
    out = tmp_path / "manifest.json"
    write_manifest(manifest, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["status"] == "SUCCESS"
    assert loaded["outputs_generated"] == ["a.xlsx"]
