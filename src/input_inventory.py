"""
Inventario inmutable de los CSV de entrada.

Se construye UNA vez, antes de llamar a `load_client_sources`, y se conserva
durante toda la ejecucion. Garantiza que el SHA-256 registrado en el
manifest corresponde exactamente a los bytes que se van a analizar, no a una
relectura posterior que podria ver un fichero ya modificado (p.ej. un CSV de
origen sobrescrito a mitad de ejecucion).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.input_loader import discover_csv_files
from src.manifest import compute_sha256


class InputIntegrityError(RuntimeError):
    """
    Se ha detectado una discrepancia entre los bytes analizados y los bytes
    archivados/originales. `code` identifica el tipo de discrepancia para
    que quede como `error_type` explicito en manifest.json (en vez del
    nombre generico de la clase de excepcion).
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InputFileRecord:
    name: str
    relative_path: str
    path: Path
    size_bytes: int | None
    modified_at: str | None
    mtime_ns: int | None
    sha256: str | None
    read_error: str | None


def _stat_and_hash(path: Path) -> tuple[int | None, str | None, int | None, str | None, str | None]:
    """Devuelve (size_bytes, modified_at, mtime_ns, sha256, read_error)."""
    try:
        stat = path.stat()
        size_bytes = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
        mtime_ns = stat.st_mtime_ns
        sha256 = compute_sha256(path)
        return size_bytes, modified_at, mtime_ns, sha256, None
    except OSError as exc:
        return None, None, None, None, str(exc)


def build_input_inventory(input_dir: Path) -> list[InputFileRecord]:
    """
    Descubre todos los CSV de input_dir y calcula tamano, fecha de
    modificacion (ISO 8601 y mtime_ns de precision) y SHA-256 de sus bytes
    originales, ANTES de cualquier intento de parseo. Un fichero illegible en
    este punto queda registrado igualmente (con `read_error`), nunca se omite
    de la lista.
    """
    records = []
    for path in discover_csv_files(input_dir):
        size_bytes, modified_at, mtime_ns, sha256, read_error = _stat_and_hash(path)
        records.append(InputFileRecord(
            name=path.name, relative_path=str(path.relative_to(input_dir)), path=path,
            size_bytes=size_bytes, modified_at=modified_at, mtime_ns=mtime_ns,
            sha256=sha256, read_error=read_error,
        ))
    return records


def verify_copies_match_originals(inventory: list[InputFileRecord], inputs_dir: Path) -> None:
    """
    Tras copiar los CSV a <run-temp>/inputs/ (--copy-inputs), comprueba que
    el SHA-256 de cada copia coincide con el del original capturado en el
    inventario. La copia archivada debe ser exactamente los bytes que se
    van a analizar.
    """
    mismatches: list[str] = []
    for record in inventory:
        if record.read_error is not None:
            continue  # no se pudo leer ni hashear el original: no se copio, no hay nada que verificar
        copy_path = inputs_dir / record.name
        try:
            copy_sha256 = compute_sha256(copy_path)
        except OSError as exc:
            mismatches.append(f"{record.name} (no se pudo leer la copia: {exc})")
            continue
        if copy_sha256 != record.sha256:
            mismatches.append(record.name)
    if mismatches:
        raise InputIntegrityError(
            "INPUT_COPY_MISMATCH",
            f"{len(mismatches)} copia(s) en inputs/ no coinciden con el CSV original: {mismatches}",
        )


def verify_originals_unchanged(inventory: list[InputFileRecord]) -> list[str]:
    """
    Al terminar el procesamiento (sin --copy-inputs), comprueba que ningun
    CSV original ha cambiado durante la ejecucion:

    - cambio de tamano o de SHA-256 (contenido real distinto, o el fichero ya
      no se puede releer): FATAL, lanza InputIntegrityError
      (INPUT_CHANGED_DURING_RUN). No se publica el resultado.
    - cambio unicamente de mtime_ns con el mismo tamano y el mismo SHA-256
      (los bytes analizados siguen siendo exactamente los mismos; p.ej. un
      `touch`, una resincronizacion de metadatos, o una copia que preserva
      contenido pero no el timestamp exacto): NO fatal. Se devuelve la lista
      de nombres afectados para que el llamador registre un warning
      (INPUT_METADATA_CHANGED) sin bloquear ni invalidar la ejecucion.
    """
    changed: list[str] = []
    metadata_only: list[str] = []
    for record in inventory:
        if record.read_error is not None:
            continue  # ya estaba en error desde el inventario inicial: no es un cambio nuevo detectable aqui
        size_bytes, _modified_at, mtime_ns, sha256, read_error = _stat_and_hash(record.path)
        if read_error is not None or size_bytes != record.size_bytes or sha256 != record.sha256:
            changed.append(record.name)
        elif mtime_ns != record.mtime_ns:
            metadata_only.append(record.name)
    if changed:
        raise InputIntegrityError(
            "INPUT_CHANGED_DURING_RUN",
            f"{len(changed)} CSV han cambiado durante la ejecucion: {changed}",
        )
    return metadata_only
