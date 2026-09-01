from pathlib import Path

import pandas as pd

from src.charts import COLOR_ML, COLOR_SCP
from src.client_analysis import analyze_client
from src.global_analysis import GlobalAnalysisResult, build_global_period_result, global_pareto_clients, global_pareto_series
from src.global_analysis import analyze_global
from src.global_charts import (
    CHART_SUBFOLDERS,
    _chart_global_bias_by_volume_bucket,
    contribution_colors,
    generate_classifications_charts,
    generate_global_charts,
    generate_impact_and_risk_charts,
    generate_models_charts,
    pareto_client_chart_label,
    pareto_series_chart_label,
)
from tests.factories import (
    build_global_analysis_result,
    build_multi_client_results,
    build_phase8_global_missing_client_results,
    build_phase8_global_multi_client_analysis_result,
    build_synthetic_client_dataframe,
    make_client_source,
)


def test_generate_global_charts_creates_files_on_disk(tmp_path: Path):
    result = build_global_analysis_result()
    charts_dir = tmp_path / "charts"
    generated = generate_global_charts(result, charts_dir)

    assert len(generated) > 0
    for path_str in generated:
        assert Path(path_str).exists()
        assert Path(path_str).stat().st_size > 0
    assert not any("models" in Path(path).parts or "classifications" in Path(path).parts for path in generated)


def test_global_legacy_model_and_classification_chart_families_generate_nothing(tmp_path: Path):
    result = build_global_analysis_result()
    assert generate_models_charts(result, tmp_path / "models") == []
    assert generate_classifications_charts(result, tmp_path / "classifications") == []
    assert not (tmp_path / "models").exists()
    assert not (tmp_path / "classifications").exists()


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


# --------------------------------------------------------------------------
# Pareto global (03-06 en impact_and_risk/)
# --------------------------------------------------------------------------

def test_pareto_charts_generated_for_both_groups_at_series_and_client_level(tmp_path: Path):
    """mixed (99999) aporta mejora y deterioro tanto en series como a nivel cliente frente a all_ml (77777)."""
    result = build_global_analysis_result()
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(result, out_dir)

    for fname in (
        "03_pareto_clients_reduction.png", "04_pareto_clients_increase.png",
        "05_pareto_series_reduction.png", "06_pareto_series_increase.png",
    ):
        assert any(p.endswith(fname) for p in generated), f"falta {fname}"
        assert (out_dir / fname).exists()
        assert (out_dir / fname).stat().st_size > 0


def test_pareto_client_increase_chart_omitted_when_all_clients_improve(tmp_path: Path):
    """Un unico cliente (all_ml, 77777) que solo mejora: el grupo de deterioro de clientes y de series queda vacio."""
    all_ml_result = build_multi_client_results()[2]
    single_client_result = GlobalAnalysisResult(
        client_results=[all_ml_result], invalid_results=[],
        periods={"6M": build_global_period_result([all_ml_result], "6M")}, client_period_tables={},
    )
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(single_client_result, out_dir)

    assert any(p.endswith("03_pareto_clients_reduction.png") for p in generated)
    assert not any(p.endswith("04_pareto_clients_increase.png") for p in generated)
    assert not (out_dir / "04_pareto_clients_increase.png").exists()
    assert any(p.endswith("05_pareto_series_reduction.png") for p in generated)
    assert not any(p.endswith("06_pareto_series_increase.png") for p in generated)
    assert not (out_dir / "06_pareto_series_increase.png").exists()


def test_pareto_client_chart_label_disambiguates_clients_sharing_file_label():
    """
    Regresion de la auditoria real: dos clientes procedentes del mismo CSV
    fisico multi-cliente comparten ETIQUETA (y, en este fixture, tambien
    DISPLAY_NAME): con el comportamiento anterior (label_col="ETIQUETA") las
    dos barras del chart de clientes global mostraban el mismo texto. La
    nueva etiqueta compuesta DISPLAY_NAME (ID_CLIENT) debe seguir siendo
    unica porque ID_CLIENT si es unico por construccion.
    """
    df_a = build_synthetic_client_dataframe()
    source_a = make_client_source(df_a, 10001, "SharedLabel")
    result_a = analyze_client(source_a)

    df_b = build_synthetic_client_dataframe()
    df_b["ID_CLIENT"] = 10002
    source_b = make_client_source(df_b, 10002, "SharedLabel")
    # mismo CSV fisico: mismo file_label/display_name que source_a, ID_CLIENT distinto
    # (make_client_source deriva file_label como "{id_client}_{label}", asi que un
    # mismo `label` no basta por si solo para reproducir la colision real).
    source_b.file_label = source_a.file_label
    source_b.display_name = source_a.display_name
    result_b = analyze_client(source_b)

    assert source_a.file_label == source_b.file_label
    assert source_a.display_name == source_b.display_name  # peor caso: tambien colisiona

    pareto = global_pareto_clients([result_a, result_b], "6M")
    group = pareto.deterioration if not pareto.deterioration.table.empty else pareto.improvement
    assert len(group.table) == 2  # ambos clientes sinteticos caen en el mismo grupo

    old_style_labels = group.table["ETIQUETA"].astype(str).tolist()
    assert len(set(old_style_labels)) == 1  # reproduce la ambiguedad detectada en la auditoria real

    new_labels = [pareto_client_chart_label(row) for _, row in group.table.iterrows()]
    assert len(new_labels) == len(set(new_labels)), f"etiquetas duplicadas: {new_labels}"
    assert set(new_labels) == {"SharedLabel (10001)", "SharedLabel (10002)"}


def test_pareto_series_chart_label_disambiguates_shared_id_configuration_across_clients():
    """
    Regresion de la auditoria real: dos clientes distintos pueden compartir
    el mismo ID_CONFIGURATION (identidad real = ID_CLIENT + ID_CONFIGURATION,
    ver global_pareto_series). La etiqueta compuesta "<ID_CLIENT>-<ID_CONFIGURATION>"
    debe distinguir ambas series.
    """
    df_a = build_synthetic_client_dataframe()
    df_a["ID_CLIENT"] = 70001  # global_pareto_series lee ID_CLIENT de la columna del df, no de source.id_client
    source_a = make_client_source(df_a, 70001, "ClientA")
    result_a = analyze_client(source_a)

    df_b = build_synthetic_client_dataframe()
    df_b["ID_CLIENT"] = 70002
    source_b = make_client_source(df_b, 70002, "ClientB")
    result_b = analyze_client(source_b)

    pareto = global_pareto_series([result_a, result_b], "6M")
    group = pareto.improvement
    assert len(group.table) == 2
    assert group.table["ID_CONFIGURATION"].nunique() == 1  # colision real de ID_CONFIGURATION

    old_style_labels = group.table["ID_CONFIGURATION"].astype(str).tolist()
    assert len(set(old_style_labels)) == 1  # con el comportamiento anterior, ambiguo

    new_labels = [pareto_series_chart_label(row) for _, row in group.table.iterrows()]
    assert len(new_labels) == len(set(new_labels)), f"etiquetas duplicadas: {new_labels}"
    assert set(new_labels) == {"70001-1001", "70002-1001"}


def test_pareto_client_charts_render_without_error_when_clients_share_file_label(tmp_path: Path):
    """Smoke test end-to-end: la colision de ETIQUETA no rompe la generacion de 03/04."""
    df_a = build_synthetic_client_dataframe()
    source_a = make_client_source(df_a, 10001, "SharedLabel")
    result_a = analyze_client(source_a)

    df_b = build_synthetic_client_dataframe()
    df_b["ID_CLIENT"] = 10002
    source_b = make_client_source(df_b, 10002, "SharedLabel")
    source_b.file_label = source_a.file_label
    source_b.display_name = source_a.display_name
    result_b = analyze_client(source_b)

    colliding_result = GlobalAnalysisResult(
        client_results=[result_a, result_b], invalid_results=[],
        periods={"6M": build_global_period_result([result_a, result_b], "6M")}, client_period_tables={},
    )
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(colliding_result, out_dir)

    assert any(p.endswith("03_pareto_clients_reduction.png") or p.endswith("04_pareto_clients_increase.png") for p in generated)
    for p in generated:
        assert Path(p).exists()
        assert Path(p).stat().st_size > 0


def test_global_charts_never_recompute_pareto(monkeypatch, tmp_path: Path):
    result = build_global_analysis_result()  # Pareto ya calculado dentro de analyze_global

    def _boom(*args, **kwargs):
        raise AssertionError("global_charts.py no debe recalcular el Pareto")

    monkeypatch.setattr("src.global_analysis.global_pareto_series", _boom)
    monkeypatch.setattr("src.global_analysis.global_pareto_clients", _boom)
    monkeypatch.setattr("src.pareto.build_pareto_analysis", _boom)

    generated = generate_global_charts(result, tmp_path / "charts")
    assert any("03_pareto_clients_reduction.png" in p for p in generated)
    assert any("05_pareto_series_reduction.png" in p for p in generated)


# --------------------------------------------------------------------------
# 07_global_bias_by_volume_bucket (Fase 8D)
# --------------------------------------------------------------------------

def test_chart_07_generated_when_phase8_available(tmp_path: Path):
    result = build_phase8_global_multi_client_analysis_result()
    out_dir = tmp_path / "impact_and_risk"
    generated = generate_impact_and_risk_charts(result, out_dir)

    assert any(p.endswith("07_global_bias_by_volume_bucket.png") for p in generated)
    path = out_dir / "07_global_bias_by_volume_bucket.png"
    assert path.exists()
    assert path.stat().st_size > 0


def test_chart_07_omitted_when_phase8_none(tmp_path: Path):
    result = analyze_global(build_phase8_global_missing_client_results())
    assert result.periods["6M"].phase8 is None
    out_dir = tmp_path / "impact_and_risk"
    path = _chart_global_bias_by_volume_bucket(result, out_dir, "07_global_bias_by_volume_bucket.png")
    assert path is None
    assert not (out_dir / "07_global_bias_by_volume_bucket.png").exists()


def test_chart_07_excludes_non_finite_bucket_without_zeroing_or_dropping_the_chart(tmp_path: Path):
    """
    Ningun Bias no finito debe llegar a matplotlib: un bucket con NaN/inf en
    scp_bias_agg o ml_bias_agg se excluye SOLO del grafico (nunca se
    sustituye por 0), y el resto de buckets finitos se siguen dibujando.
    """
    import numpy as np

    result = build_phase8_global_multi_client_analysis_result()
    phase8 = result.periods["6M"].phase8
    volume_table = phase8.volume_table.copy()
    volume_table.loc[volume_table.index[0], "scp_bias_agg"] = np.nan
    phase8.volume_table = volume_table

    out_dir = tmp_path / "impact_and_risk"
    path = _chart_global_bias_by_volume_bucket(result, out_dir, "07_global_bias_by_volume_bucket.png")
    # Con >=1 bucket finito restante, el chart debe seguir generandose.
    assert path is not None
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0
    # La tabla fuente (fuera del chart) conserva el NaN tal cual, nunca sustituido por 0.
    assert np.isnan(phase8.volume_table.loc[phase8.volume_table.index[0], "scp_bias_agg"])


def test_chart_07_not_generated_when_no_bucket_is_finite(tmp_path: Path):
    import numpy as np

    result = build_phase8_global_multi_client_analysis_result()
    phase8 = result.periods["6M"].phase8
    volume_table = phase8.volume_table.copy()
    volume_table["scp_bias_agg"] = np.nan
    volume_table["ml_bias_agg"] = np.nan
    phase8.volume_table = volume_table

    out_dir = tmp_path / "impact_and_risk"
    path = _chart_global_bias_by_volume_bucket(result, out_dir, "07_global_bias_by_volume_bucket.png")
    assert path is None
    assert not (out_dir / "07_global_bias_by_volume_bucket.png").exists()
