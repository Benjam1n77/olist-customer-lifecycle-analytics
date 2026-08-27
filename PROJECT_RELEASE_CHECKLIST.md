# Olist 项目 GitHub 发布检查清单

## 发布状态

- [x] README 完成
- [x] 数据字典完成
- [x] Dashboard 完成
- [x] 截图完成
- [x] 简历素材完成
- [x] 展示 Notebook 完成并实际执行
- [x] 客户级产物与旧工具隔离
- [x] 本地产物目录命名与真实样例说明完成
- [x] GitHub 本地发布准备完成
- [x] GitHub 仓库发布完成
- [x] GitHub Actions 远程验证通过

已确认的发布选择：仓库为 `Benjam1n77/olist-customer-lifecycle-analytics`，使用 **public**，用于面试展示；自行编写的项目代码采用 MIT，Olist 数据及其改编结果保留原 CC BY-NC-SA 4.0 许可。完整个人简历不发布。

公开仓库：[Benjam1n77/olist-customer-lifecycle-analytics](https://github.com/Benjam1n77/olist-customer-lifecycle-analytics)。

`origin` 读取地址为 `https://github.com/Benjam1n77/olist-customer-lifecycle-analytics.git`；推送使用同一仓库的 `git@github.com:Benjam1n77/olist-customer-lifecycle-analytics.git`，已验证现有 SSH 授权属于 `Benjam1n77`，未新增凭据。

## 检查结果

### README

- 已包含项目架构、数据流程和用户分层三张真实项目图片。
- 已包含技术栈、数据处理流程、核心发现、运营策略与实际运行方式。
- README 中的本地链接均可解析到当前项目文件。
- Tableau 章节已展示三页最终 Tableau 原生截图，并链接最终 TWBX。

### 数据字典

- `docs/data_dictionary.md` 已覆盖 9 张原始业务表及建模注意事项。

### `.gitignore`

已确认包含以下必需规则：

```gitignore
data/raw/*
*.csv
.env
*.pyc
.ipynb_checkpoints/
```

另外已忽略本地数据库配置、日志、缓存、原始数据、客户级名单和大体积分析表；仅以精确规则放行聚合指标 CSV、13 张正式分析图、最终 TWBX 和三张原生 Dashboard 截图。

已逐项用 `git check-ignore` 验证：原始订单、真实配置、高价值客户名单、营销目标名单和模拟任务表均被忽略；README 引用的聚合结果与图表可正常进入版本库。

新增 `/outputs/local/` 和 `/tools/legacy/` 整目录规则，覆盖 CSV 之外的 Excel、JSON、图片和脚本；本地目录不保留可发布的占位文件。

### 本地目录整理

- 三份客户级 CSV 已从 `outputs/tables/` 移到 `outputs/local/`：`customer_campaign_target_list.csv`、`high_value_churned_customers.csv`、`simulated_campaign_tasks.csv`。
- 原始质检文本移到 `outputs/local/diagnostics/`；两份现有 Tableau 中间汇总移到 `outputs/local/tableau_staging/`。
- 上述六个文件迁移前后的 SHA-256 全部一致，本轮未删除数据文件。
- `output_local_dir` 已加入默认与示例配置；生产导出路径同步更新，后续运行不会把名单写回公开汇总目录。
- `build_tableau_previews.py` 已从 `src/` 移到本地 `tools/legacy/`，输出限定于 `outputs/local/legacy_previews/`，不参与 GitHub 发布。
- 输出分工与客户级数据定义见 `outputs/README.md`；README 和来源索引已同步新路径。
- 目录统一命名为 `local`，意为“本地生成产物”；完整名单不入库是仓库体积与复现方式的取舍，不再将客户级粒度等同于敏感数据。

### 真实客户样例

- 新增 `docs/customer_samples.md`：从 71,424 条现有运营名单中，每类规则选取匿名客户 ID 字典序最小的一条，共 6 条，保留全部 16 个原字段。
- 样例已通过独立表格读取与生成器两种方式逐字段核对，源文件哈希不变。
- 页面包含核心字段预览、建议动作、完整字段字典、可展开的原始字段 JSON、源文件 SHA-256 和 CC BY-NC-SA 4.0 数据署名与许可说明。
- 新增 `src/build_sample_docs.py`，可确定性重建页面；`--check` 只核对，不改写数据或文档。
- 新增 7 项测试，防止样例数量扩大、未审核字段或规则进入样例；完整源名单可用时还会核对文档与源 CSV。GitHub CI 不包含完整本地名单，因此该项来源核对会明确跳过，其他样例检查照常运行。
- README、Notebook、输出目录说明、数据说明和报告均已链接该样例页。样例不是随机抽样或营销实验结果；完整名单仍只保留在本地。

### 展示 Notebook

- `notebooks/01_project_showcase.ipynb` 含 9 个代码单元，已使用真实 Jupyter 内核从头执行并保存输出。
- 仅读取 9 份可发布汇总 CSV，覆盖客户分层、Cohort、90 天跨日二购和履约体验；不读取本地客户名单、不连接数据库、不重新拟合模型。
- 加权 M1 留存率 0.48%（390 / 81,265），与既有交叉验证记录一致；输入文件哈希运行前后不变。
- 4 张图表已逐张检查，文字和坐标轴未裁切。审阅副本保存在本地 `notebook_runs/`，不发布。
- 已为 GitHub Actions 增加 Notebook 执行步骤；实际远程运行结果见下方发布验证记录。

### Dashboard 与截图

- 已生成最终打包工作簿 `outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx`。
- 已生成 `dashboard_overview.png`、`customer_segment.png`、`delivery_analysis.png` 三页 `1366 × 768` Tableau 原生截图。
- TWBX 中 M1 KPI 使用加权口径 `ΣM1 留存客户数 / ΣCohort Size`；21 个成熟 Cohort 的实际结果为 0.48%（390 / 81,265）。
- M1 趋势仅展示 `cohort_size ≥ 100`，不影响顶部加权 KPI。
- 用户分层页新脚注已写入 TWBX 和最终截图，截图中未发现悬浮提示框。
- README 已直接引用三张最终截图和最终 TWBX。
- 已删除 3 张临时截图、3 份重复 CSV、重复热力图、空恢复文件、旧 Excel 原型、旧独立 TWB 和含旧口径的 Dashboard 设计预览，共 11 个文件。
- Tableau 构建与口径核对说明见 `docs/tableau_build_guide.md`。

### 简历素材

- 已完成 `docs/resume/resume_project_description.md`。
- 已完成 `docs/resume/resume_metrics.md`，数字与 `docs/resume_metrics.md` 保持一致。
- 已按用户确认将 `docs/resume/resume_full.tex` 加入 `.gitignore`，避免随项目公开个人联系方式；文件原样保留在本地。项目描述与指标两份简历素材继续发布。

### 90 天二购专题

- 已生成成熟首购客户概览、首单关联因素和分组二购率三张汇总表。
- 已生成赔率比图和五页审阅工作簿；工作簿公式、数据表与图表已逐页渲染检查。
- 二购限定为首购后第 1–90 个自然日的下一笔已交付订单，同日订单不计入。
- 业务结论只表述为调整后的统计关联，不声称因果。

### Git 与自动化测试

- 已初始化本地 Git 仓库，默认分支为 `main`。
- 已创建首次提交 `d15e50c`（`Initial release: Olist customer lifecycle analytics`），包含 100 个经过核验的发布文件；该提交及发布状态更新 `41066ed` 均已推送到公开仓库的 `main`。
- 已检查 Git 暂存/跟踪文件中不存在匹配忽略规则的文件；完整个人简历、原始数据与本地产物均未进入首次提交。
- 已添加 `.github/workflows/tests.yml`，在 push、pull request 和手动触发时运行流水线注册检查与 pytest。
- 当前 67 个自动化测试在本地全部通过；包含加权 M1、原有 90 天二购边界、客户级导出路由、Tableau 中间/最终表分离、Git 忽略规则、Notebook 公开输入检查及真实样例校验。

### 大文件、密钥与数据集

- `data/raw/` 中存在 9 个本地原始数据文件，均匹配忽略规则，不应提交。
- 本轮检查的可发布候选文件中，没有超过 10 MB 的文件；大体积原始数据与营销名单继续位于已忽略路径。
- 未扫描到常见的高置信度 API Key、访问令牌或私钥格式。
- 本地 `config/config.yaml` 存在且已忽略；发布前仍应确认没有被强制加入 Git。

### 本轮本地复核（2026-08-27）

- 67 项自动化测试通过；展示 Notebook 的 9 个代码单元实际执行成功。
- 添加许可证后，检查 54 个本地 Markdown/Notebook 链接，未发现断链或链接到被忽略的文件。
- 完整简历排除并添加许可证后，当前可发布候选为 100 个文件；不包含 `outputs/local/`、旧工具或完整个人简历。本轮再次检查大文件、14 份公开 CSV 表头、高置信度密钥格式，以及可发布 Markdown/LaTeX 中的邮箱和大陆手机号格式，均无异常。客户级展示仅限已审核说明页中的 6 条真实记录，不发布完整客户 CSV。
- Notebook 已保存的输出不含本机用户目录路径；输入文件运行前后哈希一致。
- 最终 TWBX、三张原生截图、Cohort 长表与矩阵的哈希均与整理前一致。
- 本次改名涉及的本地产物与受保护的最终文件共 17 个，迁移前后 SHA-256 全部一致；旧输出目录已不存在，没有删除数据。Notebook 的 9 个代码单元在无界面进程中再次执行通过，加权 M1 留存率仍为 0.48%。
- 仅调整输出路径、展示和发布结构；本轮未重新运行数据库建模、客户圈选或统计模型。

### 代码与数据许可

- 已添加标准 MIT `LICENSE`，版权署名使用已确认的 GitHub 账号 `Benjam1n77`。
- README 与数据说明明确区分项目代码和 Olist 数据许可；MIT 不覆盖数据集、派生汇总、真实样例及数据展示输出。

## 远程发布验证（2026-08-27）

- GitHub API 已确认仓库所属账号为 `Benjam1n77`、可见性为 `public`，默认分支为 `main`。
- 已逐一对比远程与本地 100 个发布文件的 Git blob SHA 和文件模式，全部一致；完整简历、原始数据、`outputs/local/` 和 `tools/legacy/` 均不在远程文件树中。
- README 在线页面已显示 MIT 许可和三页最终 Tableau 截图；三张图片均实际加载为 `1366 × 768`。
- Notebook 在线预览已成功渲染，并显示加权 M1 留存率 0.48%；README 中的 Tableau 目录链接可正确跳转，最终 TWBX 与三张 PNG 均可访问。
- 首次 [GitHub Actions 运行](https://github.com/Benjam1n77/olist-customer-lifecycle-analytics/actions/runs/33069294132)（提交 `41066ed`）已完成，结论为 `success`：流水线注册检查、pytest 与 Notebook 从头执行全部通过。
- 远程 pytest 实际结果为 **66 passed, 1 skipped**；跳过项是依赖本地完整客户名单的样例来源复核，符合不上传完整名单的发布边界。公开样例、指标和发布规则测试均正常运行。本地有完整源名单时，67 项全部通过。
- 后续提交的实时状态见 [GitHub Actions](https://github.com/Benjam1n77/olist-customer-lifecycle-analytics/actions)；上述固定运行链接保留本次发布验证证据。
