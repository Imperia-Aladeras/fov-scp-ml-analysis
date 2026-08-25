"""
Tests de presentacion (Fase 9C): traduccion de los 5 codigos de auditoria de
metricas (Fase 9B) y agregacion global de QualityIssue ya calculados. Estos
tests demuestran PRESENTACION, no analisis: no ejercitan ningun chequeo de
src/quality_checks.py, solo la capa de traduccion/agregacion de
src/quality_presentation.py sobre QualityIssue construidos a mano.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.quality_checks import QualityIssue, QualityReport, Severity
from src.quality_presentation import (
    METRIC_AUDIT_CODES,
    filter_metric_audit_issues,
    issue_period,
    metric_audit_friendly_label,
    metric_audit_global_rows,
)


def _fake_result(id_client: int, issues: list[QualityIssue], display_name: str | None = None):
    report = QualityReport()
    report.extend(issues)
    return SimpleNamespace(
        source=SimpleNamespace(id_client=id_client, display_name=display_name or f"Cliente{id_client}"),
        quality=report,
    )


def test_metric_audit_friendly_label_translates_all_five_approved_codes():
    assert metric_audit_friendly_label("NEGATIVE_NONNEGATIVE_METRIC_VALUE") == "Valor negativo en métrica no negativa"
    assert metric_audit_friendly_label("INFINITE_METRIC_VALUE") == "Valor infinito en métrica"
    assert metric_audit_friendly_label("INVALID_WINNER_METHOD_VALUE") == "Método ganador no reconocido"
    assert metric_audit_friendly_label("UNKNOWN_COMPARISON_STATUS_VALUE") == "Estado de comparación no reconocido"
    assert metric_audit_friendly_label("INVALID_BINARY_FLAG_VALUE") == "Valor inválido en indicador binario"
    assert len(METRIC_AUDIT_CODES) == 5


def test_metric_audit_friendly_label_fallback_for_unknown_or_preexisting_code():
    """Case H: un codigo desconocido/preexistente (no de Fase 9B) no debe inventarse traduccion."""
    assert metric_audit_friendly_label("EXTREME_WAPE") is None
    assert metric_audit_friendly_label("SOME_FUTURE_CODE_NOT_YET_KNOWN") is None


def test_issue_period_reads_details_period_key():
    period_issue = QualityIssue(Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "msg", scope="period", details={"period": "M1"})
    file_issue = QualityIssue(Severity.WARNING, "INVALID_BINARY_FLAG_VALUE", "msg", scope="file", details={})
    assert issue_period(period_issue) == "M1"
    assert issue_period(file_issue) is None


def test_filter_metric_audit_issues_keeps_only_the_five_approved_codes():
    """Case I: no duplicar/arrastrar otros quality checks preexistentes en la vista filtrada."""
    issues = [
        QualityIssue(Severity.WARNING, "EXTREME_WAPE", "extremo", scope="period", details={"period": "M1"}),
        QualityIssue(Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "negativo", scope="period", details={"period": "M1"}),
        QualityIssue(Severity.ERROR, "MISSING_REQUIRED_COLUMNS", "faltan columnas", scope="file", details={}),
    ]
    filtered = filter_metric_audit_issues(issues)
    assert [i.code for i in filtered] == ["NEGATIVE_NONNEGATIVE_METRIC_VALUE"]


def test_metric_audit_global_rows_empty_when_no_metric_issues():
    results = [_fake_result(1, []), _fake_result(2, [QualityIssue(Severity.WARNING, "EXTREME_WAPE", "x", scope="period", details={"period": "M1"})])]
    assert metric_audit_global_rows(results) == []


def test_metric_audit_global_rows_groups_two_clients_same_code_and_period():
    """Case F: dos clientes afectados por el mismo codigo -> una fila agregada."""
    issue_a = QualityIssue(Severity.WARNING, "INFINITE_METRIC_VALUE", "msg A", scope="period", details={"period": "6M"})
    issue_b = QualityIssue(Severity.WARNING, "INFINITE_METRIC_VALUE", "msg B", scope="period", details={"period": "6M"})
    results = [_fake_result(10, [issue_a], "Alfa"), _fake_result(20, [issue_b], "Beta")]

    rows = metric_audit_global_rows(results)
    assert len(rows) == 1
    row = rows[0]
    assert row["codigo"] == "INFINITE_METRIC_VALUE"
    assert row["periodo"] == "6M"
    assert row["n_clientes_afectados"] == 2
    assert row["n_issues"] == 2
    assert row["descripcion"] == "Valor infinito en métrica"


def test_metric_audit_global_rows_clientes_field_lists_id_and_name_sorted_by_id():
    """Trazabilidad global (punto 3): la fila agregada debe permitir identificar que clientes estan afectados."""
    issue_a = QualityIssue(Severity.WARNING, "INFINITE_METRIC_VALUE", "msg A", scope="period", details={"period": "6M"})
    issue_b = QualityIssue(Severity.WARNING, "INFINITE_METRIC_VALUE", "msg B", scope="period", details={"period": "6M"})
    results = [_fake_result(20, [issue_b], "Beta"), _fake_result(10, [issue_a], "Alfa")]

    rows = metric_audit_global_rows(results)
    assert rows[0]["clientes"] == "10 (Alfa), 20 (Beta)"


def test_metric_audit_global_rows_clientes_field_truncates_long_lists():
    """Mas de _CLIENT_LIST_MAX clientes -> se corta con un sufijo '+N mas' en vez de una lista enorme."""
    issues_by_client = [
        _fake_result(i, [QualityIssue(Severity.WARNING, "INVALID_BINARY_FLAG_VALUE", "msg", scope="file", details={})], f"C{i}")
        for i in range(1, 11)  # 10 clientes > _CLIENT_LIST_MAX (8)
    ]
    rows = metric_audit_global_rows(issues_by_client)
    assert rows[0]["n_clientes_afectados"] == 10
    assert rows[0]["clientes"].endswith("+2 más")
    assert rows[0]["clientes"].count("(C") == 8


def test_metric_audit_global_rows_does_not_mix_different_periods_or_codes():
    """Case G: mismo codigo en dos periodos distintos -> filas separadas, no se suman."""
    issue_m1 = QualityIssue(Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "m1", scope="period", details={"period": "M1"})
    issue_6m = QualityIssue(Severity.WARNING, "NEGATIVE_NONNEGATIVE_METRIC_VALUE", "6m", scope="period", details={"period": "6M"})
    issue_other_code = QualityIssue(Severity.WARNING, "INVALID_WINNER_METHOD_VALUE", "winner", scope="period", details={"period": "M1"})
    results = [_fake_result(1, [issue_m1, issue_6m, issue_other_code])]

    rows = metric_audit_global_rows(results)
    assert len(rows) == 3
    keys = {(r["codigo"], r["periodo"]) for r in rows}
    assert keys == {
        ("NEGATIVE_NONNEGATIVE_METRIC_VALUE", "M1"),
        ("NEGATIVE_NONNEGATIVE_METRIC_VALUE", "6M"),
        ("INVALID_WINNER_METHOD_VALUE", "M1"),
    }
    for r in rows:
        assert r["n_issues"] == 1
        assert r["n_clientes_afectados"] == 1


def test_metric_audit_global_rows_file_level_issue_has_dash_period():
    issue = QualityIssue(Severity.WARNING, "UNKNOWN_COMPARISON_STATUS_VALUE", "msg", scope="file", details={})
    rows = metric_audit_global_rows([_fake_result(1, [issue])])
    assert rows[0]["periodo"] == "—"


def test_metric_audit_global_rows_includes_invalid_results():
    issue = QualityIssue(Severity.WARNING, "INVALID_BINARY_FLAG_VALUE", "msg", scope="file", details={})
    valid = _fake_result(1, [])
    invalid = _fake_result(2, [issue])
    rows = metric_audit_global_rows([valid], [invalid])
    assert len(rows) == 1
    assert rows[0]["n_clientes_afectados"] == 1
