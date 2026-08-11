"""
Log de procesamiento por cliente (processing_log_<CLIENTE>.txt).

Debe permitir entender que ha ocurrido sin abrir el codigo: timestamp,
archivo, cliente, batch, run, fase, periodo, filas, warnings, errores,
duracion, outputs generados.
"""

from __future__ import annotations

import pandas as pd

from src.client_analysis import ClientAnalysisResult
from src.quality_checks import Severity


def build_processing_log(
    result: ClientAnalysisResult, outputs_generated: list[str], duration_seconds: float,
) -> str:
    source = result.source
    lines: list[str] = []
    a = lines.append

    a(f"timestamp={pd.Timestamp.now().isoformat()}")
    a(f"archivo={source.file_name}")
    a(f"etiqueta_cliente={source.file_label}")
    a(f"display_name={source.display_name}")
    a(f"id_client={source.id_client}")
    a(f"id_batch={source.id_batch}")
    a(f"id_run_staging={source.id_run_staging}")
    a(f"source_run_id={source.source_run_id}")
    a(f"fase=Fase 3 - outputs individuales")
    a(f"fichero_valido={result.file_valid}")
    a(f"estado_global_cliente={result.status}")
    a(f"csv_reparado_comillas_dobladas={source.read_repaired}")
    a(f"filas_totales={source.n_rows}")
    a(f"series_candidatas={result.n_candidates}")
    a(f"duracion_segundos={duration_seconds:.3f}")
    a("")

    a("--- Periodos ---")
    for period, pr in result.periods.items():
        a(
            f"  periodo={period:<10} estado={pr.status:<8} candidatas={pr.n_candidates:<8} "
            f"comparables={pr.n_comparable:<8} pct_comparable={pr.pct_comparable:.1f}%"
        )
    a("")

    counts = result.quality.summary_counts()
    a(f"--- Chequeos de calidad: OK={counts['OK']} WARNING={counts['WARNING']} ERROR={counts['ERROR']} ---")
    for issue in result.quality.issues:
        if issue.severity == Severity.OK:
            continue
        a(f"  [{issue.severity.value}] {issue.code} (ambito={issue.scope}): {issue.message}")
    a("")

    a(f"--- Outputs generados ({len(outputs_generated)}) ---")
    for path in outputs_generated:
        a(f"  {path}")

    return "\n".join(lines)
