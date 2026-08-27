"""指标逻辑测试：Recency、生命周期边界、高价值分位数、一次性购买标签、评分下降比例。"""

from datetime import date

import pandas as pd
import pytest

from src.analyze_cohort import summarize_mature_retention
from src.utils import (
    assign_value_segment,
    classify_lifecycle,
    compute_recency_days,
    derive_analysis_date,
    is_one_time_buyer,
    score_drop_pct,
)

ANALYSIS_DATE = date(2018, 8, 30)


class TestRecency:
    def test_basic(self) -> None:
        assert compute_recency_days(date(2018, 8, 29), ANALYSIS_DATE) == 1

    def test_one_year(self) -> None:
        assert compute_recency_days(date(2017, 8, 30), ANALYSIS_DATE) == 365

    def test_analysis_date_derivation(self) -> None:
        # analysis_date = 最大有效购买日 + 1 天
        assert derive_analysis_date(date(2018, 8, 29)) == ANALYSIS_DATE


class TestLifecycleBoundaries:
    """生命周期边界测试（30 / 90 / 180 天）。"""

    def test_new_customer_boundary(self) -> None:
        assert classify_lifecycle(30, 1) == "new_customer"
        assert classify_lifecycle(31, 1) == "active_customer"

    def test_new_customer_requires_single_order(self) -> None:
        # recency<=30 但多单 → 不是新客，是活跃
        assert classify_lifecycle(10, 2) == "active_customer"

    def test_active_boundary(self) -> None:
        assert classify_lifecycle(90, 1) == "active_customer"
        assert classify_lifecycle(91, 1) == "at_risk"

    def test_at_risk_boundary(self) -> None:
        assert classify_lifecycle(180, 1) == "at_risk"
        assert classify_lifecycle(181, 1) == "churned"

    def test_churned(self) -> None:
        assert classify_lifecycle(714, 1) == "churned"


class TestValueSegment:
    """高价值分位数逻辑测试。"""

    def test_high_value_at_p80(self) -> None:
        assert assign_value_segment(208.55, 55.26, 208.55) == "high_value"

    def test_mid_value_between(self) -> None:
        assert assign_value_segment(100.0, 55.26, 208.55) == "mid_value"

    def test_mid_value_at_p20(self) -> None:
        assert assign_value_segment(55.26, 55.26, 208.55) == "mid_value"

    def test_low_value_below_p20(self) -> None:
        assert assign_value_segment(55.25, 55.26, 208.55) == "low_value"


class TestOneTimeBuyer:
    def test_one_order(self) -> None:
        assert is_one_time_buyer(1) is True

    def test_two_orders(self) -> None:
        assert is_one_time_buyer(2) is False

    def test_zero_orders(self) -> None:
        assert is_one_time_buyer(0) is False


class TestScoreDrop:
    def test_actual_project_numbers(self) -> None:
        # 实测：准时 4.30，延迟 2.57 → 下降 40.24%
        assert score_drop_pct(4.30, 2.57) == pytest.approx(40.2325, rel=1e-3)

    def test_no_drop(self) -> None:
        assert score_drop_pct(4.0, 4.0) == 0.0

    def test_zero_on_time_raises(self) -> None:
        with pytest.raises(ValueError):
            score_drop_pct(0.0, 2.0)


class TestCohortRetentionSummary:
    def test_m1_is_customer_weighted_and_m2_remains_simple_average(self) -> None:
        cohort = pd.DataFrame(
            {
                "cohort_month": ["2020-01", "2020-02", "2020-01", "2020-02"],
                "month_index": [1, 1, 2, 2],
                "cohort_size": [1, 99, 10, 10],
                "retained_customers": [1, 0, 2, 4],
                "retention_rate": [1.0, 0.0, 0.2, 0.4],
            }
        )

        summary = summarize_mature_retention(cohort).set_index("month_index")

        assert summary.loc[1, "retention_pct"] == 1.0
        assert summary.loc[1, "aggregation_method"] == "weighted_customer_rate"
        assert summary.loc[2, "retention_pct"] == 30.0
        assert summary.loc[2, "aggregation_method"] == "simple_cohort_average"
