"""项目配置加载模块。

职责：
1. 定位项目根目录（基于本文件位置推导，不使用绝对路径硬编码）；
2. 加载 YAML 配置文件（默认 config/config.yaml），缺失时回退到示例值；
3. 允许环境变量覆盖数据库配置（环境变量优先级高于 YAML）；
4. 提供统一的目录路径解析函数与数据库连接串构建函数。

安全约定：
- 真实配置 config.yaml 已在 .gitignore 中忽略；
- 日志中不输出数据库密码。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 项目根目录：src/ 的上一级
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# 环境变量名映射（环境变量优先于 YAML）
_ENV_DB_KEYS: dict[str, str] = {
    "host": "OLIST_DB_HOST",
    "port": "OLIST_DB_PORT",
    "user": "OLIST_DB_USER",
    "password": "OLIST_DB_PASSWORD",
    "database": "OLIST_DB_NAME",
}

# 当 config/config.yaml 不存在时使用的兜底默认值（与 config.example.yaml 一致）
_DEFAULT_CONFIG: dict[str, Any] = {
    "database": {
        "host": "localhost",
        "port": 3306,
        "user": "your_mysql_user",
        "password": "your_mysql_password",
        "database": "olist_ecommerce",
        "charset": "utf8mb4",
    },
    "paths": {
        "raw_data_dir": "data/raw",
        "interim_data_dir": "data/interim",
        "processed_data_dir": "data/processed",
        "sql_dir": "sql",
        "output_tables_dir": "outputs/tables",
        "output_figures_dir": "outputs/figures",
        "output_tableau_dir": "outputs/tableau",
        "output_local_dir": "outputs/local",
    },
    "analysis": {
        "valid_order_status": "delivered",
        "low_score_threshold": 2,
        "analysis_date": None,
    },
    "logging": {
        "level": "INFO",
        "log_file": "logs/pipeline.log",
    },
}


@dataclass(frozen=True)
class DatabaseConfig:
    """MySQL 数据库连接配置。"""

    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"

    def to_sqlalchemy_url(self) -> str:
        """构建 SQLAlchemy + PyMySQL 连接串。"""
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )

    def safe_repr(self) -> str:
        """用于日志输出的脱敏描述（不泄露密码）。"""
        return f"mysql://{self.user}@{self.host}:{self.port}/{self.database}"


class ConfigError(RuntimeError):
    """配置加载或校验失败时抛出。"""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并配置字典，override 优先。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(config_path: Path) -> dict[str, Any]:
    """读取 YAML 配置文件；文件不存在时返回空字典并提示使用示例配置。"""
    if not config_path.exists():
        example_path = PROJECT_ROOT / "config" / "config.example.yaml"
        if example_path.exists():
            logger.warning(
                "未找到 %s，已使用内置默认配置。可复制 %s 并按需修改。",
                config_path.relative_to(PROJECT_ROOT),
                example_path.relative_to(PROJECT_ROOT),
            )
        return {}
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件格式无效（应为映射结构）：{config_path}")
    return data


def _apply_env_overrides(db_cfg: dict[str, Any]) -> dict[str, Any]:
    """用环境变量覆盖数据库配置。"""
    result = dict(db_cfg)
    for key, env_name in _ENV_DB_KEYS.items():
        value = os.environ.get(env_name)
        if value is not None and value != "":
            result[key] = int(value) if key == "port" else value
    return result


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """加载完整项目配置。

    Args:
        config_path: 配置文件路径，默认 PROJECT_ROOT/config/config.yaml。

    Returns:
        合并后的配置字典（默认值 < YAML < 环境变量）。
    """
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "config.yaml"

    config = _deep_merge(_DEFAULT_CONFIG, _load_yaml(config_path))

    if "database" not in config or not isinstance(config["database"], dict):
        raise ConfigError("配置缺少 database 段落")
    config["database"] = _apply_env_overrides(config["database"])
    return config


def get_database_config(config: dict[str, Any] | None = None) -> DatabaseConfig:
    """从配置字典构建 DatabaseConfig。

    Args:
        config: 完整配置字典；为 None 时自动加载。
    """
    if config is None:
        config = load_config()
    db = config["database"]
    return DatabaseConfig(
        host=str(db["host"]),
        port=int(db["port"]),
        user=str(db["user"]),
        password=str(db["password"]),
        database=str(db["database"]),
        charset=str(db.get("charset", "utf8mb4")),
    )


def get_path(config: dict[str, Any], key: str, ensure_exists: bool = False) -> Path:
    """按配置键名解析目录路径（相对路径统一基于项目根目录）。

    Args:
        config: 完整配置字典。
        key: paths 段落中的键名，如 "raw_data_dir"。
        ensure_exists: 为 True 时自动创建目录。

    Raises:
        ConfigError: 键名不存在时抛出。
    """
    paths = config.get("paths", {})
    if key not in paths:
        raise ConfigError(f"paths 配置缺少键：{key}")
    raw_path = Path(paths[key])
    resolved = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    if ensure_exists:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def setup_logging(config: dict[str, Any] | None = None) -> None:
    """初始化项目日志：同时输出到控制台与日志文件。"""
    if config is None:
        config = load_config()
    log_cfg = config.get("logging", {})
    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)

    log_file_rel = log_cfg.get("log_file", "logs/pipeline.log")
    log_file = PROJECT_ROOT / log_file_rel
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（多次调用 setup_logging 时）
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


if __name__ == "__main__":
    setup_logging()
    cfg = load_config()
    db_cfg = get_database_config(cfg)
    logger.info("配置加载成功，数据库连接目标：%s", db_cfg.safe_repr())
    logger.info("项目根目录：%s", PROJECT_ROOT)
