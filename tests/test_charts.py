from pathlib import Path

from src.charts import CHART_SUBFOLDERS, generate_client_charts
from tests.factories import build_synthetic_client_result


def test_generate_client_charts_creates_files_on_disk(tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)
    charts_dir = tmp_path / "charts"
    generated = generate_client_charts(result, charts_dir)

    assert len(generated) > 0
    for path_str in generated:
        assert Path(path_str).exists()
        assert Path(path_str).stat().st_size > 0


def test_generate_client_charts_covers_coverage_folder_even_without_comparable_series(tmp_path: Path):
    """
    Item explicito de la Fase 3: un cliente sin series comparables sigue
    siendo un caso valido de cobertura. Los graficos de cobertura deben
    generarse; los de performance no (no se inventan datos).
    """
    result = build_synthetic_client_result(with_data=False)
    charts_dir = tmp_path / "charts"
    generated = generate_client_charts(result, charts_dir)

    assert any("coverage" in p for p in generated)
    assert not any("semester" in p for p in generated)
    assert not any("impact_and_risk" in p for p in generated)


def test_chart_subfolders_constant_matches_spec():
    assert CHART_SUBFOLDERS == (
        "coverage", "semester", "quarters", "monthly", "models", "classifications", "impact_and_risk",
    )
