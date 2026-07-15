"""
Punto de entrada del pipeline FOV SCP vs ML.

Estado actual (Fase 4 - comparativa global y acabado final):
    1. Descubre automaticamente todos los CSV de data/.
    2. Valida cada CSV (legibilidad, columnas obligatorias, cliente unico,
       nombre vs ID_CLIENT, duplicados, cliente duplicado entre ficheros).
    3. Ejecuta el nucleo de analisis (Fase 2): cobertura, comparabilidad
       especifica por periodo, WAPE global ponderado, reduccion absoluta de
       error, mejora relativa, distribucion de ganadores.
    4. Genera, para cada cliente con fichero valido, en outputs/<CLIENTE>/:
       - fov_scp_ml_summary_<CLIENTE>.xlsx (14 pestanas)
       - fov_scp_ml_report_<CLIENTE>.md (18 secciones)
       - charts/{coverage,semester,quarters,monthly,models,classifications,impact_and_risk}/*.png
       - processing_log_<CLIENTE>.txt
    5. Los clientes sin ninguna serie comparable (p.ej. por
       NOT_COMPARABLE_MISSING_VALIDATION) generan igualmente sus outputs:
       las secciones de performance quedan vacias por diseno, nunca con
       metricas inventadas.
    6. Calcula la comparativa global entre todos los clientes con fichero
       valido (4 perspectivas: impacto ponderado, mejora por cliente, mejora
       por serie, impacto absoluto) y genera en outputs/global/:
       - fov_scp_ml_global_summary.xlsx (16 pestanas)
       - fov_scp_ml_global_report.md (21 secciones)
       - charts/{coverage,semester,quarters,monthly,clients,models,classifications,impact_and_risk}/*.png
    7. Genera outputs/execution_summary.md y outputs/execution_summary.xlsx
       (una fila por CSV descubierto, valido o no).
    8. Imprime un resumen de consola por cliente y un resumen global.

Ejecucion:
    python analysis_fov_scp_ml.py
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from src.charts import generate_client_charts
from src.client_analysis import ClientAnalysisResult, analyze_client
from src.excel_writer import build_client_workbook
from src.execution_summary import (
    build_execution_records,
    build_execution_summary_markdown,
    build_execution_summary_workbook,
)
from src.global_analysis import analyze_global
from src.global_charts import generate_global_charts
from src.global_excel_writer import build_global_workbook
from src.global_report_writer import build_global_report
from src.input_loader import ClientSource, load_client_sources
from src.logging_utils import build_processing_log
from src.quality_checks import Severity
from src.report_writer import build_client_report

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
GLOBAL_DIR = OUTPUT_DIR / "global"

SUMMARY_PERIODS = ["6M", "RECENT_3M", "OLDER_3M", "M1", "M6"]
MAX_ISSUES_SHOWN = 6


def _generate_client_outputs(result: ClientAnalysisResult) -> tuple[list[str], float]:
    """
    Genera Excel, Markdown, graficos y log de un cliente en outputs/<CLIENTE>/.
    Si el fichero no es valido, solo se escribe el log (sin inventar datos).
    Devuelve (rutas generadas relativas al repo, duracion en segundos).
    """
    source = result.source
    client_dir = OUTPUT_DIR / source.folder_name
    outputs_generated: list[str] = []

    start = time.perf_counter()
    if result.file_valid and source.dataframe is not None:
        client_dir.mkdir(parents=True, exist_ok=True)

        excel_path = client_dir / f"fov_scp_ml_summary_{source.folder_name}.xlsx"
        build_client_workbook(result, excel_path)
        outputs_generated.append(str(excel_path.relative_to(BASE_DIR)))

        report_path = client_dir / f"fov_scp_ml_report_{source.folder_name}.md"
        report_path.write_text(build_client_report(result), encoding="utf-8")
        outputs_generated.append(str(report_path.relative_to(BASE_DIR)))

        chart_paths = generate_client_charts(result, client_dir / "charts")
        outputs_generated += [str(Path(p).relative_to(BASE_DIR)) for p in chart_paths]
    else:
        client_dir.mkdir(parents=True, exist_ok=True)

    duration = time.perf_counter() - start
    log_path = client_dir / f"processing_log_{source.folder_name}.txt"
    log_path.write_text(build_processing_log(result, outputs_generated, duration), encoding="utf-8")
    outputs_generated.append(str(log_path.relative_to(BASE_DIR)))

    return outputs_generated, duration


def _generate_global_outputs(global_result) -> list[str]:
    outputs_generated: list[str] = []

    excel_path = GLOBAL_DIR / "fov_scp_ml_global_summary.xlsx"
    build_global_workbook(global_result, excel_path)
    outputs_generated.append(str(excel_path.relative_to(BASE_DIR)))

    report_path = GLOBAL_DIR / "fov_scp_ml_global_report.md"
    report_path.write_text(build_global_report(global_result), encoding="utf-8")
    outputs_generated.append(str(report_path.relative_to(BASE_DIR)))

    chart_paths = generate_global_charts(global_result, GLOBAL_DIR / "charts")
    outputs_generated += [str(Path(p).relative_to(BASE_DIR)) for p in chart_paths]

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
    print(f"\n=== {source.file_name} -> outputs/{source.folder_name}/ ===")
    print(f"  Etiqueta: {source.file_label} | ID esperado por nombre: {source.id_from_filename}")
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
    results: list[ClientAnalysisResult], all_outputs: dict[str, list[str]],
    global_result, global_outputs: list[str],
) -> None:
    print("\n" + "=" * 78)
    print("RESUMEN GLOBAL DE EJECUCION (Fase 4 - comparativa global y acabado final)")
    print("=" * 78)

    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    print(f"CSV descubiertos: {len(results)}")
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
        if not result.file_valid:
            print(f"  [OMITIDO] {result.source.file_name}: fichero no valido, solo se genero el log.")
            continue
        period_statuses = {p: pr.status for p, pr in result.periods.items()}
        n_error_periods = sum(1 for s in period_statuses.values() if s == "ERROR")
        n_periods = len(period_statuses)
        n_comparable_total = sum(pr.n_comparable for pr in result.periods.values())
        coverage_note = "" if n_comparable_total > 0 else " (sin series comparables en ningun periodo: caso valido de cobertura)"
        print(
            f"  [OK] {result.source.file_name}: estado_cliente={result.status}, "
            f"periodos_con_ERROR={n_error_periods}/{n_periods}{coverage_note}"
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
    print(f"  + {sum(1 for p in global_outputs if p.endswith('.png'))} grafico(s) PNG en outputs/global/charts/")

    print(
        "\nPendiente (fuera de alcance de este pipeline): commits (se proponen, no se ejecutan)."
    )


def main() -> int:
    print(f"Descubriendo CSV en: {DATA_DIR}")
    sources = load_client_sources(DATA_DIR)
    if not sources:
        print("ERROR: no se ha encontrado ningun CSV en data/.", file=sys.stderr)
        return 1
    print(f"CSV encontrados: {len(sources)}")

    results: list[ClientAnalysisResult] = []
    all_outputs: dict[str, list[str]] = {}
    durations: dict[str, float] = {}
    for source in sources:
        try:
            result = analyze_client(source)
            outputs_generated, duration = _generate_client_outputs(result)
        except Exception as exc:  # noqa: BLE001 - aislar errores por cliente
            print(f"\nERROR INESPERADO procesando {source.file_name}: {exc}", file=sys.stderr)
            traceback.print_exc()
            result = ClientAnalysisResult(source=source, file_valid=False, status="ERROR")
            outputs_generated, duration = [], 0.0
        results.append(result)
        all_outputs[source.file_name] = outputs_generated
        durations[source.file_name] = duration
        _print_client_summary(result, outputs_generated)

    try:
        global_result = analyze_global(results)
        global_outputs = _generate_global_outputs(global_result)
    except Exception as exc:  # noqa: BLE001 - la comparativa global no debe tumbar el proceso
        print(f"\nERROR INESPERADO en la comparativa global: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    records = build_execution_records(results, all_outputs, durations)
    exec_summary_md_path = OUTPUT_DIR / "execution_summary.md"
    exec_summary_xlsx_path = OUTPUT_DIR / "execution_summary.xlsx"
    exec_summary_md_path.write_text(build_execution_summary_markdown(records), encoding="utf-8")
    build_execution_summary_workbook(records, exec_summary_xlsx_path)

    _print_global_summary(results, all_outputs, global_result, global_outputs)
    print(f"\nResumen de ejecucion: {exec_summary_md_path.relative_to(BASE_DIR)}, {exec_summary_xlsx_path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
