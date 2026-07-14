from src.logging_utils import build_processing_log
from tests.factories import build_synthetic_client_result


def test_build_processing_log_contains_key_fields():
    result = build_synthetic_client_result(with_data=True)
    log = build_processing_log(result, ["outputs/99999_Synthetic/fov_scp_ml_summary_99999_Synthetic.xlsx"], 1.23)

    assert "archivo=" in log
    assert "id_client=99999" in log
    assert "duracion_segundos=1.230" in log
    assert "periodo=6M" in log
    assert "Chequeos de calidad" in log
    assert "outputs/99999_Synthetic/fov_scp_ml_summary_99999_Synthetic.xlsx" in log


def test_build_processing_log_no_comparable_series_still_valid():
    result = build_synthetic_client_result(with_data=False)
    log = build_processing_log(result, [], 0.1)
    assert "id_client=88888" in log
    assert "series_candidatas=1" in log
