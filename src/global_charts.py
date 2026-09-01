"""
Graficos globales (comparativa entre clientes), 9 subcarpetas: coverage,
semester, quarters, monthly, clients, models, classifications, impact_and_risk,
portfolio.

Mismas reglas de visualizacion que los graficos individuales (src/charts.py):
ML=azul, SCP=rojo, Empate=gris, sin cortar titulos, cerrar todas las figuras,
no recortar valores extremos silenciosamente.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.charts import (
    COLOR_AXIS,
    COLOR_ML,
    COLOR_SCP,
    COLOR_TEXT_SECONDARY,
    COLOR_TIE,
    _apply_title,
    _new_fig,
    _pareto_bar_chart,
    _save_close,
)
from src.global_analysis import GlobalAnalysisResult, _global_series_improvement_values
from src.periods import MONTHLY_PERIODS, visible_label
from src.phase8_presentation import sort_volume_table, volume_bucket_label_es
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
)
from src.portfolio_presentation import (
    BLOCK_LABELS,
    ENGINE_LABELS,
    SCHEMA_FAMILIES,
    SCHEMA_MODEL_STABILITY_SUMMARY,
    prepare_portfolio_table,
)

MODEL_CLASSIFICATION_PERIOD = "6M"
IMPROVEMENT_CLIP_BOUND = 100.0

CHART_SUBFOLDERS = (
    "coverage", "semester", "quarters", "monthly", "clients", "models",
    "classifications", "impact_and_risk", "portfolio",
)

PORTFOLIO_FAMILY_CHART = "01_optimizer_family_selection_share.png"
PORTFOLIO_STABILITY_CHART = "02_portfolio_stability.png"
COLOR_PORTFOLIO_STABLE = "#3d7a5a"
COLOR_PORTFOLIO_CHANGED = "#c87941"


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
    return []


def generate_classifications_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    return []


# --------------------------------------------------------------------------
# portfolio/
# --------------------------------------------------------------------------

def _optimizer_family_selection_chart_data(result: GlobalAnalysisResult) -> dict | None:
    """Prepare chart coordinates from the already-calculated family table.

    The presentation adapter supplies deterministic block/family labels and
    works on a deep copy. Missing categories in one otherwise populated block
    represent an observed zero share for that block; missing blocks or
    non-finite shares make the comparison non-representable and omit it.
    """
    portfolio = result.portfolio
    if not portfolio.availability.available or portfolio.optimizer is None:
        return None
    source = portfolio.optimizer.family_tables
    if source.empty:
        return None

    table = prepare_portfolio_table(source, SCHEMA_FAMILIES).dataframe
    block_labels = (
        BLOCK_LABELS[BLOCK_OLDER_3M],
        BLOCK_LABELS[BLOCK_RECENT_3M],
    )
    by_block: dict[str, pd.DataFrame] = {}
    for block in block_labels:
        rows = table.loc[table["block"] == block]
        if rows.empty or not np.isfinite(rows["selection_share_of_assignable"].astype(float)).all():
            return None
        by_block[block] = rows

    families = list(dict.fromkeys(table["family"].tolist()))
    if not families:
        return None
    values: dict[str, list[float]] = {}
    for block in block_labels:
        shares = dict(zip(
            by_block[block]["family"],
            by_block[block]["selection_share_of_assignable"].astype(float),
        ))
        values[block] = [shares.get(family, 0.0) * 100 for family in families]
    return {"families": families, "blocks": block_labels, "values": values}


def _portfolio_stability_chart_data(result: GlobalAnalysisResult) -> list[dict] | None:
    """Prepare 100% stability bars without adding not-evaluable pairs.

    ``stability_rate`` is consumed directly from the analytical result. The
    changed segment is only its graphical complement; counts are retained for
    labels and ``not_evaluable_count`` remains separate from both segments.
    """
    portfolio = result.portfolio
    if not portfolio.availability.available or portfolio.stability is None:
        return None
    source = portfolio.stability.model_summary
    if source.empty:
        return None

    table = prepare_portfolio_table(source, SCHEMA_MODEL_STABILITY_SUMMARY).dataframe
    rows: list[dict] = []
    for engine_key in (ENGINE_SCP_AUTO, ENGINE_OPTIMIZER):
        engine = ENGINE_LABELS[engine_key]
        match = table.loc[table["engine"] == engine]
        if len(match) != 1:
            return None
        row = match.iloc[0]
        n_evaluable = int(row["n_evaluable"])
        stable_count = int(row["stable_count"])
        changed_count = int(row["changed_count"])
        if stable_count + changed_count != n_evaluable:
            return None
        if n_evaluable:
            stability_rate = float(row["stability_rate"])
            if not np.isfinite(stability_rate) or not 0 <= stability_rate <= 1:
                return None
            stable_pct = stability_rate * 100
            changed_pct = 100 - stable_pct
        else:
            stable_pct = changed_pct = 0.0
        rows.append({
            "engine": engine,
            "n_evaluable": n_evaluable,
            "stable_count": stable_count,
            "changed_count": changed_count,
            "not_evaluable_count": int(row["not_evaluable_count"]),
            "stable_pct": stable_pct,
            "changed_pct": changed_pct,
        })
    return rows if any(row["n_evaluable"] for row in rows) else None


def _chart_optimizer_family_selection_share(
    result: GlobalAnalysisResult,
    out_dir: Path,
) -> str | None:
    chart_data = _optimizer_family_selection_chart_data(result)
    if chart_data is None:
        return None

    families = chart_data["families"]
    older_label, recent_label = chart_data["blocks"]
    older = chart_data["values"][older_label]
    recent = chart_data["values"][recent_label]
    x = np.arange(len(families))
    width = 0.36
    fig, ax = _new_fig((max(8.5, len(families) * 1.35), 4.8))
    older_bars = ax.bar(x - width / 2, older, width, color=COLOR_TIE, label=older_label)
    recent_bars = ax.bar(x + width / 2, recent, width, color=COLOR_ML, label=recent_label)
    ax.bar_label(older_bars, fmt="%.1f%%", padding=2, fontsize=8, color=COLOR_TEXT_SECONDARY)
    ax.bar_label(recent_bars, fmt="%.1f%%", padding=2, fontsize=8, color=COLOR_TEXT_SECONDARY)
    ax.set_xticks(x)
    ax.set_xticklabels(families)
    plt_setp_rotation(ax)
    ax.set_ylim(0, max(105, max([*older, *recent]) * 1.18))
    ax.set_ylabel("Cuota de selección observada (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
    _apply_title(
        ax,
        "Cuota de selección observada por familia — SCP Classic Optimizer",
        "Cuota sobre asignaciones posibles de cada período; se muestran todas las familias observadas.",
    )
    return _save_close(fig, out_dir / PORTFOLIO_FAMILY_CHART)


def _chart_portfolio_stability(result: GlobalAnalysisResult, out_dir: Path) -> str | None:
    rows = _portfolio_stability_chart_data(result)
    if rows is None:
        return None

    labels = [row["engine"] for row in rows]
    stable = [row["stable_pct"] for row in rows]
    changed = [row["changed_pct"] for row in rows]
    y = np.arange(len(rows))
    fig, ax = _new_fig((9.5, 4.5))
    ax.barh(y, stable, color=COLOR_PORTFOLIO_STABLE, label="Estable")
    ax.barh(y, changed, left=stable, color=COLOR_PORTFOLIO_CHANGED, label="Cambió")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Distribución sobre pares evaluables (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
    for index, row in enumerate(rows):
        if not row["n_evaluable"]:
            ax.text(50, index, "Sin población evaluable", ha="center", va="center", fontsize=8, color=COLOR_TEXT_SECONDARY)
            continue
        if row["stable_pct"] >= 12:
            ax.text(row["stable_pct"] / 2, index, f"Estable: {row['stable_count']}", ha="center", va="center", fontsize=8, color="white")
        if row["changed_pct"] >= 12:
            ax.text(row["stable_pct"] + row["changed_pct"] / 2, index, f"Cambió: {row['changed_count']}", ha="center", va="center", fontsize=8, color="white")

    not_evaluable = " · ".join(
        f"{row['engine']}: {row['not_evaluable_count']}" for row in rows
    )
    _apply_title(
        ax,
        "Estabilidad observada entre períodos",
        f"{BLOCK_LABELS[BLOCK_OLDER_3M]} → {BLOCK_LABELS[BLOCK_RECENT_3M]} | "
        f"No evaluables (fuera del denominador): {not_evaluable}",
    )
    return _save_close(fig, out_dir / PORTFOLIO_STABILITY_CHART)


def generate_portfolio_charts(result: GlobalAnalysisResult, out_dir: Path) -> list[str]:
    """Generate only the two approved global portfolio charts when representable."""
    generated: list[str] = []
    for chart in (_chart_optimizer_family_selection_share, _chart_portfolio_stability):
        path = chart(result, out_dir)
        if path:
            generated.append(path)
    return generated


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


def pareto_client_chart_label(row) -> str:
    """
    Etiqueta de eje para los charts Pareto de clientes globales (03/04):
    DISPLAY_NAME solo, repetido entre clientes que comparten un mismo CSV
    fisico multi-cliente (ETIQUETA identica en ese caso), no identifica de
    forma inequivoca la barra. ID_CLIENT si es unico por construccion: se
    anade entre parentesis para desambiguar sin dejar de mostrar el nombre.
    Puramente de renderizado -- no toca group.table ni ninguna tabla de
    Excel/Markdown/HTML.
    """
    return f"{row['DISPLAY_NAME']} ({row['ID_CLIENT']})"


def pareto_series_chart_label(row) -> str:
    """
    Etiqueta de eje para los charts Pareto de series globales (05/06):
    ID_CONFIGURATION en solitario puede colisionar entre clientes distintos
    (identidad real = ID_CLIENT + ID_CONFIGURATION, ver global_pareto_series);
    formato compacto "<ID_CLIENT>-<ID_CONFIGURATION>" para identificar la
    barra de forma inequivoca sin saturar el eje. Puramente de renderizado.
    """
    return f"{row['ID_CLIENT']}-{row['ID_CONFIGURATION']}"


def _chart_global_bias_by_volume_bucket(result: GlobalAnalysisResult, out_dir: Path, fname: str) -> str | None:
    """
    Unico chart nuevo de Fase 8D: Bias agregado SCP vs ML por bucket de
    volumen relativo, agregado globalmente (6M). Lee
    GlobalPeriodResult.phase8.volume_table ya calculado (nunca recalcula
    Bias ni buckets aqui). Antes de dibujar cada bucket se comprueba
    finitud de scp_bias_agg/ml_bias_agg por separado: un bucket con algun
    valor no finito (NaN/inf) se excluye SOLO de este chart -- nunca se
    sustituye por 0 y nunca se elimina de volume_table (Excel/Markdown/HTML
    siguen mostrando la fila tal cual la entrega el nucleo). Si ningun
    bucket queda con ambos valores finitos, no se genera el fichero.
    """
    phase8 = result.periods[MODEL_CLASSIFICATION_PERIOD].phase8
    if phase8 is None:
        return None
    table = sort_volume_table(phase8.volume_table)
    if table is None or table.empty:
        return None

    plottable = table[np.isfinite(table["scp_bias_agg"]) & np.isfinite(table["ml_bias_agg"])]
    if plottable.empty:
        return None

    labels = [volume_bucket_label_es(v) for v in plottable["category"]]
    scp_vals = (plottable["scp_bias_agg"] * 100).tolist()
    ml_vals = (plottable["ml_bias_agg"] * 100).tolist()

    fig, ax = _new_fig((7.5, 4.5))
    x = np.arange(len(labels))
    width = 0.35
    ax.bar(x - width / 2, scp_vals, width=width, color=COLOR_SCP, label="SCP")
    ax.bar(x + width / 2, ml_vals, width=width, color=COLOR_ML, label="ML")
    ax.axhline(0, color=COLOR_AXIS, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Bias agregado (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    _apply_title(
        ax, "Bias agregado SCP vs ML por volumen relativo (global)",
        f"{visible_label(MODEL_CLASSIFICATION_PERIOD)} | todos los clientes | buckets RELATIVOS a cada cliente",
    )
    return _save_close(fig, out_dir / fname)


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

    # Pareto (aditivo, no sustituye a 01/02 anteriores): lee gp.pareto_clients/
    # .pareto_series ya calculados en global_analysis.py, nunca los recalcula.
    # Las etiquetas de eje (label_fn) son puramente de renderizado: no anaden
    # columnas a group.table (compartida con Excel/Markdown/HTML) ni afectan
    # a identidad de calculo, desempate o umbrales.
    period_tag = visible_label(MODEL_CLASSIFICATION_PERIOD)
    if gp.pareto_clients is not None:
        path = _pareto_bar_chart(
            gp.pareto_clients.improvement, "Pareto de clientes - mejora", period_tag, COLOR_ML,
            out_dir / "03_pareto_clients_reduction.png", top_n=None, unit_label="clientes",
            label_fn=pareto_client_chart_label,
        )
        if path:
            generated.append(path)
        path = _pareto_bar_chart(
            gp.pareto_clients.deterioration, "Pareto de clientes - deterioro", period_tag, COLOR_SCP,
            out_dir / "04_pareto_clients_increase.png", top_n=None, unit_label="clientes",
            label_fn=pareto_client_chart_label,
        )
        if path:
            generated.append(path)

    if gp.pareto_series is not None:
        path = _pareto_bar_chart(
            gp.pareto_series.improvement, "Pareto de series global - mejora", period_tag, COLOR_ML,
            out_dir / "05_pareto_series_reduction.png", label_fn=pareto_series_chart_label,
        )
        if path:
            generated.append(path)
        path = _pareto_bar_chart(
            gp.pareto_series.deterioration, "Pareto de series global - deterioro", period_tag, COLOR_SCP,
            out_dir / "06_pareto_series_increase.png", label_fn=pareto_series_chart_label,
        )
        if path:
            generated.append(path)

    path = _chart_global_bias_by_volume_bucket(result, out_dir, "07_global_bias_by_volume_bucket.png")
    if path:
        generated.append(path)

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
        generated += generate_portfolio_charts(result, charts_dir / "portfolio")
    finally:
        plt.close("all")
    return generated
