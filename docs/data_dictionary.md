# 数据字典（Data Dictionary）

> 依据本地 `data/raw/` 中 9 个 CSV 文件的实际表头与抽样检查编写。
> 行数为 CSV 数据行数（不含表头），由本地 `wc -l` 统计。

## 表关系总览

```text
orders.customer_id                     -> customers.customer_id
order_items.order_id                   -> orders.order_id
order_items.product_id                 -> products.product_id
order_items.seller_id                  -> sellers.seller_id
payments.order_id                      -> orders.order_id
reviews.order_id                       -> orders.order_id
products.product_category_name         -> translation.product_category_name
customers.customer_zip_code_prefix     -> geolocation.geolocation_zip_code_prefix（弱关联，仅用于地区补充）
sellers.seller_zip_code_prefix         -> geolocation.geolocation_zip_code_prefix（弱关联，仅用于地区补充）
```

重要口径：

- `customers.customer_id` 是**订单级**客户标识：同一真实客户多次下单会产生多个 `customer_id`。
- `customers.customer_unique_id` 是**真实客户**标识：所有复购、留存、流失分析必须基于它。

---

## 1. customers（客户表）

- 来源文件：`olist_customers_dataset.csv`
- 数据行数：99,441
- 数据粒度：一行一个订单级客户标识（`customer_id`）
- 主键：`customer_id`
- 候选键：无（`customer_unique_id` 与 `customer_id` 一对多，非唯一）
- 外键：无（被 `orders.customer_id` 引用）

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| customer_id | VARCHAR(32) | 订单级客户 ID，与订单一一对应 |
| customer_unique_id | VARCHAR(32) | 真实客户唯一 ID，复购分析核心键 |
| customer_zip_code_prefix | VARCHAR(5) | 客户邮编前 5 位 |
| customer_city | VARCHAR(64) | 客户城市（小写，含变音符号） |
| customer_state | CHAR(2) | 客户州（巴西州缩写，如 SP） |

- 数据质量风险：同一 `customer_unique_id` 对应多个 `customer_id`（复购的正常表现，需量化）；城市名拼写与变音符号不规范。
- 是否进入核心分析：**是**（客户维度、地区维度、复购识别的基础）。

## 2. orders（订单表）

- 来源文件：`olist_orders_dataset.csv`
- 数据行数：99,441
- 数据粒度：一行一笔订单
- 主键：`order_id`
- 外键：`customer_id -> customers.customer_id`

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| order_id | VARCHAR(32) | 订单 ID |
| customer_id | VARCHAR(32) | 订单级客户 ID |
| order_status | VARCHAR(20) | 订单状态（delivered / shipped / canceled 等） |
| order_purchase_timestamp | DATETIME | 购买时间 |
| order_approved_at | DATETIME | 审批通过时间（可为空） |
| order_delivered_carrier_date | DATETIME | 交付承运商时间（可为空） |
| order_delivered_customer_date | DATETIME | 实际签收时间（可为空） |
| order_estimated_delivery_date | DATETIME | 预计签收时间 |

- 数据质量风险：履约链路时间字段存在空值（尤其取消订单）；可能出现时间倒挂（如审批早于购买）；`order_status` 枚举需在质量检查中确认。
- 是否进入核心分析：**是**（全链路事实表核心）。

## 3. order_items（订单商品明细表）

- 来源文件：`olist_order_items_dataset.csv`
- 数据行数：112,650
- 数据粒度：一行一个订单商品行（一笔订单可有多行）
- 主键：`(order_id, order_item_id)` 复合主键
- 外键：`order_id -> orders.order_id`；`product_id -> products.product_id`；`seller_id -> sellers.seller_id`

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| order_id | VARCHAR(32) | 订单 ID |
| order_item_id | INT | 订单内商品行序号（1 起） |
| product_id | VARCHAR(32) | 商品 ID |
| seller_id | VARCHAR(32) | 卖家 ID |
| shipping_limit_date | DATETIME | 卖家发货期限时间 |
| price | DECIMAL(10,2) | 商品单价（BRL） |
| freight_value | DECIMAL(10,2) | 该行运费（BRL） |

- 数据质量风险：同一订单多行导致与 payments/reviews 直接 JOIN 会行数膨胀（必须先聚合到订单粒度）；价格或运费可能存在异常值。
- 是否进入核心分析：**是**（金额、品类、件数指标来源）。

## 4. order_payments（订单支付表）

- 来源文件：`olist_order_payments_dataset.csv`
- 数据行数：103,886
- 数据粒度：一行一条支付记录（一笔订单可多条，如组合支付）
- 主键：`(order_id, payment_sequential)` 复合主键
- 外键：`order_id -> orders.order_id`

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| order_id | VARCHAR(32) | 订单 ID |
| payment_sequential | INT | 支付序号（1 起） |
| payment_type | VARCHAR(20) | 支付方式（credit_card / boleto / voucher 等） |
| payment_installments | INT | 分期数 |
| payment_value | DECIMAL(10,2) | 支付金额（BRL） |

- 数据质量风险：存在无支付记录的订单（行数少于订单数，需在质量检查中确认缺失订单状态）；支付总额与商品+运费总额可能存在差异，不得假设二者相等。
- 是否进入核心分析：**是**（金额与支付行为指标来源）。

## 5. order_reviews（订单评价表）

- 来源文件：`olist_order_reviews_dataset.csv`
- 数据行数：CSV 实际记录 99,224 条（物理行数 104,719 被评价文本内嵌换行符抬高，统计需用 CSV 解析器）
- 数据粒度：一行一条评价（评价数多于订单数，可能存在重复评价）
- 主键：`review_id`（需在质量检查中验证唯一性）
- 外键：`order_id -> orders.order_id`

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| review_id | VARCHAR(32) | 评价 ID |
| order_id | VARCHAR(32) | 订单 ID |
| review_score | TINYINT | 评分（1–5） |
| review_comment_title | VARCHAR(100) | 评价标题（大量为空） |
| review_comment_message | TEXT | 评价正文（大量为空） |
| review_creation_date | DATETIME | 评价问卷创建时间 |
| review_answer_timestamp | DATETIME | 用户提交评价时间 |

- 数据质量风险：评价行数多于订单行数，同一订单可能有多条评价（聚合规则需在指标文档明确）；评论文本字段空值率高。
- 是否进入核心分析：**是**（满意度与履约体验分析核心）。

## 6. products（商品表）

- 来源文件：`olist_products_dataset.csv`
- 数据行数：32,951
- 数据粒度：一行一个商品
- 主键：`product_id`
- 外键：`product_category_name -> translation.product_category_name`

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| product_id | VARCHAR(32) | 商品 ID |
| product_category_name | VARCHAR(64) | 商品类别（葡萄牙语，可为空） |
| product_name_lenght | INT | 商品名长度（原始拼写如此） |
| product_description_lenght | INT | 商品描述长度 |
| product_photos_qty | INT | 图片数量 |
| product_weight_g | INT | 重量（克） |
| product_length_cm | INT | 长度（厘米） |
| product_height_cm | INT | 高度（厘米） |
| product_width_cm | INT | 宽度（厘米） |

- 数据质量风险：类别字段存在空值；部分类别可能无英文翻译；物理属性字段可能有异常值（如 0 或极大值）。
- 是否进入核心分析：**是**（品类偏好分析依赖该表）。

## 7. sellers（卖家表）

- 来源文件：`olist_sellers_dataset.csv`
- 数据行数：3,095
- 数据粒度：一行一个卖家
- 主键：`seller_id`
- 外键：无（被 `order_items.seller_id` 引用）

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| seller_id | VARCHAR(32) | 卖家 ID |
| seller_zip_code_prefix | VARCHAR(5) | 卖家邮编前 5 位 |
| seller_city | VARCHAR(64) | 卖家城市 |
| seller_state | CHAR(2) | 卖家州 |

- 数据质量风险：体量小、风险低；城市拼写不规范同 customers。
- 是否进入核心分析：**辅助**（本项目以客户为中心，卖家仅用于多卖家订单识别，不展开卖家分析）。

## 8. geolocation（地理位置表）

- 来源文件：`olist_geolocation_dataset.csv`
- 数据行数：1,000,163
- 数据粒度：一行一个邮编-坐标记录（同一邮编前缀可能有多条坐标）
- 主键：无（存在重复邮编）
- 外键：无（被客户/卖家邮编弱关联）

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| geolocation_zip_code_prefix | VARCHAR(5) | 邮编前 5 位 |
| geolocation_lat | DOUBLE | 纬度 |
| geolocation_lng | DOUBLE | 经度 |
| geolocation_city | VARCHAR(64) | 城市 |
| geolocation_state | CHAR(2) | 州 |

- 数据质量风险：体量大（约 58 MB）；同一邮编对应多坐标，直接使用会产生多对多膨胀；城市名存在变音符号差异。
- 是否进入核心分析：**否（默认）**。客户/卖家表已自带 city 与 state，满足地区分析需求；如需地图可视化再单独聚合使用。导入时仍建表保留，便于后续扩展。

## 9. translation（类别翻译表）

- 来源文件：`product_category_name_translation.csv`
- 数据行数：70
- 数据粒度：一行一个类别翻译
- 主键：`product_category_name`
- 外键：无（被 `products.product_category_name` 引用）

| 字段 | 类型建议 | 业务含义 |
| --- | --- | --- |
| product_category_name | VARCHAR(64) | 类别名（葡萄牙语） |
| product_category_name_english | VARCHAR(64) | 类别名（英文） |

- 数据质量风险：商品表中可能存在未收录在此表的类别名；该文件表头无引号（与其他文件风格不同，导入时需注意）。
- 是否进入核心分析：**是**（品类展示与报表可读性依赖英文类别名）。

---

## 建模注意事项（贯穿后续阶段）

1. **禁止**在未聚合时执行 `orders JOIN order_items JOIN order_payments JOIN order_reviews`：商品行与支付行均为一对多，直接连接会行数膨胀。必须先各自聚合到 `order_id` 粒度再连接。
2. 复购、留存、流失一律以 `customer_unique_id` 为主体。
3. 金额字段统一使用 `DECIMAL(10,2)`，时间字段统一使用 `DATETIME`。
4. 字符集统一 `utf8mb4`（城市名含葡萄牙语变音符号）。
