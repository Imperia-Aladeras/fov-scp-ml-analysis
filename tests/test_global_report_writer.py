from src.global_report_writer import build_global_report
from tests.factories import build_global_analysis_result

EXPECTED_SECTION_HEADERS = [f"## {i}." for i in range(1, 22)]


def test_build_global_report_has_all_21_sections():
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
    Secciones 13/14 ("Clientes donde mejora/empeora ML"): el nombre de
    catalogo no garantiza unicidad entre ID_CLIENT distintos, asi que estas
    listas deben llevar una columna ID_CLIENT junto al nombre, nunca mostrar
    solo el nombre.
    """
    result = build_global_analysis_result()
    report = build_global_report(result)

    section_13 = report.split("## 13.")[1].split("## 14.")[0]
    section_14 = report.split("## 14.")[1].split("## 15.")[0]

    assert "| ID_CLIENT | Cliente | Mejora ponderada 6M |" in section_13
    assert "| ID_CLIENT | Cliente | Mejora ponderada 6M |" in section_14
    # 77777_AllMlWins mejora (+50%); 99999_Synthetic empeora (ML peor que SCP en 6M).
    assert "| 77777 | AllMlWins |" in section_13
    assert "| 99999 | Synthetic |" in section_14


def test_build_global_report_preserves_technical_period_names_in_headings():
    """
    Regresion: un .lower() aplicado a la etiqueta visible completa convertia
    'M1-M3' en 'm1-m3' en el titulo de la seccion 5.
    """
    result = build_global_analysis_result()
    report = build_global_report(result)
    assert "(M1-M3)" in report
    assert "(m1-m3)" not in report
    assert "(M4-M6)" in report
    assert "(m4-m6)" not in report
