"""
Catalogo historico de ejecuciones (Fase 5C).

Genera, dentro de <output-root>/: index.html (indice operativo, estatico y
offline de las ejecuciones publicadas), run_index.log (registro del
escaneo) y catalog_assets/styles.css. Se apoya UNICAMENTE en lo que cada
ejecucion ya escribio en su propio directorio (manifest.json,
.publish_complete, index.html): nunca vuelve a leer CSV, nunca abre Excel,
nunca parsea Markdown, nunca analiza logs, nunca vuelve a ejecutar el
pipeline de clientes, y nunca compara estadisticamente unas ejecuciones con
otras.

Reconstruccion atomica de los TRES ficheros publicados (catalog_assets/
styles.css, run_index.log, index.html): todo el contenido nuevo se escribe
primero en ficheros `.tmp`; solo entonces se valida; solo si la validacion
pasa se sustituyen los ficheros definitivos (via os.replace, css -> log ->
index, en ese orden). Si CUALQUIER paso de la secuencia de sustitucion
falla, los pasos ya completados se deshacen (se restaura el contenido
anterior exacto, o se elimina el fichero si antes no existia) antes de
devolver el fallo: nunca queda el catalogo en un estado mixto entre
version antigua y nueva, y nunca quedan temporales huerfanos.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import jinja2

from src import run_catalog_models as cm
from src.execution_log import format_log_line
from src.html_formatters import encode_url_path
from src.html_report import TEMPLATES_DIR, validate_html_links
from src.manifest import MANIFEST_SCHEMA_VERSION

CATALOG_ASSETS_SRC = Path(__file__).resolve().parent.parent / "report_assets" / "catalog_styles.css"

# Nombres de carpeta reservados para el propio catalogo (Fase 5C): nunca se
# interpretan como intentos de run, ni se registran como "ignorados" (no
# son un run fallido ni sospechoso, son parte legitima del catalogo).
RESERVED_CATALOG_DIR_NAMES = {"catalog_assets"}

# Claves esperadas del schema ACTUAL de catalog_summary (ver src/manifest.py).
# Una clave presente con valor null es valida (metrica ausente para ESA
# ejecucion, p.ej. sin clientes evaluables); una clave que ni siquiera
# aparece en el dict es lo que dispara CATALOG_FIELDS_MISSING.
CATALOG_SUMMARY_KEYS: tuple[str, ...] = (
    "clients_total", "clients_evaluable_6m", "clients_without_performance_6m",
    "series_candidates_6m", "series_comparable_6m", "coverage_pct_6m",
    "wape_scp_6m", "wape_ml_6m", "weighted_improvement_pct_6m",
    "net_error_reduction_6m", "warnings_total", "errors_total",
)


@dataclass(frozen=True)
class CatalogRunEntry:
    folder_name: str
    manifest: dict
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IgnoredEntry:
    folder_name: str
    reason: str


@dataclass(frozen=True)
class CatalogScanResult:
    entries: list[CatalogRunEntry]
    ignored: list[IgnoredEntry]
    inspected_dirs: int


@dataclass(frozen=True)
class RebuildResult:
    success: bool
    entries_included: int = 0
    entries_ignored: int = 0
    warnings_total: int = 0
    error: str | None = None


def _catalog_summary_warnings(manifest: dict) -> list[str]:
    """
    Warnings de compatibilidad de schema para UN manifest, sin mutar nada.
    Distingue explicitamente: catalog_summary ausente (schema anterior a
    la Fase 5C); catalog_summary presente pero con claves concretas
    ausentes (schema parcialmente incompleto, se listan las claves); y
    manifest_schema_version superior al soportado por este catalogo (schema
    futuro, informativo).
    """
    warnings: list[str] = []
    schema_version = manifest.get("manifest_schema_version")
    catalog_summary = manifest.get("catalog_summary")

    if isinstance(schema_version, int) and schema_version > MANIFEST_SCHEMA_VERSION:
        warnings.append(
            f"CATALOG_SCHEMA_NEWER: manifest_schema_version={schema_version} es superior al "
            f"soportado por este catalogo ({MANIFEST_SCHEMA_VERSION}); puede haber campos nuevos "
            f"que este catalogo todavia no interpreta."
        )

    if not isinstance(catalog_summary, dict):
        warnings.append(
            "CATALOG_FIELDS_MISSING: manifest sin catalog_summary (version anterior a la Fase 5C, "
            "o bloque ausente); todas las metricas 6M de esta ejecucion se muestran como N/D."
        )
        return warnings

    missing_keys = [k for k in CATALOG_SUMMARY_KEYS if k not in catalog_summary]
    if missing_keys:
        warnings.append(
            "CATALOG_FIELDS_MISSING: faltan claves en catalog_summary: "
            f"{', '.join(missing_keys)}; se muestran como N/D."
        )
    return warnings


def scan_output_root(output_root: Path) -> CatalogScanResult:
    """
    Recorre los hijos DIRECTOS de output_root (nunca recursivo) y clasifica
    cada uno como run valido o ignorado, segun el criterio de la seccion 2
    de la especificacion. No modifica ni elimina ningun directorio.
    """
    entries: list[CatalogRunEntry] = []
    ignored: list[IgnoredEntry] = []

    if not output_root.exists():
        return CatalogScanResult(entries=entries, ignored=ignored, inspected_dirs=0)

    children = sorted((c for c in output_root.iterdir() if c.is_dir()), key=lambda p: p.name)

    for child in children:
        name = child.name

        if name.startswith("."):
            ignored.append(IgnoredEntry(name, "carpeta temporal o de backup (el nombre empieza por '.')"))
            continue
        if name in RESERVED_CATALOG_DIR_NAMES:
            continue

        if not (child / ".publish_complete").exists():
            ignored.append(IgnoredEntry(name, "sin marca .publish_complete"))
            continue

        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            ignored.append(IgnoredEntry(name, "sin manifest.json"))
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            ignored.append(IgnoredEntry(name, f"manifest.json corrupto o ilegible: {exc}"))
            continue
        if not isinstance(manifest, dict):
            ignored.append(IgnoredEntry(name, "manifest.json no contiene un objeto JSON"))
            continue

        if manifest.get("published") is not True:
            ignored.append(IgnoredEntry(name, f"published={manifest.get('published')!r} (no es true)"))
            continue
        if manifest.get("status") == "FAILED":
            ignored.append(IgnoredEntry(name, "status=FAILED"))
            continue
        if not (child / "index.html").exists():
            ignored.append(IgnoredEntry(name, "sin index.html"))
            continue

        entry_warnings: list[str] = []
        manifest_run_name = manifest.get("run_name")
        if manifest_run_name is not None and manifest_run_name != name:
            entry_warnings.append(
                f"CATALOG_RUN_NAME_MISMATCH: la carpeta se llama {name!r} pero "
                f"manifest['run_name'] es {manifest_run_name!r}"
            )
        entry_warnings.extend(_catalog_summary_warnings(manifest))

        entries.append(CatalogRunEntry(folder_name=name, manifest=manifest, warnings=tuple(entry_warnings)))

    return CatalogScanResult(entries=entries, ignored=ignored, inspected_dirs=len(children))


def _parse_timestamp(value) -> tuple[datetime | None, str | None]:
    """
    Devuelve (timestamp_zonificado, None) si `value` es un ISO 8601 valido
    Y con zona horaria; (None, motivo) si esta presente pero no se puede
    usar como fecha absoluta (no parseable, o "naive": sin zona horaria);
    (None, None) si esta simplemente ausente (eso no es, por si solo, una
    incidencia).
    """
    if not isinstance(value, str) or not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None, f"{value!r} no es un timestamp ISO 8601 valido"
    if dt.tzinfo is None:
        return None, f"{value!r} no incluye zona horaria (naive); no se usa como fecha absoluta"
    return dt, None


def _resolve_sort_timestamp(manifest: dict) -> tuple[datetime | None, list[str]]:
    """
    finished_at (valido y zonificado) tiene prioridad; started_at (valido y
    zonificado) es el fallback; si ninguno es utilizable, no hay timestamp
    (el run se ordena al final, nunca se excluye). Funcion PURA: no muta
    nada, devuelve los warnings nuevos para que el llamador decida como
    incorporarlos a una entrada inmutable.
    """
    warnings: list[str] = []

    finished, reason = _parse_timestamp(manifest.get("finished_at"))
    if finished is not None:
        return finished, warnings
    if reason:
        warnings.append(f"CATALOG_INVALID_TIMESTAMP: finished_at {reason}")

    started, reason = _parse_timestamp(manifest.get("started_at"))
    if started is not None:
        return started, warnings
    if reason:
        warnings.append(f"CATALOG_INVALID_TIMESTAMP: started_at {reason}")

    return None, warnings


def order_entries(entries: list[CatalogRunEntry]) -> list[CatalogRunEntry]:
    """
    Orden del catalogo (seccion 6): finished_at descendente; si falta,
    started_at descendente; como desempate deterministico, folder_name
    ascendente. Las entradas sin ningun timestamp valido se colocan al
    final, nunca excluidas. No muta ninguna CatalogRunEntry existente
    (dataclass frozen): cuando hace falta anadir un warning de timestamp,
    construye una entrada NUEVA en su lugar.
    """
    decorated: list[tuple[CatalogRunEntry, datetime | None]] = []
    for entry in entries:
        ts, extra_warnings = _resolve_sort_timestamp(entry.manifest)
        resolved_entry = (
            entry if not extra_warnings
            else CatalogRunEntry(entry.folder_name, entry.manifest, entry.warnings + tuple(extra_warnings))
        )
        decorated.append((resolved_entry, ts))

    def sort_key(item: tuple[CatalogRunEntry, datetime | None]):
        entry, ts = item
        has_ts = ts is not None
        return (not has_ts, -(ts.timestamp()) if has_ts else 0.0, entry.folder_name)

    decorated.sort(key=sort_key)
    return [entry for entry, _ts in decorated]


def _build_run_index_log(output_root: Path, scan: CatalogScanResult, ordered_entries: list[CatalogRunEntry]) -> str:
    lines: list[str] = []

    def log(message: str) -> None:
        lines.append(format_log_line("CATALOG", message))

    log(f"reconstruccion de catalogo iniciada en {output_root}")
    log(f"directorios inspeccionados={scan.inspected_dirs}")
    log(f"runs incluidos={len(ordered_entries)} runs ignorados={len(scan.ignored)}")
    for entry in ordered_entries:
        if entry.warnings:
            for w in entry.warnings:
                log(f"run={entry.folder_name} incluido con warning: {w}")
        else:
            log(f"run={entry.folder_name} incluido sin incidencias")
    for ig in scan.ignored:
        log(f"ignorado={ig.folder_name} motivo={ig.reason}")
    log("reconstruccion de catalogo completada")
    return "\n".join(lines) + "\n"


def _jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["encode_url_path"] = encode_url_path
    return env


def _read_bytes_if_exists(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _restore_or_remove(path: Path, previous_bytes: bytes | None) -> None:
    """Repone el contenido anterior exacto, o elimina el fichero si antes no existia."""
    if previous_bytes is not None:
        path.write_bytes(previous_bytes)
    else:
        path.unlink(missing_ok=True)


def _cleanup_tmp_files(paths: list[Path]) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def rebuild_run_catalog(output_root: Path) -> RebuildResult:
    """
    Reconstruye <output_root>/index.html, <output_root>/run_index.log y
    <output_root>/catalog_assets/styles.css de forma atomica conjunta. No
    descubre CSV, no calcula clientes, no crea ningun run, no modifica
    ningun manifest.json ni .publish_complete existente.

    Devuelve un RebuildResult; nunca lanza (cualquier fallo se captura y se
    reporta como RebuildResult(success=False, error=...), dejando los TRES
    ficheros del catalogo anterior -si existian- exactamente como estaban).
    """
    output_root = Path(output_root)

    try:
        output_root.mkdir(parents=True, exist_ok=True)

        scan = scan_output_root(output_root)
        ordered_entries = order_entries(scan.entries)

        assets_dir = output_root / "catalog_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        final_css = assets_dir / "styles.css"
        final_log = output_root / "run_index.log"
        final_index = output_root / "index.html"
        tmp_css = assets_dir / "styles.css.tmp"
        tmp_log = output_root / "run_index.log.tmp"
        tmp_index = output_root / "index.html.tmp"

        # Snapshot de lo que hay PUBLICADO ahora mismo, antes de escribir
        # ningun temporal: es lo que se restaura si algo falla mas adelante.
        previous_css = _read_bytes_if_exists(final_css)
        previous_log = _read_bytes_if_exists(final_log)
        previous_index = _read_bytes_if_exists(final_index)

        # 1. Genera TODO el contenido nuevo en ficheros temporales (nunca
        #    se toca ningun fichero definitivo todavia).
        tmp_css.write_bytes(CATALOG_ASSETS_SRC.read_bytes())

        rows = [
            cm.build_catalog_row_vm(entry.manifest, entry.folder_name, entry.warnings, f"{entry.folder_name}/index.html")
            for entry in ordered_entries
        ]
        last_run = rows[0] if rows else None
        all_run_warnings = [w for entry in ordered_entries for w in entry.warnings]
        ignored_rows = [{"folder_name": ig.folder_name, "reason": ig.reason} for ig in scan.ignored]
        incidents = cm.build_incidents_vm(len(ordered_entries), ignored_rows, all_run_warnings)

        html = _jinja_env().get_template("run_catalog.html").render(
            output_root_name=output_root.name, rows=rows, last_run=last_run, incidents=incidents,
        )
        tmp_index.write_text(html, encoding="utf-8")

        log_text = _build_run_index_log(output_root, scan, ordered_entries)
        tmp_log.write_text(log_text, encoding="utf-8")

        # 2. Valida ANTES de sustituir nada definitivo. index.html.tmp
        #    enlaza a run_index.log y a catalog_assets/styles.css, ninguno
        #    de los cuales existe todavia con su nombre definitivo (solo
        #    como .tmp): se reconocen como "pendientes" porque forman parte
        #    de esta MISMA transaccion y se publicaran junto al HTML.
        link_problems = validate_html_links(
            [tmp_index], output_root, pending_targets={final_log, final_css},
        )
        if link_problems:
            _cleanup_tmp_files([tmp_css, tmp_log, tmp_index])
            return RebuildResult(
                success=False, entries_included=len(ordered_entries), entries_ignored=len(scan.ignored),
                warnings_total=len(all_run_warnings),
                error="Validacion de enlaces del catalogo fallida: " + "; ".join(link_problems[:10]),
            )

        # 3. Sustituye los ficheros definitivos EN ORDEN (css -> log ->
        #    index, index en ULTIMO lugar). Si cualquier paso falla, se
        #    deshacen TODOS los pasos ya completados (se restaura el
        #    contenido anterior exacto, o se elimina si antes no existia)
        #    antes de devolver el fallo: nunca queda un estado mixto.
        completed: list[str] = []
        try:
            os.replace(tmp_css, final_css)
            completed.append("css")
            os.replace(tmp_log, final_log)
            completed.append("log")
            os.replace(tmp_index, final_index)
            completed.append("index")
        except OSError as exc:
            if "css" in completed:
                _restore_or_remove(final_css, previous_css)
            if "log" in completed:
                _restore_or_remove(final_log, previous_log)
            if "index" in completed:
                _restore_or_remove(final_index, previous_index)
            _cleanup_tmp_files([tmp_css, tmp_log, tmp_index])
            return RebuildResult(
                success=False, entries_included=len(ordered_entries), entries_ignored=len(scan.ignored),
                warnings_total=len(all_run_warnings),
                error=f"fallo al publicar el catalogo de forma atomica ({exc}); catalogo anterior restaurado",
            )

        return RebuildResult(
            success=True, entries_included=len(ordered_entries), entries_ignored=len(scan.ignored),
            warnings_total=len(all_run_warnings),
        )
    except Exception as exc:  # noqa: BLE001 - nunca se propaga: el catalogo es una operacion derivada
        for tmp_relative in ("index.html.tmp", "run_index.log.tmp", "catalog_assets/styles.css.tmp"):
            try:
                (output_root / tmp_relative).unlink(missing_ok=True)
            except OSError:
                pass
        return RebuildResult(success=False, error=f"{type(exc).__name__}: {exc}")
