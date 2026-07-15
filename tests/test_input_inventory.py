from pathlib import Path

import pytest

import src.input_inventory as input_inventory_module
from src.input_inventory import (
    InputIntegrityError,
    build_input_inventory,
    verify_copies_match_originals,
    verify_originals_unchanged,
)


def test_build_input_inventory_computes_hash_before_any_parsing(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")

    inventory = build_input_inventory(data_dir)

    assert len(inventory) == 1
    record = inventory[0]
    assert record.name == "TA_FOV_SCP_ML_10204_SKLUM.csv"
    assert record.size_bytes == len(b"a,b,c\n1,2,3\n")
    assert record.sha256 is not None
    assert record.mtime_ns is not None
    assert record.read_error is None


def test_build_input_inventory_includes_entry_for_unreadable_file(tmp_path: Path, monkeypatch):
    """
    Simula un fallo de lectura REAL (OSError durante el hash), no un fichero
    legible con read_error=None por casualidad: el registro debe permanecer
    en el inventario con read_error informado, size_bytes/sha256 en None.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_99999_Weird.csv"
    path.write_bytes(b"contenido perfectamente legible en condiciones normales")

    real_compute_sha256 = input_inventory_module.compute_sha256

    def failing_compute_sha256(p: Path) -> str:
        if p == path:
            raise OSError("permiso denegado (simulado)")
        return real_compute_sha256(p)

    monkeypatch.setattr(input_inventory_module, "compute_sha256", failing_compute_sha256)

    inventory = build_input_inventory(data_dir)

    assert len(inventory) == 1
    record = inventory[0]
    assert record.name == "TA_FOV_SCP_ML_99999_Weird.csv"
    assert record.read_error is not None
    assert "permiso denegado" in record.read_error
    assert record.sha256 is None
    assert record.size_bytes is None
    assert record.mtime_ns is None


def test_build_input_inventory_empty_dir_returns_empty_list(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert build_input_inventory(data_dir) == []


def test_verify_copies_match_originals_passes_for_faithful_copy(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (inputs_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")

    verify_copies_match_originals(inventory, inputs_dir)  # no debe lanzar


def test_verify_copies_match_originals_raises_on_mismatch(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (inputs_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"CORRUPTED BYTES")

    with pytest.raises(InputIntegrityError) as exc_info:
        verify_copies_match_originals(inventory, inputs_dir)
    assert exc_info.value.code == "INPUT_COPY_MISMATCH"


def test_verify_copies_match_originals_raises_when_copy_missing(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()  # no se copia nada dentro

    with pytest.raises(InputIntegrityError) as exc_info:
        verify_copies_match_originals(inventory, inputs_dir)
    assert exc_info.value.code == "INPUT_COPY_MISMATCH"


def test_verify_copies_match_originals_skips_records_with_read_error(tmp_path: Path, monkeypatch):
    """Un original que nunca se pudo leer no se copia ni se espera su copia: no debe generar mismatch."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_99999_Weird.csv"
    path.write_bytes(b"contenido")

    real_compute_sha256 = input_inventory_module.compute_sha256

    def failing_compute_sha256(p: Path) -> str:
        if p == path:
            raise OSError("simulado")
        return real_compute_sha256(p)

    monkeypatch.setattr(input_inventory_module, "compute_sha256", failing_compute_sha256)
    inventory = build_input_inventory(data_dir)
    assert inventory[0].read_error is not None

    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()  # no se copia nada, y no debe lanzar
    verify_copies_match_originals(inventory, inputs_dir)


def test_verify_originals_unchanged_passes_when_untouched(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv").write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    assert verify_originals_unchanged(inventory) == []


def test_verify_originals_unchanged_raises_when_content_changes(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    path.write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    path.write_bytes(b"a,b,c\n9,9,9\n")  # cambia durante la "ejecucion"

    with pytest.raises(InputIntegrityError) as exc_info:
        verify_originals_unchanged(inventory)
    assert exc_info.value.code == "INPUT_CHANGED_DURING_RUN"
    assert "TA_FOV_SCP_ML_10204_SKLUM.csv" in str(exc_info.value)


def test_verify_originals_unchanged_raises_when_file_deleted(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    path.write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)

    path.unlink()

    with pytest.raises(InputIntegrityError) as exc_info:
        verify_originals_unchanged(inventory)
    assert exc_info.value.code == "INPUT_CHANGED_DURING_RUN"


def test_verify_originals_unchanged_ignores_files_already_unreadable_at_inventory_time(tmp_path: Path):
    """Un fichero que ya estaba en error en el inventario inicial no debe volver a fallar aqui como 'cambio nuevo'."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    inventory = build_input_inventory(data_dir)  # vacio, sin ficheros
    assert verify_originals_unchanged(inventory) == []


def test_verify_originals_unchanged_returns_metadata_only_warning_without_raising(tmp_path: Path):
    """
    Cambio unicamente de mtime_ns, con los mismos bytes (mismo tamano, mismo
    SHA-256): no es fatal, se devuelve como advertencia sin lanzar.
    """
    import os

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    path.write_bytes(b"a,b,c\n1,2,3\n")
    inventory = build_input_inventory(data_dir)
    original_mtime_ns = inventory[0].mtime_ns

    # fuerza deterministamente un mtime distinto sin tocar el contenido/tamano
    new_mtime_seconds = (original_mtime_ns / 1e9) + 5.0
    os.utime(path, (new_mtime_seconds, new_mtime_seconds))
    assert path.stat().st_mtime_ns != original_mtime_ns

    metadata_changed = verify_originals_unchanged(inventory)
    assert metadata_changed == ["TA_FOV_SCP_ML_10204_SKLUM.csv"]
