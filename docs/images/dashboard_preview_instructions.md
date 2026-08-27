# Tableau 最终交付说明

交付文件：

- `outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx`：包含数据提取的最终打包工作簿。
- `outputs/tableau/dashboard_overview.png`：客户价值总览原生截图。
- `outputs/tableau/customer_segment.png`：用户分层与留存原生截图。
- `outputs/tableau/delivery_analysis.png`：履约体验原生截图。

三张 PNG 均为 `1366 × 768` 的 Tableau 原生导出截图。用户分层页显示加权 M1 留存率 0.48%，趋势仅展示 `cohort_size ≥ 100`。

用户分层页底部最终口径为：

> 口径：M1 KPI 为 21 个可观察成熟 Cohort 的加权留存率（ΣM1 留存客户数 / ΣCohort Size）；趋势仅展示 cohort_size ≥ 100；90 天二购仅计首购后第 1–90 个自然日，排除同日订单。

截图不应包含 Tableau 悬浮提示框。数据源、计算字段与导出方式见 [Tableau 搭建指南](../tableau_build_guide.md)。
