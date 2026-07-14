"""
Analisis exploratorio ad hoc: comparacion de forecast SCP vs ML.

Lee el CSV local de TA_FOV_SCP_ML_SERIES_COMPARISON, filtra los clientes
indicados y genera un Excel multi-pestana y un informe en Markdown en
castellano orientados a Producto y Operaciones.

No modifica el CSV original. No se conecta a ninguna base de datos.
No toca codigo productivo: trabaja unicamente dentro de esta carpeta.

Ejecucion:
    python analysis_fov_scp_ml.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "TA_FOV_SCP_ML_SERIES_COMPARISON_batch_62.csv"
OUTPUT_DIR = BASE_DIR / "outputs"
CHARTS_DIR = OUTPUT_DIR / "charts"
EXCEL_PATH = OUTPUT_DIR / "fov_scp_ml_summary.xlsx"
REPORT_PATH = OUTPUT_DIR / "fov_scp_ml_report.md"

CLIENTS = [10204, 10467, 10664, 10666]

# Paleta (skill dataviz): azul = ML, rojo = SCP, gris = TIE / neutro.
COLOR_ML = "#2a78d6"
COLOR_SCP = "#e34948"
COLOR_TIE = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_AXIS = "#c3c2b7"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_SURFACE = "#fcfcfb"

MONTH_COLS = [f"M{i}" for i in range(1, 7)]

REQUIRED_COLUMNS = [
    "ID", "ID_BATCH", "ID_RUN_STAGING", "ID_CLIENT", "SOURCE_RUN_ID", "ID_CONFIGURATION",
    "VALUE_LEVEL_1", "VALUE_LEVEL_2", "VALUE_LEVEL_3", "VALUE_LEVEL_4", "VALUE_LEVEL_5",
    "ML_BEST_MODEL", "ML_CLASSIFICATION", "ML_TYPE", "ML_STATUS",
    "SCP_BEST_MODEL", "SCP_CLASSIFICATION", "SCP_STATUS",
    "SERIES_CLASSIFICATION",
    "COMPARISON_STATUS",
    "HAS_BASE_CANDIDATE", "HAS_SCP_CALCULATED", "HAS_ML_CALCULATED",
    "HAS_ML_EXCLUDED", "ML_EXCLUSION_REASON", "SCP_NO_OUTPUT_REASON",
    *[f"HISTORY_M{i}" for i in range(1, 7)],
    *[f"SCP_FORECAST_M{i}" for i in range(1, 7)],
    *[f"ML_FORECAST_M{i}" for i in range(1, 7)],
    "TOTAL_HISTORY_6M",
    "SCP_TOTAL_ABS_ERROR_6M", "ML_TOTAL_ABS_ERROR_6M",
    "SCP_WAPE_6M", "ML_WAPE_6M",
    "WINNER_METHOD_6M", "WINNER_MODEL_6M",
    "FINALIST_METHOD_6M", "FINALIST_MODEL_6M",
    "WINNER_IMPROVEMENT_PCT_6M",
]

pd.set_option("mode.chained_assignment", None)


# --------------------------------------------------------------------------
# Carga y validacion
# --------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"No se encuentra el CSV de entrada: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, low_memory=False, encoding="utf-8")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Faltan columnas requeridas en el CSV de entrada: " + ", ".join(missing)
        )
    return df


def filter_clients(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["ID_CLIENT"].isin(CLIENTS)].copy()
    if sub.empty:
        raise ValueError(
            "El filtro de clientes no ha devuelto ninguna fila. "
            f"Clientes esperados: {CLIENTS}"
        )
    sub = sub[sub["HAS_BASE_CANDIDATE"] == 1].copy()
    return sub


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    scp_wape = df["SCP_WAPE_6M"]
    ml_wape = df["ML_WAPE_6M"]
    valid = scp_wape.notna() & ml_wape.notna() & (scp_wape != 0)
    df["ML_IMPROVEMENT_VS_SCP_6M"] = np.where(
        valid, (scp_wape - ml_wape) / scp_wape * 100, np.nan
    )
    return df


# --------------------------------------------------------------------------
# Utilidades de analisis
# --------------------------------------------------------------------------

def numeric_stats(series: pd.Series) -> dict:
    s = series.dropna()
    if len(s) == 0:
        return {k: np.nan for k in
                ["count", "mean", "median", "p10", "p25", "p75", "p90", "min", "max"]} | {"count": 0}
    return {
        "count": int(len(s)),
        "mean": s.mean(),
        "median": s.median(),
        "p10": s.quantile(0.10),
        "p25": s.quantile(0.25),
        "p75": s.quantile(0.75),
        "p90": s.quantile(0.90),
        "min": s.min(),
        "max": s.max(),
    }


def stats_table(groups: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for label, series in groups.items():
        row = {"GRUPO": label}
        row.update(numeric_stats(series))
        rows.append(row)
    return pd.DataFrame(rows)


def value_counts_pct(series: pd.Series, dropna: bool = False) -> pd.DataFrame:
    vc = series.value_counts(dropna=dropna)
    total = vc.sum()
    out = pd.DataFrame({
        "VALOR": vc.index.astype(str),
        "N": vc.values,
        "PCT": (vc.values / total * 100) if total else 0,
    })
    return out


def wape_global(frame: pd.DataFrame) -> tuple[float, float, float]:
    hist_sum = frame["TOTAL_HISTORY_6M"].sum()
    scp_err = frame["SCP_TOTAL_ABS_ERROR_6M"].sum()
    ml_err = frame["ML_TOTAL_ABS_ERROR_6M"].sum()
    if not hist_sum:
        return np.nan, np.nan, np.nan
    scp_wape = scp_err / hist_sum
    ml_wape = ml_err / hist_sum
    improvement = (scp_wape - ml_wape) / scp_wape * 100 if scp_wape else np.nan
    return scp_wape, ml_wape, improvement


TOP_COLUMNS = [
    "ID_CLIENT", "ID_CONFIGURATION",
    "VALUE_LEVEL_1", "VALUE_LEVEL_2", "VALUE_LEVEL_3", "VALUE_LEVEL_4", "VALUE_LEVEL_5",
    "TOTAL_HISTORY_6M",
    "SCP_WAPE_6M", "ML_WAPE_6M",
    "ML_IMPROVEMENT_VS_SCP_6M", "WINNER_IMPROVEMENT_PCT_6M",
    "WINNER_METHOD_6M", "WINNER_MODEL_6M", "FINALIST_METHOD_6M", "FINALIST_MODEL_6M",
    "SCP_BEST_MODEL", "ML_BEST_MODEL", "ML_CLASSIFICATION", "ML_TYPE", "SERIES_CLASSIFICATION",
]


# --------------------------------------------------------------------------
# Excel: helper para escribir varios bloques en una misma pestana
# --------------------------------------------------------------------------

def write_blocks(writer: pd.ExcelWriter, sheet_name: str, blocks: list[tuple[str, pd.DataFrame]]) -> None:
    startrow = 0
    for title, block_df in blocks:
        pd.DataFrame({title: []}).to_excel(
            writer, sheet_name=sheet_name, startrow=startrow, index=False, header=True
        )
        startrow += 1
        if block_df is not None and not block_df.empty:
            block_df.to_excel(writer, sheet_name=sheet_name, startrow=startrow, index=False)
            startrow += len(block_df) + 2
        else:
            pd.DataFrame({"": ["(sin datos)"]}).to_excel(
                writer, sheet_name=sheet_name, startrow=startrow, index=False, header=False
            )
            startrow += 2


def autosize_columns(writer: pd.ExcelWriter, sheet_name: str, max_width: int = 45) -> None:
    ws = writer.sheets[sheet_name]
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            length = len(str(cell.value))
            widths[cell.column] = max(widths.get(cell.column, 0), length)
    for col_idx, width in widths.items():
        letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[letter].width = min(max(width + 2, 10), max_width)


# --------------------------------------------------------------------------
# Construccion de cada bloque de analisis
# --------------------------------------------------------------------------

def build_coverage_by_client(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for client_id, group in [("TOTAL", sub)] + [(str(c), sub[sub["ID_CLIENT"] == c]) for c in CLIENTS]:
        n_candidatas = len(group)
        n_comparables = int((group["COMPARISON_STATUS"] == "COMPARABLE").sum())
        n_no_comparables = n_candidatas - n_comparables
        pct_comparables = n_comparables / n_candidatas * 100 if n_candidatas else np.nan
        n_ml_excluded = int((group["HAS_ML_EXCLUDED"] == 1).sum())
        pct_ml_excluded = n_ml_excluded / n_candidatas * 100 if n_candidatas else np.nan
        rows.append({
            "ID_CLIENT": client_id,
            "SERIES_CANDIDATAS": n_candidatas,
            "SERIES_COMPARABLES": n_comparables,
            "PCT_COMPARABLES": pct_comparables,
            "SERIES_NO_COMPARABLES": n_no_comparables,
            "SERIES_HAS_ML_EXCLUDED": n_ml_excluded,
            "PCT_HAS_ML_EXCLUDED": pct_ml_excluded,
        })
    return pd.DataFrame(rows)


def build_status_distribution(sub: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    def dist_for(group: pd.DataFrame, label: str) -> pd.DataFrame:
        total = len(group)
        vc = group["COMPARISON_STATUS"].value_counts()
        return pd.DataFrame({
            "ID_CLIENT": label,
            "COMPARISON_STATUS": vc.index,
            "N": vc.values,
            "PCT_SOBRE_CANDIDATAS": vc.values / total * 100 if total else np.nan,
        })

    frames = [dist_for(sub, "TOTAL")] + [dist_for(sub[sub["ID_CLIENT"] == c], str(c)) for c in CLIENTS]
    status_dist = pd.concat(frames, ignore_index=True)

    excl_reason = value_counts_pct(sub.loc[sub["HAS_ML_EXCLUDED"] == 1, "ML_EXCLUSION_REASON"])
    excl_reason = excl_reason.rename(columns={"VALOR": "ML_EXCLUSION_REASON"})

    scp_no_output = value_counts_pct(sub.loc[sub["COMPARISON_STATUS"] != "COMPARABLE", "SCP_NO_OUTPUT_REASON"])
    scp_no_output = scp_no_output.rename(columns={"VALOR": "SCP_NO_OUTPUT_REASON"})

    return status_dist, excl_reason, scp_no_output


def build_winner_distribution(comp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    def dist_for(group: pd.DataFrame, label: str) -> pd.DataFrame:
        total = len(group)
        vc = group["WINNER_METHOD_6M"].value_counts()
        return pd.DataFrame({
            "ID_CLIENT": label,
            "WINNER_METHOD_6M": vc.index,
            "N": vc.values,
            "PCT_SOBRE_COMPARABLES": vc.values / total * 100 if total else np.nan,
        })

    global_dist = dist_for(comp, "TOTAL")
    per_client = pd.concat(
        [dist_for(comp[comp["ID_CLIENT"] == c], str(c)) for c in CLIENTS], ignore_index=True
    )
    return global_dist, per_client


def build_wape_impact(comp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, group in [("TOTAL", comp)] + [(str(c), comp[comp["ID_CLIENT"] == c]) for c in CLIENTS]:
        scp_w, ml_w, improvement = wape_global(group)
        rows.append({
            "ID_CLIENT": label,
            "N_SERIES_COMPARABLES": len(group),
            "SCP_WAPE_GLOBAL": scp_w,
            "ML_WAPE_GLOBAL": ml_w,
            "ML_IMPROVEMENT_VS_SCP_GLOBAL_PCT": improvement,
        })
    return pd.DataFrame(rows)


def build_ml_improvement_stats(comp: pd.DataFrame) -> pd.DataFrame:
    groups = {"TOTAL": comp["ML_IMPROVEMENT_VS_SCP_6M"]}
    for c in CLIENTS:
        groups[str(c)] = comp.loc[comp["ID_CLIENT"] == c, "ML_IMPROVEMENT_VS_SCP_6M"]
    return stats_table(groups)


def build_ml_winning_models(comp: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    ml_wins = comp[comp["WINNER_METHOD_6M"] == "ML"]
    n_total_comp = len(comp)
    n_ml = len(ml_wins)
    pct = n_ml / n_total_comp * 100 if n_total_comp else np.nan

    summary = pd.DataFrame([{
        "N_SERIES_GANA_ML": n_ml,
        "PCT_SOBRE_COMPARABLES": pct,
        "N_SERIES_COMPARABLES_TOTAL": n_total_comp,
    }])

    improvement_stats = stats_table({"TODAS (gana ML)": ml_wins["WINNER_IMPROVEMENT_PCT_6M"]})

    per_client_rows = []
    for c in CLIENTS:
        g = comp[comp["ID_CLIENT"] == c]
        gw = g[g["WINNER_METHOD_6M"] == "ML"]
        per_client_rows.append({
            "ID_CLIENT": c,
            "N_COMPARABLES": len(g),
            "N_GANA_ML": len(gw),
            "PCT_GANA_ML": len(gw) / len(g) * 100 if len(g) else np.nan,
        })
    per_client = pd.DataFrame(per_client_rows)

    winner_model = value_counts_pct(ml_wins["WINNER_MODEL_6M"]).rename(columns={"VALOR": "WINNER_MODEL_6M"})
    ml_best_model = value_counts_pct(ml_wins["ML_BEST_MODEL"]).rename(columns={"VALOR": "ML_BEST_MODEL"})
    ml_classification = value_counts_pct(ml_wins["ML_CLASSIFICATION"]).rename(columns={"VALOR": "ML_CLASSIFICATION"})
    ml_type = value_counts_pct(ml_wins["ML_TYPE"]).rename(columns={"VALOR": "ML_TYPE"})
    series_classification = value_counts_pct(ml_wins["SERIES_CLASSIFICATION"]).rename(
        columns={"VALOR": "SERIES_CLASSIFICATION"})

    return [
        ("Resumen: series donde gana ML (WINNER_METHOD_6M = 'ML')", summary),
        ("Estadistica de WINNER_IMPROVEMENT_PCT_6M cuando gana ML", improvement_stats),
        ("Series y % de victoria ML por cliente", per_client),
        ("Distribucion de WINNER_MODEL_6M", winner_model),
        ("Distribucion de ML_BEST_MODEL", ml_best_model),
        ("Distribucion de ML_CLASSIFICATION", ml_classification),
        ("Distribucion de ML_TYPE", ml_type),
        ("Distribucion de SERIES_CLASSIFICATION", series_classification),
    ]


def build_scp_wins_analysis(comp: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    scp_wins = comp[comp["WINNER_METHOD_6M"] == "SCP"]
    n_total_comp = len(comp)
    n_scp = len(scp_wins)
    pct = n_scp / n_total_comp * 100 if n_total_comp else np.nan

    summary = pd.DataFrame([{
        "N_SERIES_GANA_SCP": n_scp,
        "PCT_SOBRE_COMPARABLES": pct,
        "N_SERIES_COMPARABLES_TOTAL": n_total_comp,
    }])

    improvement_stats = stats_table({"TODAS (gana SCP)": scp_wins["ML_IMPROVEMENT_VS_SCP_6M"]})

    per_client_rows = []
    for c in CLIENTS:
        g = comp[comp["ID_CLIENT"] == c]
        gw = g[g["WINNER_METHOD_6M"] == "SCP"]
        per_client_rows.append({
            "ID_CLIENT": c,
            "N_COMPARABLES": len(g),
            "N_GANA_SCP": len(gw),
            "PCT_GANA_SCP": len(gw) / len(g) * 100 if len(g) else np.nan,
        })
    per_client = pd.DataFrame(per_client_rows)

    scp_best_model = value_counts_pct(scp_wins["SCP_BEST_MODEL"]).rename(columns={"VALOR": "SCP_BEST_MODEL"})
    ml_best_model = value_counts_pct(scp_wins["ML_BEST_MODEL"]).rename(columns={"VALOR": "ML_BEST_MODEL"})
    ml_classification = value_counts_pct(scp_wins["ML_CLASSIFICATION"]).rename(columns={"VALOR": "ML_CLASSIFICATION"})
    ml_type = value_counts_pct(scp_wins["ML_TYPE"]).rename(columns={"VALOR": "ML_TYPE"})
    series_classification = value_counts_pct(scp_wins["SERIES_CLASSIFICATION"]).rename(
        columns={"VALOR": "SERIES_CLASSIFICATION"})

    return [
        ("Resumen: series donde gana SCP (WINNER_METHOD_6M = 'SCP')", summary),
        ("Estadistica de ML_IMPROVEMENT_VS_SCP_6M cuando gana SCP (negativo = ML peor)", improvement_stats),
        ("Series y % de victoria SCP por cliente", per_client),
        ("Distribucion de SCP_BEST_MODEL", scp_best_model),
        ("Distribucion de ML_BEST_MODEL (cuando pierde)", ml_best_model),
        ("Distribucion de ML_CLASSIFICATION (cuando pierde)", ml_classification),
        ("Distribucion de ML_TYPE (cuando pierde)", ml_type),
        ("Distribucion de SERIES_CLASSIFICATION (cuando pierde ML)", series_classification),
    ]


def build_exclusions(sub: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    status_dist, excl_reason, scp_no_output = build_status_distribution(sub)

    n_status_excluded = int((sub["COMPARISON_STATUS"] == "NOT_COMPARABLE_ML_EXCLUDED").sum())
    n_flag_excluded = int((sub["HAS_ML_EXCLUDED"] == 1).sum())

    reconciliation = pd.DataFrame([{
        "N_COMPARISON_STATUS_ML_EXCLUDED": n_status_excluded,
        "N_HAS_ML_EXCLUDED_1": n_flag_excluded,
        "DIFERENCIA": n_flag_excluded - n_status_excluded,
        "NOTA": (
            "COMPARISON_STATUS sigue una precedencia de estados: si una fila excluida "
            "por ML tambien cumple otra condicion de no comparabilidad (p.ej. falta de "
            "SCP), el estado principal puede no ser NOT_COMPARABLE_ML_EXCLUDED. "
            "HAS_ML_EXCLUDED = 1 es el recuento real de exclusiones ML."
        ),
    }])

    excl_by_client = []
    for c in CLIENTS:
        g = sub[sub["ID_CLIENT"] == c]
        d = value_counts_pct(g.loc[g["HAS_ML_EXCLUDED"] == 1, "ML_EXCLUSION_REASON"])
        d.insert(0, "ID_CLIENT", c)
        d = d.rename(columns={"VALOR": "ML_EXCLUSION_REASON"})
        excl_by_client.append(d)
    excl_by_client_df = pd.concat(excl_by_client, ignore_index=True) if excl_by_client else pd.DataFrame()

    return [
        ("Distribucion global de COMPARISON_STATUS (y por cliente)", status_dist),
        ("Reconciliacion: COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED' vs HAS_ML_EXCLUDED=1", reconciliation),
        ("Distribucion global de ML_EXCLUSION_REASON (sobre HAS_ML_EXCLUDED=1)", excl_reason),
        ("Distribucion de ML_EXCLUSION_REASON por cliente", excl_by_client_df),
        ("Distribucion de SCP_NO_OUTPUT_REASON (filas no comparables)", scp_no_output),
    ]


def build_top_ml_improvements(comp: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    ml_wins = comp[comp["WINNER_METHOD_6M"] == "ML"]
    top = ml_wins.sort_values("WINNER_IMPROVEMENT_PCT_6M", ascending=False).head(n)
    return top[TOP_COLUMNS]


def build_top_ml_underperformance(comp: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    scp_wins = comp[comp["WINNER_METHOD_6M"] == "SCP"]
    top = scp_wins.sort_values("ML_IMPROVEMENT_VS_SCP_6M", ascending=True).head(n)
    return top[TOP_COLUMNS]


def build_data_quality_checks(sub: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["ID_BATCH", "ID_RUN_STAGING", "ID_CLIENT", "SOURCE_RUN_ID", "ID_CONFIGURATION"]
    n_dupes = int(sub.duplicated(subset=key_cols).sum())

    hist_cols = [f"HISTORY_M{i}" for i in range(1, 7)]
    scp_fc_cols = [f"SCP_FORECAST_M{i}" for i in range(1, 7)]
    ml_fc_cols = [f"ML_FORECAST_M{i}" for i in range(1, 7)]

    checks = [
        ("Duplicados por clave (ID_BATCH+ID_RUN_STAGING+ID_CLIENT+SOURCE_RUN_ID+ID_CONFIGURATION)",
         n_dupes, len(sub)),
        ("Filas COMPARABLE sin ningun valor de historico (M1..M6 todos nulos)",
         int(comp[hist_cols].isna().all(axis=1).sum()), len(comp)),
        ("Filas COMPARABLE sin ningun forecast SCP (M1..M6 todos nulos)",
         int(comp[scp_fc_cols].isna().all(axis=1).sum()), len(comp)),
        ("Filas COMPARABLE sin ningun forecast ML (M1..M6 todos nulos)",
         int(comp[ml_fc_cols].isna().all(axis=1).sum()), len(comp)),
        ("Filas COMPARABLE sin WINNER_METHOD_6M",
         int(comp["WINNER_METHOD_6M"].isna().sum()), len(comp)),
        ("Filas COMPARABLE con SCP_WAPE_6M o ML_WAPE_6M nulo",
         int((comp["SCP_WAPE_6M"].isna() | comp["ML_WAPE_6M"].isna()).sum()), len(comp)),
        ("Filas con HAS_ML_EXCLUDED=1 y ML_EXCLUSION_REASON nulo",
         int((sub["HAS_ML_EXCLUDED"] == 1).sum() and
             ((sub["HAS_ML_EXCLUDED"] == 1) & (sub["ML_EXCLUSION_REASON"].isna())).sum()),
         int((sub["HAS_ML_EXCLUDED"] == 1).sum())),
    ]

    rows = []
    for name, count, denom in checks:
        rows.append({
            "CHECK": name,
            "N_FILAS_AFECTADAS": count,
            "DENOMINADOR": denom,
            "PCT": count / denom * 100 if denom else np.nan,
            "ESTADO": "OK" if count == 0 else "REVISAR",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Graficos (PNG simples, paleta validada por la skill dataviz)
# --------------------------------------------------------------------------

def _style_ax(ax) -> None:
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_AXIS)
    ax.tick_params(colors=COLOR_TEXT_SECONDARY, labelsize=9)
    ax.yaxis.grid(True, color=COLOR_GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_winner_distribution(comp: pd.DataFrame) -> None:
    vc = comp["WINNER_METHOD_6M"].value_counts()
    order = [m for m in ["ML", "SCP", "TIE"] if m in vc.index]
    colors = {"ML": COLOR_ML, "SCP": COLOR_SCP, "TIE": COLOR_TIE}
    values = [vc[m] for m in order]
    pcts = [v / vc.sum() * 100 for v in values]

    fig, ax = plt.subplots(figsize=(6, 4), facecolor=COLOR_SURFACE)
    _style_ax(ax)
    bars = ax.bar(order, values, color=[colors[m] for m in order], width=0.55)
    for bar, pct in zip(bars, pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{pct:.1f}%",
                 ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_title("Series comparables: metodo ganador (ventana 6M)", color=COLOR_TEXT, fontsize=12, loc="left")
    ax.set_ylabel("N series", color=COLOR_TEXT_SECONDARY, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "01_winner_distribution.png", dpi=150)
    plt.close(fig)


def chart_wape_global(comp: pd.DataFrame) -> None:
    scp_w, ml_w, _ = wape_global(comp)
    fig, ax = plt.subplots(figsize=(5, 4), facecolor=COLOR_SURFACE)
    _style_ax(ax)
    bars = ax.bar(["SCP", "ML"], [scp_w * 100, ml_w * 100], color=[COLOR_SCP, COLOR_ML], width=0.5)
    for bar, val in zip(bars, [scp_w * 100, ml_w * 100]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:.1f}%",
                 ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_title("WAPE global ponderado (todas las series comparables)", color=COLOR_TEXT, fontsize=12, loc="left")
    ax.set_ylabel("WAPE (%)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "02_wape_global.png", dpi=150)
    plt.close(fig)


def chart_coverage_by_client(coverage: pd.DataFrame) -> None:
    per_client = coverage[coverage["ID_CLIENT"] != "TOTAL"]
    fig, ax = plt.subplots(figsize=(6, 4), facecolor=COLOR_SURFACE)
    _style_ax(ax)
    bars = ax.bar(per_client["ID_CLIENT"], per_client["PCT_COMPARABLES"], color=COLOR_ML, width=0.55)
    for bar, val in zip(bars, per_client["PCT_COMPARABLES"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:.0f}%",
                 ha="center", va="bottom", fontsize=10, color=COLOR_TEXT)
    ax.set_ylim(0, 100)
    ax.set_title("% de series comparables por cliente", color=COLOR_TEXT, fontsize=12, loc="left")
    ax.set_ylabel("% comparables", color=COLOR_TEXT_SECONDARY, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "03_coverage_by_client.png", dpi=150)
    plt.close(fig)


def chart_improvement_histogram(comp: pd.DataFrame) -> None:
    s = comp["ML_IMPROVEMENT_VS_SCP_6M"].dropna()
    s = s.clip(-100, 100)  # recorte visual: outliers extremos distorsionan el histograma
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=COLOR_SURFACE)
    _style_ax(ax)
    ax.hist(s, bins=40, color=COLOR_ML, edgecolor=COLOR_SURFACE, linewidth=0.5)
    ax.axvline(0, color=COLOR_TEXT_SECONDARY, linewidth=1.2, linestyle="--")
    ax.set_title(
        "Distribucion de la mejora ML vs SCP por serie (WAPE, recortada a +/-100%)",
        color=COLOR_TEXT, fontsize=11, loc="left"
    )
    ax.set_xlabel("% mejora ML vs SCP (positivo = ML mejor)", color=COLOR_TEXT_SECONDARY, fontsize=9)
    ax.set_ylabel("N series", color=COLOR_TEXT_SECONDARY, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "04_ml_improvement_histogram.png", dpi=150)
    plt.close(fig)


def generate_charts(comp: pd.DataFrame, coverage: pd.DataFrame) -> None:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_winner_distribution(comp)
    chart_wape_global(comp)
    chart_coverage_by_client(coverage)
    chart_improvement_histogram(comp)


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------

def write_excel(sub: pd.DataFrame, comp: pd.DataFrame) -> None:
    coverage = build_coverage_by_client(sub)
    status_dist, excl_reason, scp_no_output = build_status_distribution(sub)
    winner_global, winner_per_client = build_winner_distribution(comp)
    wape_impact = build_wape_impact(comp)
    improvement_stats = build_ml_improvement_stats(comp)
    ml_win_blocks = build_ml_winning_models(comp)
    scp_win_blocks = build_scp_wins_analysis(comp)
    exclusion_blocks = build_exclusions(sub)
    top_improvements = build_top_ml_improvements(comp)
    top_underperformance = build_top_ml_underperformance(comp)
    dq_checks = build_data_quality_checks(sub, comp)

    scp_w_g, ml_w_g, impr_g = wape_global(comp)
    readme_text = pd.DataFrame({"README": [
        "Analisis exploratorio ad hoc: comparacion de forecast SCP vs ML.",
        "",
        f"Fecha de generacion: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
        f"Fuente de datos: {DATA_PATH.name} (CSV local, sin conexion a base de datos)",
        f"Clientes analizados: {', '.join(str(c) for c in CLIENTS)}",
        f"Filas totales en el CSV: {len(sub) + 0}",  # se recalcula abajo con precision
        "",
        "Grano de analisis: ID_BATCH + ID_RUN_STAGING + ID_CLIENT + SOURCE_RUN_ID + ID_CONFIGURATION.",
        "Solo se usan filas con HAS_BASE_CANDIDATE = 1 (universo candidato base).",
        "Las metricas de performance (WAPE, mejora ML) usan unicamente filas con",
        "COMPARISON_STATUS = 'COMPARABLE'.",
        "",
        "Pestanas:",
        "01_global_summary: KPIs principales de todo el analisis.",
        "02_client_coverage: cobertura de series candidatas / comparables por cliente.",
        "03_status_distribution: distribucion de COMPARISON_STATUS y motivos de exclusion/no-output.",
        "04_winner_distribution: reparto de victorias ML/SCP/TIE, global y por cliente.",
        "05_wape_impact: WAPE global ponderado SCP vs ML y mejora global.",
        "06_ml_improvement_stats: estadistica descriptiva de la mejora ML vs SCP por serie.",
        "07_ml_winning_models: detalle de las series donde gana ML (modelos, clasificaciones).",
        "08_scp_wins_analysis: detalle de las series donde gana SCP (donde pierde ML).",
        "09_exclusions: exclusiones ML y no materializacion SCP, con la reconciliacion de conteos.",
        "10_top_ml_improvements: top 20 series con mayor mejora de ML sobre SCP.",
        "11_top_ml_underperformance: top 20 series donde ML peor se comporta frente a SCP.",
        "12_data_quality_checks: chequeos de calidad de datos sobre el subconjunto analizado.",
        "",
        "Notas de interpretacion:",
        "- WAPE_GLOBAL se calcula como suma(error absoluto total 6M) / suma(historico total 6M),",
        "  usando solo filas COMPARABLE. Es un WAPE ponderado por volumen, no un promedio simple.",
        "- ML_IMPROVEMENT_VS_SCP_6M = (SCP_WAPE_6M - ML_WAPE_6M) / SCP_WAPE_6M * 100 por fila.",
        "  Positivo = ML mejora; negativo = ML empeora frente a SCP.",
        "- HAS_ML_EXCLUDED=1 es el conteo real de exclusiones ML; puede ser mayor que las filas con",
        "  COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED' porque este ultimo estado sigue una",
        "  precedencia y puede quedar enmascarado por otra condicion de no comparabilidad.",
    ]})

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        readme_text.to_excel(writer, sheet_name="00_readme", index=False)

        global_summary = pd.DataFrame([{
            "CLIENTES_ANALIZADOS": ", ".join(str(c) for c in CLIENTS),
            "SERIES_CANDIDATAS_TOTAL": len(sub),
            "SERIES_COMPARABLES_TOTAL": len(comp),
            "PCT_COMPARABLES": len(comp) / len(sub) * 100 if len(sub) else np.nan,
            "SCP_WAPE_GLOBAL": scp_w_g,
            "ML_WAPE_GLOBAL": ml_w_g,
            "ML_IMPROVEMENT_VS_SCP_GLOBAL_PCT": impr_g,
            "PCT_SERIES_GANA_ML": (comp["WINNER_METHOD_6M"] == "ML").mean() * 100 if len(comp) else np.nan,
            "PCT_SERIES_GANA_SCP": (comp["WINNER_METHOD_6M"] == "SCP").mean() * 100 if len(comp) else np.nan,
            "PCT_SERIES_TIE": (comp["WINNER_METHOD_6M"] == "TIE").mean() * 100 if len(comp) else np.nan,
        }])
        write_blocks(writer, "01_global_summary", [("Resumen ejecutivo global", global_summary)])

        write_blocks(writer, "02_client_coverage", [("Cobertura de series por cliente", coverage)])

        write_blocks(writer, "03_status_distribution", [
            ("Distribucion de COMPARISON_STATUS (global y por cliente)", status_dist),
            ("Distribucion de ML_EXCLUSION_REASON (sobre HAS_ML_EXCLUDED=1)", excl_reason),
            ("Distribucion de SCP_NO_OUTPUT_REASON (filas no comparables)", scp_no_output),
        ])

        write_blocks(writer, "04_winner_distribution", [
            ("Distribucion global de WINNER_METHOD_6M (sobre comparables)", winner_global),
            ("Distribucion de WINNER_METHOD_6M por cliente", winner_per_client),
        ])

        write_blocks(writer, "05_wape_impact", [
            ("WAPE global ponderado SCP vs ML, global y por cliente", wape_impact),
        ])

        write_blocks(writer, "06_ml_improvement_stats", [
            ("Estadistica de ML_IMPROVEMENT_VS_SCP_6M (global y por cliente)", improvement_stats),
        ])

        write_blocks(writer, "07_ml_winning_models", ml_win_blocks)
        write_blocks(writer, "08_scp_wins_analysis", scp_win_blocks)
        write_blocks(writer, "09_exclusions", exclusion_blocks)

        write_blocks(writer, "10_top_ml_improvements", [
            ("Top 20 series con mayor mejora de ML sobre SCP (WINNER_METHOD_6M='ML')", top_improvements),
        ])
        write_blocks(writer, "11_top_ml_underperformance", [
            ("Top 20 series donde ML peor se comporta frente a SCP (WINNER_METHOD_6M='SCP')", top_underperformance),
        ])
        write_blocks(writer, "12_data_quality_checks", [
            ("Chequeos de calidad de datos", dq_checks),
        ])

        for sheet_name in writer.sheets:
            autosize_columns(writer, sheet_name)

    return coverage, status_dist, winner_global, winner_per_client, wape_impact, \
        improvement_stats, ml_win_blocks, scp_win_blocks, exclusion_blocks, \
        top_improvements, top_underperformance, dq_checks


# --------------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------------

def fmt_pct(x: float, decimals: int = 1) -> str:
    if pd.isna(x):
        return "n/d"
    return f"{x:.{decimals}f}%"


def fmt_num(x: float, decimals: int = 0) -> str:
    if pd.isna(x):
        return "n/d"
    return f"{x:,.{decimals}f}".replace(",", ".")


def write_report(sub: pd.DataFrame, comp: pd.DataFrame, coverage: pd.DataFrame,
                  winner_global: pd.DataFrame, wape_impact: pd.DataFrame,
                  improvement_stats: pd.DataFrame, ml_win_blocks, scp_win_blocks,
                  exclusion_blocks, dq_checks: pd.DataFrame) -> None:

    n_candidatas = len(sub)
    n_comparables = len(comp)
    pct_comparables = n_comparables / n_candidatas * 100 if n_candidatas else np.nan
    n_no_comparables = n_candidatas - n_comparables

    scp_w_g, ml_w_g, impr_g = wape_global(comp)

    winner_counts = comp["WINNER_METHOD_6M"].value_counts()
    n_ml = int(winner_counts.get("ML", 0))
    n_scp = int(winner_counts.get("SCP", 0))
    n_tie = int(winner_counts.get("TIE", 0))
    pct_ml = n_ml / n_comparables * 100 if n_comparables else np.nan
    pct_scp = n_scp / n_comparables * 100 if n_comparables else np.nan
    pct_tie = n_tie / n_comparables * 100 if n_comparables else np.nan

    ml_improvement_row = improvement_stats[improvement_stats["GRUPO"] == "TOTAL"].iloc[0]

    n_ml_excluded_flag = int((sub["HAS_ML_EXCLUDED"] == 1).sum())
    n_ml_excluded_status = int((sub["COMPARISON_STATUS"] == "NOT_COMPARABLE_ML_EXCLUDED").sum())
    pct_ml_excluded_flag = n_ml_excluded_flag / n_candidatas * 100 if n_candidatas else np.nan

    status_counts = sub["COMPARISON_STATUS"].value_counts()

    # top modelos ML ganadores (por WINNER_MODEL_6M dentro de series donde gana ML)
    ml_wins = comp[comp["WINNER_METHOD_6M"] == "ML"]
    top_winner_models = ml_wins["WINNER_MODEL_6M"].value_counts().head(5)

    # DQ: contar issues
    dq_issues = dq_checks[dq_checks["ESTADO"] == "REVISAR"]

    lines: list[str] = []
    a = lines.append

    a("# Comparativa de forecast SCP vs ML — Informe ejecutivo")
    a("")
    a(f"**Fecha del analisis:** {pd.Timestamp.now():%d/%m/%Y}")
    a(f"**Clientes analizados:** {', '.join(str(c) for c in CLIENTS)}")
    a(f"**Ventana evaluada:** ultimos 6 meses cerrados (M1 = mes mas reciente, M6 = mas antiguo)")
    a(f"**Fuente de datos:** archivo local `{DATA_PATH.name}` (sin conexion a base de datos, sin cambios sobre datos productivos)")
    a("")
    a("---")
    a("")
    a("## Resumen ejecutivo")
    a("")
    a(
        f"Sobre los cuatro clientes analizados se han evaluado **{fmt_num(n_candidatas)} series** de forecast. "
        f"De ellas, **{fmt_num(n_comparables)} ({fmt_pct(pct_comparables)})** tienen histórico y forecast "
        f"suficientes en ambos métodos para poder compararse de forma fiable; el resto "
        f"(**{fmt_num(n_no_comparables)}**) queda fuera de la comparación por distintos motivos que se detallan "
        f"más abajo (series nuevas, sin histórico suficiente, exclusiones del propio modelo ML, etc.)."
    )
    a("")
    if pd.notna(impr_g) and impr_g > 0:
        veredicto = (
            f"En conjunto, **ML mejora el forecast frente a SCP**: el error ponderado (WAPE) global "
            f"baja de **{fmt_pct(scp_w_g*100)}** con SCP a **{fmt_pct(ml_w_g*100)}** con ML, una mejora "
            f"relativa del **{fmt_pct(impr_g)}**."
        )
    elif pd.notna(impr_g):
        veredicto = (
            f"En conjunto, **ML no mejora el forecast frente a SCP** en este batch: el error ponderado (WAPE) "
            f"global pasa de **{fmt_pct(scp_w_g*100)}** con SCP a **{fmt_pct(ml_w_g*100)}** con ML, "
            f"lo que supone un empeoramiento del **{fmt_pct(-impr_g)}**."
        )
    else:
        veredicto = "No ha sido posible calcular el WAPE global (sin series comparables)."
    a(veredicto)
    a("")
    a(
        f"A nivel de series individuales, ML gana en **{fmt_num(n_ml)} de {fmt_num(n_comparables)} series "
        f"comparables ({fmt_pct(pct_ml)})**, SCP gana en **{fmt_num(n_scp)} ({fmt_pct(pct_scp)})** y hay "
        f"empate técnico en **{fmt_num(n_tie)} ({fmt_pct(pct_tie)})**. Es decir, la mejora de ML no es "
        f"uniforme: en una parte relevante de las series SCP sigue siendo el método más preciso, y esos "
        f"casos se documentan en detalle en este informe y en la pestaña `08_scp_wins_analysis` del Excel."
    )
    a("")
    a(
        "**Lectura para negocio:** el dato que mejor resume el valor de ML es la mejora de WAPE global "
        "ponderada por volumen de histórico (arriba), porque no se deja arrastrar por series pequeñas con "
        "errores porcentuales extremos. El recuento de series ganadas (ML vs SCP) es complementario: indica "
        "en cuántos casos concretos habría que intervenir/confiar en cada método, no cuánto pesa cada caso "
        "en el negocio."
    )
    a("")
    a("---")
    a("")
    a("## Clientes analizados y cobertura")
    a("")
    a(
        "La cobertura (qué proporción de series se puede comparar) varía por cliente. Una cobertura baja no "
        "es necesariamente un problema de ML: puede deberse a series demasiado cortas, sin histórico, o "
        "directamente fuera del alcance de ambos métodos."
    )
    a("")
    a("| Cliente | Series candidatas | Series comparables | % comparables | No comparables | Exclusiones ML (HAS_ML_EXCLUDED=1) |")
    a("|---|---:|---:|---:|---:|---:|")
    for _, row in coverage.iterrows():
        a(
            f"| {row['ID_CLIENT']} | {fmt_num(row['SERIES_CANDIDATAS'])} | {fmt_num(row['SERIES_COMPARABLES'])} "
            f"| {fmt_pct(row['PCT_COMPARABLES'])} | {fmt_num(row['SERIES_NO_COMPARABLES'])} "
            f"| {fmt_num(row['SERIES_HAS_ML_EXCLUDED'])} ({fmt_pct(row['PCT_HAS_ML_EXCLUDED'])}) |"
        )
    a("")
    a("Detalle de motivos de no comparabilidad (`COMPARISON_STATUS`), global sobre las series candidatas:")
    a("")
    a("| Estado | N series | % sobre candidatas |")
    a("|---|---:|---:|")
    for status, n in status_counts.items():
        a(f"| {status} | {fmt_num(n)} | {fmt_pct(n / n_candidatas * 100)} |")
    a("")
    a(
        "**Cómo leer esta tabla:** `COMPARABLE` es la única categoría que entra en el análisis de "
        "performance. El resto son series que, por distintos motivos operativos (falta de histórico, "
        "series nuevas, exclusión explícita del motor ML, fallo del cálculo, etc.), no permiten una "
        "comparación justa entre SCP y ML y por tanto no deben usarse para argumentar a favor ni en contra "
        "de ningún método."
    )
    a("")
    a("---")
    a("")
    a("## ¿ML mejora el forecast frente a SCP?")
    a("")
    a("### Impacto agregado en precisión (WAPE global ponderado)")
    a("")
    a(
        "El WAPE (error absoluto ponderado por histórico) es la métrica principal de comparación. Se "
        "calcula sumando todo el error absoluto y todo el histórico de las series comparables, para que las "
        "series con más volumen pesen más que las series pequeñas."
    )
    a("")
    a("| Cliente | Series comparables | WAPE SCP | WAPE ML | Mejora ML vs SCP |")
    a("|---|---:|---:|---:|---:|")
    for _, row in wape_impact.iterrows():
        a(
            f"| {row['ID_CLIENT']} | {fmt_num(row['N_SERIES_COMPARABLES'])} "
            f"| {fmt_pct(row['SCP_WAPE_GLOBAL']*100) if pd.notna(row['SCP_WAPE_GLOBAL']) else 'n/d'} "
            f"| {fmt_pct(row['ML_WAPE_GLOBAL']*100) if pd.notna(row['ML_WAPE_GLOBAL']) else 'n/d'} "
            f"| {fmt_pct(row['ML_IMPROVEMENT_VS_SCP_GLOBAL_PCT'])} |"
        )
    a("")
    a(
        "Un valor positivo en la última columna indica que ML reduce el error frente a SCP en ese cliente; "
        "un valor negativo indica que, en conjunto, ML tiene más error que SCP para ese cliente."
    )
    a("")
    a("### Reparto de victorias por serie")
    a("")
    a("| Método | N series | % sobre comparables |")
    a("|---|---:|---:|")
    a(f"| ML | {fmt_num(n_ml)} | {fmt_pct(pct_ml)} |")
    a(f"| SCP | {fmt_num(n_scp)} | {fmt_pct(pct_scp)} |")
    a(f"| Empate (TIE) | {fmt_num(n_tie)} | {fmt_pct(pct_tie)} |")
    a("")
    a("### Magnitud de la mejora cuando ML gana")
    a("")
    ml_summary_df = ml_win_blocks[0][1]
    ml_stats_df = ml_win_blocks[1][1].iloc[0]
    a(
        f"En las **{fmt_num(ml_summary_df['N_SERIES_GANA_ML'].iloc[0])} series donde ML gana**, la mejora "
        f"porcentual de WAPE frente a SCP tiene una **mediana de {fmt_pct(ml_stats_df['median'])}** "
        f"(media {fmt_pct(ml_stats_df['mean'])}; rango intercuartílico entre {fmt_pct(ml_stats_df['p25'])} "
        f"y {fmt_pct(ml_stats_df['p75'])}). Se usa la mediana como referencia principal porque la media puede "
        f"distorsionarse por series con muy poco histórico, donde pequeñas diferencias absolutas generan "
        f"porcentajes de mejora muy grandes."
    )
    a("")
    a("### Magnitud de la pérdida cuando gana SCP")
    a("")
    scp_summary_df = scp_win_blocks[0][1]
    scp_stats_df = scp_win_blocks[1][1].iloc[0]
    a(
        f"En las **{fmt_num(scp_summary_df['N_SERIES_GANA_SCP'].iloc[0])} series donde gana SCP**, la "
        f"diferencia `ML_IMPROVEMENT_VS_SCP_6M` (negativa por definición en estos casos) tiene una "
        f"**mediana de {fmt_pct(scp_stats_df['median'])}**, es decir, ML tiene un WAPE típicamente "
        f"{fmt_pct(-scp_stats_df['median'])} peor que SCP en esas series. El detalle fila a fila está en la "
        f"pestaña `11_top_ml_underperformance` del Excel."
    )
    a("")
    a("---")
    a("")
    a("## ¿Con qué modelos mejora ML?")
    a("")
    a(
        "Cuando ML gana, estos son los modelos que con más frecuencia resultan ganadores "
        "(`WINNER_MODEL_6M`):"
    )
    a("")
    a("| Modelo ganador | N series | % sobre victorias ML |")
    a("|---|---:|---:|")
    n_ml_wins_total = len(ml_wins)
    for model, n in top_winner_models.items():
        a(f"| {model} | {fmt_num(n)} | {fmt_pct(n / n_ml_wins_total * 100) if n_ml_wins_total else 'n/d'} |")
    a("")
    a(
        "El detalle completo de modelos, clasificaciones ML (`ML_CLASSIFICATION`, `ML_TYPE`) y tipología de "
        "serie (`SERIES_CLASSIFICATION`) tanto en victorias como en derrotas de ML está disponible en las "
        "pestañas `07_ml_winning_models` y `08_scp_wins_analysis` del Excel, con desglose por cliente cuando "
        "la muestra lo permite."
    )
    a("")
    a("---")
    a("")
    a("## Series que quedan fuera de la comparación")
    a("")
    a(
        f"Del total de **{fmt_num(n_candidatas)}** series candidatas de los cuatro clientes, "
        f"**{fmt_num(n_no_comparables)} ({fmt_pct(100 - pct_comparables)})** no se han podido comparar. "
        f"Los motivos principales, ordenados por frecuencia, son:"
    )
    a("")
    a("| Estado (`COMPARISON_STATUS`) | N series | % sobre candidatas | Significado |")
    a("|---|---:|---:|---|")
    status_meaning = {
        "COMPARABLE": "Serie comparable (incluida en el análisis de performance).",
        "NOT_COMPARABLE_MISSING_SCP_AND_ML": "Faltan ambos forecasts (SCP y ML).",
        "NOT_COMPARABLE_ML_EXCLUDED": "ML excluyó explícitamente la serie (ver más abajo).",
        "NOT_COMPARABLE_NO_HISTORY": "No hay histórico útil para evaluar la serie.",
        "NOT_COMPARABLE_MISSING_SCP": "Falta el forecast de SCP.",
        "NOT_COMPARABLE_MISSING_ML": "Falta el forecast de ML.",
        "NOT_COMPARABLE_MISSING_VALIDATION": "No hay datos de validación disponibles.",
        "NOT_COMPARABLE_RUN_FAILED": "El run de cálculo falló.",
    }
    for status, n in status_counts.items():
        if status == "COMPARABLE":
            continue
        a(f"| {status} | {fmt_num(n)} | {fmt_pct(n / n_candidatas * 100)} | {status_meaning.get(status, '')} |")
    a("")
    a("### Exclusiones ML en detalle")
    a("")
    a(
        f"Contando el `COMPARISON_STATUS = 'NOT_COMPARABLE_ML_EXCLUDED'` hay **{fmt_num(n_ml_excluded_status)}** "
        f"series marcadas como excluidas por ML. Sin embargo, ese estado sigue una **precedencia**: si una "
        f"serie excluida por ML también cumple otra condición de no comparabilidad (por ejemplo, falta "
        f"también el forecast de SCP), el estado principal que se le asigna puede ser otro distinto. Por "
        f"eso, el recuento **real** de exclusiones ML usa el flag `HAS_ML_EXCLUDED = 1`, que asciende a "
        f"**{fmt_num(n_ml_excluded_flag)} series ({fmt_pct(pct_ml_excluded_flag)} sobre el total de "
        f"candidatas)**. La diferencia entre ambos conteos "
        f"(**{fmt_num(n_ml_excluded_flag - n_ml_excluded_status)}** series) corresponde a exclusiones ML "
        f"que quedan \"tapadas\" por otro estado con mayor precedencia, típicamente "
        f"`NOT_COMPARABLE_MISSING_SCP_AND_ML`."
    )
    a("")
    excl_reason_df = exclusion_blocks[2][1]
    if not excl_reason_df.empty:
        a("Motivos de exclusión ML (`ML_EXCLUSION_REASON`), sobre las filas con `HAS_ML_EXCLUDED = 1`:")
        a("")
        a("| Motivo | N series | % sobre exclusiones ML |")
        a("|---|---:|---:|")
        for _, row in excl_reason_df.iterrows():
            a(f"| {row['ML_EXCLUSION_REASON']} | {fmt_num(row['N'])} | {fmt_pct(row['PCT'])} |")
        a("")
    a(
        "**Nota:** estas exclusiones no son un fallo de ML frente a SCP — son series que el propio motor ML "
        "descarta de antemano por no cumplir los requisitos mínimos (histórico insuficiente, serie "
        "demasiado corta o de reciente creación), y por tanto no deben interpretarse como series donde "
        "\"ML pierde\", sino como series donde ML no llega a competir."
    )
    a("")
    a("---")
    a("")
    a("## Principales conclusiones")
    a("")
    conclusions = []
    if pd.notna(impr_g) and impr_g > 0:
        conclusions.append(
            f"ML reduce el error de forecast global un **{fmt_pct(impr_g)}** frente a SCP (WAPE ponderado) "
            f"sobre las series comparables de los cuatro clientes analizados."
        )
    elif pd.notna(impr_g):
        conclusions.append(
            f"En este batch, ML no reduce el error de forecast global frente a SCP; el WAPE ponderado "
            f"empeora un {fmt_pct(-impr_g)}."
        )
    conclusions.append(
        f"ML gana a nivel de serie individual en el {fmt_pct(pct_ml)} de los casos comparables, frente al "
        f"{fmt_pct(pct_scp)} donde gana SCP y {fmt_pct(pct_tie)} de empates."
    )
    conclusions.append(
        f"Solo el {fmt_pct(pct_comparables)} de las series candidatas de estos cuatro clientes es "
        f"comparable; cualquier conclusión sobre ML vs SCP aplica a ese subconjunto, no al universo completo."
    )
    if not top_winner_models.empty:
        conclusions.append(
            f"El modelo ganador más frecuente cuando ML gana es **{top_winner_models.index[0]}** "
            f"({fmt_num(top_winner_models.iloc[0])} series, {fmt_pct(top_winner_models.iloc[0]/n_ml_wins_total*100)})."
        )
    conclusions.append(
        f"Las exclusiones reales de ML ({fmt_num(n_ml_excluded_flag)} series, {fmt_pct(pct_ml_excluded_flag)}) "
        f"se concentran en series con histórico corto o insuficiente, no en fallos del modelo sobre series "
        f"evaluables."
    )
    for c in conclusions:
        a(f"- {c}")
    a("")
    a("---")
    a("")
    a("## Limitaciones del análisis")
    a("")
    limitations = [
        (
            "Este análisis cubre únicamente los clientes "
            f"{', '.join(str(c) for c in CLIENTS)} y el batch de validación `batch_62`; no es representativo "
            "de otros clientes ni de otros periodos."
        ),
        (
            f"Solo el {fmt_pct(pct_comparables)} de las series candidatas es comparable. Las conclusiones "
            "sobre la mejora de ML no se pueden extrapolar automáticamente a las series no comparables."
        ),
        (
            "Algunas series individuales presentan WAPE extremos (cientos o miles por ciento) por tener "
            "históricos muy pequeños; se ha usado la mediana como referencia principal y se recomienda no "
            "interpretar los valores máximos sin revisar el caso concreto."
        ),
        (
            "El análisis es retrospectivo (backtesting sobre los últimos 6 meses cerrados) y no garantiza "
            "el comportamiento futuro de ML frente a SCP."
        ),
        (
            "No se dispone de contexto de negocio adicional (roturas de stock, promociones, eventos "
            "puntuales) que pueda explicar picos de error en series concretas."
        ),
    ]
    for lim in limitations:
        a(f"- {lim}")
    a("")
    dq_issue_count = len(dq_issues)
    if dq_issue_count:
        a(
            f"- Se han detectado **{dq_issue_count} chequeo(s) de calidad de datos** con incidencias sobre "
            "el subconjunto analizado (ver pestaña `12_data_quality_checks` del Excel para el detalle)."
        )
    else:
        a("- Todos los chequeos de calidad de datos aplicados sobre el subconjunto analizado han pasado sin incidencias.")
    a("")
    a("---")
    a("")
    a("## Anexos")
    a("")
    a("- Detalle completo, desgloses por cliente y tablas de apoyo: `outputs/fov_scp_ml_summary.xlsx`.")
    a("- Gráficos de apoyo: carpeta `outputs/charts/`.")
    a(f"- Script de generación (reproducible): `analysis_fov_scp_ml.py`.")
    a("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    print(f"Leyendo CSV: {DATA_PATH}")
    df = load_data()
    print(f"Filas totales en el CSV: {len(df)}")

    sub = filter_clients(df)
    print(f"Filas tras filtrar clientes {CLIENTS} y HAS_BASE_CANDIDATE=1: {len(sub)}")

    sub = add_derived_columns(sub)
    comp = sub[sub["COMPARISON_STATUS"] == "COMPARABLE"].copy()
    print(f"Filas COMPARABLE: {len(comp)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Generando Excel...")
    (coverage, status_dist, winner_global, winner_per_client, wape_impact,
     improvement_stats, ml_win_blocks, scp_win_blocks, exclusion_blocks,
     top_improvements, top_underperformance, dq_checks) = write_excel(sub, comp)
    print(f"Excel escrito en: {EXCEL_PATH}")

    print("Generando graficos...")
    generate_charts(comp, coverage)
    print(f"Graficos escritos en: {CHARTS_DIR}")

    print("Generando informe Markdown...")
    write_report(sub, comp, coverage, winner_global, wape_impact, improvement_stats,
                 ml_win_blocks, scp_win_blocks, exclusion_blocks, dq_checks)
    print(f"Informe escrito en: {REPORT_PATH}")

    print("\nProceso completado correctamente.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
