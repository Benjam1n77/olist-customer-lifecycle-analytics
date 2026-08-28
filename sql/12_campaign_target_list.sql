-- =============================================================
-- 12_campaign_target_list.sql
-- 目的：构建营销人群名单 mart_campaign_target_list
-- 粒度：一行一个 customer_unique_id（每人至多一条推荐，互斥规则级联）
-- 依赖：mart_customer_features、dim_customer_segment
-- 规则设计（优先级自上而下，命中即停）：
--   1. SERVICE_RECOVERY   履约受损客户            → 售后关怀/补偿券/满意度回访   high
--   2. WINBACK_HIGH_VALUE 高价值已流失            → 专属召回优惠/会员关怀       high
--   3. SECOND_PURCHASE    首购未复购（14-180天）  → 首购后二购激励             high
--   4. RETAIN_AT_RISK     高价值流失风险          → 预防性挽留/限时权益         high
--   5. VIP_ENGAGE         高价值活跃              → VIP权益/新品优先/推荐奖励   medium_high
--   6. CATEGORY_PROMO     品类偏好明显            → 对应品类内容/活动/商品推荐  medium
-- 口径说明：
--   - SECOND_PURCHASE 的 recency 窗口取 14–180 天：<14 天尚未到二购激励时机，
--     >180 天已按流失处理；建议动作中的 14–30 天描述触达时点，不是筛选窗口；
--   - 未命中任何规则的客户不进入名单（如低价值已流失且无品类偏好）；
--   - 本项目只输出名单与推荐动作，不声称已实现真实触达。
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS mart_campaign_target_list;
CREATE TABLE mart_campaign_target_list AS
SELECT
    cf.customer_unique_id,
    s.value_segment,
    s.lifecycle_stage,
    s.behavior_segment,
    s.experience_segment,
    cf.favorite_category,
    cf.order_count,
    cf.total_payment,
    cf.average_order_value,
    cf.recency_days,
    cf.average_review_score,
    cf.delayed_order_rate,
    -- 推荐动作（按命中规则）
    CASE rule.hit
        WHEN 'SERVICE_RECOVERY'   THEN '售后关怀、补偿券、满意度回访'
        WHEN 'WINBACK_HIGH_VALUE' THEN '专属召回优惠或会员关怀'
        WHEN 'SECOND_PURCHASE'    THEN '首购后14-30天二购激励与品类推荐'
        WHEN 'RETAIN_AT_RISK'     THEN '预防性挽留：限时权益与个性化提醒'
        WHEN 'VIP_ENGAGE'         THEN 'VIP权益、新品优先体验、推荐奖励'
        WHEN 'CATEGORY_PROMO'     THEN '对应品类内容、活动和商品推荐'
    END AS recommended_action,
    -- 推荐渠道（与动作配套的合理默认）
    CASE rule.hit
        WHEN 'SERVICE_RECOVERY'   THEN '邮件+客服电话回访'
        WHEN 'WINBACK_HIGH_VALUE' THEN '邮件（个性化优惠券）'
        WHEN 'SECOND_PURCHASE'    THEN '邮件/App推送'
        WHEN 'RETAIN_AT_RISK'     THEN '邮件+短信'
        WHEN 'VIP_ENGAGE'         THEN 'App/会员中心'
        WHEN 'CATEGORY_PROMO'     THEN 'App推送/社交媒体'
    END AS recommended_channel,
    -- 优先级
    CASE rule.hit
        WHEN 'SERVICE_RECOVERY'   THEN 'high'
        WHEN 'WINBACK_HIGH_VALUE' THEN 'high'
        WHEN 'SECOND_PURCHASE'    THEN 'high'
        WHEN 'RETAIN_AT_RISK'     THEN 'high'
        WHEN 'VIP_ENGAGE'         THEN 'medium_high'
        WHEN 'CATEGORY_PROMO'     THEN 'medium'
    END AS campaign_priority,
    rule.hit AS reason_code
FROM mart_customer_features cf
JOIN dim_customer_segment s ON cf.customer_unique_id = s.customer_unique_id
CROSS JOIN LATERAL (
    -- 规则级联：自上而下命中即停，保证每人一条互斥推荐
    SELECT CASE
        WHEN s.experience_segment = 'service_recovery_needed'
            THEN 'SERVICE_RECOVERY'
        WHEN s.value_segment = 'high_value' AND s.lifecycle_stage = 'churned'
            THEN 'WINBACK_HIGH_VALUE'
        WHEN cf.order_count = 1 AND cf.recency_days BETWEEN 14 AND 180
            THEN 'SECOND_PURCHASE'
        WHEN s.value_segment = 'high_value' AND s.lifecycle_stage = 'at_risk'
            THEN 'RETAIN_AT_RISK'
        WHEN s.value_segment = 'high_value'
             AND s.lifecycle_stage IN ('new_customer', 'active_customer')
            THEN 'VIP_ENGAGE'
        WHEN s.behavior_segment = 'category_focused'
            THEN 'CATEGORY_PROMO'
        ELSE NULL
    END AS hit
) rule
WHERE rule.hit IS NOT NULL;

ALTER TABLE mart_campaign_target_list ADD PRIMARY KEY (customer_unique_id);
ALTER TABLE mart_campaign_target_list
    ADD KEY idx_ctl_priority (campaign_priority),
    ADD KEY idx_ctl_reason (reason_code);

-- ---------- 验证 ----------
-- 验证 1：名单无重复客户
SELECT
    '12_validation_unique' AS check_name,
    COUNT(*) AS list_rows,
    COUNT(DISTINCT customer_unique_id) AS distinct_customers,
    COUNT(*) = COUNT(DISTINCT customer_unique_id) AS no_duplicates
FROM mart_campaign_target_list;

-- 验证 2：各规则人数与优先级分布
SELECT
    reason_code,
    campaign_priority,
    COUNT(*) AS customer_count,
    CONCAT(ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2), '%') AS pct
FROM mart_campaign_target_list
GROUP BY reason_code, campaign_priority
ORDER BY FIELD(reason_code, 'SERVICE_RECOVERY', 'WINBACK_HIGH_VALUE',
    'SECOND_PURCHASE', 'RETAIN_AT_RISK', 'VIP_ENGAGE', 'CATEGORY_PROMO');

-- 验证 3：名单客户均存在于用户宽表（无幽灵客户）
SELECT
    '12_validation_refint' AS check_name,
    SUM(t.customer_unique_id IS NULL) AS orphan_rows
FROM mart_campaign_target_list l
LEFT JOIN mart_customer_features t ON l.customer_unique_id = t.customer_unique_id;

-- 验证 4：百分比字段均在 0-1 之间（delayed_order_rate 为比例）
SELECT
    '12_validation_range' AS check_name,
    SUM(delayed_order_rate < 0 OR delayed_order_rate > 1) AS out_of_range
FROM mart_campaign_target_list
WHERE delayed_order_rate IS NOT NULL;
