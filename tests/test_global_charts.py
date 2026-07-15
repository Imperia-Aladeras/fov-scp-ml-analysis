from pathlib import Path

import pandas as pd

from src.charts import COLOR_ML, COLOR_SCP
from src.global_analysis import build_global_period_result
from src.global_charts import CHART_SUBFOLDERS, contribution_colors, generate_global_charts
from tests.factories import build_global_analysis_result, build_multi_client_results


def test_generate_global_charts_creates_files_on_disk(tmp_path: Path):
    result = build_global_analysis_result()
    charts_dir = tmp_path / "charts"
    generated = generate_global_charts(result, charts_dir)

    assert len(generated) > 0
    for path_str in generated:
        assert Path(path_str).exists()
        assert Path(path_str).stat().st_size > 0


def test_chart_subfolders_constant_matches_spec():
    assert CHART_SUBFOLDERS == (
        "coverage", "semester", "quarters", "monthly", "clients", "models", "classifications", "impact_and_risk",
    )


def test_contribution_colors_uses_absolute_value_sign():
    """
    Regresion: colorear por PCT_OF_TOTAL_REDUCTION en vez de por
    ABS_ERROR_REDUCTION invertia los colores cuando la reduccion neta total
    era negativa (un cliente que empeora mucho pesaba tanto que su % de un
    total negativo salia positivo, y viceversa para los que mejoran).
    """
    # Caso real reproducido: total negativo, un cliente domina en negativo,
    # otros aportan positivo pero su % sobre el total sale con signo invertido.
    values = pd.Series([4_000_000.0, 3_000_000.0, -27_000_000.0])
    colors = contribution_colors(values)
    assert colors == [COLOR_ML, COLOR_ML, COLOR_SCP]


def test_client_contribution_chart_colors_by_absolute_value_not_percentage():
    results = build_multi_client_results()
    gp = build_global_period_result(results, "6M")
    combined = pd.concat([gp.client_reduction_table, gp.client_deterioration_table], ignore_index=True)
    if not combined.empty and (combined["ABS_ERROR_REDUCTION"] < 0).any():
        negative_row = combined[combined["ABS_ERROR_REDUCTION"] < 0].iloc[0]
        assert negative_row["ABS_ERROR_REDUCTION"] < 0
        colors = contribution_colors(combined["ABS_ERROR_REDUCTION"])
        assert colors[combined.index.get_loc(negative_row.name)] == COLOR_SCP
