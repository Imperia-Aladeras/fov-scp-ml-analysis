"""
Graficos individuales por cliente (7 subcarpetas: coverage, semester,
quarters, monthly, models, classifications, impact_and_risk).

Reglas de visualizacion (docs/analysis_requirements.md):
    - ML: azul. SCP: rojo. Empate: gris. Colores coherentes en todos los graficos.
    - No cortar titulos. Incluir tamano de muestra, periodo y cliente.
    - Cerrar todas las figuras (no acumular memoria).
    - No recortar valores extremos silenciosamente: si un histograma se
      limita a un rango, se indica en el titulo/subtitulo, se muestra cuantos
      valores quedan fuera, y las estadisticas se calculan sin recorte.

Cuando un cliente no tiene series comparables en un periodo, simplemente no
se generan los graficos de performance de ese periodo (no se inventan datos
ni se dibujan graficos vacios enganosos). Los graficos de cobertura si se
generan siempre: son validos incluso con cero comparables.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.client_analysis import ClientAnalysisResult
from src.metrics import relative_improvement_row
from src.models import category_performance_table, top_absolute_impact, top_percentage_changes
from src.periods import period_columns, visible_label

COLOR_ML = "#2a78d6"
COLOR_SCP = "#e34948"
COLOR_TIE = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_AXIS = "#c3c2b7"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_SURFACE = "#fcfcfb"

MODEL_CLASSIFICATION_PERIOD = "6M"
IMPROVEMENT_CLIP_BOUND = 100.0


def _new_fig(figsize: tuple[float, float] = (7.5, 4.2)):
    fig, ax = plt.subplots(figsize=figsize, facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(COLOR_AXIS)
    ax.spines["bottom"].set_color(COLOR_AXIS)
    ax.tick_params(colors=COLOR_TEXT_SECONDARY, labelsize=9)
    ax.yaxis.grid(True, color=COLOR_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _apply_title(ax, title: str, subtitle: str) -> None:
    """
    Titulo (via ax.set_title, con pad) + subtitulo en coordenadas de FIGURA
    (no de ejes): usar ax.transAxes para el subtitulo lo situaba a menudo
    encima del propio titulo (se solapaban) porque no reserva espacio en el
    layout. fig.text si es tenido en cuenta por el rect de tight_layout.
    """
    ax.set_title(title, color=COLOR_TEXT, fontsize=12, loc="left", pad=16)
    ax.figure.text(0.01, 0.975, subtitle, fontsize=8.5, color=COLOR_TEXT_SECONDARY, ha="left", va="top")


def _save_close(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def _client_tag(result: ClientAnalysisResult) -> str:
    source = result.source
    return f"{source.display_name} — ClientId {source.id_client}"


# --------------------------------------------------------------------------
# coverage/
# --------------------------------------------------------------------------

def _chart_comparison_status(result: ClientAnalysisResult, out_dir: Path) -> str | None:
    dist = result.comparison_status_distribution
    if not dist:
        return None
    items = sorted(dist.items(), key=lambda kv: -kv[1])
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    fig, ax = _new_fig((8.5, 4.5))
    colors = [COLOR_ML if l == "COMPARABLE" else COLOR_TIE for l in labels]
    bars = ax.barh(labels, values, color=colors)
    ax.invert_yaxis()
    for bar, val in zip(bars, values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {val:,}".replace(",", "."),
                 va="center", fontsize=8, color=COLOR_TEXT)
    _apply_title(ax, "Distribucion de COMPARISON_STATUS", f"{_client_tag(result)} | n={sum(values):,}".replace(",", "."))
    return _save_close(fig, out_dir / "01_comparison_status_distribution.png")


def _chart_coverage_by_period(result: ClientAnalysisResult, out_dir: Path) -> str | None:
    periods = list(result.periods.values())
    if not periods:
        return None
    labels = [pr.period for pr in periods]
    values = [pr.pct_comparable for pr in periods]
    fig, ax = _new_fig((9, 4.5))
    ax.bar(labels, values, color=COLOR_ML, width=0.6)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% comparable", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, "Cobertura (% comparable) por periodo", f"{_client_tag(result)} | candidatas={result.n_candidates:,}".replace(",", "."))
    plt.setp(ax.get_xticklabels(), rotation=0)
    return _save_close(fig, out_dir / "02_coverage_by_period.png")


def _chart_reason_distribution(title: str, fname: str, counts: dict, result: ClientAnalysisResult, out_dir: Path) -> str | None:
    if not counts:
        return None
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    labels, values = [k for k, _ in items], [v for _, v in items]
    fig, ax = _new_fig((7.5, 4))
    ax.barh(labels, values, color=COLOR_TIE)
    ax.invert_yaxis()
    _apply_title(ax, title, f"{_client_tag(result)} | n={sum(values):,}".replace(",", "."))
    return _save_close(fig, out_dir / fname)


def generate_coverage_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    generated = []
    for fn, args in (
        (_chart_comparison_status, (result, out_dir)),
        (_chart_coverage_by_period, (result, out_dir)),
    ):
        path = fn(*args)
        if path:
            generated.append(path)
    m6 = result.periods.get("6M")
    if m6 is not None:
        path = _chart_reason_distribution(
            "Motivos de exclusion ML (ML_EXCLUSION_REASON)", "03_ml_exclusion_reasons.png",
            m6.ml_exclusion_reason_counts, result, out_dir,
        )
        if path:
            generated.append(path)
        path = _chart_reason_distribution(
            "Motivos de ausencia de forecast SCP (SCP_NO_OUTPUT_REASON, 6M)", "04_scp_no_output_reasons.png",
            m6.scp_no_output_reason_counts, result, out_dir,
        )
        if path:
            generated.append(path)
    return generated


# --------------------------------------------------------------------------
# semester/
# --------------------------------------------------------------------------

def _chart_wape_comparison(period: str, result: ClientAnalysisResult, out_dir: Path, fname: str) -> str | None:
    pr = result.periods.get(period)
    if pr is None or pr.n_comparable == 0:
        return None
    scp_w = pr.wape.get("scp_wape_global")
    ml_w = pr.wape.get("ml_wape_global")
    if scp_w is None or ml_w is None or (isinstance(scp_w, float) and np.isnan(scp_w)):
        return None
    fig, ax = _new_fig((5.5, 4.2))
    bars = ax.bar(["SCP", "ML"], [scp_w * 100, ml_w * 100], color=[COLOR_SCP, COLOR_ML], width=0.5)
    for bar, val in zip(bars, [scp_w * 100, ml_w * 100]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:.1f}%",
                 ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_ylabel("WAPE (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, f"WAPE global ponderado SCP vs ML - {pr.label}",
                 f"{_client_tag(result)} | n={pr.n_comparable:,}".replace(",", "."))
    return _save_close(fig, out_dir / fname)


def _chart_winner_distribution(period: str, result: ClientAnalysisResult, out_dir: Path, fname: str) -> str | None:
    pr = result.periods.get(period)
    if pr is None or pr.n_comparable == 0:
        return None
    wc = pr.winner_counts
    order = [m for m in ("ML", "SCP", "TIE") if wc.get(m, {}).get("n", 0) > 0 or m in ("ML", "SCP")]
    colors = {"ML": COLOR_ML, "SCP": COLOR_SCP, "TIE": COLOR_TIE}
    values = [wc.get(m, {}).get("n", 0) for m in order]
    fig, ax = _new_fig((5.5, 4.2))
    bars = ax.bar(order, values, color=[colors[m] for m in order], width=0.55)
    for bar, m in zip(bars, order):
        pct = wc.get(m, {}).get("pct", float("nan"))
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                 f"{pct:.1f}%" if pct == pct else "n/d", ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_ylabel("N series", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, f"Distribucion de ganadores - {pr.label}", f"{_client_tag(result)} | n={pr.n_comparable:,}".replace(",", "."))
    return _save_close(fig, out_dir / fname)


def _chart_improvement_histogram(period: str, result: ClientAnalysisResult, out_dir: Path, fname: str) -> str | None:
    df = result.source.dataframe
    pr = result.periods.get(period)
    if df is None or pr is None or pr.comparable_mask is None or pr.n_comparable == 0:
        return None
    pcols = period_columns(period)
    sub = df.loc[pr.comparable_mask]
    values, _cases = relative_improvement_row(sub[pcols.scp_wape], sub[pcols.ml_wape])
    values = values.dropna()
    if values.empty:
        return None
    n_below = int((values < -IMPROVEMENT_CLIP_BOUND).sum())
    n_above = int((values > IMPROVEMENT_CLIP_BOUND).sum())
    clipped = values.clip(-IMPROVEMENT_CLIP_BOUND, IMPROVEMENT_CLIP_BOUND)
    fig, ax = _new_fig((8, 4.5))
    ax.hist(clipped, bins=40, color=COLOR_ML, edgecolor=COLOR_SURFACE, linewidth=0.5)
    ax.axvline(0, color=COLOR_TEXT_SECONDARY, linewidth=1.2, linestyle="--")
    subtitle = (
        f"{_client_tag(result)} | n={len(values):,} | eje recortado a +/-{IMPROVEMENT_CLIP_BOUND:.0f}% "
        f"({n_below} por debajo, {n_above} por encima; estadisticas sin recortar)".replace(",", ".")
    )
    _apply_title(ax, f"Distribucion de mejora relativa por serie - {pr.label}", subtitle)
    ax.set_xlabel("% mejora ML vs SCP (positivo = ML mejor)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel("N series", color=COLOR_TEXT_SECONDARY, fontsize=9)
    return _save_close(fig, out_dir / fname)


def _chart_abs_error_reduction(period: str, result: ClientAnalysisResult, out_dir: Path, fname: str) -> str | None:
    pr = result.periods.get(period)
    if pr is None or pr.n_comparable == 0:
        return None
    scp_err = pr.wape.get("scp_abs_error_sum")
    ml_err = pr.wape.get("ml_abs_error_sum")
    if scp_err is None or ml_err is None:
        return None
    fig, ax = _new_fig((5.5, 4.2))
    bars = ax.bar(["SCP", "ML"], [scp_err, ml_err], color=[COLOR_SCP, COLOR_ML], width=0.5)
    for bar, val in zip(bars, [scp_err, ml_err]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:,.0f}".replace(",", "."),
                 ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_ylabel("Error absoluto total", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(
        ax, f"Error absoluto total SCP vs ML - {pr.label}",
        f"{_client_tag(result)} | reduccion={pr.abs_error_reduction_total:,.0f}".replace(",", "."),
    )
    return _save_close(fig, out_dir / fname)


def _chart_model_win_rates(period: str, result: ClientAnalysisResult, out_dir: Path, fname: str, top_n: int = 8) -> str | None:
    df = result.source.dataframe
    pr = result.periods.get(period)
    if df is None or pr is None or pr.comparable_mask is None or pr.n_comparable == 0:
        return None
    pcols = period_columns(period)
    table = category_performance_table(df, pcols, pr.comparable_mask, "ML_BEST_MODEL")
    if table.empty:
        return None
    table = table.sort_values("n_comparable", ascending=False).head(top_n).iloc[::-1]
    fig, ax = _new_fig((8, 4.5))
    bars = ax.barh(table["category"], table["win_rate_ml_pct"], color=COLOR_ML)
    for bar, n in zip(bars, table["n_comparable"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" n={n}", va="center", fontsize=8, color=COLOR_TEXT_SECONDARY)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Tasa de victoria ML (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, f"Modelos ML y tasa de victoria - {pr.label}", f"{_client_tag(result)} | top {top_n} modelos por frecuencia")
    return _save_close(fig, out_dir / fname)


def generate_semester_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    generated = []
    for fn, fname in (
        (lambda: _chart_wape_comparison("6M", result, out_dir, "01_wape_scp_vs_ml.png"), None),
        (lambda: _chart_winner_distribution("6M", result, out_dir, "02_winner_distribution.png"), None),
        (lambda: _chart_improvement_histogram("6M", result, out_dir, "03_improvement_distribution.png"), None),
        (lambda: _chart_abs_error_reduction("6M", result, out_dir, "04_abs_error_reduction.png"), None),
        (lambda: _chart_model_win_rates("6M", result, out_dir, "05_models_win_rate.png"), None),
    ):
        path = fn()
        if path:
            generated.append(path)
    return generated


# --------------------------------------------------------------------------
# quarters/
# --------------------------------------------------------------------------

def generate_quarters_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    generated = []
    for path in (
        _chart_wape_comparison("RECENT_3M", result, out_dir, "01_wape_recent_3m.png"),
        _chart_wape_comparison("OLDER_3M", result, out_dir, "02_wape_older_3m.png"),
    ):
        if path:
            generated.append(path)

    recent, older = result.periods.get("RECENT_3M"), result.periods.get("OLDER_3M")
    if recent and older and recent.n_comparable and older.n_comparable:
        fig, ax = _new_fig((6, 4.2))
        labels = [visible_label("RECENT_3M"), visible_label("OLDER_3M")]
        values = [recent.wape.get("improvement_pct"), older.wape.get("improvement_pct")]
        colors = [COLOR_ML if v is not None and v == v and v > 0 else COLOR_SCP for v in values]
        bars = ax.bar(labels, values, color=colors, width=0.5)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:+.1f}%" if val == val else "n/d",
                     ha="center", va="bottom" if (val or 0) >= 0 else "top", fontsize=10, color=COLOR_TEXT)
        ax.axhline(0, color=COLOR_AXIS, linewidth=1)
        ax.set_ylabel("Mejora relativa ponderada (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
        _apply_title(ax, "Mejora comparativa entre trimestres", f"{_client_tag(result)}")
        generated.append(_save_close(fig, out_dir / "03_improvement_comparative.png"))

        fig, ax = _new_fig((7, 4.2))
        width = 0.25
        x = np.arange(3)
        for offset, method, color in ((-width, "ML", COLOR_ML), (0, "SCP", COLOR_SCP), (width, "TIE", COLOR_TIE)):
            vals = [recent.winner_counts.get(method, {}).get("n", 0), older.winner_counts.get(method, {}).get("n", 0), 0]
            ax.bar(x[:2] + offset, vals[:2], width=width, color=color, label=method)
        ax.set_xticks([0, 1])
        ax.set_xticklabels([visible_label("RECENT_3M"), visible_label("OLDER_3M")])
        ax.legend(frameon=False, fontsize=8)
        ax.set_ylabel("N series", color=COLOR_TEXT_SECONDARY, fontsize=9)
        _apply_title(ax, "Ganadores comparados entre trimestres", f"{_client_tag(result)}")
        generated.append(_save_close(fig, out_dir / "04_winners_comparative.png"))

        fig, ax = _new_fig((6, 4.2))
        vals = [recent.abs_error_reduction_total, older.abs_error_reduction_total]
        bars = ax.bar(labels, vals, color=COLOR_ML, width=0.5)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:,.0f}".replace(",", "."),
                     ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
        ax.axhline(0, color=COLOR_AXIS, linewidth=1)
        ax.set_ylabel("Reduccion absoluta de error", color=COLOR_TEXT_SECONDARY, fontsize=9)
        _apply_title(ax, "Reduccion absoluta comparada entre trimestres", f"{_client_tag(result)}")
        generated.append(_save_close(fig, out_dir / "05_abs_reduction_comparative.png"))

    return generated


# --------------------------------------------------------------------------
# monthly/
# --------------------------------------------------------------------------

def generate_monthly_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    months = [f"M{i}" for i in range(1, 7)]
    prs = [result.periods.get(m) for m in months]
    if not any(pr is not None and pr.n_comparable for pr in prs):
        return []

    generated = []

    fig, ax = _new_fig((8.5, 4.5))
    scp_vals = [pr.wape.get("scp_wape_global") * 100 if pr and pr.n_comparable else np.nan for pr in prs]
    ml_vals = [pr.wape.get("ml_wape_global") * 100 if pr and pr.n_comparable else np.nan for pr in prs]
    ax.plot(months, scp_vals, marker="o", color=COLOR_SCP, label="SCP", linewidth=2)
    ax.plot(months, ml_vals, marker="o", color=COLOR_ML, label="ML", linewidth=2)
    ax.set_ylabel("WAPE (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    _apply_title(ax, "Evolucion mensual del WAPE (M1-M6)", f"{_client_tag(result)}")
    generated.append(_save_close(fig, out_dir / "01_wape_evolution.png"))

    fig, ax = _new_fig((8.5, 4.5))
    imp_vals = [pr.wape.get("improvement_pct") if pr and pr.n_comparable else np.nan for pr in prs]
    ax.plot(months, imp_vals, marker="o", color=COLOR_ML, linewidth=2)
    ax.axhline(0, color=COLOR_AXIS, linewidth=1)
    ax.set_ylabel("Mejora relativa ponderada (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, "Evolucion mensual de la mejora relativa", f"{_client_tag(result)}")
    generated.append(_save_close(fig, out_dir / "02_improvement_evolution.png"))

    fig, ax = _new_fig((8.5, 4.5))
    reduction_vals = [pr.abs_error_reduction_total if pr and pr.n_comparable else np.nan for pr in prs]
    colors = [COLOR_ML if (v == v and v >= 0) else COLOR_SCP for v in reduction_vals]
    ax.bar(months, reduction_vals, color=colors)
    ax.axhline(0, color=COLOR_AXIS, linewidth=1)
    ax.set_ylabel("Reduccion absoluta de error", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, "Evolucion mensual de la reduccion absoluta", f"{_client_tag(result)}")
    generated.append(_save_close(fig, out_dir / "03_abs_reduction_evolution.png"))

    fig, ax = _new_fig((8.5, 4.5))
    pct_ml = [pr.winner_counts.get("ML", {}).get("pct") if pr and pr.n_comparable else np.nan for pr in prs]
    pct_scp = [pr.winner_counts.get("SCP", {}).get("pct") if pr and pr.n_comparable else np.nan for pr in prs]
    pct_tie = [pr.winner_counts.get("TIE", {}).get("pct") if pr and pr.n_comparable else np.nan for pr in prs]
    ax.plot(months, pct_ml, marker="o", color=COLOR_ML, label="ML", linewidth=2)
    ax.plot(months, pct_scp, marker="o", color=COLOR_SCP, label="SCP", linewidth=2)
    ax.plot(months, pct_tie, marker="o", color=COLOR_TIE, label="Empate", linewidth=2)
    ax.set_ylabel("% de series", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    _apply_title(ax, "Evolucion mensual de victorias ML/SCP/Empate", f"{_client_tag(result)}")
    generated.append(_save_close(fig, out_dir / "04_winner_pct_evolution.png"))

    fig, ax = _new_fig((8.5, 4.5))
    coverage_vals = [pr.pct_comparable if pr else np.nan for pr in prs]
    ax.bar(months, coverage_vals, color=COLOR_ML)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% comparable", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, "Cobertura mensual (% comparable)", f"{_client_tag(result)}")
    generated.append(_save_close(fig, out_dir / "05_coverage_evolution.png"))

    return generated


# --------------------------------------------------------------------------
# models/ y classifications/
# --------------------------------------------------------------------------

def generate_models_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    df = result.source.dataframe
    pr = result.periods.get(MODEL_CLASSIFICATION_PERIOD)
    if df is None or pr is None or pr.comparable_mask is None or pr.n_comparable == 0:
        return []
    pcols = period_columns(MODEL_CLASSIFICATION_PERIOD)
    generated = []

    path = _chart_model_win_rates(MODEL_CLASSIFICATION_PERIOD, result, out_dir, "01_ml_models_win_rate.png")
    if path:
        generated.append(path)

    scp_table = category_performance_table(df, pcols, pr.comparable_mask, "SCP_BEST_MODEL")
    if not scp_table.empty:
        table = scp_table.sort_values("n_comparable", ascending=False).head(8).iloc[::-1]
        fig, ax = _new_fig((8, 4.5))
        bars = ax.barh(table["category"], table["n_comparable"], color=COLOR_SCP)
        for bar, n in zip(bars, table["n_comparable"]):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" n={n}", va="center", fontsize=8, color=COLOR_TEXT_SECONDARY)
        ax.set_xlabel("Series comparables", color=COLOR_TEXT_SECONDARY, fontsize=9)
        _apply_title(ax, f"Modelos SCP por frecuencia - {visible_label(MODEL_CLASSIFICATION_PERIOD)}", f"{_client_tag(result)}")
        generated.append(_save_close(fig, out_dir / "02_scp_models_frequency.png"))

    return generated


def generate_classifications_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    df = result.source.dataframe
    pr = result.periods.get(MODEL_CLASSIFICATION_PERIOD)
    if df is None or pr is None or pr.comparable_mask is None or pr.n_comparable == 0:
        return []
    pcols = period_columns(MODEL_CLASSIFICATION_PERIOD)
    generated = []
    for idx, col in enumerate(("SERIES_CLASSIFICATION", "ML_CLASSIFICATION"), start=1):
        table = category_performance_table(df, pcols, pr.comparable_mask, col)
        if table.empty:
            continue
        table = table.sort_values("n_comparable", ascending=False).head(8).iloc[::-1]
        fig, ax = _new_fig((8, 4.5))
        bars = ax.barh(table["category"], table["win_rate_ml_pct"], color=COLOR_ML)
        for bar, n in zip(bars, table["n_comparable"]):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" n={n}", va="center", fontsize=8, color=COLOR_TEXT_SECONDARY)
        ax.set_xlim(0, 100)
        ax.set_xlabel("Tasa de victoria ML (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
        _apply_title(ax, f"{col} - tasa de victoria ML", f"{_client_tag(result)} | {visible_label(MODEL_CLASSIFICATION_PERIOD)}")
        generated.append(_save_close(fig, out_dir / f"{idx:02d}_{col.lower()}_win_rate.png"))
    return generated


# --------------------------------------------------------------------------
# impact_and_risk/
# --------------------------------------------------------------------------

def _bar_top_ranking(table: pd.DataFrame, value_col: str, title: str, subtitle: str, color: str, out_path: Path) -> str | None:
    if table.empty:
        return None
    labels = table["ID_CONFIGURATION"].astype(str).tolist()[:15]
    values = table[value_col].tolist()[:15]
    fig, ax = _new_fig((8.5, 5))
    bars = ax.barh(labels, values, color=color)
    ax.invert_yaxis()
    for bar, val in zip(bars, values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {val:,.1f}".replace(",", "."),
                 va="center", fontsize=7.5, color=COLOR_TEXT)
    ax.set_ylabel("ID_CONFIGURATION", color=COLOR_TEXT_SECONDARY, fontsize=9)
    _apply_title(ax, title, subtitle)
    return _save_close(fig, out_path)


def generate_impact_and_risk_charts(result: ClientAnalysisResult, out_dir: Path) -> list[str]:
    df = result.source.dataframe
    pr = result.periods.get(MODEL_CLASSIFICATION_PERIOD)
    if df is None or pr is None or pr.comparable_mask is None or pr.n_comparable == 0:
        return []
    pcols = period_columns(MODEL_CLASSIFICATION_PERIOD)
    generated = []
    sub_tag = f"{_client_tag(result)} | {visible_label(MODEL_CLASSIFICATION_PERIOD)}"

    top_reduction, top_increase = top_absolute_impact(df, pcols, pr.comparable_mask, n=15)
    path = _bar_top_ranking(top_reduction, "ABS_ERROR_REDUCTION", "Top reducciones absolutas de error", sub_tag, COLOR_ML, out_dir / "01_top_absolute_reductions.png")
    if path:
        generated.append(path)
    path = _bar_top_ranking(top_increase, "ABS_ERROR_REDUCTION", "Top aumentos absolutos de error", sub_tag, COLOR_SCP, out_dir / "02_top_absolute_increases.png")
    if path:
        generated.append(path)

    top_improve, top_worsen = top_percentage_changes(df, pcols, pr.comparable_mask, n=15)
    path = _bar_top_ranking(top_improve, "ML_IMPROVEMENT_VS_SCP_PCT", "Top mejoras porcentuales", sub_tag, COLOR_ML, out_dir / "03_top_percentage_improvements.png")
    if path:
        generated.append(path)
    path = _bar_top_ranking(top_worsen, "ML_IMPROVEMENT_VS_SCP_PCT", "Top deterioros porcentuales", sub_tag, COLOR_SCP, out_dir / "04_top_percentage_worsenings.png")
    if path:
        generated.append(path)

    return generated


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

CHART_SUBFOLDERS = ("coverage", "semester", "quarters", "monthly", "models", "classifications", "impact_and_risk")


def generate_client_charts(result: ClientAnalysisResult, charts_dir: Path) -> list[str]:
    """
    Genera todos los graficos individuales del cliente en sus 7 subcarpetas.
    Devuelve la lista de rutas generadas (para el log de procesamiento).
    Cierra siempre todas las figuras; nunca deja graficos abiertos en memoria.
    """
    generated: list[str] = []
    try:
        generated += generate_coverage_charts(result, charts_dir / "coverage")
        generated += generate_semester_charts(result, charts_dir / "semester")
        generated += generate_quarters_charts(result, charts_dir / "quarters")
        generated += generate_monthly_charts(result, charts_dir / "monthly")
        generated += generate_models_charts(result, charts_dir / "models")
        generated += generate_classifications_charts(result, charts_dir / "classifications")
        generated += generate_impact_and_risk_charts(result, charts_dir / "impact_and_risk")
    finally:
        plt.close("all")
    return generated
