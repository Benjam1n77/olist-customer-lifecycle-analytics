# ER 图（实体关系图）

> Olist 数据集共 9 张表，核心事实表为 `orders`，围绕订单关联客户、商品明细、支付与评价四个维度。

## 简化 ER 图

```mermaid
erDiagram
    customers ||--o{ orders : "customer_id"
    orders ||--o{ order_items : "order_id"
    orders ||--o{ order_payments : "order_id"
    orders ||--o{ order_reviews : "order_id"
    products ||--o{ order_items : "product_id"
    sellers ||--o{ order_items : "seller_id"
    translation ||--o{ products : "product_category_name"
    geolocation |o--o{ customers : "zip_code_prefix 弱关联"
    geolocation |o--o{ sellers : "zip_code_prefix 弱关联"

    customers {
        varchar customer_id PK
        varchar customer_unique_id
        varchar customer_zip_code_prefix
        varchar customer_city
        char customer_state
    }
    orders {
        varchar order_id PK
        varchar customer_id FK
        varchar order_status
        datetime order_purchase_timestamp
        datetime order_approved_at
        datetime order_delivered_carrier_date
        datetime order_delivered_customer_date
        datetime order_estimated_delivery_date
    }
    order_items {
        varchar order_id PK
        int order_item_id PK
        varchar product_id FK
        varchar seller_id FK
        datetime shipping_limit_date
        decimal price
        decimal freight_value
    }
    order_payments {
        varchar order_id PK
        int payment_sequential PK
        varchar payment_type
        int payment_installments
        decimal payment_value
    }
    order_reviews {
        varchar review_id PK
        varchar order_id FK
        tinyint review_score
        varchar review_comment_title
        text review_comment_message
        datetime review_creation_date
        datetime review_answer_timestamp
    }
    products {
        varchar product_id PK
        varchar product_category_name FK
        int product_name_lenght
        int product_description_lenght
        int product_photos_qty
        int product_weight_g
        int product_length_cm
        int product_height_cm
        int product_width_cm
    }
    sellers {
        varchar seller_id PK
        varchar seller_zip_code_prefix
        varchar seller_city
        char seller_state
    }
    translation {
        varchar product_category_name PK
        varchar product_category_name_english
    }
    geolocation {
        varchar geolocation_zip_code_prefix
        double geolocation_lat
        double geolocation_lng
        varchar geolocation_city
        char geolocation_state
    }
```

## 关系说明

| 关系 | 基数 | 说明 |
| --- | --- | --- |
| customers → orders | 1 : N | `customer_id` 为订单级标识；同一 `customer_unique_id` 可有多笔订单 |
| orders → order_items | 1 : N | 一笔订单可含多个商品行 |
| orders → order_payments | 1 : N | 一笔订单可有多条支付记录（组合支付） |
| orders → order_reviews | 1 : N | 一笔订单可能对应多条评价；原始文件另有重复 `review_id`，导入时按既定规则处理 |
| products → order_items | 1 : N | 同一商品可出现在多个订单 |
| sellers → order_items | 1 : N | 同一卖家可履约多个订单 |
| translation → products | 1 : N | 类别葡萄牙语 → 英文名 |
| geolocation ↔ customers / sellers | N : N（弱） | 仅通过邮编前缀关联，且邮编存在重复坐标，不进入核心建模 |

## 建模关键提示

1. `order_items`、`order_payments`、`order_reviews` 相对 `orders` 均为一对多，
   构建订单宽表时必须**先分别聚合到 `order_id` 粒度**再连接，否则产生多对多行数膨胀。
2. 复购与留存分析的主体是 `customer_unique_id`，而不是 `customer_id`。
3. `geolocation` 表不参与核心宽表构建（客户/卖家表已含城市与州字段）。
