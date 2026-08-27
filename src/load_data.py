"""CSV 数据导入 MySQL 模块。

职责：
1. 读取 src/config.py 配置的数据库连接信息与路径；
2. 将 data/raw/ 下的 9 个 CSV 文件分别导入对应 MySQL 表；
3. 支持重复执行（导入前清空目标表）；
4. 导入完成后输出行数校验。

导入策略：
- 使用 LOAD DATA LOCAL INFILE（速度最快）；
- translation.csv 表头无引号（其余 8 个有引号），分别处理；
- order_items / order_payments 存在一单多行，不做去重，由后续 SQL 聚合。

使用方式：
    python -m src.load_data          # 导入全部
    python -m src.load_data customers  # 仅导入 customers 表
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import pymysql
from pymysql.converters import escape_string

# 尝试使用本地 Infile（需要客户端和服务器端同时开启）
from src.config import (
    get_database_config,
    load_config,
    setup_logging,
)

logger = logging.getLogger("load_data")

# 表名 → CSV 文件名映射（含 order）
TABLE_CSV_MAP: list[tuple[str, str]] = [
    ("customers",       "olist_customers_dataset.csv"),
    ("orders",           "olist_orders_dataset.csv"),
    ("order_items",      "olist_order_items_dataset.csv"),
    ("order_payments",   "olist_order_payments_dataset.csv"),
    ("order_reviews",    "olist_order_reviews_dataset.csv"),
    ("products",        "olist_products_dataset.csv"),
    ("sellers",         "olist_sellers_dataset.csv"),
    ("geolocation",     "olist_geolocation_dataset.csv"),
    ("translation",      "product_category_name_translation.csv"),
]


def _get_conn(config: dict) -> pymysql.Connection:
    """建立 MySQL 连接（允许 LOAD DATA LOCAL INFILE）。"""
    db = config["database"]
    conn = pymysql.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        database=db["database"],
        charset=db.get("charset", "utf8mb4"),
        local_infile=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    return conn


def _truncate_table(conn: pymysql.Connection, table: str) -> None:
    """清空目标表（支持重复导入）。"""
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE `{table}`")
    conn.commit()
    logger.info("已清空表：%s", table)


def _load_csv_load_data(conn: pymysql.Connection, table: str, csv_path: Path) -> int:
    """使用 LOAD DATA LOCAL INFILE 导入，返回导入行数。

    translation.csv 表头无引号，其余 CSV 有引号，分别处理 FIELDS TERMINATED BY 与 ENCLOSED BY。
    """
    # 导入前先清空表
    _truncate_table(conn, table)

    # 判断是否为 translation（无引号格式）
    is_translation = table == "translation"

    sql = (
        f"LOAD DATA LOCAL INFILE '{csv_path.as_posix()}'\n"
        "INTO TABLE `{table}`\n"
        f"CHARACTER SET utf8mb4\n"
        "FIELDS TERMINATED BY ','\n"
        + ("OPTIONALLY " if not is_translation else "")
        + "ENCLOSED BY '\"'\n"
        "LINES TERMINATED BY '\\n'\n"
        + (" " if is_translation else "IGNORE 1 LINES ")
        + ";"
    ).format(table=table)

    # translation 表头无引号，去掉 IGNORE 1 LINES 前后的多余空格
    sql = sql.replace(" ;", ";")

    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

    # 验证导入行数
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
        count = cur.fetchone()["cnt"]
    return count


def _load_csv_pandas(conn: pymysql.Connection, table: str, csv_path: Path) -> int:
    """使用 pandas.read_csv + executemany 批量插入。"""
    _truncate_table(conn, table)

    df = pd.read_csv(csv_path, encoding="utf-8")

    cols = ", ".join(f"`{c}`" for c in df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT IGNORE INTO `{table}` ({cols}) VALUES ({placeholders})"

    # 批量插入：每 5000 行提交一次，避免内存占用过大
    BATCH = 5000
    total = 0
    with conn.cursor() as cur:
        for start in range(0, len(df), BATCH):
            batch = df.iloc[start : start + BATCH]
            rows = [
                tuple(None if pd.isna(v) else (str(v) if not isinstance(v, (int, float)) else v) for v in row)
                for _, row in batch.iterrows()
            ]
            cur.executemany(sql, rows)
            total += len(rows)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
        count = cur.fetchone()["cnt"]
    return count


def load_table(conn: pymysql.Connection, table: str, raw_dir: str | Path) -> int:
    """导入单张表，使用 pandas + executemany 批量插入。"""
    csv_name = next(name for t, name in TABLE_CSV_MAP if t == table)
    csv_path = Path(raw_dir) / csv_name
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{csv_path}")

    logger.info("开始导入 %s ← %s", table, csv_name)
    count = _load_csv_pandas(conn, table, csv_path)
    logger.info("  pandas INSERT 成功，导入 %d 行", count)
    return count


def load_all(config: dict | None = None, tables: list[str] | None = None) -> dict[str, int]:
    """导入全部表或指定表集合，返回 {表名: 导入行数}。"""
    if config is None:
        config = load_config()
    conn = _get_conn(config)
    raw_dir = Path(config["paths"]["raw_data_dir"])
    results: dict[str, int] = {}

    targets = [t for t, _ in TABLE_CSV_MAP if tables is None or t in tables]
    raw_dir: Path = Path(config["paths"]["raw_data_dir"])
    logger.info("=" * 60)
    logger.info("开始导入，共 %d 张表", len(targets))
    logger.info("=" * 60)

    for table in targets:
        try:
            results[table] = load_table(conn, table, raw_dir)
        except Exception as exc:
            logger.error("导入 %s 失败：%s", table, exc)
            results[table] = -1

    conn.close()
    logger.info("=" * 60)
    logger.info("导入完成：")
    for table, cnt in results.items():
        status = "✓" if cnt >= 0 else "✗"
        logger.info("  %s %s  %d 行", status, table, cnt)
    logger.info("=" * 60)
    return results


def main() -> int:
    """CLI 入口：python -m src.load_data [table1 table2 ...]"""
    import argparse

    parser = argparse.ArgumentParser(description="导入 CSV 数据到 MySQL")
    parser.add_argument(
        "tables",
        nargs="*",
        default=None,
        help="指定要导入的表名（省略则导入全部）",
    )
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    results = load_all(config, tables=args.tables or None)

    failed = [t for t, c in results.items() if c < 0]
    if failed:
        logger.error("以下表导入失败：%s", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
