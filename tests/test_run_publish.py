import json
import os
from pathlib import Path

import pytest

import src.run_publish as run_publish_module
from src.run_config import build_arg_parser, build_run_config
from src.run_publish import publish_run, reconcile_interrupted_publication


def _cfg(tmp_path: Path, run_name: str = "run1"):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args(["--output-root", str(tmp_path / "runs"), "--run-name", run_name])
    return build_run_config(args, tmp_path)


def _seed_run(dir_path: Path, marker: str, published: bool = False) -> None:
    """Crea un directorio de ejecucion minimo pero realista: marker + manifest.json + execution.log."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "marker.txt").write_text(marker, encoding="utf-8")
    (dir_path / "manifest.json").write_text(json.dumps({
        "run_name": dir_path.name, "status": "SUCCESS", "published": published,
        "output_dir_working": None if published else str(dir_path), "output_dir_final": None,
    }), encoding="utf-8")
    (dir_path / "execution.log").write_text("seed\n", encoding="utf-8")


def _mark_complete(dir_path: Path) -> None:
    (dir_path / ".publish_complete").write_text("published_at=test\n", encoding="utf-8")


# --------------------------------------------------------------------------
# publish_run(): flujo normal (happy path).
# --------------------------------------------------------------------------

def test_publish_run_renames_temp_to_final_when_no_previous_run(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_temp, "NEW")

    publish_run(cfg)

    assert not cfg.run_dir_temp.exists()
    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "NEW"
    manifest = json.loads((cfg.run_dir_final / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["published"] is True
    assert manifest["output_dir_working"] is None
    log_text = (cfg.run_dir_final / "execution.log").read_text(encoding="utf-8")
    assert "PUBLISH" in log_text and "publicado en" in log_text
    assert cfg.publish_marker_path.exists()


def test_publish_run_replaces_previous_run_via_backup_swap(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    publish_run(cfg)

    assert not cfg.run_dir_temp.exists()
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "NEW"
    assert cfg.publish_marker_path.exists()


def test_publish_run_restores_previous_run_when_final_rename_fails(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    real_rename = os.rename

    def fake_rename(src, dst):
        if Path(src) == cfg.run_dir_temp and Path(dst) == cfg.run_dir_final:
            raise OSError("fallo simulado durante la publicacion")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", fake_rename)

    with pytest.raises(OSError):
        publish_run(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


# --------------------------------------------------------------------------
# publish_run(): finalizacion transaccional (manifest/log/marca).
# --------------------------------------------------------------------------

def test_publish_run_rolls_back_without_previous_run_when_manifest_patch_fails(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_temp, "NEW")

    def failing_patch(run_config):
        raise OSError("fallo simulado escribiendo manifest.json")
    monkeypatch.setattr(run_publish_module, "_patch_manifest_published", failing_patch)

    with pytest.raises(OSError):
        publish_run(cfg)

    assert not cfg.run_dir_final.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"
    assert not cfg.run_dir_backup.exists()


def test_publish_run_rolls_back_and_restores_previous_run_when_manifest_patch_fails(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    def failing_patch(run_config):
        raise OSError("fallo simulado escribiendo manifest.json")
    monkeypatch.setattr(run_publish_module, "_patch_manifest_published", failing_patch)

    with pytest.raises(OSError):
        publish_run(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


def test_publish_run_rolls_back_when_manifest_json_is_corrupt(tmp_path: Path):
    cfg = _cfg(tmp_path)
    cfg.run_dir_temp.mkdir(parents=True)
    (cfg.run_dir_temp / "marker.txt").write_text("NEW", encoding="utf-8")
    (cfg.run_dir_temp / "manifest.json").write_text("{not valid json", encoding="utf-8")
    (cfg.run_dir_temp / "execution.log").write_text("seed\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        publish_run(cfg)

    assert not cfg.run_dir_final.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


def test_publish_run_rolls_back_and_restores_previous_run_when_final_log_append_fails(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    def failing_log_append(run_config):
        raise OSError("fallo simulado escribiendo execution.log")
    monkeypatch.setattr(run_publish_module, "_append_final_publish_log_line", failing_log_append)

    with pytest.raises(OSError):
        publish_run(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"
    # el manifest.json patcheado (published=true) viaja de vuelta al temporal;
    # la correccion definitiva de ese campo es responsabilidad del llamador
    # (analysis_fov_scp_ml._mark_publish_failure).
    manifest = json.loads((cfg.run_dir_temp / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["published"] is True  # aun sin corregir a este nivel
    # y NUNCA se creo la marca de publicacion completa para esta ejecucion fallida
    assert not (cfg.run_dir_temp / ".publish_complete").exists()


def test_publish_run_rolls_back_when_marker_creation_fails(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    def failing_marker(run_config):
        raise OSError("fallo simulado creando .publish_complete")
    monkeypatch.setattr(run_publish_module, "_create_publish_complete_marker", failing_marker)

    with pytest.raises(OSError):
        publish_run(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"
    assert not (cfg.run_dir_temp / ".publish_complete").exists()


def test_publish_run_backup_survives_until_marker_created_and_removed_only_on_success(tmp_path: Path, monkeypatch):
    """El backup nunca se elimina hasta que manifest+log+marca se han actualizado con exito."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    def failing_patch(run_config):
        raise OSError("fallo simulado")
    monkeypatch.setattr(run_publish_module, "_patch_manifest_published", failing_patch)

    with pytest.raises(OSError):
        publish_run(cfg)
    assert not cfg.run_dir_backup.exists()  # ya restaurado a final, no queda huerfano

    monkeypatch.undo()
    _seed_run(cfg.run_dir_temp, "NEW2")
    publish_run(cfg)
    assert not cfg.run_dir_backup.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "NEW2"
    assert cfg.publish_marker_path.exists()


# --------------------------------------------------------------------------
# Punto 2: escritura atomica del manifest durante la publicacion.
# --------------------------------------------------------------------------

def test_patch_manifest_published_leaves_no_tmp_file_after_success(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_temp, "NEW")

    publish_run(cfg)

    assert not (cfg.run_dir_final / "manifest.json.tmp").exists()
    assert (cfg.run_dir_final / "manifest.json").exists()


def test_manifest_replace_failure_leaves_original_manifest_intact_and_rolls_back(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "OLD")
    _seed_run(cfg.run_dir_temp, "NEW")

    real_replace = os.replace

    def failing_replace(src, dst):
        if str(dst).endswith("manifest.json"):
            raise OSError("fallo simulado en os.replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        publish_run(cfg)

    # la ejecucion anterior se restaura y su manifest.json original nunca
    # quedo corrupto ni a medio escribir (os.replace nunca llego a sustituirlo)
    restored_manifest = json.loads((cfg.run_dir_final / "manifest.json").read_text(encoding="utf-8"))
    assert restored_manifest["status"] == "SUCCESS"
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"


def test_atomic_write_json_uses_temp_file_and_replace(tmp_path: Path, monkeypatch):
    calls = []
    real_replace = os.replace

    def spying_replace(src, dst):
        calls.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spying_replace)

    target = tmp_path / "manifest.json"
    target.write_text(json.dumps({"a": 1}), encoding="utf-8")
    run_publish_module._atomic_write_json(target, {"a": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert not (tmp_path / "manifest.json.tmp").exists()
    assert calls == [("manifest.json.tmp", "manifest.json")]


# --------------------------------------------------------------------------
# Punto 1 + 3: reconcile_interrupted_publication() - los 6 casos, construyendo
# directamente los estados de disco que dejaria una interrupcion abrupta, sin
# depender de que publish_run() ejecute su propio rollback.
# --------------------------------------------------------------------------

def test_reconcile_case1_backup_only_restores_backup_to_final(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")

    reconcile_interrupted_publication(cfg)

    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"


def test_reconcile_case2_backup_and_final_with_marker_keeps_final_removes_backup(tmp_path: Path):
    """backup anterior + final nuevo CON marca: la publicacion SI se completo; se conserva final, se limpia el backup."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")
    _seed_run(cfg.run_dir_final, "NEW", published=True)
    _mark_complete(cfg.run_dir_final)

    reconcile_interrupted_publication(cfg)

    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "NEW"
    assert cfg.publish_marker_path.exists()
    assert not cfg.run_dir_temp.exists()


def test_reconcile_case3_backup_and_final_without_marker_restores_previous_and_preserves_new(tmp_path: Path):
    """backup anterior + final nuevo SIN marca: la publicacion NO se completo; se restaura la anterior."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")
    _seed_run(cfg.run_dir_final, "NEW", published=True)  # published=true en el manifest, pero SIN marca

    reconcile_interrupted_publication(cfg)

    # la ejecucion anterior valida NUNCA se pierde: reaparece en 'final'
    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    # la nueva ejecucion incompleta se conserva integra para diagnostico, en el temporal
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


def test_reconcile_case4_final_only_with_marker_is_noop(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "COMPLETE", published=True)
    _mark_complete(cfg.run_dir_final)

    reconcile_interrupted_publication(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "COMPLETE"
    assert cfg.publish_marker_path.exists()
    assert not cfg.run_dir_temp.exists()
    assert not cfg.run_dir_backup.exists()


def test_reconcile_case5_final_only_without_marker_moves_to_temp(tmp_path: Path):
    """final sin backup y sin marca: nunca se trata como publicada, se mueve al temporal."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_final, "INCOMPLETE", published=True)  # published=true, pero sin marca: no es de fiar

    reconcile_interrupted_publication(cfg)

    assert not cfg.run_dir_final.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "INCOMPLETE"


def test_reconcile_case6_neither_backup_nor_final_is_noop(tmp_path: Path):
    cfg = _cfg(tmp_path)
    reconcile_interrupted_publication(cfg)
    assert not cfg.run_dir_final.exists()
    assert not cfg.run_dir_temp.exists()
    assert not cfg.run_dir_backup.exists()


def test_reconcile_corrupt_manifest_with_backup_restores_previous_run(tmp_path: Path):
    """
    manifest corrupto (o ausente) en 'final', con backup disponible: la
    decision de reconciliar se basa UNICAMENTE en la presencia de la marca,
    nunca en poder parsear manifest.json, asi que un manifest corrupto no
    hace fallar la reconciliacion: se trata igual que 'sin marca' y se
    restaura la ejecucion anterior.
    """
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")
    cfg.run_dir_final.mkdir(parents=True)
    (cfg.run_dir_final / "marker.txt").write_text("NEW", encoding="utf-8")
    (cfg.run_dir_final / "manifest.json").write_text("{not valid json at all", encoding="utf-8")
    # sin .publish_complete

    reconcile_interrupted_publication(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert not cfg.run_dir_backup.exists()
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


def test_reconcile_missing_manifest_with_backup_restores_previous_run(tmp_path: Path):
    """final sin manifest.json en absoluto (interrupcion muy temprana), con backup disponible: se restaura la anterior."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")
    cfg.run_dir_final.mkdir(parents=True)
    (cfg.run_dir_final / "marker.txt").write_text("NEW", encoding="utf-8")
    # sin manifest.json, sin .publish_complete

    reconcile_interrupted_publication(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    assert cfg.run_dir_temp.exists()
    assert (cfg.run_dir_temp / "marker.txt").read_text(encoding="utf-8") == "NEW"


def test_reconcile_interruption_right_after_published_true_but_before_marker(tmp_path: Path):
    """
    Reproduce exactamente el punto de fallo mas peligroso: el proceso muere
    justo despues de patchear manifest.json a published=true, pero antes de
    escribir la linea final del log o crear la marca. El manifest MIENTE
    (published=true) pero la reconciliacion nunca confia en el, solo en la
    marca: la ejecucion se trata como interrumpida y la anterior se restaura.
    """
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "OLD")
    cfg.run_dir_final.mkdir(parents=True)
    (cfg.run_dir_final / "marker.txt").write_text("NEW", encoding="utf-8")
    (cfg.run_dir_final / "manifest.json").write_text(json.dumps({
        "run_name": "run1", "status": "SUCCESS", "published": True,
        "output_dir_working": None, "output_dir_final": str(cfg.run_dir_final),
    }), encoding="utf-8")
    # execution.log SIN la linea final de PUBLISH, y SIN .publish_complete
    (cfg.run_dir_final / "execution.log").write_text("seed\n", encoding="utf-8")

    reconcile_interrupted_publication(cfg)

    assert cfg.run_dir_final.exists()
    assert (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8") == "OLD"
    restored_manifest = json.loads((cfg.run_dir_final / "manifest.json").read_text(encoding="utf-8"))
    assert restored_manifest["published"] is False  # el manifest restaurado es el de la ejecucion anterior, correcto
    assert cfg.run_dir_temp.exists()
    new_manifest_at_temp = json.loads((cfg.run_dir_temp / "manifest.json").read_text(encoding="utf-8"))
    assert new_manifest_at_temp["published"] is True  # la mentira queda preservada para diagnostico, no publicada


def test_reconcile_never_deletes_previous_valid_run_when_present(tmp_path: Path):
    """Prueba de propiedad general: en ningun escenario con backup valido este se pierde sin restaurarse a final."""
    cfg = _cfg(tmp_path)
    _seed_run(cfg.run_dir_backup, "PREVIOUS_VALID")
    _seed_run(cfg.run_dir_final, "MAYBE_INCOMPLETE")  # sin marca

    reconcile_interrupted_publication(cfg)

    final_marker = (cfg.run_dir_final / "marker.txt").read_text(encoding="utf-8")
    assert final_marker == "PREVIOUS_VALID"
