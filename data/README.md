# 数据说明

## 数据来源

本项目使用 Kaggle 公开数据集：

**Brazilian E-Commerce Public Dataset by Olist**

下载地址：<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>

本项目实际下载文件中的购买时间覆盖 2016 年 9 月至 2018 年 8 月；最大有效购买日期为 2018-08-29。不同资料页可能使用概括性月份描述，项目口径以实际文件校验结果为准。

## 匿名化与数据许可

[Olist 官方数据页](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 说明这是已经匿名化的公开商业数据，标注许可为 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。

本项目公开的 [真实客户样例](../docs/customer_samples.md) 来自该数据集，经项目 SQL 汇总与标签规则派生，再确定性选取。数据及其改编内容遵循原数据许可要求（署名、非商业、相同方式共享）。项目自行编写的代码采用 [MIT License](../LICENSE)，不替换原数据许可，也不覆盖汇总表、样例、图表、Tableau 内嵌数据或 Notebook 数据输出。

## 下载与放置方式

1. 登录 Kaggle，下载数据集压缩包（约 60 MB）。
2. 解压后，将以下 9 个 CSV 文件放入本项目的 `data/raw/` 目录：

```text
data/raw/
├── olist_customers_dataset.csv
├── olist_orders_dataset.csv
├── olist_order_items_dataset.csv
├── olist_order_payments_dataset.csv
├── olist_order_reviews_dataset.csv
├── olist_products_dataset.csv
├── olist_sellers_dataset.csv
├── olist_geolocation_dataset.csv
└── product_category_name_translation.csv
```

也可以使用 Kaggle API 下载：

```bash
pip install kaggle
kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw/
unzip data/raw/brazilian-ecommerce.zip -d data/raw/
```

## 目录约定

| 目录 | 用途 | 准备方式 |
| --- | --- | --- |
| `data/raw/` | 原始 CSV 文件 | 从数据源下载 |
| `data/interim/` | 导入前清洗/转换的中间文件 | 流程按需生成 |
| `data/processed/` | 分析用最终文件 | 流程按需生成 |

## 重要数据口径提示

- 本目录提供数据准备说明；原始数据需另行下载，处理后的汇总见 [分析输出](../outputs/README.md)。
- 客户复购识别必须使用 `customer_unique_id`；`customer_id` 是订单级客户标识，同一真实客户多次下单会生成多个 `customer_id`，不能直接用于跨订单复购统计。
- `olist_geolocation_dataset.csv` 的邮编坐标存在重复，不进入核心宽表；建模依据见 [数据字典](../docs/data_dictionary.md)。
