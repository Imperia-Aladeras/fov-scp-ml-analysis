"""
Capa de presentacion de la auditoria de metricas (Fase 9C): traduccion a
castellano de los 5 codigos METRIC_00X calculados en Fase 9B
(src/quality_checks.py) y agregacion de QualityIssue ya producidos por
ClientAnalysisResult para el reporting global.

Este modulo NUNCA recalcula ningun chequeo de calidad: unicamente traduce
codigos machine-readable ya existentes y agrupa QualityIssue ya calculados,
igual que src/phase8_presentation.py hace para Bias/volumen. No se cambia
QualityIssue.code en ningun sitio: la traduccion es exclusivamente de
presentacion (Markdown/Excel/HTML), nunca del dato subyacente.
"""

from __future__ import annotations

from src.quality_checks import QualityIssue

# Los 5 codigos nuevos de Fase 9B (METRIC_001-005), todos WARNING/scope
# period o file segun el chequeo. Ver src/quality_checks.py lineas 781-796
# para el contrato completo (congelado, no se toca aqui).
METRIC_AUDIT_LABELS_ES = {
    "NEGATIVE_NONNEGATIVE_METRIC_VALUE": "Valor negativo en métrica no negativa",
    "INFINITE_METRIC_VALUE": "Valor infinito en métrica",
    "INVALID_WINNER_METHOD_VALUE": "Método ganador no reconocido",
    "UNKNOWN_COMPARISON_STATUS_VALUE": "Estado de comparación no reconocido",
    "INVALID_BINARY_FLAG_VALUE": "Valor inválido en indicador binario",
}

METRIC_AUDIT_CODES = frozenset(METRIC_AUDIT_LABELS_ES)

# Tope de clientes listados por nombre en la fila agregada global: por
# encima de este numero se corta con un "+N mas" en vez de una lista enorme
# (seccion 6/9C: "no quiero una lista enorme, pero comprueba que un usuario
# puede identificar que clientes estan afectados"). El detalle completo sin
# tope siempre esta disponible en 15_data_quality_checks del Excel global.
_CLIENT_LIST_MAX = 8


def metric_audit_friendly_label(code: str) -> str | None:
    """
    Traduce un codigo de auditoria de metricas (Fase 9B) a su etiqueta en
    castellano. None si `code` no es uno de los 5 codigos aprobados: no se
    inventa traduccion para codigos desconocidos o preexistentes, el
    llamador debe hacer fallback al codigo/mensaje original.
    """
    return METRIC_AUDIT_LABELS_ES.get(code)


def issue_period(issue: QualityIssue) -> str | None:
    """Periodo (M1..M6/RECENT_3M/OLDER_3M/6M) del QualityIssue si esta presente en `details`; None en otro caso (checks file/client-level)."""
    return issue.details.get("period")


def filter_metric_audit_issues(issues: list[QualityIssue]) -> list[QualityIssue]:
    """Filtra una lista de QualityIssue a unicamente los 5 codigos aprobados de auditoria de metricas (Fase 9B)."""
    return [i for i in issues if i.code in METRIC_AUDIT_CODES]


def _format_affected_clients(clients_map: dict) -> str:
    """
    "12345 (Nombre), 67890 (Otro)" ordenado por ID_CLIENT, cortado a
    `_CLIENT_LIST_MAX` entradas con un "+N mas" cuando hay mas clientes de
    los que caben en una fila legible. El detalle sin cortar (ID_CLIENT +
    CLIENTE por incidencia) siempre esta disponible en 15_data_quality_checks
    del Excel global -- este resumen es de identificacion rapida, no
    sustituye a ese detalle.
    """
    ordered = sorted(clients_map.items())
    shown = [f"{id_client} ({name})" for id_client, name in ordered[:_CLIENT_LIST_MAX]]
    remaining = len(ordered) - len(shown)
    if remaining > 0:
        shown.append(f"+{remaining} más")
    return ", ".join(shown)


def metric_audit_global_rows(client_results: list, invalid_results: list = ()) -> list[dict]:
    """
    Agrega, para el reporting GLOBAL, los QualityIssue de auditoria de
    metricas (Fase 9B) ya producidos por cada ClientAnalysisResult -- NUNCA
    vuelve a ejecutar check_negative_nonnegative_metrics/etc. sobre una
    concatenacion global (se perderia contexto de cliente/periodo).

    Agrupa por (severidad, codigo, periodo): un METRIC_001 en M1 y otro en
    6M son incidencias distintas aunque compartan codigo, no se suman entre
    si (ver seccion 12/13 de la especificacion de Fase 9C).
    """
    groups: dict[tuple, dict] = {}
    for result in list(client_results) + list(invalid_results):
        for issue in result.quality.issues:
            if issue.code not in METRIC_AUDIT_CODES:
                continue
            period = issue_period(issue)
            key = (issue.severity.value, issue.code, period)
            entry = groups.setdefault(key, {"n_issues": 0, "clients": {}})
            entry["n_issues"] += 1
            entry["clients"][result.source.id_client] = result.source.display_name

    rows = [
        {
            "severidad": severity, "codigo": code, "descripcion": METRIC_AUDIT_LABELS_ES[code],
            "periodo": period or "—", "n_clientes_afectados": len(v["clients"]), "n_issues": v["n_issues"],
            "clientes": _format_affected_clients(v["clients"]),
        }
        for (severity, code, period), v in groups.items()
    ]
    rows.sort(key=lambda r: (-r["n_issues"], r["codigo"], r["periodo"]))
    return rows
