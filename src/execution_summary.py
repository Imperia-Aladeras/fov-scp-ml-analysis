"""
Resumen de ejecucion: outputs/execution_summary.md y .xlsx.

Una fila por CSV descubierto (valido o no), con: archivo, carpeta de salida,
ID_CLIENT, etiqueta, batch, run, filas, candidatas, comparables 6M, estado,
warnings, errores, duracion, informe/Excel/graficos generados.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from openpyxl.utils import get_column_letter

from src.client_analysis import ClientAnalysisResult
from src.excel_writer import HEADER_FILL, HEADER_FONT, autosize_columns


@dataclass
class ExecutionRecord:
    archivo: str
    carpeta_salida: str
    id_client: object
    etiqueta: str
    id_batch: list
    id_run_staging: list
    filas: int
    candidatas: int
    comparables_6m: int
    estado: str
    warnings: int
    errors: int
    duracion_segundos: float
    informe_generado: bool
    excel_generado: bool
    graficos_generados: int


def build_execution_records(
    results: list[ClientAnalysisResult],
    outputs_by_file: dict[str, list[str]],
    durations_by_file: dict[str, float],
) -> list[ExecutionRecord]:
    records = []
    for r in results:
        source = r.source
        outputs = outputs_by_file.get(source.file_name, [])
        duration = durations_by_file.get(source.file_name, 0.0)
        counts = r.quality.summary_counts()
        pr_6m = r.periods.get("6M")
        records.append(ExecutionRecord(
            archivo=source.file_name,
            carpeta_salida=f"outputs/{source.folder_name}/" if r.file_valid else "",
            id_client=source.id_client, etiqueta=source.file_label,
            id_batch=source.id_batch, id_run_staging=source.id_run_staging,
            filas=source.n_rows, candidatas=r.n_candidates,
            comparables_6m=pr_6m.n_comparable if pr_6m else 0,
            estado=r.status, warnings=counts.get("WARNING", 0), errors=counts.get("ERROR", 0),
            duracion_segundos=duration,
            informe_generado=any(p.endswith(".md") for p in outputs),
            excel_generado=any(p.endswith(".xlsx") for p in outputs),
            graficos_generados=sum(1 for p in outputs if p.endswith(".png")),
        ))
    return records


def execution_summary_table(records: list[ExecutionRecord]) -> pd.DataFrame:
    return pd.DataFrame([{
        "ARCHIVO": rec.archivo, "CARPETA_SALIDA": rec.carpeta_salida,
        "ID_CLIENT": rec.id_client, "ETIQUETA": rec.etiqueta,
        "ID_BATCH": str(rec.id_batch), "ID_RUN_STAGING": str(rec.id_run_staging),
        "FILAS": rec.filas, "CANDIDATAS": rec.candidatas, "COMPARABLES_6M": rec.comparables_6m,
        "ESTADO": rec.estado, "WARNINGS": rec.warnings, "ERRORS": rec.errors,
        "DURACION_SEGUNDOS": round(rec.duracion_segundos, 3),
        "INFORME_GENERADO": rec.informe_generado, "EXCEL_GENERADO": rec.excel_generado,
        "GRAFICOS_GENERADOS": rec.graficos_generados,
    } for rec in records])


def build_execution_summary_workbook(records: list[ExecutionRecord], output_path: Path) -> None:
    table = execution_summary_table(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="execution_summary", index=False)
        ws = writer.sheets["execution_summary"]
        for col_idx in range(1, len(table.columns) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
        ws.freeze_panes = "A2"
        autosize_columns(writer, "execution_summary")
        if ws.max_row >= 2:
            ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"


def build_execution_summary_markdown(records: list[ExecutionRecord]) -> str:
    lines: list[str] = []
    a = lines.append

    n_total = len(records)
    status_counts: dict[str, int] = {}
    for rec in records:
        status_counts[rec.estado] = status_counts.get(rec.estado, 0) + 1
    total_duration = sum(rec.duracion_segundos for rec in records)

    a("# Resumen de ejecucion")
    a("")
    a(f"**Fecha:** {pd.Timestamp.now():%d/%m/%Y %H:%M}")
    a(f"**CSV descubiertos:** {n_total}")
    a(f"**Duracion total:** {total_duration:.2f} s")
    a("")
    a("| Estado | N |")
    a("|---|---|")
    for status, n in sorted(status_counts.items()):
        a(f"| {status} | {n} |")
    a("")
    a("| Archivo | Carpeta salida | ID_CLIENT | Filas | Candidatas | Comparables 6M | Estado | Warnings | Errors | Duracion (s) | Informe | Excel | Graficos |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for rec in records:
        a(
            f"| {rec.archivo} | {rec.carpeta_salida} | {rec.id_client} | {rec.filas} | {rec.candidatas} | "
            f"{rec.comparables_6m} | {rec.estado} | {rec.warnings} | {rec.errors} | {rec.duracion_segundos:.2f} | "
            f"{'si' if rec.informe_generado else 'no'} | {'si' if rec.excel_generado else 'no'} | {rec.graficos_generados} |"
        )
    a("")
    return "\n".join(lines)
