"""
Configuracion tipada de una ejecucion del pipeline (Fase 5A) y saneamiento
del nombre de ejecucion (--run-name).

RunConfig es la unica fuente de rutas de una ejecucion: se construye una vez
en el orquestador (analysis_fov_scp_ml.py) y se inyecta a los writers y
generadores existentes. Ningun otro modulo mantiene variables globales de
rutas de ejecucion.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.version import PIPELINE_VERSION

MAX_RUN_NAME_LENGTH = 100

_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Caracteres que se SANEAN por sustitucion (benignos): prohibidos en rutas de
# Windows pero que no indican un intento de escapar de --output-root.
_BENIGN_FORBIDDEN_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


class RunNameError(ValueError):
    """
    run-name contiene un patron no saneable de forma segura: path traversal,
    ruta absoluta, drive de Windows o separador de directorios. Estos
    patrones no se sustituyen, se RECHAZAN explicitamente. El llamador debe
    devolver el codigo de salida 2 sin procesar ningun CSV.
    """


def now_local() -> datetime:
    """Timestamp local con zona horaria adjunta (ISO 8601 con offset)."""
    return datetime.now().astimezone()


def default_run_name() -> str:
    return now_local().strftime("%Y%m%d_%H%M%S")


def _reject_dangerous_patterns(raw: str) -> None:
    # El separador es la condicion necesaria para que ".." pueda navegar mas
    # de un nivel (p.ej. "../evil", "foo/../bar"): se rechaza primero.
    if "/" in raw or "\\" in raw:
        raise RunNameError(f"run-name contiene un separador de directorios ('/' o '\\'): {raw!r}")
    if _DRIVE_PATTERN.match(raw):
        raise RunNameError(f"run-name parece un drive de Windows (p.ej. 'C:'): {raw!r}")
    # Sin separadores, todo el valor es un unico segmento: solo es peligroso
    # si ese segmento completo es literalmente ".." (sube un nivel al unirlo
    # con output-root). "..." o "foo..bar" no navegan nada, son nombres
    # literales validos y no deben rechazarse.
    if raw.strip() == "..":
        raise RunNameError(f"run-name es un patron de path traversal ('..'): {raw!r}")


def sanitize_run_name(raw: str) -> str:
    """
    Sanea caracteres benignos por sustitucion (predecible: se reemplazan por
    '_'). Rechaza (RunNameError) los patrones peligrosos: path traversal,
    rutas absolutas, drives de Windows y separadores de directorios: esos
    NO se sanean, se rechazan. Si el resultado saneado queda vacio, usa el
    timestamp actual. Limita la longitud a MAX_RUN_NAME_LENGTH y evita
    nombres reservados de Windows (CON, NUL, COM1...).
    """
    _reject_dangerous_patterns(raw)

    name = _BENIGN_FORBIDDEN_CHARS.sub("_", raw.strip())
    name = name.strip(" .")
    if len(name) > MAX_RUN_NAME_LENGTH:
        name = name[:MAX_RUN_NAME_LENGTH].strip(" .")
    if not name:
        return default_run_name()
    if name.split(".")[0].upper() in _RESERVED_WINDOWS_NAMES:
        name = f"{name}_run"
    return name


def build_arg_parser(base_dir: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analysis_fov_scp_ml.py",
        description=(
            "Pipeline reproducible de comparativa SCP Classic Auto vs SCP Classic Optimizer: "
            "ejecuciones aisladas y trazables, "
            "con informe HTML, Excel y Markdown por ejecucion."
        ),
    )
    parser.add_argument(
        "--input-dir", type=Path, default=base_dir / "data",
        help="Carpeta con los CSV de entrada. Por defecto: <repo>/data.",
    )
    parser.add_argument(
        "--output-root", type=Path, default=base_dir / "outputs" / "runs",
        help="Carpeta raiz donde se publican las ejecuciones. Por defecto: <repo>/outputs/runs.",
    )
    parser.add_argument(
        "--run-name", type=str, default=None,
        help="Nombre de la ejecucion. Por defecto: timestamp local YYYYMMDD_HHMMSS.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Permite sustituir una ejecucion existente con el mismo nombre.",
    )
    parser.add_argument(
        "--copy-inputs", action="store_true", default=False,
        help="Copia los CSV originales dentro de la ejecucion (inputs/).",
    )
    parser.add_argument(
        "--open-report", action="store_true", default=False,
        help=(
            "Abre index.html en el navegador por defecto tras publicar la ejecucion. "
            "Accion de conveniencia posterior a la publicacion: nunca afecta al resultado "
            "del analisis ni al codigo de salida."
        ),
    )
    parser.add_argument(
        "--rebuild-run-index", action="store_true", default=False,
        help=(
            "Modo separado (Fase 5C): reconstruye unicamente el catalogo historico de "
            "ejecuciones de --output-root, sin analizar ningun CSV ni crear un run nuevo. "
            "Incompatible con --input-dir, --run-name, --overwrite, --copy-inputs y "
            "--open-report; solo admite --output-root."
        ),
    )
    return parser


def build_rebuild_index_arg_parser(base_dir: Path) -> argparse.ArgumentParser:
    """
    Parser DEDICADO al modo --rebuild-run-index (Fase 5C): reconoce
    UNICAMENTE --rebuild-run-index y --output-root. Cualquier otro
    argumento del parser normal (--input-dir, --run-name, --overwrite,
    --copy-inputs, --open-report) es "unrecognized argument" para este
    parser (argparse llama a sys.exit(2) automaticamente con un mensaje de
    error): no hay ninguna ambiguedad posible entre "el usuario no
    proporciono el argumento" y "el usuario proporciono el valor por
    defecto", porque esos argumentos ni siquiera existen en este modo.
    """
    parser = argparse.ArgumentParser(
        prog="analysis_fov_scp_ml.py --rebuild-run-index",
        description="Reconstruye el catalogo historico de ejecuciones de --output-root (Fase 5C). No procesa CSV.",
    )
    parser.add_argument("--rebuild-run-index", action="store_true", default=False)
    parser.add_argument(
        "--output-root", type=Path, default=base_dir / "outputs" / "runs",
        help="Carpeta raiz cuyas ejecuciones publicadas se catalogan. Por defecto: <repo>/outputs/runs.",
    )
    return parser


def _ensure_direct_child(path: Path, parent: Path) -> None:
    if path.parent != parent:
        raise RunNameError(f"Ruta de ejecucion invalida: {path} no es hijo directo de {parent}.")


@dataclass(frozen=True)
class RunConfig:
    input_dir: Path
    output_root: Path
    run_name_requested: str
    run_name_effective: str
    copy_inputs: bool
    overwrite: bool
    started_at: datetime
    open_report: bool = False
    pipeline_version: str = PIPELINE_VERSION

    @property
    def run_dir_temp(self) -> Path:
        return self.output_root / f".{self.run_name_effective}.tmp"

    @property
    def run_dir_backup(self) -> Path:
        return self.output_root / f".{self.run_name_effective}.backup"

    @property
    def run_dir_final(self) -> Path:
        return self.output_root / self.run_name_effective

    @property
    def clients_dir(self) -> Path:
        return self.run_dir_temp / "clients"

    @property
    def global_dir(self) -> Path:
        return self.run_dir_temp / "global"

    @property
    def inputs_dir(self) -> Path:
        return self.run_dir_temp / "inputs"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir_temp / "manifest.json"

    @property
    def run_config_path(self) -> Path:
        return self.run_dir_temp / "run_config.json"

    @property
    def execution_log_path(self) -> Path:
        return self.run_dir_temp / "execution.log"

    @property
    def execution_summary_md_path(self) -> Path:
        return self.run_dir_temp / "execution_summary.md"

    @property
    def execution_summary_xlsx_path(self) -> Path:
        return self.run_dir_temp / "execution_summary.xlsx"

    @property
    def publish_marker_path(self) -> Path:
        """
        Marca durable de publicacion completa: solo existe dentro de
        run_dir_final, y solo se crea como ULTIMO paso de la transaccion de
        publicacion, despues de que manifest.json y execution.log se hayan
        actualizado con exito. Es la unica senal fiable de que una
        publicacion se completo por entero (nunca el contenido de
        manifest.json, que puede decir published=true sin que la
        publicacion se haya completado realmente si el proceso murio justo
        despues de ese paso).
        """
        return self.run_dir_final / ".publish_complete"

    def to_run_config_dict(self) -> dict:
        return {
            "input_dir": str(self.input_dir),
            "output_root": str(self.output_root),
            "run_name_requested": self.run_name_requested,
            "run_name_effective": self.run_name_effective,
            "copy_inputs": self.copy_inputs,
            "overwrite": self.overwrite,
            "open_report": self.open_report,
            "pipeline_version": self.pipeline_version,
            "started_at": self.started_at.isoformat(),
        }


def build_run_config(args: argparse.Namespace, base_dir: Path, started_at: datetime | None = None) -> RunConfig:
    """
    Construye un RunConfig a partir de argumentos ya parseados. Funcion pura
    (no toca disco): la validacion de existencia/colision de directorios se
    hace en el orquestador. Puede lanzar RunNameError si --run-name contiene
    un patron peligroso no saneable.
    """
    run_name_requested = args.run_name if args.run_name is not None else default_run_name()
    run_name_effective = sanitize_run_name(run_name_requested)
    output_root = Path(args.output_root).resolve()
    input_dir = Path(args.input_dir).resolve()

    cfg = RunConfig(
        input_dir=input_dir, output_root=output_root,
        run_name_requested=run_name_requested, run_name_effective=run_name_effective,
        copy_inputs=bool(args.copy_inputs), overwrite=bool(args.overwrite),
        started_at=started_at or now_local(), open_report=bool(args.open_report),
        pipeline_version=PIPELINE_VERSION,
    )
    _ensure_direct_child(cfg.run_dir_temp, cfg.output_root)
    _ensure_direct_child(cfg.run_dir_final, cfg.output_root)
    return cfg
