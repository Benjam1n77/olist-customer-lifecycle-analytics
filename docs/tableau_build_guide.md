# Olist Tableau Dashboard 搭建指南

## 工作簿与截图

- 打包工作簿：`outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx`。
- 三页 Tableau 原生导出截图：`dashboard_overview.png`、`customer_segment.png`、`delivery_analysis.png`。
- 三页 Dashboard 均为固定尺寸 `1366 × 768`，截图与最终工作簿的指标口径一致。
- 用户分层页脚注说明加权 M1 口径；截图不含悬浮提示框。

## 1. Tableau 数据源

| 数据源 | 用途 |
| --- | --- |
| `customer_overview.csv` | 客户、订单、支付与复购 KPI |
| `customer_segment_dashboard.csv` | 用户分层人数、支付占比与平均客单价 |
| `cohort_dashboard.csv` | Cohort 留存热力图与 M1 趋势 |
| `delivery_dashboard.csv` | 延迟区间、州延迟率与评分 |
| `campaign_dashboard.csv` | 运营目标人群规模与优先级 |
| `delivery_experience_summary.csv` | 履约体验 KPI 与统计检验汇总 |
| `repeat_purchase_90d_overview.csv` | 90 天跨日二购 KPI 汇总 |

这些文件已经是 Dashboard 粒度，不需要在 Tableau 中再次连接原始明细表，也不需要建立跨数据源 JOIN。

Dashboard CSV、TWBX 和原生截图位于 `outputs/tableau/`；上表中的履约体验与 90 天二购汇总位于 `outputs/tables/`。导出过程中的中间汇总写入 `outputs/local/tableau_staging/`，具体生成方式见 [输出说明](../outputs/README.md)。

## 2. 视觉规范

- Dashboard 固定尺寸：`1366 × 768`。
- 主色：深蓝 `#17324D`。
- 客户规模：蓝色 `#2F6B9A`。
- 正常/正向指标：绿色 `#2A9D8F`。
- 风险提示：橙色 `#F4A261`。
- 履约受损或严重延迟：红色 `#E76F51`。
- 背景：`#F4F7FA`；图表和 KPI 卡使用白色。
- 金额格式：`R$ #,##0` 或 `R$ #,##0.00`。
- CSV 中的比例字段以 `0–100` 保存，在 Tableau 中使用自定义格式 `0.00"%"`，不要再次乘以 100。

## 3. 页面一：Customer Value Overview

### KPI 工作表

从 `customer_overview.csv` 创建五个文本工作表：

1. `KPI Customers`：`customer_count`。
2. `KPI Orders`：`order_count`。
3. `KPI Payment`：`payment_amount`。
4. `KPI Repeat Rate`：`repeat_rate`。
5. `KPI One-time Rate`：`one_time_rate`。

Marks 选择 `Text`，隐藏标题和网格线，将 KPI 值置于中心，标签使用小号灰色文字。

### Segment Size

- 数据源：`customer_segment_dashboard.csv`。
- Rows：`segment`。
- Columns：`SUM(customer_count)`。
- Marks：Horizontal Bar。
- 排序：按客户数降序。
- Label：显示客户数，格式 `#,##0`。

### Campaign Target Volume

- 数据源：`campaign_dashboard.csv`。
- Rows：`reason_code`。
- Columns：`SUM(customer_count)`。
- Color：`campaign_priority`。
- Label：显示客户数。
- 排序：客户数降序。

## 4. 页面二：Customer Segmentation & Retention

### Payment Share

- 数据源：`customer_segment_dashboard.csv`。
- Rows：`segment`。
- Columns：`SUM(payment_share)`。
- Marks：Horizontal Bar。
- 格式：`0.00"%"`。

### M1 Retention Trend

- 数据源：`cohort_dashboard.csv`。
- Filter：`month_index = 1`。
- 为避免极小 Cohort 扭曲趋势图，再增加 `cohort_size >= 100` 的展示筛选。
- Columns：`cohort_month`，使用离散月份。
- Rows：`AVG(retention_pct)`。
- Marks：Line + Circle。
- 图表标题必须注明 `cohorts with 100+ customers`。

顶部 KPI 使用全部 21 个可观察成熟 Cohort 的**加权 M1 留存率 0.48%**，计算字段为：

```text
SUM(IF [month_index] = 1 THEN [retained_customers] END)
/
SUM(IF [month_index] = 1 THEN [cohort_size] END)
```

顶部 KPI 不继承趋势图的 `cohort_size >= 100` 展示筛选。

### Cohort Heatmap

- Rows：`cohort_month`。
- Columns：`month_index`。
- Color：`AVG(retention_pct)`。
- Label：可选 `AVG(retention_pct)`。
- Marks：Square。
- 不可观察的未来月份保持空白，不填充为 0。

## 5. 页面三：Delivery Experience & Satisfaction

### Delay Bucket Score

- 数据源：`delivery_dashboard.csv`。
- Filter：`grain = 'delay_bucket'`。
- Columns：`dim_value`。
- Rows：`AVG(avg_score)`。
- Marks：Bar。

创建排序字段 `Delay Bucket Order`：

```text
CASE [dim_value]
WHEN 'on_time' THEN 1
WHEN 'delay_1_3' THEN 2
WHEN 'delay_4_7' THEN 3
WHEN 'delay_8_14' THEN 4
WHEN 'delay_15_plus' THEN 5
END
```

按该字段升序排列。

### State Delay Rate

- Filter：`grain = 'state'`。
- Filter：`orders >= 100`。
- Rows：`dim_value`。
- Columns：`AVG(delay_rate_pct)`。
- 使用 Top 10 Filter，按 `AVG(delay_rate_pct)` 取最高十个州。

### 页面注释

在 Dashboard 底部保留：

> Delivery delay is strongly associated with lower review scores; observational data does not establish causality.

## 6. Dashboard 组装

Tableau 官方流程是在创建工作表后点击 `New Dashboard`，再将工作表拖入页面。官方说明：<https://help.tableau.com/current/pro/desktop/en-us/dashboards_create.htm>

每页使用垂直容器：

1. 深蓝标题栏。
2. KPI 横向容器。
3. 两列主体图表区域。
4. 数据来源和口径说明。

将所有外边距统一设置，关闭默认阴影和粗边框，仅用浅灰细线分隔 KPI 卡片。

## 7. 核对与导出

发布或截图前核对：

- 客户数：93,358。
- 有效订单：96,478。
- 总支付金额：15,422,461.77 BRL。
- 一次性购买率：97.00%；复购率：3.00%。
- 加权 M1 留存率：0.48%（390 / 81,265；21 个成熟 Cohort）。
- 高价值流失客户：10,915。
- 延迟率：7.98%；准时评分：4.30；延迟评分：2.57。

用户分层页底部口径必须为：

> 口径：M1 KPI 为 21 个可观察成熟 Cohort 的加权留存率（ΣM1 留存客户数 / ΣCohort Size）；趋势仅展示 cohort_size ≥ 100；90 天二购仅计首购后第 1–90 个自然日，排除同日订单。

使用 Tableau 图片导出功能生成：

- `outputs/tableau/dashboard_overview.png`
- `outputs/tableau/customer_segment.png`
- `outputs/tableau/delivery_analysis.png`

导出图片应保持 `1366 × 768`，并确认没有悬浮提示框，指标与工作簿一致。
