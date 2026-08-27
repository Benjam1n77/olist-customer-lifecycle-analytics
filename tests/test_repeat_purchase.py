"""首购后 90 天二购分析的窗口与汇总逻辑测试。"""

from datetime import date, datetime

import pandas as pd

from src.analyze_repeat_purchase import (
    is_mature_first_purchase,
    is_repeat_within_window,
    summarize_segment_rates,
)


def test_mature_window_includes_90_day_boundary() -> None:
    assert is_mature_first_purchase(date(2018, 6, 1), date(2018, 8, 30))
    assert not is_mature_first_purchase(date(2018, 6, 2), date(2018, 8, 30))


def test_repeat_window_boundaries() -> None:
    first = datetime(2018, 1, 1, 12, 0, 0)
    assert not is_repeat_within_window(first, datetime(2018, 1, 1, 12, 0, 0))
    assert not is_repeat_within_window(first, datetime(2018, 1, 1, 23, 59, 59))
    assert is_repeat_within_window(first, datetime(2018, 1, 2, 0, 0, 0))
    assert is_repeat_within_window(first, datetime(2018, 4, 1, 12, 0, 0))
    assert not is_repeat_within_window(first, datetime(2018, 4, 2, 0, 0, 0))
    assert not is_repeat_within_window(first, None)


def test_segment_rate_reconciles_to_overall() -> None:
    sample = pd.DataFrame(
        {
            "repeat_90d": [1, 0, 1, 0],
            "delivery_status": ["on_time", "on_time", "delayed", "delayed"],
            "review_group": ["high_4_5"] * 4,
            "payment_type": ["credit_card"] * 4,
            "installment_flag": ["single_payment"] * 4,
            "order_value_quartile": ["Q1_low", "Q2", "Q3", "Q4_high"],
            "item_count_group": ["single_item"] * 4,
            "seller_count_group": ["single_seller"] * 4,
            "category_group": ["other"] * 4,
        }
    )
    rates = summarize_segment_rates(sample)
    overall = rates[(rates["dimension"] == "overall") & (rates["group"] == "all")]
    assert int(overall.iloc[0]["customer_count"]) == 4
    assert int(overall.iloc[0]["repeat_customers_90d"]) == 2
    assert float(overall.iloc[0]["repeat_rate_90d_pct"]) == 50.0
