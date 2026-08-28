"""从现有运营名单生成少量真实样例说明，不改写数据、不重新计算标签。

运行 python -m src.build_sample_docs；使用 --check 只核对现有文档。
输出为 Markdown，不创建或改写完整客户 CSV。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from src.config import PROJECT_ROOT, get_path, load_config

RULE_ORDER = (
    "SERVICE_RECOVERY", "WINBACK_HIGH_VALUE", "SECOND_PURCHASE",
    "RETAIN_AT_RISK", "VIP_ENGAGE", "CATEGORY_PROMO",
)

FIELD_DEFINITIONS = (
    ("customer_unique_id", "字符串", "公开数据中的匿名客户标识；跨订单关联键，不是姓名或联系方式。"),
    ("value_segment", "分类标签", "价值分层：high_value / mid_value / low_value；由历史支付分位数规则生成。"),
    ("lifecycle_stage", "分类标签", "生命周期：new_customer / active_customer / at_risk / churned；依据最近购买时间等规则生成。"),
    ("behavior_segment", "分类标签", "行为主标签，如 installment_user、high_aov、category_focused；按标签优先级确定。"),
    ("experience_segment", "分类标签", "履约体验标签，如 service_recovery_needed、low_satisfaction、delivery_normal。"),
    ("favorite_category", "字符串", "按项目规则选出的偏好品类，保留原品类编码；不是人工推测。"),
    ("order_count", "整数／笔", "客户已交付订单数；不同于商品件数。"),
    ("total_payment", "数值／BRL", "客户已交付订单的历史支付总额。"),
    ("average_order_value", "数值／BRL", "客户历史支付总额 ÷ 已交付订单数，保留源表精度。"),
    ("recency_days", "整数／自然日", "距最近有效购买的天数，观察日沿用项目实际分析日。"),
    ("average_review_score", "数值／1–5 分", "客户有效订单的平均评分；无可用评分时为空。"),
    ("delayed_order_rate", "数值／0–1 比例", "客户可判定履约状态订单中的延迟比例；1.0 表示 100%，不是 1%。"),
    ("recommended_action", "字符串", "SQL 规则生成的建议运营动作；不是已执行动作或效果记录。"),
    ("recommended_channel", "字符串", "规则配套的建议渠道名称；不是已验证可用的联系方式。"),
    ("campaign_priority", "分类标签", "规则优先级：high / medium_high / medium。"),
    ("reason_code", "分类标签", "互斥运营规则命中原因；按规则优先级命中即停。"),
)
FIELDS = tuple(item[0] for item in FIELD_DEFINITIONS)


def select_records(rows):
    """每类规则选取匿名客户 ID 字典序最小的一条；严格限定为六条。"""
    selected = {}
    seen_ids = set()
    row_count = 0
    for row in rows:
        if set(row) != set(FIELDS) or any(value is None for value in row.values()):
            raise ValueError("运营名单字段或列数变化，请人工核对样例字段范围")
        customer_id = row["customer_unique_id"]
        rule = row["reason_code"]
        if not re.fullmatch(r"[0-9a-f]{32}", customer_id):
            raise ValueError("匿名客户 ID 格式异常")
        if customer_id in seen_ids:
            raise ValueError("运营名单包含重复客户 ID")
        if rule not in RULE_ORDER:
            raise ValueError(f"未审核的运营规则：{rule}")
        seen_ids.add(customer_id)
        row_count += 1
        if rule not in selected or customer_id < selected[rule]["customer_unique_id"]:
            selected[rule] = {field: row[field] for field in FIELDS}
    if set(selected) != set(RULE_ORDER):
        raise ValueError("名单未覆盖全部六类运营规则，不能生成完整样例页")
    return [selected[rule] for rule in RULE_ORDER], row_count


def markdown_table(headers, rows):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(escape(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def build_document(source: Path) -> str:
    """只读源 CSV，保留字段原始文本，生成可审阅的 Markdown。"""
    content = source.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("运营名单字段顺序或字段集合变化，请人工核对")
    records, source_rows = select_records(reader)
    digest = hashlib.sha256(content).hexdigest()
    try:
        source_label = source.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        # 自定义输入路径只在说明中记录文件名。
        source_label = source.name + "（自定义本地生成目录）"
    core = markdown_table(
        ["运营规则", "匿名客户 ID", "订单数（笔）", "历史支付（BRL）", "Recency（天）"],
        ([row[key] for key in ("reason_code", "customer_unique_id", "order_count", "total_payment", "recency_days")] for row in records),
    )
    actions = markdown_table(
        ["运营规则", "优先级", "建议动作", "建议渠道"],
        ([row[key] for key in ("reason_code", "campaign_priority", "recommended_action", "recommended_channel")] for row in records),
    )
    dictionary = markdown_table(["字段", "类型／单位", "含义与注意事项"], FIELD_DEFINITIONS)
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    return f"""# 真实客户样例与字段说明

本页展示 **{len(records)} 条真实客户级派生记录**，每类运营规则一条。购买金额、评分等来自项目处理结果；标签、建议动作和渠道由 SQL 规则生成。

## 样例来源与选取方式

- 原始来源：[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，Olist 提供的公开匿名化数据。
- 完整来源：`{source_label}`，共 {source_rows:,} 条记录，由项目流程在本地生成。
- 生成逻辑：[运营圈选 SQL](../sql/12_campaign_target_list.sql) → [CSV 导出](../src/export_outputs.py) → [样例说明生成](../src/build_sample_docs.py)。
- 选取规则：各 `reason_code` 内按完整 `customer_unique_id` 字典序升序，取第一条；展示顺序沿用运营规则顺序。
- 源文件 SHA-256：`{digest}`。

这是一组用于解释字段与规则的确定性样例，**不是随机抽样，不代表总体占比或典型客户**。匿名 ID 与字段值均保留源文件原值。

## 核心字段预览

{core}

## 规则输出：建议动作，不是实际触达

{actions}

`recommended_channel` 是建议渠道类别，不表示数据集包含该客户的邮箱或电话号码，也不证明触达渠道可用。`SECOND_PURCHASE` 名单的筛选条件为 Recency 14–180 天；建议动作中的“14–30 天”描述建议触达时点，不是名单筛选窗口。两者也不同于首购后第 1–90 天的跨日二购分析窗口。

本项目未实施真实营销触达或 A/B 实验。`simulated_campaign_tasks.csv` 仅演示排期，任务状态为 `SIMULATED`，不代表实际发送或实验结果。

## 完整字段字典

{dictionary}

标签阈值、优先级和观察窗口以 [指标定义](metric_definitions.md) 为准。空值保留为空，不能当作零；数值不重新四舍五入。

## 六条完整记录

<details>
<summary>展开查看全部原字段（JSON 以字符串保留 CSV 原始文本与精度）</summary>

```json
{payload}
```

</details>

## 复现与更新

已有本地完整名单时运行：

```bash
python -m src.build_sample_docs
python -m src.build_sample_docs --check
```

生成器只读取现有名单，不连接数据库、不重算客户标签、不写入输入数据。本页可直接使用现有样例阅读；如需重新选取样例，先按项目流程生成运营名单。完整名单更新后应同步重建并核对本页。

## 数据署名与许可

数据提供者为 Olist；本页样例经本项目 SQL 汇总、标签规则与确定性选取产生，已说明改动方式。样例数据及其改编遵循原数据的 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可（署名、非商业、相同方式共享）。项目代码的许可证单独处理，不替换原数据许可；不表示 Olist 为本项目或运营建议背书。
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验样例页是否与现有名单一致")
    args = parser.parse_args(argv)
    source = get_path(load_config(), "output_local_dir") / "customer_campaign_target_list.csv"
    output = PROJECT_ROOT / "docs/customer_samples.md"
    expected = build_document(source)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print("样例页与本地名单不一致，请先重新生成并审阅")
            return 1
        print("样例校验通过：六条记录及来源说明与本地 CSV 一致")
        return 0
    output.write_text(expected, encoding="utf-8")
    print("已生成 docs/customer_samples.md（六条真实记录，输入文件未改写）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
