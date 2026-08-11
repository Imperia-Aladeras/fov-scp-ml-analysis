"""
Graficos globales (comparativa entre clientes), 8 subcarpetas: coverage,
semester, quarters, monthly, clients, models, classifications, impact_and_risk.

Mismas reglas de visualizacion que los graficos individuales (src/charts.py):
ML=azul, SCP=rojo, Empate=gris, sin cortar titulos, cerrar todas las figuras,
no recortar valores extremos silenciosamente.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.charts import (
    COLOR_ML,
    COLOR_SCP,
    COLOR_TIE,
    _apply_title,
    _new_fig,
    _save_close,
)
from src.global_analysis import GlobalAnalysisResult, global_category_performance_table, _global_series_improvement_values
from src.periods import MONTHLY_PERIODS, visible_label

MODEL_CLASSIFICATION_PERIOD = "6M"
IMPROVEMENT_CLIP_BOUND = 100.0

CHART_SUBFOLDERS = ("coverage", "semester", "quarters", "monthly", "clients", "models", "classifications", "impact_and_risk")


def _client_labels_and_values(result: GlobalAnalysisResult, period: str, getter) -> tuple[list[str], list[float]]:
    labels, values = [], []
    for r in result.client_results:
        pr = r.periods.get(period)
        if pr is None:
            continue
        labels.append(f"{r.source.display_name} ({r.source.id_client})")
        values.append(getter(pr))
    return labels, values


# --------------------------------------------------------------------------
# coverage/
# --------------------------------------------------------------------------

def generate_coverage_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    labels, values = _client_labels_and_values(result, "6M", lambda pr: pr.pct_comparable)
    if not labels:
        return []
    fig, ax = _new_fig((9, 4.5))
    ax.bar(labels, values, color=COLOR_ML)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% comparable", color="#52514e", fontsize=9)
    plt_setp_rotation(ax)
    _apply_title(ax, "Cobertura (% comparable) por cliente", f"{visible_label('6M')} | {len(labels)} clientes")
    return [_save_close(fig, out_dir / "01_coverage_by_client.png")]


def plt_setp_rotation(ax) -> None:
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")


# --------------------------------------------------------------------------
# semester/
# --------------------------------------------------------------------------

def generate_semester_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    generated = []
    labels, scp_vals = _client_labels_and_values(result, "6M", lambda pr: pr.wape.get("scp_wape_global"))
    _, ml_vals = _client_labels_and_values(result, "6M", lambda pr: pr.wape.get("ml_wape_global"))
    if labels:
        x = np.arange(len(labels))
        fig, ax = _new_fig((max(9, len(labels) * 1.1), 4.8))
        width = 0.35
        ax.bar(x - width / 2, [v * 100 if v == v else 0 for v in scp_vals], width, color=COLOR_SCP, label="SCP")
        ax.bar(x + width / 2, [v * 100 if v == v else 0 for v in ml_vals], width, color=COLOR_ML, label="ML")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        plt_setp_rotation(ax)
        ax.legend(frameon=False, fontsize=8)
        ax.set_ylabel("WAPE (%)", color="#52514e", fontsize=9)
        _apply_title(ax, "WAPE semestral (6M) por cliente", f"{len(labels)} clientes")
        generated.append(_save_close(fig, out_dir / "01_wape_by_client.png"))

    labels2, imp_vals = _client_labels_and_values(result, "6M", lambda pr: pr.wape.get("improvement_pct"))
    if labels2:
        colors = [COLOR_ML if (v == v and v > 0) else COLOR_SCP for v in imp_vals]
        fig, ax = _new_fig((max(9, len(labels2) * 1.1), 4.8))
        ax.bar(labels2, imp_vals, color=colors)
        ax.axhline(0, color="#c3c2b7", linewidth=1)
        plt_setp_rotation(ax)
        ax.set_ylabel("Mejora relativa ponderada (%)", color="#52514e", fontsize=9)
        _apply_title(ax, "Mejora semestral (6M) por cliente", f"{len(labels2)} clientes")
        generated.append(_save_close(fig, out_dir / "02_improvement_by_client.png"))

    labels3, red_vals = _client_labels_and_values(result, "6M", lambda pr: pr.abs_error_reduction_total)
    if labels3:
        colors = [COLOR_ML if (v == v and v >= 0) else COLOR_SCP for v in red_vals]
        fig, ax = _new_fig((max(9, len(labels3) * 1.1), 4.8))
        ax.bar(labels3, red_vals, color=colors)
        ax.axhline(0, color="#c3c2b7", linewidth=1)
        plt_setp_rotation(ax)
        ax.set_ylabel("Reduccion absoluta de error", color="#52514e", fontsize=9)
        _apply_title(ax, "Reduccion absoluta (6M) por cliente", f"{len(labels3)} clientes")
        generated.append(_save_close(fig, out_dir / "03_abs_reduction_by_client.png"))

    gp = result.periods["6M"]
    mean_v = gp.client_improvement_stats.get("mean")
    median_v = gp.client_improvement_stats.get("median")
    if mean_v == mean_v:
        fig, ax = _new_fig((5, 4.2))
        bars = ax.bar(["Media entre clientes", "Mediana entre clientes"], [mean_v, median_v], color=[COLOR_TIE, COLOR_ML], width=0.5)
        for bar, val in zip(bars, [mean_v, median_v]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:+.1f}%",
                     ha="center", va="bottom" if val >= 0 else "top", fontsize=10, color="#0b0b0b")
        ax.axhline(0, color="#c3c2b7", linewidth=1)
        ax.set_ylabel("Mejora relativa (%)", color="#52514e", fontsize=9)
        _apply_title(ax, "Media vs mediana de mejora entre clientes (6M)", f"n={gp.client_improvement_stats.get('count', 0)} clientes")
        generated.append(_save_close(fig, out_dir / "04_client_improvement_mean_vs_median.png"))

    return generated


# --------------------------------------------------------------------------
# quarters/
# --------------------------------------------------------------------------

def generate_quarters_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    recent, older = result.periods["RECENT_3M"], result.periods["OLDER_3M"]
    generated = []

    fig, ax = _new_fig((6, 4.2))
    labels = [visible_label("RECENT_3M"), visible_label("OLDER_3M")]
    scp_vals = [recent.scp_wape_global * 100, older.scp_wape_global * 100]
    ml_vals = [recent.ml_wape_global * 100, older.ml_wape_global * 100]
    x = np.arange(2)
    width = 0.3
    ax.bar(x - width / 2, scp_vals, width, color=COLOR_SCP, label="SCP")
    ax.bar(x + width / 2, ml_vals, width, color=COLOR_ML, label="ML")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylabel("WAPE (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "WAPE global ponderado: primer vs segundo trimestre", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "01_wape_recent_vs_older.png"))

    fig, ax = _new_fig((6, 4.2))
    values = [recent.global_improvement_pct, older.global_improvement_pct]
    colors = [COLOR_ML if v == v and v > 0 else COLOR_SCP for v in values]
    bars = ax.bar(labels, values, color=colors, width=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:+.1f}%",
                 ha="center", va="bottom" if val >= 0 else "top", fontsize=10, color="#0b0b0b")
    ax.axhline(0, color="#c3c2b7", linewidth=1)
    ax.set_ylabel("Mejora global ponderada (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "Mejora global ponderada: primer vs segundo trimestre", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "02_improvement_recent_vs_older.png"))

    return generated


# --------------------------------------------------------------------------
# monthly/
# --------------------------------------------------------------------------

def generate_monthly_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    generated = []

    fig, ax = _new_fig((8.5, 4.5))
    scp_vals = [result.periods[m].scp_wape_global * 100 for m in MONTHLY_PERIODS]
    ml_vals = [result.periods[m].ml_wape_global * 100 for m in MONTHLY_PERIODS]
    ax.plot(MONTHLY_PERIODS, scp_vals, marker="o", color=COLOR_SCP, label="SCP", linewidth=2)
    ax.plot(MONTHLY_PERIODS, ml_vals, marker="o", color=COLOR_ML, label="ML", linewidth=2)
    ax.legend(frameon=False, fontsize=8)
    ax.set_ylabel("WAPE global ponderado (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "Evolucion mensual del WAPE global (M1-M6)", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "01_wape_evolution_global.png"))

    fig, ax = _new_fig((9, 5))
    for r in result.client_results:
        vals = [r.periods[m].wape.get("improvement_pct") if m in r.periods else np.nan for m in MONTHLY_PERIODS]
        ax.plot(MONTHLY_PERIODS, vals, marker="o", linewidth=1.3, alpha=0.8, label=f"{r.source.display_name} ({r.source.id_client})")
    ax.axhline(0, color="#c3c2b7", linewidth=1)
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.set_ylabel("Mejora relativa ponderada (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "Evolucion mensual de la mejora por cliente", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "02_improvement_evolution_by_client.png"))

    return generated


# --------------------------------------------------------------------------
# clients/
# --------------------------------------------------------------------------

def generate_clients_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    from src.periods import ALL_PERIODS

    generated = []
    fig, ax = _new_fig((9.5, 4.5))
    values = [result.periods[p].client_improvement_stats.get("pct_improved") for p in ALL_PERIODS]
    ax.bar(ALL_PERIODS, values, color=COLOR_ML)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% clientes donde mejora ML", color="#52514e", fontsize=9)
    _apply_title(ax, "% de clientes donde mejora ML, por periodo", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "01_pct_clients_improving_by_period.png"))

    fig, ax = _new_fig((9.5, 4.5))
    values = [result.periods[p].winner_counts.get("ML", {}).get("pct") for p in ALL_PERIODS]
    ax.bar(ALL_PERIODS, values, color=COLOR_ML)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% series donde gana ML", color="#52514e", fontsize=9)
    _apply_title(ax, "% de series donde gana ML, por periodo", f"{len(result.client_results)} clientes")
    generated.append(_save_close(fig, out_dir / "02_pct_series_ml_wins_by_period.png"))

    return generated


# --------------------------------------------------------------------------
# models/ y classifications/
# --------------------------------------------------------------------------

def generate_models_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    table = global_category_performance_table(result.client_results, MODEL_CLASSIFICATION_PERIOD, "ML_BEST_MODEL")
    if table.empty:
        return []
    table = table.sort_values("n_comparable", ascending=False).head(10).iloc[::-1]
    fig, ax = _new_fig((8.5, 5))
    bars = ax.barh(table["category"], table["win_rate_ml_pct"], color=COLOR_ML)
    for bar, n in zip(bars, table["n_comparable"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" n={n}", va="center", fontsize=8, color="#52514e")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Tasa de victoria ML (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "Modelos ML y tasa de victoria (todos los clientes)", visible_label(MODEL_CLASSIFICATION_PERIOD))
    return [_save_close(fig, out_dir / "01_global_models_win_rate.png")]


def generate_classifications_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    table = global_category_performance_table(result.client_results, MODEL_CLASSIFICATION_PERIOD, "SERIES_CLASSIFICATION")
    if table.empty:
        return []
    table = table.sort_values("n_comparable", ascending=False).head(10).iloc[::-1]
    fig, ax = _new_fig((8.5, 5))
    bars = ax.barh(table["category"], table["win_rate_ml_pct"], color=COLOR_ML)
    for bar, n in zip(bars, table["n_comparable"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" n={n}", va="center", fontsize=8, color="#52514e")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Tasa de victoria ML (%)", color="#52514e", fontsize=9)
    _apply_title(ax, "SERIES_CLASSIFICATION y tasa de victoria (todos los clientes)", visible_label(MODEL_CLASSIFICATION_PERIOD))
    return [_save_close(fig, out_dir / "01_global_classifications_win_rate.png")]


# --------------------------------------------------------------------------
# impact_and_risk/
# --------------------------------------------------------------------------

def contribution_colors(values) -> list[str]:
    """
    Colorea por el signo de ABS_ERROR_REDUCTION (valor absoluto, no % del
    total): cuando la reduccion neta total es negativa o cercana a cero, el
    PORCENTAJE de contribucion invierte de signo respecto al valor real (ver
    la nota en el informe Markdown, seccion 15); el valor absoluto es
    inequivoco: positivo = ML reduce error, negativo = ML lo aumenta.
    """
    return [COLOR_ML if v >= 0 else COLOR_SCP for v in values]


def generate_impact_and_risk_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    generated = []
    gp = result.periods[MODEL_CLASSIFICATION_PERIOD]
    # Se combinan las dos tablas (reduce / aumenta) solo para el grafico:
    # el valor representado y usado para colorear sigue siendo
    # ABS_ERROR_REDUCTION (inequivoco), nunca un % sobre la reduccion neta.
    combined = pd.concat(
        [gp.client_reduction_table[["ETIQUETA", "ABS_ERROR_REDUCTION"]] if not gp.client_reduction_table.empty else pd.DataFrame(columns=["ETIQUETA", "ABS_ERROR_REDUCTION"]),
         gp.client_deterioration_table[["ETIQUETA", "ABS_ERROR_REDUCTION"]] if not gp.client_deterioration_table.empty else pd.DataFrame(columns=["ETIQUETA", "ABS_ERROR_REDUCTION"])],
        ignore_index=True,
    )
    if not combined.empty:
        sorted_contrib = combined.sort_values("ABS_ERROR_REDUCTION", ascending=False)
        fig, ax = _new_fig((9, 4.8))
        colors = contribution_colors(sorted_contrib["ABS_ERROR_REDUCTION"])
        ax.bar(sorted_contrib["ETIQUETA"], sorted_contrib["ABS_ERROR_REDUCTION"], color=colors)
        ax.axhline(0, color="#c3c2b7", linewidth=1)
        plt_setp_rotation(ax)
        ax.set_ylabel("Reduccion absoluta de error (positivo = ML mejor)", color="#52514e", fontsize=9)
        subtitle = (
            f"reduccion positiva total={gp.reduction_totals['REDUCCION_POSITIVA_TOTAL']:,.0f} | "
            f"deterioro total absoluto={gp.reduction_totals['DETERIORO_TOTAL_ABSOLUTO']:,.0f} | "
            f"reduccion neta={gp.reduction_totals['REDUCCION_NETA']:,.0f}"
        )
        _apply_title(ax, "Reduccion absoluta de error por cliente (6M)", subtitle)
        generated.append(_save_close(fig, out_dir / "01_client_contribution_to_reduction.png"))

    values = _global_series_improvement_values(result.client_results, MODEL_CLASSIFICATION_PERIOD).dropna()
    if not values.empty:
        n_below = int((values < -IMPROVEMENT_CLIP_BOUND).sum())
        n_above = int((values > IMPROVEMENT_CLIP_BOUND).sum())
        clipped = values.clip(-IMPROVEMENT_CLIP_BOUND, IMPROVEMENT_CLIP_BOUND)
        fig, ax = _new_fig((8.5, 4.8))
        ax.hist(clipped, bins=40, color=COLOR_ML, edgecolor="#fcfcfb", linewidth=0.5)
        ax.axvline(0, color="#52514e", linewidth=1.2, linestyle="--")
        subtitle = (
            f"n={len(values)} series | eje recortado a +/-{IMPROVEMENT_CLIP_BOUND:.0f}% "
            f"({n_below} por debajo, {n_above} por encima; estadisticas sin recortar)"
        )
        _apply_title(ax, "Distribucion global de mejora por serie (6M, todos los clientes)", subtitle)
        ax.set_xlabel("% mejora ML vs SCP (positivo = ML mejor)", color="#52514e", fontsize=9)
        ax.set_ylabel("N series", color="#52514e", fontsize=9)
        generated.append(_save_close(fig, out_dir / "02_global_improvement_distribution.png"))

    return generated


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def generate_global_charts(result: GlobalAnalysisResult, charts_dir: Path) -> list[str]:
    import matplotlib.pyplot as plt

    generated: list[str] = []
    try:
        generated += generate_coverage_charts(result, charts_dir / "coverage")
        generated += generate_semester_charts(result, charts_dir / "semester")
        generated += generate_quarters_charts(result, charts_dir / "quarters")
        generated += generate_monthly_charts(result, charts_dir / "monthly")
        generated += generate_clients_charts(result, charts_dir / "clients")
        generated += generate_models_charts(result, charts_dir / "models")
        generated += generate_classifications_charts(result, charts_dir / "classifications")
        generated += generate_impact_and_risk_charts(result, charts_dir / "impact_and_risk")
    finally:
        plt.close("all")
    return generated
