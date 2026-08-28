-- =============================================================
-- 10_cohort_retention.sql
-- 目的：按首购月份划分 Cohort，计算月度留存明细表 cohort_retention_long
-- 粒度：一行一个 (cohort_month, month_index) 组合
-- 依赖：mart_order_summary
-- 口径（详见 docs/metric_definitions.md）：
--   - Cohort 划分：客户首笔 delivered 订单的购买月份（与 mart_customer_features.first_purchase_date 一致）
--   - 活跃定义：该月有至少一笔 delivered 订单
--   - 观察窗口截断：
--     analysis_date = 2018-08-30，2018-08 为不完整月份，
--     观察窗口终点取最后一个完整月份 2018-07。
--     * 可观察的 (cohort, month_index) 格子全量生成：实际留存为 0 也记 0（真实发生的流失）；
--     * 尚未可观察的格子不生成行，绝不以 0 填充（"不得把未来尚未发生的月份视为 0 留存"）。
--   - month_index = 0 为 Cohort 首购当月，留存率恒为 100%（验证项）
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

DROP TABLE IF EXISTS cohort_retention_long;
CREATE TABLE cohort_retention_long AS
WITH RECURSIVE
observation AS (
    -- 观察窗口：analysis_date（最大有效购买日+1，数据推导）所在月份不完整，
    -- 终点取最后一个完整月份（实测 2018-07）；
    -- 副作用：首购发生在不完整月份的客户无法观察 M0，不进入 Cohort（验证 2 记录勾稽）
    SELECT DATE_FORMAT(DATE_SUB(DATE_ADD(MAX(purchase_date), INTERVAL 1 DAY), INTERVAL 1 MONTH), '%Y-%m-01') AS last_full_month
    FROM mart_order_summary
    WHERE order_status = 'delivered'
),
nums AS (
    -- 月份序号序列（覆盖最长 Cohort 观察期，数据集跨度约 22 个月）
    SELECT 0 AS k
    UNION ALL
    SELECT k + 1 FROM nums WHERE k < 30
),
customer_cohort AS (
    -- 粒度：一行一个真实客户；首购月份即 Cohort
    SELECT
        customer_unique_id,
        DATE_FORMAT(MIN(purchase_date), '%Y-%m-01') AS cohort_month
    FROM mart_order_summary
    WHERE order_status = 'delivered'
    GROUP BY customer_unique_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM customer_cohort
    GROUP BY cohort_month
),
cohort_grid AS (
    -- 粒度：cohort × 可观察 month_index（含留存为 0 的格子；不含未来不可观察格子）
    SELECT
        cs.cohort_month,
        n.k AS month_index,
        DATE_FORMAT(DATE_ADD(cs.cohort_month, INTERVAL n.k MONTH), '%Y-%m-01') AS activity_month
    FROM cohort_size cs
    CROSS JOIN observation o
    JOIN nums n
      ON n.k <= TIMESTAMPDIFF(MONTH, cs.cohort_month, o.last_full_month)
),
monthly_activity AS (
    -- 粒度：客户 × 活跃月份（去重）
    SELECT DISTINCT
        m.customer_unique_id,
        DATE_FORMAT(m.purchase_date, '%Y-%m-01') AS activity_month
    FROM mart_order_summary m
    WHERE m.order_status = 'delivered'
),
actual_retention AS (
    -- 粒度：cohort × activity_month 的实际留存人数（观察窗口内）
    SELECT
        cc.cohort_month,
        ma.activity_month,
        COUNT(DISTINCT cc.customer_unique_id) AS retained_customers
    FROM customer_cohort cc
    JOIN monthly_activity ma ON cc.customer_unique_id = ma.customer_unique_id
    CROSS JOIN observation o
    WHERE ma.activity_month <= o.last_full_month
    GROUP BY cc.cohort_month, ma.activity_month
)
SELECT
    g.cohort_month,
    g.activity_month,
    g.month_index,
    cs.cohort_size,
    COALESCE(ar.retained_customers, 0)                          AS retained_customers,
    ROUND(COALESCE(ar.retained_customers, 0) / cs.cohort_size, 4) AS retention_rate
FROM cohort_grid g
JOIN cohort_size cs ON g.cohort_month = cs.cohort_month
LEFT JOIN actual_retention ar
    ON g.cohort_month = ar.cohort_month AND g.activity_month = ar.activity_month;

ALTER TABLE cohort_retention_long
    ADD PRIMARY KEY (cohort_month, month_index),
    ADD KEY idx_cohort_index (month_index);

-- ---------- 验证 ----------
-- 验证 1：所有 Cohort 的 Month 0 留存率 = 100%
SELECT
    '10_validation_m0' AS check_name,
    COUNT(*) AS cohort_count,
    SUM(retention_rate = 1.0) AS m0_is_100pct,
    COUNT(*) = SUM(retention_rate = 1.0) AS all_match
FROM cohort_retention_long
WHERE month_index = 0;

-- 验证 2：Cohort 规模勾稽（排除首购在不完整月份的客户后应精确相等）
-- 首购在 2018-08（不完整观察月）的客户无法观察 M0，不进入 Cohort 表
SELECT
    '10_validation_size' AS check_name,
    (SELECT SUM(cohort_size) FROM cohort_retention_long WHERE month_index = 0) AS sum_cohort_size,
    (SELECT COUNT(*) FROM mart_customer_features WHERE first_purchase_date < '2018-08-01') AS customers_with_full_m0,
    (SELECT COUNT(*) FROM mart_customer_features WHERE first_purchase_date >= '2018-08-01') AS customers_excluded_incomplete_month,
    (SELECT SUM(cohort_size) FROM cohort_retention_long WHERE month_index = 0) =
    (SELECT COUNT(*) FROM mart_customer_features WHERE first_purchase_date < '2018-08-01') AS is_match;

-- 验证 3：无超出观察窗口的记录（activity_month 不应出现 2018-08）
SELECT
    '10_validation_window' AS check_name,
    MAX(activity_month) AS max_activity_month,
    SUM(activity_month > '2018-07-01') AS out_of_window_rows
FROM cohort_retention_long;

-- 验证 4：成熟 Cohort 的 M1/M2/M3 汇总留存率
-- M1 对外 KPI 使用客户数加权口径：SUM(retained_customers) / SUM(cohort_size)
-- M2/M3 继续沿用成熟 Cohort 留存率的简单平均；Cohort 明细不作改写
SELECT
    '10_mature_retention' AS check_name,
    month_index,
    COUNT(*) AS mature_cohorts,
    CASE
        WHEN month_index = 1 THEN
            ROUND(SUM(retained_customers) / NULLIF(SUM(cohort_size), 0) * 100, 2)
        ELSE ROUND(AVG(retention_rate) * 100, 2)
    END AS retention_pct,
    CASE
        WHEN month_index = 1 THEN 'weighted_customer_rate'
        ELSE 'simple_cohort_average'
    END AS aggregation_method,
    MIN(cohort_month) AS earliest_cohort,
    MAX(cohort_month) AS latest_cohort
FROM cohort_retention_long
WHERE month_index BETWEEN 1 AND 3
GROUP BY month_index
ORDER BY month_index;

-- 输出：完整留存明细（供 Python 导出 CSV 与绘制热力图）
SELECT cohort_month, month_index, cohort_size, retained_customers,
       ROUND(retention_rate * 100, 2) AS retention_pct
FROM cohort_retention_long
ORDER BY cohort_month, month_index;
