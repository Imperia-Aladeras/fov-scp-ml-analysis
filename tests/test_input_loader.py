from pathlib import Path

import pandas as pd

from src.input_loader import (
    ClientSource,
    coerce_numeric_columns,
    discover_csv_files,
    extract_id_from_label,
    extract_label_from_filename,
    has_identification_columns,
    is_parseable_as_csv,
    load_client_sources,
    normalize_folder_name,
    read_csv_defensive,
    unwrap_double_quoted_line,
)
from src.quality_checks import Severity

SIMPLE_HEADER = "ID,ID_BATCH,ID_RUN_STAGING,ID_CLIENT,SOURCE_RUN_ID,ID_CONFIGURATION,VALUE_LEVEL_1"


def _wrap_line_like_source_defect(line: str) -> str:
    """Reproduce el defecto real: la linea completa envuelta en comillas CSV,
    con las comillas internas dobladas."""
    return '"' + line.replace('"', '""') + '"'


def test_discover_csv_files_finds_only_csv_and_is_sorted(tmp_path: Path):
    (tmp_path / "b.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hola", encoding="utf-8")

    found = discover_csv_files(tmp_path)
    assert [p.name for p in found] == ["a.csv", "b.csv"]


def test_extract_label_from_filename_strips_prefix_and_extension():
    label = extract_label_from_filename(Path("TA_FOV_SCP_ML_10204_SKLUM.csv"))
    assert label == "10204_SKLUM"


def test_extract_id_from_label_parses_leading_digits():
    assert extract_id_from_label("10204_SKLUM") == 10204
    assert extract_id_from_label("SKLUM") is None


def test_normalize_folder_name_keeps_underscores_and_replaces_forbidden_chars():
    assert normalize_folder_name("10204_SKLUM") == "10204_SKLUM"
    assert normalize_folder_name('10467_Client:Name/Weird*') == "10467_Client_Name_Weird_"


def test_unwrap_double_quoted_line_recovers_original():
    original = 'ID,"ID_BATCH","ID_RUN_STAGING"'
    wrapped = _wrap_line_like_source_defect(original)
    assert unwrap_double_quoted_line(wrapped) == original


def test_unwrap_double_quoted_line_leaves_unwrapped_line_unchanged():
    line = "ID,ID_BATCH,ID_RUN_STAGING"
    assert unwrap_double_quoted_line(line) == line


def test_read_csv_defensive_standard_well_formed_csv(tmp_path: Path):
    """Item 5: CSV estandar valido -> no se intenta ninguna reparacion."""
    path = tmp_path / "clean.csv"
    path.write_text(SIMPLE_HEADER + "\n1,63,63,10204,1,23,DECORACION\n", encoding="utf-8")

    result = read_csv_defensive(path)
    assert result.error is None
    assert result.repaired is False
    assert list(result.dataframe.columns) == SIMPLE_HEADER.split(",")
    assert result.dataframe.loc[0, "ID_CLIENT"] == 10204


def test_read_csv_defensive_repairs_double_quoted_lines(tmp_path: Path):
    """
    Item 5: CSV envuelto valido. Reproduce el defecto real de los CSV de
    origen: cada linea fisica (cabecera y filas) envuelta en una capa extra
    de comillas CSV, incluyendo un campo con coma y comillas internas.
    """
    row = '2,63,63,10204,1,44,"Cuadros, Lienzos"'
    physical_lines = [SIMPLE_HEADER, row]
    wrapped_text = "\n".join(_wrap_line_like_source_defect(line) for line in physical_lines)

    path = tmp_path / "corrupted.csv"
    bom = "﻿"
    path.write_text(bom + wrapped_text, encoding="utf-8")

    result = read_csv_defensive(path)
    assert result.error is None
    assert result.repaired is True
    assert result.standard_reject_reason is not None
    assert result.n_rows_recovered == 1
    assert list(result.dataframe.columns) == SIMPLE_HEADER.split(",")
    assert int(result.dataframe.loc[0, "ID_CLIENT"]) == 10204
    assert result.dataframe.loc[0, "VALUE_LEVEL_1"] == "Cuadros, Lienzos"


def test_read_csv_defensive_unreadable_file_returns_error(tmp_path: Path):
    path = tmp_path / "garbage.csv"
    path.write_bytes(b"\xff\xfe\x00\x01not really a csv at all {{{")

    result = read_csv_defensive(path)
    assert result.dataframe is None
    assert result.error is not None


def test_read_csv_defensive_corrupted_csv_not_matching_wrap_pattern_is_not_repaired(tmp_path: Path):
    """
    Item 5: un CSV realmente corrupto (no envuelto en comillas dobladas, con
    una comilla suelta que rompe la tokenizacion) no debe repararse como si
    seguueria el patron de envoltorio conocido. Debe fallar con un error
    explicito, sin inventar una reparacion.
    """
    header = SIMPLE_HEADER  # sin envolver, 7 columnas
    # comas sin escapar dentro de valores que deberian ir citados, con un
    # numero de campos inconsistente entre filas: pandas no puede tokenizar
    # esto de forma estandar (ParserError), y las lineas no siguen el patron
    # de envoltorio de comillas dobladas conocido.
    row1 = "1,63,63,10204,1,23,Some, Bad, Text"
    row2 = "2,63,63,10204,1,24,Other, Even, More, Extra, Fields, Here, Really"
    path = tmp_path / "truly_corrupted.csv"
    path.write_text(header + "\n" + row1 + "\n" + row2 + "\n", encoding="utf-8")

    result = read_csv_defensive(path)
    assert result.dataframe is None
    assert result.repaired is False
    assert "patron de comillas dobladas" in result.error


def test_read_csv_defensive_parseable_but_missing_identification_columns(tmp_path: Path):
    """
    Item 6: un CSV perfectamente parseable (nivel 1) pero sin las columnas
    minimas de identificacion (nivel 2) debe rechazarse con un motivo que
    lo diga explicitamente, no con un numero arbitrario de columnas.
    """
    path = tmp_path / "no_identification.csv"
    path.write_text("COL_A,COL_B,COL_C\n1,2,3\n", encoding="utf-8")

    result = read_csv_defensive(path)
    assert result.dataframe is None
    assert "identificacion" in result.standard_reject_reason


def test_is_parseable_as_csv_distinguishes_collapsed_single_column():
    collapsed = pd.DataFrame({"ID,ID_BATCH,ID_CLIENT": ["1,63,10204"]})
    normal = pd.DataFrame({"ID": [1], "ID_BATCH": [63], "ID_CLIENT": [10204]})
    assert is_parseable_as_csv(collapsed) is False
    assert is_parseable_as_csv(normal) is True


def test_has_identification_columns_requires_id_client_and_id_configuration():
    with_ids = pd.DataFrame({"ID_CLIENT": [1], "ID_CONFIGURATION": [2], "OTHER": [3]})
    without_ids = pd.DataFrame({"ID_CLIENT": [1], "OTHER": [3]})
    assert has_identification_columns(with_ids) is True
    assert has_identification_columns(without_ids) is False


# --------------------------------------------------------------------------
# Item 7: conversion explicita de columnas numericas.
# --------------------------------------------------------------------------

def test_coerce_numeric_columns_converts_text_numbers_and_flags_bad_values_as_nan():
    df = pd.DataFrame({"HISTORY_M1": ["100", "200.5", "abc", None]})
    coerced = coerce_numeric_columns(df, ["HISTORY_M1"])
    assert pd.api.types.is_numeric_dtype(coerced["HISTORY_M1"])
    assert coerced["HISTORY_M1"].tolist()[:2] == [100.0, 200.5]
    assert pd.isna(coerced["HISTORY_M1"].iloc[2])
    assert pd.isna(coerced["HISTORY_M1"].iloc[3])


def test_coerce_numeric_columns_leaves_already_numeric_columns_unchanged():
    df = pd.DataFrame({"HISTORY_M1": [1.0, 2.0]})
    coerced = coerce_numeric_columns(df, ["HISTORY_M1"])
    assert coerced["HISTORY_M1"].tolist() == [1.0, 2.0]


def _write_minimal_valid_csv(path: Path, id_client: int, extra_rows: str = "") -> None:
    path.write_text(
        SIMPLE_HEADER + "\n" + f"1,63,63,{id_client},1,23,LABEL\n" + extra_rows,
        encoding="utf-8",
    )


def test_load_client_sources_detects_filename_id_mismatch(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_minimal_valid_csv(data_dir / "TA_FOV_SCP_ML_99999_Wrong.csv", id_client=10204)

    sources = load_client_sources(data_dir)
    assert len(sources) == 1
    codes = [i.code for i in sources[0].quality.issues]
    assert "FILENAME_ID_MISMATCH" in codes


def test_load_client_sources_detects_multiple_clients_in_one_csv(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_minimal_valid_csv(path, id_client=10204, extra_rows="2,63,63,10467,1,24,LABEL2\n")

    sources = load_client_sources(data_dir)
    assert len(sources) == 1
    source = sources[0]
    codes = [i.code for i in source.quality.issues]
    assert "MULTIPLE_CLIENTS_IN_CSV" in codes
    assert source.is_valid is False


def test_load_client_sources_detects_duplicate_logical_key(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv"
    _write_minimal_valid_csv(path, id_client=10204, extra_rows="2,63,63,10204,1,23,LABEL_DUP\n")

    sources = load_client_sources(data_dir)
    codes = [i.code for i in sources[0].quality.issues]
    assert "DUPLICATE_LOGICAL_KEY" in codes


def test_load_client_sources_detects_duplicate_client_across_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_minimal_valid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    _write_minimal_valid_csv(data_dir / "TA_FOV_SCP_ML_10204_OtherFile.csv", id_client=10204)

    sources = load_client_sources(data_dir)
    assert len(sources) == 2
    for source in sources:
        codes = [i.code for i in source.quality.issues]
        assert "DUPLICATE_CLIENT_ACROSS_FILES" in codes
        assert source.is_valid is False


def test_load_client_sources_isolates_unreadable_csv_from_valid_ones(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_minimal_valid_csv(data_dir / "TA_FOV_SCP_ML_10204_SKLUM.csv", id_client=10204)
    (data_dir / "TA_FOV_SCP_ML_99999_Broken.csv").write_bytes(b"\xff\xfe not a csv")

    sources = load_client_sources(data_dir)
    assert len(sources) == 2
    good = next(s for s in sources if s.id_from_filename == 10204)
    bad = next(s for s in sources if s.id_from_filename == 99999)
    assert good.dataframe is not None
    assert bad.dataframe is None
    assert any(i.severity == Severity.ERROR for i in bad.quality.issues)
