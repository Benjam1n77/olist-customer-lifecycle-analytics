"""履约体验统计检验模块。

职责：
1. 从 mart_delivery_sample 读取订单级样本；
2. 独立计算准时/延迟评分对比（与 SQL 交叉验证）；
3. 卡方检验：延迟与否 × 低评分与否的关联性；
4. Mann–Whitney U 检验：准时组与延迟组评分分布差异（评分为有序分类，
   不满足正态假设，故用非参数检验）；
5. 控制类别/地区/订单金额的逻辑回归（Brief 11.4 可选项）：
   验证排除混淆后延迟与低评分的关联是否依然存在；
6. 导出 outputs/tables/delivery_experience_summary.csv。

结论表述约束（Brief 11.4）：
只能说"配送延迟与较低评分显著相关"，不得断言因果——
观察性数据无法排除混淆因素（如偏远地区同时导致延迟与商品结构差异）。

使用方式：
    python -m src.analyze_delivery
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text

from src.config import get_database_config, get_path, load_config, setup_logging

logger = logging.getLogger("analyze_delivery")


def load_sample(config: dict) -> pd.DataFrame:
    """读取履约分析样本表。"""
    db = get_database_config(config)
    engine = create_engine(db.to_sqlalchemy_url())
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text(
                    "SELECT order_id, customer_state, main_category, delay_days, "
                    "is_delayed, delay_bucket, review_score, is_low_score, "
                    "item_amount, is_high_value_customer FROM mart_delivery_sample"
                ),
                conn,
            )
    finally:
        engine.dispose()
    logger.info("读取履约样本 %d 行", len(df))
    return df


def compute_core_metrics(df: pd.DataFrame) -> dict[str, float]:
    """独立计算核心对比指标（与 SQL 交叉验证）。"""
    on_time = df[df["is_delayed"] == 0]["review_score"]
    delayed = df[df["is_delayed"] == 1]["review_score"]
    metrics = {
        "sample_orders": float(len(df)),
        "on_time_orders": float(len(on_time)),
        "delayed_orders": float(len(delayed)),
        "delay_rate_pct": round(len(delayed) / len(df) * 100, 2),
        "on_time_avg_score": round(on_time.mean(), 2),
        "delayed_avg_score": round(delayed.mean(), 2),
        "score_diff": round(on_time.mean() - delayed.mean(), 2),
        "score_drop_pct": round(
            (on_time.mean() - delayed.mean()) / on_time.mean() * 100, 2
        ),
    }
    return metrics


def chi_square_test(df: pd.DataFrame) -> dict[str, float]:
    """卡方检验：延迟与否 × 低评分与否。"""
    contingency = pd.crosstab(df["is_delayed"], df["is_low_score"])
    chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
    # Cramér's V 衡量关联强度（2×2 表时等于 phi 系数）
    n = contingency.values.sum()
    cramers_v = (chi2 / n) ** 0.5
    return {
        "chi2": round(float(chi2), 2),
        "p_value": float(p_value),
        "dof": int(dof),
        "cramers_v": round(float(cramers_v), 4),
    }


def mann_whitney_test(df: pd.DataFrame) -> dict[str, float]:
    """Mann–Whitney U 检验：准时组 vs 延迟组评分分布。"""
    on_time = df[df["is_delayed"] == 0]["review_score"]
    delayed = df[df["is_delayed"] == 1]["review_score"]
    u_stat, p_value = stats.mannwhitneyu(
        on_time, delayed, alternative="two-sided"
    )
    return {"u_statistic": float(u_stat), "p_value": float(p_value)}


def logistic_regression_controlled(df: pd.DataFrame) -> dict[str, float]:
    """控制类别/地区/订单金额后的逻辑回归。

    模型：is_low_score ~ is_delayed + ln(item_amount+1) + state + main_category

    目的：排除混淆因素后验证延迟与低评分的关联是否依然存在。
    注意：回归系数仍只体现统计关联，不构成因果证据。

    Returns:
        包含延迟变量赔率比（OR）、95% 置信区间、p 值、样本量与伪 R² 的字典。
    """
    import statsmodels.api as sm

    reg_df = df.dropna(subset=["item_amount"]).copy()
    reg_df["log_amount"] = np.log1p(reg_df["item_amount"])
    reg_df["category"] = reg_df["main_category"].fillna("unknown")

    design = pd.get_dummies(
        reg_df[["customer_state", "category"]],
        columns=["customer_state", "category"],
        drop_first=True,
        dtype=float,
    )
    X = pd.concat(
        [reg_df[["is_delayed", "log_amount"]].astype(float), design], axis=1
    )
    X = sm.add_constant(X)
    y = reg_df["is_low_score"].astype(float)

    model = sm.Logit(y, X).fit(method="bfgs", maxiter=200, disp=False)
    coef = model.params["is_delayed"]
    conf = model.conf_int().loc["is_delayed"]
    return {
        "n_obs": int(model.nobs),
        "delay_odds_ratio": round(float(np.exp(coef)), 3),
        "delay_or_ci_low": round(float(np.exp(conf[0])), 3),
        "delay_or_ci_high": round(float(np.exp(conf[1])), 3),
        "delay_p_value": float(model.pvalues["is_delayed"]),
        "pseudo_r_squared": round(float(model.prsquared), 4),
    }


def export_summary(
    metrics: dict, chi2_res: dict, mw_res: dict, logit_res: dict, out_dir: Path
) -> Path:
    """导出汇总 CSV（一行一个指标，便于阅读与引用）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "delivery_experience_summary.csv"

    rows = [{"metric": k, "value": v, "source": "python"} for k, v in metrics.items()]
    rows += [
        {
            "metric": f"chi_square_{k}",
            "value": v,
            "source": "scipy.stats.chi2_contingency",
        }
        for k, v in chi2_res.items()
    ]
    rows += [
        {
            "metric": f"mann_whitney_{k}",
            "value": v,
            "source": "scipy.stats.mannwhitneyu",
        }
        for k, v in mw_res.items()
    ]
    rows += [
        {
            "metric": f"logit_controlled_{k}",
            "value": v,
            "source": "statsmodels.Logit（控制州/类别/金额）",
        }
        for k, v in logit_res.items()
    ]
    rows.append(
        {
            "metric": "conclusion",
            "value": "配送延迟与较低评分显著相关（观察性数据，不构成因果证据）",
            "source": "-",
        }
    )

    pd.DataFrame(rows).to_csv(out_path, index=False)
    logger.info("已导出：%s", out_path)
    return out_path


def main() -> int:
    """履约体验统计检验入口。"""
    setup_logging()
    config = load_config()

    df = load_sample(config)
    if df.empty:
        logger.error("mart_delivery_sample 为空，请先执行 sql/11_delivery_experience.sql")
        return 1

    metrics = compute_core_metrics(df)
    logger.info(
        "Python 端核心指标：准时均分 %.2f / 延迟均分 %.2f / 下降 %.2f%%",
        metrics["on_time_avg_score"],
        metrics["delayed_avg_score"],
        metrics["score_drop_pct"],
    )

    chi2_res = chi_square_test(df)
    logger.info(
        "卡方检验：chi2=%.2f, p=%.3e, Cramér's V=%.4f（%s）",
        chi2_res["chi2"],
        chi2_res["p_value"],
        chi2_res["cramers_v"],
        "显著相关" if chi2_res["p_value"] < 0.05 else "不显著",
    )

    mw_res = mann_whitney_test(df)
    logger.info(
        "Mann–Whitney U：U=%.0f, p=%.3e（%s）",
        mw_res["u_statistic"],
        mw_res["p_value"],
        "评分分布显著不同" if mw_res["p_value"] < 0.05 else "无显著差异",
    )

    logit_res = logistic_regression_controlled(df)
    logger.info(
        "控制类别/地区/金额后逻辑回归：延迟 OR=%.3f（95%% CI %.3f–%.3f），p=%.3e，伪R²=%.4f（%s）",
        logit_res["delay_odds_ratio"],
        logit_res["delay_or_ci_low"],
        logit_res["delay_or_ci_high"],
        logit_res["delay_p_value"],
        logit_res["pseudo_r_squared"],
        "控制混淆后关联仍显著" if logit_res["delay_p_value"] < 0.05 else "控制后不再显著",
    )

    tables_dir = get_path(config, "output_tables_dir", ensure_exists=True)
    export_summary(metrics, chi2_res, mw_res, logit_res, tables_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
