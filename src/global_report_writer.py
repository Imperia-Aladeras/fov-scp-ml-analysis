"""
Generacion del informe Markdown global (21 secciones, ver
docs/analysis_requirements.md "Informe Markdown global").

Responde explicitamente las 12 preguntas interpretativas de la spec
("Objetivo interpretativo del informe global"), distinguiendo siempre
impacto ponderado, mejora media/mediana por cliente, mejora media/mediana
por serie, frecuencia de victoria, reduccion absoluta y cobertura.
"""

from __future__ import annotations

import math

import pandas as pd

from src.global_analysis import GlobalAnalysisResult
from src.global_portfolio_view import build_global_portfolio_view
from src.periods import ALL_PERIODS, MONTHLY_PERIODS, visible_label
from src.portfolio_presentation import prepare_portfolio_presentation
from src.phase8_presentation import (
    BIAS_METHODOLOGY_NOTE,
    PHASE8_NO_ROUTING_NOTE,
    PHASE8_ONLY_6M_NOTE,
    PHASE8_SMALL_SAMPLE_NOTE,
    VOLUME_METHODOLOGY_NOTE_GLOBAL,
    direction_label_es,
    sort_volume_table,
    volume_bucket_label_es,
)
from src.quality_presentation import metric_audit_global_rows
from src.report_writer import (
    _fmt_num,
    _fmt_pct_fraction,
    _fmt_pct_scaled,
    _fmt_signed_pct_fraction,
    _fmt_signed_pct_scaled,
    _pareto_concentration_line,
    _pareto_table_lines,
    _portfolio_md_table,
    _table_from_rows,
)

MODEL_CLASSIFICATION_PERIOD = "6M"

# Contrato completo de columnas Phase8 (src.phase8.category_performance_table_with_bias):
# se conservan TODAS las senales presentes en la tabla fuente, no solo Bias.
_PHASE8_BASE_HEADERS = [
    "Categoria", "N comparable", "N gana ML", "N gana SCP", "N empate", "Tasa victoria ML",
    "WAPE SCP", "WAPE ML", "Mejora agregada", "Mediana mejora", "Reduccion absoluta",
    "% volumen historico", "Muestra pequena",
]
_PHASE8_BIAS_HEADERS = ["Bias SCP", "Direccion SCP", "Bias ML", "Direccion ML"]
_CROSS_TABLE_TOP_N = 30


def _metric_audit_global_table_lines(rows: list[dict]) -> list[str]:
    """
    Tabla compacta de auditoria de metricas (Fase 9B) agregada por
    (severidad, codigo, periodo) via src.quality_presentation.metric_audit_global_rows
    -- consume QualityIssue ya calculados por cada ClientAnalysisResult,
    nunca recalcula los chequeos sobre el conjunto global.
    """
    if not rows:
        return ["No se han detectado incidencias de auditoría de métricas."]
    headers = ["Severidad", "Código", "Descripción", "Periodo", "N clientes afectados", "N incidencias", "Clientes"]
    table_rows = [
        [
            r["severidad"], r["codigo"], r["descripcion"], r["periodo"],
            str(r["n_clientes_afectados"]), str(r["n_issues"]), r["clientes"],
        ]
        for r in rows
    ]
    return _table_from_rows(headers, table_rows)


def _phase8_category_table_lines(table: pd.DataFrame, category_label: str = "Categoria", top_n: int = 10) -> list[str]:
    """
    Formatea una tabla ya calculada de src.phase8 (model_tables/classification_tables/
    volume_table/classification_volume_cross, PeriodResult.phase8 global, nunca
    recalculada aqui) conservando TODAS las senales disponibles en la tabla fuente
    -- no solo las 4 columnas de Bias. `n_clients` se muestra unicamente cuando la
    columna existe realmente en `table` (volume_table global NO la tiene: no se
    fabrica ni se recalcula).
    """
    if table is None or table.empty:
        return ["_Sin datos (sin series comparables)._"]
    has_n_clients = "n_clients" in table.columns
    headers = list(_PHASE8_BASE_HEADERS)
    headers[0] = category_label
    if has_n_clients:
        headers.insert(1, "N clientes")
    headers += _PHASE8_BIAS_HEADERS
    rows = []
    for _, r in table.head(top_n).iterrows():
        row = [str(r["category"])]
        if has_n_clients:
            row.append(_fmt_num(r["n_clients"]))
        row += [
            _fmt_num(r["n_comparable"]),
            _fmt_num(r["n_win_ml"]), _fmt_num(r["n_win_scp"]), _fmt_num(r["n_tie"]),
            _fmt_pct_scaled(r["win_rate_ml_pct"]), _fmt_pct_fraction(r["scp_wape_agg"]),
            _fmt_pct_fraction(r["ml_wape_agg"]), _fmt_signed_pct_scaled(r["improvement_agg_pct"]),
            _fmt_signed_pct_scaled(r["median_improvement_pct"]),
            _fmt_num(r["abs_error_reduction"]), _fmt_pct_scaled(r["pct_of_history_volume"]),
            "si" if r["small_sample"] else "no",
            _fmt_signed_pct_fraction(r["scp_bias_agg"]), direction_label_es(r["scp_direction"]),
            _fmt_signed_pct_fraction(r["ml_bias_agg"]), direction_label_es(r["ml_direction"]),
        ]
        rows.append(row)
    return _table_from_rows(headers, rows)


def _phase8_cross_truncation_note(table: pd.DataFrame, top_n: int = _CROSS_TABLE_TOP_N) -> str | None:
    """
    Nunca truncar en silencio: si `table` (classification_volume_cross, ya
    calculada por el nucleo) tiene mas filas que las mostradas por
    `_phase8_cross_table_lines`, deja explicito cuantas se muestran frente al
    total real. No recorta ni filtra `table`: solo informa. Devuelve None
    cuando se muestran todas las filas (nada que avisar).
    """
    if table is None or table.empty or len(table) <= top_n:
        return None
    return (
        f"_Mostrando {top_n} de {len(table)} combinaciones "
        f"(el Excel global, hoja `17_phase8_global`, conserva el listado completo)._"
    )


def _phase8_cross_table_lines(table: pd.DataFrame, top_n: int = _CROSS_TABLE_TOP_N) -> list[str]:
    """
    Como `_phase8_category_table_lines`, pero para classification_volume_cross
    (columnas SERIES_CLASSIFICATION + VOLUME_BUCKET en vez de una unica
    `category`). Renderiza EXACTAMENTE las filas que entrega el nucleo -- incluye
    filas SERIES_CLASSIFICATION x NOT_ASSIGNABLE si estan presentes, nunca se
    filtran ni se inventan.
    """
    if table is None or table.empty:
        return ["_Sin datos (sin series comparables)._"]
    has_n_clients = "n_clients" in table.columns
    headers = ["Clasificacion", "Volumen relativo", "N comparable"]
    if has_n_clients:
        headers.append("N clientes")
    headers += [
        "N gana ML", "N gana SCP", "N empate", "Tasa victoria ML", "WAPE SCP", "WAPE ML",
        "Mejora agregada", "Mediana mejora", "Reduccion absoluta", "% volumen historico",
        "Muestra pequena",
    ] + _PHASE8_BIAS_HEADERS
    rows = []
    for _, r in table.head(top_n).iterrows():
        row = [str(r["SERIES_CLASSIFICATION"]), volume_bucket_label_es(r["VOLUME_BUCKET"]), _fmt_num(r["n_comparable"])]
        if has_n_clients:
            row.append(_fmt_num(r["n_clients"]))
        row += [
            _fmt_num(r["n_win_ml"]), _fmt_num(r["n_win_scp"]), _fmt_num(r["n_tie"]),
            _fmt_pct_scaled(r["win_rate_ml_pct"]), _fmt_pct_fraction(r["scp_wape_agg"]),
            _fmt_pct_fraction(r["ml_wape_agg"]), _fmt_signed_pct_scaled(r["improvement_agg_pct"]),
            _fmt_signed_pct_scaled(r["median_improvement_pct"]),
            _fmt_num(r["abs_error_reduction"]), _fmt_pct_scaled(r["pct_of_history_volume"]),
            "si" if r["small_sample"] else "no",
            _fmt_signed_pct_fraction(r["scp_bias_agg"]), direction_label_es(r["scp_direction"]),
            _fmt_signed_pct_fraction(r["ml_bias_agg"]), direction_label_es(r["ml_direction"]),
        ]
        rows.append(row)
    return _table_from_rows(headers, rows)


def _period_summary_line(result: GlobalAnalysisResult, period: str) -> str:
    gp = result.periods[period]
    return (
        f"WAPE SCP={_fmt_pct_fraction(gp.scp_wape_global)}, WAPE ML={_fmt_pct_fraction(gp.ml_wape_global)}, "
        f"mejora global ponderada={_fmt_signed_pct_scaled(gp.global_improvement_pct)}, "
        f"reduccion absoluta={_fmt_num(gp.abs_error_reduction_total)}, "
        f"series comparables={_fmt_num(gp.n_comparable_total)} de {_fmt_num(gp.n_candidates_total)} candidatas "
        f"({_fmt_pct_scaled(gp.pct_comparable_global)})."
    )


def _category_table_lines(table: pd.DataFrame, top_n: int = 10, extra_client_col: bool = True) -> list[str]:
    if table.empty:
        return ["_Sin datos (sin series comparables)._"]
    headers = ["Categoria", "N series", "N clientes", "Tasa victoria ML", "WAPE SCP", "WAPE ML", "Mejora agregada", "Mediana mejora"]
    rows = []
    for _, r in table.head(top_n).iterrows():
        rows.append([
            str(r["category"]), _fmt_num(r["n_comparable"]),
            _fmt_num(r.get("n_clients")) if extra_client_col else "n/d",
            _fmt_pct_scaled(r["win_rate_ml_pct"]), _fmt_pct_fraction(r["scp_wape_agg"]),
            _fmt_pct_fraction(r["ml_wape_agg"]), _fmt_signed_pct_scaled(r["improvement_agg_pct"]),
            _fmt_signed_pct_scaled(r["median_improvement_pct"]),
        ])
    return _table_from_rows(headers, rows)


def build_global_report(result: GlobalAnalysisResult) -> str:
    lines: list[str] = []
    a = lines.append

    m6 = result.periods["6M"]
    recent = result.periods["RECENT_3M"]
    older = result.periods["OLDER_3M"]

    a("# Comparativa global SCP vs ML — todos los clientes")
    a("")
    a(f"**Fecha del analisis:** {pd.Timestamp.now():%d/%m/%Y}")
    a(f"**Clientes incluidos:** {len(result.client_results)}")
    if result.invalid_results:
        a(f"**Clientes excluidos (fichero invalido):** {len(result.invalid_results)}")
    a("")
    a("---")
    a("")

    # 1. Resumen ejecutivo
    a("## 1. Resumen ejecutivo")
    a("")
    veredicto = "mejora" if (m6.global_improvement_pct == m6.global_improvement_pct and m6.global_improvement_pct > 0) else "no mejora"
    m6_stats = m6.client_improvement_stats
    n_total, n_evaluable, n_missing = m6_stats.get("n_total"), m6_stats.get("n_evaluable"), m6_stats.get("n_missing")
    n_improved = m6_stats.get("n_improved")
    a(
        f"Sobre {_fmt_num(n_total)} clientes cargados y {_fmt_num(m6.n_comparable_total)} series comparables en "
        f"el semestre completo, ML **{veredicto}** el WAPE global ponderado frente a SCP "
        f"({_fmt_signed_pct_scaled(m6.global_improvement_pct)}). ML mejora en **{_fmt_num(n_improved)} de "
        f"{_fmt_num(n_evaluable)} clientes con performance calculable** en 6M "
        f"({_fmt_pct_scaled(m6_stats.get('pct_improved'))}; mediana de mejora por cliente: "
        f"{_fmt_signed_pct_scaled(m6_stats.get('median'))})"
        + (f", y otros {_fmt_num(n_missing)} clientes no tienen series comparables en 6M" if n_missing else "")
        + f". A nivel de serie, gana en el {_fmt_pct_scaled(m6.winner_counts.get('ML', {}).get('pct'))} de las "
        f"series comparables. Estas cifras no deben confundirse entre si: se detallan por separado en las "
        f"secciones siguientes."
    )
    a("")
    a("---")
    a("")

    # 2. Clientes analizados
    a("## 2. Clientes analizados")
    a("")
    rows = [[str(r.source.id_client), r.source.display_name, r.source.file_label, r.source.file_name, r.status]
            for r in result.client_results]
    a("\n".join(_table_from_rows(["ID_CLIENT", "Nombre", "Etiqueta", "CSV", "Estado"], rows)))
    if result.invalid_results:
        a("")
        a("Excluidos de la comparativa global por fichero invalido:")
        a("")
        a("\n".join(_table_from_rows(
            ["ID (nombre)", "CSV"],
            [[str(r.source.id_from_filename), r.source.file_name] for r in result.invalid_results],
        )))
    a("")
    a("---")
    a("")

    # 3. Calidad y cobertura de los inputs
    a("## 3. Calidad y cobertura de los inputs")
    a("")
    a(
        f"Series candidatas totales: **{_fmt_num(m6.n_candidates_total)}**. Series comparables en 6M: "
        f"**{_fmt_num(m6.n_comparable_total)}** ({_fmt_pct_scaled(m6.pct_comparable_global)}). La cobertura "
        f"varia sensiblemente entre clientes (ver 02_client_coverage en el Excel global)."
    )
    a("")
    n_repaired = sum(1 for r in result.client_results if r.source.read_repaired)
    a(f"Clientes cuyo CSV requirio normalizacion en memoria (comillas dobladas): {n_repaired} de {len(result.client_results)}.")
    a("")
    a("---")
    a("")

    # 4 / 5. Semestre y trimestres
    a("## 4. Resultado del semestre completo")
    a("")
    a(_period_summary_line(result, "6M"))
    a("")
    a("---")
    a("")

    a(f"## 5. Resultado del {visible_label('RECENT_3M')}")
    a("")
    a(_period_summary_line(result, "RECENT_3M"))
    a("")
    a("---")
    a("")

    a(f"## 6. Resultado del {visible_label('OLDER_3M')}")
    a("")
    a(_period_summary_line(result, "OLDER_3M"))
    a("")
    a("---")
    a("")

    # 7. Comparacion entre trimestres
    a("## 7. Comparacion entre trimestres")
    a("")
    sign_change = (
        "cambia de signo entre trimestres"
        if (recent.global_improvement_pct * older.global_improvement_pct < 0)
        else "mantiene el mismo signo en ambos trimestres"
    )
    a(
        f"Mejora ponderada: {_fmt_signed_pct_scaled(recent.global_improvement_pct)} (primer trimestre) vs "
        f"{_fmt_signed_pct_scaled(older.global_improvement_pct)} (segundo trimestre). La mejora global {sign_change}."
    )
    a("")
    a(
        f"% de clientes que mejoran: {_fmt_pct_scaled(recent.client_improvement_stats.get('pct_improved'))} "
        f"vs {_fmt_pct_scaled(older.client_improvement_stats.get('pct_improved'))}."
    )
    a("")
    a("---")
    a("")

    # 8. Evolucion mensual
    a("## 8. Evolucion mensual")
    a("")
    a("\n".join(_table_from_rows(
        ["Mes", "Comparables", "WAPE SCP", "WAPE ML", "Mejora ponderada", "% clientes mejoran", "% series gana ML"],
        [
            [
                month, _fmt_num(result.periods[month].n_comparable_total),
                _fmt_pct_fraction(result.periods[month].scp_wape_global),
                _fmt_pct_fraction(result.periods[month].ml_wape_global),
                _fmt_signed_pct_scaled(result.periods[month].global_improvement_pct),
                _fmt_pct_scaled(result.periods[month].client_improvement_stats.get("pct_improved")),
                _fmt_pct_scaled(result.periods[month].winner_counts.get("ML", {}).get("pct")),
            ]
            for month in MONTHLY_PERIODS
        ],
    )))
    a("")
    a(
        "No se concluye que ML mejora de forma estable solo porque gane mas series en algun mes: comparar "
        "siempre con la mejora ponderada y el % de clientes que mejoran de la misma fila."
    )
    a("")
    a("---")
    a("")

    # 9. WAPE global ponderado (las 9 ventanas, perspectiva 1)
    a("## 9. WAPE global ponderado")
    a("")
    a("Perspectiva 1 (impacto ponderado por volumen) para cada periodo:")
    a("")
    a("\n".join(_table_from_rows(
        ["Periodo", "WAPE SCP", "WAPE ML", "Mejora global ponderada"],
        [
            [p, _fmt_pct_fraction(result.periods[p].scp_wape_global), _fmt_pct_fraction(result.periods[p].ml_wape_global),
             _fmt_signed_pct_scaled(result.periods[p].global_improvement_pct)]
            for p in ALL_PERIODS
        ],
    )))
    a("")
    a("---")
    a("")

    # 10 / 11. Media y mediana de mejora por cliente
    a("## 10. Media de mejora por cliente")
    a("")
    a(
        "Perspectiva 2 (cada cliente pesa igual, no se pondera por numero de series). La media, la desviacion "
        "y el resto de estadisticos de esta seccion se calculan **unicamente sobre los clientes evaluables** "
        "(con mejora calculable en ese periodo); `N_SIN_PERFORMANCE` indica cuantos clientes del total no "
        "entran en el calculo por no tener ninguna serie comparable en ese periodo:"
    )
    a("")
    a("\n".join(_table_from_rows(
        ["Periodo", "N total", "N evaluables", "N sin performance", "Media entre clientes", "Desviacion"],
        [[p, _fmt_num(result.periods[p].client_improvement_stats.get("n_total")),
          _fmt_num(result.periods[p].client_improvement_stats.get("n_evaluable")),
          _fmt_num(result.periods[p].client_improvement_stats.get("n_missing")),
          _fmt_signed_pct_scaled(result.periods[p].client_improvement_stats.get("mean")),
          _fmt_pct_scaled(result.periods[p].client_improvement_stats.get("std"))] for p in ALL_PERIODS],
    )))
    a("")
    a("---")
    a("")

    a("## 11. Mediana de mejora por cliente")
    a("")
    a(
        "La mediana es la referencia principal cuando hay clientes outlier. Mismo denominador que la seccion "
        "10 (unicamente clientes evaluables, columna N evaluables):"
    )
    a("")
    a("\n".join(_table_from_rows(
        ["Periodo", "N evaluables", "Mediana entre clientes", "P25", "P75"],
        [[p, _fmt_num(result.periods[p].client_improvement_stats.get("n_evaluable")),
          _fmt_signed_pct_scaled(result.periods[p].client_improvement_stats.get("median")),
          _fmt_signed_pct_scaled(result.periods[p].client_improvement_stats.get("p25")),
          _fmt_signed_pct_scaled(result.periods[p].client_improvement_stats.get("p75"))] for p in ALL_PERIODS],
    )))
    a("")
    a("---")
    a("")

    # 12. Media y mediana por serie
    a("## 12. Media y mediana por serie")
    a("")
    a(
        "Perspectiva 3: estadistica de la mejora relativa de cada serie individual de todos los clientes "
        "juntos (no reconstruida desde las medianas por cliente)."
    )
    a("")
    a("\n".join(_table_from_rows(
        ["Periodo", "Media por serie", "Mediana por serie", "P25", "P75"],
        [[p, _fmt_signed_pct_scaled(result.periods[p].series_improvement_stats.get("mean")),
          _fmt_signed_pct_scaled(result.periods[p].series_improvement_stats.get("median")),
          _fmt_signed_pct_scaled(result.periods[p].series_improvement_stats.get("p25")),
          _fmt_signed_pct_scaled(result.periods[p].series_improvement_stats.get("p75"))] for p in ALL_PERIODS],
    )))
    a("")
    a(
        "La media por serie puede ser extremadamente negativa o positiva (ordenes de magnitud mayor que la "
        "mediana): esto ocurre cuando una o pocas series tienen un SCP_WAPE casi nulo pero no exactamente "
        "cero, lo que dispara el porcentaje de mejora individual a valores muy grandes al dividir por un "
        "denominador casi nulo. No se recorta ni se oculta ese valor (ver seccion 20), pero la mediana es la "
        "referencia principal para interpretar el comportamiento tipico de una serie."
    )
    a("")
    a("---")
    a("")

    # 13 / 14. Clientes donde mejora / empeora
    a("## 13. Clientes donde mejora ML")
    a("")
    improving = [
        (r.source.id_client, r.source.display_name, r.periods["6M"].wape.get("improvement_pct"))
        for r in result.client_results
        if r.periods.get("6M") and r.periods["6M"].wape.get("improvement_pct") is not None
        and not math.isnan(r.periods["6M"].wape.get("improvement_pct")) and r.periods["6M"].wape.get("improvement_pct") > 0
    ]
    improving.sort(key=lambda x: -x[2])
    a(
        f"ML mejora en **{len(improving)} de {_fmt_num(n_evaluable)} clientes con performance calculable** en "
        f"6M" + (f". Otros {_fmt_num(n_missing)} clientes no tienen series comparables en 6M y no entran en "
                 f"este recuento." if n_missing else ".")
    )
    a("")
    a("\n".join(_table_from_rows(
        ["ID_CLIENT", "Cliente", "Mejora ponderada 6M"],
        [[str(cid), name, _fmt_signed_pct_scaled(v)] for cid, name, v in improving],
    )) if improving else "_Ninguno._")
    a("")
    a("---")
    a("")

    a("## 14. Clientes donde empeora")
    a("")
    worsening = [
        (r.source.id_client, r.source.display_name, r.periods["6M"].wape.get("improvement_pct"))
        for r in result.client_results
        if r.periods.get("6M") and r.periods["6M"].wape.get("improvement_pct") is not None
        and not math.isnan(r.periods["6M"].wape.get("improvement_pct")) and r.periods["6M"].wape.get("improvement_pct") <= 0
    ]
    worsening.sort(key=lambda x: x[2])
    a(
        f"{len(worsening)} de {_fmt_num(n_evaluable)} clientes con performance calculable no mejoran (empeoran "
        f"o quedan iguales) en 6M" + (f". Otros {_fmt_num(n_missing)} clientes no tienen series comparables en "
                                      f"6M y no entran en este recuento." if n_missing else ".")
    )
    a("")
    a("\n".join(_table_from_rows(
        ["ID_CLIENT", "Cliente", "Mejora ponderada 6M"],
        [[str(cid), name, _fmt_signed_pct_scaled(v)] for cid, name, v in worsening],
    )) if worsening else "_Ninguno._")
    a("")
    a("---")
    a("")

    # 15. Concentracion de la mejora
    a("## 15. Concentracion de la mejora")
    a("")
    totals = m6.reduction_totals
    a(
        f"**REDUCCION_POSITIVA_TOTAL** (suma de clientes que reducen error): {_fmt_num(totals['REDUCCION_POSITIVA_TOTAL'])}. "
        f"**DETERIORO_TOTAL_ABSOLUTO** (suma, en valor absoluto, de clientes que aumentan error): "
        f"{_fmt_num(totals['DETERIORO_TOTAL_ABSOLUTO'])}. **REDUCCION_NETA**: {_fmt_num(totals['REDUCCION_NETA'])}."
    )
    a("")
    a(
        "No se calcula ni se presenta un porcentaje de contribucion sobre la reduccion neta (puede ser cero o "
        "negativa y da lugar a porcentajes fuera de 0-100% dificiles de interpretar): cada cliente se compara "
        "solo dentro de su propio grupo (reduce error / aumenta error)."
    )
    a("")
    reducers = m6.client_reduction_table
    if not reducers.empty:
        top_reducer = reducers.iloc[0]
        a(
            f"El cliente que **mas reduce error** en 6M es **{top_reducer['ETIQUETA']}** "
            f"({_fmt_pct_scaled(top_reducer['PCT_OF_POSITIVE_REDUCTION'])} de la reduccion positiva total)."
        )
        a("")
        a("Clientes que reducen error:")
        a("")
        a("\n".join(_table_from_rows(
            ["Cliente", "Reduccion absoluta", "% de la reduccion positiva"],
            [[row["ETIQUETA"], _fmt_num(row["ABS_ERROR_REDUCTION"]), _fmt_pct_scaled(row["PCT_OF_POSITIVE_REDUCTION"])]
             for _, row in reducers.iterrows()],
        )))
    else:
        a("Ningun cliente reduce error en 6M.")
    a("")
    worseners = m6.client_deterioration_table
    if not worseners.empty:
        top_worsener = worseners.iloc[0]
        a(
            f"El cliente que **mas aumenta error** en 6M es **{top_worsener['ETIQUETA']}** "
            f"({_fmt_pct_scaled(top_worsener['PCT_OF_TOTAL_DETERIORATION'])} del deterioro total absoluto). "
            f"Este cliente NO es un contribuidor positivo a la reduccion: aporta deterioro, no mejora."
        )
        a("")
        a("Clientes que aumentan error:")
        a("")
        a("\n".join(_table_from_rows(
            ["Cliente", "Reduccion absoluta (negativa)", "% del deterioro total"],
            [[row["ETIQUETA"], _fmt_num(row["ABS_ERROR_REDUCTION"]), _fmt_pct_scaled(row["PCT_OF_TOTAL_DETERIORATION"])]
             for _, row in worseners.iterrows()],
        )))
    else:
        a("Ningun cliente aumenta error en 6M.")
    a("")

    if m6.pareto_clients is not None:
        a(
            "**Pareto de clientes — umbrales exactos de concentracion** (complementa el top-1 anterior con "
            "cuantos clientes explican el 50/80/90% de cada grupo; mejora y deterioro se calculan por "
            "separado, cada uno con su propio denominador):"
        )
        a("")
        a(_pareto_concentration_line(m6.pareto_clients.improvement, "mejora"))
        a("")
        a(_pareto_concentration_line(m6.pareto_clients.deterioration, "deterioro"))
        if m6.pareto_clients.n_no_evaluables:
            a("")
            a(
                f"{_fmt_num(m6.pareto_clients.n_no_evaluables)} cliente(s) no son evaluables para impacto "
                f"absoluto en 6M (algun input ausente en alguna de sus series) y no participan en el Pareto "
                f"de clientes."
            )
        a("")

    a("### Pareto de series global (todos los clientes)")
    a("")
    if m6.pareto_series is not None:
        a(_pareto_concentration_line(m6.pareto_series.improvement, "mejora"))
        a("")
        a(_pareto_concentration_line(m6.pareto_series.deterioration, "deterioro"))
        if m6.pareto_series.n_no_evaluables:
            a("")
            a(
                f"{_fmt_num(m6.pareto_series.n_no_evaluables)} serie(s) comparable(s) en 6M no son evaluables "
                f"para impacto absoluto (falta SCP_TOTAL_ABS_ERROR_6M o ML_TOTAL_ABS_ERROR_6M) y no participan "
                f"en el Pareto de series."
            )
        a("")
        a("Top 10 series con mayor reduccion absoluta (mejora), todos los clientes:")
        a("")
        a("\n".join(_pareto_table_lines(m6.pareto_series.improvement.table, top_n=10)))
        a("")
        a("Top 10 series con mayor aumento absoluto (deterioro), todos los clientes:")
        a("")
        a("\n".join(_pareto_table_lines(m6.pareto_series.deterioration.table, top_n=10)))
    else:
        a("Pareto de series no disponible para este periodo.")
    a("")
    a("---")
    a("")

    portfolio_view = build_global_portfolio_view(
        prepare_portfolio_presentation(result.portfolio)
    )

    # 16. Seleccion observada global
    a("## 16. Selección observada y performance condicionada")
    a("")
    a(portfolio_view["message"])
    a("")
    if not portfolio_view["available"]:
        if portfolio_view["missing_required_columns"]:
            missing = ", ".join(f"`{column}`" for column in portfolio_view["missing_required_columns"])
            a(f"Metadata específica ausente: {missing}.")
    else:
        a("La asignación de modelo y la población con performance evaluable son universos distintos.")
        a("")
        a("\n".join(_portfolio_md_table([
            ("Motor", "engine"), ("Período", "block"), ("Base", "n_base_series"),
            ("Eventos", "n_structural_events"), ("Modelo informado", "n_model_present"),
            ("Modelo ausente", "n_model_missing"), ("Cobertura", "selection_assignment_rate"),
            ("Métricas evaluables", "n_block_metrics_evaluable"),
            ("Performance evaluable", "n_performance_evaluable"),
        ], portfolio_view["coverage"])))
        if portfolio_view["has_assignments"]:
            for group in portfolio_view["models"]:
                a("")
                a(f"**{group['engine']} · {group['block']}** — selecciones más frecuentes.")
                a("")
                a("\n".join(_portfolio_md_table([
                    ("Modelo", "model_name"), ("Selecciones", "selection_count"),
                    ("Cuota", "selection_share_of_assignable"), ("N performance", "n_performance"),
                    ("N clientes", "n_clients"), ("Muestra", "sample_note"),
                    ("WAPE Auto", "scp_wape"), ("WAPE Optimizer", "optimizer_wape"),
                    ("Mejora Optimizer vs Auto", "optimizer_improvement_vs_scp"),
                ], group["rows"])))
        else:
            a("_Sin asignaciones observadas; la cobertura anterior sigue siendo informativa._")
    a("")
    a(portfolio_view["methodology_note"])
    a("")
    a("Detalle completo: hojas `11_models_and_win_rates` y `19_portfolio_events` del Excel global.")
    a("")
    a("---")
    a("")

    # 17. Portfolio Optimizer
    a("## 17. Portfolio Optimizer: familias y clasificación")
    a("")
    if not portfolio_view["available"]:
        a(portfolio_view["message"])
    elif not portfolio_view["has_assignments"]:
        a("Sin asignaciones observadas; no hay familias ni pares clasificación–modelo que resumir.")
    else:
        for group in portfolio_view["families"]:
            a(f"**Familias · {group['block']}**")
            a("")
            a("\n".join(_portfolio_md_table([
                ("Familia", "family"), ("Selecciones", "selection_count"),
                ("Cuota", "selection_share_of_assignable"), ("N performance", "n_performance"),
                ("N clientes", "n_clients"), ("Muestra", "sample_note"),
                ("WAPE Auto", "scp_wape"), ("WAPE Optimizer", "optimizer_wape"),
                ("Mejora Optimizer vs Auto", "optimizer_improvement_vs_scp"),
            ], group["rows"])))
            a("")
        a("Los cruces usan la población pair-assignable, distinta del total de eventos Optimizer.")
        a("")
        a("\n".join(_portfolio_md_table([
            ("Período", "block"), ("Clasificación informada", "n_classification_present"),
            ("Clasificación ausente", "n_classification_missing"),
            ("Cobertura clasificación", "classification_assignment_rate"),
            ("Pares asignables", "n_pair_assignable"), ("Cobertura pares", "pair_assignment_rate"),
        ], portfolio_view["classification_coverage"])))
        a("")
        a("Las selecciones frecuentes por clasificación × modelo y clasificación × familia se muestran en HTML; Excel conserva los cruces completos.")
    a("")
    a("Detalle completo: hoja `12_classifications` del Excel global.")
    a("")
    a("---")
    a("")

    # 18. Estabilidad global
    a("## 18. Estabilidad, transiciones y performance descriptiva")
    a("")
    if not portfolio_view["available"]:
        a(portfolio_view["message"])
    elif not portfolio_view["has_assignments"]:
        a("Sin asignaciones observadas; no hay parejas evaluables para estabilidad.")
    else:
        a(portfolio_view["stability_note"])
        a("")
        a("\n".join(_portfolio_md_table([
            ("Motor", "engine"), ("Evaluables", "n_evaluable"), ("Estables", "stable_count"),
            ("Cambiaron", "changed_count"), ("No evaluables", "not_evaluable_count"),
            ("Tasa estabilidad", "stability_rate"),
        ], portfolio_view["model_stability"])))
        a("")
        a("Transiciones de modelo más frecuentes; las diagonales representan estabilidad válida:")
        a("")
        a("\n".join(_portfolio_md_table([
            ("Motor", "engine"), ("Anterior", "older_value"), ("Reciente", "recent_value"),
            ("Transiciones", "transition_count"), ("Cuota", "transition_share_of_evaluable"),
        ], portfolio_view["model_transitions"]["rows"])))
        if portfolio_view["model_transitions"]["truncated"]:
            a("")
            a("La tabla muestra las transiciones más frecuentes por motor; Excel conserva la matriz completa.")
        a("")
        a("Performance descriptiva por estabilidad:")
        a("")
        a("\n".join(_portfolio_md_table([
            ("Dimensión", "stability_type"), ("Motor", "engine"), ("Período", "block"),
            ("Estado", "stability_state"), ("N performance", "n_performance"),
            ("N clientes", "n_clients"), ("Muestra", "sample_note"),
            ("WAPE Auto", "scp_wape"), ("WAPE Optimizer", "optimizer_wape"),
            ("Mejora Optimizer vs Auto", "optimizer_improvement_vs_scp"),
        ], portfolio_view["performance_by_stability"])))
        a("")
        a(portfolio_view["small_sample_note"])
    a("")
    a("Detalle completo: hoja `18_portfolio_stability` del Excel global.")
    a("")
    a("---")
    a("")

    # 19. Cobertura y exclusiones
    a("## 19. Cobertura y exclusiones")
    a("")
    total_excluded = sum((r.periods["6M"].n_ml_excluded if r.periods.get("6M") else 0) for r in result.client_results)
    a(
        f"Del universo candidato total ({_fmt_num(m6.n_candidates_total)} series), "
        f"{_fmt_pct_scaled(100 - m6.pct_comparable_global)} queda fuera de comparacion en 6M. "
        f"Exclusiones ML reales (HAS_ML_EXCLUDED=1) en todos los clientes: {_fmt_num(total_excluded)}."
    )
    a("")
    a("---")
    a("")

    # 20. Riesgos y limitaciones
    a("## 20. Riesgos y limitaciones")
    a("")
    limitations = [
        "El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo "
        "no esta documentado y no se reconstruye (ver informes individuales).",
        "Los clientes no proceden necesariamente del mismo ID_BATCH ni de la misma ejecucion (ver 15_data_quality_checks).",
        "La seleccion observada por periodo es descriptiva y no constituye una recomendacion de routing.",
        "Los clientes sin ninguna serie comparable en un periodo SI se incluyen en cobertura, en calidad y en "
        "las tablas por cliente de ese periodo; unicamente quedan fuera del CALCULO de medias, medianas, "
        "WAPE, winners o mejoras de ese periodo por no tener performance calculable (ver seccion 1 y "
        "N_CLIENTES_SIN_PERFORMANCE en el Excel global). Se documentan tambien en su informe individual.",
        "Este analisis es retrospectivo (backtesting) y no garantiza comportamiento futuro.",
    ]
    for lim in limitations:
        a(f"- {lim}")
    a("")
    a("### Auditoría de métricas")
    a("")
    audit_rows = metric_audit_global_rows(result.client_results, result.invalid_results)
    a("\n".join(_metric_audit_global_table_lines(audit_rows)))
    if audit_rows:
        a("")
        a(
            "Un mismo código en dos periodos distintos se cuenta en filas separadas (no se mezclan universos "
            "distintos); ver el detalle completo por cliente en la hoja `15_data_quality_checks` del Excel global."
        )
    a("")
    a("---")
    a("")

    # 21. Conclusion final
    a("## 21. Conclusion final")
    a("")
    a(
        f"ML **{veredicto}** el WAPE global ponderado un {_fmt_signed_pct_scaled(m6.global_improvement_pct)} "
        f"sobre el volumen total analizado en 6M. Mejora en **{_fmt_num(n_improved)} de {_fmt_num(n_evaluable)} "
        f"clientes con performance calculable** (mediana de mejora por cliente "
        f"{_fmt_signed_pct_scaled(m6.client_improvement_stats.get('median'))})"
        + (f", mientras que otros {_fmt_num(n_missing)} clientes no tienen series comparables en 6M" if n_missing else "")
        + f", y gana en el {_fmt_pct_scaled(m6.winner_counts.get('ML', {}).get('pct'))} de las series comparables "
        f"(mediana de mejora por serie {_fmt_signed_pct_scaled(m6.series_improvement_stats.get('median'))}). "
        f"La cobertura efectiva es del {_fmt_pct_scaled(m6.pct_comparable_global)} del universo candidato."
    )
    a("")
    totals = m6.reduction_totals
    if totals["REDUCCION_NETA"] <= 0 and totals["DETERIORO_TOTAL_ABSOLUTO"] > 0:
        worseners = m6.client_deterioration_table
        top_worsener_label = worseners.iloc[0]["ETIQUETA"] if not worseners.empty else "n/d"
        a(
            f"La reduccion neta de error absoluto es {_fmt_num(totals['REDUCCION_NETA'])} (reduccion positiva "
            f"total {_fmt_num(totals['REDUCCION_POSITIVA_TOTAL'])} frente a deterioro total absoluto "
            f"{_fmt_num(totals['DETERIORO_TOTAL_ABSOLUTO'])}), explicada principalmente por el deterioro "
            f"concentrado en **{top_worsener_label}** (ver seccion 15). Esto es coherente con que el WAPE "
            f"global ponderado empeore aunque la mayoria de clientes y series mejoren: el impacto ponderado "
            f"por volumen y la mejora tipica por cliente/serie responden preguntas distintas."
        )
        a("")
    a(
        "Estas cifras (impacto ponderado, mejora por cliente, mejora por serie, frecuencia de victoria, "
        "cobertura y concentracion) se han mantenido deliberadamente separadas a lo largo de este informe: "
        "una lectura favorable en una de ellas no implica que las demas lo sean en la misma medida."
    )
    a("")
    a("---")
    a("")

    # 22. Diagnostico global Fase 8 -- Bias y volumen relativo
    a("## 22. Diagnóstico global Fase 8 — Bias y volumen relativo")
    a("")
    if m6.phase8 is not None:
        phase8 = m6.phase8
        bt = phase8.bias_total
        a(
            f"**Bias agregado SCP:** {_fmt_signed_pct_fraction(bt.scp_bias_agg)} ({direction_label_es(bt.scp_direction)}). "
            f"**Bias agregado ML:** {_fmt_signed_pct_fraction(bt.ml_bias_agg)} ({direction_label_es(bt.ml_direction)})."
        )
        a("")
        a(BIAS_METHODOLOGY_NOTE)
        a("")
        a("**Volumen relativo global (VOLUME_BUCKET).**")
        a("")
        a(VOLUME_METHODOLOGY_NOTE_GLOBAL)
        a("")
        volume_table = sort_volume_table(phase8.volume_table)
        if volume_table is not None and not volume_table.empty:
            volume_table = volume_table.copy()
            volume_table["category"] = volume_table["category"].map(volume_bucket_label_es)
        a("\n".join(_phase8_category_table_lines(volume_table, category_label="Volumen relativo")))
        a("")
        a(
            f"**Clientes con volumen relativo no asignable (NOT_ASSIGNABLE):** "
            f"{_fmt_num(phase8.n_clients_with_not_assignable_volume)}."
        )
        a("")
        a(
            "El cruce SERIES_CLASSIFICATION x VOLUME_BUCKET sigue no disponible: "
            "SERIES_CLASSIFICATION es metadata legacy ambigua para 6M."
        )
        a("")
        a(f"- {PHASE8_ONLY_6M_NOTE}")
        a(f"- {PHASE8_SMALL_SAMPLE_NOTE}")
        a(f"- {PHASE8_NO_ROUTING_NOTE}")
    else:
        a(
            "Diagnóstico global Fase 8 (Bias y volumen relativo) no disponible: "
            "al menos un cliente participante no tiene el diagnóstico Fase 8 calculado para 6M "
            "(backend COMPARISON_STATUS ausente)."
        )
    a("")

    return "\n".join(lines)
