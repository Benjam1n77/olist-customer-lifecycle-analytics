"""分析结果导出模块。

阶段 9 职责：
1. 导出营销人群名单 mart_campaign_target_list 为 CSV；
2. 生成模拟触达任务表（明确标注 SIMULATED，仅演示排期，
   本项目未实现真实触达系统——Brief 第 12 节约束）。

后续阶段 10 将在本模块继续扩展图表与 Tableau 数据导出。
阶段 10 职责：
3. 导出高价值流失客户名单（Brief 11.3）；
4. 导出 Tableau 汇总数据：中间表进入本地目录，最终展示表进入 outputs/tableau/；
5. 客户级名单与模拟任务统一进入 outputs/local/，不提交到 GitHub。

使用方式：
    python -m src.export_outputs --campaign
    python -m src.export_outputs --tableau --churn
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("export_outputs")

# 各规则的模拟排期偏移（天）：相对分析观察日 2018-08-30
_SIMULATED_OFFSET_DAYS: dict[str, int] = {
    "SERVICE_RECOVERY": 1,    # 服务补救最紧急
    "WINBACK_HIGH_VALUE": 3,
    "RETAIN_AT_RISK": 5,
    "SECOND_PURCHASE": 7,
    "VIP_ENGAGE": 10,
    "CATEGORY_PROMO": 14,
}

ANALYSIS_DATE = pd.Timestamp("2018-08-30")


def build_tableau_dashboard_csvs(source_dir: Path, out_dir: Path) -> list[Path]:
    """从本地中间表生成公开 Dashboard 汇总，计算口径保持不变。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(source_dir / "customer_overview_metrics.csv")
    metric_values = metrics.set_index("metric")["value"]
    required_metrics = {
        "total_customers",
        "valid_delivered_orders",
        "total_payment_brl",
        "repeat_buyer_pct",
        "one_time_buyer_pct",
    }
    missing = required_metrics.difference(metric_values.index)
    if missing:
        raise ValueError(f"Tableau 总览源数据缺少指标：{sorted(missing)}")

    customer_overview = pd.DataFrame(
        [
            {
                "customer_count": int(metric_values["total_customers"]),
                "order_count": int(metric_values["valid_delivered_orders"]),
                "payment_amount": round(float(metric_values["total_payment_brl"]), 2),
                "repeat_rate": round(float(metric_values["repeat_buyer_pct"]), 2),
                "one_time_rate": round(float(metric_values["one_time_buyer_pct"]), 2),
            }
        ]
    )

    segments = pd.read_csv(source_dir / "customer_segments.csv")
    segments["weighted_aov"] = segments["avg_aov"] * segments["customer_count"]
    segment_dashboard = (
        segments.groupby("final_segment", as_index=False)
        .agg(
            customer_count=("customer_count", "sum"),
            total_payment=("total_payment", "sum"),
            weighted_aov=("weighted_aov", "sum"),
        )
        .rename(columns={"final_segment": "segment"})
    )
    segment_dashboard["payment_share"] = (
        segment_dashboard["total_payment"]
        / float(metric_values["total_payment_brl"])
        * 100
    ).round(2)
    segment_dashboard["average_order_value"] = (
        segment_dashboard["weighted_aov"] / segment_dashboard["customer_count"]
    ).round(2)
    segment_dashboard = segment_dashboard[
        ["segment", "customer_count", "payment_share", "average_order_value"]
    ].sort_values("customer_count", ascending=False)

    dashboard_frames = {
        "customer_overview.csv": customer_overview,
        "customer_segment_dashboard.csv": segment_dashboard,
        "cohort_dashboard.csv": pd.read_csv(source_dir / "cohort_retention.csv"),
        "delivery_dashboard.csv": pd.read_csv(source_dir / "delivery_experience.csv"),
        "campaign_dashboard.csv": pd.read_csv(source_dir / "campaign_targets.csv"),
    }

    if round(customer_overview.loc[0, "repeat_rate"] + customer_overview.loc[0, "one_time_rate"], 2) != 100:
        raise ValueError("复购率与一次性购买率未勾稽至 100%")
    if int(segment_dashboard["customer_count"].sum()) != int(metric_values["total_customers"]):
        raise ValueError("客户分层人数未与客户总数勾稽")
    if abs(float(segment_dashboard["payment_share"].sum()) - 100) > 0.05:
        raise ValueError("客户分层支付占比未勾稽至 100%")

    outputs: list[Path] = []
    for name, frame in dashboard_frames.items():
        output_path = out_dir / name
        frame.to_csv(output_path, index=False)
        outputs.append(output_path)
        logger.info("Tableau Dashboard 数据已生成：%s（%d 行）", output_path, len(frame))
    return outputs


def _get_engine(config: dict):
    """创建 SQLAlchemy 引擎。"""
    db = get_database_config(config)
    return create_engine(db.to_sqlalchemy_url())


def export_campaign_list(config: dict) -> Path:
    """将客户级营销名单导出到本地目录。"""
    engine = _get_engine(config)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(
                    "SELECT * FROM mart_campaign_target_list "
                    "ORDER BY FIELD(campaign_priority, 'high', 'medium_high', 'medium'), "
                    "reason_code, total_payment DESC"
                ),
                conn,
            )
    finally:
        engine.dispose()

    out_dir = get_path(config, "output_local_dir", ensure_exists=True)
    out_path = out_dir / "customer_campaign_target_list.csv"
    df.to_csv(out_path, index=False)
    logger.info("营销名单已导出：%s（%d 人）", out_path, len(df))
    return out_path


def export_simulated_tasks(config: dict) -> Path:
    """生成模拟触达任务表（明确标注为模拟数据）。"""
    engine = _get_engine(config)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(
                    "SELECT customer_unique_id, reason_code, campaign_priority, "
                    "recommended_action, recommended_channel "
                    "FROM mart_campaign_target_list"
                ),
                conn,
            )
    finally:
        engine.dispose()

    df["simulated_send_date"] = df["reason_code"].map(
        lambda r: (ANALYSIS_DATE + pd.Timedelta(days=_SIMULATED_OFFSET_DAYS[r]))
        .date()
        .isoformat()
    )
    df["task_status"] = "SIMULATED"  # 未真实发送，仅演示排期
    df = df.sort_values(["simulated_send_date", "campaign_priority", "reason_code"])

    out_dir = get_path(config, "output_local_dir", ensure_exists=True)
    out_path = out_dir / "simulated_campaign_tasks.csv"
    df.to_csv(out_path, index=False)
    logger.info(
        "模拟触达任务表已导出：%s（%d 条，全部标注 SIMULATED，未真实发送）",
        out_path,
        len(df),
    )
    return out_path


def export_high_value_churned(config: dict) -> Path:
    """导出高价值流失客户名单（Brief 11.3）并输出汇总指标。"""
    engine = _get_engine(config)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(
                    "SELECT cf.customer_unique_id, cf.first_purchase_date, "
                    "cf.last_purchase_date, cf.recency_days, cf.order_count, "
                    "cf.total_payment, cf.average_order_value, cf.favorite_category, "
                    "cf.customer_state, cf.average_review_score, cf.delayed_order_rate "
                    "FROM mart_customer_features cf "
                    "JOIN dim_customer_segment s USING (customer_unique_id) "
                    "WHERE s.value_segment = 'high_value' "
                    "  AND s.lifecycle_stage = 'churned' "
                    "ORDER BY cf.total_payment DESC"
                ),
                conn,
            )
            totals = pd.read_sql(
                text(
                    "SELECT COUNT(*) AS all_customers, SUM(total_payment) AS all_payment "
                    "FROM mart_customer_features"
                ),
                conn,
            )
    finally:
        engine.dispose()

    out_dir = get_path(config, "output_local_dir", ensure_exists=True)
    out_path = out_dir / "high_value_churned_customers.csv"
    df.to_csv(out_path, index=False)

    all_row = totals.iloc[0]
    cust_share = len(df) / all_row["all_customers"] * 100
    pay_share = df["total_payment"].sum() / all_row["all_payment"] * 100
    logger.info(
        "高价值流失名单已导出：%s（%d 人，占客户 %.2f%%，历史支付占比 %.2f%%）",
        out_path,
        len(df),
        cust_share,
        pay_share,
    )
    return out_path


def export_tableau_csvs(config: dict) -> list[Path]:
    """导出 6 个最终 Tableau 汇总 CSV，中间表仅留在本地目录。"""
    out_dir = get_path(config, "output_tableau_dir", ensure_exists=True)
    source_dir = get_path(config, "output_local_dir", ensure_exists=True) / "tableau_staging"
    source_dir.mkdir(parents=True, exist_ok=True)
    engine = _get_engine(config)
    outputs: list[Path] = []

    queries: dict[str, str] = {
        # 页面 1：客户价值总览（核心指标 + 月度趋势）
        "customer_overview_metrics.csv": """
            SELECT metric, value FROM (
                SELECT 1 AS ord, 'total_customers' AS metric,
                       CAST(COUNT(*) AS CHAR) AS value FROM mart_customer_features
                UNION ALL
                SELECT 2, 'valid_delivered_orders',
                       CAST(COUNT(*) AS CHAR) FROM mart_order_summary WHERE order_status = 'delivered'
                UNION ALL
                SELECT 3, 'total_payment_brl',
                       CAST(ROUND(SUM(total_payment), 2) AS CHAR) FROM mart_customer_features
                UNION ALL
                SELECT 4, 'average_order_value_brl',
                       CAST(ROUND(AVG(average_order_value), 2) AS CHAR) FROM mart_customer_features
                UNION ALL
                SELECT 5, 'one_time_buyer_pct',
                       CAST(ROUND(SUM(order_count = 1) / COUNT(*) * 100, 2) AS CHAR) FROM mart_customer_features
                UNION ALL
                SELECT 6, 'repeat_buyer_pct',
                       CAST(ROUND(SUM(order_count >= 2) / COUNT(*) * 100, 2) AS CHAR) FROM mart_customer_features
                UNION ALL
                SELECT 7, 'high_value_customers',
                       CAST(SUM(value_segment = 'high_value') AS CHAR) FROM dim_customer_segment
                UNION ALL
                SELECT 8, 'high_value_churned_customers',
                       CAST(SUM(value_segment = 'high_value' AND lifecycle_stage = 'churned') AS CHAR)
                       FROM dim_customer_segment
            ) t ORDER BY ord
        """,
        # 页面 1/2：用户分层人数与收入贡献
        "customer_segments.csv": """
            SELECT s.final_segment, s.value_segment, s.lifecycle_stage,
                   COUNT(*) AS customer_count,
                   ROUND(SUM(cf.total_payment), 2) AS total_payment,
                   ROUND(AVG(cf.average_order_value), 2) AS avg_aov
            FROM dim_customer_segment s
            JOIN mart_customer_features cf USING (customer_unique_id)
            GROUP BY s.final_segment, s.value_segment, s.lifecycle_stage
            ORDER BY customer_count DESC
        """,
        # 页面 2：Cohort 留存
        "cohort_retention.csv": """
            SELECT cohort_month, activity_month, month_index, cohort_size,
                   retained_customers, ROUND(retention_rate * 100, 2) AS retention_pct
            FROM cohort_retention_long ORDER BY cohort_month, month_index
        """,
        # 页面 3：履约体验（分段 + 州两个粒度，用 grain 列区分）
        "delivery_experience.csv": """
            SELECT 'delay_bucket' AS grain,
                   delay_bucket COLLATE utf8mb4_unicode_ci AS dim_value,
                   COUNT(*) AS orders,
                   ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) AS delay_rate_pct,
                   ROUND(AVG(review_score), 2) AS avg_score
            FROM mart_delivery_sample GROUP BY delay_bucket
            UNION ALL
            SELECT 'state', customer_state, COUNT(*),
                   ROUND(SUM(is_delayed) / COUNT(*) * 100, 2),
                   ROUND(AVG(review_score), 2)
            FROM mart_delivery_sample GROUP BY customer_state
        """,
        # 页面 1/3：类别表现
        "category_performance.csv": """
            SELECT m.main_category,
                   COUNT(*) AS delivered_orders,
                   ROUND(SUM(m.payment_amount), 2) AS revenue,
                   ROUND(AVG(m.review_score), 2) AS avg_score,
                   ROUND(SUM(m.is_delayed) / SUM(m.is_delayed IS NOT NULL) * 100, 2) AS delay_rate_pct
            FROM mart_order_summary m
            WHERE m.order_status = 'delivered' AND m.main_category IS NOT NULL
            GROUP BY m.main_category ORDER BY revenue DESC
        """,
        # 页面 1：营销目标汇总
        "campaign_targets.csv": """
            SELECT reason_code, campaign_priority, COUNT(*) AS customer_count,
                   ROUND(SUM(total_payment), 2) AS total_payment,
                   ROUND(AVG(recency_days), 0) AS avg_recency_days
            FROM mart_campaign_target_list
            GROUP BY reason_code, campaign_priority ORDER BY customer_count DESC
        """,
    }

    try:
        with engine.connect() as conn:
            for name, sql in queries.items():
                df = pd.read_sql(text(sql), conn)
                # 品类汇总已是最终表；其余五张供 Dashboard 转换使用。
                target_dir = out_dir if name == "category_performance.csv" else source_dir
                out_path = target_dir / name
                df.to_csv(out_path, index=False)
                outputs.append(out_path)
                logger.info("Tableau 数据已导出：%s（%d 行）", out_path, len(df))
    finally:
        engine.dispose()
    outputs.extend(build_tableau_dashboard_csvs(source_dir, out_dir))
    return outputs


def main(argv: list[str] | None = None) -> int:
    """导出入口：python -m src.export_outputs --campaign [--tableau] [--churn]"""
    parser = argparse.ArgumentParser(description="导出分析结果")
    parser.add_argument(
        "--campaign", action="store_true", help="导出营销名单与模拟触达任务表"
    )
    parser.add_argument(
        "--tableau", action="store_true", help="导出 6 个 Tableau 看板数据 CSV"
    )
    parser.add_argument(
        "--churn", action="store_true", help="导出高价值流失客户名单"
    )
    args = parser.parse_args(argv)

    setup_logging()
    config = load_config()

    did_something = False
    if args.campaign:
        export_campaign_list(config)
        export_simulated_tasks(config)
        did_something = True
    if args.churn:
        export_high_value_churned(config)
        did_something = True
    if args.tableau:
        export_tableau_csvs(config)
        did_something = True

    if not did_something:
        logger.info("未指定导出目标，可用参数：--campaign / --tableau / --churn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
