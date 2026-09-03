from src.global_analysis import analyze_global
from src.global_report_writer import build_global_report
from src.quality_checks import QualityIssue, Severity
from tests.factories import (
    build_global_analysis_result,
    build_multi_client_results,
    build_phase8_global_missing_client_results,
    build_phase8_global_multi_client_analysis_result,
)

EXPECTED_SECTION_HEADERS = [f"## {i}." for i in range(1, 23)]


def test_build_global_report_has_all_22_sections():
    result = build_global_analysis_result()
    report = build_global_report(result)
    for header in EXPECTED_SECTION_HEADERS:
        assert header in report, f"falta la seccion {header}"


def test_build_global_report_mentions_all_valid_clients():
    result = build_global_analysis_result()
    report = build_global_report(result)
    for label in ("99999_Synthetic", "88888_NoComparable", "77777_AllMlWins"):
        assert label in report


def test_build_global_report_improving_and_worsening_tables_include_id_client():
    """
    Secciones 13/14 ("Clientes donde Optimizer mejora frente a Auto/empeora"): el nombre de
    catalogo no garantiza unicidad entre ID_CLIENT distintos, asi que estas
    listas deben llevar una columna ID_CLIENT junto al nombre, nunca mostrar
    solo el nombre.
    """
    result = build_global_analysis_result()
    report = build_global_report(result)

    section_13 = report.split("## 13.")[1].split("## 14.")[0]
    section_14 = report.split("## 14.")[1].split("## 15.")[0]

    assert "| ID_CLIENT | Cliente | Mejora ponderada Optimizer vs Auto 6M |" in section_13
    assert "| ID_CLIENT | Cliente | Mejora ponderada Optimizer vs Auto 6M |" in section_14
    # 77777_AllMlWins mejora (+50%); 99999_Synthetic empeora (ML peor que SCP en 6M).
    assert "| 77777 | AllMlWins |" in section_13
    assert "| 99999 | Synthetic |" in section_14


# --------------------------------------------------------------------------
# Fase 9C: subseccion "Auditoria de metricas" (5 codigos aprobados de Fase
# 9B) dentro de la seccion 20 (Riesgos y limitaciones). Tests de
# PRESENTACION: los QualityIssue se inyectan a mano sobre resultados
# sinteticos ya calculados, nunca se ejercitan los checks de
# src/quality_checks.py, y nunca se recalculan sobre el conjunto global.
# --------------------------------------------------------------------------

def _section_20(report: str) -> str:
    return report.split("## 20. Riesgos y limitaciones")[1].split("## 21.")[0]


def test_global_metric_audit_subsection_clean_when_no_metric_issues():
    """Case A (global): sin issues METRIC_* -> mensaje breve, sin filas por codigo."""
    result = build_global_analysis_result()
    report = build_global_report(result)
    section_20 = _section_20(report)

    assert "### Auditoría de métricas" in section_20
    assert "No se han detectado incidencias de auditoría de métricas." in section_20


def test_global_metric_audit_subsection_aggregates_two_clients_same_code():
    """Case F: global con dos clientes afectados por el mismo codigo -> una fila con N clientes afectados = 2."""
    clients = build_multi_client_results()
    clients[0].quality.add(QualityIssue(
        Severity.WARNING, "INFINITE_METRIC_VALUE", "msg a", scope="period", details={"period": "6M"},
    ))
    clients[2].quality.add(QualityIssue(
        Severity.WARNING, "INFINITE_METRIC_VALUE", "msg b", scope="period", details={"period": "6M"},
    ))
    result = analyze_global(clients)
    report = build_global_report(result)
    section_20 = _section_20(report)

    assert "INFINITE_METRIC_VALUE" in section_20
    assert "Valor infinito en métrica" in section_20
    rows = [line for line in section_20.splitlines() if "INFINITE_METRIC_VALUE" in line]
    assert len(rows) == 1
    assert (
        "| WARNING | INFINITE_METRIC_VALUE | Valor infinito en métrica | 6M | 2 | 2 | "
        "77777 (AllMlWins), 99999 (Synthetic) |"
    ) == rows[0]


def test_global_metric_audit_subsection_keeps_different_periods_in_separate_rows():
    """Case G: mismo codigo en dos periodos distintos -> dos filas separadas, no mezcladas."""
    clients = build_multi_client_results()
    clients[0].quality.add(QualityIssue(
        Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "m1", scope="period", details={"period": "M1"},
    ))
    clients[0].quality.add(QualityIssue(
        Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "6m", scope="period", details={"period": "6M"},
    ))
    result = analyze_global(clients)
    report = build_global_report(result)
    section_20 = _section_20(report)

    rows = [line for line in section_20.splitlines() if "NEGATIVE_NONNEGATIVE_METRIC_VALUE" in line]
    assert len(rows) == 2
    assert any("| M1 |" in r for r in rows)
    assert any("| 6M |" in r for r in rows)


def test_global_metric_audit_subsection_does_not_duplicate_other_quality_checks():
    """Case I: un warning preexistente (no METRIC_*) no debe aparecer en la subseccion filtrada."""
    clients = build_multi_client_results()
    clients[0].quality.add(QualityIssue(
        Severity.WARNING, "EXTREME_WAPE", "3 filas > 500%.", scope="period", details={"period": "M1"},
    ))
    result = analyze_global(clients)
    report = build_global_report(result)
    section_20 = _section_20(report)
    audit_subsection = section_20.split("### Auditoría de métricas")[1]

    assert "EXTREME_WAPE" not in audit_subsection


def test_build_global_report_preserves_technical_period_names_in_headings():
    """
    Regresion: un .lower() aplicado a la etiqueta visible completa convertia
    'M3–M1' en 'm3–m1' en el titulo de la seccion 5.
    """
    result = build_global_analysis_result()
    report = build_global_report(result)
    assert "(M3–M1)" in report
    assert "(m3–m1)" not in report
    assert "(M6–M4)" in report
    assert "(m6–m4)" not in report


# --------------------------------------------------------------------------
# 15. Concentracion de la mejora (ampliacion Pareto)
# --------------------------------------------------------------------------

def test_section_15_includes_pareto_client_thresholds():
    result = build_global_analysis_result()
    report = build_global_report(result)
    section_15 = report.split("## 15.")[1].split("## 16.")[0]

    assert "Pareto de clientes" in section_15
    assert "explican el 50%" in section_15


def test_section_15_includes_pareto_series_global_with_mejora_and_deterioro_separated():
    result = build_global_analysis_result()
    report = build_global_report(result)
    section_15 = report.split("## 15.")[1].split("## 16.")[0]

    assert "Pareto de series global" in section_15
    assert "Top 10 series con mayor reduccion absoluta (mejora)" in section_15
    assert "Top 10 series con mayor aumento absoluto (deterioro)" in section_15
    # mixed (99999) aporta 1 fila de mejora y 1 de deterioro; all_ml (77777) aporta 2 de mejora.
    assert "1001" in section_15 or "2001" in section_15  # alguna serie de mejora visible
    assert "1002" in section_15  # la unica serie de deterioro (mixed, fila 1)


def test_build_global_report_never_recomputes_pareto(monkeypatch):
    result = build_global_analysis_result()  # Pareto ya calculado dentro de analyze_global

    def _boom(*args, **kwargs):
        raise AssertionError("global_report_writer no debe recalcular el Pareto")

    monkeypatch.setattr("src.global_analysis.global_pareto_series", _boom)
    monkeypatch.setattr("src.global_analysis.global_pareto_clients", _boom)
    monkeypatch.setattr("src.pareto.build_pareto_analysis", _boom)

    report = build_global_report(result)
    assert "Pareto de series global" in report


# --------------------------------------------------------------------------
# 22. Diagnostico global Fase 8 (Fase 8D)
# --------------------------------------------------------------------------

def test_section_22_preserves_bias_volume_not_assignable_and_suppresses_cross():
    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    assert "## 22. Diagnóstico global Fase 8" in report
    section_22 = report.split("## 22.")[1]

    assert "Bias agregado Auto" in section_22
    assert "Bias agregado Optimizer" in section_22
    assert "Volumen relativo global" in section_22
    assert "Clientes con volumen relativo no asignable" in section_22
    assert "1" in section_22.split("Clientes con volumen relativo no asignable")[1][:40]
    assert "SERIES_CLASSIFICATION x VOLUME_BUCKET" in section_22  # aviso explicito, no tabla
    assert "metadata legacy" in section_22
    assert "SERIES_CLASSIFICATION x VOLUME_BUCKET" in section_22
    assert "| Clasificacion |" not in section_22


def test_section_22_never_leaks_raw_machine_codes_or_percent_small_sample():
    import re

    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    section_22 = report.split("## 22.")[1]

    for code in ("RELATIVE_LOW", "RELATIVE_MEDIUM", "RELATIVE_HIGH", "POSITIVE", "NEGATIVE", "NOT_EVALUABLE"):
        assert code not in section_22
    assert not re.search(r"\bnan\b", section_22.lower())
    # "inf" en solitario (valor no finito), no como subcadena de "infraprevision".
    assert not re.search(r"(?<![a-záéíóúñ])inf(?![a-záéíóúñ])", section_22.lower())
    # small_sample debe ser un booleano si/no, nunca un "% muestra pequena"
    assert "% muestra" not in section_22.lower()


def test_section_22_never_shows_n_clientes_for_volume_bucket_table():
    """volume_table global no lleva n_clients (a diferencia de modelo/clasificacion/cruce): no se fabrica."""
    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    section_22 = report.split("## 22.")[1]
    volume_block = section_22.split("Volumen relativo global")[1].split("Clientes con volumen")[0]
    assert "N clientes" not in volume_block


def test_section_22_short_note_when_phase8_none():
    result = analyze_global(build_phase8_global_missing_client_results())
    assert result.periods["6M"].phase8 is None
    report = build_global_report(result)
    section_22 = report.split("## 22.")[1]
    assert "no disponible" in section_22
    assert "Bias agregado Auto" not in section_22


def test_sections_16_to_18_show_explicit_portfolio_unavailability():
    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    for start, end in (("## 16.", "## 17."), ("## 17.", "## 18."), ("## 18.", "## 19.")):
        section = report.split(start)[1].split(end)[0]
        assert "Análisis de selección por bloques no disponible" in section
        assert "Bias Auto" not in section


def test_sections_16_to_18_do_not_fall_back_to_legacy_table_when_phase8_none():
    result = analyze_global(build_phase8_global_missing_client_results())
    report = build_global_report(result)
    section_16 = report.split("## 16.")[1].split("## 17.")[0]
    assert "Bias Auto" not in section_16
    assert "selección por bloques no disponible" in section_16
