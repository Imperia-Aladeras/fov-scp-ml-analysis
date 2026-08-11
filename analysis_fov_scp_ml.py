"""
Punto de entrada del pipeline FOV SCP vs ML.

Estado actual (Fase 5A - pipeline reutilizable con ejecuciones aisladas y trazables):
    1. Parsea argumentos de linea de comandos (--input-dir, --output-root,
       --run-name, --overwrite, --copy-inputs), con valores por defecto que
       reproducen el comportamiento historico (data/ -> outputs/runs/<timestamp>/).
    2. Construye un RunConfig tipado: unica fuente de las rutas de la
       ejecucion, inyectada explicitamente a cada writer/generador.
    3. Construye un inventario inmutable de los CSV de entrada (nombre, ruta
       relativa, tamano, fecha de modificacion, SHA-256 de los bytes
       originales) ANTES de llamar a load_client_sources, para que el hash
       registrado corresponda exactamente a los bytes analizados.
    4. Con --copy-inputs: copia los CSV a <run>/inputs/, verifica que el
       SHA-256 de cada copia coincide con el original, y analiza desde la
       copia archivada. Sin --copy-inputs: analiza los originales y, al
       terminar, vuelve a comprobarlos; si alguno cambio durante la
       ejecucion, la ejecucion falla (INPUT_CHANGED_DURING_RUN) y no se
       publica.
    5. Descubre automaticamente todos los CSV de entrada, valida cada uno de
       forma aislada (un fichero invalido no bloquea a los demas) y ejecuta
       el nucleo de analisis por cliente y periodo.
    6. Genera, para cada cliente con fichero valido, en <run>/clients/<CLIENTE>/:
       - fov_scp_ml_summary_<CLIENTE>.xlsx (14 pestanas)
       - fov_scp_ml_report_<CLIENTE>.md (18 secciones)
       - charts/{coverage,semester,quarters,monthly,models,classifications,impact_and_risk}/*.png
       - processing_log_<CLIENTE>.txt
    7. Calcula la comparativa global (4 perspectivas) y la escribe en
       <run>/global/: fov_scp_ml_global_summary.xlsx (16 pestanas),
       fov_scp_ml_global_report.md (21 secciones) y sus graficos.
    8. Genera <run>/execution_summary.md, <run>/execution_summary.xlsx,
       <run>/manifest.json (metadata completa: inventario de inputs con
       SHA-256, procedencia Git incluyendo git_worktree_dirty, cifras
       agregadas, estado de publicacion) y <run>/execution.log.
    9. Publica la ejecucion de forma transaccional: se escribe primero en un
       directorio temporal oculto; solo se renombra al nombre final cuando
       el procesamiento termina correctamente, y solo se considera
       publicada de verdad cuando manifest.json, execution.log Y la marca
       durable `.publish_complete` se han escrito con exito (esa marca, no
       el contenido de manifest.json, es la unica senal fiable de
       publicacion completa). Si el proceso se interrumpe abruptamente en
       cualquier punto de esa transaccion, la siguiente ejecucion repara el
       estado (reconcile_interrupted_publication) sin perder nunca una
       ejecucion anterior valida. Cualquier fallo (de configuracion, de
       procesamiento, de preparacion del directorio o de publicacion) deja
       el manifest con status FAILED y el temporal intacto para
       diagnostico; nunca se publica un resultado a medias.
   10. Codigos de salida: 0 = completado (aunque existan warnings o clientes
       aislados); 1 = fallo durante el procesamiento, la preparacion del
       directorio o la publicacion; 2 = error de configuracion o argumentos
       detectable antes de tocar disco (incluye colision de ejecucion sin
       --overwrite).

Ejecucion:
    python analysis_fov_scp_ml.py
    python analysis_fov_scp_ml.py --input-dir <carpeta> --output-root <carpeta> --run-name <nombre> [--overwrite] [--copy-inputs]
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

from src.charts import generate_client_charts
from src.client_analysis import ClientAnalysisResult, analyze_client
from src.client_catalog import build_client_folder_name, load_client_catalog, resolve_client_name
from src.excel_writer import build_client_workbook
from src.execution_log import format_log_line
from src.execution_summary import (
    build_execution_records,
    build_execution_summary_markdown,
    build_execution_summary_workbook,
)
from src.global_analysis import analyze_global
from src.global_charts import generate_global_charts
from src.global_excel_writer import build_global_workbook
from src.global_report_writer import build_global_report
from src.html_report import generate_html_report, validate_run_links
from src.input_inventory import (
    InputFileRecord,
    InputIntegrityError,
    build_input_inventory,
    verify_copies_match_originals,
    verify_originals_unchanged,
)
from src.input_loader import ClientSource, load_client_sources_from_csv
from src.logging_utils import build_processing_log
from src.manifest import build_manifest, compute_sha256, detect_git_commit, detect_git_worktree_dirty, write_manifest
from src.quality_checks import Severity
from src.report_writer import build_client_report
from src.run_catalog import rebuild_run_catalog
from src.run_config import (
    RunConfig,
    RunNameError,
    build_arg_parser,
    build_rebuild_index_arg_parser,
    build_run_config,
    now_local,
)
from src.run_publish import publish_run, reconcile_interrupted_publication

BASE_DIR = Path(__file__).resolve().parent

SUMMARY_PERIODS = ["6M", "RECENT_3M", "OLDER_3M", "M1", "M6"]
MAX_ISSUES_SHOWN = 6


def _generate_client_outputs(result: ClientAnalysisResult, clients_dir: Path, relative_to: Path) -> tuple[list[str], float]:
    """
    Genera Excel, Markdown, graficos y log de un cliente en clients_dir/<CLIENTE>/.
    Si el fichero no es valido, solo se escribe el log (sin inventar datos).
    Devuelve (rutas generadas relativas a relative_to, duracion en segundos).
    """
    source = result.source
    client_dir = clients_dir / source.folder_name
    outputs_generated: list[str] = []

    start = time.perf_counter()
    if result.file_valid and source.dataframe is not None:
        client_dir.mkdir(parents=True, exist_ok=True)

        excel_path = client_dir / f"fov_scp_ml_summary_{source.folder_name}.xlsx"
        build_client_workbook(result, excel_path)
        outputs_generated.append(str(excel_path.relative_to(relative_to)))

        report_path = client_dir / f"fov_scp_ml_report_{source.folder_name}.md"
        report_path.write_text(build_client_report(result), encoding="utf-8")
        outputs_generated.append(str(report_path.relative_to(relative_to)))

        chart_paths = generate_client_charts(result, client_dir / "charts")
        outputs_generated += [str(Path(p).relative_to(relative_to)) for p in chart_paths]
    else:
        client_dir.mkdir(parents=True, exist_ok=True)

    duration = time.perf_counter() - start
    log_path = client_dir / f"processing_log_{source.folder_name}.txt"
    log_path.write_text(build_processing_log(result, outputs_generated, duration), encoding="utf-8")
    outputs_generated.append(str(log_path.relative_to(relative_to)))

    return outputs_generated, duration


def _generate_global_outputs(global_result, global_dir: Path, relative_to: Path) -> list[str]:
    outputs_generated: list[str] = []

    excel_path = global_dir / "fov_scp_ml_global_summary.xlsx"
    build_global_workbook(global_result, excel_path)
    outputs_generated.append(str(excel_path.relative_to(relative_to)))

    report_path = global_dir / "fov_scp_ml_global_report.md"
    report_path.write_text(build_global_report(global_result), encoding="utf-8")
    outputs_generated.append(str(report_path.relative_to(relative_to)))

    chart_paths = generate_global_charts(global_result, global_dir / "charts")
    outputs_generated += [str(Path(p).relative_to(relative_to)) for p in chart_paths]

    return outputs_generated


def _print_period_line(result: ClientAnalysisResult, period: str) -> None:
    pr = result.periods.get(period)
    if pr is None:
        return
    wape = pr.wape
    scp_wape = wape.get("scp_wape_global")
    ml_wape = wape.get("ml_wape_global")
    improvement = wape.get("improvement_pct")

    def fmt_pct(x: float | None) -> str:
        if x is None or x != x:
            return "n/d"
        return f"{x * 100:.1f}%"

    def fmt_signed_pct(x: float | None) -> str:
        if x is None or x != x:
            return "n/d"
        return f"{x:+.1f}%"

    print(
        f"    {period:<10} [{pr.status:<7}] candidatas={pr.n_candidates:>6} "
        f"comparables={pr.n_comparable:>6} ({pr.pct_comparable:5.1f}%)  "
        f"WAPE_SCP={fmt_pct(scp_wape):>8}  WAPE_ML={fmt_pct(ml_wape):>8}  "
        f"mejora={fmt_signed_pct(improvement):>8}  "
        f"ML/SCP/TIE={pr.winner_counts.get('ML', {}).get('n', 0)}/"
        f"{pr.winner_counts.get('SCP', {}).get('n', 0)}/"
        f"{pr.winner_counts.get('TIE', {}).get('n', 0)}"
    )


def _print_client_summary(result: ClientAnalysisResult, outputs_generated: list[str]) -> None:
    source: ClientSource = result.source
    print(f"\n=== {source.display_name} (ID_CLIENT={source.id_client}) -> clients/{source.folder_name}/ ===")
    print(f"  Etiqueta fichero: {source.file_label} | ID esperado por nombre: {source.id_from_filename}")
    print(
        f"  Fichero valido: {result.file_valid} | Estado global del cliente: {result.status} | "
        f"CSV reparado (comillas dobladas): {source.read_repaired}"
    )

    if source.dataframe is None:
        print("  DataFrame no disponible: fichero aislado, no bloquea a los demas. Solo se escribe el log.")
    else:
        print(
            f"  ID_CLIENT={source.id_client} | ID_BATCH={source.id_batch} | "
            f"ID_RUN_STAGING={source.id_run_staging} | SOURCE_RUN_ID={source.source_run_id}"
        )
        print(f"  Filas totales: {source.n_rows} | Series candidatas (HAS_BASE_CANDIDATE=1): {result.n_candidates}")
        if result.comparison_status_distribution:
            print(f"  Distribucion original de COMPARISON_STATUS: {result.comparison_status_distribution}")

    if result.periods:
        print("  Cobertura y WAPE global ponderado por periodo (muestra, [estado del periodo]):")
        for period in SUMMARY_PERIODS:
            _print_period_line(result, period)

    counts = result.quality.summary_counts()
    print(f"  Chequeos de calidad: OK={counts['OK']} WARNING={counts['WARNING']} ERROR={counts['ERROR']}")
    shown = 0
    for issue in result.quality.issues:
        if issue.severity == Severity.OK:
            continue
        print(f"    {issue}")
        shown += 1
        if shown >= MAX_ISSUES_SHOWN:
            remaining = counts["WARNING"] + counts["ERROR"] - shown
            if remaining > 0:
                print(f"    ... y {remaining} incidencia(s) mas (ver processing_log del cliente).")
            break

    print(f"  Outputs generados: {len(outputs_generated)}")
    for path in outputs_generated:
        if path.endswith((".xlsx", ".md", ".txt")):
            print(f"    {path}")
    n_charts = sum(1 for p in outputs_generated if p.endswith(".png"))
    if n_charts:
        print(f"    + {n_charts} grafico(s) PNG en charts/")


def _print_global_summary(
    results: list[ClientAnalysisResult], all_outputs: dict[int, list[str]],
    global_result, global_outputs: list[str],
) -> None:
    print("\n" + "=" * 78)
    print("RESUMEN GLOBAL DE EJECUCION (Fase 5A - pipeline reutilizable)")
    print("=" * 78)

    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    # len(results) es el numero de ClientAnalysisResult (clientes), no de CSV
    # fisicos: desde la Fase 3, un unico CSV fisico puede particionarse en
    # varios clientes, asi que nunca debe presentarse como "CSV descubiertos".
    print(f"Clientes procesados: {len(results)}")
    for status, n in sorted(status_counts.items()):
        print(f"  {status}: {n}")

    total_rows = sum(r.source.n_rows for r in results)
    total_candidates = sum(r.n_candidates for r in results)
    total_comparable_6m = sum(r.periods["6M"].n_comparable for r in results if "6M" in r.periods)
    total_files_written = sum(len(v) for v in all_outputs.values()) + len(global_outputs)
    total_charts = sum(1 for v in all_outputs.values() for p in v if p.endswith(".png"))
    total_charts += sum(1 for p in global_outputs if p.endswith(".png"))

    print(f"Filas totales procesadas: {total_rows}")
    print(f"Series candidatas totales: {total_candidates}")
    print(f"Series comparables en 6M (semestre completo): {total_comparable_6m}")
    print(f"Ficheros de salida escritos: {total_files_written} (incluye {total_charts} graficos PNG)")

    print("\nComprobacion: ningun cliente con fichero valido queda inutilizado por completo")
    print("por una incidencia de periodo/fila localizada:")
    for result in results:
        # filename ya no identifica a un cliente en particular (varios
        # clientes pueden compartir el mismo CSV fisico): ID_CLIENT es la
        # identidad inequivoca, filename queda solo como metadata.
        if not result.file_valid:
            print(
                f"  [OMITIDO] ID_CLIENT={result.source.id_client} | archivo={result.source.file_name}: "
                f"fichero no valido, solo se genero el log."
            )
            continue
        period_statuses = {p: pr.status for p, pr in result.periods.items()}
        n_error_periods = sum(1 for s in period_statuses.values() if s == "ERROR")
        n_periods = len(period_statuses)
        n_comparable_total = sum(pr.n_comparable for pr in result.periods.values())
        coverage_note = "" if n_comparable_total > 0 else " (sin series comparables en ningun periodo: caso valido de cobertura)"
        print(
            f"  [OK] ID_CLIENT={result.source.id_client} | archivo={result.source.file_name}: "
            f"estado_cliente={result.status}, periodos_con_ERROR={n_error_periods}/{n_periods}{coverage_note}"
        )

    m6 = global_result.periods["6M"]
    print("\nComparativa global (semestre completo, 6M):")
    print(f"  Clientes incluidos: {len(global_result.client_results)} | excluidos (fichero invalido): {len(global_result.invalid_results)}")
    print(f"  WAPE_SCP_GLOBAL={m6.scp_wape_global:.4f}  WAPE_ML_GLOBAL={m6.ml_wape_global:.4f}  "
          f"MEJORA_GLOBAL_PONDERADA={m6.global_improvement_pct:+.1f}%")
    n_improved = m6.client_improvement_stats.get('n_improved')
    n_evaluable = m6.client_improvement_stats.get('n_evaluable')
    n_missing = m6.client_improvement_stats.get('n_missing')
    print(f"  Mejora por cliente (peso igual): media={m6.client_improvement_stats.get('mean'):+.1f}%  "
          f"mediana={m6.client_improvement_stats.get('median'):+.1f}%  "
          f"% clientes que mejoran={m6.client_improvement_stats.get('pct_improved'):.1f}% "
          f"({n_improved}/{n_evaluable} evaluables; {n_missing} sin performance)")
    print(f"  Mejora por serie: media={m6.series_improvement_stats.get('mean'):+.1f}%  "
          f"mediana={m6.series_improvement_stats.get('median'):+.1f}%")
    print(f"  % series donde gana ML: {m6.winner_counts.get('ML', {}).get('pct'):.1f}%")

    print("\nOutputs globales generados:")
    for path in global_outputs:
        if path.endswith((".xlsx", ".md")):
            print(f"  {path}")
    print(f"  + {sum(1 for p in global_outputs if p.endswith('.png'))} grafico(s) PNG en global/charts/")


def _overall_status(results: list[ClientAnalysisResult]) -> str:
    for r in results:
        counts = r.quality.summary_counts()
        if not r.file_valid or counts.get("WARNING", 0) or counts.get("ERROR", 0):
            return "SUCCESS_WITH_WARNINGS"
    return "SUCCESS"


def _apply_metadata_changed_status(status: str, metadata_changed: list[str]) -> str:
    """
    Un cambio de SOLO metadata (mtime_ns, mismos bytes) durante la ejecucion
    no invalida ni bloquea la publicacion, pero el resultado nunca queda
    como SUCCESS puro: como minimo escala a SUCCESS_WITH_WARNINGS, para que
    quede una senal auditable (ver input_metadata_changed en manifest.json
    y el WARNING correspondiente en execution.log).
    """
    if metadata_changed and status == "SUCCESS":
        return "SUCCESS_WITH_WARNINGS"
    return status


def _write_execution_log(log_lines: list[str], path: Path) -> None:
    path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def _prepare_run_directories(run_config: RunConfig) -> None:
    run_config.clients_dir.mkdir(parents=True, exist_ok=True)
    run_config.global_dir.mkdir(parents=True, exist_ok=True)
    if run_config.copy_inputs:
        run_config.inputs_dir.mkdir(parents=True, exist_ok=True)
    run_config.run_config_path.write_text(
        json.dumps(run_config.to_run_config_dict(), indent=2, ensure_ascii=False), encoding="utf-8",
    )


def _handle_setup_failure(run_config: RunConfig, started_at: datetime, phase: str, exc: Exception) -> int:
    """
    Fallo de sistema de archivos durante la preparacion del directorio de
    ejecucion (reconcile_interrupted_publication, eliminacion del temporal
    con --overwrite, creacion de directorios, escritura de run_config.json). No
    oculta la excepcion original; si el temporal llego a existir, deja un
    manifest FAILED y un execution.log con traceback en el, de forma best
    effort. Nunca publica.
    """
    finished_at = now_local()
    tb = traceback.format_exc()
    print(f"\nERROR DE SISTEMA DE ARCHIVOS en fase {phase}: {exc}", file=sys.stderr)
    print(tb, file=sys.stderr)

    if run_config.run_dir_temp.exists():
        try:
            manifest = build_manifest(
                run_config, inventory=[], results=[], global_result=None, outputs_generated=[],
                started_at=started_at, finished_at=finished_at, status="FAILED",
                git_commit=detect_git_commit(BASE_DIR), git_worktree_dirty=detect_git_worktree_dirty(BASE_DIR),
                copy_inputs=run_config.copy_inputs, published=False,
                failure={"phase": phase, "error_type": type(exc).__name__, "error_message": str(exc)},
            )
            write_manifest(manifest, run_config.manifest_path)
        except OSError:
            pass
        try:
            with run_config.execution_log_path.open("a", encoding="utf-8") as f:
                f.write(format_log_line(phase, f"FALLO DE SISTEMA DE ARCHIVOS: {exc}") + "\n")
                f.write(tb + "\n")
        except OSError:
            pass
        print(f"Directorio temporal conservado para diagnostico en: {run_config.run_dir_temp}", file=sys.stderr)

    return 1


def _mark_publish_failure(run_config: RunConfig, exc: Exception) -> None:
    """
    Best-effort: deja constancia del fallo de publicacion sin ocultar la
    excepcion original. Se invoca SIEMPRE que publish_run() lance una
    excepcion; a esas alturas run_publish.publish_run ya ha restaurado el
    directorio temporal (integro, con su manifest posiblemente desactualizado
    -p.ej. `published=true` si el fallo ocurrio justo despues de patchear el
    manifest pero antes de escribir el log final-), por lo que aqui se
    fuerza el estado correcto de forma incondicional: FAILED, no publicado.
    """
    try:
        manifest = json.loads(run_config.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["status"] = "FAILED"
    manifest["published"] = False
    manifest["output_dir_working"] = str(run_config.run_dir_temp)
    manifest["output_dir_final"] = str(run_config.run_dir_final)
    manifest["failure"] = {"phase": "PUBLISH", "error_type": type(exc).__name__, "error_message": str(exc)}
    try:
        write_manifest(manifest, run_config.manifest_path)
    except OSError:
        pass
    try:
        with run_config.execution_log_path.open("a", encoding="utf-8") as f:
            f.write(format_log_line("PUBLISH", f"FALLO: {exc}") + "\n")
            f.write(traceback.format_exc() + "\n")
    except OSError:
        pass


def run_pipeline(run_config: RunConfig) -> int:
    """
    Orquesta una ejecucion completa dentro de run_config.run_dir_temp: no
    publica (eso lo hace el llamador solo si el resultado es 0). Devuelve el
    codigo de salida (0 completado, 1 fallo global, cero CSV, o inputs
    modificados durante la ejecucion).
    """
    started_at = run_config.started_at
    log_lines: list[str] = []
    phase = "SETUP"
    results: list[ClientAnalysisResult] = []
    global_result = None
    all_outputs: dict[int, list[str]] = {}
    outputs_generated: list[str] = []
    inventory: list[InputFileRecord] = []
    git_commit: str | None = None
    git_worktree_dirty: bool | None = None
    client_catalog_info: dict | None = None

    def log(message: str) -> None:
        log_lines.append(format_log_line(phase, message))

    try:
        log(
            f"input_dir={run_config.input_dir} output_root={run_config.output_root} "
            f"run_name={run_config.run_name_effective} copy_inputs={run_config.copy_inputs} "
            f"overwrite={run_config.overwrite}"
        )

        phase = "GIT_INFO"
        git_commit = detect_git_commit(BASE_DIR)
        git_worktree_dirty = detect_git_worktree_dirty(BASE_DIR)
        log(f"git_commit={git_commit} git_worktree_dirty={git_worktree_dirty}")
        if git_worktree_dirty:
            log(
                "WARNING: el working tree del repositorio tiene cambios sin commit "
                "(git_worktree_dirty=true); la ejecucion continua con normalidad."
            )

        phase = "INVENTORY"
        print(f"Descubriendo CSV en: {run_config.input_dir}")
        inventory = build_input_inventory(run_config.input_dir)
        log(f"csv_encontrados={len(inventory)}")
        print(f"CSV encontrados: {len(inventory)}")

        if not inventory:
            phase = "INVENTORY"
            log("ERROR: no se ha encontrado ningun CSV en input_dir.")
            finished_at = now_local()
            manifest = build_manifest(
                run_config, inventory, results, None, outputs_generated, started_at, finished_at, "FAILED",
                git_commit, git_worktree_dirty, run_config.copy_inputs, published=False,
                failure={
                    "phase": phase, "error_type": "NoCsvFoundError",
                    "error_message": "No se ha encontrado ningun CSV en input_dir.",
                },
                client_catalog_info=client_catalog_info,
            )
            write_manifest(manifest, run_config.manifest_path)
            _write_execution_log(log_lines, run_config.execution_log_path)
            print(f"ERROR: no se ha encontrado ningun CSV en {run_config.input_dir}.", file=sys.stderr)
            return 1

        if len(inventory) > 1:
            phase = "INVENTORY"
            log(f"ERROR: se han encontrado {len(inventory)} CSV en input_dir; se esperaba exactamente 1.")
            finished_at = now_local()
            manifest = build_manifest(
                run_config, inventory, results, None, outputs_generated, started_at, finished_at, "FAILED",
                git_commit, git_worktree_dirty, run_config.copy_inputs, published=False,
                failure={
                    "phase": phase, "error_type": "MultipleCsvFoundError",
                    "error_message": (
                        f"Se han encontrado {len(inventory)} CSV en input_dir; se esperaba exactamente 1."
                    ),
                },
                client_catalog_info=client_catalog_info,
            )
            write_manifest(manifest, run_config.manifest_path)
            _write_execution_log(log_lines, run_config.execution_log_path)
            print(
                f"ERROR: se han encontrado {len(inventory)} CSV en {run_config.input_dir}; "
                f"se esperaba exactamente 1.", file=sys.stderr,
            )
            return 1

        if run_config.copy_inputs:
            phase = "COPY_INPUTS"
            run_config.inputs_dir.mkdir(parents=True, exist_ok=True)
            n_copied = 0
            for record in inventory:
                if record.read_error is not None:
                    continue
                shutil.copy2(record.path, run_config.inputs_dir / record.name)
                n_copied += 1
            verify_copies_match_originals(inventory, run_config.inputs_dir)
            log(f"csv_copiados={n_copied} en {run_config.inputs_dir}; SHA-256 de cada copia verificado contra el original")

        phase = "DISCOVER"
        source_path = (
            run_config.inputs_dir / inventory[0].name if run_config.copy_inputs else inventory[0].path
        )
        sources = load_client_sources_from_csv(source_path)
        log(f"clientes_cargados={len(sources)} desde {source_path}")

        # Fase 5: el loader (src/input_loader.py) es deliberadamente agnostico
        # a catalogo/presentacion. La resolucion de display_name y el
        # folder_name tecnico ocurren aqui, una unica vez por run, fuera del
        # loader. load_client_catalog nunca lanza: un catalogo ausente o
        # corrupto degrada a {} con warning, y cada cliente cae al fallback
        # "Cliente <id>" de resolve_client_name, nunca bloquea el run.
        phase = "CLIENT_CATALOG_LOAD"
        client_catalog_path = BASE_DIR / "config" / "client-catalog.json"
        client_catalog, client_catalog_warning = load_client_catalog(client_catalog_path)
        if client_catalog_warning:
            log(f"WARNING CLIENT_CATALOG: {client_catalog_warning}")
        log(f"catalogo_clientes cargado: {len(client_catalog)} entrada(s) desde {client_catalog_path}")
        client_catalog_info = {
            "relative_path": str(client_catalog_path.relative_to(BASE_DIR)) if client_catalog_path.exists() else None,
            "sha256": compute_sha256(client_catalog_path) if client_catalog_path.exists() else None,
            "n_entries": len(client_catalog),
            "warning": client_catalog_warning,
        }

        phase = "DISCOVER"
        for source in sources:
            source.display_name = resolve_client_name(source.id_client, client_catalog)
            source.folder_name = build_client_folder_name(source.id_client, source.display_name)

        durations: dict[int, float] = {}
        phase = "CLIENT_PROCESSING"
        for source in sources:
            try:
                result = analyze_client(source)
                outputs, duration = _generate_client_outputs(result, run_config.clients_dir, run_config.run_dir_temp)
            except Exception as exc:  # noqa: BLE001 - aislar errores por cliente
                print(f"\nERROR INESPERADO procesando cliente {source.id_client}: {exc}", file=sys.stderr)
                traceback.print_exc()
                log(f"ERROR AISLADO cliente={source.id_client}: {exc}")
                result = ClientAnalysisResult(source=source, file_valid=False, status="ERROR")
                outputs, duration = [], 0.0
            results.append(result)
            all_outputs[source.id_client] = outputs
            durations[source.id_client] = duration
            counts = result.quality.summary_counts()
            log(
                f"cliente={source.id_client} estado={result.status} duracion={duration:.3f}s "
                f"warnings={counts.get('WARNING', 0)} errors={counts.get('ERROR', 0)}"
            )
            outputs_generated.extend(outputs)
            _print_client_summary(result, outputs)

        metadata_changed: list[str] = []
        if not run_config.copy_inputs:
            phase = "VERIFY_INPUTS_UNCHANGED"
            metadata_changed = verify_originals_unchanged(inventory)
            log("verificacion post-ejecucion: los CSV originales no han cambiado durante el procesamiento")
            if metadata_changed:
                log(
                    f"WARNING INPUT_METADATA_CHANGED: {len(metadata_changed)} CSV cambiaron su fecha de "
                    f"modificacion sin cambiar tamano ni SHA-256 (mismos bytes analizados): {metadata_changed}"
                )

        phase = "GLOBAL_ANALYSIS"
        global_result = analyze_global(results)
        global_outputs = _generate_global_outputs(global_result, run_config.global_dir, run_config.run_dir_temp)
        outputs_generated.extend(global_outputs)
        log("comparativa_global completada")

        phase = "EXECUTION_SUMMARY"
        records = build_execution_records(inventory, results, all_outputs, durations, clients_subdir="clients")
        run_config.execution_summary_md_path.write_text(build_execution_summary_markdown(records), encoding="utf-8")
        build_execution_summary_workbook(records, run_config.execution_summary_xlsx_path)
        outputs_generated.append(run_config.execution_summary_md_path.name)
        outputs_generated.append(run_config.execution_summary_xlsx_path.name)
        log("execution_summary generado")

        phase = "HTML_REPORT"
        finished_at = now_local()
        status = _apply_metadata_changed_status(_overall_status(results), metadata_changed)
        html_generated = generate_html_report(
            run_config=run_config, results=results, global_result=global_result,
            all_outputs=all_outputs, global_outputs=global_outputs, execution_records=records,
            started_at=started_at, finished_at=finished_at, status=status,
            git_commit=git_commit, git_worktree_dirty=git_worktree_dirty,
        )
        outputs_generated.extend(html_generated)
        log(f"informe_html generado: {len(html_generated)} fichero(s) (index.html, paginas de cliente, assets)")

        phase = "MANIFEST"
        outputs_generated.append("run_config.json")
        outputs_generated.append("manifest.json")
        outputs_generated.append("execution.log")
        manifest = build_manifest(
            run_config, inventory, results, global_result, outputs_generated, started_at, finished_at, status,
            git_commit, git_worktree_dirty, run_config.copy_inputs, published=False,
            input_metadata_changed=metadata_changed,
            client_catalog_info=client_catalog_info,
        )
        write_manifest(manifest, run_config.manifest_path)
        log("manifest generado")

        _write_execution_log(log_lines, run_config.execution_log_path)

        phase = "HTML_LINK_VALIDATION"
        link_problems = validate_run_links(run_config.run_dir_temp)
        if link_problems:
            raise RuntimeError(
                f"Validacion de enlaces del informe HTML fallida ({len(link_problems)} problema(s)):\n"
                + "\n".join(link_problems[:20])
            )
        print(f"Validacion de enlaces del informe HTML: {len(html_generated)} fichero(s), sin problemas.")

        _print_global_summary(results, all_outputs, global_result, global_outputs)
        print(
            f"\nResumen de ejecucion: execution_summary.md, execution_summary.xlsx "
            f"(dentro de {run_config.run_dir_temp})"
        )
        return 0

    except Exception as exc:  # noqa: BLE001 - fallo global, no se oculta
        finished_at = now_local()
        tb = traceback.format_exc()
        error_type = getattr(exc, "code", type(exc).__name__)
        log(f"FALLO GLOBAL ({error_type}): {exc}")
        log_lines.append(tb)
        try:
            _write_execution_log(log_lines, run_config.execution_log_path)
        except OSError:
            pass
        try:
            manifest = build_manifest(
                run_config, inventory, results, global_result, outputs_generated, started_at, finished_at, "FAILED",
                git_commit, git_worktree_dirty, run_config.copy_inputs, published=False,
                failure={"phase": phase, "error_type": error_type, "error_message": str(exc)},
                client_catalog_info=client_catalog_info,
            )
            write_manifest(manifest, run_config.manifest_path)
        except OSError:
            pass
        print(f"\nFALLO GLOBAL en fase {phase}: {exc}", file=sys.stderr)
        print(tb, file=sys.stderr)
        return 1


def _run_rebuild_index_mode(argv: list[str]) -> int:
    """
    Modo separado --rebuild-run-index (Fase 5C): NO descubre CSV, NO
    calcula clientes, NO crea ningun run ni directorio temporal de run, NO
    modifica ningun manifest.json ni .publish_complete existente. Solo
    reconstruye <output-root>/index.html y <output-root>/run_index.log a
    partir de las ejecuciones ya publicadas.
    """
    parser = build_rebuild_index_arg_parser(BASE_DIR)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse ya ha escrito a stderr el motivo (argumento incompatible
        # como --input-dir, --run-name, --overwrite, --copy-inputs o
        # --open-report: este parser dedicado ni siquiera los reconoce) y ha
        # llamado a sys.exit(2); se traduce a un codigo de salida normal en
        # vez de dejar que la excepcion escape de main().
        return exc.code if isinstance(exc.code, int) else 2

    output_root = Path(args.output_root).resolve()
    print(f"Reconstruyendo catalogo de ejecuciones (--rebuild-run-index) en: {output_root}")
    result = rebuild_run_catalog(output_root)
    if not result.success:
        print(f"ERROR: fallo al reconstruir el catalogo de ejecuciones: {result.error}", file=sys.stderr)
        return 1

    print(
        f"Catalogo reconstruido: {result.entries_included} ejecucion(es) incluida(s), "
        f"{result.entries_ignored} directorio(s) ignorado(s), {result.warnings_total} warning(s) de compatibilidad."
    )
    print(f"  {output_root / 'index.html'}")
    print(f"  {output_root / 'run_index.log'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if "--rebuild-run-index" in raw_argv:
        return _run_rebuild_index_mode(raw_argv)

    parser = build_arg_parser(BASE_DIR)
    args = parser.parse_args(argv)

    started_at = now_local()
    try:
        run_config = build_run_config(args, BASE_DIR, started_at=started_at)
    except RunNameError as exc:
        print(f"ERROR DE CONFIGURACION (run-name): {exc}", file=sys.stderr)
        return 2

    if not run_config.input_dir.is_dir():
        print(f"ERROR DE CONFIGURACION: --input-dir no existe o no es una carpeta: {run_config.input_dir}", file=sys.stderr)
        return 2

    setup_phase = "SETUP"
    try:
        setup_phase = "RECONCILE_INTERRUPTED_PUBLICATION"
        reconcile_interrupted_publication(run_config)

        setup_phase = "CHECK_TEMP_COLLISION"
        if run_config.run_dir_temp.exists():
            if not run_config.overwrite:
                print(
                    f"ERROR: ya existe un directorio temporal de una ejecucion anterior en "
                    f"{run_config.run_dir_temp} (probablemente interrumpida). No se elimina "
                    f"automaticamente. Usa --overwrite para eliminarlo, o elige otro --run-name.",
                    file=sys.stderr,
                )
                return 2
            setup_phase = "REMOVE_ORPHAN_TEMP"
            print(f"--overwrite: eliminando directorio temporal preexistente en {run_config.run_dir_temp}")
            shutil.rmtree(run_config.run_dir_temp)

        setup_phase = "CHECK_FINAL_COLLISION"
        if run_config.run_dir_final.exists() and not run_config.overwrite:
            print(
                f"ERROR: la ejecucion '{run_config.run_name_effective}' ya existe en "
                f"{run_config.run_dir_final}. Usa --overwrite para sustituirla.", file=sys.stderr,
            )
            return 2

        setup_phase = "PREPARE_DIRECTORIES"
        _prepare_run_directories(run_config)
    except Exception as exc:  # noqa: BLE001 - fallo de sistema de archivos, no se oculta
        return _handle_setup_failure(run_config, started_at, setup_phase, exc)

    exit_code = run_pipeline(run_config)
    if exit_code != 0:
        print(f"\nLa ejecucion NO se ha publicado. Directorio temporal conservado para diagnostico en: {run_config.run_dir_temp}")
        return exit_code

    try:
        publish_run(run_config)
    except Exception as exc:  # noqa: BLE001 - no se oculta el fallo de publicacion
        # publish_run() (src/run_publish.py) ya ha deshecho la publicacion y
        # restaurado el directorio temporal (y la ejecucion anterior, si la
        # habia) antes de propagar. Aqui solo queda dejar constancia en el
        # manifest/log del temporal y devolver el codigo de salida correcto:
        # nunca se devuelve 0 cuando la finalizacion queda incompleta.
        _mark_publish_failure(run_config, exc)
        print(f"\nERROR: fallo al publicar la ejecucion: {exc}", file=sys.stderr)
        traceback.print_exc()
        print(f"Directorio temporal conservado para diagnostico en: {run_config.run_dir_temp}")
        return 1

    print(f"\nEjecucion publicada en: {run_config.run_dir_final}")

    _try_rebuild_catalog_after_publish(run_config)

    if run_config.open_report:
        _try_open_report(run_config)

    return 0


def _append_best_effort_log(run_config: RunConfig, message: str, phase: str = "OPEN_REPORT") -> None:
    try:
        with (run_config.run_dir_final / "execution.log").open("a", encoding="utf-8") as f:
            f.write(format_log_line(phase, message) + "\n")
    except OSError:
        pass


def _try_rebuild_catalog_after_publish(run_config: RunConfig) -> None:
    """
    Reconstruccion automatica del catalogo historico de ejecuciones (Fase
    5C), POSTERIOR a la publicacion del run: se invoca aqui, cuando
    publish_run() ya ha terminado con exito. Es una operacion derivada
    sobre --output-root, fuera del directorio del run: nunca se anade al
    manifest del run (el catalogo vive en otro directorio) ni a su
    outputs_generated. Un fallo aqui NUNCA revierte el run ya publicado,
    nunca borra .publish_complete, nunca cambia el manifest a FAILED, y
    nunca afecta al codigo de salida del analisis (0): solo se avisa por
    consola y, de forma best-effort, en el execution.log ya publicado del
    run, indicando como reconstruir el catalogo manualmente.
    """
    result = rebuild_run_catalog(run_config.output_root)
    if result.success:
        print(f"Catalogo de ejecuciones actualizado en: {run_config.output_root / 'index.html'}")
        return
    message = (
        f"no se ha podido actualizar el catalogo de ejecuciones de {run_config.output_root} "
        f"({result.error}). El run ya publicado sigue siendo valido."
    )
    print(
        f"AVISO: {message} Para reconstruirlo manualmente:\n"
        f'  python analysis_fov_scp_ml.py --rebuild-run-index --output-root "{run_config.output_root}"',
        file=sys.stderr,
    )
    _append_best_effort_log(run_config, f"AVISO: {message}", phase="CATALOG")


def _try_open_report(run_config: RunConfig) -> None:
    """
    Accion de conveniencia POSTERIOR a la publicacion (Fase 5B, --open-report):
    solo se invoca aqui, cuando publish_run() ya ha terminado con exito y
    run_dir_final/index.html + .publish_complete existen. Un fallo al abrir
    el navegador (excepcion o False) nunca revierte la publicacion, nunca
    borra .publish_complete, nunca cambia el manifest ni el codigo de
    salida: la ejecucion ya quedo publicada correctamente antes de llegar
    aqui, esto es solo una comodidad posterior.
    """
    report_path = run_config.run_dir_final / "index.html"
    if not report_path.exists() or not run_config.publish_marker_path.exists():
        print(
            f"AVISO: --open-report solicitado pero el informe publicado no esta completo "
            f"todavia en {report_path}; no se abre el navegador.", file=sys.stderr,
        )
        return
    try:
        opened = webbrowser.open(report_path.resolve().as_uri())
    except Exception as exc:  # noqa: BLE001 - no debe invalidar una publicacion ya completa
        print(f"AVISO: no se ha podido abrir el navegador para --open-report: {exc}", file=sys.stderr)
        _append_best_effort_log(run_config, f"AVISO: excepcion al abrir el navegador: {exc}")
        return
    if not opened:
        print(
            f"AVISO: el navegador no se ha podido abrir automaticamente. Puedes abrir manualmente: {report_path}",
            file=sys.stderr,
        )
        _append_best_effort_log(run_config, "AVISO: webbrowser.open() devolvio False.")


if __name__ == "__main__":
    sys.exit(main())
