-- =============================================================
-- 05_payment_aggregation.sql
-- 目的：将 order_payments 聚合到 order_id 粒度，建立 order_payment_agg
-- 粒度：一行一笔订单
-- 口径：
--   - payment_amount        = SUM(payment_value) 支付记录金额合计
--   - payment_record_count  = 支付记录条数
--   - payment_type_count    = 去重支付方式数
--   - main_payment_type     = 支付金额最高的方式；并列时取 payment_type 字典序较小者
--   - max_installments      = 最大分期数
-- 注意：payment_amount 与订单商品+运费(item_amount)不假设相等，
--       二者差异在 sql/13_validation_queries.sql 中量化检查
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS order_payment_agg;
CREATE TABLE order_payment_agg AS
WITH payment_base AS (
    -- 粒度：一行一笔订单；基础金额与计数
    SELECT
        order_id,
        ROUND(SUM(payment_value), 2)    AS payment_amount,
        COUNT(*)                        AS payment_record_count,
        COUNT(DISTINCT payment_type)    AS payment_type_count,
        MAX(payment_installments)       AS max_installments
    FROM order_payments
    GROUP BY order_id
),
type_amount AS (
    -- 粒度：订单 × 支付方式；按方式汇总金额，用于判定主支付方式
    SELECT
        order_id,
        payment_type,
        SUM(payment_value) AS type_amount
    FROM order_payments
    GROUP BY order_id, payment_type
),
type_ranked AS (
    -- 粒度：订单 × 支付方式；金额降序排名（并列时按类型名确定性取一）
    SELECT
        order_id,
        payment_type,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY type_amount DESC, payment_type ASC
        ) AS rn
    FROM type_amount
)
SELECT
    pb.order_id,
    pb.payment_amount,
    pb.payment_record_count,
    pb.payment_type_count,
    tr.payment_type AS main_payment_type,
    pb.max_installments
FROM payment_base pb
LEFT JOIN type_ranked tr
    ON pb.order_id = tr.order_id AND tr.rn = 1;

-- 添加主键（CTAS 不自带约束）
ALTER TABLE order_payment_agg ADD PRIMARY KEY (order_id);

-- 验证：聚合行数应等于 order_payments 的去重订单数；金额合计聚合前后一致
SELECT
    '05_validation_rows' AS check_name,
    (SELECT COUNT(*) FROM order_payment_agg) AS agg_rows,
    (SELECT COUNT(DISTINCT order_id) FROM order_payments) AS distinct_orders,
    (SELECT COUNT(*) FROM order_payment_agg) = (SELECT COUNT(DISTINCT order_id) FROM order_payments) AS is_match;

SELECT
    '05_validation_amount' AS check_name,
    (SELECT ROUND(SUM(payment_amount), 2) FROM order_payment_agg) AS agg_total,
    (SELECT ROUND(SUM(payment_value), 2) FROM order_payments) AS raw_total,
    (SELECT ROUND(SUM(payment_amount), 2) FROM order_payment_agg) = (SELECT ROUND(SUM(payment_value), 2) FROM order_payments) AS is_match;
