-- =============================================================
-- 11_delivery_experience.sql
-- 目的：履约体验（配送延迟 × 客户评分）分析
-- 依赖：mart_order_summary、dim_customer_segment
-- 分析样本口径（重要）：
--   仅取 delivered 订单中 is_delayed 可判定（签收与预计时间齐全）
--   且有评价（review_score 非空）的订单。
-- 输出：
--   1) mart_delivery_sample：订单级分析样本（供聚合与图表）
--   2) 核心对比指标（准时 vs 延迟评分、评分下降比例）
--   3) 延迟分段 / 州 / 类别 / 高价值客户 聚合统计
--   4) 延迟 × 低评分列联表（供 Python 卡方检验）
-- 结论表述约束：只能说"配送延迟与较低评分显著相关"，不得断言因果。
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

-- ---------- 1. 订单级分析样本 ----------
DROP TABLE IF EXISTS mart_delivery_sample;
CREATE TABLE mart_delivery_sample AS
SELECT
    m.order_id,
    m.customer_unique_id,
    m.customer_state,
    m.main_category,
    m.delivery_days,
    m.delay_days,
    m.is_delayed,
    CASE
        WHEN m.is_delayed = 0 THEN 'on_time'
        -- is_delayed=1 但 delay_days=0：当天超时（时间戳晚于预计但日期相同），归入 1-3 天档
        WHEN m.is_delayed = 1 AND m.delay_days <= 3 THEN 'delay_1_3'
        WHEN m.delay_days BETWEEN 4 AND 7 THEN 'delay_4_7'
        WHEN m.delay_days BETWEEN 8 AND 14 THEN 'delay_8_14'
        WHEN m.delay_days >= 15 THEN 'delay_15_plus'
    END AS delay_bucket,
    m.review_score,
    m.is_low_score,
    m.item_amount,
    CASE WHEN s.value_segment = 'high_value' THEN 1 ELSE 0 END AS is_high_value_customer
FROM mart_order_summary m
LEFT JOIN dim_customer_segment s ON m.customer_unique_id = s.customer_unique_id
WHERE m.order_status = 'delivered'
  AND m.is_delayed IS NOT NULL
  AND m.review_score IS NOT NULL;

ALTER TABLE mart_delivery_sample ADD PRIMARY KEY (order_id);
ALTER TABLE mart_delivery_sample
    ADD KEY idx_ds_bucket (delay_bucket),
    ADD KEY idx_ds_state (customer_state),
    ADD KEY idx_ds_category (main_category);

-- ---------- 2. 核心对比：准时 vs 延迟 ----------
SELECT
    '11_core_comparison' AS check_name,
    SUM(is_delayed = 0) AS on_time_orders,
    SUM(is_delayed = 1) AS delayed_orders,
    CONCAT(ROUND(SUM(is_delayed = 1) / COUNT(*) * 100, 2), '%') AS delay_rate,
    ROUND(AVG(CASE WHEN is_delayed = 0 THEN review_score END), 2) AS on_time_avg_score,
    ROUND(AVG(CASE WHEN is_delayed = 1 THEN review_score END), 2) AS delayed_avg_score,
    ROUND(AVG(CASE WHEN is_delayed = 0 THEN review_score END)
        - AVG(CASE WHEN is_delayed = 1 THEN review_score END), 2) AS score_diff,
    CONCAT(ROUND(
        (AVG(CASE WHEN is_delayed = 0 THEN review_score END)
         - AVG(CASE WHEN is_delayed = 1 THEN review_score END))
        / AVG(CASE WHEN is_delayed = 0 THEN review_score END) * 100, 2), '%') AS score_drop_pct,
    CONCAT(ROUND(SUM(CASE WHEN is_delayed = 0 THEN is_low_score END)
        / SUM(is_delayed = 0) * 100, 2), '%') AS on_time_low_score_rate,
    CONCAT(ROUND(SUM(CASE WHEN is_delayed = 1 THEN is_low_score END)
        / SUM(is_delayed = 1) * 100, 2), '%') AS delayed_low_score_rate
FROM mart_delivery_sample;

-- ---------- 3. 延迟分段统计 ----------
SELECT
    delay_bucket,
    COUNT(*) AS order_count,
    ROUND(AVG(review_score), 2) AS avg_score,
    CONCAT(ROUND(SUM(is_low_score) / COUNT(*) * 100, 2), '%') AS low_score_rate
FROM mart_delivery_sample
GROUP BY delay_bucket
ORDER BY FIELD(delay_bucket, 'on_time', 'delay_1_3', 'delay_4_7', 'delay_8_14', 'delay_15_plus');

-- ---------- 4. 各州延迟率 ----------
SELECT
    customer_state,
    COUNT(*) AS order_count,
    SUM(is_delayed) AS delayed_orders,
    ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) AS delay_rate_pct,
    ROUND(AVG(review_score), 2) AS avg_score
FROM mart_delivery_sample
GROUP BY customer_state
HAVING COUNT(*) >= 100
ORDER BY delay_rate_pct DESC;

-- ---------- 5. 各类别延迟率（按订单主类别） ----------
SELECT
    main_category,
    COUNT(*) AS order_count,
    SUM(is_delayed) AS delayed_orders,
    ROUND(SUM(is_delayed) / COUNT(*) * 100, 2) AS delay_rate_pct,
    ROUND(AVG(review_score), 2) AS avg_score
FROM mart_delivery_sample
WHERE main_category IS NOT NULL
GROUP BY main_category
HAVING COUNT(*) >= 100
ORDER BY delay_rate_pct DESC;

-- ---------- 6. 高价值客户的延迟体验 ----------
SELECT
    '11_high_value' AS check_name,
    SUM(is_high_value_customer = 1 AND is_delayed = 0) AS hv_on_time_orders,
    SUM(is_high_value_customer = 1 AND is_delayed = 1) AS hv_delayed_orders,
    ROUND(AVG(CASE WHEN is_high_value_customer = 1 AND is_delayed = 0 THEN review_score END), 2) AS hv_on_time_score,
    ROUND(AVG(CASE WHEN is_high_value_customer = 1 AND is_delayed = 1 THEN review_score END), 2) AS hv_delayed_score,
    ROUND(AVG(CASE WHEN is_high_value_customer = 0 AND is_delayed = 0 THEN review_score END), 2) AS others_on_time_score,
    ROUND(AVG(CASE WHEN is_high_value_customer = 0 AND is_delayed = 1 THEN review_score END), 2) AS others_delayed_score
FROM mart_delivery_sample;

-- ---------- 7. 延迟 × 低评分列联表（供 Python 卡方检验） ----------
SELECT
    is_delayed,
    SUM(is_low_score = 1) AS low_score_orders,
    SUM(is_low_score = 0) AS normal_score_orders,
    COUNT(*) AS total
FROM mart_delivery_sample
GROUP BY is_delayed
ORDER BY is_delayed;

-- ---------- 验证 ----------
-- 样本量勾稽：样本 = delivered 且双时间齐全且有评价的订单
SELECT
    '11_validation_sample' AS check_name,
    (SELECT COUNT(*) FROM mart_delivery_sample) AS sample_rows,
    (SELECT COUNT(*) FROM mart_order_summary
     WHERE order_status = 'delivered' AND is_delayed IS NOT NULL AND review_score IS NOT NULL) AS expected_rows,
    (SELECT COUNT(*) FROM mart_delivery_sample) =
    (SELECT COUNT(*) FROM mart_order_summary
     WHERE order_status = 'delivered' AND is_delayed IS NOT NULL AND review_score IS NOT NULL) AS is_match;
