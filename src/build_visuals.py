"""Python 核心分析图表生成模块（图 01–12）。

口径约束：
- 所有数值读取 MySQL 建模产出表，与 SQL 指标口径一致；
- 图表文字使用英文（避免 matplotlib 中文字体缺失），说明性文字留在 README；
- 图片统一保存至 outputs/figures/。

使用方式：
    python -m src.build_visuals
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("build_visuals")

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def _engine(config: dict):
    db = get_database_config(config)
    return create_engine(db.to_sqlalchemy_url())


def q(config: dict, sql: str) -> pd.DataFrame:
    """执行 SQL 并返回 DataFrame（内部辅助函数）。"""
    engine = _engine(config)
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)
    finally:
        engine.dispose()


def _save(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_path = out_dir / name
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("已保存：%s", out_path)


# ---------- 01 订单状态分布 ----------
def fig01_order_status(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT order_status, COUNT(*) AS cnt FROM mart_order_summary "
        "GROUP BY order_status ORDER BY cnt DESC",
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#2ca02c" if s == "delivered" else "#999999" for s in df["order_status"]]
    ax.bar(df["order_status"], df["cnt"], color=colors)
    ax.set_title("Order Status Distribution (all 99,441 orders)")
    ax.set_xlabel("Order Status")
    ax.set_ylabel("Order Count")
    ax.tick_params(axis="x", rotation=30)
    _save(fig, out_dir, "01_order_status_distribution.png")


# ---------- 02 月度订单与收入 ----------
def fig02_monthly_orders_revenue(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT purchase_month, COUNT(*) AS orders, "
        "ROUND(SUM(payment_amount), 0) AS revenue "
        "FROM mart_order_summary WHERE order_status = 'delivered' "
        "GROUP BY purchase_month ORDER BY purchase_month",
    )
    fig, ax1 = plt.subplots(figsize=(13, 5))
    ax1.bar(df["purchase_month"], df["orders"], color="#4c72b0", label="Delivered Orders")
    ax1.set_xlabel("Purchase Month")
    ax1.set_ylabel("Delivered Order Count", color="#4c72b0")
    ax2 = ax1.twinx()
    ax2.plot(df["purchase_month"], df["revenue"], color="#c44e52", marker="o", label="Revenue (BRL)")
    ax2.set_ylabel("Revenue (BRL)", color="#c44e52")
    ax2.spines["top"].set_visible(False)
    ax1.set_title("Monthly Delivered Orders and Revenue (valid orders)")
    ax1.tick_params(axis="x", rotation=60)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    _save(fig, out_dir, "02_monthly_orders_revenue.png")


# ---------- 03 一次性 vs 复购用户 ----------
def fig03_one_time_vs_repeat(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT CASE WHEN order_count = 1 THEN 'one_time' ELSE 'repeat' END AS buyer_type, "
        "COUNT(*) AS customers, ROUND(AVG(average_order_value), 2) AS avg_aov, "
        "ROUND(AVG(total_payment), 2) AS avg_total_payment, "
        "ROUND(AVG(average_review_score), 2) AS avg_review_score, "
        "ROUND(AVG(delayed_order_rate) * 100, 2) AS avg_delay_rate_pct "
        "FROM mart_customer_features GROUP BY buyer_type",
    ).set_index("buyer_type")
    metrics = [
        ("avg_aov", "Average Order Value (BRL)"),
        ("avg_total_payment", "Average Total Payment (BRL)"),
        ("avg_review_score", "Average Review Score"),
        ("avg_delay_rate_pct", "Average Delay Rate (%)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (col, title) in zip(axes.flat, metrics):
        df[["avg_aov", "avg_total_payment", "avg_review_score", "avg_delay_rate_pct"]][col].plot(
            kind="bar", ax=ax, color=["#4c72b0", "#dd8452"]
        )
        ax.set_title(title)
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=0)
        for i, v in enumerate(df[col]):
            ax.text(i, v, f"{v:,.2f}", ha="center", va="bottom", fontsize=9)
    fig.suptitle(
        "One-time vs Repeat Buyers (delivered orders; "
        f"one-time={int(df.loc['one_time', 'customers']):,}, repeat={int(df.loc['repeat', 'customers']):,})",
        y=1.00,
    )
    _save(fig, out_dir, "03_one_time_vs_repeat_buyers.png")


# ---------- 04 客户价值分布 ----------
def fig04_value_distribution(config: dict, out_dir: Path) -> None:
    df = q(config, "SELECT total_payment FROM mart_customer_features")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(df["total_payment"].clip(upper=df["total_payment"].quantile(0.99)), bins=60, color="#55a868")
    p20, p80 = df["total_payment"].quantile([0.2, 0.8])
    ax.axvline(p20, color="#c44e52", linestyle="--", label=f"p20 = {p20:.2f}")
    ax.axvline(p80, color="#8172b3", linestyle="--", label=f"p80 = {p80:.2f}")
    ax.set_title("Customer Value Distribution (total_payment, clipped at p99)")
    ax.set_xlabel("Total Payment (BRL)")
    ax.set_ylabel("Customer Count")
    ax.legend()
    _save(fig, out_dir, "04_customer_value_distribution.png")


# ---------- 05 最终人群分布 ----------
def fig05_segment_distribution(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT final_segment, COUNT(*) AS cnt FROM dim_customer_segment "
        "GROUP BY final_segment ORDER BY cnt DESC",
    )
    name_map = {
        "履约受损客户": "Fulfillment-damaged",
        "高价值活跃客户": "High-value active",
        "高价值流失风险客户": "High-value at-risk",
        "高价值已流失客户": "High-value churned",
        "重复购买成长客户": "Repeat growth",
        "首购未复购客户": "One-time (not repeated)",
        "低价值长期沉默客户": "Low-value silent",
        "其他普通客户": "Others",
    }
    df["label"] = df["final_segment"].map(name_map)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(df["label"][::-1], df["cnt"][::-1], color="#4c72b0")
    customer_count = int(df["cnt"].sum())
    ax.set_title(f"Final Customer Segment Distribution ({customer_count:,} customers)")
    ax.set_xlabel("Customer Count")
    for i, v in enumerate(df["cnt"][::-1]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    _save(fig, out_dir, "05_customer_segment_distribution.png")


# ---------- 06 Cohort 留存热力图 ----------
def fig06_cohort_heatmap(config: dict, out_dir: Path) -> None:
    from src.analyze_cohort import load_retention, plot_heatmap

    df = load_retention(config)
    plot_heatmap(df, out_dir)


# ---------- 07 M1 留存趋势 ----------
def fig07_m1_trend(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT cohort_month, ROUND(retention_rate * 100, 2) AS m1_retention_pct, cohort_size "
        "FROM cohort_retention_long "
        "WHERE month_index = 1 AND cohort_size >= 100 ORDER BY cohort_month",
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        [str(m)[:7] for m in df["cohort_month"]],
        df["m1_retention_pct"],
        marker="o",
        color="#4c72b0",
    )
    ax.set_title("M1 Retention Rate by Cohort (cohort size >= 100)")
    ax.set_xlabel("Cohort Month (First Purchase)")
    ax.set_ylabel("M1 Retention Rate (%)")
    ax.tick_params(axis="x", rotation=60)
    _save(fig, out_dir, "07_m1_retention_trend.png")


# ---------- 08 准时 vs 延迟评分 ----------
def fig08_on_time_vs_delayed(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT CASE WHEN is_delayed = 0 THEN 'on_time' ELSE 'delayed' END AS grp, "
        "COUNT(*) AS orders, ROUND(AVG(review_score), 2) AS avg_score "
        "FROM mart_delivery_sample GROUP BY grp",
    ).set_index("grp")
    fig, ax = plt.subplots(figsize=(7, 5))
    df["avg_score"].plot(kind="bar", ax=ax, color=["#55a868", "#c44e52"], legend=False)
    ax.set_title("Average Review Score: On-time vs Delayed Orders")
    ax.set_xlabel("")
    ax.set_ylabel("Average Review Score (1-5)")
    ax.set_ylim(0, 5)
    ax.tick_params(axis="x", rotation=0)
    for i, v in enumerate(df["avg_score"]):
        ax.text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=11)
    ax.text(0.5, -0.18, f"Score drop: 40.24% (on-time {df.loc['on_time', 'avg_score']:.2f} -> delayed {df.loc['delayed', 'avg_score']:.2f})", transform=ax.transAxes, ha="center", fontsize=9)
    _save(fig, out_dir, "08_on_time_vs_delayed_review_score.png")


# ---------- 09 延迟分段评分 ----------
def fig09_delay_bucket_score(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT delay_bucket, COUNT(*) AS orders, ROUND(AVG(review_score), 2) AS avg_score "
        "FROM mart_delivery_sample GROUP BY delay_bucket "
        "ORDER BY FIELD(delay_bucket, 'on_time', 'delay_1_3', 'delay_4_7', 'delay_8_14', 'delay_15_plus')",
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(df["delay_bucket"], df["avg_score"], color=["#55a868", "#ccb974", "#dd8452", "#c44e52", "#8c2f39"])
    ax.set_title("Average Review Score by Delay Bucket")
    ax.set_xlabel("Delay Bucket")
    ax.set_ylabel("Average Review Score (1-5)")
    ax.set_ylim(0, 5)
    for i, (v, n) in enumerate(zip(df["avg_score"], df["orders"])):
        ax.text(i, v + 0.05, f"{v:.2f}\n(n={n:,})", ha="center", fontsize=9)
    _save(fig, out_dir, "09_delay_bucket_review_score.png")


# ---------- 10 各州延迟率 ----------
def fig10_state_delay_rate(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT customer_state, COUNT(*) AS orders, "
        "ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) AS delay_rate_pct "
        "FROM mart_delivery_sample GROUP BY customer_state "
        "HAVING COUNT(*) >= 100 ORDER BY delay_rate_pct DESC",
    )
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.barh(df["customer_state"][::-1], df["delay_rate_pct"][::-1], color="#dd8452")
    ax.set_title("Delivery Delay Rate by State (orders >= 100)")
    ax.set_xlabel("Delay Rate (%)")
    _save(fig, out_dir, "10_state_delay_rate.png")


# ---------- 11 各类别延迟率 ----------
def fig11_category_delay_rate(config: dict, out_dir: Path) -> None:
    df = q(
        config,
        "SELECT main_category, COUNT(*) AS orders, "
        "ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) AS delay_rate_pct "
        "FROM mart_delivery_sample WHERE main_category IS NOT NULL "
        "GROUP BY main_category HAVING COUNT(*) >= 100 "
        "ORDER BY delay_rate_pct DESC LIMIT 15",
    )
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(df["main_category"][::-1], df["delay_rate_pct"][::-1], color="#c44e52")
    ax.set_title("Delivery Delay Rate by Category (Top 15, orders >= 100)")
    ax.set_xlabel("Delay Rate (%)")
    _save(fig, out_dir, "11_category_delay_rate.png")


# ---------- 12 高价值流失客户画像 ----------
def fig12_high_value_churn_profile(config: dict, out_dir: Path) -> None:
    hv_where = "s.value_segment = 'high_value' AND s.lifecycle_stage = 'churned'"
    overview = q(
        config,
        "SELECT COUNT(*) AS customers, ROUND(SUM(cf.total_payment), 0) AS total_payment, "
        "ROUND(AVG(cf.average_order_value), 2) AS avg_aov, "
        "ROUND(AVG(cf.average_review_score), 2) AS avg_review_score, "
        "ROUND(AVG(cf.delayed_order_rate) * 100, 2) AS avg_delay_rate_pct "
        "FROM mart_customer_features cf "
        f"JOIN dim_customer_segment s USING (customer_unique_id) WHERE {hv_where}",
    )
    totals = q(
        config,
        "SELECT COUNT(*) AS all_customers, ROUND(SUM(total_payment), 0) AS all_payment "
        "FROM mart_customer_features",
    )
    top_cat = q(
        config,
        "SELECT cf.favorite_category, COUNT(*) AS cnt FROM mart_customer_features cf "
        "JOIN dim_customer_segment s USING (customer_unique_id) "
        f"WHERE {hv_where} AND cf.favorite_category IS NOT NULL "
        "GROUP BY cf.favorite_category ORDER BY cnt DESC LIMIT 5",
    )
    top_state = q(
        config,
        "SELECT cf.customer_state, COUNT(*) AS cnt FROM mart_customer_features cf "
        "JOIN dim_customer_segment s USING (customer_unique_id) "
        f"WHERE {hv_where} "
        "GROUP BY cf.customer_state ORDER BY cnt DESC LIMIT 5",
    )

    hv = overview.iloc[0]
    all_row = totals.iloc[0]
    cust_share = hv["customers"] / all_row["all_customers"] * 100
    pay_share = hv["total_payment"] / all_row["all_payment"] * 100

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    # a) 人数与收入占比
    ax = axes[0][0]
    ax.bar(["Customer %", "Revenue %"], [cust_share, pay_share], color=["#4c72b0", "#c44e52"])
    ax.set_title(f"High-value Churned Share (n={int(hv['customers']):,})")
    ax.set_ylabel("% of All Customers / Revenue")
    for i, v in enumerate([cust_share, pay_share]):
        ax.text(i, v + 0.3, f"{v:.1f}%", ha="center")
    # b) Top 类别
    ax = axes[0][1]
    ax.barh(top_cat["favorite_category"][::-1], top_cat["cnt"][::-1], color="#55a868")
    ax.set_title("Top 5 Favorite Categories")
    ax.set_xlabel("Customer Count")
    # c) Top 州
    ax = axes[1][0]
    ax.bar(top_state["customer_state"], top_state["cnt"], color="#ccb974")
    ax.set_title("Top 5 States")
    ax.set_ylabel("Customer Count")
    # d) 体验指标
    ax = axes[1][1]
    labels = ["Avg AOV (BRL)", "Avg Review Score", "Avg Delay Rate (%)"]
    values = [hv["avg_aov"], hv["avg_review_score"], hv["avg_delay_rate_pct"]]
    ax.bar(labels, values, color="#8172b3")
    ax.set_title("Experience Metrics")
    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.02, f"{v:.2f}", ha="center")
    fig.suptitle(
        f"High-value Churned Customer Profile (value=high & lifecycle=churned; "
        f"historical payment {hv['total_payment']:,.0f} BRL)",
        y=1.00,
    )
    _save(fig, out_dir, "12_high_value_churn_profile.png")


def main() -> int:
    """生成全部 12 张图。"""
    setup_logging()
    config = load_config()
    out_dir = get_path(config, "output_figures_dir", ensure_exists=True)

    builders = [
        fig01_order_status,
        fig02_monthly_orders_revenue,
        fig03_one_time_vs_repeat,
        fig04_value_distribution,
        fig05_segment_distribution,
        fig06_cohort_heatmap,
        fig07_m1_trend,
        fig08_on_time_vs_delayed,
        fig09_delay_bucket_score,
        fig10_state_delay_rate,
        fig11_category_delay_rate,
        fig12_high_value_churn_profile,
    ]
    for fn in builders:
        try:
            fn(config, out_dir)
        except Exception as exc:
            logger.error("%s 生成失败：%s", fn.__name__, exc)
            raise
    logger.info("全部 %d 张图表生成完成。", len(builders))
    return 0


if __name__ == "__main__":
    sys.exit(main())
