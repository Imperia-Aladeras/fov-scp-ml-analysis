from src.report_writer import (
    _fmt_num,
    _fmt_pct_fraction,
    _fmt_pct_scaled,
    _fmt_signed_pct_fraction,
    _fmt_signed_pct_scaled,
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

def test_sections_10_11_12_include_bias_columns():
    result = build_synthetic_client_result(with_data=True)
    report = build_client_report(result)
    section_10 = report.split("## 10. Modelos ML")[1].split("## 11.")[0]
    assert "Bias SCP" in section_10
    assert "Direccion SCP" in section_10


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
