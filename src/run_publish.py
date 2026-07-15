"""
Publicacion transaccional de una ejecucion: run_dir_temp -> run_dir_final.

El renombrado del directorio, la actualizacion de manifest.json
(published=true, output_dir_working=null), el registro final en
execution.log, y la creacion de una marca durable de publicacion completa
(.publish_complete) se tratan como una unica transaccion:

- si existe una ejecucion anterior con el mismo nombre, se mueve primero a
  un backup temporal;
- el temporal nuevo se renombra a final;
- se actualizan OBLIGATORIAMENTE manifest.json (de forma atomica, ver
  `_atomic_write_json`) y execution.log en su ubicacion final (nunca de
  forma best-effort: un fallo aqui se propaga);
- solo cuando ambos han tenido exito se crea `.publish_complete` dentro de
  final: es el ULTIMO paso de la transaccion;
- solo despues de crear esa marca se elimina el backup.

Si el renombrado inicial falla, nada se ha tocado todavia (aparte de mover
la ejecucion anterior a backup, que se restaura). Si el renombrado tiene
exito pero la actualizacion de manifest/log/marca falla (OSError o
json.JSONDecodeError sobre un manifest corrupto), la publicacion se deshace
POR COMPLETO: el directorio final vuelve a moverse al temporal (integro,
para diagnostico) y la ejecucion anterior, si la habia, se restaura desde el
backup, antes de propagar la excepcion original. Nunca se devuelve exito de
forma silenciosa cuando la finalizacion queda incompleta: el llamador
(analysis_fov_scp_ml.main) debe tratar cualquier excepcion de este modulo
como fallo de publicacion (codigo de salida 1) y dejar constancia en el
manifest que ha quedado en el temporal.

`reconcile_interrupted_publication` repara el estado de disco que puede
dejar una interrupcion ABRUPTA (proceso matado, corte de energia/Windows) en
CUALQUIER punto de esa transaccion, incluidos casos que publish_run() nunca
llega a ver porque el proceso murio antes de que su propio try/except
pudiera reaccionar. La unica senal fiable que usa es la presencia de
`.publish_complete` dentro de `final`: nunca el contenido de manifest.json.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from src.execution_log import format_log_line
from src.run_config import RunConfig, now_local

# En Windows, renombrar un directorio recien escrito puede fallar de forma
# TRANSITORIA (WinError 5, Access is denied) si un antivirus o el indexador
# de busqueda mantiene abierto brevemente un fichero justo despues de
# cerrarlo (observado con los .xlsx/.png que acaba de escribir el pipeline).
# Se reintenta con un backoff corto antes de propagar el error como
# definitivo.
_RENAME_RETRY_ATTEMPTS = 5
_RENAME_RETRY_BASE_DELAY_SECONDS = 0.15


def _rename_with_retry(src, dst) -> None:
    last_exc: OSError | None = None
    for attempt in range(_RENAME_RETRY_ATTEMPTS):
        try:
            os.rename(src, dst)
            return
        except OSError as exc:
            last_exc = exc
            if attempt < _RENAME_RETRY_ATTEMPTS - 1:
                time.sleep(_RENAME_RETRY_BASE_DELAY_SECONDS * (attempt + 1))
    raise last_exc


def reconcile_interrupted_publication(run_config: RunConfig) -> None:
    """
    Repara el estado de disco que puede dejar una interrupcion abrupta
    durante publish_run(), en cualquier punto de la transaccion. Se invoca
    al principio de cada ejecucion, antes de crear el temporal nuevo.

    La UNICA senal fiable de que una publicacion se completo por entero es
    la presencia de `.publish_complete` dentro de `final`. Nunca se usa el
    contenido de manifest.json para decidir si una ejecucion esta completa:
    puede decir `published=true` sin que la publicacion se haya completado
    realmente (p.ej. si el proceso murio justo despues de patchear el
    manifest pero antes de escribir el log o crear la marca).

    Casos:
      1. backup existe, final no existe -> se restaura backup a final.
      2. backup y final existen, final SI tiene la marca -> final es la
         publicacion completa; se elimina el backup.
      3. backup y final existen, final NO tiene la marca -> final es una
         publicacion interrumpida a medio camino: se mueve al temporal
         (se conserva integra para diagnostico) y se restaura backup a
         final. La ejecucion anterior valida nunca se pierde.
      4. final existe sin backup, SI tiene la marca -> no se hace nada: es
         una ejecucion previa completa y normal.
      5. final existe sin backup, NO tiene la marca -> se mueve al
         temporal; nunca se trata como publicada.
      6. ni backup ni final existen -> no-op.

    En ningun caso se elimina silenciosamente una ejecucion anterior valida.
    """
    backup = run_config.run_dir_backup
    final = run_config.run_dir_final
    temp = run_config.run_dir_temp
    marker = run_config.publish_marker_path

    backup_exists = backup.exists()
    final_exists = final.exists()

    if not backup_exists and not final_exists:
        return

    if backup_exists and not final_exists:
        _rename_with_retry(backup, final)
        return

    final_is_complete = marker.exists()

    if not backup_exists:
        if not final_is_complete:
            _rename_with_retry(final, temp)
        return

    # backup_exists and final_exists
    if final_is_complete:
        shutil.rmtree(backup)
    else:
        _rename_with_retry(final, temp)
        _rename_with_retry(backup, final)


def _atomic_write_json(path: Path, data: dict) -> None:
    """
    Escribe `data` como JSON de forma atomica: escribe primero un fichero
    temporal en el MISMO directorio, fuerza flush + fsync, y sustituye el
    fichero definitivo con os.replace (atomico a nivel de sistema de
    archivos en la misma unidad). Nunca se escribe directamente sobre el
    fichero definitivo: un fallo a mitad de escritura nunca deja `path`
    parcialmente escrito o corrupto.
    """
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _patch_manifest_published(run_config: RunConfig) -> None:
    """
    Marca manifest.json (ya en su ubicacion final) como publicado. NO es
    best-effort: propaga OSError (fichero no accesible/no escribible) y
    json.JSONDecodeError (manifest corrupto), porque forma parte de la
    transaccion de publicacion.
    """
    final_manifest_path = run_config.run_dir_final / "manifest.json"
    manifest = json.loads(final_manifest_path.read_text(encoding="utf-8"))
    manifest["published"] = True
    manifest["output_dir_working"] = None
    manifest["output_dir_final"] = str(run_config.run_dir_final)
    _atomic_write_json(final_manifest_path, manifest)


def _append_final_publish_log_line(run_config: RunConfig) -> None:
    """Anade el registro final de publicacion a execution.log (ya en su ubicacion final). Propaga OSError."""
    final_log_path = run_config.run_dir_final / "execution.log"
    with final_log_path.open("a", encoding="utf-8") as f:
        f.write(format_log_line("PUBLISH", f"publicado en {run_config.run_dir_final}") + "\n")


def _create_publish_complete_marker(run_config: RunConfig) -> None:
    """Ultimo paso de la transaccion de publicacion: crea la marca durable. Propaga OSError."""
    run_config.publish_marker_path.write_text(f"published_at={now_local().isoformat()}\n", encoding="utf-8")


def publish_run(run_config: RunConfig) -> None:
    """
    Publica run_dir_temp como run_dir_final. Si run_dir_final ya existe, lo
    mueve primero a un backup temporal (la ejecucion anterior se conserva
    intacta ahi).

    Tras el renombrado, actualiza manifest.json, execution.log y crea
    `.publish_complete` en su ubicacion final: si CUALQUIERA de estos tres
    pasos falla, la publicacion se deshace por completo (ver docstring del
    modulo) antes de propagar la excepcion. El backup solo se elimina
    cuando la finalizacion se ha completado con exito (marca creada).
    """
    temp = run_config.run_dir_temp
    final = run_config.run_dir_final
    backup = run_config.run_dir_backup

    if backup.exists():
        shutil.rmtree(backup)

    had_previous = final.exists()
    if had_previous:
        _rename_with_retry(final, backup)

    try:
        _rename_with_retry(temp, final)
    except OSError:
        if had_previous:
            _rename_with_retry(backup, final)
        raise

    try:
        _patch_manifest_published(run_config)
        _append_final_publish_log_line(run_config)
        _create_publish_complete_marker(run_config)
    except (OSError, json.JSONDecodeError):
        # la finalizacion no se completo: se deshace la publicacion entera.
        # la nueva ejecucion vuelve a su temporal, integra, para diagnostico.
        _rename_with_retry(final, temp)
        if had_previous:
            _rename_with_retry(backup, final)
        raise

    if had_previous:
        shutil.rmtree(backup)
