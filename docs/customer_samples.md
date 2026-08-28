# 真实客户样例与字段说明

本页展示 **6 条真实客户级派生记录**，每类运营规则一条。购买金额、评分等来自项目处理结果；标签、建议动作和渠道由 SQL 规则生成。

## 样例来源与选取方式

- 原始来源：[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，Olist 提供的公开匿名化数据。
- 完整来源：`outputs/local/customer_campaign_target_list.csv`，共 71,424 条记录，由项目流程在本地生成。
- 生成逻辑：[运营圈选 SQL](../sql/12_campaign_target_list.sql) → [CSV 导出](../src/export_outputs.py) → [样例说明生成](../src/build_sample_docs.py)。
- 选取规则：各 `reason_code` 内按完整 `customer_unique_id` 字典序升序，取第一条；展示顺序沿用运营规则顺序。
- 源文件 SHA-256：`dbde3a883ab9c0c6f5a9045c3e30ed3ef265747d13a11dac3a6392d1c29ab0ec`。

这是一组用于解释字段与规则的确定性样例，**不是随机抽样，不代表总体占比或典型客户**。匿名 ID 与字段值均保留源文件原值。

## 核心字段预览

| 运营规则 | 匿名客户 ID | 订单数（笔） | 历史支付（BRL） | Recency（天） |
| --- | --- | --- | --- | --- |
| SERVICE_RECOVERY | 0005ef4cd20d2893f0d9fbd94d3c0d97 | 1 | 129.76 | 171 |
| WINBACK_HIGH_VALUE | 00053a61a98854899e70ed204dd4bafe | 1 | 419.18 | 183 |
| SECOND_PURCHASE | 0000366f3b9a7992bf8c76cfdf3221e2 | 1 | 141.9 | 112 |
| RETAIN_AT_RISK | 011575986092c30523ecb71ff10cb473 | 2 | 214.9 | 134 |
| VIP_ENGAGE | 012a218df8995d3ec3bb221828360c86 | 2 | 1510.38 | 73 |
| CATEGORY_PROMO | 00082cbe03e478190aadbea78542e933 | 1 | 126.26 | 284 |

## 规则输出：建议动作，不是实际触达

| 运营规则 | 优先级 | 建议动作 | 建议渠道 |
| --- | --- | --- | --- |
| SERVICE_RECOVERY | high | 售后关怀、补偿券、满意度回访 | 邮件+客服电话回访 |
| WINBACK_HIGH_VALUE | high | 专属召回优惠或会员关怀 | 邮件（个性化优惠券） |
| SECOND_PURCHASE | high | 首购后14-30天二购激励与品类推荐 | 邮件/App推送 |
| RETAIN_AT_RISK | high | 预防性挽留：限时权益与个性化提醒 | 邮件+短信 |
| VIP_ENGAGE | medium_high | VIP权益、新品优先体验、推荐奖励 | App/会员中心 |
| CATEGORY_PROMO | medium | 对应品类内容、活动和商品推荐 | App推送/社交媒体 |

`recommended_channel` 是建议渠道类别，不表示数据集包含该客户的邮箱或电话号码，也不证明触达渠道可用。`SECOND_PURCHASE` 名单的筛选条件为 Recency 14–180 天；建议动作中的“14–30 天”描述建议触达时点，不是名单筛选窗口。两者也不同于首购后第 1–90 天的跨日二购分析窗口。

本项目未实施真实营销触达或 A/B 实验。`simulated_campaign_tasks.csv` 仅演示排期，任务状态为 `SIMULATED`，不代表实际发送或实验结果。

## 完整字段字典

| 字段 | 类型／单位 | 含义与注意事项 |
| --- | --- | --- |
| customer_unique_id | 字符串 | 公开数据中的匿名客户标识；跨订单关联键，不是姓名或联系方式。 |
| value_segment | 分类标签 | 价值分层：high_value / mid_value / low_value；由历史支付分位数规则生成。 |
| lifecycle_stage | 分类标签 | 生命周期：new_customer / active_customer / at_risk / churned；依据最近购买时间等规则生成。 |
| behavior_segment | 分类标签 | 行为主标签，如 installment_user、high_aov、category_focused；按标签优先级确定。 |
| experience_segment | 分类标签 | 履约体验标签，如 service_recovery_needed、low_satisfaction、delivery_normal。 |
| favorite_category | 字符串 | 按项目规则选出的偏好品类，保留原品类编码；不是人工推测。 |
| order_count | 整数／笔 | 客户已交付订单数；不同于商品件数。 |
| total_payment | 数值／BRL | 客户已交付订单的历史支付总额。 |
| average_order_value | 数值／BRL | 客户历史支付总额 ÷ 已交付订单数，保留源表精度。 |
| recency_days | 整数／自然日 | 距最近有效购买的天数，观察日沿用项目实际分析日。 |
| average_review_score | 数值／1–5 分 | 客户有效订单的平均评分；无可用评分时为空。 |
| delayed_order_rate | 数值／0–1 比例 | 客户可判定履约状态订单中的延迟比例；1.0 表示 100%，不是 1%。 |
| recommended_action | 字符串 | SQL 规则生成的建议运营动作；不是已执行动作或效果记录。 |
| recommended_channel | 字符串 | 规则配套的建议渠道名称；不是已验证可用的联系方式。 |
| campaign_priority | 分类标签 | 规则优先级：high / medium_high / medium。 |
| reason_code | 分类标签 | 互斥运营规则命中原因；按规则优先级命中即停。 |

标签阈值、优先级和观察窗口以 [指标定义](metric_definitions.md) 为准。空值保留为空，不能当作零；数值不重新四舍五入。

## 六条完整记录

<details>
<summary>展开查看全部原字段（JSON 以字符串保留 CSV 原始文本与精度）</summary>

```json
[
  {
    "customer_unique_id": "0005ef4cd20d2893f0d9fbd94d3c0d97",
    "value_segment": "mid_value",
    "lifecycle_stage": "at_risk",
    "behavior_segment": "installment_user",
    "experience_segment": "service_recovery_needed",
    "favorite_category": "esporte_lazer",
    "order_count": "1",
    "total_payment": "129.76",
    "average_order_value": "129.76",
    "recency_days": "171",
    "average_review_score": "1.0",
    "delayed_order_rate": "1.0",
    "recommended_action": "售后关怀、补偿券、满意度回访",
    "recommended_channel": "邮件+客服电话回访",
    "campaign_priority": "high",
    "reason_code": "SERVICE_RECOVERY"
  },
  {
    "customer_unique_id": "00053a61a98854899e70ed204dd4bafe",
    "value_segment": "high_value",
    "lifecycle_stage": "churned",
    "behavior_segment": "high_aov",
    "experience_segment": "low_satisfaction",
    "favorite_category": "esporte_lazer",
    "order_count": "1",
    "total_payment": "419.18",
    "average_order_value": "419.18",
    "recency_days": "183",
    "average_review_score": "1.0",
    "delayed_order_rate": "0.0",
    "recommended_action": "专属召回优惠或会员关怀",
    "recommended_channel": "邮件（个性化优惠券）",
    "campaign_priority": "high",
    "reason_code": "WINBACK_HIGH_VALUE"
  },
  {
    "customer_unique_id": "0000366f3b9a7992bf8c76cfdf3221e2",
    "value_segment": "mid_value",
    "lifecycle_stage": "at_risk",
    "behavior_segment": "installment_user",
    "experience_segment": "delivery_normal",
    "favorite_category": "cama_mesa_banho",
    "order_count": "1",
    "total_payment": "141.9",
    "average_order_value": "141.9",
    "recency_days": "112",
    "average_review_score": "5.0",
    "delayed_order_rate": "0.0",
    "recommended_action": "首购后14-30天二购激励与品类推荐",
    "recommended_channel": "邮件/App推送",
    "campaign_priority": "high",
    "reason_code": "SECOND_PURCHASE"
  },
  {
    "customer_unique_id": "011575986092c30523ecb71ff10cb473",
    "value_segment": "high_value",
    "lifecycle_stage": "at_risk",
    "behavior_segment": "installment_user",
    "experience_segment": "delivery_normal",
    "favorite_category": "brinquedos",
    "order_count": "2",
    "total_payment": "214.9",
    "average_order_value": "107.45",
    "recency_days": "134",
    "average_review_score": "3.5",
    "delayed_order_rate": "0.0",
    "recommended_action": "预防性挽留：限时权益与个性化提醒",
    "recommended_channel": "邮件+短信",
    "campaign_priority": "high",
    "reason_code": "RETAIN_AT_RISK"
  },
  {
    "customer_unique_id": "012a218df8995d3ec3bb221828360c86",
    "value_segment": "high_value",
    "lifecycle_stage": "active_customer",
    "behavior_segment": "high_aov",
    "experience_segment": "delivery_normal",
    "favorite_category": "automotivo",
    "order_count": "2",
    "total_payment": "1510.38",
    "average_order_value": "755.19",
    "recency_days": "73",
    "average_review_score": "3.5",
    "delayed_order_rate": "0.0",
    "recommended_action": "VIP权益、新品优先体验、推荐奖励",
    "recommended_channel": "App/会员中心",
    "campaign_priority": "medium_high",
    "reason_code": "VIP_ENGAGE"
  },
  {
    "customer_unique_id": "00082cbe03e478190aadbea78542e933",
    "value_segment": "mid_value",
    "lifecycle_stage": "churned",
    "behavior_segment": "category_focused",
    "experience_segment": "delivery_normal",
    "favorite_category": "malas_acessorios",
    "order_count": "1",
    "total_payment": "126.26",
    "average_order_value": "126.26",
    "recency_days": "284",
    "average_review_score": "5.0",
    "delayed_order_rate": "0.0",
    "recommended_action": "对应品类内容、活动和商品推荐",
    "recommended_channel": "App推送/社交媒体",
    "campaign_priority": "medium",
    "reason_code": "CATEGORY_PROMO"
  }
]
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
