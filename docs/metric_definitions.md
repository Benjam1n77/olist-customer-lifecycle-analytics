# 指标口径定义（Metric Definitions）

> 本文档定义分析样本、指标计算、客户标签与观察窗口。
> 任何分析结果引用指标时，以本文档为准。

---

## 全局口径

| 口径项 | 定义 | 说明 |
| --- | --- | --- |
| analysis_date | 数据集中最大有效购买日期 + 1 天 | 所有 Recency、流失、生命周期判断的观察日，本数据集为 2018-08-30 |
| 有效订单 | `order_status = 'delivered'` | 核心用户价值与复购分析仅统计已交付订单；全状态分布保留在 mart_order_summary |
| 客户主体 | `customer_unique_id` | 复购、留存、流失分析一律以真实客户 ID 为主体 |
| 金额单位 | BRL（巴西雷亚尔），DECIMAL(10,2) | 所有金额保留 2 位小数 |

### 金额口径

```text
goods_amount   = 订单内 SUM(price)                 商品价格合计
freight_amount = 订单内 SUM(freight_value)          运费合计
item_amount    = goods_amount + freight_amount     订单应付总额
payment_amount = 订单内 SUM(payment_value)          实际支付记录金额合计
```

**实测差异（不得假设相等）**：98,665 笔双金额齐全订单中，98,089 笔完全相等；260 笔（0.26%）差异 > 0.05 元（241 笔支付多于商品+运费，19 笔支付少于商品+运费，最大差异 182.81 元）。用户价值分析以 `payment_amount`（实际支付）为准，订单规模描述可同时展示两者。

---

## 订单宽表（mart_order_summary）口径

### 聚合规则（一单多行 → 一单一行）

| 字段 | 聚合规则 | 理由 |
| --- | --- | --- |
| item_count | COUNT(商品行) | 商品行总数 |
| distinct_product_count | COUNT(DISTINCT product_id) | 同商品多件只计 1 |
| seller_count | COUNT(DISTINCT seller_id) | 多卖家拆单识别 |
| product_category_count | COUNT(DISTINCT 类别) | NULL 类别不计入 |
| goods_amount / freight_amount / item_amount | SUM | 金额合计，ROUND 2 位 |
| main_category | 订单内商品金额(price)合计最高的类别；并列取类别名字典序较小者；类别全为 NULL 则为 NULL | 确定性规则，可复现 |
| payment_amount | SUM(payment_value) | 组合支付合计 |
| main_payment_type | 支付金额最高的方式；并列取类型名字典序较小者 | 确定性规则 |
| max_installments | MAX(payment_installments) | 最大分期数 |
| review_score | MAX(review_score) | 同单多评价（243 单）按最高分汇总，不据此推断评价先后顺序 |
| has_review_comment | 任一条评价含标题或正文 → 1 | 评论存在性 |
| review_response_days | 取提交时间最新一条的 DATEDIFF(提交 − 问卷创建) | 代表最终响应时长 |

### 履约时效派生字段

```text
delivery_days           = DATEDIFF(实际签收日期, 购买日期)
estimated_delivery_days = DATEDIFF(预计签收日期, 购买日期)
delay_days              = DATEDIFF(实际签收日期, 预计签收日期)
is_delayed              = 实际签收日期 > 预计签收日期（1/0；任一时间缺失为 NULL）
is_low_score            = review_score <= 2（1/0；无评价为 NULL）
```

注：以上指标只使用购买/签收/预计签收三个时间，不涉及审批与承运商时间，
因此质量检查 D2/D3 的时间链路异常订单不影响这些指标。

### 覆盖范围

| 表 | 行数 | 说明 |
| --- | --- | --- |
| mart_order_summary | 99,441 | 与 orders 一致，一行一订单（已验证） |
| 有商品行的订单 | 98,666 | 775 笔订单无商品行（多为 created/canceled），相关字段为 NULL |
| 有支付记录的订单 | 99,440 | 1 笔订单无支付记录 |
| 有评价的订单 | 98,167 | 评价表去重后的订单覆盖 |

---

## 用户宽表（mart_customer_features）口径

### 覆盖范围与观察日

| 口径项 | 实测值 | 说明 |
| --- | --- | --- |
| analysis_date | **2018-08-30** | 最大有效购买日期 2018-08-29 + 1 天，数据推导非手工指定 |
| 入表客户数 | 93,358 | 至少有一笔 delivered 订单的真实客户 |
| 排除客户数 | 2,738 | 仅有无效订单（canceled 等）的客户，不进入核心分析 |
| recency_days 范围 | 1 – 714 天 | 无负值（已验证） |

#### 客户口径勾稽关系

```text
全量真实客户数（订单中出现过的 customer_unique_id） = 96,096
  = 用户宽表客户数（≥1 笔 delivered）    93,358
  + 排除客户数（零 delivered）           2,738
```

被排除 2,738 人的订单状态构成（已验证）：shipped 1,047 / unavailable 576 / canceled 544 / invoiced 298 / processing 287 / created 4 / approved 2。排除理由：这些客户没有任何完成交付的订单，无法计算有效消费金额、履约体验与复购行为，故不进入价值/生命周期分层；但在 README 与报表中披露全量客户数时须使用 96,096 并说明本勾稽关系。另注：全数据集 1,107 笔 shipped 订单全部属于这批被排除客户。

### 字段计算规则

| 字段 | 规则 |
| --- | --- |
| first/last_purchase_date | delivered 订单购买日期的 MIN / MAX |
| customer_tenure_days | last − first（天） |
| recency_days | DATEDIFF(analysis_date, last_purchase_date) |
| order_count | COUNT(DISTINCT order_id)，仅 delivered；已验证总和 = 96,478 |
| repeat_purchase_flag | order_count ≥ 2 → 1 |
| total_goods/freight/payment | delivered 订单金额合计；total_payment 已验证 = 15,422,461.77（与订单宽表一致） |
| average_order_value | total_payment / order_count |
| average_item_count | AVG(item_count) |
| favorite_category | **消费金额口径**：商品明细级 SUM(price) 最高的类别；并列取字典序较小者；无类别消费为 NULL |
| favorite_payment_type | 支付金额 SUM(payment_value) 最高的方式；并列取字典序较小者 |
| average_delivery_days | AVG(delivery_days)，仅 delivery_days 非空订单 |
| delayed_order_count / rate | is_delayed=1 的单数；分母为 is_delayed 可判定（非 NULL）的单数 |
| average_delay_days | AVG(delay_days)，含负值（提前送达），仅 delay_days 非空订单 |
| average_review_score | AVG(review_score)，仅有评价订单 |
| low_score_order_count / rate | is_low_score=1 的单数；分母为有评价的单数 |
| customer_state | **最近订单口径**：最近一笔 delivered 订单对应的州；同日多单按 order_id 字典序确定性取一 |

### 用户宽表实测分布

| 指标 | 数值 |
| --- | --- |
| 一次性购买率 | 97.00%（90,557 / 93,358） |
| 复购客户数（≥2 笔 delivered） | 2,801 |
| 最多订单数 | 15 |
| Recency ≤30 / ≤90 / 91–180 / >180 天 | 6,621 / 18,390 / 19,587 / 55,381 |

> 复购口径注：此处 2,801 为“≥2 笔 delivered 订单”口径；原始客户表质量检查 A5 的 2,997 为“≥2 个 customer_id（含未交付）”口径，两者的订单状态范围不同。
> Recency 分布显示 59.3% 客户距观察日超 180 天；这是历史行为分布，不代表对未来购买行为的预测。

---

## 用户标签与分层（dim_customer_segment）口径

### RFM 评分（数据适配版）

97% 客户为一次性购买，F 若机械五等分会失去区分度，因此采用以下频次分段：

| 维度 | 评分规则 | 实测阈值（数据推导） |
| --- | --- | --- |
| R | recency 分位评分，越小分越高（5→1） | p20=93 / p80=383 天（p40/p60 见 SQL 输出） |
| F | 先分一次性/复购，复购再细分频次：1单=1，2单=2，3–4单=3，5–9单=4，≥10单=5 | 复购分布：2单 2,573 / 3–4单 209 / ≥5单 19 人 |
| M | total_payment 分位评分（1→5） | p20=55.26 / p80=208.55 BRL |
| rfm_score | R×100 + F×10 + M（三位数，如 553） | 范围 111–555 |

分位数用 ROW_NUMBER 取第 CEIL(q×n) 行实现（MySQL 8.0 无 PERCENTILE_CONT），并列时按 customer_unique_id 确定性排序。

### 价值标签

| 标签 | 规则 | 实测人数 |
| --- | --- | --- |
| high_value | total_payment ≥ p80（208.55 BRL） | 18,675（20.00%） |
| mid_value | p20 ≤ total_payment < p80 | 56,014（60.00%） |
| low_value | total_payment < p20（55.26 BRL） | 18,669（20.00%） |

### 生命周期标签

| 标签 | 规则 | 实测人数 |
| --- | --- | --- |
| new_customer | recency ≤ 30 且 order_count = 1 | 6,414（6.87%） |
| active_customer | recency ≤ 90（非新客） | 11,976（12.83%） |
| at_risk | 90 < recency ≤ 180 | 19,587（20.98%） |
| churned | recency > 180 | 55,381（59.32%） |

生命周期采用 30/90/180 天的规则阈值。对应的 Recency 分布为 6,621/18,390/19,587/55,381 人；这些阈值用于历史客户分层，未通过预测模型或实验优化。

### 行为标签（6 个布尔标签 + 1 个主标签）

| 标签 | 规则 | 实测依据 |
| --- | --- | --- |
| one_time_buyer / repeat_buyer | order_count = 1 / ≥ 2 | 90,557 / 2,801 |
| high_aov | average_order_value ≥ p80（201.81 BRL） | 约 20% |
| price_sensitive | average_order_value ≤ p20（55.00 BRL） | 约 20% |
| category_focused | 偏好类别消费占比 ≥ 70% | 商品明细级金额计算 |
| installment_user | 任一 delivered 订单 max_installments > 1 | 订单宽表推导 |

behavior_segment 主标签优先级：high_aov > installment_user > category_focused > price_sensitive > repeat_buyer > one_time_buyer。

### 履约体验标签

| 标签 | 规则 |
| --- | --- |
| service_recovery_needed | delayed_order_count ≥ 1 且 average_review_score ≤ 2 |
| low_satisfaction | average_review_score ≤ 2 |
| frequent_delay | delayed_order_rate ≥ 0.5 且 delayed_order_count ≥ 2 |
| delivery_delayed | delayed_order_count ≥ 1 |
| delivery_normal | delayed_order_count = 0（含无可判定订单） |

experience_segment 主标签优先级：service_recovery_needed > low_satisfaction > frequent_delay > delivery_delayed > delivery_normal。

### 最终业务人群（final_segment，优先级自上而下互斥）

| 人群 | 规则 | 实测人数 |
| --- | --- | --- |
| 履约受损客户 | service_recovery_needed | 4,024（4.31%） |
| 高价值活跃客户 | high_value 且 new/active | 3,666（3.93%） |
| 高价值流失风险客户 | high_value 且 at_risk | 3,761（4.03%） |
| 高价值已流失客户 | high_value 且 churned | 10,326（11.06%） |
| 重复购买成长客户 | repeat_buyer 且 recency ≤ 180 | 510（0.55%） |
| 首购未复购客户 | order_count = 1 且 recency ≤ 180 | 28,521（30.55%） |
| 低价值长期沉默客户 | low_value 且 churned | 10,837（11.61%） |
| 其他普通客户 | 其余（中价值流失、首购超 180 天等） | 31,713（33.97%） |

验证：各人群之和 = 93,358 = 用户宽表行数 ✓；价值分层 20/60/20 与分位数定义一致 ✓。

---

## Cohort 留存（cohort_retention_long）口径

### 定义

| 口径项 | 规则 |
| --- | --- |
| Cohort 划分 | 客户首笔 delivered 订单的购买月份（与 mart_customer_features.first_purchase_date 一致） |
| 活跃定义 | 该月至少一笔 delivered 订单 |
| month_index | TIMESTAMPDIFF(MONTH, cohort_month, activity_month)，M0 = 首购当月（留存恒 100%，已验证） |
| retention_rate | retained_customers / cohort_size |

### 观察窗口截断与成熟 Cohort

- analysis_date = 2018-08-30，2018-08 为不完整月份，观察窗口终点取最后完整月 **2018-07**（由数据推导，非硬编码）；
- **可观察格子全量生成**：当月没有留存客户时记 0；
- **不可观察格子不生成行**：绝不把未来尚未发生的月份视为 0 留存；
- **覆盖范围勾稽**：首购在 2018-08 的 6,144 名客户无法观察完整 M0，不进入 Cohort；Cohort 总人数 87,214 + 6,144 = 93,358（已验证）；
- 成熟定义：某 Cohort 的 month_index = k 格子存在即代表已可观察；M1 KPI 按客户数加权汇总，M2/M3 对可观察成熟 Cohort 的明细留存率取简单平均。

### 实测结果（SQL 与 Python 双端一致）

| 指标 | 成熟 Cohort 数 | 汇总口径 | 留存率 |
| --- | --- | --- | --- |
| M1 留存率 | 21（2016-09 ~ 2018-06） | **ΣM1 留存客户数 / ΣCohort Size = 390 / 81,265** | **0.48%** |
| M2 留存率 | 20（2016-09 ~ 2018-05） | 成熟 Cohort 简单平均 | **0.29%** |
| M3 留存率 | 19（2016-09 ~ 2018-04） | 成熟 Cohort 简单平均 | **0.21%** |

共 22 个 Cohort（2016-09 ~ 2018-07），255 行留存明细。加权 M1 留存率为 0.48%；M2/M3 使用成熟 Cohort 简单平均，因此不将三者作为同一聚合口径的连续趋势直接比较。用户宽表实测一次性购买率为 97.00%。

### 产出文件

```text
outputs/tables/cohort_retention_long.csv      # 长表（255 行）
outputs/tables/cohort_retention_matrix.csv    # 矩阵（22 Cohort × M0-M21）
outputs/figures/06_cohort_retention_heatmap.png  # 热力图（不可观察格子留空）
```

---

## 履约体验分析口径与实测

### 分析样本

仅取 delivered 且 is_delayed 可判定（签收/预计时间齐全）且有评价的订单：共 **95,364 笔**（已验证与订单宽表勾稽一致）。

### 延迟分段口径

| 分段 | 定义 |
| --- | --- |
| on_time | is_delayed = 0 |
| delay_1_3 | is_delayed = 1 且 delay_days ≤ 3（含 delay_days=0 的当天超时订单：时间戳晚于预计但日期相同，共 1,267 笔） |
| delay_4_7 / delay_8_14 / delay_15_plus | 按 delay_days 区间 |

### 实测结果（SQL 与 Python 双端一致）

| 指标 | 数值 |
| --- | --- |
| 延迟率（样本内） | 7.98%（7,613 / 95,364） |
| 准时订单平均评分 | **4.30** |
| 延迟订单平均评分 | **2.57** |
| 评分差值 | 1.73 分 |
| 评分下降比例 | **40.24%**（(4.30−2.57)/4.30） |
| 低评分率：准时 vs 延迟 | 9.15% vs 53.99% |
| 分段均分：1-3 / 4-7 / 8-14 / 15+ 天 | 3.60 / 2.11 / 1.67 / 1.72 |
| 高价值客户：准时 vs 延迟均分 | 4.21 vs 2.46（延迟同样重创高价值客户） |
| 州延迟率极值 | AL 23.21% 最高，RO 2.93% 最低（≥100 单的州） |

### 统计检验（scipy / statsmodels，方法限制已说明）

| 检验 | 结果 | 解读 |
| --- | --- | --- |
| 卡方检验（延迟×低评分） | χ²=12,670.16, p<0.001, Cramér's V=0.3645 | 关联显著且强度中等偏强 |
| Mann–Whitney U（两组评分分布） | p<0.001 | 分布显著不同（评分为有序分类，不满足正态假设故用非参数检验） |
| 控制变量逻辑回归 | 延迟 OR=11.35（95% CI 10.78–11.95），p<0.001，伪R²=0.1294，n=95,364 | 控制州、主类别、订单金额（对数）后，延迟订单出现低评分的赔率约为准时订单的 11.3 倍 |

模型设定：`is_low_score ~ is_delayed + ln(item_amount+1) + 州哑变量 + 主类别哑变量`（statsmodels Logit，BFGS）。金额取对数缓解右偏；类别空值归为 unknown。

**结论与限制**：配送延迟与较低评分显著相关，且该关联在控制类别、地区与订单金额后仍显著。观察性数据无法排除全部混淆因素（如商品特性、客服响应等未观测变量），回归系数不构成因果证据。

---

## 专题：首购后 90 天二购驱动因素

### 样本与结果变量

| 口径项 | 定义与实测值 |
| --- | --- |
| 客户主体 | `customer_unique_id` |
| 首购 | 客户最早一笔 `delivered` 订单 |
| 二购 | 首购后第 1–90 个自然日内最早出现的下一笔 `delivered` 订单；同日订单不计入 |
| 成熟观察窗 | `DATEDIFF(analysis_date, first_purchase_date) >= 90`；首购截止日 2018-06-01 |
| 成熟客户数 | **75,563** |
| 90 天跨日二购客户数 / 二购率 | **980 / 1.2969%** |
| 二购间隔中位数 | **29.00 天**（使用购买时间戳计算实际间隔） |

同日订单被排除，以降低平台拆单或同次购物会话被误判为行为复购的风险。SQL 会跳过同日订单并寻找最早的跨日订单，不会因为客户先有同日订单而漏掉之后的真实二购。

### 特征与模型

| 模型 | 样本 | 特征 | 控制变量 |
| --- | ---: | --- | --- |
| purchase_time | 75,563 | 支付金额 `log2(x+1)`、运费占比每增加 10 个百分点、多商品、多卖家、分期 | 客户州、主品类、首购月份 |
| first_order_experience | 74,820 | purchase_time 特征 + 首单配送延迟 + 首单低评分 | 客户州、主品类、首购月份 |

首单体验模型只保留配送状态和评分均可观察的客户。评价缺失标记不进入模型，避免把可能受平台记录机制或行为时间顺序影响的缺失状态解释为业务驱动。模型为 statsmodels Binomial GLM，使用 HC1 稳健标准误；赔率比只代表调整后关联。

### 实测结果

| 首单特征 | 实际二购率对比 | 调整后 OR（95% CI） | p 值 | 结论 |
| --- | --- | --- | ---: | --- |
| 多商品 vs 单商品 | 1.7897% vs 1.2423% | **1.4099（1.1349–1.7515）** | 0.0019 | 显著正向关联 |
| 低评分（1–2 分） | 0.9885%（高评分组 1.3644%） | **0.7371（0.5835–0.9311）** | 0.0105 | 显著负向关联 |
| 延迟 vs 按时 | 1.0588% vs 1.3198% | 0.9127（0.6890–1.2090） | 0.5242 | 调整后未发现显著关联 |
| 分期 vs 单次支付 | 1.2782% vs 1.3170% | 0.9598（0.8368–1.1008） | 0.5575 | 未发现显著关联 |

产出文件：`repeat_purchase_90d_overview.csv`、`repeat_purchase_90d_driver_summary.csv`、`repeat_purchase_90d_segment_rates.csv`、`repeat_purchase_90d_analysis.xlsx` 和 `13_repeat_purchase_90d_drivers.png`。

---

## 营销人群名单（mart_campaign_target_list）口径

### 规则级联（自上而下命中即停，每人一条互斥推荐）

| reason_code | 命中条件 | 推荐动作 | 优先级 | 实测人数 |
| --- | --- | --- | --- | --- |
| SERVICE_RECOVERY | experience_segment = service_recovery_needed | 售后关怀、补偿券、满意度回访 | high | 4,024 |
| WINBACK_HIGH_VALUE | high_value 且 churned | 专属召回优惠或会员关怀 | high | 10,326 |
| SECOND_PURCHASE | order_count=1 且 recency 14–180 天 | 首购后14-30天二购激励与品类推荐 | high | 33,527 |
| RETAIN_AT_RISK | high_value 且 at_risk | 预防性挽留：限时权益与个性化提醒 | high | 335 |
| VIP_ENGAGE | high_value 且 new/active | VIP权益、新品优先体验、推荐奖励 | medium_high | 612 |
| CATEGORY_PROMO | behavior_segment = category_focused | 对应品类内容、活动和商品推荐 | medium | 22,600 |

合计 **71,424 人**（已验证：无重复客户、无孤立记录、比例字段均在 0–1）。

### 口径勾稽与边界

- SECOND_PURCHASE 名单按 recency 14–180 天筛选；建议动作中的“14–30 天”描述建议触达时点，不是名单筛选窗口。人数勾稽：一次性购买 14–180 天共 35,003 人 − 已被更高优先级规则命中的 1,476 人 = 33,527 ✓
- 未命中任何规则的客户（约 21,934 人，如低价值已流失且无品类偏好）不进入名单；
- 本项目只输出名单与推荐动作，**未实现真实触达**；模拟触达任务表（simulated_campaign_tasks.csv）全部标注 SIMULATED，仅演示按优先级排期（服务补救+1天 → 品类推广+14天）。
