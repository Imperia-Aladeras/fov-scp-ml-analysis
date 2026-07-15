"""
Formatters centralizados para el informe HTML (Fase 5B).

Ningun valor ausente (`None`, `NaN`, `inf`, `-inf`) debe llegar nunca al HTML
visible como su representacion interna de Python/NumPy/pandas: siempre se
convierte a "N/D" o a una frase equivalente. Estos formatters son la UNICA
via por la que los view models producen texto formateado; los templates no
formatean numeros directamente.
"""

from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import quote

NA_TEXT = "N/D"


def is_missing(x) -> bool:
    if x is None:
        return True
    if isinstance(x, float):
        return math.isnan(x) or math.isinf(x)
    return False


def fmt_na(x, formatter=str) -> str:
    """Aplica `formatter` solo si `x` no es un valor ausente; si no, N/D."""
    if is_missing(x):
        return NA_TEXT
    return formatter(x)


def fmt_pct_fraction(x, decimals: int = 1) -> str:
    """Formatea una fraccion 0-1 (p.ej. WAPE) como porcentaje."""
    if is_missing(x):
        return NA_TEXT
    return f"{x * 100:.{decimals}f}%"


def fmt_pct_scaled(x, decimals: int = 1) -> str:
    """Formatea un valor ya expresado en base 100 (mejora, cobertura, tasas)."""
    if is_missing(x):
        return NA_TEXT
    return f"{x:.{decimals}f}%"


def fmt_signed_pct(x, decimals: int = 1) -> str:
    if is_missing(x):
        return NA_TEXT
    return f"{x:+.{decimals}f}%"


def fmt_num(x, decimals: int = 0) -> str:
    """Numero con separador de miles '.' y decimal ',' (convencion es-ES)."""
    if is_missing(x):
        return NA_TEXT
    integer_part, _, decimal_part = f"{x:,.{decimals}f}".partition(".")
    integer_part = integer_part.replace(",", ".")
    return f"{integer_part},{decimal_part}" if decimal_part else integer_part


def fmt_int(x) -> str:
    return fmt_num(x, 0)


def fmt_bool_si_no(x) -> str:
    if x is None:
        return NA_TEXT
    return "Sí" if x else "No"


def fmt_fraction_of(numerator, denominator, unit_label: str = "clientes") -> str:
    """
    '6 de 7 clientes evaluables', nunca solo un porcentaje aislado (ver
    seccion 6.2 de la especificacion: numerador y denominador siempre
    explicitos).
    """
    if is_missing(numerator) or is_missing(denominator):
        return NA_TEXT
    return f"{fmt_int(numerator)} de {fmt_int(denominator)} {unit_label}"


def fmt_datetime(dt) -> str:
    if dt is None:
        return NA_TEXT
    return dt.strftime("%d/%m/%Y %H:%M:%S %z")


def fmt_duration_seconds(seconds) -> str:
    if is_missing(seconds):
        return NA_TEXT
    seconds = float(seconds)
    minutes, secs = divmod(seconds, 60)
    if minutes >= 1:
        return f"{int(minutes)} min {secs:.1f} s"
    return f"{secs:.2f} s"


def encode_url_path(path: str) -> str:
    """
    Codifica cada segmento de una ruta URL relativa (separada por '/') de
    forma independiente: nunca codifica el propio separador. Necesario para
    nombres de cliente con espacios, acentos u otros caracteres validos en
    un nombre de fichero pero que deben codificarse en una URL.
    """
    if not path:
        return path
    return "/".join(quote(segment, safe="") for segment in path.split("/"))


def to_posix(path) -> str:
    """Normaliza una ruta (Path o str, con separadores de cualquier SO) a forma POSIX ('/')."""
    return "/".join(Path(path).parts)
