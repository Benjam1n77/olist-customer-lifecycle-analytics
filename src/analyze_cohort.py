"""Cohort 留存分析导出与可视化模块。

职责：
1. 从 MySQL 读取 cohort_retention_long（由 sql/10_cohort_retention.sql 构建）；
2. 导出长表 CSV 与留存矩阵 CSV 至 outputs/tables/；
3. 绘制 Cohort 留存热力图至 outputs/figures/；
4. 输出成熟 Cohort 的 M1/M2/M3 汇总。

口径说明：
- 观察窗口截断已在 SQL 层处理（不可观察的格子不存在行，绝不以 0 填充）；
- 首购在不完整观察月（2018-08）的客户不进入 Cohort（无法观察 M0）。

使用方式：
    python -m src.analyze_cohort
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面环境下绘图

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("analyze_cohort")


def load_retention(config: dict) -> pd.DataFrame:
    """从 MySQL 读取 Cohort 留存长表。

    Args:
        config: 完整项目配置字典。

    Returns:
        留存长表 DataFrame（cohort_month, activity_month, month_index,
        cohort_size, retained_customers, retention_rate）。
    """
    db = get_database_config(config)
    engine = create_engine(db.to_sqlalchemy_url())
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(
                    "SELECT cohort_month, activity_month, month_index, "
                    "cohort_size, retained_customers, retention_rate "
                    "FROM cohort_retention_long "
                    "ORDER BY cohort_month, month_index"
                ),
                conn,
            )
    except Exception as exc:
        logger.error("读取 cohort_retention_long 失败：%s", exc)
        raise
    finally:
        engine.dispose()
    logger.info("读取留存长表 %d 行", len(df))
    return df


def export_long_csv(df: pd.DataFrame, out_dir: Path) -> Path:
    """导出留存长表 CSV（含百分比列）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cohort_retention_long.csv"
    export = df.copy()
    export["retention_pct"] = (export["retention_rate"] * 100).round(2)
    export.to_csv(out_path, index=False)
    logger.info("已导出：%s（%d 行）", out_path, len(export))
    return out_path


def export_matrix_csv(df: pd.DataFrame, out_dir: Path) -> Path:
    """导出留存矩阵 CSV：行=Cohort 月份，列=month_index，值=留存率%。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cohort_retention_matrix.csv"
    matrix = df.pivot_table(
        index="cohort_month",
        columns="month_index",
        values="retention_rate",
        aggfunc="first",
    )
    matrix = (matrix * 100).round(2)
    matrix.columns = [f"M{c}" for c in matrix.columns]
    matrix.index.name = "cohort_month"
    matrix.to_csv(out_path)
    logger.info("已导出：%s（%d 个 Cohort）", out_path, len(matrix))
    return out_path


def plot_heatmap(df: pd.DataFrame, out_dir: Path) -> Path:
    """绘制 Cohort 留存热力图（英文标签避免字体问题）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "06_cohort_retention_heatmap.png"

    matrix = df.pivot_table(
        index="cohort_month",
        columns="month_index",
        values="retention_rate",
        aggfunc="first",
    )
    matrix = matrix * 100
    matrix.columns = [f"M{c}" for c in matrix.columns]
    # Cohort 标签简化为 YYYY-MM
    matrix.index = [str(m)[:7] for m in matrix.index]

    fig, ax = plt.subplots(figsize=(14, 9))
    sns.heatmap(
        matrix,
        ax=ax,
        cmap="YlGnBu",
        annot=False,
        fmt=".1f",
        linewidths=0.3,
        cbar_kws={"label": "Retention Rate (%)"},
    )
    ax.set_title(
        "Olist Cohort Retention Heatmap (delivered orders, "
        "unobservable cells left blank)",
        fontsize=13,
    )
    ax.set_xlabel("Months Since First Purchase")
    ax.set_ylabel("Cohort Month (First Purchase)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("已保存热力图：%s", out_path)
    return out_path


def summarize_mature_retention(df: pd.DataFrame) -> pd.DataFrame:
    """汇总成熟 Cohort 的 M1/M2/M3 留存率。

    表中行存在即代表该 ``month_index`` 可观察（不可观察格子无行）。
    对外 M1 KPI 使用客户数加权口径：``SUM(retained_customers) /
    SUM(cohort_size)``；M2/M3 继续沿用成熟 Cohort 留存率的简单平均。
    Cohort 明细行及每行 ``retention_rate`` 不作任何改写。
    """
    records: list[dict] = []
    mature = df[df["month_index"].between(1, 3)]

    for month_index, group in mature.groupby("month_index", sort=True):
        if month_index == 1:
            denominator = group["cohort_size"].sum()
            if denominator <= 0:
                raise ValueError("M1 Cohort Size 合计必须大于 0")
            retention_pct = round(
                group["retained_customers"].sum() / denominator * 100,
                2,
            )
            aggregation_method = "weighted_customer_rate"
        else:
            retention_pct = round(group["retention_rate"].mean() * 100, 2)
            aggregation_method = "simple_cohort_average"

        records.append(
            {
                "month_index": month_index,
                "mature_cohorts": group["cohort_month"].nunique(),
                "retention_pct": retention_pct,
                "aggregation_method": aggregation_method,
                "earliest_cohort": group["cohort_month"].min(),
                "latest_cohort": group["cohort_month"].max(),
            }
        )

    return pd.DataFrame(records)


def main() -> int:
    """Cohort 留存导出与绘图入口。"""
    setup_logging()
    config = load_config()

    df = load_retention(config)
    if df.empty:
        logger.error("cohort_retention_long 为空，请先执行 sql/10_cohort_retention.sql")
        return 1

    tables_dir = get_path(config, "output_tables_dir", ensure_exists=True)
    figures_dir = get_path(config, "output_figures_dir", ensure_exists=True)

    export_long_csv(df, tables_dir)
    export_matrix_csv(df, tables_dir)
    plot_heatmap(df, figures_dir)

    summary = summarize_mature_retention(df)
    logger.info("成熟 Cohort 留存汇总：")
    for _, row in summary.iterrows():
        logger.info(
            "  M%d：成熟 Cohort %d 个（%s ~ %s），留存 %.2f%%（%s）",
            row["month_index"],
            row["mature_cohorts"],
            str(row["earliest_cohort"])[:7],
            str(row["latest_cohort"])[:7],
            row["retention_pct"],
            row["aggregation_method"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
