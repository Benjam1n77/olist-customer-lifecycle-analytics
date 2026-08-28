# 分析输出

本目录包含分析汇总表、图表和 Tableau 看板，可结合[展示 Notebook](../notebooks/01_project_showcase.ipynb)与[完整报告](../docs/project_report.md)阅读。

## 目录结构

| 目录 | 内容 |
| --- | --- |
| `tables/` | Cohort、90 天二购、履约体验和 SQL × Python 校验汇总，以及二购分析工作簿 |
| `figures/` | 客户分层、留存和履约体验等分析图表 |
| `tableau/` | Dashboard 汇总数据、打包工作簿（TWBX）和三页 Tableau 原生截图 |
| `local/` | 运行流程后生成的完整客户名单、模拟任务、中间表和诊断文件 |

Tableau 工作簿与截图采用**加权 M1 留存率 0.48%**（390 / 81,265；21 个成熟 Cohort）。趋势图仅展示 `cohort_size ≥ 100`，该筛选不影响 KPI。完整口径见[指标定义](../docs/metric_definitions.md)。

## 数据粒度与样例

汇总表按客户分群、Cohort 月龄或履约分组组织。客户级导出则以 `customer_unique_id` 为跨订单关联键，记录客户特征、标签和建议动作。

| 本地导出文件 | 内容 |
| --- | --- |
| `local/customer_campaign_target_list.csv` | 客户标签、消费特征和运营建议 |
| `local/high_value_churned_customers.csv` | 高价值流失客户的购买、品类、地区与体验特征 |
| `local/simulated_campaign_tasks.csv` | 建议动作、渠道与模拟排期；全部标注为 `SIMULATED`，未实际发送 |

[6 条真实运营样例与字段说明](../docs/customer_samples.md)展示每类规则的一条记录。样例按确定性规则选取，用于解释输出结构，不代表总体分布或真实营销触达。数据来源与许可见[数据说明](../data/README.md)。

## 生成与复现

完成数据库建模与分析后，在项目根目录运行：

```bash
# 导出完整客户名单与模拟任务
python -m src.export_outputs --campaign --churn

# 导出 Tableau 汇总数据
python -m src.export_outputs --tableau

# 从现有运营名单生成样例说明，并核对一致性
python -m src.build_sample_docs
python -m src.build_sample_docs --check
```

客户级文件写入配置项 `output_local_dir`（默认 `outputs/local/`）；Tableau 中间表写入其下的 `tableau_staging/`，看板汇总 CSV 写入 `outputs/tableau/`。导出脚本不改写 TWBX 或截图，工作簿与图片的制作方式见[Tableau 指南](../docs/tableau_build_guide.md)。

展示 Notebook 仅读取项目汇总 CSV，无需 MySQL 或完整客户名单，也不重新拟合模型。
