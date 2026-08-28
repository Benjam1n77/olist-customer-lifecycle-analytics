-- =============================================================
-- 07_build_order_mart.sql
-- 目的：构建订单粒度分析宽表 mart_order_summary（一行一笔订单）
-- 依赖：先执行 04/05/06 建立三张聚合表（避免多对多 JOIN 行数膨胀）
-- 口径：
--   - 以 orders 为主表 LEFT JOIN 三张聚合表与客户表：
--     个别订单可能没有商品行/支付记录/评价（如 created/canceled 状态），保留为 NULL
--   - delivery_days            = DATEDIFF(实际签收日期, 购买日期)
--   - estimated_delivery_days  = DATEDIFF(预计签收日期, 购买日期)
--   - delay_days               = DATEDIFF(实际签收日期, 预计签收日期)
--   - is_delayed               = 实际签收日期 > 预计签收日期（1/0；缺时间为 NULL）
--   - is_low_score             = review_score <= 2（1/0；无评价为 NULL）
--   - purchase_date/month 由购买时间戳派生
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS mart_order_summary;
CREATE TABLE mart_order_summary AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp                          AS purchase_datetime,
    DATE(o.order_purchase_timestamp)                    AS purchase_date,
    DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m')    AS purchase_month,
    o.order_approved_at                                 AS approved_datetime,
    o.order_delivered_carrier_date                      AS carrier_datetime,
    o.order_delivered_customer_date                     AS delivered_datetime,
    o.order_estimated_delivery_date                     AS estimated_delivery_datetime,
    c.customer_city,
    c.customer_state,
    -- 商品聚合（无商品行的订单为 NULL）
    ia.item_count,
    ia.distinct_product_count,
    ia.seller_count,
    ia.product_category_count,
    ia.goods_amount,
    ia.freight_amount,
    ia.item_amount,
    -- 支付聚合（无支付记录的订单为 NULL）
    pa.payment_amount,
    pa.main_payment_type,
    pa.max_installments,
    -- 类别与评价
    ia.main_category,
    ra.review_count,
    ra.review_score,
    ra.has_review_comment,
    -- 履约时效派生字段
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
         AND o.order_purchase_timestamp IS NOT NULL
        THEN DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp)
    END                                                 AS delivery_days,
    CASE
        WHEN o.order_estimated_delivery_date IS NOT NULL
         AND o.order_purchase_timestamp IS NOT NULL
        THEN DATEDIFF(o.order_estimated_delivery_date, o.order_purchase_timestamp)
    END                                                 AS estimated_delivery_days,
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
         AND o.order_estimated_delivery_date IS NOT NULL
        THEN DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date)
    END                                                 AS delay_days,
    CASE
        WHEN o.order_delivered_customer_date IS NULL
          OR o.order_estimated_delivery_date IS NULL THEN NULL
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1
        ELSE 0
    END                                                 AS is_delayed,
    CASE
        WHEN ra.review_score IS NULL THEN NULL
        WHEN ra.review_score <= 2 THEN 1
        ELSE 0
    END                                                 AS is_low_score
FROM orders o
LEFT JOIN customers c          ON o.customer_id = c.customer_id
LEFT JOIN order_item_agg ia    ON o.order_id = ia.order_id
LEFT JOIN order_payment_agg pa ON o.order_id = pa.order_id
LEFT JOIN order_review_agg ra  ON o.order_id = ra.order_id;

-- 添加主键与常用索引
ALTER TABLE mart_order_summary ADD PRIMARY KEY (order_id);
ALTER TABLE mart_order_summary
    ADD KEY idx_mart_unique_id (customer_unique_id),
    ADD KEY idx_mart_purchase_month (purchase_month),
    ADD KEY idx_mart_status (order_status),
    ADD KEY idx_mart_state (customer_state);

-- 验证 1：一行一订单
SELECT
    '07_validation_grain' AS check_name,
    COUNT(*) AS mart_rows,
    COUNT(DISTINCT order_id) AS distinct_orders,
    COUNT(*) = COUNT(DISTINCT order_id) AS is_one_row_per_order
FROM mart_order_summary;

-- 验证 2：行数与 orders 一致（LEFT JOIN 未产生膨胀或丢失）
SELECT
    '07_validation_rows' AS check_name,
    (SELECT COUNT(*) FROM mart_order_summary) AS mart_rows,
    (SELECT COUNT(*) FROM orders) AS orders_rows,
    (SELECT COUNT(*) FROM mart_order_summary) = (SELECT COUNT(*) FROM orders) AS is_match;

-- 验证 3：item_amount 与 payment_amount 差异量化（不得假设相等）
SELECT
    '07_validation_amount_diff' AS check_name,
    COUNT(*) AS orders_with_both,
    SUM(ROUND(item_amount, 2) = ROUND(payment_amount, 2)) AS exact_match,
    SUM(ABS(item_amount - payment_amount) <= 0.05) AS within_5cents,
    SUM(ABS(item_amount - payment_amount) > 0.05) AS diff_gt_5cents,
    ROUND(AVG(payment_amount - item_amount), 2) AS avg_diff
FROM mart_order_summary
WHERE item_amount IS NOT NULL AND payment_amount IS NOT NULL;
