"""
Catalogo local de nombres descriptivos de cliente (config/client-catalog.json).

ID_CLIENT es siempre la identidad canonica; el nombre del catalogo es
unicamente una etiqueta de presentacion, nunca una clave de agrupacion ni
de filtrado.

Este modulo es deliberadamente aislado (Fase 1): no se integra todavia en
el pipeline, no imprime nada, no escribe en ningun log y no produce ningun
efecto secundario. `load_client_catalog` nunca lanza: cualquier problema de
lectura o de contenido degrada a un catalogo vacio, devolviendo ademas un
texto explicativo para que un futuro integrador decida como presentarlo
(consola, execution.log, manifest...). La ausencia del fichero es un estado
valido, no una degradacion, y por eso no genera warning.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from src.input_loader import normalize_folder_name


def _loads_object_detecting_duplicate_keys(text: str) -> tuple[object, list[str]]:
    """
    Envoltorio minimo sobre json.loads que detecta claves JSON textuales
    duplicadas dentro de un mismo objeto, en vez de aceptar en silencio el
    comportamiento estandar de json.loads (el ultimo valor gana). No
    introduce ninguna abstraccion nueva: es un unico hook privado de uso
    interno, sin superficie publica.
    """
    duplicate_keys: list[str] = []

    def _hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        seen: dict[str, object] = {}
        for key, value in pairs:
            if key in seen:
                duplicate_keys.append(key)
            seen[key] = value
        return seen

    raw = json.loads(text, object_pairs_hook=_hook)
    return raw, duplicate_keys


def load_client_catalog(path: Path) -> tuple[dict[int, str], str | None]:
    """
    Carga config/client-catalog.json de forma defensiva. Nunca lanza.

    Devuelve (catalog, warning):
      - catalog: dict[int, str] con unicamente las entradas estructuralmente
        validas. Un fichero ausente o un objeto JSON vacio ({}) son estados
        validos y devuelven {} sin warning.
      - warning: None cuando no hubo nada que degradar; en caso contrario,
        una descripcion textual del problema. Nunca se imprime ni se
        escribe en ningun log desde aqui.

    Los valores se conservan exactamente como aparecen en el JSON: no se
    recortan ni se normalizan (ver docstring de modulo).
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}, None
    except (OSError, UnicodeDecodeError) as exc:
        return {}, f"No se pudo leer {path}: {exc}"

    try:
        raw, duplicate_keys = _loads_object_detecting_duplicate_keys(text)
    except json.JSONDecodeError as exc:
        return {}, f"El catalogo {path} no es JSON valido: {exc}"

    if duplicate_keys:
        return {}, (
            f"El catalogo {path} contiene {len(duplicate_keys)} clave(s) JSON "
            f"duplicada(s), lo que lo hace ambiguo: {sorted(set(duplicate_keys))}. "
            f"No se selecciona ningun valor de forma arbitraria."
        )

    if not isinstance(raw, dict):
        return {}, f"La raiz de {path} no es un objeto JSON (tipo {type(raw).__name__})."

    catalog: dict[int, str] = {}
    n_skipped = 0
    colliding_ids: set[int] = set()
    for key, value in raw.items():
        try:
            id_client = int(key)
        except (TypeError, ValueError):
            n_skipped += 1
            continue
        if not isinstance(value, str) or value.strip() == "":
            n_skipped += 1
            continue
        if id_client in catalog:
            colliding_ids.add(id_client)
            continue
        catalog[id_client] = value

    if colliding_ids:
        return {}, (
            f"El catalogo {path} contiene claves JSON distintas que normalizan "
            f"al mismo ID_CLIENT ({sorted(colliding_ids)}), lo que lo hace "
            f"ambiguo. No se selecciona ningun valor de forma arbitraria."
        )

    warning = None
    if n_skipped:
        warning = (
            f"{n_skipped} entrada(s) de {path} se ignoraron por ser "
            f"estructuralmente invalidas (clave no convertible a ID_CLIENT, "
            f"valor no textual, o nombre vacio/solo espacios); el resto del "
            f"catalogo ({len(catalog)} entrada(s)) se usa con normalidad."
        )
    return catalog, warning


def resolve_client_name(id_client: int, catalog: Mapping[int, str]) -> str:
    """
    Resuelve el nombre de presentacion de un cliente. ID_CLIENT sigue siendo
    la identidad canonica; el valor devuelto es unicamente una etiqueta de
    presentacion, nunca se usa para agrupar ni para filtrar.
    """
    return catalog.get(id_client, f"Cliente {id_client}")


_INTERNAL_WHITESPACE = re.compile(r"\s+")


def slugify_display_name(display_name: str) -> str:
    """
    Deriva un slug minimo y deterministico de un display_name ya resuelto
    (Fase 5): recorta espacios exteriores, pasa a minusculas UNICAMENTE en
    el slug (display_name conserva su capitalizacion original en todo lo
    demas), colapsa el whitespace interno a un unico guion, y reutiliza
    normalize_folder_name (src/input_loader.py) para sustituir caracteres
    incompatibles con rutas de Windows. Nunca translitera Unicode/acentos a
    ASCII: "Aldelís" -> "aldelís", no "aldelis".
    """
    text = display_name.strip().lower()
    text = _INTERNAL_WHITESPACE.sub("-", text)
    return normalize_folder_name(text)


def build_client_folder_name(id_client: int, display_name: str) -> str:
    """
    Nombre tecnico de carpeta/fichero por cliente (Fase 5):
    `{id_client}-{slug(display_name)}`. ID_CLIENT como prefijo es la unica
    garantia de unicidad: dos clientes con el mismo display_name (el
    catalogo no impide duplicados, ver config/client-catalog.json) producen
    el mismo slug pero un folder_name distinto.
    """
    return f"{id_client}-{slugify_display_name(display_name)}"
