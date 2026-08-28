# Olist 质量与发布检查清单

本清单用于核对项目的可复现性、指标一致性与交付完整性。自动化验证状态见 [GitHub Actions](https://github.com/Benjam1n77/olist-customer-lifecycle-analytics/actions)。

## 文档与导航

- [x] [英文首页](README.md)与[中文完整版](README.zh-CN.md)提供双向语言链接。
- [x] README 包含业务问题、技术方案、核心发现、Dashboard 和复现方式。
- [x] 详细报告、Notebook 叙述和 Tableau 标注的语言已说明。
- [x] 文档中的相对链接指向仓库内可访问的文件或目录。
- [x] [数据字典](docs/data_dictionary.md)、[指标定义](docs/metric_definitions.md)和[分析报告](docs/project_report.md)说明数据模型、分析方法与限制。

## 指标与分析边界

- [x] 核心指标可追溯至[指标索引](docs/resume_metrics.md)及[SQL × Python 校验结果](outputs/tables/cross_validation_results.csv)。
- [x] **加权 M1 留存率 0.48%**：21 个可观察成熟 Cohort 的 ΣM1 留存客户数 / ΣCohort Size = 390 / 81,265。
- [x] M1 趋势仅展示 `cohort_size ≥ 100`；该筛选不改变 KPI 的分母。
- [x] Cohort 明细保留可观察的零留存单元格；不可观察月份不填零。M2/M3 的简单平均与加权 M1 分别说明。
- [x] 90 天二购仅计首购后第 1–90 个自然日的下一笔已交付订单，排除同日订单；成熟样本 75,563 人，二购 980 人，二购率 1.2969%。
- [x] 统计模型结果表述为调整后的关联，不作为因果效应。
- [x] 运营建议、模拟排期与 A/B 方案不作为真实触达或实验结果。

## 展示 Notebook 与真实样例

- [x] [展示 Notebook](notebooks/01_project_showcase.ipynb)只读取 9 份仓库内汇总 CSV，不连接数据库，不重新拟合模型。
- [x] Notebook 可从头执行，核对加权 M1、分组人数和输入文件哈希，并保留可阅读的输出。
- [x] [客户样例](docs/customer_samples.md)限定为每类运营规则一条，共 6 条、16 个字段；原值与完整本地来源一致。
- [x] 样例页说明确定性选取方法、字段含义、源文件哈希和数据许可，不将样例解释为随机抽样。

## Tableau 交付

- [x] 打包工作簿：[Olist_Customer_Lifecycle_Dashboard.twbx](outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx)。
- [x] 客户价值总览：[dashboard_overview.png](outputs/tableau/dashboard_overview.png)。
- [x] 用户分层与留存：[customer_segment.png](outputs/tableau/customer_segment.png)。
- [x] 履约体验：[delivery_analysis.png](outputs/tableau/delivery_analysis.png)。
- [x] 三张截图均为 `1366 × 768` 的 Tableau 原生导出图片，无悬浮提示框，与工作簿及 README 一致。
- [x] 用户分层页脚注明确加权 M1、趋势筛选和 90 天跨日二购的口径，见[Tableau 指南](docs/tableau_build_guide.md)。

## 数据、配置与许可

- [x] 原始数据需从[数据来源](data/README.md)另行下载；完整客户名单、中间结果与诊断由流程生成。
- [x] `.gitignore` 覆盖 `data/raw/*`、`*.csv`、`.env`、`*.pyc`、`.ipynb_checkpoints/`、本地配置、日志与 `outputs/local/`。
- [x] 汇总 CSV、分析图、最终工作簿和截图按明确文件规则纳入版本控制。
- [x] 当前待发布文件已移除已知数据库凭据、访问令牌和私钥；无超过 10 MB 的文件。
- [ ] 已暴露的数据库密码完成轮换；远端旧提交与缓存处置完成并复核。
- [x] 项目代码采用 [MIT License](LICENSE)；Olist 数据及其改编结果遵循 CC BY-NC-SA 4.0，详见[数据许可说明](data/README.md)。

## 验证方式

在项目根目录安装依赖后运行：

```bash
python run_pipeline.py --list-stages
python -m pytest -q
jupyter nbconvert --to notebook --execute notebooks/01_project_showcase.ipynb \
  --output-dir outputs/local/notebook_runs --ExecutePreprocessor.timeout=180
```

具备完整本地运营名单时，可额外核对样例来源：

```bash
python -m src.build_sample_docs --check
```

[CI 工作流](.github/workflows/tests.yml)在 push、pull request 和手动触发时检查流水线注册、运行测试并执行 Notebook。公共克隆不包含完整客户名单，因此仅跳过依赖该文件的来源核对；样例字段、数量和规则检查正常运行。

发布更新时还需复核相对链接、Git 忽略规则、文件大小与凭据扫描；涉及 Tableau 或数据变化时，重新核对工作簿、截图和指标来源。
