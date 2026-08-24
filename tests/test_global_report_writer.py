from src.global_analysis import analyze_global
from src.global_report_writer import build_global_report
from tests.factories import (
    build_global_analysis_result,
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

def test_section_22_present_with_bias_volume_and_cross_when_phase8_available():
    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    assert "## 22. Diagnóstico global Fase 8" in report
    section_22 = report.split("## 22.")[1]

    assert "Bias agregado SCP" in section_22
    assert "Bias agregado ML" in section_22
    assert "Volumen relativo global" in section_22
    assert "Clientes con volumen relativo no asignable" in section_22
    assert "1" in section_22.split("Clientes con volumen relativo no asignable")[1][:40]
    assert "SERIES_CLASSIFICATION x VOLUME_BUCKET" in section_22
    assert "No asignable" in section_22  # traduccion del bucket NOT_ASSIGNABLE en el cruce


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
    assert "Bias agregado SCP" not in section_22


def test_sections_16_to_18_include_bias_columns_when_phase8_available():
    result = build_phase8_global_multi_client_analysis_result()
    report = build_global_report(result)
    section_16 = report.split("## 16.")[1].split("## 17.")[0]
    assert "Bias SCP" in section_16
    assert "N gana ML" in section_16


def test_sections_16_to_18_fall_back_to_legacy_table_when_phase8_none():
    result = analyze_global(build_phase8_global_missing_client_results())
    report = build_global_report(result)
    section_16 = report.split("## 16.")[1].split("## 17.")[0]
    assert "Bias SCP" not in section_16
