"""Olist 客户生命周期分析流水线入口。

按阶段执行数据导入、质量校验、宽表建模、客户分析与结果导出。各阶段的
实现均在 ``src/`` 或 ``sql/`` 中，可通过 ``--list-stages`` 查看。

用法：
    python run_pipeline.py --check-config      # 校验配置与数据目录
    python run_pipeline.py --list-stages       # 查看阶段定义
    python run_pipeline.py --stage <name>      # 运行指定阶段
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from typing import Callable

from src.config import (
    PROJECT_ROOT,
    get_database_config,
    get_path,
    load_config,
    setup_logging,
)

logger = logging.getLogger("run_pipeline")

from src import load_data


def _run_sql_files(*files: str) -> None:
    """依次执行 sql/ 下的脚本（依赖 mysql CLI 与 config 中的连接信息）。"""
    from src.config import get_database_config, get_path, load_config

    config = load_config()
    db = get_database_config(config)
    sql_dir = get_path(config, "sql_dir")
    for name in files:
        sql_path = sql_dir / name
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL 文件不存在：{sql_path}")
        mysql_env = os.environ.copy()
        mysql_env["MYSQL_PWD"] = db.password
        with sql_path.open("r", encoding="utf-8") as fh:
            result = subprocess.run(
                [
                    "mysql",
                    f"--host={db.host}",
                    f"--port={db.port}",
                    f"--user={db.user}",
                    db.database,
                ],
                stdin=fh,
                capture_output=True,
                text=True,
                env=mysql_env,
            )
        if result.returncode != 0:
            raise RuntimeError(f"执行 {name} 失败：{result.stderr}")
        print(result.stdout)


def run_build_order_mart() -> None:
    """构建三张订单级聚合表与订单宽表。"""
    _run_sql_files(
        "04_order_item_aggregation.sql",
        "05_payment_aggregation.sql",
        "06_review_aggregation.sql",
        "07_build_order_mart.sql",
    )


def run_build_customer_mart() -> None:
    """基于订单宽表构建客户粒度特征宽表。"""
    _run_sql_files("08_build_customer_feature_mart.sql")


def run_segmentation() -> None:
    """基于客户特征构建 RFM 与多维标签分层。"""
    _run_sql_files("09_customer_segmentation.sql")


def run_cohort() -> None:
    """计算 Cohort 留存，并导出 CSV 与热力图。"""
    _run_sql_files("10_cohort_retention.sql")
    from src import analyze_cohort

    rc = analyze_cohort.main()
    if rc != 0:
        raise RuntimeError("analyze_cohort 执行失败")


def run_delivery() -> None:
    """执行履约体验聚合与统计检验。"""
    _run_sql_files("11_delivery_experience.sql")
    from src import analyze_delivery

    rc = analyze_delivery.main()
    if rc != 0:
        raise RuntimeError("analyze_delivery 执行失败")


def run_repeat_purchase_90d() -> None:
    """首购后 90 天二购驱动因素分析（依赖订单宽表）。"""
    from src import analyze_repeat_purchase

    rc = analyze_repeat_purchase.main()
    if rc != 0:
        raise RuntimeError("analyze_repeat_purchase 执行失败")


def run_campaign() -> None:
    """按规则级联构建营销人群名单并导出 CSV。"""
    _run_sql_files("12_campaign_target_list.sql")
    from src import export_outputs

    rc = export_outputs.main(["--campaign"])
    if rc != 0:
        raise RuntimeError("export_outputs --campaign 执行失败")


def run_export() -> None:
    """导出 Python 图表、高价值流失名单和 Tableau 数据。"""
    from src import build_visuals, export_outputs

    rc = export_outputs.main(["--churn", "--tableau"])
    if rc != 0:
        raise RuntimeError("export_outputs --churn --tableau 执行失败")
    rc = build_visuals.main()
    if rc != 0:
        raise RuntimeError("build_visuals 执行失败")


def run_validate_data() -> None:
    """数据验证：质量检查 SQL + 10 项一致性验证 + SQL×Python 交叉验证。"""
    _run_sql_files("03_data_quality_checks.sql", "13_validation_queries.sql")
    from src import validate_data

    rc = validate_data.main()
    if rc != 0:
        raise RuntimeError("validate_data 交叉验证存在失败项")

# 阶段注册表：名称 -> 执行函数。尚未实现的阶段值为 None，运行时明确报错。
STAGE_REGISTRY: dict[str, Callable[[], None] | None] = {
    "load_data": lambda: load_data.main(),        # CSV → MySQL 导入
    "validate_data": run_validate_data,           # 质量检查 + 交叉验证
    "build_order_mart": run_build_order_mart,      # 订单粒度宽表
    "build_customer_mart": run_build_customer_mart,  # 用户粒度宽表
    "segmentation": run_segmentation,              # 用户标签与生命周期
    "cohort": run_cohort,                          # Cohort 留存
    "delivery": run_delivery,                      # 履约体验分析
    "repeat_purchase_90d": run_repeat_purchase_90d,  # 首购后 90 天二购驱动
    "campaign": run_campaign,                      # 营销人群名单
    "export": run_export,                          # 图表与 Tableau 输出
}


def check_config() -> int:
    """校验配置与目录就绪状态，返回退出码（0 = 正常）。"""
    config = load_config()
    db_cfg = get_database_config(config)
    logger.info("配置加载成功，数据库连接目标：%s", db_cfg.safe_repr())

    exit_code = 0

    auto_create_keys = {"raw_data_dir", "interim_data_dir", "processed_data_dir"}
    for key in (
        "raw_data_dir",
        "interim_data_dir",
        "processed_data_dir",
        "sql_dir",
        "output_tables_dir",
        "output_figures_dir",
        "output_tableau_dir",
        "output_local_dir",
    ):
        path = get_path(config, key, ensure_exists=key in auto_create_keys)
        status = "存在" if path.exists() else "缺失"
        logger.info("目录 %-22s %s", key + ":", path)
        if not path.exists() and key != "output_local_dir":
            exit_code = 1

    # 检查原始数据文件
    expected_csvs = [
        "olist_customers_dataset.csv",
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv",
        "olist_products_dataset.csv",
        "olist_sellers_dataset.csv",
        "olist_geolocation_dataset.csv",
        "product_category_name_translation.csv",
    ]
    raw_dir = get_path(config, "raw_data_dir")
    missing = [name for name in expected_csvs if not (raw_dir / name).exists()]
    if missing:
        logger.warning(
            "data/raw 缺少 %d 个数据文件（下载方式见 data/README.md）：%s",
            len(missing),
            ", ".join(missing),
        )
    else:
        logger.info("data/raw 中 9 个原始数据文件齐全。")

    return exit_code


def list_stages() -> None:
    """打印所有阶段及其实现状态。"""
    print(f"项目根目录：{PROJECT_ROOT}\n")
    print("阶段列表：")
    for name, func in STAGE_REGISTRY.items():
        status = "已实现" if func is not None else "待实现"
        print(f"  - {name:<20} [{status}]")


def run_stage(stage_name: str) -> int:
    """运行指定阶段；未实现的阶段返回非零退出码。"""
    if stage_name not in STAGE_REGISTRY:
        logger.error("未知阶段：%s。可用阶段见 --list-stages", stage_name)
        return 2
    func = STAGE_REGISTRY[stage_name]
    if func is None:
        logger.error("阶段 %s 尚未实现。", stage_name)
        return 1
    logger.info("开始执行阶段：%s", stage_name)
    func()
    logger.info("阶段 %s 执行完成。", stage_name)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Olist 客户生命周期分析流水线入口",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--check-config", action="store_true", help="校验配置文件与目录/数据就绪状态"
    )
    parser.add_argument(
        "--list-stages", action="store_true", help="列出全部阶段及实现状态"
    )
    parser.add_argument("--stage", type=str, default=None, help="运行指定阶段")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    setup_logging()

    if args.check_config:
        return check_config()
    if args.list_stages:
        list_stages()
        return 0
    if args.stage:
        return run_stage(args.stage)

    logger.info("未指定操作。使用 --check-config / --list-stages / --stage 查看帮助。")
    list_stages()
    return 0


if __name__ == "__main__":
    sys.exit(main())
