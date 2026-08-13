"""
Generacion del informe Markdown individual por cliente (18 secciones, ver
docs/analysis_requirements.md "Informe Markdown individual").

Cuando un cliente no tiene ninguna serie comparable en un periodo (o en
ningun periodo), las secciones de performance correspondientes lo indican
explicitamente en lugar de inventar metricas: es un caso valido de
cobertura/diagnostico, no un error.
"""

from __future__ import annotations

import math

import pandas as pd

from src.client_analysis import ClientAnalysisResult, PeriodResult
from src.models import (
    category_performance_table,
    top_absolute_impact,
    top_percentage_changes,
)
from src.periods import period_columns, visible_label

MODEL_CLASSIFICATION_PERIOD = "6M"


def _fmt_pct_fraction(x) -> str:
    """Formatea un WAPE (fraccion 0-1) como porcentaje."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:.1f}%"


def _fmt_pct_scaled(x) -> str:
    """Formatea un valor ya expresado en base 100 (mejora, cobertura, tasas)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:.1f}%"


def _fmt_signed_pct_scaled(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:+.1f}%"


def _fmt_num(x, decimals: int = 0) -> str:
    """Formatea con separador de miles '.' y decimal ',' (convencion es-ES)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    integer_part, _, decimal_part = f"{x:,.{decimals}f}".partition(".")
    integer_part = integer_part.replace(",", ".")
    return f"{integer_part},{decimal_part}" if decimal_part else integer_part


def _no_data_line(period_label: str) -> str:
    return (
        f"Sin series comparables en {period_label}: no hay metricas de performance que mostrar "
        f"(caso valido de cobertura, no se inventan datos)."
    )


def _period_wape_line(pr: PeriodResult) -> str:
    if pr.n_comparable == 0:
        return _no_data_line(pr.label)
    scp = _fmt_pct_fraction(pr.wape.get("scp_wape_global"))
    ml = _fmt_pct_fraction(pr.wape.get("ml_wape_global"))
    imp = _fmt_signed_pct_scaled(pr.wape.get("improvement_pct"))
    return (
        f"WAPE SCP={scp}, WAPE ML={ml}, mejora relativa ponderada={imp}, "
        f"reduccion absoluta de error={_fmt_num(pr.abs_error_reduction_total)}, "
        f"series comparables={_fmt_num(pr.n_comparable)}, "
        f"historico total={_fmt_num(pr.wape.get('history_sum'))}."
    )


def _winner_line(pr: PeriodResult) -> str:
    if pr.n_comparable == 0:
        return _no_data_line(pr.label)
    wc = pr.winner_counts
    return (
        f"ML gana {_fmt_num(wc.get('ML', {}).get('n', 0))} ({_fmt_pct_scaled(wc.get('ML', {}).get('pct'))}), "
        f"SCP gana {_fmt_num(wc.get('SCP', {}).get('n', 0))} ({_fmt_pct_scaled(wc.get('SCP', {}).get('pct'))}), "
        f"empate {_fmt_num(wc.get('TIE', {}).get('n', 0))} ({_fmt_pct_scaled(wc.get('TIE', {}).get('pct'))})."
    )


def _table_from_rows(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _category_table_lines(table: pd.DataFrame, top_n: int = 10) -> list[str]:
    if table.empty:
        return ["_Sin datos (sin series comparables)._"]
    headers = ["Categoria", "N", "Tasa victoria ML", "WAPE SCP", "WAPE ML", "Mejora agregada", "Mediana mejora", "% muestra pequena"]
    rows = []
    for _, r in table.head(top_n).iterrows():
        rows.append([
            str(r["category"]), _fmt_num(r["n_comparable"]),
            _fmt_pct_scaled(r["win_rate_ml_pct"]), _fmt_pct_fraction(r["scp_wape_agg"]),
            _fmt_pct_fraction(r["ml_wape_agg"]), _fmt_signed_pct_scaled(r["improvement_agg_pct"]),
            _fmt_signed_pct_scaled(r["median_improvement_pct"]), "si" if r["small_sample"] else "no",
        ])
    return _table_from_rows(headers, rows)


def _pareto_table_lines(table: pd.DataFrame, top_n: int = 5) -> list[str]:
    """
    Reutilizada tanto por el Pareto individual (seccion 9) como por el
    Pareto de series global (seccion 15 del informe global): ID_CLIENT
    siempre esta presente en la tabla (parte de `_ranking_columns`, incluida
    tanto a nivel individual -- constante, el propio cliente -- como a nivel
    global, donde es necesaria para desambiguar filas: dos clientes distintos
    pueden compartir el mismo ID_CONFIGURATION, ver global_pareto_series).
    """
    if table.empty:
        return ["_Sin series en este grupo._"]
    headers = ["Rank", "ID_CLIENT", "ID_CONFIGURATION", "Reduccion absoluta", "% del grupo", "% acumulado"]
    rows = []
    for _, r in table.head(top_n).iterrows():
        rows.append([
            _fmt_num(r["RANK"]), str(r.get("ID_CLIENT", "")), str(r.get("ID_CONFIGURATION", "")),
            _fmt_num(r["ABS_ERROR_REDUCTION"]), _fmt_pct_scaled(r["PCT_OF_GROUP"]), _fmt_pct_scaled(r["CUMULATIVE_PCT"]),
        ])
    return _table_from_rows(headers, rows)


def _pareto_concentration_line(group, label: str) -> str:
    s = group.summary
    if s.n_total == 0:
        return f"Sin series con {label} en 6M para este cliente."
    parts = [f"{_fmt_num(s.n_total)} series con {label}"]
    for pct, n_for in (("50", s.n_for_50), ("80", s.n_for_80), ("90", s.n_for_90)):
        if n_for is not None:
            parts.append(f"{_fmt_num(n_for)} explican el {pct}%")
    return ", ".join(parts) + f" del impacto total de {label} ({_fmt_num(s.total_impact)} unidades)."


def _ranking_table_lines(df: pd.DataFrame, value_col: str, value_fmt) -> list[str]:
    if df.empty:
        return ["_Sin datos (sin series comparables)._"]
    headers = ["ID_CONFIGURATION", value_col, "WAPE SCP", "WAPE ML", "Winner", "Modelo SCP", "Modelo ML", "Clasificacion"]
    rows = []
    for _, r in df.head(10).iterrows():
        scp_wape_col = next((c for c in df.columns if "SCP_WAPE" in c), None)
        ml_wape_col = next((c for c in df.columns if c.startswith("ML_WAPE")), None)
        winner_col = next((c for c in df.columns if c.startswith("WINNER_METHOD")), None)
        rows.append([
            str(r.get("ID_CONFIGURATION", "")), value_fmt(r[value_col]),
            _fmt_pct_fraction(r.get(scp_wape_col)) if scp_wape_col else "n/d",
            _fmt_pct_fraction(r.get(ml_wape_col)) if ml_wape_col else "n/d",
            str(r.get(winner_col, "")) if winner_col else "n/d",
            str(r.get("SCP_BEST_MODEL", "")), str(r.get("ML_BEST_MODEL", "")),
            str(r.get("SERIES_CLASSIFICATION", "")),
        ])
    return _table_from_rows(headers, rows)


def build_client_report(result: ClientAnalysisResult) -> str:
    source = result.source
    lines: list[str] = []
    a = lines.append

    m6 = result.periods.get("6M")
    recent = result.periods.get("RECENT_3M")
    older = result.periods.get("OLDER_3M")
    no_comparable_anywhere = bool(result.periods) and all(pr.n_comparable == 0 for pr in result.periods.values())

    a(f"# Informe individual SCP vs ML — {source.display_name}")
    a("")
    a(f"**Fecha del analisis:** {pd.Timestamp.now():%d/%m/%Y}")
    a(f"**Cliente:** {source.display_name} | ID_CLIENT={source.id_client} | Fichero: `{source.file_name}` (etiqueta: {source.file_label})")
    a(f"**Batch/Run:** ID_BATCH={source.id_batch} | ID_RUN_STAGING={source.id_run_staging} | SOURCE_RUN_ID={source.source_run_id}")
    a(f"**Estado global del cliente:** {result.status}")
    a("")
    a("---")
    a("")

    # 1. Resumen ejecutivo
    a("## 1. Resumen ejecutivo")
    a("")
    if no_comparable_anywhere:
        a(
            f"Este cliente tiene **{_fmt_num(result.n_candidates)} series candidatas**, pero "
            f"**ninguna es comparable** en ningun periodo analizado. No es un error del pipeline: "
            f"es un caso valido de cobertura que requiere diagnostico (ver seccion 2). No se reportan "
            f"metricas de performance porque no existen series validas sobre las que calcularlas."
        )
    elif m6 is not None:
        a(
            f"Sobre **{_fmt_num(result.n_candidates)} series candidatas**, **{_fmt_num(m6.n_comparable)} "
            f"({_fmt_pct_scaled(m6.pct_comparable)})** son comparables en el semestre completo (6M). {_period_wape_line(m6)}"
        )
        a("")
        a(f"Frecuencia de victoria en 6M: {_winner_line(m6)}")
    a("")
    a("---")
    a("")

    # 2. Cobertura
    a("## 2. Cobertura")
    a("")
    a(f"Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **{_fmt_num(result.n_candidates)}**.")
    a("")
    a("Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):")
    a("")
    a("\n".join(_table_from_rows(["COMPARISON_STATUS", "N", "% sobre candidatas"], [
        [status, _fmt_num(n), _fmt_pct_scaled(n / result.n_candidates * 100 if result.n_candidates else float("nan"))]
        for status, n in sorted(result.comparison_status_distribution.items(), key=lambda kv: -kv[1])
    ])))
    a("")
    if m6 is not None:
        a(
            f"Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): "
            f"**{_fmt_num(m6.n_ml_excluded)}** ({_fmt_pct_scaled(m6.pct_ml_excluded)} sobre candidatas)."
        )
        if m6.ml_exclusion_reason_counts:
            a("")
            a("Motivos de exclusion ML:")
            a("")
            a("\n".join(_table_from_rows(["Motivo", "N"], [
                [k, _fmt_num(v)] for k, v in sorted(m6.ml_exclusion_reason_counts.items(), key=lambda kv: -kv[1])
            ])))
    a("")
    a("Cobertura por periodo:")
    a("")
    a("\n".join(_table_from_rows(
        ["Periodo", "Candidatas", "Comparables", "% comparable"],
        [
            [p, _fmt_num(pr.n_candidates), _fmt_num(pr.n_comparable), _fmt_pct_scaled(pr.pct_comparable)]
            for p, pr in result.periods.items()
        ],
    )))
    a("")
    a("---")
    a("")

    # 3. Semestre completo
    a("## 3. Semestre completo (6M)")
    a("")
    if m6 is not None:
        a(_period_wape_line(m6))
        a("")
        a(f"Frecuencia de victoria: {_winner_line(m6)}")
    a("")
    a("---")
    a("")

    # 4. Primer trimestre
    a(f"## 4. {visible_label('RECENT_3M')}")
    a("")
    if recent is not None:
        a(_period_wape_line(recent))
        a("")
        a(f"Frecuencia de victoria: {_winner_line(recent)}")
    a("")
    a("---")
    a("")

    # 5. Segundo trimestre
    a(f"## 5. {visible_label('OLDER_3M')}")
    a("")
    if older is not None:
        a(_period_wape_line(older))
        a("")
        a(f"Frecuencia de victoria: {_winner_line(older)}")
    a("")
    a("---")
    a("")

    # 6. Comparacion entre trimestres
    a("## 6. Comparacion entre trimestres")
    a("")
    if recent is not None and older is not None and recent.n_comparable and older.n_comparable:
        imp_r = recent.wape.get("improvement_pct")
        imp_o = older.wape.get("improvement_pct")
        sign_change = (
            "cambia de signo entre trimestres" if (imp_r is not None and imp_o is not None and not math.isnan(imp_r) and not math.isnan(imp_o) and imp_r * imp_o < 0)
            else "mantiene el mismo signo en ambos trimestres"
        )
        a(
            f"Mejora ponderada en {visible_label('RECENT_3M')}: {_fmt_signed_pct_scaled(imp_r)}. "
            f"Mejora ponderada en {visible_label('OLDER_3M')}: {_fmt_signed_pct_scaled(imp_o)}. "
            f"La mejora {sign_change}."
        )
        a("")
        a(
            f"% victorias ML: {_fmt_pct_scaled(recent.winner_counts.get('ML', {}).get('pct'))} (primer trimestre) "
            f"vs {_fmt_pct_scaled(older.winner_counts.get('ML', {}).get('pct'))} (segundo trimestre)."
        )
    else:
        a("No hay datos suficientes en ambos trimestres para compararlos (alguno sin series comparables).")
    a("")
    a("---")
    a("")

    # 7. Evolucion mensual
    a("## 7. Evolucion mensual")
    a("")
    months = [result.periods.get(f"M{i}") for i in range(1, 7)]
    if any(pr is not None and pr.n_comparable for pr in months):
        a("\n".join(_table_from_rows(
            ["Mes", "Comparables", "WAPE SCP", "WAPE ML", "Mejora relativa", "% ML", "% SCP", "% Empate"],
            [
                [
                    f"M{i}", _fmt_num(pr.n_comparable), _fmt_pct_fraction(pr.wape.get("scp_wape_global")),
                    _fmt_pct_fraction(pr.wape.get("ml_wape_global")), _fmt_signed_pct_scaled(pr.wape.get("improvement_pct")),
                    _fmt_pct_scaled(pr.winner_counts.get("ML", {}).get("pct")),
                    _fmt_pct_scaled(pr.winner_counts.get("SCP", {}).get("pct")),
                    _fmt_pct_scaled(pr.winner_counts.get("TIE", {}).get("pct")),
                ]
                for i, pr in enumerate(months, start=1) if pr is not None
            ],
        )))
        m1, m6mo = months[0], months[5]
        if m1 and m6mo and m1.n_comparable and m6mo.n_comparable:
            a("")
            a(
                f"M1 (mas reciente) vs M6 (mas antiguo): mejora {_fmt_signed_pct_scaled(m1.wape.get('improvement_pct'))} "
                f"vs {_fmt_signed_pct_scaled(m6mo.wape.get('improvement_pct'))}. No se concluye estabilidad ni tendencia "
                f"solo a partir de dos puntos; ver la tabla completa para el patron mes a mes."
            )
    else:
        a("Sin series comparables en ningun mes.")
    a("")
    a("---")
    a("")

    # 8. Frecuencia de victoria
    a("## 8. Frecuencia de victoria")
    a("")
    if m6 is not None:
        a(f"Semestre completo: {_winner_line(m6)}")
    a("")
    a(
        "La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del "
        "impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente "
        "que ML gane en la mayoria de series, ni al reves."
    )
    a("")
    a("---")
    a("")

    # 9. Impacto absoluto
    a("## 9. Impacto absoluto")
    a("")
    if m6 is not None and m6.n_comparable:
        a(
            f"Reduccion absoluta de error en 6M: **{_fmt_num(m6.abs_error_reduction_total)}** unidades de "
            f"historico (positivo = ML reduce error total frente a SCP)."
        )
        if m6.pareto is not None:
            pareto = m6.pareto
            a("")
            a(
                "**Pareto de concentracion del impacto absoluto (6M).** Mejora y deterioro se calculan "
                "por separado, cada uno con su propio denominador (nunca se mezclan signos)."
            )
            a("")
            a(_pareto_concentration_line(pareto.improvement, "mejora"))
            a("")
            a(_pareto_concentration_line(pareto.deterioration, "deterioro"))
            if pareto.n_no_evaluables:
                a("")
                a(
                    f"{_fmt_num(pareto.n_no_evaluables)} serie(s) comparable(s) en 6M no son evaluables para "
                    f"impacto absoluto (falta SCP_TOTAL_ABS_ERROR_6M o ML_TOTAL_ABS_ERROR_6M) y no participan "
                    f"en el Pareto."
                )
            a("")
            a("Top 5 series con mayor reduccion absoluta (mejora):")
            a("")
            a("\n".join(_pareto_table_lines(pareto.improvement.table)))
            a("")
            a("Top 5 series con mayor aumento absoluto (deterioro):")
            a("")
            a("\n".join(_pareto_table_lines(pareto.deterioration.table)))
    else:
        a(_no_data_line(visible_label("6M")))
    a("")
    a("---")
    a("")

    df = source.dataframe
    pcols_6m = period_columns(MODEL_CLASSIFICATION_PERIOD)
    mask_6m = m6.comparable_mask if m6 is not None else None
    has_6m_data = df is not None and mask_6m is not None and mask_6m.any()

    # 10. Modelos ML
    a("## 10. Modelos ML")
    a("")
    if has_6m_data:
        ml_models = category_performance_table(df, pcols_6m, mask_6m, "ML_BEST_MODEL")
        a(f"Modelos seleccionados por ML en {visible_label(MODEL_CLASSIFICATION_PERIOD)} (top 10 por frecuencia):")
        a("")
        a("\n".join(_category_table_lines(ml_models)))
        a("")
        a(
            "La frecuencia de seleccion no implica que ese modelo aporte mas valor: comparar la tasa de "
            "victoria y la mejora agregada, no solo el conteo."
        )
    else:
        a(_no_data_line(visible_label(MODEL_CLASSIFICATION_PERIOD)))
    a("")
    a("---")
    a("")

    # 11. Modelos SCP
    a("## 11. Modelos SCP")
    a("")
    if has_6m_data:
        scp_models = category_performance_table(df, pcols_6m, mask_6m, "SCP_BEST_MODEL")
        a(f"Modelos SCP en {visible_label(MODEL_CLASSIFICATION_PERIOD)} (top 10 por frecuencia), incluye contra que compite ML:")
        a("")
        a("\n".join(_category_table_lines(scp_models)))
    else:
        a(_no_data_line(visible_label(MODEL_CLASSIFICATION_PERIOD)))
    a("")
    a("---")
    a("")

    # 12. Clasificaciones
    a("## 12. Clasificaciones")
    a("")
    if has_6m_data:
        for col, label in (
            ("ML_CLASSIFICATION", "ML_CLASSIFICATION"), ("ML_TYPE", "ML_TYPE"),
            ("SERIES_CLASSIFICATION", "SERIES_CLASSIFICATION"), ("SCP_CLASSIFICATION", "SCP_CLASSIFICATION"),
        ):
            table = category_performance_table(df, pcols_6m, mask_6m, col)
            if table.empty:
                continue
            a(f"**{label}** (top 10):")
            a("")
            a("\n".join(_category_table_lines(table)))
            a("")
        a(
            "Las categorias con menos de 10 series comparables se marcan como muestra pequena: no se "
            "deben extraer conclusiones fuertes de ellas."
        )
    else:
        a(_no_data_line(visible_label(MODEL_CLASSIFICATION_PERIOD)))
    a("")
    a("---")
    a("")

    # 13. Exclusiones
    a("## 13. Exclusiones")
    a("")
    n_status_excluded = result.comparison_status_distribution.get("NOT_COMPARABLE_ML_EXCLUDED", 0)
    n_flag_excluded = m6.n_ml_excluded if m6 is not None else 0
    a(
        f"`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: {_fmt_num(n_status_excluded)} filas. "
        f"`HAS_ML_EXCLUDED=1` (recuento real): {_fmt_num(n_flag_excluded)} filas. La diferencia "
        f"({_fmt_num(n_flag_excluded - n_status_excluded)}) corresponde a exclusiones ML \"tapadas\" por "
        f"otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP)."
    )
    a("")
    a("---")
    a("")

    # 14 / 15. Casos de mayor mejora / deterioro
    a("## 14. Casos de mayor mejora")
    a("")
    if has_6m_data:
        top_improve, _ = top_percentage_changes(df, pcols_6m, mask_6m)
        a(f"Top series con mayor mejora porcentual en {visible_label(MODEL_CLASSIFICATION_PERIOD)}:")
        a("")
        a("\n".join(_ranking_table_lines(top_improve, "ML_IMPROVEMENT_VS_SCP_PCT", _fmt_signed_pct_scaled)))
    else:
        a(_no_data_line(visible_label(MODEL_CLASSIFICATION_PERIOD)))
    a("")
    a("---")
    a("")

    a("## 15. Casos de mayor deterioro")
    a("")
    if has_6m_data:
        _, top_worsen = top_percentage_changes(df, pcols_6m, mask_6m)
        a(f"Top series donde ML peor se comporta frente a SCP en {visible_label(MODEL_CLASSIFICATION_PERIOD)}:")
        a("")
        a("\n".join(_ranking_table_lines(top_worsen, "ML_IMPROVEMENT_VS_SCP_PCT", _fmt_signed_pct_scaled)))
    else:
        a(_no_data_line(visible_label(MODEL_CLASSIFICATION_PERIOD)))
    a("")
    a("---")
    a("")

    # 16. Riesgos
    a("## 16. Riesgos")
    a("")
    risks = []
    if source.read_repaired:
        risks.append("El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).")
    codes_present = {i.code for i in result.quality.issues}
    if "POSSIBLE_MOJIBAKE_IN_TEXT" in codes_present:
        risks.append("Se han detectado posibles artefactos de codificacion en columnas VALUE_LEVEL_*.")
    if "BATCH_HETEROGENEITY_ACROSS_CLIENTS" in codes_present:
        risks.append("Los clientes del batch cargado no proceden todos del mismo ID_BATCH.")
    if "NEGATIVE_HISTORY_ROW_COMPARABLE_IN_6M" in codes_present:
        risks.append("Hay series con historico mensual negativo (posible ajuste/devolucion) que siguen siendo comparables en 6M.")
    extreme_wape_n = sum(i.details.get("n_extreme", 0) for i in result.quality.issues if i.code == "EXTREME_WAPE")
    if extreme_wape_n:
        risks.append(f"{extreme_wape_n} observaciones de WAPE extremo (>500%), tipicamente series con historico muy pequeno.")
    if not risks:
        risks.append("No se han detectado riesgos adicionales relevantes mas alla de los chequeos de calidad estandar.")
    for r in risks:
        a(f"- {r}")
    a("")
    a("---")
    a("")

    # 17. Limitaciones
    a("## 17. Limitaciones")
    a("")
    limitations = [
        "El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo "
        "(relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.",
        "Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.",
        "Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan "
        "silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.",
        "Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.",
    ]
    if no_comparable_anywhere:
        limitations.append(
            "Este cliente no tiene ninguna serie comparable: las secciones de performance quedan vacias "
            "por diseno, no se ha inventado ningun dato para rellenarlas."
        )
    for lim in limitations:
        a(f"- {lim}")
    a("")
    a("---")
    a("")

    # 18. Conclusion
    a("## 18. Conclusion")
    a("")
    if no_comparable_anywhere:
        a(
            f"No es posible concluir sobre la mejora de ML frente a SCP para este cliente: ninguna de sus "
            f"{_fmt_num(result.n_candidates)} series candidatas es comparable (ver seccion 2 para el motivo). "
            f"Esto es un resultado de cobertura, no de performance."
        )
    elif m6 is not None and m6.n_comparable:
        imp = m6.wape.get("improvement_pct")
        median_imp = m6.improvement_stats_all.get("median")
        pct_ml = m6.winner_counts.get("ML", {}).get("pct")
        veredicto = "mejora" if (imp is not None and not math.isnan(imp) and imp > 0) else "no mejora"
        a(
            f"En el semestre completo, ML **{veredicto}** el WAPE global ponderado frente a SCP "
            f"({_fmt_signed_pct_scaled(imp)}). A nivel de serie individual, la mediana de mejora es "
            f"{_fmt_signed_pct_scaled(median_imp)} y ML gana en el {_fmt_pct_scaled(pct_ml)} de las series "
            f"comparables ({_fmt_pct_scaled(m6.pct_comparable)} del universo candidato). Estas cuatro cifras "
            f"(impacto ponderado, mediana por serie, frecuencia de victoria y cobertura) no deben "
            f"confundirse entre si: una es favorable no implica que las demas lo sean en la misma medida."
        )
    else:
        a(_no_data_line(visible_label("6M")))
    a("")

    return "\n".join(lines)
