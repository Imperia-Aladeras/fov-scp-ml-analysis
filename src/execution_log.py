"""Formato de lineas para execution.log (log global de una ejecucion, Fase 5A)."""

from __future__ import annotations

from datetime import datetime


def format_log_line(phase: str, message: str, timestamp: datetime | None = None) -> str:
    ts = (timestamp or datetime.now().astimezone()).isoformat()
    return f"{ts} [{phase}] {message}"
