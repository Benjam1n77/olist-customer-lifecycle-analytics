-- =============================================================
-- 03_data_quality_checks.sql
-- 目的：系统化数据质量检查，输出检查结果供 docs/data_quality_report.md 引用
-- 说明：
--   - 每个检查块使用 CTE 便于定位问题；
--   - 异常数 / 总行数 反映问题严重程度；
--   - 涉及时间逻辑的检查仅针对 order_status='delivered' 的记录；
--   - 该文件可重复执行，不修改任何表数据。
-- =============================================================

USE olist_ecommerce;

-- ==============================================================
-- A. 主键与唯一性
-- ==============================================================

-- A1. orders.order_id 是否唯一
SELECT
    'A1' AS check_id,
    'orders.order_id 唯一性' AS check_name,
    COUNT(DISTINCT order_id) AS distinct_count,
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_count
FROM orders;

-- A2. products.product_id 是否唯一
SELECT
    'A2' AS check_id,
    'products.product_id 唯一性' AS check_name,
    COUNT(DISTINCT product_id) AS distinct_count,
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(DISTINCT product_id) AS duplicate_count
FROM products;

-- A3. sellers.seller_id 是否唯一
SELECT
    'A3' AS check_id,
    'sellers.seller_id 唯一性' AS check_name,
    COUNT(DISTINCT seller_id) AS distinct_count,
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(DISTINCT seller_id) AS duplicate_count
FROM sellers;

-- A4. customers.customer_id 是否唯一
SELECT
    'A4' AS check_id,
    'customers.customer_id 唯一性' AS check_name,
    COUNT(DISTINCT customer_id) AS distinct_count,
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(DISTINCT customer_id) AS duplicate_count
FROM customers;

-- A5. customer_unique_id 对应多个 customer_id（复购客户的正常表现）
SELECT
    'A5' AS check_id,
    'customer_unique_id 对应多个 customer_id（复购客户）' AS check_name,
    COUNT(DISTINCT customer_unique_id) AS unique_customers,
    COUNT(*) AS total_customer_ids,
    COUNT(DISTINCT customer_unique_id) AS unique_ids,
    COUNT(*) - COUNT(DISTINCT customer_unique_id) AS extra_ids
FROM customers;

-- A6. order_reviews.review_id 是否唯一
SELECT
    'A6' AS check_id,
    'reviews.review_id 唯一性' AS check_name,
    COUNT(DISTINCT review_id) AS distinct_count,
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(DISTINCT review_id) AS duplicate_count
FROM order_reviews;

-- ==============================================================
-- B. 空值分布
-- ==============================================================

-- B1. orders 时间字段空值分布
SELECT
    'B1' AS check_id,
    'orders 时间字段空值分布' AS check_name,
    COUNT(*) AS total_orders,
    SUM(order_approved_at IS NULL) AS approved_null,
    SUM(order_delivered_carrier_date IS NULL) AS carrier_null,
    SUM(order_delivered_customer_date IS NULL) AS delivered_null,
    SUM(order_estimated_delivery_date IS NULL) AS estimated_null,
    CONCAT(ROUND(SUM(order_approved_at IS NULL) / COUNT(*) * 100, 2), '%') AS approved_null_pct,
    CONCAT(ROUND(SUM(order_delivered_customer_date IS NULL) / COUNT(*) * 100, 2), '%') AS delivered_null_pct
FROM orders;

-- B2. products 类别空值
SELECT
    'B2' AS check_id,
    'products.category_name 空值' AS check_name,
    COUNT(*) AS total_products,
    SUM(product_category_name IS NULL) AS category_null,
    CONCAT(ROUND(SUM(product_category_name IS NULL) / COUNT(*) * 100, 2), '%') AS null_pct
FROM products;

-- B3. order_reviews 评分空值
SELECT
    'B3' AS check_id,
    'reviews.review_score 空值' AS check_name,
    COUNT(*) AS total_reviews,
    SUM(review_score IS NULL) AS score_null,
    CONCAT(ROUND(SUM(review_score IS NULL) / COUNT(*) * 100, 2), '%') AS null_pct
FROM order_reviews;

-- B4. order_items 价格/运费空值
SELECT
    'B4' AS check_id,
    'order_items.price / freight_value 空值' AS check_name,
    COUNT(*) AS total_items,
    SUM(price IS NULL) AS price_null,
    SUM(freight_value IS NULL) AS freight_null,
    CONCAT(ROUND(SUM(price IS NULL) / COUNT(*) * 100, 2), '%') AS price_null_pct,
    CONCAT(ROUND(SUM(freight_value IS NULL) / COUNT(*) * 100, 2), '%') AS freight_null_pct
FROM order_items;

-- B5. order_payments 金额空值
SELECT
    'B5' AS check_id,
    'payments.payment_value 空值' AS check_name,
    COUNT(*) AS total_payments,
    SUM(payment_value IS NULL) AS value_null,
    CONCAT(ROUND(SUM(payment_value IS NULL) / COUNT(*) * 100, 2), '%') AS null_pct
FROM order_payments;

-- ==============================================================
-- C. 枚举值
-- ==============================================================

-- C1. order_status 枚举值分布
SELECT
    'C1' AS check_id,
    'orders.order_status 枚举值' AS check_name,
    order_status,
    COUNT(*) AS order_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM orders
GROUP BY order_status
ORDER BY order_count DESC;

-- C2. payment_type 枚举值分布
SELECT
    'C2' AS check_id,
    'payments.payment_type 枚举值' AS check_name,
    payment_type,
    COUNT(*) AS payment_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM order_payments
GROUP BY payment_type
ORDER BY payment_count DESC;

-- C3. review_score 分布（1-5 完整性）
SELECT
    'C3' AS check_id,
    'reviews.review_score 分布' AS check_name,
    review_score,
    COUNT(*) AS review_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM order_reviews
WHERE review_score IS NOT NULL
GROUP BY review_score
ORDER BY review_score;

-- ==============================================================
-- D. 时间逻辑（仅针对 delivered 订单，避免取消/未交付干扰）
-- ==============================================================

-- D1. 购买时间 > 审批时间（异常：购买在审批之后）
-- pct 分母为所有 delivered 且 approved 非空的订单总数
SELECT
    'D1' AS check_id,
    '订单：购买时间 > 审批时间（时间倒挂）' AS check_name,
    SUM(order_purchase_timestamp > order_approved_at) AS anomaly_count,
    COUNT(*) AS total_checked,
    CONCAT(ROUND(SUM(order_purchase_timestamp > order_approved_at) / COUNT(*) * 100, 2), '%') AS pct
FROM orders
WHERE order_status = 'delivered'
  AND order_approved_at IS NOT NULL;

-- D2. 审批时间 > 交付承运商时间
-- pct 分母为所有 delivered 且 approved/carrier 非空的订单总数
SELECT
    'D2' AS check_id,
    '订单：审批时间 > 交付承运商时间' AS check_name,
    SUM(order_approved_at > order_delivered_carrier_date) AS anomaly_count,
    COUNT(*) AS total_checked,
    CONCAT(ROUND(SUM(order_approved_at > order_delivered_carrier_date) / COUNT(*) * 100, 2), '%') AS pct
FROM orders
WHERE order_status = 'delivered'
  AND order_approved_at IS NOT NULL
  AND order_delivered_carrier_date IS NOT NULL;

-- D3. 交付承运商时间 > 实际签收时间
SELECT
    'D3' AS check_id,
    '订单：交付承运商时间 > 实际签收时间' AS check_name,
    SUM(order_delivered_carrier_date > order_delivered_customer_date) AS anomaly_count,
    COUNT(*) AS total_checked,
    CONCAT(ROUND(SUM(order_delivered_carrier_date > order_delivered_customer_date) / COUNT(*) * 100, 2), '%') AS pct
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_carrier_date IS NOT NULL
  AND order_delivered_customer_date IS NOT NULL;

-- D4. 实际签收时间早于购买时间
SELECT
    'D4' AS check_id,
    '订单：实际签收时间 < 购买时间' AS check_name,
    SUM(order_delivered_customer_date < order_purchase_timestamp) AS anomaly_count,
    COUNT(*) AS total_checked,
    CONCAT(ROUND(SUM(order_delivered_customer_date < order_purchase_timestamp) / COUNT(*) * 100, 2), '%') AS pct
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;

-- D5. 预计签收时间早于购买时间
SELECT
    'D5' AS check_id,
    '订单：预计签收时间 < 购买时间' AS check_name,
    SUM(order_estimated_delivery_date < order_purchase_timestamp) AS anomaly_count,
    COUNT(*) AS total_checked,
    CONCAT(ROUND(SUM(order_estimated_delivery_date < order_purchase_timestamp) / COUNT(*) * 100, 2), '%') AS pct
FROM orders
WHERE order_estimated_delivery_date IS NOT NULL;

-- ==============================================================
-- E. 数值合理性
-- ==============================================================

-- E1. 商品价格 <= 0
SELECT
    'E1' AS check_id,
    'order_items.price <= 0' AS check_name,
    SUM(price <= 0) AS anomaly_count,
    COUNT(*) AS total_non_null,
    CONCAT(ROUND(SUM(price <= 0) / COUNT(*) * 100, 2), '%') AS pct
FROM order_items
WHERE price IS NOT NULL;

-- E2. 运费 < 0
SELECT
    'E2' AS check_id,
    'order_items.freight_value < 0' AS check_name,
    SUM(freight_value < 0) AS anomaly_count,
    COUNT(*) AS total_non_null,
    CONCAT(ROUND(SUM(freight_value < 0) / COUNT(*) * 100, 2), '%') AS pct
FROM order_items
WHERE freight_value IS NOT NULL;

-- E3. 支付金额 <= 0
SELECT
    'E3' AS check_id,
    'payments.payment_value <= 0' AS check_name,
    SUM(payment_value <= 0) AS anomaly_count,
    COUNT(*) AS total_non_null,
    CONCAT(ROUND(SUM(payment_value <= 0) / COUNT(*) * 100, 2), '%') AS pct
FROM order_payments
WHERE payment_value IS NOT NULL;

-- E4. 分期数 < 0
SELECT
    'E4' AS check_id,
    'payments.payment_installments < 0' AS check_name,
    SUM(payment_installments < 0) AS anomaly_count,
    COUNT(*) AS total_non_null,
    CONCAT(ROUND(SUM(payment_installments < 0) / COUNT(*) * 100, 2), '%') AS pct
FROM order_payments
WHERE payment_installments IS NOT NULL;

-- E5. 商品重量 <= 0
SELECT
    'E5' AS check_id,
    'products.product_weight_g <= 0' AS check_name,
    SUM(product_weight_g <= 0) AS anomaly_count,
    COUNT(*) AS total_non_null,
    CONCAT(ROUND(SUM(product_weight_g <= 0) / COUNT(*) * 100, 2), '%') AS pct
FROM products
WHERE product_weight_g IS NOT NULL;

-- ==============================================================
-- F. 关联完整性
-- ==============================================================

-- F1. 订单找不到客户（customer_id 孤立）
SELECT
    'F1' AS check_id,
    'orders 找不到 customers（孤立订单）' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM orders) * 100, 2), '%') AS pct
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- F2. 商品明细找不到订单（order_id 孤立）
SELECT
    'F2' AS check_id,
    'order_items 找不到 orders（孤立商品明细）' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM order_items) * 100, 2), '%') AS pct
FROM order_items oi
LEFT JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_id IS NULL;

-- F3. 支付找不到订单
SELECT
    'F3' AS check_id,
    'payments 找不到 orders（孤立支付）' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM order_payments) * 100, 2), '%') AS pct
FROM order_payments p
LEFT JOIN orders o ON p.order_id = o.order_id
WHERE o.order_id IS NULL;

-- F4. 评价找不到订单
SELECT
    'F4' AS check_id,
    'reviews 找不到 orders（孤立评价）' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM order_reviews) * 100, 2), '%') AS pct
FROM order_reviews r
LEFT JOIN orders o ON r.order_id = o.order_id
WHERE o.order_id IS NULL;

-- F5. 商品找不到商品维度
SELECT
    'F5' AS check_id,
    'order_items.product_id 找不到 products（孤立商品）' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM order_items) * 100, 2), '%') AS pct
FROM order_items oi
LEFT JOIN products p ON oi.product_id = p.product_id
WHERE p.product_id IS NULL;

-- F6. 类别找不到翻译
SELECT
    'F6' AS check_id,
    'products.category 无翻译记录' AS check_name,
    COUNT(*) AS orphan_count,
    CONCAT(ROUND(COUNT(*) / (SELECT COUNT(*) FROM products) * 100, 2), '%') AS pct
FROM products p
LEFT JOIN translation t ON p.product_category_name = t.product_category_name
WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL;

-- ==============================================================
-- G. 多重记录（订单粒度的多行情况）
-- ==============================================================

-- G1. 每订单对应商品行数分布
SELECT
    'G1' AS check_id,
    '每订单对应 order_items 行数分布' AS check_name,
    items_per_order,
    COUNT(*) AS order_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM (
    SELECT order_id, COUNT(*) AS items_per_order
    FROM order_items
    GROUP BY order_id
) t
GROUP BY items_per_order
ORDER BY items_per_order;

-- G2. 每订单对应支付行数分布
SELECT
    'G2' AS check_id,
    '每订单对应 payments 行数分布' AS check_name,
    payments_per_order,
    COUNT(*) AS order_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM (
    SELECT order_id, COUNT(*) AS payments_per_order
    FROM order_payments
    GROUP BY order_id
) t
GROUP BY payments_per_order
ORDER BY payments_per_order;

-- G3. 每订单对应评价行数分布
SELECT
    'G3' AS check_id,
    '每订单对应 reviews 行数分布' AS check_name,
    reviews_per_order,
    COUNT(*) AS order_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM (
    SELECT order_id, COUNT(*) AS reviews_per_order
    FROM order_reviews
    GROUP BY order_id
) t
GROUP BY reviews_per_order
ORDER BY reviews_per_order;

-- G4. 同订单是否有多条评价（重复评价）
SELECT
    'G4' AS check_id,
    '存在重复评价（同订单多条记录）的订单数' AS check_name,
    COUNT(DISTINCT order_id) AS orders_with_duplicate_reviews
FROM (
    SELECT order_id, COUNT(*) AS cnt
    FROM order_reviews
    GROUP BY order_id
    HAVING cnt > 1
) t;
