-- =============================================================
-- 06_review_aggregation.sql
-- 目的：将 order_reviews 聚合到 order_id 粒度，建立 order_review_agg
-- 粒度：一行一笔订单
-- 聚合规则（同单多评价，共 243 个订单）：
--   - review_score          = 取最高分（MAX）；理由：评价多为跟进补充，
--                             最高分代表客户最终满意状态；规则已在此处与指标文档记录
--   - has_review_comment    = 任一条评价含标题或正文则为 1
--   - review_response_days  = 取 review_answer_timestamp 最新的一条
--                             （DATEDIFF(提交时间 − 问卷创建时间)），代表最终响应时长
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS order_review_agg;
CREATE TABLE order_review_agg AS
WITH review_base AS (
    -- 粒度：一行一笔订单；评分与评论存在性
    SELECT
        order_id,
        COUNT(*)                                        AS review_count,
        MAX(review_score)                               AS review_score,
        MAX(CASE
                WHEN (review_comment_title IS NOT NULL AND review_comment_title <> '')
                  OR (review_comment_message IS NOT NULL AND review_comment_message <> '')
                THEN 1 ELSE 0
            END)                                        AS has_review_comment
    FROM order_reviews
    GROUP BY order_id
),
review_latest AS (
    -- 粒度：订单评价行；按提交时间倒序排名，取最新一条计算响应时长
    SELECT
        order_id,
        DATEDIFF(review_answer_timestamp, review_creation_date) AS response_days,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_answer_timestamp DESC, review_id ASC
        ) AS rn
    FROM order_reviews
    WHERE review_answer_timestamp IS NOT NULL
      AND review_creation_date IS NOT NULL
)
SELECT
    rb.order_id,
    rb.review_count,
    rb.review_score,
    rb.has_review_comment,
    rl.response_days AS review_response_days
FROM review_base rb
LEFT JOIN review_latest rl
    ON rb.order_id = rl.order_id AND rl.rn = 1;

-- 添加主键（CTAS 不自带约束）
ALTER TABLE order_review_agg ADD PRIMARY KEY (order_id);

-- 验证：聚合行数应等于 order_reviews 的去重订单数
SELECT
    '06_validation' AS check_name,
    (SELECT COUNT(*) FROM order_review_agg) AS agg_rows,
    (SELECT COUNT(DISTINCT order_id) FROM order_reviews) AS distinct_orders,
    (SELECT COUNT(*) FROM order_review_agg) = (SELECT COUNT(DISTINCT order_id) FROM order_reviews) AS is_match;
