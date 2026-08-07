import json
from pathlib import Path

from src.client_catalog import load_client_catalog, resolve_client_name


def _write_catalog(tmp_path: Path, text: str, name: str = "client-catalog.json") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_client_catalog_reads_valid_file(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10338": "Grefusa", "202": "Suavinex"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {10338: "Grefusa", 202: "Suavinex"}
    assert warning is None


def test_load_client_catalog_empty_object_is_valid(tmp_path: Path):
    path = _write_catalog(tmp_path, "{}")

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is None


def test_load_client_catalog_missing_file_returns_empty_without_warning(tmp_path: Path):
    path = tmp_path / "does-not-exist.json"

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is None


def test_load_client_catalog_empty_file_returns_warning(tmp_path: Path):
    path = _write_catalog(tmp_path, "")

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is not None


def test_load_client_catalog_invalid_json_returns_warning(tmp_path: Path):
    path = _write_catalog(tmp_path, "{not valid json")

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is not None


def test_load_client_catalog_non_object_root_returns_warning(tmp_path: Path):
    path = _write_catalog(tmp_path, '["10338", "Grefusa"]')

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is not None


def test_load_client_catalog_skips_non_numeric_key(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"abc": "Invalido", "10338": "Grefusa"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {10338: "Grefusa"}
    assert warning is not None
    assert "1" in warning  # una entrada ignorada


def test_load_client_catalog_skips_non_string_value(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10338": 42, "202": "Suavinex"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {202: "Suavinex"}
    assert warning is not None


def test_load_client_catalog_skips_empty_name(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10338": "", "202": "Suavinex"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {202: "Suavinex"}
    assert warning is not None


def test_load_client_catalog_skips_whitespace_only_name(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10338": "   ", "202": "Suavinex"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {202: "Suavinex"}
    assert warning is not None


def test_resolve_client_name_returns_known_name():
    assert resolve_client_name(10338, {10338: "Grefusa"}) == "Grefusa"


def test_resolve_client_name_returns_fallback_for_unknown_id():
    assert resolve_client_name(99999, {}) == "Cliente 99999"
    assert resolve_client_name(99999, {10338: "Grefusa"}) == "Cliente 99999"


def test_load_client_catalog_preserves_unicode_and_accents(tmp_path: Path):
    data = {
        "10684": "Aldelís",
        "10552": "Compañía Alfaro",
        "10608": "Azul Difusión Gastronómica",
    }
    path = _write_catalog(tmp_path, json.dumps(data, ensure_ascii=False))

    catalog, warning = load_client_catalog(path)

    assert catalog == {10684: "Aldelís", 10552: "Compañía Alfaro", 10608: "Azul Difusión Gastronómica"}
    assert warning is None


def test_load_client_catalog_does_not_strip_or_normalize_values(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10338": " Grefusa "}')

    catalog, warning = load_client_catalog(path)

    assert catalog[10338] == " Grefusa "
    assert warning is None


def test_load_client_catalog_allows_duplicate_names_across_different_ids(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"10503": "Fiorucci", "10537": "Fiorucci"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {10503: "Fiorucci", 10537: "Fiorucci"}
    assert warning is None


def test_load_client_catalog_size_is_not_hardcoded(tmp_path: Path):
    small = {str(i): f"Cliente sintetico {i}" for i in range(3)}
    large = {str(i): f"Cliente sintetico {i}" for i in range(50)}

    small_path = _write_catalog(tmp_path, json.dumps(small), name="small.json")
    large_path = _write_catalog(tmp_path, json.dumps(large), name="large.json")

    small_catalog, small_warning = load_client_catalog(small_path)
    large_catalog, large_warning = load_client_catalog(large_path)

    assert len(small_catalog) == len(small)
    assert len(large_catalog) == len(large)
    assert small_warning is None
    assert large_warning is None


def test_load_client_catalog_detects_duplicate_textual_key(tmp_path: Path):
    # json duplicado a nivel textual: no se puede construir con json.dumps
    # (un dict de Python no puede tener dos claves iguales), asi que se
    # escribe el texto JSON directamente para reproducir el caso real.
    path = _write_catalog(tmp_path, '{"10338": "Grefusa", "10338": "Otro Nombre"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is not None
    assert "10338" in warning


def test_load_client_catalog_detects_keys_colliding_after_int_normalization(tmp_path: Path):
    path = _write_catalog(tmp_path, '{"010338": "Grefusa", "10338": "Otro Nombre"}')

    catalog, warning = load_client_catalog(path)

    assert catalog == {}
    assert warning is not None
    assert "10338" in warning
