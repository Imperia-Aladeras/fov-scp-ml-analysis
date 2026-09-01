from pathlib import Path

from src.charts import (
    CHART_SUBFOLDERS,
    generate_classifications_charts,
    generate_client_charts,
    generate_impact_and_risk_charts,
    generate_models_charts,
)
from tests.factories import build_multi_client_results, build_synthetic_client_result, build_volume_bucket_client_result


def test_generate_client_charts_creates_files_on_disk(tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)
    charts_dir = tmp_path / "charts"
    generated = generate_client_charts(result, charts_dir)

    assert len(generated) > 0
    for path_str in generated:
        assert Path(path_str).exists()
        assert Path(path_str).stat().st_size > 0
    assert not any("models" in Path(path).parts or "classifications" in Path(path).parts for path in generated)


def test_legacy_model_and_classification_chart_families_generate_nothing(tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)
    assert generate_models_charts(result, tmp_path / "models") == []
    assert generate_classifications_charts(result, tmp_path / "classifications") == []
    assert not (tmp_path / "models").exists()
    assert not (tmp_path / "classifications").exists()


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


def test_pareto_charts_generated_for_both_groups_when_mixed(tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)  # 1 fila mejora, 1 fila deterioro en 6M
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(result, out_dir)

    assert any(p.endswith("05_pareto_series_reduction.png") for p in generated)
    assert any(p.endswith("06_pareto_series_increase.png") for p in generated)
    for p in generated:
        assert Path(p).exists()
        assert Path(p).stat().st_size > 0


def test_pareto_increase_chart_omitted_when_deterioration_group_empty(tmp_path: Path):
    all_ml_result = build_multi_client_results()[2]  # 77777_AllMlWins: ambas filas ganan ML en 6M
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(all_ml_result, out_dir)

    assert any(p.endswith("05_pareto_series_reduction.png") for p in generated)
    assert not any(p.endswith("06_pareto_series_increase.png") for p in generated)
    assert not (out_dir / "06_pareto_series_increase.png").exists()


def test_charts_never_recompute_pareto(monkeypatch, tmp_path: Path):
    result = build_synthetic_client_result(with_data=True)  # Pareto ya calculado dentro de analyze_client

    def _boom(*args, **kwargs):
        raise AssertionError("charts.py no debe recalcular el Pareto")

    monkeypatch.setattr("src.models.pareto_absolute_impact", _boom)
    monkeypatch.setattr("src.pareto.build_pareto_analysis", _boom)

    generated = generate_client_charts(result, tmp_path / "charts")
    assert any("05_pareto_series_reduction.png" in p for p in generated)


# --------------------------------------------------------------------------
# Fase 8C: chart de Bias por bucket de volumen relativo (6M).
# --------------------------------------------------------------------------

def test_bias_by_volume_bucket_chart_generated_when_volume_ok(tmp_path: Path):
    result = build_volume_bucket_client_result()  # 9 filas -> 3 buckets OK
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(result, out_dir)

    matches = [p for p in generated if p.endswith("07_bias_by_volume_bucket.png")]
    assert len(matches) == 1
    assert Path(matches[0]).exists()
    assert Path(matches[0]).stat().st_size > 0


def test_bias_by_volume_bucket_chart_omitted_when_not_assignable(tmp_path: Path):
    """El fixture sintetico estandar solo tiene 2 filas comparables en 6M -> NOT_ASSIGNABLE: no se fabrica un chart de 1 barra."""
    result = build_synthetic_client_result(with_data=True)
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(result, out_dir)

    assert not any(p.endswith("07_bias_by_volume_bucket.png") for p in generated)
    assert not (out_dir / "07_bias_by_volume_bucket.png").exists()


def test_bias_by_volume_bucket_chart_never_recomputes(monkeypatch, tmp_path: Path):
    result = build_volume_bucket_client_result()  # Fase 8 ya calculada dentro de analyze_client

    def _boom(*args, **kwargs):
        raise AssertionError("charts.py no debe recalcular Fase 8")

    monkeypatch.setattr("src.phase8.build_phase8_client_diagnostics", _boom)
    monkeypatch.setattr("src.phase8.bias_aggregate", _boom)
    monkeypatch.setattr("src.phase8.compute_volume_buckets", _boom)

    generated = generate_impact_and_risk_charts(result, tmp_path / "impact_and_risk")
    assert any(p.endswith("07_bias_by_volume_bucket.png") for p in generated)
