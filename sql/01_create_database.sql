-- =============================================================
-- 01_create_database.sql
-- 目的：创建项目数据库 olist_ecommerce
-- 口径：统一使用 utf8mb4 字符集（城市/类别字段含葡萄牙语变音符号）
-- 可重复执行：CREATE DATABASE IF NOT EXISTS
-- =============================================================

CREATE DATABASE IF NOT EXISTS olist_ecommerce
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE olist_ecommerce;
