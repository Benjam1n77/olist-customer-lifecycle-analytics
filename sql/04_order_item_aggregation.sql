-- =============================================================
-- 04_order_item_aggregation.sql
-- 目的：将 order_items 聚合到 order_id 粒度，建立 order_item_agg
-- 粒度：一行一笔订单
-- 口径：
--   - goods_amount   = SUM(price)          订单商品价格合计
--   - freight_amount = SUM(freight_value)  订单运费合计
--   - item_amount    = goods_amount + freight_amount
--   - main_category  = 订单中商品金额(price)最高的类别；
--                      金额并列时取 product_category_name 字典序较小者（确定性规则）；
--                      类别为 NULL 的商品行不参与判定，若整单商品均无类别则为 NULL
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS order_item_agg;
CREATE TABLE order_item_agg AS
WITH item_with_category AS (
    -- 粒度：订单商品行；关联商品类别（保留无类别行）
    SELECT
        oi.order_id,
        oi.product_id,
        oi.seller_id,
        oi.price,
        oi.freight_value,
        p.product_category_name
    FROM order_items oi
    LEFT JOIN products p ON oi.product_id = p.product_id
),
order_base AS (
    -- 粒度：一行一笔订单；基础计数与金额
    SELECT
        order_id,
        COUNT(*)                       AS item_count,
        COUNT(DISTINCT product_id)     AS distinct_product_count,
        COUNT(DISTINCT seller_id)      AS seller_count,
        COUNT(DISTINCT product_category_name) AS product_category_count,
        ROUND(SUM(price), 2)           AS goods_amount,
        ROUND(SUM(freight_value), 2)   AS freight_amount,
        ROUND(SUM(price) + SUM(freight_value), 2) AS item_amount
    FROM item_with_category
    GROUP BY order_id
),
category_amount AS (
    -- 粒度：订单 × 类别；按类别汇总商品金额，用于判定主类别
    SELECT
        order_id,
        product_category_name,
        SUM(price) AS category_goods_amount
    FROM item_with_category
    WHERE product_category_name IS NOT NULL
    GROUP BY order_id, product_category_name
),
category_ranked AS (
    -- 粒度：订单 × 类别；金额降序排名（并列时按类别名确定性取一）
    SELECT
        order_id,
        product_category_name,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY category_goods_amount DESC, product_category_name ASC
        ) AS rn
    FROM category_amount
)
SELECT
    ob.order_id,
    ob.item_count,
    ob.distinct_product_count,
    ob.seller_count,
    ob.product_category_count,
    ob.goods_amount,
    ob.freight_amount,
    ob.item_amount,
    cr.product_category_name AS main_category
FROM order_base ob
LEFT JOIN category_ranked cr
    ON ob.order_id = cr.order_id AND cr.rn = 1;

-- 添加主键与索引（CTAS 不自带约束）
ALTER TABLE order_item_agg ADD PRIMARY KEY (order_id);

-- 验证：聚合行数应等于 order_items 的去重订单数
SELECT
    '04_validation' AS check_name,
    (SELECT COUNT(*) FROM order_item_agg) AS agg_rows,
    (SELECT COUNT(DISTINCT order_id) FROM order_items) AS distinct_orders,
    (SELECT COUNT(*) FROM order_item_agg) = (SELECT COUNT(DISTINCT order_id) FROM order_items) AS is_match;
