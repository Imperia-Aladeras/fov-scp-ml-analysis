"""Phase 10B.3: model selection and performance conditioned on selection."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.global_analysis import analyze_global
from src.portfolio import (
    BLOCK_OLDER_3M,
    BLOCK_RECENT_3M,
    ENGINE_OPTIMIZER,
    ENGINE_SCP_AUTO,
    MODEL_TABLE_COLUMNS,
    build_portfolio_model_result,
)
from tests.factories import build_synthetic_client_dataframe
from tests.test_portfolio import _client_result, _portfolio_dataframe


def _event(
    *,
    engine: str,
    block: str,
    model_name: str | None,
    id_client: int,
    id_configuration: int,
    performance: bool,
    history: float | None,
    scp_abs_error: float | None,
    optimizer_abs_error: float | None,
    scp_signed_error: float | None,
    optimizer_signed_error: float | None,
    scp_wape: float | None,
    optimizer_wape: float | None,
    winner_method: str | None,
) -> dict:
    selection = model_name is not None
    return {
        "ID_CLIENT": id_client,
        "ID_CONFIGURATION": id_configuration,
        "engine": engine,
        "block": block,
        "model_name": model_name,
        "selection_evaluable": selection,
        "performance_evaluable": selection and performance,
        "total_history": history,
        "scp_total_abs_error": scp_abs_error,
        "optimizer_total_abs_error": optimizer_abs_error,
        "scp_total_signed_error": scp_signed_error,
        "optimizer_total_signed_error": optimizer_signed_error,
        "scp_wape": scp_wape,
        "optimizer_wape": optimizer_wape,
        "winner_method": winner_method,
    }


def _conditioned_events() -> pd.DataFrame:
    rows: list[dict] = []
    for engine, winners in (
        (ENGINE_SCP_AUTO, ("SCP", "TIE", "SCP", None, None)),
        (ENGINE_OPTIMIZER, ("ML", "TIE", "ML", None, None)),
    ):
        rows.extend([
            _event(
                engine=engine, block=BLOCK_OLDER_3M, model_name="ModelA",
                id_client=1, id_configuration=1, performance=True,
                history=100.0, scp_abs_error=20.0, optimizer_abs_error=10.0,
                scp_signed_error=20.0, optimizer_signed_error=10.0,
                scp_wape=0.2, optimizer_wape=0.1, winner_method=winners[0],
            ),
            _event(
                engine=engine, block=BLOCK_OLDER_3M, model_name="ModelA",
                id_client=2, id_configuration=2, performance=True,
                history=900.0, scp_abs_error=90.0, optimizer_abs_error=180.0,
                scp_signed_error=-90.0, optimizer_signed_error=180.0,
                scp_wape=0.1, optimizer_wape=0.2, winner_method=winners[1],
            ),
            _event(
                engine=engine, block=BLOCK_OLDER_3M, model_name="ModelB",
                id_client=1, id_configuration=3, performance=True,
                history=500.0, scp_abs_error=50.0, optimizer_abs_error=25.0,
                scp_signed_error=50.0, optimizer_signed_error=25.0,
                scp_wape=0.1, optimizer_wape=0.05, winner_method=winners[2],
            ),
            _event(
                engine=engine, block=BLOCK_OLDER_3M, model_name="ModelC",
                id_client=1, id_configuration=4, performance=False,
                history=None, scp_abs_error=None, optimizer_abs_error=None,
                scp_signed_error=None, optimizer_signed_error=None,
                scp_wape=None, optimizer_wape=None, winner_method=winners[3],
            ),
            _event(
                engine=engine, block=BLOCK_OLDER_3M, model_name=None,
                id_client=1, id_configuration=5, performance=False,
                history=None, scp_abs_error=None, optimizer_abs_error=None,
                scp_signed_error=None, optimizer_signed_error=None,
                scp_wape=None, optimizer_wape=None, winner_method=winners[4],
            ),
            _event(
                engine=engine, block=BLOCK_RECENT_3M, model_name="RecentOnly",
                id_client=1, id_configuration=6, performance=True,
                history=200.0, scp_abs_error=40.0, optimizer_abs_error=20.0,
                scp_signed_error=40.0, optimizer_signed_error=20.0,
                scp_wape=0.2, optimizer_wape=0.1,
                winner_method="SCP" if engine == ENGINE_SCP_AUTO else "ML",
            ),
        ])
    return pd.DataFrame(rows)


def _row(table: pd.DataFrame, engine: str, block: str, model_name: str) -> pd.Series:
    selected = table[
        (table["engine"] == engine)
        & (table["block"] == block)
        & (table["model_name"] == model_name)
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def test_selection_population_is_assignable_only_and_order_is_deterministic():
    table = build_portfolio_model_result(_conditioned_events()).by_engine_block_model

    assert tuple(table.columns) == MODEL_TABLE_COLUMNS
    assert table["model_name"].notna().all()
    assert list(table[["engine", "block", "model_name"]].itertuples(index=False, name=None)) == [
        (ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelA"),
        (ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelB"),
        (ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelC"),
        (ENGINE_SCP_AUTO, BLOCK_RECENT_3M, "RecentOnly"),
        (ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "ModelA"),
        (ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "ModelB"),
        (ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "ModelC"),
        (ENGINE_OPTIMIZER, BLOCK_RECENT_3M, "RecentOnly"),
    ]

    scp_a = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelA")
    scp_b = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelB")
    scp_c = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelC")
    assert scp_a["selection_count"] == 2
    assert scp_b["selection_count"] == 1
    assert scp_c["selection_count"] == 1
    assert scp_a["selection_assignable_count"] == 4
    assert scp_a["selection_share_of_assignable"] == 0.5
    assert scp_b["selection_share_of_assignable"] == 0.25
    assert scp_c["selection_share_of_assignable"] == 0.25

    shares = table.groupby(["engine", "block"], observed=True)["selection_share_of_assignable"].sum()
    assert shares.eq(1.0).all()
    assert scp_c["n_performance"] == 0
    assert scp_c["historical_volume"] == 0.0
    assert scp_c["volume_share"] == 0.0
    assert bool(scp_c["small_sample"]) is True
    assert math.isnan(scp_c["scp_wape"])


def test_conditioned_performance_uses_ratios_of_sums_and_performance_volume_denominator():
    table = build_portfolio_model_result(_conditioned_events()).by_engine_block_model
    scp_a = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelA")
    scp_b = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelB")

    assert scp_a["n_performance"] == 2
    assert scp_a["n_clients"] == 2
    assert scp_a["historical_volume"] == 1000.0
    assert scp_a["volume_share"] == pytest.approx(1000 / 1500)
    assert scp_b["volume_share"] == pytest.approx(500 / 1500)
    assert scp_a["volume_share"] + scp_b["volume_share"] == pytest.approx(1.0)
    volume_shares = table.groupby(["engine", "block"], observed=True)["volume_share"].sum()
    assert volume_shares.eq(1.0).all()

    assert scp_a["scp_wape"] == pytest.approx((20 + 90) / 1000)
    assert scp_a["optimizer_wape"] == pytest.approx((10 + 180) / 1000)
    assert scp_a["scp_wape"] != pytest.approx((0.2 + 0.1) / 2)
    assert scp_a["scp_bias"] == pytest.approx((20 - 90) / 1000)
    assert scp_a["optimizer_bias"] == pytest.approx((10 + 180) / 1000)
    assert scp_a["optimizer_improvement_vs_scp"] == pytest.approx((0.11 - 0.19) / 0.11 * 100)
    assert scp_a["optimizer_median_improvement_vs_scp"] == pytest.approx(-25.0)
    assert scp_a["optimizer_abs_error_reduction_vs_scp"] == -80.0


def test_winner_rate_is_symmetric_but_comparative_metric_direction_is_fixed():
    table = build_portfolio_model_result(_conditioned_events()).by_engine_block_model
    scp_a = _row(table, ENGINE_SCP_AUTO, BLOCK_OLDER_3M, "ModelA")
    optimizer_a = _row(table, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "ModelA")

    assert scp_a["selected_engine_win_count"] == 1
    assert optimizer_a["selected_engine_win_count"] == 1
    assert scp_a["tie_count"] == optimizer_a["tie_count"] == 1
    assert scp_a["selected_engine_win_rate"] == optimizer_a["selected_engine_win_rate"] == 0.5

    assert scp_a["optimizer_improvement_vs_scp"] == optimizer_a["optimizer_improvement_vs_scp"]
    assert (
        scp_a["optimizer_abs_error_reduction_vs_scp"]
        == optimizer_a["optimizer_abs_error_reduction_vs_scp"]
        == -80.0
    )


def test_zero_wape_rules_and_small_sample_boundary_are_preserved():
    rows: list[dict] = []
    for index in range(9):
        rows.append(_event(
            engine=ENGINE_OPTIMIZER, block=BLOCK_OLDER_3M, model_name="Nine",
            id_client=1, id_configuration=index, performance=True,
            history=100.0, scp_abs_error=20.0, optimizer_abs_error=10.0,
            scp_signed_error=20.0, optimizer_signed_error=10.0,
            scp_wape=0.2, optimizer_wape=0.1, winner_method="ML",
        ))
    for index in range(10):
        rows.append(_event(
            engine=ENGINE_OPTIMIZER, block=BLOCK_OLDER_3M, model_name="Ten",
            id_client=2, id_configuration=100 + index, performance=True,
            history=100.0, scp_abs_error=20.0, optimizer_abs_error=10.0,
            scp_signed_error=20.0, optimizer_signed_error=10.0,
            scp_wape=0.2, optimizer_wape=0.1, winner_method="ML",
        ))
    rows.extend([
        _event(
            engine=ENGINE_OPTIMIZER, block=BLOCK_RECENT_3M, model_name="BothZero",
            id_client=1, id_configuration=1000, performance=True,
            history=100.0, scp_abs_error=0.0, optimizer_abs_error=0.0,
            scp_signed_error=0.0, optimizer_signed_error=0.0,
            scp_wape=0.0, optimizer_wape=0.0, winner_method="TIE",
        ),
        _event(
            engine=ENGINE_OPTIMIZER, block=BLOCK_RECENT_3M, model_name="OptimizerPerfect",
            id_client=1, id_configuration=1001, performance=True,
            history=100.0, scp_abs_error=20.0, optimizer_abs_error=0.0,
            scp_signed_error=20.0, optimizer_signed_error=0.0,
            scp_wape=0.2, optimizer_wape=0.0, winner_method="ML",
        ),
    ])

    table = build_portfolio_model_result(pd.DataFrame(rows)).by_engine_block_model
    nine = _row(table, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "Nine")
    ten = _row(table, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "Ten")
    both_zero = _row(table, ENGINE_OPTIMIZER, BLOCK_RECENT_3M, "BothZero")
    perfect = _row(table, ENGINE_OPTIMIZER, BLOCK_RECENT_3M, "OptimizerPerfect")

    assert nine["n_performance"] == 9 and bool(nine["small_sample"]) is True
    assert ten["n_performance"] == 10 and bool(ten["small_sample"]) is False
    assert math.isnan(both_zero["optimizer_improvement_vs_scp"])
    assert math.isnan(both_zero["optimizer_median_improvement_vs_scp"])
    assert perfect["optimizer_improvement_vs_scp"] == 100.0
    assert perfect["optimizer_median_improvement_vs_scp"] == 100.0


def test_model_tables_integrate_for_client_and_global_without_historical_fallback():
    client_a = _client_result(_portfolio_dataframe(95001), 95001)
    client_b = _client_result(_portfolio_dataframe(95002), 95002)
    client_table = client_a.portfolio.model_tables.by_engine_block_model

    assert client_a.portfolio.availability.available is True
    assert not client_table.empty
    client_autoets = _row(client_table, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "AutoETS")
    assert client_autoets["n_performance"] == 1
    assert client_autoets["n_clients"] == 1

    global_result = analyze_global([client_a, client_b])
    global_table = global_result.portfolio.model_tables.by_engine_block_model
    global_autoets = _row(global_table, ENGINE_OPTIMIZER, BLOCK_OLDER_3M, "AutoETS")
    assert global_autoets["selection_count"] == 2
    assert global_autoets["n_performance"] == 2
    assert global_autoets["n_clients"] == 2

    historical = _client_result(build_synthetic_client_dataframe(), 96001)
    assert historical.portfolio.availability.available is False
    assert historical.portfolio.model_tables is None
    assert analyze_global([client_a, historical]).portfolio.model_tables is None
