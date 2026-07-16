"""
View models del catalogo historico de ejecuciones (Fase 5C).

Construidos UNICAMENTE a partir del `manifest.json` ya escrito en disco por
cada ejecucion (nunca de ClientAnalysisResult ni GlobalAnalysisResult): el
catalogo debe poder reconstruirse sin volver a ejecutar el pipeline de
clientes ni releer CSV/Excel/Markdown. Toda conversion de numero a texto
pasa por src/html_formatters.py, igual que en el informe HTML de Fase 5B;
un valor ausente en `catalog_summary` (manifest antiguo, o campo opcional
sin calcular) se muestra siempre como N/D, nunca como 0.
"""

from __future__ import annotations

from datetime import datetime

from src.html_formatters import (
    NA_TEXT,
    fmt_fraction_of,
    fmt_int,
    fmt_num,
    fmt_pct_fraction,
    fmt_pct_scaled,
    fmt_signed_pct,
)


def _format_iso_timestamp(value) -> str:
    if not isinstance(value, str) or not value:
        return NA_TEXT
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return NA_TEXT
    return dt.strftime("%d/%m/%Y %H:%M:%S %z")


def _worktree_label(value) -> str:
    if value is True:
        return "sucio"
    if value is False:
        return "limpio"
    return "N/D"


def _catalog_summary(manifest: dict) -> dict:
    summary = manifest.get("catalog_summary")
    return summary if isinstance(summary, dict) else {}


def build_catalog_row_vm(manifest: dict, folder_name: str, warnings: list[str], run_url: str) -> dict:
    """
    Una fila del catalogo (y, reutilizada tal cual, la seccion "Ultima
    ejecucion completada"). `run_url` ya es la ruta relativa (POSIX, SIN
    codificar) desde <output-root>/index.html hasta
    <folder_name>/index.html; el filtro encode_url_path se aplica en el
    template, igual que en el informe HTML de Fase 5B (dos fases:
    bookkeeping sin codificar, codificacion solo al renderizar).
    """
    summary = _catalog_summary(manifest)
    clients_total = summary.get("clients_total")
    clients_evaluable = summary.get("clients_evaluable_6m")
    schema_version = manifest.get("manifest_schema_version")
    git_commit = manifest.get("git_commit")

    return {
        "run_name": manifest.get("run_name") or folder_name,
        "folder_name": folder_name,
        "started_at": _format_iso_timestamp(manifest.get("started_at")),
        "finished_at": _format_iso_timestamp(manifest.get("finished_at")),
        "pipeline_version": manifest.get("pipeline_version") or NA_TEXT,
        "manifest_schema_version": str(schema_version) if schema_version is not None else NA_TEXT,
        "git_commit_short": (git_commit[:12] if git_commit else NA_TEXT),
        "git_worktree_label": _worktree_label(manifest.get("git_worktree_dirty")),
        "status": manifest.get("status") or NA_TEXT,
        "clients_total": fmt_int(clients_total),
        "clients_evaluable_6m": fmt_int(clients_evaluable),
        "clients_without_performance_6m": fmt_int(summary.get("clients_without_performance_6m")),
        "clients_evaluable_fraction": fmt_fraction_of(clients_evaluable, clients_total, "clientes"),
        "series_candidates_6m": fmt_int(summary.get("series_candidates_6m")),
        "series_comparable_6m": fmt_int(summary.get("series_comparable_6m")),
        "coverage_pct_6m": fmt_pct_scaled(summary.get("coverage_pct_6m")),
        "wape_scp_6m": fmt_pct_fraction(summary.get("wape_scp_6m")),
        "wape_ml_6m": fmt_pct_fraction(summary.get("wape_ml_6m")),
        "weighted_improvement_pct_6m": fmt_signed_pct(summary.get("weighted_improvement_pct_6m")),
        "net_error_reduction_6m": fmt_num(summary.get("net_error_reduction_6m")),
        "warnings_total": fmt_int(summary.get("warnings_total")),
        "errors_total": fmt_int(summary.get("errors_total")),
        "url": run_url,
        "row_warnings": list(warnings),
        "has_compat_warning": any(w.startswith("CATALOG_FIELDS_MISSING") for w in warnings),
    }


def build_incidents_vm(n_included: int, ignored_rows: list[dict], all_run_warnings: list[str]) -> dict:
    """
    `ignored_rows`: lista de dicts {"folder_name": ..., "reason": ...} ya
    construidos por el llamador (run_catalog.py), para no acoplar este
    modulo a sus dataclasses internas.
    """
    return {
        "n_included": fmt_int(n_included),
        "n_ignored": fmt_int(len(ignored_rows)),
        "n_warnings": fmt_int(len(all_run_warnings)),
        "ignored": ignored_rows,
        "warnings": list(all_run_warnings),
    }
