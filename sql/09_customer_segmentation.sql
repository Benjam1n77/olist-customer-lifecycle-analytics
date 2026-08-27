-- =============================================================
-- 09_customer_segmentation.sql
-- 目的：构建用户标签与生命周期分层表 dim_customer_segment
-- 粒度：一行一个 customer_unique_id（93,358 人，与 mart_customer_features 一致）
-- 依赖：mart_customer_features（阶段 5）、mart_order_summary（阶段 4）
-- 设计说明（详见 docs/metric_definitions.md）：
--   RFM 数据适配：97% 客户为一次性购买，F 若机械五等分会失去区分度。
--   因此 R/M 用分位数评分，F 先区分一次性/复购再细分频次。
--   所有分位数阈值在查询中由数据推导并输出，可复现。
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS dim_customer_segment;
CREATE TABLE dim_customer_segment AS
WITH
-- ---------- 0. 分位数阈值（数据推导，避免手工拍脑袋） ----------
-- 说明：MySQL 8.0 不支持 PERCENTILE_CONT，改用 ROW_NUMBER 取第 CEIL(q*n) 行的方式
ranked AS (
    SELECT
        recency_days,
        total_payment,
        average_order_value,
        ROW_NUMBER() OVER (ORDER BY recency_days, customer_unique_id)        AS r_rn,
        ROW_NUMBER() OVER (ORDER BY total_payment, customer_unique_id)       AS m_rn,
        ROW_NUMBER() OVER (ORDER BY average_order_value, customer_unique_id) AS a_rn,
        COUNT(*) OVER ()                                                     AS n
    FROM mart_customer_features
),
pct AS (
    SELECT
        -- recency 越小越好：分位点用于 R 评分（1-5）
        MAX(CASE WHEN r_rn = CEIL(0.2 * n) THEN recency_days END) AS r_p20,
        MAX(CASE WHEN r_rn = CEIL(0.4 * n) THEN recency_days END) AS r_p40,
        MAX(CASE WHEN r_rn = CEIL(0.6 * n) THEN recency_days END) AS r_p60,
        MAX(CASE WHEN r_rn = CEIL(0.8 * n) THEN recency_days END) AS r_p80,
        -- total_payment：M 评分与价值分层共用分位点
        MAX(CASE WHEN m_rn = CEIL(0.2 * n) THEN total_payment END) AS m_p20,
        MAX(CASE WHEN m_rn = CEIL(0.4 * n) THEN total_payment END) AS m_p40,
        MAX(CASE WHEN m_rn = CEIL(0.6 * n) THEN total_payment END) AS m_p60,
        MAX(CASE WHEN m_rn = CEIL(0.8 * n) THEN total_payment END) AS m_p80,
        -- average_order_value：high_aov / price_sensitive 边界
        MAX(CASE WHEN a_rn = CEIL(0.2 * n) THEN average_order_value END) AS aov_p20,
        MAX(CASE WHEN a_rn = CEIL(0.8 * n) THEN average_order_value END) AS aov_p80
    FROM ranked
),
-- ---------- 1. 辅助特征：分期使用与类别集中度 ----------
installment AS (
    -- 是否使用过分期（任一 delivered 订单分期数 > 1）
    SELECT customer_unique_id, MAX(max_installments > 1) AS uses_installment
    FROM mart_order_summary
    WHERE order_status = 'delivered'
    GROUP BY customer_unique_id
),
category_share AS (
    -- 偏好类别消费占比（用于 category_focused 判定）
    SELECT cs.customer_unique_id, cs.cat_spend / t.total_spend AS top_category_share
    FROM (
        SELECT v.customer_unique_id, p.product_category_name, SUM(oi.price) AS cat_spend,
               ROW_NUMBER() OVER (PARTITION BY v.customer_unique_id ORDER BY SUM(oi.price) DESC) AS rn
        FROM mart_order_summary v
        JOIN order_items oi ON v.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE v.order_status = 'delivered' AND p.product_category_name IS NOT NULL
        GROUP BY v.customer_unique_id, p.product_category_name
    ) cs
    JOIN (
        SELECT v.customer_unique_id, SUM(oi.price) AS total_spend
        FROM mart_order_summary v
        JOIN order_items oi ON v.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE v.order_status = 'delivered' AND p.product_category_name IS NOT NULL
        GROUP BY v.customer_unique_id
    ) t ON cs.customer_unique_id = t.customer_unique_id
    WHERE cs.rn = 1
),
-- ---------- 2. RFM 评分 ----------
rfm AS (
    SELECT
        cf.customer_unique_id,
        -- R：recency 越小分越高
        CASE
            WHEN cf.recency_days <= p.r_p20 THEN 5
            WHEN cf.recency_days <= p.r_p40 THEN 4
            WHEN cf.recency_days <= p.r_p60 THEN 3
            WHEN cf.recency_days <= p.r_p80 THEN 2
            ELSE 1
        END AS r_score,
        -- F：先区分一次性/复购，复购按频次细分（数据分布：2单2573人，3-4单209人，≥5单19人）
        CASE
            WHEN cf.order_count = 1 THEN 1
            WHEN cf.order_count = 2 THEN 2
            WHEN cf.order_count BETWEEN 3 AND 4 THEN 3
            WHEN cf.order_count BETWEEN 5 AND 9 THEN 4
            ELSE 5
        END AS f_score,
        -- M：支付金额越高分越高
        CASE
            WHEN cf.total_payment <= p.m_p20 THEN 1
            WHEN cf.total_payment <= p.m_p40 THEN 2
            WHEN cf.total_payment <= p.m_p60 THEN 3
            WHEN cf.total_payment <= p.m_p80 THEN 4
            ELSE 5
        END AS m_score,
        -- 价值分层（Brief 10.2）
        CASE
            WHEN cf.total_payment >= p.m_p80 THEN 'high_value'
            WHEN cf.total_payment >= p.m_p20 THEN 'mid_value'
            ELSE 'low_value'
        END AS value_segment,
        -- 生命周期（Brief 10.3 初始规则，Recency 分布已在阶段 5 输出佐证）
        CASE
            WHEN cf.recency_days <= 30 AND cf.order_count = 1 THEN 'new_customer'
            WHEN cf.recency_days <= 90 THEN 'active_customer'
            WHEN cf.recency_days <= 180 THEN 'at_risk'
            ELSE 'churned'
        END AS lifecycle_stage,
        -- 行为标签（6 个布尔标签）
        CASE WHEN cf.order_count = 1 THEN 1 ELSE 0 END                        AS is_one_time_buyer,
        CASE WHEN cf.order_count >= 2 THEN 1 ELSE 0 END                       AS is_repeat_buyer,
        CASE WHEN cf.average_order_value >= p.aov_p80 THEN 1 ELSE 0 END       AS is_high_aov,
        CASE WHEN cf.average_order_value <= p.aov_p20 THEN 1 ELSE 0 END       AS is_price_sensitive,
        CASE WHEN csh.top_category_share >= 0.7 THEN 1 ELSE 0 END             AS is_category_focused,
        COALESCE(ins.uses_installment, 0)                                     AS is_installment_user
    FROM mart_customer_features cf
    CROSS JOIN pct p
    LEFT JOIN installment ins ON cf.customer_unique_id = ins.customer_unique_id
    LEFT JOIN category_share csh ON cf.customer_unique_id = csh.customer_unique_id
),
-- ---------- 3. 行为主标签（优先级：高客单 > 分期用户 > 品类聚焦 > 价格敏感 > 复购 > 一次性） ----------
behavior AS (
    SELECT
        r.*,
        CASE
            WHEN is_high_aov = 1 THEN 'high_aov'
            WHEN is_installment_user = 1 THEN 'installment_user'
            WHEN is_category_focused = 1 THEN 'category_focused'
            WHEN is_price_sensitive = 1 THEN 'price_sensitive'
            WHEN is_repeat_buyer = 1 THEN 'repeat_buyer'
            ELSE 'one_time_buyer'
        END AS behavior_segment
    FROM rfm r
),
-- ---------- 4. 履约体验标签（Brief 10.5） ----------
experience AS (
    SELECT
        b.*,
        cf.delayed_order_count,
        cf.delayed_order_rate,
        cf.average_review_score,
        -- 布尔标签
        CASE WHEN cf.delayed_order_count >= 1
              AND cf.average_review_score IS NOT NULL AND cf.average_review_score <= 2
             THEN 1 ELSE 0 END AS is_service_recovery_needed,
        CASE WHEN cf.average_review_score IS NOT NULL AND cf.average_review_score <= 2
             THEN 1 ELSE 0 END AS is_low_satisfaction,
        CASE WHEN cf.delayed_order_rate >= 0.5 AND cf.delayed_order_count >= 2
             THEN 1 ELSE 0 END AS is_frequent_delay,
        CASE WHEN cf.delayed_order_count >= 1 THEN 1 ELSE 0 END AS is_delivery_delayed,
        CASE WHEN COALESCE(cf.delayed_order_count, 0) = 0 THEN 1 ELSE 0 END AS is_delivery_normal
    FROM behavior b
    JOIN mart_customer_features cf ON b.customer_unique_id = cf.customer_unique_id
),
-- ---------- 5. 体验主标签（优先级：需服务补救 > 低满意 > 频繁延迟 > 有延迟 > 正常） ----------
exp_seg AS (
    SELECT
        e.*,
        CASE
            WHEN is_service_recovery_needed = 1 THEN 'service_recovery_needed'
            WHEN is_low_satisfaction = 1 THEN 'low_satisfaction'
            WHEN is_frequent_delay = 1 THEN 'frequent_delay'
            WHEN is_delivery_delayed = 1 THEN 'delivery_delayed'
            ELSE 'delivery_normal'
        END AS experience_segment
    FROM experience e
)
-- ---------- 6. 最终输出 ----------
SELECT
    customer_unique_id,
    value_segment,
    lifecycle_stage,
    behavior_segment,
    experience_segment,
    r_score * 100 + f_score * 10 + m_score AS rfm_score,
    -- 最终业务人群（优先级自上而下，互斥）
    CASE
        WHEN is_service_recovery_needed = 1 THEN '履约受损客户'
        WHEN value_segment = 'high_value' AND lifecycle_stage IN ('new_customer', 'active_customer') THEN '高价值活跃客户'
        WHEN value_segment = 'high_value' AND lifecycle_stage = 'at_risk' THEN '高价值流失风险客户'
        WHEN value_segment = 'high_value' AND lifecycle_stage = 'churned' THEN '高价值已流失客户'
        WHEN is_repeat_buyer = 1 AND recency_days_lte_180 = 1 THEN '重复购买成长客户'
        WHEN is_one_time_buyer = 1 AND recency_days_lte_180 = 1 THEN '首购未复购客户'
        WHEN value_segment = 'low_value' AND lifecycle_stage = 'churned' THEN '低价值长期沉默客户'
        ELSE '其他普通客户'
    END AS final_segment
FROM (
    SELECT
        e.customer_unique_id,
        e.value_segment,
        e.lifecycle_stage,
        e.behavior_segment,
        e.experience_segment,
        e.r_score, e.f_score, e.m_score,
        e.is_service_recovery_needed,
        e.is_repeat_buyer,
        e.is_one_time_buyer,
        CASE WHEN cf.recency_days <= 180 THEN 1 ELSE 0 END AS recency_days_lte_180
    FROM exp_seg e
    JOIN mart_customer_features cf ON e.customer_unique_id = cf.customer_unique_id
) final_input;

-- 添加主键与索引
ALTER TABLE dim_customer_segment ADD PRIMARY KEY (customer_unique_id);
ALTER TABLE dim_customer_segment
    ADD KEY idx_seg_value (value_segment),
    ADD KEY idx_seg_lifecycle (lifecycle_stage),
    ADD KEY idx_seg_final (final_segment);

-- ---------- 验证 ----------
-- 验证 1：人数与用户宽表一致（分层人数之和 = 总用户数）
SELECT
    '09_validation_count' AS check_name,
    (SELECT COUNT(*) FROM dim_customer_segment) AS seg_rows,
    (SELECT COUNT(*) FROM mart_customer_features) AS feature_rows,
    (SELECT COUNT(*) FROM dim_customer_segment) = (SELECT COUNT(*) FROM mart_customer_features) AS is_match;

-- 验证 2：各维度分布
SELECT 'value_segment' AS dim, value_segment AS label, COUNT(*) AS cnt,
       CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM dim_customer_segment GROUP BY value_segment
UNION ALL
SELECT 'lifecycle_stage', lifecycle_stage, COUNT(*),
       CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%')
FROM dim_customer_segment GROUP BY lifecycle_stage;

SELECT final_segment, COUNT(*) AS cnt,
       CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM dim_customer_segment GROUP BY final_segment ORDER BY cnt DESC;

-- 验证 3：RFM 分位数阈值（记录到指标文档用；同样用 ROW_NUMBER 方式）
SELECT
    MAX(CASE WHEN r_rn = CEIL(0.2 * n) THEN recency_days END) AS r_p20,
    MAX(CASE WHEN r_rn = CEIL(0.8 * n) THEN recency_days END) AS r_p80,
    MAX(CASE WHEN m_rn = CEIL(0.2 * n) THEN total_payment END) AS m_p20,
    MAX(CASE WHEN m_rn = CEIL(0.8 * n) THEN total_payment END) AS m_p80,
    MAX(CASE WHEN a_rn = CEIL(0.2 * n) THEN average_order_value END) AS aov_p20,
    MAX(CASE WHEN a_rn = CEIL(0.8 * n) THEN average_order_value END) AS aov_p80
FROM (
    SELECT recency_days, total_payment, average_order_value,
           ROW_NUMBER() OVER (ORDER BY recency_days, customer_unique_id) AS r_rn,
           ROW_NUMBER() OVER (ORDER BY total_payment, customer_unique_id) AS m_rn,
           ROW_NUMBER() OVER (ORDER BY average_order_value, customer_unique_id) AS a_rn,
           COUNT(*) OVER () AS n
    FROM mart_customer_features
) t;
