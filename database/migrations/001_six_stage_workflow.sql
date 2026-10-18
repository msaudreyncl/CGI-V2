-- ============================================================
-- CGI Migration 001 — Six-Stage Transaction Workflow
-- Additive changes only. Safe to run on an existing cgi_db.
-- ============================================================

USE cgi_db;

-- ------------------------------------------------------------
-- 1. New table: pending_transactions
--    Tracks in-progress workflow state from Prepare through
--    the moment analysis is finalized.  Only finalized,
--    analyzed data is written to the inspections table.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_transactions (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    txn_number      VARCHAR(20)  NOT NULL UNIQUE
                        COMMENT 'CGI-YYYYMMDD-XXXXXX — generated at Prepare stage',
    farmer_id       INT UNSIGNED NOT NULL,
    officer_id      INT UNSIGNED NOT NULL,
    weight_g        DECIMAL(7,2) NULL
                        COMMENT 'Populated at Weight stage (must be 340–360 g)',
    status          ENUM(
                        'prepared',
                        'weighed',
                        'captured',
                        'analyzed',
                        'completed'
                    ) NOT NULL DEFAULT 'prepared',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pending_farmer
        FOREIGN KEY (farmer_id)  REFERENCES farmers(id),
    CONSTRAINT fk_pending_officer
        FOREIGN KEY (officer_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- 2. inspections — new columns for dual-view workflow
-- ------------------------------------------------------------

-- Transaction number carried forward from pending_transactions
ALTER TABLE inspections
    ADD COLUMN IF NOT EXISTS txn_number VARCHAR(20) UNIQUE NULL
        COMMENT 'CGI-YYYYMMDD-XXXXXX — copied from pending_transactions'
        AFTER notes;

-- Raw View B image path
ALTER TABLE inspections
    ADD COLUMN IF NOT EXISTS image_path_b VARCHAR(500) NULL
        COMMENT 'Relative path to raw View B image in static/uploads/'
        AFTER image_path;

-- YOLOv8-annotated View A image path
ALTER TABLE inspections
    ADD COLUMN IF NOT EXISTS image_path_annotated_a VARCHAR(500) NULL
        COMMENT 'Relative path to annotated View A image (bounding boxes)'
        AFTER image_path_b;

-- YOLOv8-annotated View B image path
ALTER TABLE inspections
    ADD COLUMN IF NOT EXISTS image_path_annotated_b VARCHAR(500) NULL
        COMMENT 'Relative path to annotated View B image (bounding boxes)'
        AFTER image_path_annotated_a;

-- ------------------------------------------------------------
-- 3. transactions — workflow status + print tracking
-- ------------------------------------------------------------

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS status ENUM(
                                        'in_progress',
                                        'analyzed',
                                        'completed'
                                    ) NOT NULL DEFAULT 'in_progress'
        COMMENT 'Workflow stage of this transaction'
        AFTER notes;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS print_status ENUM(
                                              'pending',
                                              'printed',
                                              'failed'
                                          ) NOT NULL DEFAULT 'pending'
        COMMENT 'Thermal receipt print outcome'
        AFTER status;
