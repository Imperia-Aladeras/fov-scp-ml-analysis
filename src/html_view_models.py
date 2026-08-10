"""
View models: transforman los resultados estructurados ya calculados
(ClientAnalysisResult, GlobalAnalysisResult, ExecutionRecord, RunConfig,
InputFileRecord) en diccionarios listos para los templates Jinja2 del
informe HTML (Fase 5B).

Este modulo NUNCA recalcula WAPE, MAE, RMSE, Bias, winners, mejoras,
cobertura ni impactos absolutos: solo lee campos ya calculados por
src/client_analysis.py, src/global_analysis.py, src/metrics.py y
src/models.py, y decide como presentarlos (texto, N/D, agrupacion,
verdicto textual a partir de un signo ya calculado). Toda conversion de
numero a texto pasa por src/html_formatters.py; los templates no formatean
numeros directamente.
"""

from __future__ import annotations

from src.html_formatters import (
    NA_TEXT,
    fmt_bool_si_no,
    fmt_datetime,
    fmt_duration_seconds,
    fmt_fraction_of,
    fmt_int,
    fmt_num,
    fmt_pct_fraction,
    fmt_pct_scaled,
    fmt_signed_pct,
    is_missing,
)
from src.periods import MONTHLY_PERIODS

MODEL_CLASSIFICATION_PERIOD = "6M"

# Etiquetas temporales EXACTAS exigidas para el texto visible del HTML (con
# guion en-raya "–"), separadas de src.periods.VISIBLE_LABELS: esa fuente
# de verdad compartida (guion normal "-") sigue alimentando Markdown/Excel
# sin cambios, para no alterar esos formatos ya aprobados.
TEMPORAL_LABELS_HTML = {
    "6M": "Semestre completo (M1–M6)",
    "RECENT_3M": "Primer trimestre del semestre (M1–M3)",
    "OLDER_3M": "Segundo trimestre del semestre (M4–M6)",
}

METHODOLOGY_NOTES = [
    "M1 es el mes cerrado más reciente; M6 es el mes más antiguo del semestre.",
    "RECENT_3M corresponde visualmente a M1–M3 (“Primer trimestre del semestre”).",
    "OLDER_3M corresponde visualmente a M4–M6 (“Segundo trimestre del semestre”).",
    "El ganador principal (WINNER_METHOD_*) se basa en WAPE y se usa siempre como fuente de verdad.",
    "MAE, RMSE y Bias son métricas de auditoría, no la métrica principal de comparación.",
    "El criterio exacto de empate relativo (relativeDiff < 0.0001) no está documentado en el "
    "repositorio y no se reconstruye.",
    "Los clientes sin performance calculable no se utilizan para concluir mejora o deterioro.",
    "Cobertura y performance son perspectivas diferentes: un cliente puede tener cobertura sin "
    "tener performance calculable.",
]


def improvement_verdict(pct) -> str:
    """Decide el verdicto textual a partir de un porcentaje YA CALCULADO (no recalcula nada)."""
    if is_missing(pct):
        return "sin datos"
    return "mejora" if pct > 0 else "no mejora"


# --------------------------------------------------------------------------
# 6.1 Cabecera de ejecucion
# --------------------------------------------------------------------------

def build_header_vm(
    run_config, git_commit, git_worktree_dirty, status, started_at, finished_at,
    n_clients_processed, n_clients_valid, batches_detected,
) -> dict:
    duration = (finished_at - started_at).total_seconds() if started_at and finished_at else None
    if git_worktree_dirty is True:
        worktree_label = "sucio (cambios sin commit)"
    elif git_worktree_dirty is False:
        worktree_label = "limpio"
    else:
        worktree_label = "N/D (Git no disponible o no es un repositorio)"
    return {
        "run_name": run_config.run_name_effective,
        "started_at": fmt_datetime(started_at),
        "finished_at": fmt_datetime(finished_at),
        "duration": fmt_duration_seconds(duration),
        "pipeline_version": run_config.pipeline_version,
        "git_commit_short": (git_commit[:12] if git_commit else NA_TEXT),
        "git_commit_full": git_commit or NA_TEXT,
        "git_worktree_label": worktree_label,
        "status": status,
        # n_clients_processed: numero de registros que representan un
        # cliente logico real (id_client is not None), ya filtrado por el
        # llamador. NI el numero de CSV fisicos (ver manifest["n_csv_discovered"]
        # en src/manifest.py para eso) NI el numero de filas del resumen: un
        # CSV con read_error genera una fila sin cliente asociado que no debe
        # contar aqui.
        "n_clients_processed": fmt_int(n_clients_processed),
        "n_clients_valid": fmt_int(n_clients_valid),
        "batches_detected": ", ".join(str(b) for b in batches_detected) if batches_detected else NA_TEXT,
        "copy_inputs": fmt_bool_si_no(run_config.copy_inputs),
    }


# --------------------------------------------------------------------------
# 6.2 Resumen ejecutivo
# --------------------------------------------------------------------------

def build_executive_summary_vm(global_result) -> dict:
    m6 = global_result.periods["6M"]
    stats = m6.client_improvement_stats
    n_total, n_evaluable, n_missing = stats.get("n_total"), stats.get("n_evaluable"), stats.get("n_missing")
    n_improved = stats.get("n_improved")
    totals = m6.reduction_totals
    verdict = improvement_verdict(m6.global_improvement_pct)

    conclusion = (
        f"ML {verdict} el WAPE global ponderado frente a SCP en el semestre completo "
        f"({fmt_signed_pct(m6.global_improvement_pct)}). "
        f"{fmt_fraction_of(n_improved, n_evaluable, 'clientes evaluables')} mejoran"
        + (f"; {fmt_int(n_missing)} cliente(s) no disponen de performance calculable" if n_missing else "")
        + f". A nivel de serie, ML gana en el {fmt_pct_scaled(m6.winner_counts.get('ML', {}).get('pct'))} "
        f"de las series comparables. Estas cifras responden preguntas distintas y no deben confundirse entre sí."
    )

    return {
        "n_clients_total": fmt_int(n_total),
        "n_clients_evaluable": fmt_int(n_evaluable),
        "n_clients_missing_performance": fmt_int(n_missing),
        "series_candidatas": fmt_int(m6.n_candidates_total),
        "series_comparables_6m": fmt_int(m6.n_comparable_total),
        "cobertura_global": fmt_pct_scaled(m6.pct_comparable_global),
        "wape_scp": fmt_pct_fraction(m6.scp_wape_global),
        "wape_ml": fmt_pct_fraction(m6.ml_wape_global),
        "mejora_global_ponderada": fmt_signed_pct(m6.global_improvement_pct),
        "mejora_global_verdict": verdict,
        "clientes_mejoran_fraction": fmt_fraction_of(n_improved, n_evaluable, "clientes evaluables"),
        "clientes_sin_performance_note": (
            f"{fmt_int(n_missing)} cliente(s) no disponen de performance calculable en 6M." if n_missing else None
        ),
        "pct_series_gana_ml": fmt_pct_scaled(m6.winner_counts.get("ML", {}).get("pct")),
        "reduccion_positiva_total": fmt_num(totals.get("REDUCCION_POSITIVA_TOTAL")),
        "deterioro_total_absoluto": fmt_num(totals.get("DETERIORO_TOTAL_ABSOLUTO")),
        "reduccion_neta": fmt_num(totals.get("REDUCCION_NETA")),
        "conclusion": conclusion,
    }


# --------------------------------------------------------------------------
# 6.3 Perspectivas diferenciadas (6M)
# --------------------------------------------------------------------------

def build_perspectives_vm(global_result) -> dict:
    m6 = global_result.periods["6M"]
    client_stats = m6.client_improvement_stats
    series_stats = m6.series_improvement_stats

    return {
        "impacto_ponderado": {
            "wape_scp": fmt_pct_fraction(m6.scp_wape_global),
            "wape_ml": fmt_pct_fraction(m6.ml_wape_global),
            "mejora": fmt_signed_pct(m6.global_improvement_pct),
            "historico_total": fmt_num(m6.history_sum),
            "pregunta": "¿Cuánto error total reduce ML sobre el volumen total analizado?",
        },
        "mejora_por_cliente": {
            "n_total": fmt_int(client_stats.get("n_total")),
            "n_evaluable": fmt_int(client_stats.get("n_evaluable")),
            "n_missing": fmt_int(client_stats.get("n_missing")),
            "media": fmt_signed_pct(client_stats.get("mean")),
            "mediana": fmt_signed_pct(client_stats.get("median")),
            "p25": fmt_signed_pct(client_stats.get("p25")),
            "p75": fmt_signed_pct(client_stats.get("p75")),
            "pct_mejoran": fmt_pct_scaled(client_stats.get("pct_improved")),
            "fraction_mejoran": fmt_fraction_of(client_stats.get("n_improved"), client_stats.get("n_evaluable"), "evaluables"),
            "pregunta": "¿Mejora ML en la mayoría de clientes? (cada cliente pesa igual)",
        },
        "mejora_por_serie": {
            "n_series": fmt_int(series_stats.get("count")),
            "media": fmt_signed_pct(series_stats.get("mean")),
            "mediana": fmt_signed_pct(series_stats.get("median")),
            "p25": fmt_signed_pct(series_stats.get("p25")),
            "p75": fmt_signed_pct(series_stats.get("p75")),
            "pregunta": "¿Mejora ML en la mayoría de series individuales?",
        },
        "frecuencia_victoria": {
            "pct_ml": fmt_pct_scaled(m6.winner_counts.get("ML", {}).get("pct")),
            "pct_scp": fmt_pct_scaled(m6.winner_counts.get("SCP", {}).get("pct")),
            "pct_tie": fmt_pct_scaled(m6.winner_counts.get("TIE", {}).get("pct")),
            "n_ml": fmt_int(m6.winner_counts.get("ML", {}).get("n")),
            "n_scp": fmt_int(m6.winner_counts.get("SCP", {}).get("n")),
            "n_tie": fmt_int(m6.winner_counts.get("TIE", {}).get("n")),
            "pregunta": "¿Con qué frecuencia gana cada método, serie a serie?",
        },
        "impacto_absoluto": {
            "reduccion_positiva_total": fmt_num(m6.reduction_totals.get("REDUCCION_POSITIVA_TOTAL")),
            "deterioro_total_absoluto": fmt_num(m6.reduction_totals.get("DETERIORO_TOTAL_ABSOLUTO")),
            "reduccion_neta": fmt_num(m6.reduction_totals.get("REDUCCION_NETA")),
            "pregunta": "¿La mejora está concentrada en pocos clientes de gran volumen?",
        },
        "cobertura": {
            "series_candidatas": fmt_int(m6.n_candidates_total),
            "series_comparables": fmt_int(m6.n_comparable_total),
            "pct_comparable": fmt_pct_scaled(m6.pct_comparable_global),
            "pregunta": "¿Qué porcentaje del universo candidato queda dentro de la comparación?",
        },
    }


def build_monthly_evolution_vm(global_result) -> list[dict]:
    rows = []
    for month in MONTHLY_PERIODS:
        gp = global_result.periods[month]
        rows.append({
            "periodo": month,
            "comparables": fmt_int(gp.n_comparable_total),
            "wape_scp": fmt_pct_fraction(gp.scp_wape_global),
            "wape_ml": fmt_pct_fraction(gp.ml_wape_global),
            "mejora": fmt_signed_pct(gp.global_improvement_pct),
            "pct_clientes_mejoran": fmt_pct_scaled(gp.client_improvement_stats.get("pct_improved")),
            "pct_series_gana_ml": fmt_pct_scaled(gp.winner_counts.get("ML", {}).get("pct")),
        })
    return rows


# --------------------------------------------------------------------------
# 6.5 Tabla de clientes
# --------------------------------------------------------------------------

def build_client_row_vm(result) -> dict:
    source = result.source
    m6 = result.periods.get("6M") if result.periods else None
    counts = result.quality.summary_counts()
    warnings_n = counts.get("WARNING", 0)
    errors_n = counts.get("ERROR", 0)

    invalido = not result.file_valid
    sin_performance = (not invalido) and (m6 is None or m6.n_comparable == 0)
    evaluable = (not invalido) and (m6 is not None and m6.n_comparable > 0)

    if invalido:
        status_flag, status_label = "invalido", "Inválido"
    elif sin_performance:
        status_flag, status_label = "sin_performance", "Sin performance"
    elif errors_n:
        status_flag, status_label = "con_errores", "Con errores"
    elif warnings_n:
        status_flag, status_label = "con_warnings", "Con warnings"
    else:
        status_flag, status_label = "evaluable", "Evaluable"

    return {
        "id_client": source.id_client if source.id_client is not None else NA_TEXT,
        "etiqueta": source.file_label,
        "folder_name": source.folder_name,
        "estado": result.status,
        "batches": ", ".join(str(b) for b in source.id_batch) if source.id_batch else NA_TEXT,
        "candidatas": fmt_int(result.n_candidates),
        "comparables_6m": fmt_int(m6.n_comparable) if m6 else NA_TEXT,
        "cobertura": fmt_pct_scaled(m6.pct_comparable) if m6 else NA_TEXT,
        "wape_scp": fmt_pct_fraction(m6.wape.get("scp_wape_global")) if m6 and m6.n_comparable else NA_TEXT,
        "wape_ml": fmt_pct_fraction(m6.wape.get("ml_wape_global")) if m6 and m6.n_comparable else NA_TEXT,
        "mejora": fmt_signed_pct(m6.wape.get("improvement_pct")) if m6 and m6.n_comparable else NA_TEXT,
        "warnings": warnings_n,
        "errors": errors_n,
        "status_flag": status_flag,
        "status_label": status_label,
        "has_page": True,  # toda fila de la tabla de clientes corresponde a un ClientAnalysisResult -> siempre tiene pagina
    }


def build_client_table_vm(client_results: list) -> list[dict]:
    return [build_client_row_vm(r) for r in client_results]


# --------------------------------------------------------------------------
# 6.6 Inventario de archivos
# --------------------------------------------------------------------------

def build_inventory_row_vm(record) -> dict:
    """
    `record` es un ExecutionRecord (src.execution_summary): ya combina el
    inventario de inputs con el resultado de analisis correlacionado (o su
    ausencia). No se inventa ID_CLIENT, etiqueta ni carpeta para un CSV que
    no produjo ClientAnalysisResult.
    """
    from src.execution_summary import INPUT_NOT_ANALYZED

    has_client_page = record.estado != INPUT_NOT_ANALYZED and bool(record.carpeta_salida)
    return {
        "archivo": record.archivo,
        "id_client": record.id_client if record.id_client is not None else NA_TEXT,
        "etiqueta": record.etiqueta or NA_TEXT,
        "estado": record.estado,
        "size_bytes": fmt_num(record.size_bytes),
        "sha256_short": (record.sha256[:12] + "…") if record.sha256 else NA_TEXT,
        "sha256_full": record.sha256 or NA_TEXT,
        "analysis_error": record.analysis_error,
        "log_generado": record.log_generado,
        "has_client_page": has_client_page,
        "folder_name": record.carpeta_salida.rstrip("/").split("/")[-1] if record.carpeta_salida else None,
    }


def build_inventory_table_vm(execution_records: list) -> list[dict]:
    return [build_inventory_row_vm(r) for r in execution_records]


# --------------------------------------------------------------------------
# 7. Pagina individual de cliente
# --------------------------------------------------------------------------

def _period_block_vm(pr, label: str) -> dict:
    if pr is None:
        return {"label": label, "has_data": False}
    if pr.n_comparable == 0:
        return {
            "label": label, "has_data": False,
            "n_candidates": fmt_int(pr.n_candidates), "n_comparable": 0,
            "explanation": (
                f"{fmt_int(pr.n_candidates)} series candidatas, pero ninguna es comparable en este periodo: "
                f"no hay universo evaluable suficiente para calcular performance."
            ),
        }
    return {
        "label": label, "has_data": True,
        "n_candidates": fmt_int(pr.n_candidates), "n_comparable": fmt_int(pr.n_comparable),
        "pct_comparable": fmt_pct_scaled(pr.pct_comparable),
        "wape_scp": fmt_pct_fraction(pr.wape.get("scp_wape_global")),
        "wape_ml": fmt_pct_fraction(pr.wape.get("ml_wape_global")),
        "mejora": fmt_signed_pct(pr.wape.get("improvement_pct")),
        "reduccion_absoluta": fmt_num(pr.abs_error_reduction_total),
        "historico_total": fmt_num(pr.wape.get("history_sum")),
        "pct_ml": fmt_pct_scaled(pr.winner_counts.get("ML", {}).get("pct")),
        "pct_scp": fmt_pct_scaled(pr.winner_counts.get("SCP", {}).get("pct")),
        "pct_tie": fmt_pct_scaled(pr.winner_counts.get("TIE", {}).get("pct")),
        "n_ml": fmt_int(pr.winner_counts.get("ML", {}).get("n")),
        "n_scp": fmt_int(pr.winner_counts.get("SCP", {}).get("n")),
        "n_tie": fmt_int(pr.winner_counts.get("TIE", {}).get("n")),
        "media_mejora_serie": fmt_signed_pct(pr.improvement_stats_all.get("mean")),
        "mediana_mejora_serie": fmt_signed_pct(pr.improvement_stats_all.get("median")),
    }


def _category_table_vm(table, top_n: int = 10) -> list[dict]:
    if table is None or table.empty:
        return []
    rows = []
    for _, r in table.head(top_n).iterrows():
        rows.append({
            "categoria": str(r["category"]),
            "n": fmt_int(r["n_comparable"]),
            "tasa_victoria_ml": fmt_pct_scaled(r["win_rate_ml_pct"]),
            "wape_scp": fmt_pct_fraction(r["scp_wape_agg"]),
            "wape_ml": fmt_pct_fraction(r["ml_wape_agg"]),
            "mejora_agregada": fmt_signed_pct(r["improvement_agg_pct"]),
            "mediana_mejora": fmt_signed_pct(r["median_improvement_pct"]),
            "muestra_pequena": bool(r["small_sample"]),
        })
    return rows


def _ranking_table_vm(df, value_col: str, signed: bool = True, top_n: int = 10) -> list[dict]:
    if df is None or df.empty:
        return []
    rows = []
    fmt_value = fmt_signed_pct if signed else fmt_num
    for _, r in df.head(top_n).iterrows():
        scp_wape_col = next((c for c in df.columns if "SCP_WAPE" in c), None)
        ml_wape_col = next((c for c in df.columns if c.startswith("ML_WAPE")), None)
        winner_col = next((c for c in df.columns if c.startswith("WINNER_METHOD")), None)
        rows.append({
            "id_configuration": str(r.get("ID_CONFIGURATION", NA_TEXT)),
            "valor": fmt_value(r[value_col]),
            "wape_scp": fmt_pct_fraction(r.get(scp_wape_col)) if scp_wape_col else NA_TEXT,
            "wape_ml": fmt_pct_fraction(r.get(ml_wape_col)) if ml_wape_col else NA_TEXT,
            "winner": str(r.get(winner_col, NA_TEXT)) if winner_col else NA_TEXT,
            "modelo_scp": str(r.get("SCP_BEST_MODEL", "") or NA_TEXT),
            "modelo_ml": str(r.get("ML_BEST_MODEL", "") or NA_TEXT),
            "clasificacion": str(r.get("SERIES_CLASSIFICATION", "") or NA_TEXT),
        })
    return rows


def build_client_page_vm(result, prev_client=None, next_client=None) -> dict:
    """
    prev_client / next_client: tuplas (etiqueta, folder_name) o None. El
    orden determinista (ID_CLIENT, etiqueta, nombre de fichero) lo decide
    el llamador (src/html_report.py), que tiene visibilidad de TODOS los
    clientes de la ejecucion.
    """
    from src.models import category_performance_table, top_absolute_impact, top_percentage_changes
    from src.periods import period_columns

    source = result.source
    counts = result.quality.summary_counts()

    vm = {
        "id_client": source.id_client if source.id_client is not None else NA_TEXT,
        "etiqueta": source.file_label,
        "file_name": source.file_name,
        "id_batch": ", ".join(str(b) for b in source.id_batch) if source.id_batch else NA_TEXT,
        "id_run_staging": ", ".join(str(b) for b in source.id_run_staging) if source.id_run_staging else NA_TEXT,
        "source_run_id": ", ".join(str(b) for b in source.source_run_id) if source.source_run_id else NA_TEXT,
        "estado": result.status,
        "file_valid": result.file_valid,
        "n_candidates": fmt_int(result.n_candidates),
        "warnings_count": counts.get("WARNING", 0),
        "errors_count": counts.get("ERROR", 0),
        "quality_issues": [
            {"severity": i.severity.value, "code": i.code, "message": i.message}
            for i in result.quality.issues if i.severity.value != "OK"
        ],
        "prev_client": prev_client,
        "next_client": next_client,
        "comparison_status_distribution": [
            {"status": k, "n": fmt_int(v), "pct": fmt_pct_scaled(v / result.n_candidates * 100 if result.n_candidates else float("nan"))}
            for k, v in sorted(result.comparison_status_distribution.items(), key=lambda kv: -kv[1])
        ],
    }

    if not result.file_valid:
        vm["kind"] = "invalid"
        vm["conclusion"] = (
            "Este fichero no es válido: no se ha calculado ningún periodo. Ver los errores de calidad "
            "de datos para el diagnóstico completo. No se muestran secciones estadísticas porque no existen "
            "datos válidos sobre los que calcularlas."
        )
        return vm

    m6 = result.periods.get("6M")
    recent = result.periods.get("RECENT_3M")
    older = result.periods.get("OLDER_3M")
    no_comparable_anywhere = bool(result.periods) and all(pr.n_comparable == 0 for pr in result.periods.values())

    vm["kind"] = "no_performance" if no_comparable_anywhere else "normal"
    vm["coverage_by_period"] = [
        {"periodo": p, "candidatas": fmt_int(pr.n_candidates), "comparables": fmt_int(pr.n_comparable),
         "pct_comparable": fmt_pct_scaled(pr.pct_comparable)}
        for p, pr in result.periods.items()
    ]
    vm["semestre"] = _period_block_vm(m6, TEMPORAL_LABELS_HTML["6M"])
    vm["primer_trimestre"] = _period_block_vm(recent, TEMPORAL_LABELS_HTML["RECENT_3M"])
    vm["segundo_trimestre"] = _period_block_vm(older, TEMPORAL_LABELS_HTML["OLDER_3M"])
    vm["monthly"] = [
        _period_block_vm(result.periods.get(f"M{i}"), f"M{i}") for i in range(1, 7)
    ]

    if no_comparable_anywhere:
        vm["conclusion"] = (
            f"No es posible concluir sobre la mejora de ML frente a SCP para este cliente: ninguna de sus "
            f"{fmt_int(result.n_candidates)} series candidatas es comparable en ningún periodo analizado. "
            f"Esto es un resultado de cobertura, no de performance: WAPE, mejora y winner no están "
            f"disponibles (N/D), no son cero."
        )
        return vm

    df = source.dataframe
    pcols_6m = period_columns(MODEL_CLASSIFICATION_PERIOD)
    mask_6m = m6.comparable_mask if m6 is not None else None
    has_6m_data = df is not None and mask_6m is not None and mask_6m.any()

    if has_6m_data:
        vm["ml_models"] = _category_table_vm(category_performance_table(df, pcols_6m, mask_6m, "ML_BEST_MODEL"))
        vm["scp_models"] = _category_table_vm(category_performance_table(df, pcols_6m, mask_6m, "SCP_BEST_MODEL"))
        vm["classifications"] = {
            col: _category_table_vm(category_performance_table(df, pcols_6m, mask_6m, col))
            for col in ("ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION", "SCP_CLASSIFICATION")
        }
        vm["classifications"] = {k: v for k, v in vm["classifications"].items() if v}
        top_improve, top_worsen = top_percentage_changes(df, pcols_6m, mask_6m, n=10)
        vm["top_improvements"] = _ranking_table_vm(top_improve, "ML_IMPROVEMENT_VS_SCP_PCT")
        vm["top_deteriorations"] = _ranking_table_vm(top_worsen, "ML_IMPROVEMENT_VS_SCP_PCT")
        top_reduction, top_increase = top_absolute_impact(df, pcols_6m, mask_6m, n=10)
        vm["top_abs_reductions"] = _ranking_table_vm(top_reduction, "ABS_ERROR_REDUCTION", signed=False)
        vm["top_abs_increases"] = _ranking_table_vm(top_increase, "ABS_ERROR_REDUCTION", signed=False)
    else:
        vm["ml_models"] = vm["scp_models"] = []
        vm["classifications"] = {}
        vm["top_improvements"] = vm["top_deteriorations"] = []
        vm["top_abs_reductions"] = vm["top_abs_increases"] = []

    n_status_excluded = result.comparison_status_distribution.get("NOT_COMPARABLE_ML_EXCLUDED", 0)
    n_flag_excluded = m6.n_ml_excluded if m6 is not None else 0
    vm["exclusions"] = {
        "n_status_excluded": fmt_int(n_status_excluded),
        "n_flag_excluded": fmt_int(n_flag_excluded),
        "ml_exclusion_reasons": [
            {"motivo": k, "n": fmt_int(v)}
            for k, v in sorted((m6.ml_exclusion_reason_counts if m6 else {}).items(), key=lambda kv: -kv[1])
        ],
    }

    limitations = [
        "El winner (WINNER_METHOD_*) se usa como fuente de verdad; el criterio exacto de empate relativo "
        "no está documentado y no se reconstruye.",
        "Modelos y clasificaciones se muestran únicamente para el semestre completo (6M).",
        "Los valores extremos de WAPE o de mejora relativa no se recortan silenciosamente en las "
        "estadísticas: se conservan y se señalan en los chequeos de calidad.",
        "Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.",
    ]
    vm["limitations"] = limitations

    if m6 is not None and m6.n_comparable:
        imp = m6.wape.get("improvement_pct")
        verdict = improvement_verdict(imp)
        vm["conclusion"] = (
            f"En el semestre completo, ML {verdict} el WAPE global ponderado frente a SCP "
            f"({fmt_signed_pct(imp)}). La mediana de mejora por serie es "
            f"{fmt_signed_pct(m6.improvement_stats_all.get('median'))} y ML gana en el "
            f"{fmt_pct_scaled(m6.winner_counts.get('ML', {}).get('pct'))} de las series comparables "
            f"({fmt_pct_scaled(m6.pct_comparable)} del universo candidato)."
        )
    else:
        vm["conclusion"] = "Sin series comparables en el semestre completo: no hay conclusión de performance que mostrar."

    return vm
