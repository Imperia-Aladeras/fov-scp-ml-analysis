from src.report_writer import (
    _fmt_num,
    _fmt_pct_fraction,
    _fmt_pct_scaled,
    _fmt_signed_pct_scaled,
    build_client_report,
)
from tests.factories import build_synthetic_client_result

EXPECTED_SECTION_HEADERS = [f"## {i}." for i in range(1, 19)]


def test_fmt_helpers():
    assert _fmt_pct_fraction(0.357) == "35.7%"
    assert _fmt_pct_fraction(None) == "n/d"
    assert _fmt_pct_scaled(12.34) == "12.3%"
    assert _fmt_signed_pct_scaled(5.0) == "+5.0%"
    assert _fmt_signed_pct_scaled(-5.0) == "-5.0%"
    assert _fmt_num(1234.5) == "1.234"
    assert _fmt_num(1234.5, decimals=1) == "1.234,5"


def test_build_client_report_has_all_18_sections():
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
