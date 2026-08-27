# Olist Customer Lifecycle Analytics

[English](README.md) | [简体中文](README.zh-CN.md)

An end-to-end analytics project using SQL, Python and Tableau to turn historical e-commerce transactions into customer segments, retention insights and proposed lifecycle campaigns.

Quick review: [Showcase notebook](notebooks/01_project_showcase.ipynb) · [Full report](docs/project_report.md) · [Tableau workbook](outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx)

> Language: this homepage is in English. The detailed reports, supporting documentation and notebook narrative remain in Simplified Chinese. The Tableau workbook and screenshots retain their original Chinese labels and annotations.

## Business questions

- How common is repeat purchasing, and which first-order characteristics are associated with a second purchase?
- Which customers are high-value, at risk or classified as churned under the project's lifecycle rules?
- How does delivery experience relate to satisfaction, and how can these findings inform campaign and service-recovery priorities?

The project produces analysis, rule-based customer lists and experiment proposals. It does not report live campaign results or measured business uplift.

## Data and technical approach

Source: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

The dataset contains **9 source tables, 99,441 orders and 96,096 unique customers**. Core customer analysis uses **96,478 delivered orders from 93,358 customers**. The analysis date is **2018-08-30**, one day after the latest valid purchase date.

Customer-level analysis uses `customer_unique_id`; `customer_id` is an order-level customer identifier and must not be used to identify repeat customers across orders.

| Layer | Implementation |
| --- | --- |
| SQL modeling | MySQL, CTEs and window functions; pre-aggregate items, payments and reviews before joining to avoid one-to-many row multiplication |
| Analytical marts | One row per order in `mart_order_summary`; one row per customer in `mart_customer_features` |
| Customer segmentation | RFM (Recency, Frequency, Monetary), lifecycle labels and priority-ordered campaign rules |
| Retention and experience | Mature-cohort retention, 90-day repeat purchasing excluding same-day orders, delivery/score comparisons and adjusted statistical associations |
| Python and BI | pandas, NumPy, matplotlib, seaborn, statsmodels and Tableau |
| Validation | Data-quality checks, SQL/Python metric reconciliation, pytest and notebook execution in GitHub Actions |

Modeling details: [data dictionary](docs/data_dictionary.md), [entity relationships](docs/er_diagram.md) and [metric definitions](docs/metric_definitions.md) — all in Chinese.

## Key findings

Reported metrics are traceable to the [verified metric index](docs/resume_metrics.md) and [SQL/Python reconciliation results](outputs/tables/cross_validation_results.csv).

| Finding | Observed result | Scope |
| --- | --- | --- |
| Repeat-purchase structure | **97.00%** one-time buyers; **3.00%** repeat buyers | Customers with delivered orders in the historical observation window |
| Weighted M1 retention | **0.48%** = **390 / 81,265** | **21** observable mature cohorts |
| 90-day repeat purchase | **1.2969%** = **980 / 75,563** | First-purchase customers with a complete 90-day observation window; same-day orders excluded |
| Time to repeat purchase | Median **29 days** | Customers who made a qualifying repeat purchase within that 90-day window |
| High-value churned customers | **10,915**, accounting for **30.89%** of historical payment value | Full high-value/churned group, before exclusive-segment priority rules |
| Delivery and satisfaction | Average score **2.57** for delayed orders vs **4.30** for on-time orders | **40.24%** lower, calculated using the underlying unrounded scores |

**Weighted M1 retention: 0.48%.** The KPI is `SUM(M1 retained customers) / SUM(M1 cohort size)` across all 21 observable mature cohorts. The trend chart only shows cohorts with `cohort_size >= 100`; that display filter does not change the KPI denominator.

The 90-day metric counts the earliest subsequent delivered order on **calendar days 1–90 after the first purchase**, excluding same-day orders. It is distinct from both calendar-month M1 retention and the full-window repeat-buyer rate.

The exclusive high-value/churned segment contains **10,326** customers: **589** members of the full group receive the higher-priority delivery-affected label instead.

### First-order characteristics and 90-day repeat purchasing

The following results come from the complete first-order experience model (**74,820 customers**), adjusting for customer state, main product category, first-purchase month and other first-order characteristics.

| First-order characteristic | Adjusted odds ratio | 95% confidence interval | p-value | Interpretation |
| --- | ---: | --- | ---: | --- |
| Multiple items | **1.4099** | 1.1349–1.7515 | 0.0019 | Positive association with repeat purchasing |
| Low review score (1–2) | **0.7371** | 0.5835–0.9311 | 0.0105 | Negative association with repeat purchasing |
| Delayed delivery | **0.9127** | 0.6890–1.2090 | 0.5242 | No statistically significant association after adjustment |

These are observational associations, not causal effects. An odds ratio is not a percentage-point change in purchase probability. Delivery's relationship with satisfaction must not be conflated with its adjusted relationship with repeat purchasing.

See the [90-day analysis report (Chinese)](docs/repeat_purchase_90d_analysis.md) and [exported model results](outputs/tables/repeat_purchase_90d_driver_summary.csv).

## Tableau dashboards

[Download the final packaged workbook](outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx) or inspect the [aggregate Tableau inputs](outputs/tableau/). The images below are the actual final Tableau exports, with their original Chinese labels and annotations.

### Customer Value Overview

![Customer Value Overview — original Tableau export with Chinese labels](outputs/tableau/dashboard_overview.png)

### Customer Segmentation & Retention

![Customer Segmentation and Retention — original Tableau export with Chinese labels](outputs/tableau/customer_segment.png)

### Delivery Experience & Satisfaction

![Delivery Experience and Satisfaction — original Tableau export with Chinese labels](outputs/tableau/delivery_analysis.png)

## Operational implications

- Test post-purchase nurturing and category recommendations, using the observed repeat-purchase window to inform experiment design.
- Prioritize high-value churned customers for rule-based win-back evaluation, while respecting the service-recovery priority rules.
- Treat low first-order ratings as a service-recovery signal; evaluate any subsequent repeat-purchase incentives separately.

These are proposed actions. The [A/B test designs (Chinese)](docs/ab_test_design.md) have not been implemented, and no campaign lift or causal impact is claimed.

## Reproduce the showcase

The notebook reads **9 published aggregate CSVs**. It needs no raw dataset, customer-level export or database connection, and does not refit the statistical models. Its narrative is in Chinese; saved outputs can also be viewed directly on GitHub.

Run from the repository root. GitHub Actions uses Python 3.11.

```bash
git clone https://github.com/Benjam1n77/olist-customer-lifecycle-analytics.git
cd olist-customer-lifecycle-analytics

python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python -m pytest -q
jupyter notebook notebooks/01_project_showcase.ipynb
```

To execute the notebook without a UI and keep the resulting copy local:

```bash
jupyter nbconvert --to notebook --execute notebooks/01_project_showcase.ipynb \
  --output-dir outputs/local/notebook_runs --ExecutePreprocessor.timeout=180
```

The notebook recomputes weighted M1 retention, checks aggregate consistency and verifies that its source files were not modified. The source-verification test for the complete customer list is intentionally skipped in a public clone, where that local-only file is absent.

<details>
<summary>Rebuild the full SQL/Python pipeline (MySQL required)</summary>

Use a dedicated local MySQL 8 database and install the `mysql` command-line client. Download the source CSVs into `data/raw/` using the [data setup guide (Chinese)](data/README.md).

Create a local configuration from [the example](config/config.example.yaml) if one does not already exist, then set your own database credentials. Do not overwrite an existing configuration or commit real credentials.

```bash
cp -n config/config.example.yaml config/config.yaml
```

After editing the configuration, initialize the schema and import the CSVs. Replace `your_mysql_user` with your configured local database user.

**Rebuild warning:** the schema script drops and recreates source tables, and the loader clears target tables before loading. Only run these steps against the dedicated project database.

```bash
mysql -u your_mysql_user -p < sql/01_create_database.sql
mysql -u your_mysql_user -p < sql/02_create_tables.sql
python -m src.load_data

python run_pipeline.py --check-config
python run_pipeline.py --list-stages
python run_pipeline.py --stage build_order_mart
python run_pipeline.py --stage build_customer_mart
python run_pipeline.py --stage segmentation
python run_pipeline.py --stage cohort
python run_pipeline.py --stage delivery
python run_pipeline.py --stage repeat_purchase_90d
python run_pipeline.py --stage campaign
python run_pipeline.py --stage export
python run_pipeline.py --stage validate_data
```

The final validation stage requires the preceding analytical tables. Pipeline implementation: [run_pipeline.py](run_pipeline.py). Full implementation notes: [project report (Chinese)](docs/project_report.md).

</details>

## Repository guide

| Location | Contents |
| --- | --- |
| `sql/`, `src/` | SQL modeling, Python analysis, validation and export code |
| `notebooks/` | Executed, aggregate-only project showcase |
| `docs/` | Reports, metric definitions, data dictionary and supporting analysis, primarily in Chinese |
| `outputs/tables/` | Published analytical summaries and reconciliation results |
| `outputs/figures/`, `outputs/tableau/` | Analysis figures, final Tableau workbook, aggregate inputs and screenshots |
| `tests/`, `.github/` | Automated checks and CI |
| `outputs/local/` | Full customer exports, intermediate tables and diagnostics generated when running the pipeline; not version-controlled |

Download the raw dataset separately to rebuild the pipeline. The repository includes aggregate results; complete customer exports and intermediate outputs are generated locally. Database credentials belong in local configuration or environment variables.

[Six real anonymized customer examples (Chinese)](docs/customer_samples.md) include field definitions and a deterministic selection method; they are not a random sample or evidence of actual marketing contact. See the [output guide (Chinese)](outputs/README.md).

## Limitations

- Historical data does not describe Olist's current business performance.
- Retention and rule-based churn labels depend on the observation window; later customer behavior is unobserved.
- The models identify adjusted associations, not causal effects or proven intervention benefits.
- The dataset lacks campaign exposure, browsing behavior and cost information needed for campaign attribution, profit or a full customer lifetime value estimate.

## License

The project's original Python, SQL, tests, configuration, workflows and notebook code cells are licensed under the [MIT License](LICENSE).

The Olist dataset and its adaptations — including aggregate tables, customer examples, data visualizations, embedded Tableau data and notebook data outputs — are **not covered by MIT**. They remain subject to [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) (attribution, non-commercial use and share-alike). The code license does not grant commercial-use rights to the data. Third-party dependencies retain their own licenses.
