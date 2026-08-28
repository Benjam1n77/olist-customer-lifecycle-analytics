-- =============================================================
-- 02_create_tables.sql
-- 目的：为 9 个原始 CSV 建立 MySQL 表（字段名与 CSV 表头一致，便于直接导入）
-- 口径：
--   - 字符集 utf8mb4 / InnoDB
--   - 金额 DECIMAL(10,2)，时间 DATETIME，计数 INT，评分 TINYINT
--   - 外键关系为逻辑外键（见 docs/er_diagram.md），不建物理 FK 约束：
--     关联完整性由 sql/03_data_quality_checks.sql 量化检查
-- 可重复执行：DROP TABLE IF EXISTS + CREATE TABLE
-- =============================================================

USE olist_ecommerce;

-- -------------------------------------------------------------
-- 1. customers：订单级客户维度（复购分析需经 customer_unique_id 归并）
-- -------------------------------------------------------------
DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    customer_id             VARCHAR(32)   NOT NULL COMMENT '订单级客户ID（主键）',
    customer_unique_id      VARCHAR(32)   NOT NULL COMMENT '真实客户唯一ID（复购/留存分析核心键）',
    customer_zip_code_prefix VARCHAR(5)   NULL     COMMENT '客户邮编前5位',
    customer_city           VARCHAR(64)   NULL     COMMENT '客户城市',
    customer_state          CHAR(2)       NULL     COMMENT '客户州（BR 州缩写）',
    PRIMARY KEY (customer_id),
    KEY idx_customers_unique_id (customer_unique_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '客户表：粒度=订单级客户标识';

-- -------------------------------------------------------------
-- 2. orders：订单主事实表
-- -------------------------------------------------------------
DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    order_id                        VARCHAR(32) NOT NULL COMMENT '订单ID（主键）',
    customer_id                     VARCHAR(32) NOT NULL COMMENT '订单级客户ID -> customers',
    order_status                    VARCHAR(20) NOT NULL COMMENT '订单状态',
    order_purchase_timestamp        DATETIME    NULL     COMMENT '购买时间',
    order_approved_at               DATETIME    NULL     COMMENT '审批通过时间',
    order_delivered_carrier_date    DATETIME    NULL     COMMENT '交付承运商时间',
    order_delivered_customer_date   DATETIME    NULL     COMMENT '实际签收时间',
    order_estimated_delivery_date   DATETIME    NULL     COMMENT '预计签收时间',
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_id (customer_id),
    KEY idx_orders_status (order_status),
    KEY idx_orders_purchase_ts (order_purchase_timestamp)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '订单表：粒度=一笔订单';

-- -------------------------------------------------------------
-- 3. order_items：订单商品明细（一单多行，聚合前禁止与支付/评价直接 JOIN）
-- -------------------------------------------------------------
DROP TABLE IF EXISTS order_items;
CREATE TABLE order_items (
    order_id          VARCHAR(32)   NOT NULL COMMENT '订单ID -> orders',
    order_item_id     INT           NOT NULL COMMENT '订单内商品行序号（1起）',
    product_id        VARCHAR(32)   NULL     COMMENT '商品ID -> products',
    seller_id         VARCHAR(32)   NULL     COMMENT '卖家ID -> sellers',
    shipping_limit_date DATETIME    NULL     COMMENT '卖家发货期限时间',
    price             DECIMAL(10,2) NULL     COMMENT '商品单价（BRL）',
    freight_value     DECIMAL(10,2) NULL     COMMENT '该行运费（BRL）',
    PRIMARY KEY (order_id, order_item_id),
    KEY idx_order_items_product_id (product_id),
    KEY idx_order_items_seller_id (seller_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '订单商品明细表：粒度=订单商品行';

-- -------------------------------------------------------------
-- 4. order_payments：订单支付记录（一单可多条，组合支付）
-- -------------------------------------------------------------
DROP TABLE IF EXISTS order_payments;
CREATE TABLE order_payments (
    order_id             VARCHAR(32)   NOT NULL COMMENT '订单ID -> orders',
    payment_sequential   INT           NOT NULL COMMENT '支付序号（1起）',
    payment_type         VARCHAR(20)   NULL     COMMENT '支付方式',
    payment_installments INT           NULL     COMMENT '分期数',
    payment_value        DECIMAL(10,2) NULL     COMMENT '支付金额（BRL）',
    PRIMARY KEY (order_id, payment_sequential)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '订单支付表：粒度=一条支付记录';

-- -------------------------------------------------------------
-- 5. order_reviews：订单评价（一单可有多条评价记录）
-- -------------------------------------------------------------
DROP TABLE IF EXISTS order_reviews;
CREATE TABLE order_reviews (
    review_id                VARCHAR(32) NOT NULL COMMENT '评价ID（主键，唯一性待质量检查验证）',
    order_id                 VARCHAR(32) NOT NULL COMMENT '订单ID -> orders',
    review_score             TINYINT     NULL     COMMENT '评分（1-5）',
    review_comment_title     VARCHAR(100) NULL    COMMENT '评价标题（大量为空）',
    review_comment_message   TEXT        NULL     COMMENT '评价正文（大量为空）',
    review_creation_date     DATETIME    NULL     COMMENT '评价问卷创建时间',
    review_answer_timestamp  DATETIME    NULL     COMMENT '用户提交评价时间',
    PRIMARY KEY (review_id),
    KEY idx_order_reviews_order_id (order_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '订单评价表：粒度=一条评价';

-- -------------------------------------------------------------
-- 6. products：商品维度
-- -------------------------------------------------------------
DROP TABLE IF EXISTS products;
CREATE TABLE products (
    product_id                  VARCHAR(32) NOT NULL COMMENT '商品ID（主键）',
    product_category_name       VARCHAR(64) NULL     COMMENT '商品类别（葡萄牙语）-> translation',
    product_name_lenght         INT         NULL     COMMENT '商品名长度（原始拼写 lenght）',
    product_description_lenght  INT         NULL     COMMENT '商品描述长度',
    product_photos_qty          INT         NULL     COMMENT '图片数量',
    product_weight_g            INT         NULL     COMMENT '重量（克）',
    product_length_cm           INT         NULL     COMMENT '长度（厘米）',
    product_height_cm           INT         NULL     COMMENT '高度（厘米）',
    product_width_cm            INT         NULL     COMMENT '宽度（厘米）',
    PRIMARY KEY (product_id),
    KEY idx_products_category (product_category_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '商品表：粒度=一个商品';

-- -------------------------------------------------------------
-- 7. sellers：卖家维度
-- -------------------------------------------------------------
DROP TABLE IF EXISTS sellers;
CREATE TABLE sellers (
    seller_id              VARCHAR(32) NOT NULL COMMENT '卖家ID（主键）',
    seller_zip_code_prefix VARCHAR(5)  NULL     COMMENT '卖家邮编前5位',
    seller_city            VARCHAR(64) NULL     COMMENT '卖家城市',
    seller_state           CHAR(2)     NULL     COMMENT '卖家州',
    PRIMARY KEY (seller_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '卖家表：粒度=一个卖家';

-- -------------------------------------------------------------
-- 8. geolocation：地理位置（邮编有重复坐标，无主键；不进入核心宽表）
-- -------------------------------------------------------------
DROP TABLE IF EXISTS geolocation;
CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(5)  NOT NULL COMMENT '邮编前5位',
    geolocation_lat             DOUBLE      NULL     COMMENT '纬度',
    geolocation_lng             DOUBLE      NULL     COMMENT '经度',
    geolocation_city            VARCHAR(64) NULL     COMMENT '城市',
    geolocation_state           CHAR(2)     NULL     COMMENT '州',
    KEY idx_geolocation_zip (geolocation_zip_code_prefix),
    KEY idx_geolocation_city (geolocation_city)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '地理位置表：粒度=邮编-坐标记录（存在重复）';

-- -------------------------------------------------------------
-- 9. translation：商品类别葡英翻译
-- -------------------------------------------------------------
DROP TABLE IF EXISTS translation;
CREATE TABLE translation (
    product_category_name         VARCHAR(64) NOT NULL COMMENT '类别名（葡萄牙语，主键）',
    product_category_name_english VARCHAR(64) NULL     COMMENT '类别名（英文）',
    PRIMARY KEY (product_category_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '类别翻译表：粒度=一个类别';
