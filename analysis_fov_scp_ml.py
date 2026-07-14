"""
Punto de entrada del pipeline FOV SCP vs ML.

Estado actual (Fase 2 - nucleo de carga, validacion y metricas):
    1. Descubre automaticamente todos los CSV de data/.
    2. Valida cada CSV (legibilidad, columnas obligatorias, cliente unico,
       nombre vs ID_CLIENT, duplicados, cliente duplicado entre ficheros).
    3. Ejecuta el analisis de cobertura, comparabilidad especifica por
       periodo (M1..M6, RECENT_3M, OLDER_3M, 6M), WAPE global ponderado,
       reduccion absoluta de error, mejora relativa y distribucion de
       ganadores para cada cliente valido.
    4. Imprime un resumen de consola por cliente y un resumen global.

Pendiente (Fase 3 / Fase 4, no implementado todavia):
    - Excel, Markdown y graficos individuales por cliente en outputs/<CLIENTE>/.
    - Comparativa global entre clientes en outputs/global/.
    - execution_summary.md / execution_summary.xlsx en la raiz de outputs/.
    - README.md y requirements.txt actualizados.

Ejecucion:
    python analysis_fov_scp_ml.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from src.client_analysis import ClientAnalysisResult, analyze_client
from src.input_loader import ClientSource, load_client_sources
from src.periods import ALL_PERIODS
from src.quality_checks import Severity

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SUMMARY_PERIODS = ["6M", "RECENT_3M", "OLDER_3M", "M1", "M6"]
MAX_ISSUES_SHOWN = 8


def _print_period_line(result: ClientAnalysisResult, period: str) -> None:
    pr = result.periods.get(period)
    if pr is None:
        return
    wape = pr.wape
    scp_wape = wape.get("scp_wape_global")
    ml_wape = wape.get("ml_wape_global")
    improvement = wape.get("improvement_pct")

    def fmt_pct(x: float | None) -> str:
        if x is None or x != x:  # NaN check sin depender de numpy aqui
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


def _print_client_summary(result: ClientAnalysisResult) -> None:
    source: ClientSource = result.source
    print(f"\n=== {source.file_name} -> outputs/{source.folder_name}/ (Fase 3, pendiente) ===")
    print(f"  Etiqueta: {source.file_label} | ID esperado por nombre: {source.id_from_filename}")
    print(
        f"  Fichero valido: {result.file_valid} | Estado global del cliente: {result.status} | "
        f"CSV reparado (comillas dobladas): {source.read_repaired}"
    )

    if source.dataframe is None:
        print("  DataFrame no disponible: fichero aislado, no bloquea a los demas.")
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
                print(f"    ... y {remaining} incidencia(s) mas (ver detalle en Fase 3, processing_log por cliente).")
            break


def _print_global_summary(results: list[ClientAnalysisResult]) -> None:
    print("\n" + "=" * 78)
    print("RESUMEN GLOBAL DE EJECUCION (Fase 2 - nucleo, sin outputs finales)")
    print("=" * 78)

    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    print(f"CSV descubiertos: {len(results)}")
    for status, n in sorted(status_counts.items()):
        print(f"  {status}: {n}")

    total_rows = sum(r.source.n_rows for r in results)
    total_candidates = sum(r.n_candidates for r in results)
    total_comparable_6m = sum(
        r.periods["6M"].n_comparable for r in results if "6M" in r.periods
    )
    print(f"Filas totales procesadas: {total_rows}")
    print(f"Series candidatas totales: {total_candidates}")
    print(f"Series comparables en 6M (semestre completo): {total_comparable_6m}")

    print("\nComprobacion: ningun cliente con fichero valido queda inutilizado por completo")
    print("por una incidencia de periodo/fila localizada (el estado global nunca es ERROR")
    print("salvo que el propio fichero no sea valido):")
    for result in results:
        if not result.file_valid:
            continue
        period_statuses = {p: pr.status for p, pr in result.periods.items()}
        n_error_periods = sum(1 for s in period_statuses.values() if s == "ERROR")
        n_periods = len(period_statuses)
        usable = result.status != "ERROR" and n_error_periods < n_periods
        flag = "OK" if usable else "REVISAR"
        print(
            f"  [{flag}] {result.source.file_name}: estado_cliente={result.status}, "
            f"periodos_con_ERROR={n_error_periods}/{n_periods}"
        )

    print(
        "\nPendiente: Fase 3 (Excel/Markdown/graficos por cliente en outputs/<CLIENTE>/) "
        "y Fase 4 (comparativa global en outputs/global/, execution_summary, README)."
    )


def main() -> int:
    print(f"Descubriendo CSV en: {DATA_DIR}")
    sources = load_client_sources(DATA_DIR)
    if not sources:
        print("ERROR: no se ha encontrado ningun CSV en data/.", file=sys.stderr)
        return 1
    print(f"CSV encontrados: {len(sources)}")

    results: list[ClientAnalysisResult] = []
    for source in sources:
        try:
            result = analyze_client(source)
        except Exception as exc:  # noqa: BLE001 - aislar errores por cliente
            print(f"\nERROR INESPERADO procesando {source.file_name}: {exc}", file=sys.stderr)
            traceback.print_exc()
            result = ClientAnalysisResult(source=source, file_valid=False, status="ERROR")
        results.append(result)
        _print_client_summary(result)

    _print_global_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
