"""首购后 90 天二购驱动因素分析。

分析口径：
1. 客户主体为 ``customer_unique_id``；
2. 首购与二购均限定为 delivered 订单；
3. 二购必须发生在首购后的另一个自然日，排除同日拆单/同次会话；
4. 仅保留从首购日期到 analysis_date 已满 90 天的成熟样本；
5. 结果变量为首购后第 1–90 天是否出现第二笔 delivered 订单；
6. 特征只来自首单，购买时特征与首单履约后体验特征分两层模型；
7. 回归结果只解释为关联，不构成因果证据。

产出：
- outputs/tables/repeat_purchase_90d_overview.csv
- outputs/tables/repeat_purchase_90d_driver_summary.csv
- outputs/tables/repeat_purchase_90d_segment_rates.csv
- outputs/figures/13_repeat_purchase_90d_drivers.png

使用方式：
    python -m src.analyze_repeat_purchase
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("analyze_repeat_purchase")

WINDOW_DAYS = 90
CATEGORY_MIN_CUSTOMERS = 500

FIRST_ORDER_QUERY = """
WITH ranked_orders AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY m.customer_unique_id
            ORDER BY m.purchase_datetime, m.order_id
        ) AS order_rank
    FROM mart_order_summary m
    WHERE m.order_status = 'delivered'
),
first_orders AS (
    SELECT *
    FROM ranked_orders
    WHERE order_rank = 1
),
second_later_orders AS (
    SELECT
        f.customer_unique_id,
        MIN(m.purchase_datetime) AS second_purchase_datetime
    FROM first_orders f
    INNER JOIN mart_order_summary m
        ON m.customer_unique_id = f.customer_unique_id
       AND m.order_status = 'delivered'
       AND m.purchase_date > f.purchase_date
    GROUP BY f.customer_unique_id
),
analysis_window AS (
    SELECT DATE_ADD(MAX(purchase_date), INTERVAL 1 DAY) AS analysis_date
    FROM mart_order_summary
    WHERE order_status = 'delivered'
)
SELECT
    f.customer_unique_id,
    f.order_id AS first_order_id,
    f.purchase_datetime AS first_purchase_datetime,
    f.purchase_date AS first_purchase_date,
    s.second_purchase_datetime,
    w.analysis_date,
    f.customer_state,
    f.main_category,
    f.main_payment_type,
    f.payment_amount,
    f.item_amount,
    f.freight_amount,
    f.item_count,
    f.seller_count,
    f.max_installments,
    f.is_delayed,
    f.review_score,
    f.has_review_comment
FROM first_orders f
LEFT JOIN second_later_orders s
    ON s.customer_unique_id = f.customer_unique_id
CROSS JOIN analysis_window w
WHERE DATEDIFF(w.analysis_date, f.purchase_date) >= :window_days
ORDER BY f.customer_unique_id
"""


def is_mature_first_purchase(
    first_purchase: date, analysis_date: date, window_days: int = WINDOW_DAYS
) -> bool:
    """判断首购是否拥有完整观察窗口。"""
    return analysis_date - first_purchase >= timedelta(days=window_days)


def is_repeat_within_window(
    first_purchase: datetime,
    second_purchase: datetime | None,
    window_days: int = WINDOW_DAYS,
) -> bool:
    """判断跨自然日二购是否发生在首购后第 1–window_days 天。"""
    if second_purchase is None or pd.isna(second_purchase):
        return False
    elapsed_days = (second_purchase.date() - first_purchase.date()).days
    return 1 <= elapsed_days <= window_days


def load_first_order_sample(config: dict) -> pd.DataFrame:
    """从订单宽表读取成熟首购客户及首单特征。"""
    db = get_database_config(config)
    engine = create_engine(db.to_sqlalchemy_url())
    try:
        with engine.connect() as conn:
            sample = pd.read_sql(
                text(FIRST_ORDER_QUERY),
                conn,
                params={"window_days": WINDOW_DAYS},
            )
    finally:
        engine.dispose()
    logger.info("读取成熟首购客户 %d 人", len(sample))
    return sample


def prepare_model_sample(raw: pd.DataFrame) -> pd.DataFrame:
    """生成回归需要的无泄漏首单特征与 90 天二购标签。"""
    if raw.empty:
        raise ValueError("成熟首购样本为空")
    if raw["customer_unique_id"].duplicated().any():
        raise ValueError("首购样本不是一人一行")

    sample = raw.copy()
    for column in (
        "first_purchase_datetime",
        "second_purchase_datetime",
        "analysis_date",
    ):
        sample[column] = pd.to_datetime(sample[column])

    sample["repeat_90d"] = [
        int(is_repeat_within_window(first, second))
        for first, second in zip(
            sample["first_purchase_datetime"],
            sample["second_purchase_datetime"],
        )
    ]
    sample["days_to_second_purchase"] = (
        sample["second_purchase_datetime"] - sample["first_purchase_datetime"]
    ).dt.total_seconds() / 86400
    sample["calendar_days_to_second_purchase"] = (
        sample["second_purchase_datetime"].dt.normalize()
        - sample["first_purchase_datetime"].dt.normalize()
    ).dt.days
    sample.loc[sample["repeat_90d"] == 0, "days_to_second_purchase"] = np.nan
    sample.loc[
        sample["repeat_90d"] == 0, "calendar_days_to_second_purchase"
    ] = np.nan

    numeric_columns = (
        "payment_amount",
        "item_amount",
        "freight_amount",
        "item_count",
        "seller_count",
        "max_installments",
        "is_delayed",
        "review_score",
        "has_review_comment",
    )
    for column in numeric_columns:
        sample[column] = pd.to_numeric(sample[column], errors="coerce")

    sample["payment_amount"] = sample["payment_amount"].fillna(0).clip(lower=0)
    sample["log2_payment_amount"] = np.log2(sample["payment_amount"] + 1)

    freight_share = sample["freight_amount"] / sample["item_amount"]
    freight_share = freight_share.replace([np.inf, -np.inf], np.nan)
    sample["freight_share_missing"] = freight_share.isna().astype(int)
    sample["freight_share_10pp"] = (freight_share / 0.10).fillna(
        freight_share.median() / 0.10
    )

    sample["multi_item"] = (sample["item_count"].fillna(0) >= 2).astype(int)
    sample["multi_seller"] = (sample["seller_count"].fillna(0) >= 2).astype(int)
    sample["installment_user"] = (
        sample["max_installments"].fillna(0) > 1
    ).astype(int)

    sample["delivery_status_missing"] = sample["is_delayed"].isna().astype(int)
    sample["is_delayed"] = sample["is_delayed"].fillna(0).astype(int)
    sample["review_missing"] = sample["review_score"].isna().astype(int)
    sample["low_score"] = (sample["review_score"].fillna(5) <= 2).astype(int)

    sample["customer_state_group"] = sample["customer_state"].fillna("unknown")
    sample["main_category"] = sample["main_category"].fillna("unknown")
    category_counts = sample["main_category"].value_counts()
    retained_categories = set(
        category_counts[category_counts >= CATEGORY_MIN_CUSTOMERS].index
    )
    sample["category_group"] = sample["main_category"].where(
        sample["main_category"].isin(retained_categories), "other"
    )
    sample["cohort_month"] = sample["first_purchase_datetime"].dt.strftime("%Y-%m")

    sample["delivery_status"] = np.select(
        [
            sample["delivery_status_missing"] == 1,
            sample["is_delayed"] == 1,
        ],
        ["unknown", "delayed"],
        default="on_time",
    )
    sample["review_group"] = np.select(
        [
            sample["review_missing"] == 1,
            sample["review_score"].between(1, 2),
            sample["review_score"] == 3,
        ],
        ["missing", "low_1_2", "neutral_3"],
        default="high_4_5",
    )
    sample["payment_type"] = sample["main_payment_type"].fillna("unknown")
    sample["installment_flag"] = sample["installment_user"].map(
        {0: "single_payment", 1: "installment"}
    )
    sample["item_count_group"] = sample["multi_item"].map(
        {0: "single_item", 1: "multi_item"}
    )
    sample["seller_count_group"] = sample["multi_seller"].map(
        {0: "single_seller", 1: "multi_seller"}
    )
    sample["order_value_quartile"] = pd.qcut(
        sample["payment_amount"],
        q=4,
        labels=["Q1_low", "Q2", "Q3", "Q4_high"],
        duplicates="drop",
    ).astype(str)

    if not sample["repeat_90d"].isin([0, 1]).all():
        raise ValueError("二购标签不是二元变量")
    if (sample.loc[sample["repeat_90d"] == 1, "days_to_second_purchase"] < 0).any():
        raise ValueError("出现首购之前的第二笔订单")
    if (
        sample.loc[
            sample["repeat_90d"] == 1, "calendar_days_to_second_purchase"
        ]
        > WINDOW_DAYS
    ).any():
        raise ValueError("二购标签包含超过 90 天的订单")
    return sample


def fit_driver_models(sample: pd.DataFrame) -> dict[str, object]:
    """拟合购买时特征模型和首单体验完整样本模型。"""
    controls = (
        "C(customer_state_group) + C(category_group) + C(cohort_month)"
    )
    purchase_candidates = [
        "log2_payment_amount",
        "freight_share_10pp",
        "freight_share_missing",
        "multi_item",
        "multi_seller",
        "installment_user",
    ]
    experience_candidates = ["is_delayed", "low_score"]
    # 缺失指示变量在当前真实样本中可能全为 0。常量列与截距完全共线，
    # 应在拟合前剔除；这不改变指标口径，只避免奇异设计矩阵。
    purchase_terms = " + ".join(
        term for term in purchase_candidates if sample[term].nunique() > 1
    )
    experience_sample = sample[
        (sample["delivery_status_missing"] == 0)
        & (sample["review_missing"] == 0)
    ].copy()
    if experience_sample.empty:
        raise ValueError("首单配送与评价体验完整样本为空")
    experience_terms = " + ".join(
        term
        for term in experience_candidates
        if experience_sample[term].nunique() > 1
    )
    purchase_formula = f"repeat_90d ~ {purchase_terms} + {controls}"
    experience_formula = (
        f"repeat_90d ~ {purchase_terms} + {experience_terms} + {controls}"
    )

    models = {
        "purchase_time": smf.glm(
            formula=purchase_formula,
            data=sample,
            family=sm.families.Binomial(),
        ).fit(cov_type="HC1"),
        "first_order_experience": smf.glm(
            formula=experience_formula,
            data=experience_sample,
            family=sm.families.Binomial(),
        ).fit(cov_type="HC1"),
    }
    return models


DRIVER_LABELS = {
    "log2_payment_amount": "首单支付金额翻倍",
    "freight_share_10pp": "运费占比增加 10 个百分点",
    "multi_item": "首单包含多个商品",
    "multi_seller": "首单包含多个卖家",
    "installment_user": "首单使用分期付款",
    "is_delayed": "首单配送延迟",
    "low_score": "首单低评分（1–2 分）",
}

DRIVER_PLOT_LABELS = {
    "log2_payment_amount": "First-order payment amount doubles",
    "freight_share_10pp": "Freight share +10 percentage points",
    "multi_item": "Multiple items in first order",
    "multi_seller": "Multiple sellers in first order",
    "installment_user": "Installment payment on first order",
    "is_delayed": "First-order delivery delayed",
    "low_score": "Low first-order review score (1-2)",
}


def extract_driver_summary(models: dict[str, object]) -> pd.DataFrame:
    """提取核心首单变量的调整后赔率比和稳健置信区间。"""
    rows: list[dict[str, object]] = []
    for model_name, model in models.items():
        terms = list(DRIVER_LABELS)
        if model_name == "purchase_time":
            terms = [term for term in terms if term not in {"is_delayed", "low_score"}]
        conf = model.conf_int()
        for term in terms:
            coefficient = float(model.params[term])
            odds_ratio = float(np.exp(coefficient))
            ci_low = float(np.exp(conf.loc[term, 0]))
            ci_high = float(np.exp(conf.loc[term, 1]))
            p_value = float(model.pvalues[term])
            if p_value >= 0.05:
                direction = "未发现显著关联"
            elif odds_ratio > 1:
                direction = "正向关联"
            else:
                direction = "负向关联"
            rows.append(
                {
                    "model": model_name,
                    "driver": term,
                    "driver_label": DRIVER_LABELS[term],
                    "odds_ratio": round(odds_ratio, 4),
                    "ci_95_low": round(ci_low, 4),
                    "ci_95_high": round(ci_high, 4),
                    "p_value": p_value,
                    "direction": direction,
                    "n_obs": int(model.nobs),
                    "aic": round(float(model.aic), 2),
                    "interpretation_scope": (
                        "首购时可见特征的调整后关联"
                        if model_name == "purchase_time"
                        else "加入首单履约与评价体验后的调整后关联"
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_segment_rates(sample: pd.DataFrame) -> pd.DataFrame:
    """汇总不同首单特征组的实际 90 天二购率。"""
    dimensions = {
        "overall": pd.Series("all", index=sample.index),
        "delivery_status": sample["delivery_status"],
        "review_group": sample["review_group"],
        "payment_type": sample["payment_type"],
        "installment_flag": sample["installment_flag"],
        "order_value_quartile": sample["order_value_quartile"],
        "item_count_group": sample["item_count_group"],
        "seller_count_group": sample["seller_count_group"],
        "category_group": sample["category_group"],
    }
    outputs: list[pd.DataFrame] = []
    total = len(sample)
    for dimension, groups in dimensions.items():
        frame = pd.DataFrame({"group": groups, "repeat_90d": sample["repeat_90d"]})
        summary = (
            frame.groupby("group", dropna=False)["repeat_90d"]
            .agg(customer_count="size", repeat_customers_90d="sum")
            .reset_index()
        )
        summary.insert(0, "dimension", dimension)
        summary["repeat_rate_90d_pct"] = (
            summary["repeat_customers_90d"] / summary["customer_count"] * 100
        ).round(4)
        summary["sample_share_pct"] = (
            summary["customer_count"] / total * 100
        ).round(4)
        outputs.append(summary)
    return pd.concat(outputs, ignore_index=True)


def build_overview(sample: pd.DataFrame, models: dict[str, object]) -> pd.DataFrame:
    """生成可直接引用的分析概览指标。"""
    repeat_days = sample.loc[sample["repeat_90d"] == 1, "days_to_second_purchase"]
    analysis_date = sample["analysis_date"].iloc[0].date().isoformat()
    cutoff_date = (
        sample["analysis_date"].iloc[0].date() - timedelta(days=WINDOW_DAYS)
    ).isoformat()
    metrics: list[dict[str, object]] = [
        {
            "metric": "analysis_date",
            "value": analysis_date,
            "unit": "date",
            "definition": "最大有效购买日期 + 1 天",
        },
        {
            "metric": "mature_first_purchase_cutoff",
            "value": cutoff_date,
            "unit": "date",
            "definition": "首购日期不晚于该日，保证 90 天观察窗口",
        },
        {
            "metric": "eligible_customers",
            "value": int(len(sample)),
            "unit": "customers",
            "definition": "拥有完整 90 天观察窗口的首购客户",
        },
        {
            "metric": "repeat_customers_90d",
            "value": int(sample["repeat_90d"].sum()),
            "unit": "customers",
            "definition": "首购后第 1–90 个自然日出现下一笔 delivered 订单的客户",
        },
        {
            "metric": "repeat_rate_90d_pct",
            "value": round(float(sample["repeat_90d"].mean() * 100), 4),
            "unit": "percent",
            "definition": "跨自然日 repeat_customers_90d / eligible_customers",
        },
        {
            "metric": "median_days_to_second_purchase",
            "value": round(float(repeat_days.median()), 2),
            "unit": "days",
            "definition": "第 1–90 天完成二购客户的首购至二购实际间隔中位数",
        },
    ]
    for model_name, model in models.items():
        metrics.extend(
            [
                {
                    "metric": f"{model_name}_n_obs",
                    "value": int(model.nobs),
                    "unit": "customers",
                    "definition": "逻辑回归样本量",
                },
                {
                    "metric": f"{model_name}_aic",
                    "value": round(float(model.aic), 2),
                    "unit": "aic",
                    "definition": "模型 AIC，仅用于同一样本模型间相对比较",
                },
            ]
        )
    overview = pd.DataFrame(metrics)
    overview["source"] = "mart_order_summary / Python statsmodels GLM"
    return overview


def plot_driver_odds_ratios(driver_summary: pd.DataFrame, out_dir: Path) -> Path:
    """绘制扩展模型中核心首单驱动因素的调整后赔率比。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "13_repeat_purchase_90d_drivers.png"
    plot_df = driver_summary[
        driver_summary["model"] == "first_order_experience"
    ].copy()
    plot_df = plot_df.iloc[::-1]

    fig, axis = plt.subplots(figsize=(11, 6.5))
    y_positions = np.arange(len(plot_df))
    axis.errorbar(
        plot_df["odds_ratio"],
        y_positions,
        xerr=np.vstack(
            [
                plot_df["odds_ratio"] - plot_df["ci_95_low"],
                plot_df["ci_95_high"] - plot_df["odds_ratio"],
            ]
        ),
        fmt="o",
        color="#2F6B9A",
        ecolor="#90A4AE",
        capsize=4,
        markersize=7,
    )
    axis.axvline(1, color="#E76F51", linewidth=1.4, linestyle="--")
    axis.set_yticks(
        y_positions,
        plot_df["driver"].map(DRIVER_PLOT_LABELS),
    )
    axis.set_xscale("log")
    axis.set_xlabel("Adjusted odds ratio (log scale, 95% robust CI)")
    axis.set_title(
        "First-order factors associated with a repeat purchase within 90 days",
        fontsize=13,
        fontweight="bold",
    )
    axis.grid(axis="x", alpha=0.25)
    for y_position, (_, row) in zip(y_positions, plot_df.iterrows()):
        axis.annotate(
            f"OR {row['odds_ratio']:.2f}",
            (row["ci_95_high"], y_position),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    axis.text(
        0,
        -0.18,
        "Controls: customer state, product category and first-purchase cohort. "
        "Associations are not causal effects.",
        transform=axis.transAxes,
        fontsize=9,
        color="#607D8B",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    logger.info("已保存二购驱动因素图：%s", out_path)
    return out_path


def export_results(
    overview: pd.DataFrame,
    driver_summary: pd.DataFrame,
    segment_rates: pd.DataFrame,
    out_dir: Path,
) -> list[Path]:
    """导出三张汇总 CSV，不导出客户级明细。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "repeat_purchase_90d_overview.csv": overview,
        "repeat_purchase_90d_driver_summary.csv": driver_summary,
        "repeat_purchase_90d_segment_rates.csv": segment_rates,
    }
    paths: list[Path] = []
    for name, frame in outputs.items():
        path = out_dir / name
        frame.to_csv(path, index=False)
        paths.append(path)
        logger.info("已导出：%s（%d 行）", path, len(frame))
    return paths


def main() -> int:
    """运行首购后 90 天二购驱动因素分析。"""
    setup_logging()
    config = load_config()
    raw = load_first_order_sample(config)
    sample = prepare_model_sample(raw)
    models = fit_driver_models(sample)
    driver_summary = extract_driver_summary(models)
    segment_rates = summarize_segment_rates(sample)
    overview = build_overview(sample, models)

    tables_dir = get_path(config, "output_tables_dir", ensure_exists=True)
    figures_dir = get_path(config, "output_figures_dir", ensure_exists=True)
    export_results(overview, driver_summary, segment_rates, tables_dir)
    plot_driver_odds_ratios(driver_summary, figures_dir)

    logger.info(
        "90 天二购分析完成：成熟客户 %d 人，二购 %d 人，二购率 %.4f%%",
        len(sample),
        int(sample["repeat_90d"].sum()),
        sample["repeat_90d"].mean() * 100,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
