from pathlib import Path

import pandas as pd
import pytest

import src.input_loader as input_loader_module
from src.client_analysis import analyze_client
from src.input_loader import (
    ClientSource,
    coerce_numeric_columns,
    discover_csv_files,
    extract_id_from_label,
    extract_label_from_filename,
    has_identification_columns,
    is_parseable_as_csv,
    load_client_sources,
    load_client_sources_from_csv,
    normalize_folder_name,
    read_csv_defensive,
    unwrap_double_quoted_line,
)
from src.periods import all_required_columns
from src.quality_checks import Severity, StructuralInputError

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


# ==============================================================================
# Fase 2 (EN PARALELO): load_client_sources_from_csv.
#
# El loader legacy (load_client_sources) solo exige all_required_columns()
# (234 columnas). El nuevo loader exige ademas RUN_START_DATE, asi que estos
# tests necesitan un CSV con el contrato COMPLETO (235 columnas), no el
# fixture minimo de 7 columnas (SIMPLE_HEADER) usado arriba: con solo 7
# columnas, load_client_sources_from_csv abortaria siempre en
# MISSING_REQUIRED_COLUMNS antes de llegar a la validacion que cada test
# quiere ejercitar.
# ==============================================================================

FULL_REQUIRED_COLUMNS = [*all_required_columns(), "RUN_START_DATE"]
DEFAULT_TEST_RUN_START_DATE = "2026-01-01"


def _write_structural_csv(path: Path, rows: list[dict]) -> None:
    """
    Escribe un CSV con las 235 columnas exigidas por
    load_client_sources_from_csv. Cada dict de `rows` fija solo las columnas
    relevantes para el test; el resto queda vacio (NaN al leer), lo cual es
    valido porque estos tests solo ejercitan validacion fisica/estructural,
    no metricas analiticas.
    """
    full_rows = [{col: row.get(col, "") for col in FULL_REQUIRED_COLUMNS} for row in rows]
    pd.DataFrame(full_rows, columns=FULL_REQUIRED_COLUMNS).to_csv(path, index=False)


def _structural_row(
    id_configuration, id_client="10204", id_batch="63", id_run_staging="63",
    source_run_id="1", run_start_date=DEFAULT_TEST_RUN_START_DATE,
) -> dict:
    """
    id_configuration es obligatorio y sin default deliberadamente: cada
    fila de un mismo cliente debe recibir un valor distinto para no chocar
    por accidente con DUPLICATE_LOGICAL_KEY en tests que no lo estan
    ejercitando.
    """
    return {
        "ID": str(id_configuration), "ID_CLIENT": id_client, "ID_BATCH": id_batch,
        "ID_RUN_STAGING": id_run_staging, "SOURCE_RUN_ID": source_run_id,
        "ID_CONFIGURATION": str(id_configuration), "RUN_START_DATE": run_start_date,
    }


# ------------------------------------------------------------------
# Camino general
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_single_client_produces_one_partition(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1), _structural_row(2)])

    sources = load_client_sources_from_csv(path)

    assert len(sources) == 1
    assert sources[0].id_client == 10204
    assert sources[0].n_rows == 2


def test_load_client_sources_from_csv_does_not_resolve_display_name(tmp_path: Path):
    """
    Fase 5: el loader es agnostico a catalogo/presentacion (decision cerrada).
    display_name debe quedar sin resolver (valor por defecto ""); la
    resolucion via config/client-catalog.json ocurre despues, en la
    orquestacion de analysis_fov_scp_ml.py, nunca aqui.
    """
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1)])

    sources = load_client_sources_from_csv(path)

    assert sources[0].display_name == ""


def test_load_client_sources_from_csv_multiple_clients_produces_one_partition_per_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)

    assert {s.id_client for s in sources} == {10204, 10467}
    assert len(sources) == 2


def test_load_client_sources_from_csv_reads_file_exactly_once(tmp_path: Path, monkeypatch):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1)])

    calls = []
    original = input_loader_module.read_csv_defensive

    def counting_read(p):
        calls.append(p)
        return original(p)

    monkeypatch.setattr(input_loader_module, "read_csv_defensive", counting_read)
    input_loader_module.load_client_sources_from_csv(path)
    assert len(calls) == 1


def test_load_client_sources_from_csv_partition_contains_only_its_own_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)

    for source in sources:
        assert set(source.dataframe["ID_CLIENT"].unique()) == {source.id_client}


def test_load_client_sources_from_csv_partitions_are_independent_copies(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)
    by_client = {s.id_client: s for s in sources}
    by_client[10204].dataframe.loc[by_client[10204].dataframe.index[0], "ID_BATCH"] = 999999

    assert (by_client[10467].dataframe["ID_BATCH"] == 999999).sum() == 0


def test_load_client_sources_from_csv_n_rows_matches_partition_size(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204"), _structural_row(2, id_client="10204"),
        _structural_row(3, id_client="10204"),
        _structural_row(4, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)
    by_client = {s.id_client: s for s in sources}

    assert by_client[10204].n_rows == 3
    assert by_client[10467].n_rows == 1


def test_load_client_sources_from_csv_unreadable_file_raises_csv_not_readable(tmp_path: Path):
    path = tmp_path / "garbage.csv"
    path.write_bytes(b"\xff\xfe not a csv")

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "CSV_NOT_READABLE"


def test_load_client_sources_from_csv_missing_required_columns_raises(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_incomplete.csv"
    path.write_text(SIMPLE_HEADER + "\n1,63,63,10204,1,23,DECORACION\n", encoding="utf-8")

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "MISSING_REQUIRED_COLUMNS"


def test_load_client_sources_from_csv_does_not_validate_filename_against_id_client(tmp_path: Path):
    """
    El full export es un unico fichero fisico cuyo nombre NO representa la
    identidad de cada cliente: check_filename_matches_id no debe invocarse.
    """
    path = tmp_path / "TA_FOV_SCP_ML_99999_DoesNotMatch.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="10204")])

    sources = load_client_sources_from_csv(path)

    codes = [i.code for i in sources[0].quality.issues]
    assert "FILENAME_ID_MISMATCH" not in codes


# ------------------------------------------------------------------
# ID_CLIENT
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_partial_null_id_client_raises_invalid_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="10204"), _structural_row(2, id_client="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CLIENT"


def test_load_client_sources_from_csv_all_null_id_client_raises_invalid_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CLIENT"


def test_load_client_sources_from_csv_non_numeric_id_client_raises_invalid_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="ABC")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CLIENT"


def test_load_client_sources_from_csv_non_integral_id_client_raises_invalid_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="10204.5")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CLIENT"


def test_load_client_sources_from_csv_infinite_id_client_raises_invalid_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="inf")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CLIENT"


def test_load_client_sources_from_csv_accepts_plain_integer_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="10204")])

    sources = load_client_sources_from_csv(path)
    assert sources[0].id_client == 10204


def test_load_client_sources_from_csv_accepts_integral_float_id_client(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_client="10204.0")])

    sources = load_client_sources_from_csv(path)
    assert sources[0].id_client == 10204


# ------------------------------------------------------------------
# Scope
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_complete_scope_is_valid(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1)])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1


def test_load_client_sources_from_csv_null_id_batch_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_batch="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_null_id_run_staging_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_run_staging="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_null_source_run_id_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, source_run_id="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_non_integral_id_batch_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_batch="63.5")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_infinite_id_run_staging_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_run_staging="inf")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_non_numeric_source_run_id_raises_invalid_execution_scope(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, source_run_id="abc")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_EXECUTION_SCOPE"


def test_load_client_sources_from_csv_accepts_integral_float_scope_fields(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, id_batch="63.0", id_run_staging="63.0", source_run_id="1.0")])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1


def test_load_client_sources_from_csv_two_scopes_same_client_raises_ambiguous_client_execution(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_batch="63", id_run_staging="63", source_run_id="1"),
        _structural_row(2, id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "AMBIGUOUS_CLIENT_EXECUTION"


def test_load_client_sources_from_csv_different_scopes_across_clients_is_valid(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204", id_batch="63", id_run_staging="63", source_run_id="1"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)
    assert {s.id_client for s in sources} == {10204, 10467}


def test_load_client_sources_from_csv_ambiguous_scope_with_disjoint_configurations_still_raises(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_batch="63", id_run_staging="63", source_run_id="1"),
        _structural_row(2, id_batch="64", id_run_staging="64", source_run_id="2"),
    ])  # ID_CONFIGURATION 1 y 2: disjuntas entre los dos scopes, sigue siendo error

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "AMBIGUOUS_CLIENT_EXECUTION"


def test_load_client_sources_from_csv_ambiguous_scope_with_overlapping_configurations_still_raises(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_batch="63", id_run_staging="63", source_run_id="1"),
        _structural_row(1, id_batch="64", id_run_staging="64", source_run_id="2"),
    ])  # misma ID_CONFIGURATION=1 en ambos scopes: solapada, sigue siendo error

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "AMBIGUOUS_CLIENT_EXECUTION"


# ------------------------------------------------------------------
# Duplicados
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_duplicate_logical_key_raises(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1), _structural_row(1)])  # misma clave logica completa

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "DUPLICATE_LOGICAL_KEY"


# ------------------------------------------------------------------
# ID_CONFIGURATION
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_null_id_configuration_raises_invalid_id_configuration(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row("")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CONFIGURATION"


def test_load_client_sources_from_csv_non_numeric_id_configuration_raises_invalid_id_configuration(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row("abc")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CONFIGURATION"


def test_load_client_sources_from_csv_non_integral_id_configuration_raises_invalid_id_configuration(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row("1.5")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CONFIGURATION"


def test_load_client_sources_from_csv_infinite_id_configuration_raises_invalid_id_configuration(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row("inf")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_ID_CONFIGURATION"


def test_load_client_sources_from_csv_accepts_integral_float_id_configuration(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row("1.0")])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1


# ------------------------------------------------------------------
# RUN_START_DATE
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_valid_run_start_date_is_ok(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, run_start_date="2026-01-01")])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1


def test_load_client_sources_from_csv_null_run_start_date_raises_invalid(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, run_start_date="")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_RUN_START_DATE"


def test_load_client_sources_from_csv_unparseable_run_start_date_raises_invalid(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, run_start_date="no-es-una-fecha")])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INVALID_RUN_START_DATE"


def test_load_client_sources_from_csv_same_client_same_date_different_hours_is_ok(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, run_start_date="2026-01-01 00:00:00"),
        _structural_row(2, run_start_date="2026-01-01 08:30:00"),
    ])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1


def test_load_client_sources_from_csv_mixed_seconds_and_milliseconds_precision_is_ok(tmp_path: Path):
    """
    pandas 2.3.3 infiere el formato desde la primera fila si no se pasa
    format="mixed": una Serie con "...00:00:00" seguido de
    "...00:00:00.001" produciria NaT en la segunda fila sin ese parametro
    (comprobado explicitamente antes de aplicar el fix). Mismo cliente,
    mismo dia logico, precision textual mixta -> debe seguir siendo valido.
    """
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, run_start_date="2026-01-01 00:00:00"),
        _structural_row(2, run_start_date="2026-01-01 00:00:00.001"),
    ])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1
    assert sources[0].dataframe["RUN_START_DATE"].notna().all()


def test_load_client_sources_from_csv_date_only_mixed_with_millisecond_timestamp_is_ok(tmp_path: Path):
    """Fecha sin componente de hora mezclada con timestamp con milisegundos, mismo cliente."""
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, run_start_date="2026-01-01"),
        _structural_row(2, run_start_date="2026-01-01 00:00:00.001"),
    ])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 1
    assert sources[0].dataframe["RUN_START_DATE"].notna().all()


def test_load_client_sources_from_csv_preserves_full_timestamp_not_normalized(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [_structural_row(1, run_start_date="2026-01-01 13:45:30")])

    sources = load_client_sources_from_csv(path)
    stored = sources[0].dataframe["RUN_START_DATE"].iloc[0]

    assert stored == pd.Timestamp("2026-01-01 13:45:30")
    assert (stored.hour, stored.minute, stored.second) == (13, 45, 30)


def test_load_client_sources_from_csv_client_with_two_dates_raises_inconsistent(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, run_start_date="2026-01-01"),
        _structural_row(2, run_start_date="2026-02-01"),
    ])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INCONSISTENT_CLIENT_RUN_START_DATE"


def test_load_client_sources_from_csv_multiple_clients_same_date_is_ok(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204", run_start_date="2026-01-01"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2",
                         run_start_date="2026-01-01"),
    ])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 2


def test_load_client_sources_from_csv_multiple_clients_different_dates_raises_incompatible(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204", run_start_date="2026-01-01"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2",
                         run_start_date="2026-02-01"),
    ])

    with pytest.raises(StructuralInputError) as exc_info:
        load_client_sources_from_csv(path)
    assert exc_info.value.code == "INCOMPATIBLE_RUN_START_DATE"


def test_load_client_sources_from_csv_clients_in_different_batches_same_date_is_ok(tmp_path: Path):
    """No debe validarse unicamente por ID_BATCH: batches muy distintos, misma fecha logica -> valido."""
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204", id_batch="63", id_run_staging="63", source_run_id="1",
                         run_start_date="2026-01-01"),
        _structural_row(2, id_client="10467", id_batch="999", id_run_staging="999", source_run_id="9",
                         run_start_date="2026-01-01"),
    ])

    sources = load_client_sources_from_csv(path)
    assert len(sources) == 2


# ------------------------------------------------------------------
# Warnings fisicos y batch heterogeneity
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_replicates_non_numeric_warning_to_every_partition(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])
    df = pd.read_csv(path)
    df["HISTORY_M1"] = df["HISTORY_M1"].astype(object)
    df.loc[0, "HISTORY_M1"] = "no-es-numero"
    df.to_csv(path, index=False)

    sources = load_client_sources_from_csv(path)

    for source in sources:
        codes = [i.code for i in source.quality.issues]
        assert "NON_NUMERIC_VALUES" in codes


def test_load_client_sources_from_csv_batch_heterogeneity_warning_added_to_all_sources(tmp_path: Path):
    path = tmp_path / "TA_FOV_SCP_ML_full_export.csv"
    _write_structural_csv(path, [
        _structural_row(1, id_client="10204", id_batch="63", id_run_staging="63", source_run_id="1"),
        _structural_row(2, id_client="10467", id_batch="64", id_run_staging="64", source_run_id="2"),
    ])

    sources = load_client_sources_from_csv(path)

    for source in sources:
        codes = [i.code for i in source.quality.issues]
        assert "BATCH_HETEROGENEITY_ACROSS_CLIENTS" in codes


# ------------------------------------------------------------------
# Caracterizacion: N=1 debe ser equivalente al loader legacy
# ------------------------------------------------------------------

def test_load_client_sources_from_csv_single_client_matches_legacy_load_client_sources(tmp_path: Path):
    from tests.factories import DEFAULT_RUN_START_DATE, build_synthetic_client_dataframe

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "TA_FOV_SCP_ML_99999_Synthetic.csv"

    df = build_synthetic_client_dataframe()
    df["ID"] = range(1, len(df) + 1)
    df["ID_BATCH"] = 63
    df["ID_RUN_STAGING"] = 63
    df["SOURCE_RUN_ID"] = 1
    # Columna extra respecto al contrato legacy: el loader legacy debe
    # ignorarla, ya que solo es obligatoria para load_client_sources_from_csv
    # en esta fase (no forma parte todavia de periods.STATIC_REQUIRED_COLUMNS).
    df["RUN_START_DATE"] = DEFAULT_RUN_START_DATE
    missing_cols = [col for col in all_required_columns() if col not in df.columns]
    df = pd.concat([df, pd.DataFrame(None, index=df.index, columns=missing_cols)], axis=1)
    df.to_csv(path, index=False)

    legacy_sources = load_client_sources(data_dir)
    assert len(legacy_sources) == 1
    legacy_result = analyze_client(legacy_sources[0])

    new_sources = load_client_sources_from_csv(path)
    assert len(new_sources) == 1
    new_result = analyze_client(new_sources[0])

    assert legacy_result.file_valid == new_result.file_valid is True
    assert legacy_result.n_candidates == new_result.n_candidates
    for period in ("6M", "M1"):
        legacy_pr = legacy_result.periods[period]
        new_pr = new_result.periods[period]
        assert legacy_pr.n_comparable == new_pr.n_comparable
        assert legacy_pr.wape["scp_wape_global"] == new_pr.wape["scp_wape_global"]
        assert legacy_pr.wape["ml_wape_global"] == new_pr.wape["ml_wape_global"]
        assert legacy_pr.winner_counts == new_pr.winner_counts
