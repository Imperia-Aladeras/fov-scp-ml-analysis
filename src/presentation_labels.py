"""Canonical labels for Reporting presentation surfaces.

This module contains text only.  It deliberately has no dependency on the
analytics/model layers so HTML, Markdown, Excel, charts and CLI output can
share one vocabulary without changing technical contracts.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


SCP_CLASSIC_AUTO_LABEL = "SCP Classic Auto"
SCP_CLASSIC_OPTIMIZER_LABEL = "SCP Classic Optimizer"

AUTO_LABEL = "Auto"
OPTIMIZER_LABEL = "Optimizer"
TIE_LABEL = "Empate"

GENERAL_COMPARISON_LABEL = (
    f"{SCP_CLASSIC_AUTO_LABEL} vs {SCP_CLASSIC_OPTIMIZER_LABEL}"
)
DIRECTIONAL_COMPARISON_LABEL = f"{OPTIMIZER_LABEL} vs {AUTO_LABEL}"

RECENT_3M_LABEL = "3 meses recientes (M3–M1)"
OLDER_3M_LABEL = "3 meses anteriores (M6–M4)"
SEMESTER_LABEL = "Semestre completo (M1–M6)"

PERIOD_LABELS: Mapping[str, str] = MappingProxyType({
    "RECENT_3M": RECENT_3M_LABEL,
    "OLDER_3M": OLDER_3M_LABEL,
    "6M": SEMESTER_LABEL,
})

RAW_WINNER_SHORT_LABELS: Mapping[str, str] = MappingProxyType({
    "SCP": AUTO_LABEL,
    "ML": OPTIMIZER_LABEL,
    "TIE": TIE_LABEL,
})

RAW_WINNER_FULL_LABELS: Mapping[str, str] = MappingProxyType({
    "SCP": SCP_CLASSIC_AUTO_LABEL,
    "ML": SCP_CLASSIC_OPTIMIZER_LABEL,
    "TIE": TIE_LABEL,
})


def winner_short_label(value: object) -> object:
    """Translate a raw winner for display without mutating the source value."""
    return RAW_WINNER_SHORT_LABELS.get(value, value)
