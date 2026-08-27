# Tableau 最终交付说明

当前最终交付：

- `outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx`：包含数据提取的最终打包工作簿。
- `outputs/tableau/dashboard_overview.png`：客户价值总览原生截图。
- `outputs/tableau/customer_segment.png`：用户分层与留存原生截图。
- `outputs/tableau/delivery_analysis.png`：履约体验原生截图。

三张 PNG 均为 `1366 × 768` 的最终 Tableau 原生导出截图，不是程序化布局原型。用户分层页显示加权 M1 留存率 0.48%，趋势仅展示 `cohort_size ≥ 100`。

用户分层页底部最终口径为：

> 口径：M1 KPI 为 21 个可观察成熟 Cohort 的加权留存率（ΣM1 留存客户数 / ΣCohort Size）；趋势仅展示 cohort_size ≥ 100；90 天二购仅计首购后第 1–90 个自然日，排除同日订单。

最终截图中不得保留 Tableau 悬浮提示框。历史设计预览、Excel 原型、恢复文件和旧独立 TWB 已从发布目录清理。
