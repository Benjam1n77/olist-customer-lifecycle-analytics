"""特征逻辑测试：配送延迟计算、Cohort month_index、营销规则优先级、订单聚合。"""

from datetime import date, datetime

import pytest

from src.utils import (
    aggregate_order_items,
    campaign_rule_hit,
    classify_delay_bucket,
    cohort_month_index,
    compute_delay_days,
    compute_delivery_days,
    is_delayed,
)


class TestDeliveryDelay:
    """配送延迟计算测试。"""

    def test_delivery_days(self) -> None:
        assert compute_delivery_days(date(2018, 1, 1), date(2018, 1, 11)) == 10

    def test_delay_days_positive(self) -> None:
        assert compute_delay_days(date(2018, 1, 15), date(2018, 1, 10)) == 5

    def test_delay_days_negative_early(self) -> None:
        # 提前送达为负值
        assert compute_delay_days(date(2018, 1, 8), date(2018, 1, 10)) == -2

    def test_missing_dates_return_none(self) -> None:
        assert compute_delay_days(None, date(2018, 1, 10)) is None
        assert compute_delivery_days(date(2018, 1, 1), None) is None
        assert is_delayed(None, date(2018, 1, 10)) is None

    def test_is_delayed_flag(self) -> None:
        assert is_delayed(date(2018, 1, 11), date(2018, 1, 10)) is True
        assert is_delayed(date(2018, 1, 10), date(2018, 1, 10)) is False

    def test_datetime_normalized(self) -> None:
        # 时间戳参与比较时归一化到日期级
        delivered = datetime(2018, 1, 10, 15, 30)
        estimated = datetime(2018, 1, 10, 0, 0)
        assert is_delayed(delivered, estimated) is False
        assert compute_delay_days(delivered, estimated) == 0

    def test_same_day_late_goes_to_1_3_bucket(self) -> None:
        # 当天超时（is_delayed=1 但 delay_days=0）归入 1-3 天档
        assert classify_delay_bucket(True, 0) == "delay_1_3"

    def test_bucket_boundaries(self) -> None:
        assert classify_delay_bucket(False, -3) == "on_time"
        assert classify_delay_bucket(True, 3) == "delay_1_3"
        assert classify_delay_bucket(True, 4) == "delay_4_7"
        assert classify_delay_bucket(True, 7) == "delay_4_7"
        assert classify_delay_bucket(True, 8) == "delay_8_14"
        assert classify_delay_bucket(True, 14) == "delay_8_14"
        assert classify_delay_bucket(True, 15) == "delay_15_plus"


class TestCohortMonthIndex:
    """Cohort month_index 测试。"""

    def test_same_month(self) -> None:
        assert cohort_month_index(date(2017, 5, 1), date(2017, 5, 20)) == 0

    def test_next_month(self) -> None:
        assert cohort_month_index(date(2017, 5, 1), date(2017, 6, 1)) == 1

    def test_cross_year(self) -> None:
        assert cohort_month_index(date(2017, 11, 1), date(2018, 2, 1)) == 3

    def test_long_span(self) -> None:
        assert cohort_month_index(date(2016, 9, 1), date(2018, 7, 1)) == 22


class TestCampaignRulePriority:
    """营销规则优先级测试（级联命中即停）。"""

    def test_service_recovery_wins_over_winback(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="service_recovery_needed",
            value_segment="high_value",
            lifecycle_stage="churned",
            order_count=1,
            recency_days=400,
            behavior_segment="one_time_buyer",
        )
        assert hit == "SERVICE_RECOVERY"

    def test_winback_over_second_purchase(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="high_value",
            lifecycle_stage="churned",
            order_count=1,
            recency_days=200,
            behavior_segment="one_time_buyer",
        )
        # recency>180 本也不满足 SECOND_PURCHASE，但验证高价值流失优先
        assert hit == "WINBACK_HIGH_VALUE"

    def test_second_purchase_window(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="mid_value",
            lifecycle_stage="at_risk",
            order_count=1,
            recency_days=100,
            behavior_segment="one_time_buyer",
        )
        assert hit == "SECOND_PURCHASE"

    def test_second_purchase_boundary_below_14(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="mid_value",
            lifecycle_stage="active_customer",
            order_count=1,
            recency_days=13,
            behavior_segment="one_time_buyer",
        )
        # <14 天未到激励时机，落到 category_focused 判断（此处不满足→None）
        assert hit is None

    def test_vip_engage(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="high_value",
            lifecycle_stage="active_customer",
            order_count=3,
            recency_days=20,
            behavior_segment="repeat_buyer",
        )
        assert hit == "VIP_ENGAGE"

    def test_category_promo_fallback(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="low_value",
            lifecycle_stage="active_customer",
            order_count=2,
            recency_days=30,
            behavior_segment="category_focused",
        )
        assert hit == "CATEGORY_PROMO"

    def test_no_rule_hit(self) -> None:
        hit = campaign_rule_hit(
            experience_segment="delivery_normal",
            value_segment="low_value",
            lifecycle_stage="churned",
            order_count=1,
            recency_days=400,
            behavior_segment="one_time_buyer",
        )
        assert hit is None


class TestOrderAggregation:
    """订单商品行金额聚合测试。"""

    def test_single_item(self) -> None:
        result = aggregate_order_items([58.90], [13.29])
        assert result["goods_amount"] == 58.90
        assert result["freight_amount"] == 13.29
        assert result["item_amount"] == 72.19

    def test_multi_item(self) -> None:
        result = aggregate_order_items([10.00, 20.50, 30.25], [5.00, 5.00, 5.00])
        assert result["goods_amount"] == 60.75
        assert result["freight_amount"] == 15.00
        assert result["item_amount"] == 75.75

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            aggregate_order_items([10.0], [1.0, 2.0])
