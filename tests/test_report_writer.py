from src.quality_checks import QualityIssue, Severity
from src.report_writer import (
    _fmt_num,
    _fmt_pct_fraction,
    _fmt_pct_scaled,
    _fmt_signed_pct_fraction,
    _fmt_signed_pct_scaled,
    _metric_audit_table_lines,
    build_client_report,
)
from tests.factories import build_multi_client_results, build_synthetic_client_result, build_volume_bucket_client_result

EXPECTED_SECTION_HEADERS = [f"## {i}." for i in range(1, 20)]


def test_fmt_helpers():
    assert _fmt_pct_fraction(0.357) == "35.7%"
    assert _fmt_pct_fraction(None) == "n/d"
    assert _fmt_pct_scaled(12.34) == "12.3%"
    assert _fmt_signed_pct_scaled(5.0) == "+5.0%"
    assert _fmt_signed_pct_scaled(-5.0) == "-5.0%"
    assert _fmt_num(1234.5) == "1.234"
    assert _fmt_num(1234.5, decimals=1) == "1.234,5"
    assert _fmt_signed_pct_fraction(0.12) == "+12.0%"
    assert _fmt_signed_pct_fraction(-0.05) == "-5.0%"
    assert _fmt_signed_pct_fraction(None) == "n/d"


def test_build_client_report_has_all_19_sections():
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    for header in EXPECTED_SECTION_HEADERS:
        assert header in report, f"falta la seccion {header}"


def test_build_client_report_mentions_client_label_and_status():
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    assert "99999_Synthetic" in report
    assert result.status in report


def test_build_client_report_no_comparable_series_states_it_explicitly_without_inventing_metrics():
    result = build_synthetic_client_result(with_data=False)
    report = build_client_report(result)
    for header in EXPECTED_SECTION_HEADERS:
        assert header in report
    assert "ninguna" in report.lower() or "sin series comparables" in report.lower()
    # No debe aparecer un WAPE inventado tipo "0.0%" presentado como resultado real de 6M
    assert "no se inventan" in report.lower() or "no se inventa" in report.lower()


def test_section_9_includes_pareto_concentration_and_tables():
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)

    section_9 = report.split("## 9. Impacto absoluto")[1].split("## 10.")[0]
    assert "Pareto de concentracion" in section_9
    assert "1001" in section_9  # unica serie de mejora
    assert "1002" in section_9  # unica serie de deterioro
    assert "explican el 50%" in section_9


def test_section_9_states_empty_deterioration_group_explicitly():
    all_ml_result = build_multi_client_results()[2]  # 77777_AllMlWins: ambas filas ganan ML en 6M
    report = build_client_report(all_ml_result)

    section_9 = report.split("## 9. Impacto absoluto")[1].split("## 10.")[0]
    assert "Sin series con deterioro en 6M" in section_9


# --------------------------------------------------------------------------
# Fase 9C: subseccion "Auditoria de metricas" (5 codigos aprobados de Fase
# 9B), dentro de la seccion 16 (Riesgos). Tests de PRESENTACION, no de
# analisis: los QualityIssue se inyectan a mano sobre un resultado sintetico
# ya calculado, nunca se ejercitan los checks de src/quality_checks.py.
# --------------------------------------------------------------------------

def _section_16(report: str) -> str:
    return report.split("## 16. Riesgos")[1].split("## 17.")[0]


def test_metric_audit_subsection_present_and_clean_when_no_metric_issues():
    """Case A: cliente sin issues METRIC_* -> mensaje breve, sin filas OK por codigo."""
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    section_16 = _section_16(report)

    assert "### Auditoría de métricas" in section_16
    assert "No se han detectado incidencias de auditoría de métricas." in section_16
    assert "METRIC_001" not in section_16
    assert "PASS" not in section_16


def test_metric_audit_subsection_shows_metric_001_period_level():
    """Case B: METRIC_001 period-level aparece con codigo, traduccion y mensaje (incluye periodo via nombre de columna)."""
    result = build_synthetic_client_result(with_data=True)
    result.quality.issues.append(QualityIssue(
        Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE",
        "1 filas con SCP_WAPE_M1 negativo (dominio matematico >=0 para WAPE).",
        scope="period", details={"file": "f", "period": "M1", "column": "SCP_WAPE_M1", "n_violations": 1},
    ))
    report = build_client_report(result)
    section_16 = _section_16(report)

    assert "NEGATIVE_NONNEGATIVE_METRIC_VALUE" in section_16
    assert "Valor negativo en métrica no negativa" in section_16
    assert "SCP_WAPE_M1" in section_16
    assert "WARNING" in section_16


def test_metric_audit_subsection_shows_metric_003_with_unexpected_values():
    """Case C: METRIC_003 con unexpected_values en el mensaje (texto ya generado por Fase 9B, no se reformatea)."""
    result = build_synthetic_client_result(with_data=True)
    result.quality.issues.append(QualityIssue(
        Severity.WARNING, "INVALID_WINNER_METHOD_VALUE",
        "2 filas comparables en 6M con WINNER_METHOD_6M fuera del dominio ['ML', 'SCP', 'TIE']: {'DRAW': 2}.",
        scope="period", details={"file": "f", "period": "6M", "column": "WINNER_METHOD_6M", "unexpected_values": {"DRAW": 2}, "n_rows": 2},
    ))
    report = build_client_report(result)
    section_16 = _section_16(report)

    assert "Método ganador no reconocido" in section_16
    assert "DRAW" in section_16


def test_metric_audit_subsection_shows_explicit_scope_and_period_for_period_level_issue():
    """
    Revision 9C: Ambito y Periodo deben ser columnas propias (issue.scope /
    issue_period(issue)), no solo deducibles del texto de issue.message --
    aqui el mensaje deliberadamente NO repite el periodo en prosa (como
    ocurre en la vida real con METRIC_001/002), para demostrar que la tabla
    no depende de ello.
    """
    result = build_synthetic_client_result(with_data=True)
    result.quality.issues.append(QualityIssue(
        Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "mensaje sin periodo en prosa",
        scope="period", details={"period": "6M"},
    ))
    report = build_client_report(result)
    section_16 = _section_16(report)
    audit_subsection = section_16.split("### Auditoría de métricas")[1]

    assert "| Severidad | Código | Descripción | Ámbito | Periodo | Detalle |" in audit_subsection
    assert (
        "| WARNING | NEGATIVE_NONNEGATIVE_METRIC_VALUE | Valor negativo en métrica no negativa | "
        "period | 6M | mensaje sin periodo en prosa |"
    ) in audit_subsection


def test_metric_audit_subsection_shows_dash_period_for_file_level_issue():
    """Case D/E: METRIC_004/METRIC_005 son file-level -> Ambito='file', Periodo='—' (nunca 'None')."""
    result = build_synthetic_client_result(with_data=True)
    result.quality.issues.append(QualityIssue(
        Severity.WARNING, "INVALID_BINARY_FLAG_VALUE",
        "1 filas con HAS_ML_EXCLUDED fuera del dominio {0,1}: {2: 1}.",
        scope="file", details={"column": "HAS_ML_EXCLUDED", "unexpected_values": {2: 1}, "n_rows": 1},
    ))
    report = build_client_report(result)
    section_16 = _section_16(report)
    audit_subsection = section_16.split("### Auditoría de métricas")[1]

    assert "| WARNING | INVALID_BINARY_FLAG_VALUE | Valor inválido en indicador binario | file | — |" in audit_subsection
    assert " None " not in audit_subsection
    assert "| None |" not in audit_subsection


def test_metric_audit_subsection_does_not_duplicate_other_quality_checks():
    """Case I: un warning preexistente (no METRIC_*) no debe aparecer en la subseccion filtrada."""
    result = build_synthetic_client_result(with_data=True)
    result.quality.issues.append(QualityIssue(
        Severity.WARNING, "EXTREME_WAPE", "3 filas con SCP_WAPE_M1 > 500%.", scope="period", details={"period": "M1", "n_extreme": 3},
    ))
    report = build_client_report(result)
    section_16 = _section_16(report)
    audit_subsection = section_16.split("### Auditoría de métricas")[1]

    assert "EXTREME_WAPE" not in audit_subsection


def test_metric_audit_table_lines_never_renders_raw_none_nan_or_dict_repr_of_details():
    """Case J: las columnas que SI generamos (severidad/codigo/descripcion) nunca son None/nan/dict crudo."""
    issue = QualityIssue(
        Severity.WARNING, "INFINITE_METRIC_VALUE", "1 filas con ML_WAPE_6M = +-inf.",
        scope="period", details={"period": "6M", "column": "ML_WAPE_6M", "n_violations": 1, "sample_ids": [1]},
    )
    lines = _metric_audit_table_lines([issue])
    rendered = "\n".join(lines)

    assert "nan" not in rendered.lower()
    assert " None" not in rendered
    assert "{'period'" not in rendered  # no se vuelca el dict `details` crudo


def test_build_client_report_never_recomputes_pareto(monkeypatch):
    result = build_synthetic_client_result(with_data=True)  # Pareto ya calculado dentro de analyze_client

    def _boom(*args, **kwargs):
        raise AssertionError("report_writer no debe recalcular el Pareto")

    monkeypatch.setattr("src.models.pareto_absolute_impact", _boom)
    monkeypatch.setattr("src.pareto.build_pareto_analysis", _boom)

    report = build_client_report(result)
    assert "Pareto de concentracion" in report


# --------------------------------------------------------------------------
# Fase 8C: seccion 18 (Bias + volumen relativo) y Bias integrado en 10/11/12.
# --------------------------------------------------------------------------

def test_sections_10_11_12_show_explicit_legacy_metadata_unavailability():
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    for start, end in (("## 10.", "## 11."), ("## 11.", "## 12."), ("## 12.", "## 13.")):
        section = report.split(start)[1].split(end)[0]
        assert "metadata legacy" in section
        assert "OLDER_3M" in section and "RECENT_3M" in section
        assert "sin datos" not in section.lower()
        assert "Bias SCP" not in section


def test_section_18_present_with_bias_total_and_volume_not_assignable():
    """El fixture sintetico estandar solo tiene 2 filas comparables en 6M -> NOT_ASSIGNABLE (n<3)."""
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    section_18 = report.split("## 18. Diagnóstico Fase 8")[1].split("## 19.")[0]
    assert "Bias agregado SCP" in section_18
    assert "Bias agregado ML" in section_18
    assert "no asignable" in section_18.lower()
    assert "no evaluable" in section_18.lower() or "%" in section_18


def test_section_18_ok_case_has_three_buckets_in_business_order():
    result = build_volume_bucket_client_result()
    report = build_client_report(result)
    section_18 = report.split("## 18. Diagnóstico Fase 8")[1].split("## 19.")[0]
    low_idx = section_18.find("Bajo relativo")
    medium_idx = section_18.find("Medio relativo")
    high_idx = section_18.find("Alto relativo")
    assert -1 < low_idx < medium_idx < high_idx


def test_section_18_methodology_warnings_present():
    result = build_volume_bucket_client_result()
    report = build_client_report(result)
    section_18 = report.split("## 18. Diagnóstico Fase 8")[1].split("## 19.")[0]
    assert "6M" in section_18
    assert "muestra pequena" in section_18.lower()
    assert "routing" in section_18.lower() or "causalidad" in section_18.lower()


def test_section_18_no_individual_classification_volume_cross():
    result = build_volume_bucket_client_result()
    report = build_client_report(result)
    section_18 = report.split("## 18. Diagnóstico Fase 8")[1].split("## 19.")[0]
    assert "SERIES_CLASSIFICATION" not in section_18


def test_section_18_phase8_none_does_not_crash():
    result = build_synthetic_client_result(with_data=True)
    result.periods["6M"].phase8 = None
    report = build_client_report(result)
    section_18 = report.split("## 18. Diagnóstico Fase 8")[1].split("## 19.")[0]
    assert "no disponible" in section_18.lower()


def test_build_client_report_never_recomputes_phase8(monkeypatch):
    result = build_volume_bucket_client_result()  # Fase 8 ya calculada dentro de analyze_client

    def _boom(*args, **kwargs):
        raise AssertionError("report_writer no debe recalcular Fase 8")

    monkeypatch.setattr("src.phase8.build_phase8_client_diagnostics", _boom)
    monkeypatch.setattr("src.phase8.bias_aggregate", _boom)
    monkeypatch.setattr("src.phase8.compute_volume_buckets", _boom)
    monkeypatch.setattr("src.phase8.classification_volume_cross_table", _boom)

    report = build_client_report(result)
    assert "## 18. Diagnóstico Fase 8" in report
