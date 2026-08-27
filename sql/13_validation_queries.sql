-- =============================================================
-- 13_validation_queries.sql
-- 目的：对全部建模产出做最终一致性验证（Brief 16.1 的 10 项）
-- 每项输出 pass/fail，全部应为 1
-- =============================================================

USE olist_ecommerce;

-- V1. 订单宽表一行一订单
SELECT 'V1_order_grain' AS check_name,
       COUNT(*) = COUNT(DISTINCT order_id) AS pass
FROM mart_order_summary;

-- V2. 用户宽表一行一客户
SELECT 'V2_customer_grain' AS check_name,
       COUNT(*) = COUNT(DISTINCT customer_unique_id) AS pass
FROM mart_customer_features;

-- V3. 聚合前后有效订单数一致（delivered）
SELECT 'V3_valid_orders' AS check_name,
       (SELECT COUNT(*) FROM mart_order_summary WHERE order_status = 'delivered') =
       (SELECT COUNT(*) FROM mart_order_summary m
        JOIN order_item_agg ia ON m.order_id = ia.order_id
        WHERE m.order_status = 'delivered') AS pass;

-- V4. 用户订单总数与订单宽表一致
SELECT 'V4_order_total' AS check_name,
       (SELECT SUM(order_count) FROM mart_customer_features) =
       (SELECT COUNT(*) FROM mart_order_summary WHERE order_status = 'delivered') AS pass;

-- V5. 支付金额聚合前后基本一致（误差 < 0.05 BRL）
SELECT 'V5_payment_amount' AS check_name,
       ABS((SELECT SUM(payment_amount) FROM order_payment_agg) -
           (SELECT SUM(payment_value) FROM order_payments)) < 0.05 AS pass;

-- V6. 商品金额聚合前后基本一致（误差 < 0.05 BRL）
SELECT 'V6_goods_amount' AS check_name,
       ABS((SELECT SUM(goods_amount) FROM order_item_agg) -
           (SELECT SUM(price) FROM order_items)) < 0.05 AS pass;

-- V7. Cohort Month 0 留存率为 100%
SELECT 'V7_cohort_m0' AS check_name,
       COUNT(*) = SUM(retention_rate = 1.0) AS pass
FROM cohort_retention_long
WHERE month_index = 0;

-- V8. 用户分层人数之和等于总用户数
SELECT 'V8_segment_sum' AS check_name,
       (SELECT COUNT(*) FROM dim_customer_segment) =
       (SELECT COUNT(*) FROM mart_customer_features) AS pass;

-- V9. 营销名单不存在重复客户
SELECT 'V9_campaign_unique' AS check_name,
       COUNT(*) = COUNT(DISTINCT customer_unique_id) AS pass
FROM mart_campaign_target_list;

-- V10. 所有百分比/比例字段位于 0-100%（0-1）区间
SELECT 'V10_pct_range' AS check_name,
       (SELECT SUM(delayed_order_rate BETWEEN 0 AND 1) = COUNT(delayed_order_rate)
        FROM mart_customer_features WHERE delayed_order_rate IS NOT NULL)
       AND
       (SELECT SUM(low_score_rate BETWEEN 0 AND 1) = COUNT(low_score_rate)
        FROM mart_customer_features WHERE low_score_rate IS NOT NULL)
       AND
       (SELECT SUM(retention_rate BETWEEN 0 AND 1) = COUNT(*)
        FROM cohort_retention_long) AS pass;

-- V11. Cohort 明细留存率与客户数勾稽一致（M1 KPI 在此明细上加权汇总）
SELECT 'V11_cohort_retention_reconciles' AS check_name,
       SUM(ABS(retention_rate - retained_customers / cohort_size) > 0.000001) = 0 AS pass
FROM cohort_retention_long;
