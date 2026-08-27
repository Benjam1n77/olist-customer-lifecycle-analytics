# 输出目录与公开边界

此目录区分正式发布结果与本地生成产物。`local/` 表示“本地生成产物”，不是敏感性或保密等级；完整名单、中间数据和诊断不纳入 Git，是为了保持仓库精简、避免重复存储。`.gitignore` 对公开结果采用逐文件白名单，对 `local/` 整个目录忽略。

```text
outputs/
├── tables/                 # 可公开：Cohort、二购、履约与校验汇总表/工作簿
├── figures/                # 可公开：13 张正式分析图
├── tableau/                # 可公开：6 张最终汇总 CSV、TWBX、3 张原生截图
└── local/                  # 本地生成产物，所有文件类型均被 Git 忽略
    ├── customer_campaign_target_list.csv
    ├── high_value_churned_customers.csv
    ├── simulated_campaign_tasks.csv
    ├── diagnostics/        # 原始质检文本等诊断产物
    ├── tableau_staging/    # Tableau 转换前的中间汇总 CSV
    ├── notebook_runs/      # 本地执行副本与图表检查产物
    └── legacy_previews/    # 运行旧工具时生成的设计原型，非正式截图
```

## 什么是客户级文件

一行对应一个客户，或一行对应一个可关联到客户的任务/行为，即属于客户级明细。`customer_unique_id` 是用于跨订单关联的匿名标识。“客户级”仅描述粒度，并不意味着数据必然敏感或不能公开。Olist 官方说明数据已匿名化；本项目没有添加姓名、电话等身份信息。数据来源与许可见 [数据说明](../data/README.md)。

| 本地文件 | 粒度与内容 | 发布规则 |
| --- | --- | --- |
| `local/customer_campaign_target_list.csv` | 客户 ID、价值/生命周期标签、消费特征、运营建议 | 不发布 |
| `local/high_value_churned_customers.csv` | 客户 ID、首末购日期、金额、品类、地区与体验特征 | 不发布 |
| `local/simulated_campaign_tasks.csv` | 客户 ID、推荐动作、渠道和模拟排期 | 不发布；全部为 SIMULATED，未真实发送 |
| `tableau/customer_segment_dashboard.csv` | 每个人群一行，仅含人数、支付占比与客单价 | 精确白名单发布 |
| `tables/cohort_retention_long.csv` | 每个 Cohort × 月龄一行，不含客户 ID | 精确白名单发布；保留原始 Cohort 汇总行 |

`local/` 也存放 Tableau 转换前汇总等非客户级中间结果。完整文件留在本地；公开 [6 条真实运营样例及完整字段说明](../docs/customer_samples.md)，每类运营规则选取一条，用于展示交付结构，不用于估计总体分布。

## 生成与复现

- `python -m src.export_outputs --campaign --churn`：将三份客户级 CSV 写入配置项 `output_local_dir`（默认 `outputs/local/`）。
- `python -m src.export_outputs --tableau`：中间表写入 `local/tableau_staging/`，最终六张 Tableau 汇总写入 `tableau/`；不改写 TWBX 或原生截图。
- `python -m src.build_sample_docs`：从已生成本地运营名单确定性选取真实记录，刷新 `docs/customer_samples.md`；不修改名单、不重新计算标签。
- [展示 Notebook](../notebooks/01_project_showcase.ipynb) 只读取已发布的汇总 CSV，无需 MySQL、原始数据或本地名单，不重新拟合模型。
- 本地目录首次运行时自动创建，不需要在 Git 中保留占位文件。发布时不要使用 `git add -f` 强制加入整个目录；若自定义输出路径，需要同步检查忽略规则。

原始数据仍在 `data/raw/`，去重审计明细仍在 `data/interim/`，运行日志仍在 `logs/`，真实连接配置仍在 `config/config.yaml`；这些内容继续被忽略。`docs/project_report.html` 和 `.pdf` 是不发布的本地报告副本，正式文档以 Markdown 为准。

旧布局工具仅存于本地 `tools/legacy/`，它和其生成的设计预览均不随公开仓库发布。正式 Tableau 交付始终是 `tableau/` 中的最终 TWBX 和三张原生 PNG。
