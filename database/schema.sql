-- ============================================================
-- Coffee Grade Identification (CGI) — Database Schema
-- MySQL 8.0+  |  XAMPP-compatible
-- ============================================================

CREATE DATABASE IF NOT EXISTS cgi_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cgi_db;

-- ------------------------------------------------------------
-- 1. Cooperatives
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cooperatives (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(150)    NOT NULL,
    location      VARCHAR(255)    NOT NULL,
    contact       VARCHAR(100)    NULL,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 2. Users  (Admin | officer | farmer)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100)    NOT NULL,
    email           VARCHAR(150)    NOT NULL UNIQUE,
    password_hash   VARCHAR(255)    NOT NULL,
    role            ENUM('admin','officer','farmer') NOT NULL DEFAULT 'farmer',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 3. Farmers  (extended profile for farmer-role users)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS farmers (
    id                INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id           INT UNSIGNED    NOT NULL UNIQUE,
    cooperative_id    INT UNSIGNED    NULL,
    contact_number    VARCHAR(30)     NULL,
    address           VARCHAR(255)    NULL,
    created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_farmers_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_farmers_cooperative
        FOREIGN KEY (cooperative_id) REFERENCES cooperatives(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 4. Inspections
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inspections (
    id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    farmer_id             INT UNSIGNED    NOT NULL,
    officer_id            INT UNSIGNED    NOT NULL,
    sample_weight_g       DECIMAL(7,2)    NOT NULL COMMENT 'Measured weight in grams (must be 340-360 g)',
    total_beans_detected  INT UNSIGNED    NOT NULL DEFAULT 0,
    image_path            VARCHAR(500)    NOT NULL COMMENT 'Relative path to uploaded image in static/uploads/',
    grade                 ENUM('extra_class','class_i','class_ii') NOT NULL,
    over_threshold_flag   TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '1 = at least one defect exceeded Class II upper bound',
    notes                 TEXT            NULL,
    created_at            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_inspections_farmer
        FOREIGN KEY (farmer_id) REFERENCES farmers(id),
    CONSTRAINT fk_inspections_officer
        FOREIGN KEY (officer_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 5. Defect Results  (one row per defect class per inspection)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS defect_results (
    id                INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    inspection_id     INT UNSIGNED    NOT NULL,
    defect_type       ENUM(
                          'black_bean',
                          'moldy_infested',
                          'immature',
                          'broken',
                          'dried_cherry',
                          'foreign_matter'
                      ) NOT NULL,
    bean_count        INT UNSIGNED    NOT NULL DEFAULT 0,
    defect_percentage DECIMAL(6,3)    NOT NULL DEFAULT 0.000,
    assigned_class    ENUM('extra_class','class_i','class_ii') NOT NULL,
    over_threshold    TINYINT(1)      NOT NULL DEFAULT 0,

    CONSTRAINT fk_defect_inspection
        FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE CASCADE,
    UNIQUE KEY uq_inspection_defect (inspection_id, defect_type)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 6. Pricing Config  (grade multipliers, configurable by Admin/Officer)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pricing_config (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    grade         ENUM('extra_class','class_i','class_ii') NOT NULL UNIQUE,
    multiplier    DECIMAL(5,4)    NOT NULL DEFAULT 1.0000 COMMENT 'Price = market_rate x multiplier x weight_kg',
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by    INT UNSIGNED    NULL COMMENT 'FK to users.id of last editor',

    CONSTRAINT fk_pricing_updated_by
        FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 7. Transactions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    inspection_id   INT UNSIGNED    NOT NULL UNIQUE COMMENT 'One inspection = one transaction',
    weight_kg       DECIMAL(7,4)    NOT NULL,
    price_per_kg    DECIMAL(10,4)   NOT NULL,
    total_price     DECIMAL(12,4)   NOT NULL,
    currency        VARCHAR(10)     NOT NULL DEFAULT 'PHP',
    price_source    ENUM('api','manual') NOT NULL DEFAULT 'api',
    notes           TEXT            NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_transactions_inspection
        FOREIGN KEY (inspection_id) REFERENCES inspections(id)
) ENGINE=InnoDB;
