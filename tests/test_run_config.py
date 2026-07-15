import re
from datetime import datetime
from pathlib import Path

import pytest

from src.run_config import (
    MAX_RUN_NAME_LENGTH,
    RunNameError,
    build_arg_parser,
    build_run_config,
    default_run_name,
    sanitize_run_name,
)
from src.version import PIPELINE_VERSION


def test_default_run_name_matches_timestamp_pattern():
    assert re.fullmatch(r"\d{8}_\d{6}", default_run_name())


def test_build_arg_parser_defaults(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args([])
    assert args.input_dir == tmp_path / "data"
    assert args.output_root == tmp_path / "outputs" / "runs"
    assert args.run_name is None
    assert args.overwrite is False
    assert args.copy_inputs is False


def test_build_arg_parser_explicit_params(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args([
        "--input-dir", str(tmp_path / "custom_in"),
        "--output-root", str(tmp_path / "custom_out"),
        "--run-name", "validacion_septiembre_2026",
        "--overwrite", "--copy-inputs",
    ])
    assert args.input_dir == tmp_path / "custom_in"
    assert args.output_root == tmp_path / "custom_out"
    assert args.run_name == "validacion_septiembre_2026"
    assert args.overwrite is True
    assert args.copy_inputs is True


def test_sanitize_run_name_keeps_readable_label():
    assert sanitize_run_name("validacion_septiembre_2026") == "validacion_septiembre_2026"


def test_sanitize_run_name_substitutes_benign_forbidden_chars():
    assert sanitize_run_name('run:name|weird?') == "run_name_weird_"


def test_sanitize_run_name_rejects_path_traversal():
    with pytest.raises(RunNameError):
        sanitize_run_name("../evil")
    with pytest.raises(RunNameError):
        sanitize_run_name("foo/../bar")
    with pytest.raises(RunNameError):
        sanitize_run_name("..")


def test_sanitize_run_name_keeps_harmless_multiple_dots():
    """'...' o 'foo..bar' no navegan ningun directorio (no hay separador): son nombres literales validos."""
    assert sanitize_run_name("foo..bar") == "foo..bar"


def test_sanitize_run_name_rejects_directory_separators():
    with pytest.raises(RunNameError):
        sanitize_run_name("sub/dir")
    with pytest.raises(RunNameError):
        sanitize_run_name("sub\\dir")


def test_sanitize_run_name_rejects_absolute_and_drive_paths():
    with pytest.raises(RunNameError):
        sanitize_run_name("C:\\evil")
    with pytest.raises(RunNameError):
        sanitize_run_name("/etc/passwd")


def test_sanitize_run_name_falls_back_to_timestamp_when_empty_after_sanitizing():
    result = sanitize_run_name("   ...   ")
    assert re.fullmatch(r"\d{8}_\d{6}", result)


def test_sanitize_run_name_limits_length():
    result = sanitize_run_name("a" * 500)
    assert len(result) <= MAX_RUN_NAME_LENGTH


def test_sanitize_run_name_avoids_windows_reserved_names():
    assert sanitize_run_name("CON") == "CON_run"
    assert sanitize_run_name("com1") == "com1_run"
    assert sanitize_run_name("NUL.txt") == "NUL.txt_run"


def test_build_run_config_computes_direct_children_of_output_root(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args(["--run-name", "mi_run"])
    cfg = build_run_config(args, tmp_path, started_at=datetime(2026, 7, 15, 10, 0, 0).astimezone())

    assert cfg.run_name_effective == "mi_run"
    assert cfg.run_dir_temp.parent == cfg.output_root
    assert cfg.run_dir_final.parent == cfg.output_root
    assert cfg.run_dir_backup.parent == cfg.output_root
    assert cfg.pipeline_version == PIPELINE_VERSION


def test_build_run_config_serializes_to_dict_without_python_objects(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args(["--run-name", "mi_run", "--copy-inputs"])
    cfg = build_run_config(args, tmp_path)
    data = cfg.to_run_config_dict()

    assert data["run_name_requested"] == "mi_run"
    assert data["run_name_effective"] == "mi_run"
    assert data["copy_inputs"] is True
    assert data["overwrite"] is False
    assert data["pipeline_version"] == PIPELINE_VERSION
    assert isinstance(data["input_dir"], str)
    assert isinstance(data["output_root"], str)
    assert isinstance(data["started_at"], str)

    import json
    json.dumps(data)  # no debe lanzar: solo tipos serializables


def test_build_run_config_propagates_run_name_error_for_dangerous_names(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args(["--run-name", "../escape"])
    with pytest.raises(RunNameError):
        build_run_config(args, tmp_path)


def test_build_run_config_uses_timestamp_when_run_name_not_given(tmp_path: Path):
    parser = build_arg_parser(tmp_path)
    args = parser.parse_args([])
    cfg = build_run_config(args, tmp_path)
    assert re.fullmatch(r"\d{8}_\d{6}", cfg.run_name_effective)
