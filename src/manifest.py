"""
manifest.json: metadata completa y trazable de una ejecucion del pipeline.

`build_manifest` NO descubre CSV ni calcula hashes: recibe el inventario ya
construido (src/input_inventory.py) antes del parseo, para que el SHA-256
registrado corresponda exactamente a los bytes analizados. Incluye una
entrada por cada CSV del inventario, incluso si no pudo convertirse en un
ClientSource valido.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

from src.client_analysis import ClientAnalysisResult
from src.run_config import RunConfig

# Version del ESQUEMA de manifest.json (Fase 5C: catalogo historico de
# ejecuciones), deliberadamente independiente de pipeline_version (que versiona
# el propio pipeline de analisis, no la forma del manifiesto). Se incrementa
# solo cuando cambia la forma/semantica de los campos de manifest.json que el
# catalogo (src/run_catalog.py) necesita interpretar.
MANIFEST_SCHEMA_VERSION = 2


def compute_sha256(path: Path) -> str:
    """SHA-256 sobre los bytes originales del fichero (streaming por bloques)."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_git_commit(repo_dir: Path) -> str | None:
    """Commit HEAD actual, o None si Git no esta disponible o no es un repositorio. Nunca lanza."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True,
            text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def detect_git_worktree_dirty(repo_dir: Path) -> bool | None:
    """
    True si el working tree tiene cambios sin commit, False si esta limpio,
    None si Git no esta disponible o el directorio no es un repositorio.
    Nunca lanza. Usa `git status --porcelain`, que solo expone nombres de
    fichero y codigos de estado: nunca se almacena el diff ni contenido de
    los ficheros.
    """
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True,
            text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def _build_csv_entry(record, result: ClientAnalysisResult | None, copy_inputs: bool) -> dict:
    """
    Procedencia individual por CSV (nunca un booleano global aplicado a
    todos): un fichero con `read_error` no se copia ni se analiza nunca,
    aunque --copy-inputs este activo, y debe quedar como `not_analyzed`
    explicitamente, no como `copy`.
    """
    entry: dict = {
        "name": record.name,
        "relative_path": record.relative_path,
        "size_bytes": record.size_bytes, "modified_at": record.modified_at,
        "mtime_ns": record.mtime_ns, "sha256": record.sha256, "read_error": record.read_error,
        "id_client": None, "etiqueta": None, "filas": None, "estado": None,
        "warnings": None, "errors": None,
    }
    if record.read_error is not None:
        entry["analyzed_source"] = "not_analyzed"
        entry["analysis_status"] = "INPUT_READ_ERROR"
        entry["analysis_error"] = record.read_error
    elif result is not None:
        entry["analyzed_source"] = "copy" if copy_inputs else "original"
        entry["analysis_status"] = result.status
        entry["analysis_error"] = None
        counts = result.quality.summary_counts()
        entry.update({
            "id_client": result.source.id_client, "etiqueta": result.source.file_label,
            "filas": result.source.n_rows, "estado": result.status,
            "warnings": counts.get("WARNING", 0), "errors": counts.get("ERROR", 0),
        })
    else:
        entry["analyzed_source"] = "not_analyzed"
        entry["analysis_status"] = "NOT_PROCESSED"
        entry["analysis_error"] = None
    return entry


def _none_if_nan(x):
    """
    Serializa NaN como None (null en JSON): un valor ausente nunca debe
    llegar al manifest como el NaN interno de pandas/NumPy (json.dumps lo
    escribiria como el token no estandar `NaN`, y el catalogo debe poder
    distinguir "ausente" sin depender de esa extension no estandar).
    """
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def build_manifest(
    run_config: RunConfig,
    inventory: list,
    results: list[ClientAnalysisResult],
    global_result,
    outputs_generated: list[str],
    started_at: datetime,
    finished_at: datetime,
    status: str,
    git_commit: str | None,
    git_worktree_dirty: bool | None,
    copy_inputs: bool,
    published: bool,
    input_metadata_changed: list[str] = (),
    failure: dict | None = None,
) -> dict:
    by_filename = {r.source.file_name: r for r in results}
    csv_entries = [_build_csv_entry(record, by_filename.get(record.name), copy_inputs) for record in inventory]

    total_rows = sum(r.source.n_rows for r in results)
    total_candidates = sum(r.n_candidates for r in results)
    total_comparable_6m = sum(r.periods["6M"].n_comparable for r in results if "6M" in r.periods)
    total_warnings = sum(r.quality.summary_counts().get("WARNING", 0) for r in results)
    total_errors = sum(r.quality.summary_counts().get("ERROR", 0) for r in results)
    batches = sorted({b for r in results for b in r.source.id_batch})

    n_evaluable_6m = None
    n_missing_6m = None
    catalog_summary = None
    if global_result is not None and "6M" in global_result.periods:
        m6 = global_result.periods["6M"]
        m6_stats = m6.client_improvement_stats
        n_evaluable_6m = m6_stats.get("n_evaluable")
        n_missing_6m = m6_stats.get("n_missing")

        # "Resumen estable" para el catalogo historico de ejecuciones (Fase
        # 5C, src/run_catalog.py): unicamente reempaqueta valores YA
        # calculados por analyze_global() (src/global_analysis.py) sobre
        # 6M, mas los totales de warnings/errors ya sumados arriba. No
        # repite ningun calculo estadistico aqui.
        catalog_summary = {
            "clients_total": len(results),
            "clients_evaluable_6m": _none_if_nan(n_evaluable_6m),
            "clients_without_performance_6m": _none_if_nan(n_missing_6m),
            "series_candidates_6m": _none_if_nan(m6.n_candidates_total),
            "series_comparable_6m": _none_if_nan(m6.n_comparable_total),
            "coverage_pct_6m": _none_if_nan(m6.pct_comparable_global),
            "wape_scp_6m": _none_if_nan(m6.scp_wape_global),
            "wape_ml_6m": _none_if_nan(m6.ml_wape_global),
            "weighted_improvement_pct_6m": _none_if_nan(m6.global_improvement_pct),
            "net_error_reduction_6m": _none_if_nan(m6.reduction_totals.get("REDUCCION_NETA")),
            "warnings_total": total_warnings,
            "errors_total": total_errors,
        }

    manifest = {
        "run_name": run_config.run_name_effective,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "published": published,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "pipeline_version": run_config.pipeline_version,
        "git_commit": git_commit,
        "git_worktree_dirty": git_worktree_dirty,
        "input_dir": str(run_config.input_dir),
        "output_dir_final": str(run_config.run_dir_final),
        "output_dir_working": None if published else str(run_config.run_dir_temp),
        "n_csv_discovered": len(inventory),
        "n_clients_total": len(results),
        "n_clients_valid": sum(1 for r in results if r.file_valid),
        "n_clients_evaluable_6m": n_evaluable_6m,
        "n_clients_missing_performance_6m": n_missing_6m,
        "batches_detected": batches,
        "total_rows": total_rows,
        "series_candidatas": total_candidates,
        "series_comparables_6m": total_comparable_6m,
        "warnings_total": total_warnings,
        "errors_total": total_errors,
        "input_metadata_changed": list(input_metadata_changed),
        "outputs_generated": outputs_generated,
        "csv_files": csv_entries,
        "catalog_summary": catalog_summary,
    }
    if failure is not None:
        manifest["failure"] = failure
    return manifest


def write_manifest(manifest: dict, path: Path) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
