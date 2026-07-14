from src.periods import (
    ALL_PERIODS,
    MONTHLY_PERIODS,
    QUARTER_MONTHS,
    SEMESTER_MONTHS,
    period_columns,
    visible_label,
)


def test_recent_3m_is_m1_m2_m3():
    assert QUARTER_MONTHS["RECENT_3M"] == ["M1", "M2", "M3"]


def test_older_3m_is_m4_m5_m6():
    assert QUARTER_MONTHS["OLDER_3M"] == ["M4", "M5", "M6"]


def test_semester_is_all_six_months():
    assert SEMESTER_MONTHS == MONTHLY_PERIODS
    assert SEMESTER_MONTHS == ["M1", "M2", "M3", "M4", "M5", "M6"]


def test_all_periods_contains_nine_technical_periods():
    assert set(ALL_PERIODS) == {"M1", "M2", "M3", "M4", "M5", "M6", "RECENT_3M", "OLDER_3M", "6M"}


def test_visible_labels_do_not_use_forbidden_terms():
    forbidden = ["trimestre reciente", "trimestre anterior", "Q1", "Q2"]
    for period in ALL_PERIODS:
        label = visible_label(period)
        for term in forbidden:
            assert term.lower() not in label.lower()


def test_visible_label_semester():
    assert visible_label("6M") == "Semestre completo (M1-M6)"


def test_period_columns_monthly_naming():
    cols = period_columns("M1")
    assert cols.total_history == "HISTORY_M1"
    assert cols.scp_total_forecast == "SCP_FORECAST_M1"
    assert cols.ml_wape == "ML_WAPE_M1"
    assert cols.winner_method == "WINNER_METHOD_M1"


def test_period_columns_aggregate_naming():
    cols = period_columns("RECENT_3M")
    assert cols.total_history == "TOTAL_HISTORY_RECENT_3M"
    assert cols.scp_total_abs_error == "SCP_TOTAL_ABS_ERROR_RECENT_3M"
    assert cols.winner_method == "WINNER_METHOD_RECENT_3M"

    cols_6m = period_columns("6M")
    assert cols_6m.total_history == "TOTAL_HISTORY_6M"
    assert cols_6m.ml_wape == "ML_WAPE_6M"


def test_period_columns_no_duplicate_names_across_periods():
    seen = set()
    for period in ALL_PERIODS:
        for col in period_columns(period).as_tuple():
            assert col not in seen, f"columna duplicada entre periodos: {col}"
            seen.add(col)
