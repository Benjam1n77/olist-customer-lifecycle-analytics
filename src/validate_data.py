"""SQL × Python 交叉验证模块。

对 11 个关键指标分别用 SQL 与 Python（pandas）独立计算并比对：
    总客户数、有效订单数、一次性购买用户占比、复购率、总支付金额、
    平均客单价、延迟订单率、准时平均评分、延迟平均评分、
    高价值流失用户数、M1 留存率

判定标准：
    - 计数类：必须完全相等；
    - 金额类：绝对差 < 0.05 BRL（两位小数舍入误差）；
    - 百分比/均值类：绝对差 < 0.01（小数或百分点，按指标口径）。

结果输出至 outputs/tables/cross_validation_results.csv。

使用方式：
    python -m src.validate_data
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("validate_data")


def _engine(config: dict):
    db = get_database_config(config)
    return create_engine(db.to_sqlalchemy_url())


def _scalar(conn, sql: str) -> float:
    """执行 SQL 返回单个标量值。"""
    return conn.execute(text(sql)).scalar()


def run_cross_validation(config: dict) -> pd.DataFrame:
    """执行全部交叉验证，返回结果 DataFrame。"""
    engine = _engine(config)
    rows: list[dict] = []

    with engine.connect() as conn:
        # ---------- Python 端：一次性读取所需列 ----------
        orders = pd.read_sql(
            text(
                "SELECT customer_unique_id, order_status, payment_amount "
                "FROM mart_order_summary"
            ),
            conn,
        )
        customers = pd.read_sql(
            text("SELECT order_count FROM mart_customer_features"), conn
        )
        delivery = pd.read_sql(
            text("SELECT is_delayed, review_score FROM mart_delivery_sample"), conn
        )
        segments = pd.read_sql(
            text("SELECT value_segment, lifecycle_stage FROM dim_customer_segment"),
            conn,
        )
        cohort = pd.read_sql(
            text(
                "SELECT month_index, cohort_size, retained_customers "
                "FROM cohort_retention_long "
                "WHERE month_index = 1"
            ),
            conn,
        )

        # ---------- Python 端计算 ----------
        py = {
            "total_customers": int(orders["customer_unique_id"].nunique()),
            "valid_orders": int((orders["order_status"] == "delivered").sum()),
            "one_time_buyer_pct": round(
                (customers["order_count"] == 1).mean() * 100, 2
            ),
            "repeat_rate_pct": round((customers["order_count"] >= 2).mean() * 100, 2),
            "total_payment": round(
                orders.loc[orders["order_status"] == "delivered", "payment_amount"].sum(), 2
            ),
            "average_order_value": round(
                orders.loc[orders["order_status"] == "delivered", "payment_amount"].mean(), 2
            ),
            "delay_rate_pct": round(delivery["is_delayed"].mean() * 100, 2),
            "on_time_avg_score": round(
                delivery.loc[delivery["is_delayed"] == 0, "review_score"].mean(), 2
            ),
            "delayed_avg_score": round(
                delivery.loc[delivery["is_delayed"] == 1, "review_score"].mean(), 2
            ),
            "high_value_churned": int(
                (
                    (segments["value_segment"] == "high_value")
                    & (segments["lifecycle_stage"] == "churned")
                ).sum()
            ),
            "m1_retention_pct": round(
                cohort["retained_customers"].sum()
                / cohort["cohort_size"].sum()
                * 100,
                2,
            ),
        }

        # ---------- SQL 端计算 ----------
        sql = {
            "total_customers": _scalar(
                conn, "SELECT COUNT(DISTINCT customer_unique_id) FROM mart_order_summary"
            ),
            "valid_orders": _scalar(
                conn,
                "SELECT COUNT(*) FROM mart_order_summary WHERE order_status='delivered'",
            ),
            "one_time_buyer_pct": _scalar(
                conn,
                "SELECT ROUND(SUM(order_count = 1) / COUNT(*) * 100, 2) "
                "FROM mart_customer_features",
            ),
            "repeat_rate_pct": _scalar(
                conn,
                "SELECT ROUND(SUM(order_count >= 2) / COUNT(*) * 100, 2) "
                "FROM mart_customer_features",
            ),
            "total_payment": _scalar(
                conn,
                "SELECT ROUND(SUM(payment_amount), 2) FROM mart_order_summary "
                "WHERE order_status='delivered'",
            ),
            "average_order_value": _scalar(
                conn,
                "SELECT ROUND(AVG(payment_amount), 2) FROM mart_order_summary "
                "WHERE order_status='delivered'",
            ),
            "delay_rate_pct": _scalar(
                conn,
                "SELECT ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) FROM mart_delivery_sample",
            ),
            "on_time_avg_score": _scalar(
                conn,
                "SELECT ROUND(AVG(review_score), 2) FROM mart_delivery_sample "
                "WHERE is_delayed = 0",
            ),
            "delayed_avg_score": _scalar(
                conn,
                "SELECT ROUND(AVG(review_score), 2) FROM mart_delivery_sample "
                "WHERE is_delayed = 1",
            ),
            "high_value_churned": _scalar(
                conn,
                "SELECT COUNT(*) FROM dim_customer_segment "
                "WHERE value_segment='high_value' AND lifecycle_stage='churned'",
            ),
            "m1_retention_pct": _scalar(
                conn,
                "SELECT ROUND(SUM(retained_customers) / "
                "SUM(cohort_size) * 100, 2) FROM cohort_retention_long "
                "WHERE month_index = 1",
            ),
        }
    engine.dispose()

    # ---------- 比对 ----------
    tolerances = {
        "total_customers": 0,
        "valid_orders": 0,
        "one_time_buyer_pct": 0.01,
        "repeat_rate_pct": 0.01,
        "total_payment": 0.05,
        "average_order_value": 0.01,
        "delay_rate_pct": 0.01,
        "on_time_avg_score": 0.01,
        "delayed_avg_score": 0.01,
        "high_value_churned": 0,
        "m1_retention_pct": 0.01,
    }
    for metric, sql_val in sql.items():
        py_val = py[metric]
        diff = abs(float(sql_val) - float(py_val))
        rows.append(
            {
                "metric": metric,
                "sql_value": sql_val,
                "python_value": py_val,
                "abs_diff": round(diff, 4),
                "tolerance": tolerances[metric],
                "status": "PASS" if diff <= tolerances[metric] else "FAIL",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    """交叉验证入口。"""
    setup_logging()
    config = load_config()

    result = run_cross_validation(config)
    out_dir = get_path(config, "output_tables_dir", ensure_exists=True)
    out_path = out_dir / "cross_validation_results.csv"
    result.to_csv(out_path, index=False)

    for _, row in result.iterrows():
        logger.info(
            "%-22s SQL=%-14s Python=%-14s diff=%-8s [%s]",
            row["metric"],
            row["sql_value"],
            row["python_value"],
            row["abs_diff"],
            row["status"],
        )

    failed = result[result["status"] == "FAIL"]
    if not failed.empty:
        logger.error("交叉验证存在 %d 项失败：%s", len(failed), list(failed["metric"]))
        return 1
    logger.info("全部 %d 项交叉验证通过，结果已保存：%s", len(result), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
