-- ============================================================
-- CGI Migration 002 — User Management Enhancements
-- Additive changes only. Safe to run on an existing cgi_db.
-- ============================================================

USE cgi_db;

-- ------------------------------------------------------------
-- 1. users — role-prefixed display ID (SA00001 / CO00001 / FF00001)
--    Generated at registration time; stored for fast display.
-- ------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS user_id_display VARCHAR(10) UNIQUE NULL
        COMMENT 'Role-prefixed sequential ID: SA00001 | CO00001 | FF00001'
        AFTER id;

-- ------------------------------------------------------------
-- 2. users — last successful login timestamp
--    Updated by the /api/auth/login endpoint on every
--    successful authentication.  NULL means never logged in.
-- ------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_login_at DATETIME NULL
        COMMENT 'Timestamp of last successful login (Asia/Manila)'
        AFTER updated_at;

-- ------------------------------------------------------------
-- 3. Back-fill user_id_display for existing rows
--    Uses role-specific counters so each prefix is independent.
-- ------------------------------------------------------------
UPDATE users u
JOIN (
    SELECT id,
           CASE role
               WHEN 'admin'   THEN CONCAT('SA', LPAD(ROW_NUMBER() OVER (PARTITION BY role ORDER BY id), 5, '0'))
               WHEN 'officer' THEN CONCAT('CO', LPAD(ROW_NUMBER() OVER (PARTITION BY role ORDER BY id), 5, '0'))
               ELSE                 CONCAT('FF', LPAD(ROW_NUMBER() OVER (PARTITION BY role ORDER BY id), 5, '0'))
           END AS uid
    FROM users
) src ON src.id = u.id
SET u.user_id_display = src.uid
WHERE u.user_id_display IS NULL;
