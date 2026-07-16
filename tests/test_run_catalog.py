"""
Tests del catalogo historico de ejecuciones (Fase 5C): descubrimiento,
compatibilidad de manifest, presentacion, atomicidad de la reconstruccion,
y flujos end-to-end via pipeline.main(). Usan tmp_path y datos sinteticos;
ninguno depende de los CSV reales de data/ ni de las ejecuciones reales de
outputs/runs/.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

import analysis_fov_scp_ml as pipeline
from src import run_catalog_models as cm
from src.html_report import extract_local_links, validate_html_links
from src.manifest import MANIFEST_SCHEMA_VERSION
from src.periods import ALL_PERIODS, period_columns
from src.run_catalog import (
    CATALOG_SUMMARY_KEYS,
    CatalogRunEntry,
    IgnoredEntry,
    _catalog_summary_warnings,
    _resolve_sort_timestamp,
    order_entries,
    rebuild_run_catalog,
    scan_output_root,
)

# --------------------------------------------------------------------------
# Fixtures locales: runs sinteticos construidos directamente en disco (sin
# pasar por analyze_client/analyze_global), para ejercitar scan_output_root
# de forma rapida y aislada.
# --------------------------------------------------------------------------

def _minimal_catalog_summary(**overrides) -> dict:
    base = {
        "clients_total": 3, "clients_evaluable_6m": 2, "clients_without_performance_6m": 1,
        "series_candidates_6m": 100, "series_comparable_6m": 60, "coverage_pct_6m": 60.0,
        "wape_scp_6m": 0.2, "wape_ml_6m": 0.15, "weighted_improvement_pct_6m": 25.0,
        "net_error_reduction_6m": 500.0, "warnings_total": 3, "errors_total": 0,
    }
    base.update(overrides)
    return base


def _minimal_manifest(run_name: str = "myrun", **overrides) -> dict:
    manifest = {
        "run_name": run_name,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "SUCCESS",
        "published": True,
        "started_at": "2026-07-15T10:00:00+02:00",
        "finished_at": "2026-07-15T10:05:00+02:00",
        "pipeline_version": "1.0.0",
        "git_commit": "abc123def4567890",
        "git_worktree_dirty": False,
        "catalog_summary": _minimal_catalog_summary(),
    }
    manifest.update(overrides)
    return manifest


def _make_run_dir(
    root: Path, folder_name: str, *,
    manifest: dict | None = ...,  # type: ignore[assignment]
    manifest_text: str | None = None,
    publish_complete: bool = True,
    index_html: bool = True,
) -> Path:
    d = root / folder_name
    d.mkdir(parents=True, exist_ok=True)
    if publish_complete:
        (d / ".publish_complete").write_text("published_at=2026-07-15T10:05:00+02:00\n", encoding="utf-8")
    if manifest_text is not None:
        (d / "manifest.json").write_text(manifest_text, encoding="utf-8")
    elif manifest is not ...:
        if manifest is not None:
            (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (d / "manifest.json").write_text(json.dumps(_minimal_manifest(folder_name)), encoding="utf-8")
    if index_html:
        (d / "index.html").write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# Descubrimiento
# --------------------------------------------------------------------------

def test_scan_includes_complete_valid_run(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    scan = scan_output_root(tmp_path)
    assert [e.folder_name for e in scan.entries] == ["run_a"]
    assert scan.ignored == []


def test_scan_ignores_run_without_publish_complete_marker(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", publish_complete=False)
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert scan.ignored[0].folder_name == "run_a"
    assert ".publish_complete" in scan.ignored[0].reason


def test_scan_ignores_run_with_published_false(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", manifest=_minimal_manifest("run_a", published=False))
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert "published" in scan.ignored[0].reason


def test_scan_ignores_run_with_status_failed(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", manifest=_minimal_manifest("run_a", status="FAILED"))
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert "FAILED" in scan.ignored[0].reason


def test_scan_ignores_run_without_index_html(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", index_html=False)
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert "index.html" in scan.ignored[0].reason


def test_scan_ignores_run_with_corrupt_manifest(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", manifest_text="{not valid json")
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert "corrupto" in scan.ignored[0].reason


def test_scan_ignores_folder_without_manifest(tmp_path: Path):
    d = tmp_path / "run_a"
    d.mkdir()
    (d / ".publish_complete").write_text("x", encoding="utf-8")
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert "manifest.json" in scan.ignored[0].reason


def test_scan_ignores_temp_folder(tmp_path: Path):
    (tmp_path / ".run_a.tmp").mkdir()
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert scan.ignored[0].folder_name == ".run_a.tmp"
    assert "empieza por" in scan.ignored[0].reason


def test_scan_ignores_backup_folder(tmp_path: Path):
    (tmp_path / ".run_a.backup").mkdir()
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert scan.ignored[0].folder_name == ".run_a.backup"


def test_scan_ignores_catalog_assets_directory_silently(tmp_path: Path):
    (tmp_path / "catalog_assets").mkdir()
    scan = scan_output_root(tmp_path)
    assert scan.entries == []
    assert scan.ignored == []  # ni siquiera se registra como ignorado: es propio del catalogo


def test_scan_warns_on_run_name_mismatch_but_still_includes(tmp_path: Path):
    _make_run_dir(tmp_path, "carpeta_real", manifest=_minimal_manifest("nombre_distinto"))
    scan = scan_output_root(tmp_path)
    assert len(scan.entries) == 1
    assert any("CATALOG_RUN_NAME_MISMATCH" in w for w in scan.entries[0].warnings)


def test_scan_on_missing_output_root_returns_empty(tmp_path: Path):
    scan = scan_output_root(tmp_path / "does_not_exist")
    assert scan.entries == []
    assert scan.ignored == []
    assert scan.inspected_dirs == 0


# --------------------------------------------------------------------------
# Compatibilidad de manifest
# --------------------------------------------------------------------------

def test_scan_flags_current_schema_without_compat_warning(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    scan = scan_output_root(tmp_path)
    assert scan.entries[0].warnings == ()


def test_scan_flags_old_schema_without_catalog_summary(tmp_path: Path):
    old_manifest = _minimal_manifest("run_a")
    del old_manifest["catalog_summary"]
    del old_manifest["manifest_schema_version"]
    _make_run_dir(tmp_path, "run_a", manifest=old_manifest)
    scan = scan_output_root(tmp_path)
    assert len(scan.entries) == 1
    assert any("CATALOG_FIELDS_MISSING" in w for w in scan.entries[0].warnings)


def test_row_vm_shows_nd_for_missing_optional_fields(tmp_path: Path):
    old_manifest = _minimal_manifest("run_a")
    del old_manifest["catalog_summary"]
    row = cm.build_catalog_row_vm(old_manifest, "run_a", ["CATALOG_FIELDS_MISSING: x"], "run_a/index.html")
    assert row["wape_scp_6m"] == "N/D"
    assert row["clients_total"] == "N/D"
    assert row["has_compat_warning"] is True


def test_row_vm_shows_nd_for_null_metrics(tmp_path: Path):
    manifest = _minimal_manifest("run_a", catalog_summary=_minimal_catalog_summary(wape_scp_6m=None, net_error_reduction_6m=None))
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    assert row["wape_scp_6m"] == "N/D"
    assert row["net_error_reduction_6m"] == "N/D"


def test_scan_flags_invalid_timestamp(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a", manifest=_minimal_manifest("run_a", finished_at="no-es-una-fecha", started_at="tampoco"))
    scan = scan_output_root(tmp_path)
    ordered = order_entries(scan.entries)
    assert any("CATALOG_INVALID_TIMESTAMP" in w for w in ordered[0].warnings)
    row = cm.build_catalog_row_vm(ordered[0].manifest, ordered[0].folder_name, ordered[0].warnings, "x")
    assert row["finished_at"] == "N/D"


@pytest.mark.parametrize("dirty,expected", [(True, "sucio"), (False, "limpio"), (None, "N/D")])
def test_row_vm_worktree_label(dirty, expected):
    manifest = _minimal_manifest("run_a", git_worktree_dirty=dirty)
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    assert row["git_worktree_label"] == expected


def test_row_vm_shows_nd_when_git_absent():
    manifest = _minimal_manifest("run_a", git_commit=None)
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    assert row["git_commit_short"] == "N/D"


# --------------------------------------------------------------------------
# Presentacion
# --------------------------------------------------------------------------

def test_order_entries_descending_by_finished_at():
    e1 = CatalogRunEntry("older", _minimal_manifest("older", finished_at="2026-01-01T10:00:00+02:00"))
    e2 = CatalogRunEntry("newer", _minimal_manifest("newer", finished_at="2026-06-01T10:00:00+02:00"))
    ordered = order_entries([e1, e2])
    assert [e.folder_name for e in ordered] == ["newer", "older"]


def test_order_entries_deterministic_tiebreak_on_identical_timestamp():
    same_ts = "2026-01-01T10:00:00+02:00"
    e_b = CatalogRunEntry("run_b", _minimal_manifest("run_b", finished_at=same_ts))
    e_a = CatalogRunEntry("run_a", _minimal_manifest("run_a", finished_at=same_ts))
    ordered_1 = order_entries([e_b, e_a])
    ordered_2 = order_entries([e_a, e_b])
    assert [e.folder_name for e in ordered_1] == [e.folder_name for e in ordered_2]


def test_order_entries_places_invalid_timestamp_last():
    good = CatalogRunEntry("good", _minimal_manifest("good", finished_at="2026-01-01T10:00:00+02:00"))
    bad = CatalogRunEntry("bad", _minimal_manifest("bad", finished_at="not-a-date", started_at="not-a-date-either"))
    ordered = order_entries([bad, good])
    assert [e.folder_name for e in ordered] == ["good", "bad"]


def test_fraction_shows_numerator_and_denominator():
    manifest = _minimal_manifest("run_a", catalog_summary=_minimal_catalog_summary(clients_total=7, clients_evaluable_6m=6))
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    assert row["clients_evaluable_fraction"] == "6 de 7 clientes"


def test_row_vm_never_renders_nan_none_inf_literally():
    manifest = _minimal_manifest(
        "run_a",
        catalog_summary=_minimal_catalog_summary(
            wape_scp_6m=float("nan"), weighted_improvement_pct_6m=float("inf"), net_error_reduction_6m=None,
        ),
    )
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    for value in row.values():
        if isinstance(value, str):
            assert "nan" not in value.lower()
            assert value != "None"
            assert "inf" not in value.lower()


def test_row_vm_url_is_relative():
    manifest = _minimal_manifest("10204_SKLUM")
    row = cm.build_catalog_row_vm(manifest, "10204_SKLUM", [], "10204_SKLUM/index.html")
    assert row["url"] == "10204_SKLUM/index.html"
    assert not row["url"].startswith("/")
    assert ":" not in row["url"]


# --------------------------------------------------------------------------
# Atomicidad
# --------------------------------------------------------------------------

def _read_previous_catalog_files(tmp_path: Path) -> tuple[bytes, bytes, bytes]:
    return (
        (tmp_path / "index.html").read_bytes(),
        (tmp_path / "run_index.log").read_bytes(),
        (tmp_path / "catalog_assets" / "styles.css").read_bytes(),
    )


def _assert_catalog_files_unchanged(tmp_path: Path, previous: tuple[bytes, bytes, bytes]) -> None:
    previous_html, previous_log, previous_css = previous
    assert (tmp_path / "index.html").read_bytes() == previous_html
    assert (tmp_path / "run_index.log").read_bytes() == previous_log
    assert (tmp_path / "catalog_assets" / "styles.css").read_bytes() == previous_css


def _assert_no_leftover_tmp_files(tmp_path: Path) -> None:
    assert list(tmp_path.rglob("*.tmp")) == []


def test_rebuild_creates_valid_catalog_with_zero_runs(tmp_path: Path):
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    assert result.entries_included == 0
    assert (tmp_path / "index.html").exists()
    assert "No hay ejecuciones publicadas" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert (tmp_path / "run_index.log").exists()
    assert (tmp_path / "catalog_assets" / "styles.css").exists()
    _assert_no_leftover_tmp_files(tmp_path)


def test_rebuild_succeeds_cleanly_with_no_previous_catalog(tmp_path: Path):
    """Escenario 6: publicacion correcta cuando no hay catalogo previo, sin backups ni temporales huerfanos."""
    _make_run_dir(tmp_path, "run_a")
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "run_index.log").exists()
    assert (tmp_path / "catalog_assets" / "styles.css").exists()
    _assert_no_leftover_tmp_files(tmp_path)
    assert list(tmp_path.rglob("*.bak")) == []


def test_rebuild_failure_before_any_replace_preserves_all_three_files(tmp_path: Path, monkeypatch):
    """Escenario 1: fallo durante la preparacion (antes de cualquier os.replace)."""
    _make_run_dir(tmp_path, "run_a")
    first = rebuild_run_catalog(tmp_path)
    assert first.success is True
    previous = _read_previous_catalog_files(tmp_path)

    import src.run_catalog as run_catalog_module
    monkeypatch.setattr(run_catalog_module, "CATALOG_ASSETS_SRC", tmp_path / "no_existe.css")

    second = rebuild_run_catalog(tmp_path)
    assert second.success is False
    _assert_catalog_files_unchanged(tmp_path, previous)
    _assert_no_leftover_tmp_files(tmp_path)


@pytest.mark.parametrize(
    "fail_at_call,expected_in_error",
    [
        (1, None),  # 1a llamada a os.replace = catalog_assets/styles.css
        (2, None),  # 2a llamada = run_index.log (exito del 1o, fallo del 2o)
        (3, None),  # 3a llamada = index.html (exito de los 2 primeros, fallo del ultimo)
    ],
)
def test_rebuild_rolls_back_all_files_when_any_replace_step_fails(
    tmp_path: Path, monkeypatch, fail_at_call: int, expected_in_error,
):
    """
    Escenarios 2, 3, 4 y 5: exito parcial de la secuencia de os.replace
    (css -> log -> index) seguido de un fallo en cualquier paso concreto.
    Cubre explicitamente "exito del replace de run_index.log y fallo del
    replace de index.html" (fail_at_call=3, con css y log ya completados).
    """
    _make_run_dir(tmp_path, "run_a")
    first = rebuild_run_catalog(tmp_path)
    assert first.success is True
    previous = _read_previous_catalog_files(tmp_path)

    _make_run_dir(tmp_path, "run_b")  # cambiaria el contenido si la reconstruccion tuviera exito

    import src.run_catalog as run_catalog_module
    real_replace = run_catalog_module.os.replace
    counter = {"n": 0}

    def flaky_replace(src, dst):
        counter["n"] += 1
        if counter["n"] == fail_at_call:
            raise OSError(f"fallo simulado en la llamada os.replace numero {fail_at_call}")
        return real_replace(src, dst)

    monkeypatch.setattr(run_catalog_module.os, "replace", flaky_replace)

    second = rebuild_run_catalog(tmp_path)
    assert second.success is False
    # HTML, log Y CSS anteriores quedan exactamente intactos, sin importar
    # cuantos de los 3 replace ya se hubieran completado antes del fallo.
    _assert_catalog_files_unchanged(tmp_path, previous)
    _assert_no_leftover_tmp_files(tmp_path)
    assert list(tmp_path.rglob("*.bak")) == []


def test_rebuild_link_validation_failure_prevents_replacing_index(tmp_path: Path, monkeypatch):
    _make_run_dir(tmp_path, "run_a")
    first = rebuild_run_catalog(tmp_path)
    assert first.success is True
    previous = _read_previous_catalog_files(tmp_path)

    import src.run_catalog as run_catalog_module
    monkeypatch.setattr(
        run_catalog_module, "validate_html_links",
        lambda paths, root, pending_targets=None: ["problema simulado"],
    )

    second = rebuild_run_catalog(tmp_path)
    assert second.success is False
    assert "problema simulado" in second.error
    _assert_catalog_files_unchanged(tmp_path, previous)
    _assert_no_leftover_tmp_files(tmp_path)


def test_rebuild_replaces_index_only_after_successful_validation(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    assert "run_a/index.html" in (tmp_path / "index.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Enlace a run_index.log
# --------------------------------------------------------------------------

def test_run_index_log_link_present_in_index_html(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="run_index.log"' in html


def test_run_index_log_target_exists_after_publish(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    assert (tmp_path / "run_index.log").exists()
    problems = validate_html_links([tmp_path / "index.html"], tmp_path)
    assert problems == []


def test_run_index_log_link_valid_after_moving_output_root(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    rebuild_run_catalog(tmp_path)

    moved = tmp_path.parent / "moved_catalog_copy"
    shutil.copytree(tmp_path, moved)

    problems = validate_html_links([moved / "index.html"], moved)
    assert problems == []
    assert (moved / "run_index.log").exists()


def test_run_index_log_link_present_with_zero_valid_runs(tmp_path: Path):
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="run_index.log"' in html
    assert validate_html_links([tmp_path / "index.html"], tmp_path) == []


def test_run_index_log_link_valid_when_rebuilding_over_existing_catalog(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    first = rebuild_run_catalog(tmp_path)
    assert first.success is True

    _make_run_dir(tmp_path, "run_b")
    second = rebuild_run_catalog(tmp_path)
    assert second.success is True

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="run_index.log"' in html
    assert validate_html_links([tmp_path / "index.html"], tmp_path) == []


# --------------------------------------------------------------------------
# Validacion completa de catalog_summary (claves del schema)
# --------------------------------------------------------------------------

def test_catalog_summary_complete_produces_no_warning():
    manifest = _minimal_manifest("run_a")
    assert _catalog_summary_warnings(manifest) == []


def test_catalog_summary_partially_incomplete_lists_missing_keys():
    manifest = _minimal_manifest("run_a")
    del manifest["catalog_summary"]["wape_scp_6m"]
    del manifest["catalog_summary"]["net_error_reduction_6m"]

    warnings = _catalog_summary_warnings(manifest)
    assert len(warnings) == 1
    assert "CATALOG_FIELDS_MISSING" in warnings[0]
    assert "wape_scp_6m" in warnings[0]
    assert "net_error_reduction_6m" in warnings[0]


def test_catalog_summary_absent_produces_generic_warning_and_run_still_included(tmp_path: Path):
    manifest = _minimal_manifest("run_a")
    del manifest["catalog_summary"]
    _make_run_dir(tmp_path, "run_a", manifest=manifest)

    scan = scan_output_root(tmp_path)
    assert len(scan.entries) == 1
    assert any("CATALOG_FIELDS_MISSING" in w for w in scan.entries[0].warnings)

    row = cm.build_catalog_row_vm(manifest, "run_a", scan.entries[0].warnings, "run_a/index.html")
    for key in CATALOG_SUMMARY_KEYS:
        assert row[key] == "N/D"


def test_catalog_summary_null_value_is_not_treated_as_missing():
    """Una clave PRESENTE con valor null es valida: no debe confundirse con una clave ausente."""
    manifest = _minimal_manifest("run_a", catalog_summary=_minimal_catalog_summary(wape_scp_6m=None, net_error_reduction_6m=None))
    assert set(manifest["catalog_summary"]) == set(CATALOG_SUMMARY_KEYS)
    assert _catalog_summary_warnings(manifest) == []
    row = cm.build_catalog_row_vm(manifest, "run_a", [], "run_a/index.html")
    assert row["wape_scp_6m"] == "N/D"  # se muestra N/D, pero NO por ser "ausente"


def test_catalog_summary_old_schema_without_version_or_summary():
    manifest = _minimal_manifest("run_a")
    del manifest["manifest_schema_version"]
    del manifest["catalog_summary"]
    warnings = _catalog_summary_warnings(manifest)
    assert len(warnings) == 1
    assert "CATALOG_FIELDS_MISSING" in warnings[0]


def test_catalog_summary_schema_newer_than_supported_is_flagged():
    manifest = _minimal_manifest("run_a", manifest_schema_version=MANIFEST_SCHEMA_VERSION + 97)
    warnings = _catalog_summary_warnings(manifest)
    assert any("CATALOG_SCHEMA_NEWER" in w for w in warnings)
    assert any(str(MANIFEST_SCHEMA_VERSION + 97) in w for w in warnings)


def test_catalog_summary_warnings_reflected_in_run_index_log_and_incidents(tmp_path: Path):
    manifest = _minimal_manifest("run_a")
    del manifest["catalog_summary"]["wape_scp_6m"]
    _make_run_dir(tmp_path, "run_a", manifest=manifest)

    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    assert result.warnings_total == 1

    log_text = (tmp_path / "run_index.log").read_text(encoding="utf-8")
    assert "CATALOG_FIELDS_MISSING" in log_text
    assert "wape_scp_6m" in log_text

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "CATALOG_FIELDS_MISSING" in html
    assert "wape_scp_6m" in html


# --------------------------------------------------------------------------
# Timestamps y warnings inmutables
# --------------------------------------------------------------------------

def test_resolve_sort_timestamp_accepts_offset_timestamp():
    manifest = _minimal_manifest("run_a", finished_at="2026-03-01T10:00:00+02:00")
    ts, warnings = _resolve_sort_timestamp(manifest)
    assert ts is not None
    assert warnings == []


def test_resolve_sort_timestamp_naive_generates_warning_and_is_not_used():
    manifest = _minimal_manifest("run_a", finished_at="2026-03-01T10:00:00", started_at=None)
    ts, warnings = _resolve_sort_timestamp(manifest)
    assert ts is None
    assert any("zona horaria" in w for w in warnings)


def test_resolve_sort_timestamp_falls_back_to_started_at_when_finished_invalid():
    manifest = _minimal_manifest("run_a", finished_at="no-es-valido", started_at="2026-01-01T09:00:00+02:00")
    ts, warnings = _resolve_sort_timestamp(manifest)
    assert ts is not None
    assert any("finished_at" in w for w in warnings)
    assert not any("started_at" in w for w in warnings)


def test_resolve_sort_timestamp_both_invalid_returns_none_with_two_warnings():
    manifest = _minimal_manifest("run_a", finished_at="no-es-valido", started_at="tampoco-es-valido")
    ts, warnings = _resolve_sort_timestamp(manifest)
    assert ts is None
    assert len(warnings) == 2


def test_order_entries_never_mutates_the_original_entry(tmp_path: Path):
    original = CatalogRunEntry(
        "run_a", _minimal_manifest("run_a", finished_at="no-valido", started_at="tampoco"), warnings=(),
    )
    order_entries([original])
    assert original.warnings == ()  # el objeto original pasado como argumento permanece intacto


def test_order_entries_returns_new_entry_with_appended_warning_when_needed():
    original = CatalogRunEntry(
        "run_a", _minimal_manifest("run_a", finished_at="no-valido", started_at="tampoco"), warnings=("PREEXISTENTE",),
    )
    ordered = order_entries([original])
    assert ordered[0] is not original
    assert "PREEXISTENTE" in ordered[0].warnings
    assert any("CATALOG_INVALID_TIMESTAMP" in w for w in ordered[0].warnings)


def test_repeated_rebuild_does_not_duplicate_timestamp_warnings(tmp_path: Path):
    manifest = _minimal_manifest("run_a", finished_at="no-valido", started_at="tampoco-valido")
    _make_run_dir(tmp_path, "run_a", manifest=manifest)

    first = rebuild_run_catalog(tmp_path)
    assert first.success is True
    second = rebuild_run_catalog(tmp_path)
    assert second.success is True

    assert first.warnings_total == second.warnings_total
    log_text = (tmp_path / "run_index.log").read_text(encoding="utf-8")
    assert log_text.count("CATALOG_INVALID_TIMESTAMP") == 2  # finished_at + started_at, no duplicadas


# --------------------------------------------------------------------------
# End-to-end: helpers para pasar por el pipeline real
# --------------------------------------------------------------------------

_HEADER_STATIC = {
    "ID": 1, "ID_BATCH": 63, "ID_RUN_STAGING": 60, "SOURCE_RUN_ID": 1, "ID_CONFIGURATION": 1,
    "VALUE_LEVEL_1": "Cat", "VALUE_LEVEL_2": None, "VALUE_LEVEL_3": None, "VALUE_LEVEL_4": None, "VALUE_LEVEL_5": None,
    "ML_STATUS": "OK", "SCP_STATUS": "OK", "HAS_SCP_CALCULATED": 1, "HAS_ML_CALCULATED": 1,
    "HAS_ML_EXCLUDED": 0, "ML_EXCLUSION_REASON": None, "SCP_NO_OUTPUT_REASON": None, "COPIED_AT": "2026-01-01",
    "ML_BEST_MODEL": "AutoETS", "ML_CLASSIFICATION": "smooth", "ML_TYPE": "smooth_ok",
    "SCP_BEST_MODEL": "x11 seasonal", "SCP_CLASSIFICATION": "smooth", "SERIES_CLASSIFICATION": "smooth",
    "COMPARISON_STATUS": "COMPARABLE", "HAS_BASE_CANDIDATE": 1,
}


def _write_client_csv(path: Path, id_client: int, *, history: float = 100.0, scp_err: float = 20.0, ml_err: float = 10.0, winner: str = "ML") -> None:
    row = dict(_HEADER_STATIC)
    row["ID_CLIENT"] = id_client
    for period in ALL_PERIODS:
        pcols = period_columns(period)
        n_months = 1 if period.startswith("M") else (3 if period in ("RECENT_3M", "OLDER_3M") else 6)
        h, se, me = history * n_months, scp_err * n_months, ml_err * n_months
        scp_wape, ml_wape = se / h, me / h
        row[pcols.total_history] = h
        row[pcols.scp_total_forecast] = h + se
        row[pcols.ml_total_forecast] = h + me
        row[pcols.scp_total_signed_error] = se
        row[pcols.ml_total_signed_error] = me
        row[pcols.scp_total_abs_error] = se
        row[pcols.ml_total_abs_error] = me
        row[pcols.scp_total_squared_error] = se ** 2
        row[pcols.ml_total_squared_error] = me ** 2
        row[pcols.positive_history_month_count] = n_months
        row[pcols.scp_mae] = se / n_months
        row[pcols.ml_mae] = me / n_months
        row[pcols.scp_rmse] = math.sqrt((se ** 2) / n_months)
        row[pcols.ml_rmse] = math.sqrt((me ** 2) / n_months)
        row[pcols.scp_wape] = scp_wape
        row[pcols.ml_wape] = ml_wape
        row[pcols.scp_bias] = se / h
        row[pcols.ml_bias] = me / h
        row[pcols.winner_method] = winner
        row[pcols.winner_model] = "AutoETS"
        row[pcols.finalist_method] = "SCP"
        row[pcols.finalist_model] = "x11 seasonal"
        row[pcols.winner_improvement_pct] = (scp_wape - ml_wape) / scp_wape * 100
    pd.DataFrame([row]).to_csv(path, index=False)


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------

def test_e2e_two_runs_both_appear_most_recent_first(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    assert pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "run_first"]) == 0
    assert pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "run_second"]) == 0

    html = (output_root / "index.html").read_text(encoding="utf-8")
    pos_first = html.index("run_first")
    pos_second = html.index("run_second")
    assert pos_second < pos_first  # el segundo (mas reciente) aparece primero en la tabla

    assert 'href="run_second/index.html">Abrir informe de esta ejecución' in html


def test_e2e_interrupted_run_does_not_appear_and_is_logged(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    def failing_publish(run_config):
        raise OSError("fallo simulado de publicacion")

    monkeypatch.setattr(pipeline, "publish_run", failing_publish)
    exit_code = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "broken_run"])
    assert exit_code == 1
    assert (output_root / ".broken_run.tmp").exists()

    result = rebuild_run_catalog(output_root)
    assert result.success is True
    assert result.entries_included == 0
    log_text = (output_root / "run_index.log").read_text(encoding="utf-8")
    assert ".broken_run.tmp" in log_text
    html = (output_root / "index.html").read_text(encoding="utf-8")
    assert 'href="broken_run/index.html"' not in html
    assert 'href=".broken_run.tmp/index.html"' not in html


def test_e2e_corrupt_manifest_does_not_appear_and_is_registered(tmp_path: Path):
    output_root = tmp_path / "runs"
    output_root.mkdir()
    _make_run_dir(output_root, "corrupt_run", manifest_text="{ this is not json")

    result = rebuild_run_catalog(output_root)
    assert result.success is True
    assert result.entries_included == 0
    assert result.entries_ignored == 1
    log_text = (output_root / "run_index.log").read_text(encoding="utf-8")
    assert "corrupt_run" in log_text
    assert "corrupto" in log_text
    html = (output_root / "index.html").read_text(encoding="utf-8")
    # aparece mencionado en el detalle de incidencias (motivo del descarte),
    # pero nunca como una fila/enlace real de ejecucion publicada
    assert 'href="corrupt_run/index.html"' not in html


def test_e2e_old_manifest_appears_with_nd_fields(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"
    assert pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "legacy_run"]) == 0

    # simula un manifest de una version anterior a la Fase 5C: se le quitan
    # los campos nuevos, preservando el resto (mismo patron que un manifest
    # real ya publicado antes de esta fase).
    manifest_path = output_root / "legacy_run" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["catalog_summary"]
    del manifest["manifest_schema_version"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = rebuild_run_catalog(output_root)
    assert result.success is True
    assert result.entries_included == 1
    html = (output_root / "index.html").read_text(encoding="utf-8")
    assert "legacy_run" in html
    assert "CATALOG_FIELDS_MISSING" in (output_root / "run_index.log").read_text(encoding="utf-8")


def test_e2e_rebuild_run_index_mode_does_not_process_csv_or_create_run(tmp_path: Path):
    output_root = tmp_path / "runs"
    _make_run_dir(output_root, "existing_run")
    non_existent_input = tmp_path / "does_not_exist_at_all"

    exit_code = pipeline.main([
        "--rebuild-run-index", "--output-root", str(output_root),
    ])
    assert exit_code == 0
    # ningun directorio nuevo aparte de catalog_assets/index.html/run_index.log
    children = {p.name for p in output_root.iterdir()}
    assert children == {"existing_run", "catalog_assets", "index.html", "run_index.log"}
    assert not non_existent_input.exists()


def test_e2e_incompatible_arguments_return_exit_2_and_do_not_touch_catalog(tmp_path: Path):
    output_root = tmp_path / "runs"
    _make_run_dir(output_root, "existing_run")
    rebuild_run_catalog(output_root)
    before = (output_root / "index.html").read_text(encoding="utf-8")

    exit_code = pipeline.main([
        "--rebuild-run-index", "--output-root", str(output_root), "--run-name", "whatever",
    ])
    assert exit_code == 2
    assert (output_root / "index.html").read_text(encoding="utf-8") == before


@pytest.mark.parametrize("flag", ["--input-dir", "--overwrite", "--copy-inputs", "--open-report"])
def test_e2e_rebuild_run_index_rejects_each_incompatible_flag(tmp_path: Path, flag: str):
    output_root = tmp_path / "runs"
    extra = [flag] if flag in ("--overwrite", "--copy-inputs", "--open-report") else [flag, str(tmp_path / "data")]
    exit_code = pipeline.main(["--rebuild-run-index", "--output-root", str(output_root), *extra])
    assert exit_code == 2


def test_e2e_normal_run_auto_updates_catalog_and_keeps_exit_code_0(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    exit_code = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "auto_run"])
    assert exit_code == 0
    assert (output_root / "index.html").exists()
    assert "auto_run" in (output_root / "index.html").read_text(encoding="utf-8")


def test_e2e_catalog_rebuild_failure_after_publish_does_not_invalidate_run(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    from src.run_catalog import RebuildResult
    monkeypatch.setattr(pipeline, "rebuild_run_catalog", lambda root: RebuildResult(success=False, error="fallo simulado"))

    exit_code = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "catalogfail_run"])
    assert exit_code == 0

    run_dir = output_root / "catalogfail_run"
    assert (run_dir / ".publish_complete").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["published"] is True
    assert manifest["status"] != "FAILED"
    log_text = (run_dir / "execution.log").read_text(encoding="utf-8")
    assert "fallo simulado" in log_text
    assert "CATALOG" in log_text


def test_e2e_run_without_csv_does_not_publish_or_add_catalog_row(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_root = tmp_path / "runs"

    exit_code = pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "empty_run"])
    assert exit_code == 1
    assert not (output_root / "empty_run").exists()
    assert not (output_root / "index.html").exists()  # nunca se intento reconstruir: el run nunca se publico


def test_e2e_overwrite_produces_single_catalog_row_with_latest_manifest_data(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_root = tmp_path / "runs"

    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204, winner="SCP", scp_err=10.0, ml_err=30.0)
    assert pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "overwrite_run"]) == 0

    (data_dir / "TA_FOV_SCP_ML_10204_Ok.csv").unlink()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204, winner="ML", scp_err=20.0, ml_err=10.0)
    assert pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "overwrite_run", "--overwrite",
    ]) == 0

    html = (output_root / "index.html").read_text(encoding="utf-8")
    # una unica FILA en la tabla de ejecuciones (el enlace "Abrir" de la
    # tabla es distinto del enlace "Abrir informe de esta ejecucion" de la
    # seccion "Ultima ejecucion", que tambien apunta aqui al ser el unico run)
    assert html.count('<a href="overwrite_run/index.html">Abrir</a>') == 1
    manifest = json.loads((output_root / "overwrite_run" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["catalog_summary"]["weighted_improvement_pct_6m"] > 0  # datos del SEGUNDO manifest (ML gana)


def test_e2e_copy_inputs_run_appears_and_catalog_does_not_reference_inputs_dir(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Ok.csv", 10204)
    output_root = tmp_path / "runs"

    exit_code = pipeline.main([
        "--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "copyinputs_run", "--copy-inputs",
    ])
    assert exit_code == 0
    html = (output_root / "index.html").read_text(encoding="utf-8")
    assert "copyinputs_run" in html
    assert "inputs/" not in html


def test_e2e_zero_valid_runs_produces_valid_catalog_with_correct_message(tmp_path: Path):
    output_root = tmp_path / "runs"
    exit_code = pipeline.main(["--rebuild-run-index", "--output-root", str(output_root)])
    assert exit_code == 0
    html = (output_root / "index.html").read_text(encoding="utf-8")
    assert "No hay ejecuciones publicadas" in html
    assert "ultima-ejecucion" in html  # la seccion se conserva (vacia), no desaparece


def test_e2e_moving_output_root_preserves_all_catalog_links(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10204_Alfa.csv", 10204)
    _write_client_csv(data_dir / "TA_FOV_SCP_ML_10461_Beta.csv", 10461, winner="SCP", scp_err=10.0, ml_err=30.0)
    output_root = tmp_path / "runs"
    assert pipeline.main(["--input-dir", str(data_dir), "--output-root", str(output_root), "--run-name", "movable_run"]) == 0

    moved_parent = tmp_path / "otra ubicacion ñ"
    moved_parent.mkdir()
    moved_root = moved_parent / "runs_copy"
    shutil.copytree(output_root, moved_root)

    problems = validate_html_links([moved_root / "index.html"], moved_root)
    assert problems == []
    moved_html = (moved_root / "index.html").read_text(encoding="utf-8")
    assert str(tmp_path) not in moved_html
    assert str(output_root) not in moved_html
    assert "C:\\" not in moved_html


# --------------------------------------------------------------------------
# Seguridad (escapado, sin URLs externas)
# --------------------------------------------------------------------------

def test_malicious_run_name_is_escaped_not_executed(tmp_path: Path):
    manifest = _minimal_manifest('<script>alert("x")</script>')
    _make_run_dir(tmp_path, "safe_folder_name", manifest=manifest)
    result = rebuild_run_catalog(tmp_path)
    assert result.success is True
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_catalog_html_has_no_forbidden_link_schemes(tmp_path: Path):
    _make_run_dir(tmp_path, "run_a")
    rebuild_run_catalog(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    for link in extract_local_links(html):
        lowered = link.lower()
        assert not lowered.startswith("javascript:")
        assert not lowered.startswith("data:")
        assert not lowered.startswith("http://")
        assert not lowered.startswith("https://")
        assert not lowered.startswith("//")
        assert "file:///" not in lowered
