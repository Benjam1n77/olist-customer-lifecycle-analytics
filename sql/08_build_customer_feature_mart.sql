-- =============================================================
-- 08_build_customer_feature_mart.sql
-- 目的：构建用户粒度特征宽表 mart_customer_features
-- 粒度：一行一个 customer_unique_id（真实客户）
-- 依赖：mart_order_summary（阶段 4）
-- 口径（详见 docs/metric_definitions.md）：
--   - 仅纳入至少有一笔 delivered 订单的客户（93,358 人）；
--     2,738 个仅有无效订单（canceled 等）的客户不进入核心分析
--   - 核心价值/行为指标一律只统计 delivered 订单
--   - order_count = DISTINCT order_id（delivered）
--   - analysis_date = 最大有效购买日期 + 1 天 = 2018-08-30（数据推导，非手工指定）
--   - recency_days = DATEDIFF(analysis_date, last_purchase_date)
--   - favorite_category：按消费金额(SUM price，商品明细级)判定；
--     并列取类别名字典序较小者；无类别消费则为 NULL
--   - favorite_payment_type：按支付金额(SUM payment_value)判定；并列取字典序较小者
--   - customer_state：取最近一笔 delivered 订单对应的州；
--     同日多单按 order_id 字典序取最大者（确定性规则）
--   - average_delay_days = AVG(delay_days)，含负值（提前送达），
--     仅统计 delay_days 非空的订单
--   - delayed_order_rate / low_score_rate 分母为可判定订单数
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS mart_customer_features;
CREATE TABLE mart_customer_features AS
WITH analysis AS (
    -- 观察日：最大有效购买日期 + 1 天
    SELECT DATE_ADD(MAX(purchase_date), INTERVAL 1 DAY) AS analysis_date
    FROM mart_order_summary
    WHERE order_status = 'delivered'
),
valid_orders AS (
    -- 粒度：一行一笔有效订单
    SELECT *
    FROM mart_order_summary
    WHERE order_status = 'delivered'
),
customer_base AS (
    -- 粒度：一行一个真实客户；首末购、频次与金额
    SELECT
        v.customer_unique_id,
        MIN(v.purchase_date)                                   AS first_purchase_date,
        MAX(v.purchase_date)                                   AS last_purchase_date,
        DATEDIFF(MAX(v.purchase_date), MIN(v.purchase_date))   AS customer_tenure_days,
        DATEDIFF(a.analysis_date, MAX(v.purchase_date))        AS recency_days,
        COUNT(DISTINCT v.order_id)                             AS order_count,
        CASE WHEN COUNT(DISTINCT v.order_id) >= 2 THEN 1 ELSE 0 END AS repeat_purchase_flag,
        ROUND(SUM(v.goods_amount), 2)                          AS total_goods_amount,
        ROUND(SUM(v.freight_amount), 2)                        AS total_freight_amount,
        ROUND(SUM(v.payment_amount), 2)                        AS total_payment,
        ROUND(SUM(v.payment_amount) / COUNT(DISTINCT v.order_id), 2) AS average_order_value,
        ROUND(AVG(v.item_count), 2)                            AS average_item_count
    FROM valid_orders v
    CROSS JOIN analysis a
    GROUP BY v.customer_unique_id, a.analysis_date
),
-- 偏好类别：商品明细级消费金额（delivered 订单）
category_spend AS (
    SELECT
        v.customer_unique_id,
        p.product_category_name,
        SUM(oi.price) AS category_spend
    FROM valid_orders v
    JOIN order_items oi ON v.order_id = oi.order_id
    JOIN products p     ON oi.product_id = p.product_id
    WHERE p.product_category_name IS NOT NULL
    GROUP BY v.customer_unique_id, p.product_category_name
),
category_ranked AS (
    SELECT
        customer_unique_id,
        product_category_name,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY category_spend DESC, product_category_name ASC
        ) AS rn
    FROM category_spend
),
-- 偏好支付方式：支付记录级金额（delivered 订单）
payment_spend AS (
    SELECT
        v.customer_unique_id,
        op.payment_type,
        SUM(op.payment_value) AS type_spend
    FROM valid_orders v
    JOIN order_payments op ON v.order_id = op.order_id
    GROUP BY v.customer_unique_id, op.payment_type
),
payment_ranked AS (
    SELECT
        customer_unique_id,
        payment_type,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY type_spend DESC, payment_type ASC
        ) AS rn
    FROM payment_spend
),
-- 履约与评价体验（delivered 订单）
experience AS (
    SELECT
        customer_unique_id,
        ROUND(AVG(delivery_days), 2)                            AS average_delivery_days,
        SUM(is_delayed = 1)                                     AS delayed_order_count,
        ROUND(SUM(is_delayed = 1) / NULLIF(SUM(is_delayed IS NOT NULL), 0), 4) AS delayed_order_rate,
        ROUND(AVG(delay_days), 2)                               AS average_delay_days,
        ROUND(AVG(review_score), 2)                             AS average_review_score,
        SUM(is_low_score = 1)                                   AS low_score_order_count,
        ROUND(SUM(is_low_score = 1) / NULLIF(SUM(is_low_score IS NOT NULL), 0), 4) AS low_score_rate
    FROM valid_orders
    GROUP BY customer_unique_id
),
-- 地区：最近一笔 delivered 订单对应的州（同日按 order_id 字典序确定性取一）
latest_order AS (
    SELECT
        customer_unique_id,
        customer_state,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY purchase_date DESC, order_id DESC
        ) AS rn
    FROM valid_orders
)
SELECT
    cb.customer_unique_id,
    cb.first_purchase_date,
    cb.last_purchase_date,
    cb.customer_tenure_days,
    cb.recency_days,
    cb.order_count,
    cb.repeat_purchase_flag,
    cb.total_goods_amount,
    cb.total_freight_amount,
    cb.total_payment,
    cb.average_order_value,
    cb.average_item_count,
    cr.product_category_name  AS favorite_category,
    pr.payment_type           AS favorite_payment_type,
    ex.average_delivery_days,
    ex.delayed_order_count,
    ex.delayed_order_rate,
    ex.average_delay_days,
    ex.average_review_score,
    ex.low_score_order_count,
    ex.low_score_rate,
    lo.customer_state
FROM customer_base cb
LEFT JOIN category_ranked cr ON cb.customer_unique_id = cr.customer_unique_id AND cr.rn = 1
LEFT JOIN payment_ranked pr  ON cb.customer_unique_id = pr.customer_unique_id AND pr.rn = 1
LEFT JOIN experience ex      ON cb.customer_unique_id = ex.customer_unique_id
LEFT JOIN latest_order lo    ON cb.customer_unique_id = lo.customer_unique_id AND lo.rn = 1;

-- 添加主键与常用索引
ALTER TABLE mart_customer_features ADD PRIMARY KEY (customer_unique_id);
ALTER TABLE mart_customer_features
    ADD KEY idx_cf_recency (recency_days),
    ADD KEY idx_cf_order_count (order_count),
    ADD KEY idx_cf_state (customer_state);

-- 验证 1：一行一客户，行数 = 有 delivered 订单的去重客户数
SELECT
    '08_validation_grain' AS check_name,
    (SELECT COUNT(*) FROM mart_customer_features) AS mart_rows,
    (SELECT COUNT(DISTINCT customer_unique_id) FROM mart_order_summary WHERE order_status = 'delivered') AS expected_rows,
    (SELECT COUNT(*) FROM mart_customer_features) =
    (SELECT COUNT(DISTINCT customer_unique_id) FROM mart_order_summary WHERE order_status = 'delivered') AS is_match;

-- 验证 2：用户订单数之和 = delivered 订单总数
SELECT
    '08_validation_orders' AS check_name,
    (SELECT SUM(order_count) FROM mart_customer_features) AS sum_order_count,
    (SELECT COUNT(*) FROM mart_order_summary WHERE order_status = 'delivered') AS delivered_orders,
    (SELECT SUM(order_count) FROM mart_customer_features) =
    (SELECT COUNT(*) FROM mart_order_summary WHERE order_status = 'delivered') AS is_match;

-- 验证 3：用户总支付金额与订单宽表一致
SELECT
    '08_validation_payment' AS check_name,
    (SELECT ROUND(SUM(total_payment), 2) FROM mart_customer_features) AS customer_total,
    (SELECT ROUND(SUM(payment_amount), 2) FROM mart_order_summary WHERE order_status = 'delivered') AS mart_total,
    ABS((SELECT SUM(total_payment) FROM mart_customer_features) -
        (SELECT SUM(payment_amount) FROM mart_order_summary WHERE order_status = 'delivered')) < 0.05 AS is_match;

-- 验证 4：recency 非负且分布概览
SELECT
    '08_validation_recency' AS check_name,
    MIN(recency_days) AS min_recency,
    MAX(recency_days) AS max_recency,
    SUM(recency_days < 0) AS negative_count
FROM mart_customer_features;
