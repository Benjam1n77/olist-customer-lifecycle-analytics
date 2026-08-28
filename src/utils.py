"""指标计算纯函数库。

本模块函数与 SQL 建模口径一一对应（见 docs/metric_definitions.md），
用于：
1. pytest 单元测试验证逻辑边界；
2. SQL × Python 交叉验证（src/validate_data.py）。

约定：日期参数接受 datetime.date / datetime.datetime / pandas Timestamp。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Sequence

# ---------- 生命周期规则阈值 ----------
NEW_CUSTOMER_RECENCY_MAX = 30
ACTIVE_RECENCY_MAX = 90
AT_RISK_RECENCY_MAX = 180

# 低评分阈值
LOW_SCORE_THRESHOLD = 2


def to_date(value: Any) -> date:
    """将 datetime/Timestamp 归一化为 date（注意 datetime 是 date 子类，须先判断）。"""
    if isinstance(value, datetime):
        return value.date()
    return value


def compute_recency_days(last_purchase_date: Any, analysis_date: Any) -> int:
    """Recency = 观察日 − 最近购买日（天）。

    与 SQL 口径一致：DATEDIFF(analysis_date, last_purchase_date)。
    """
    return (to_date(analysis_date) - to_date(last_purchase_date)).days


def classify_lifecycle(recency_days: int, order_count: int) -> str:
    """生命周期标签（判定顺序与 SQL CASE 一致）。

    - new_customer: recency <= 30 且 order_count = 1
    - active_customer: recency <= 90
    - at_risk: 90 < recency <= 180
    - churned: recency > 180
    """
    if recency_days <= NEW_CUSTOMER_RECENCY_MAX and order_count == 1:
        return "new_customer"
    if recency_days <= ACTIVE_RECENCY_MAX:
        return "active_customer"
    if recency_days <= AT_RISK_RECENCY_MAX:
        return "at_risk"
    return "churned"


def assign_value_segment(total_payment: float, p20: float, p80: float) -> str:
    """价值标签：>= p80 高价值，>= p20 中价值，否则低价值。"""
    if total_payment >= p80:
        return "high_value"
    if total_payment >= p20:
        return "mid_value"
    return "low_value"


def is_one_time_buyer(order_count: int) -> bool:
    """一次性购买标签：仅 1 笔有效订单。"""
    return order_count == 1


def compute_delivery_days(purchase_date: Any, delivered_date: Any) -> int | None:
    """delivery_days = 实际签收日期 − 购买日期；任一缺失返回 None。"""
    if purchase_date is None or delivered_date is None:
        return None
    return (to_date(delivered_date) - to_date(purchase_date)).days


def compute_delay_days(delivered_date: Any, estimated_date: Any) -> int | None:
    """delay_days = 实际签收日期 − 预计签收日期；任一缺失返回 None。"""
    if delivered_date is None or estimated_date is None:
        return None
    return (to_date(delivered_date) - to_date(estimated_date)).days


def is_delayed(delivered_date: Any, estimated_date: Any) -> bool | None:
    """is_delayed = 实际签收日期 > 预计签收日期（日期级比较）；缺失返回 None。"""
    if delivered_date is None or estimated_date is None:
        return None
    return to_date(delivered_date) > to_date(estimated_date)


def classify_delay_bucket(delayed: bool | None, delay_days: int | None) -> str | None:
    """延迟分段；当天超时归入 1-3 天档。"""
    if delayed is None:
        return None
    if not delayed:
        return "on_time"
    if delay_days is not None and delay_days <= 3:
        return "delay_1_3"
    if delay_days is not None and delay_days <= 7:
        return "delay_4_7"
    if delay_days is not None and delay_days <= 14:
        return "delay_8_14"
    return "delay_15_plus"


def cohort_month_index(cohort_month: Any, activity_month: Any) -> int:
    """Cohort month_index = 活跃月与首购月的自然月差。

    与 SQL TIMESTAMPDIFF(MONTH, cohort, activity) 一致（按月首对齐）。
    """
    c = to_date(cohort_month)
    a = to_date(activity_month)
    return (a.year - c.year) * 12 + (a.month - c.month)


def score_drop_pct(on_time_avg_score: float, delayed_avg_score: float) -> float:
    """评分下降比例 = (准时均分 − 延迟均分) / 准时均分 × 100。"""
    if on_time_avg_score == 0:
        raise ValueError("准时均分不能为 0")
    return (on_time_avg_score - delayed_avg_score) / on_time_avg_score * 100


def is_low_score(review_score: int | None, threshold: int = LOW_SCORE_THRESHOLD) -> bool | None:
    """is_low_score = review_score <= 2；无评价返回 None。"""
    if review_score is None:
        return None
    return review_score <= threshold


def campaign_rule_hit(
    experience_segment: str | None,
    value_segment: str,
    lifecycle_stage: str,
    order_count: int,
    recency_days: int,
    behavior_segment: str,
) -> str | None:
    """营销规则级联（自上而下命中即停，与 SQL 12 完全一致）。

    Returns:
        reason_code；未命中任何规则返回 None。
    """
    if experience_segment == "service_recovery_needed":
        return "SERVICE_RECOVERY"
    if value_segment == "high_value" and lifecycle_stage == "churned":
        return "WINBACK_HIGH_VALUE"
    if order_count == 1 and 14 <= recency_days <= 180:
        return "SECOND_PURCHASE"
    if value_segment == "high_value" and lifecycle_stage == "at_risk":
        return "RETAIN_AT_RISK"
    if value_segment == "high_value" and lifecycle_stage in (
        "new_customer",
        "active_customer",
    ):
        return "VIP_ENGAGE"
    if behavior_segment == "category_focused":
        return "CATEGORY_PROMO"
    return None


def aggregate_order_items(prices: Sequence[float], freights: Sequence[float]) -> dict[str, float]:
    """订单商品行聚合：goods/freight/item 三个金额。"""
    if len(prices) != len(freights):
        raise ValueError("prices 与 freights 长度不一致")
    goods = round(sum(prices), 2)
    freight = round(sum(freights), 2)
    return {
        "goods_amount": goods,
        "freight_amount": freight,
        "item_amount": round(goods + freight, 2),
    }


def derive_analysis_date(max_valid_purchase_date: Any) -> date:
    """analysis_date = 最大有效购买日期 + 1 天。"""
    return to_date(max_valid_purchase_date) + timedelta(days=1)
